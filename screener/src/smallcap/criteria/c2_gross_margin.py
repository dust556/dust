"""Condition 2 -- gross margin above 40% *and* improving.

Novy-Marx (2013), "The Other Side of Value", showed gross profitability
predicts returns about as well as book-to-market, and argued it is the
cleanest measure of economic profitability because it sits above the line
where discretionary spending (R&D, advertising, restructuring) muddies the
picture.

The brief adds the part that matters most: direction. A 45% margin falling
two points a year and a 41% margin rising two points a year are very
different businesses, and the level alone cannot tell them apart. So the
criterion gates on three things:

1. the latest margin clears the level threshold;
2. the OLS slope through the annual margin history is positive;
3. the most recent margin is above the year-ago margin (so an improving
   trend cannot be an artefact of old history).

Novy-Marx's own ratio (gross profit / total assets) is reported alongside,
because for an asset-heavy firm the two can point in opposite directions.
"""

from __future__ import annotations

from typing import List

from ..config import Config
from ..metrics import (
    gross_margin,
    gross_margin_series,
    gross_profits_to_assets,
    trailing_twelve_months,
    years_between,
)
from ..models import CompanyFinancials, CriterionResult, Verdict
from ..util.stats import ols_slope, r_squared, ramp
from .base import insufficient

KEY = "gross_margin"
LABEL = "Gross margin above threshold and improving"


class GrossMarginCriterion:
    key = KEY
    label = LABEL

    def evaluate(self, company: CompanyFinancials, config: Config) -> CriterionResult:
        settings = config.gross_margin
        threshold = (
            f"gross margin >= {settings.min_level:.0%} and rising "
            f"(slope >= {settings.min_slope_per_year:+.2%}/yr)"
        )

        annuals = company.annual_periods()
        series = gross_margin_series(annuals)
        if len(series) < settings.min_trend_periods:
            return insufficient(
                KEY,
                LABEL,
                [f"gross margin history ({len(series)} of {settings.min_trend_periods} years)"],
                threshold,
            )

        window = series[-settings.trend_periods :]
        base_date = window[0][0]
        xs = [years_between(base_date, end) for end, _ in window]
        ys = [margin for _, margin in window]

        slope = ols_slope(xs, ys)
        fit = r_squared(xs, ys)
        latest_annual_margin = ys[-1]

        # Prefer a TTM margin for the level test: it is up to three quarters
        # fresher than the last fiscal year.
        quarters = company.quarterly_periods()
        ttm = trailing_twelve_months(quarters)
        ttm_margin = gross_margin(ttm) if ttm is not None else None
        prior_ttm = trailing_twelve_months(quarters, end_index=-5)
        prior_ttm_margin = gross_margin(prior_ttm) if prior_ttm is not None else None

        level = ttm_margin if ttm_margin is not None else latest_annual_margin
        level_basis = "TTM" if ttm_margin is not None else "latest fiscal year"

        if ttm_margin is not None and prior_ttm_margin is not None:
            recent_delta = ttm_margin - prior_ttm_margin
            delta_basis = "TTM vs year-ago TTM"
        elif len(ys) >= 2:
            recent_delta = ys[-1] - ys[-2]
            delta_basis = "latest fiscal year vs prior year"
        else:
            recent_delta = None
            delta_basis = "unavailable"

        if slope is None or recent_delta is None:
            return insufficient(
                KEY, LABEL, ["gross margin trend"], threshold
            )

        reasons: List[str] = []
        level_ok = level >= settings.min_level
        slope_ok = slope >= settings.min_slope_per_year
        delta_ok = recent_delta >= settings.min_recent_delta

        reasons.append(
            f"gross margin {level:.1%} ({level_basis}) vs {settings.min_level:.0%} threshold"
            f" -- {'above' if level_ok else 'below'}"
        )
        reasons.append(
            f"trend {slope:+.2%}/yr over {len(window)} years"
            f" (R^2 {fit:.2f})" if fit is not None else f"trend {slope:+.2%}/yr over {len(window)} years"
        )
        reasons.append(
            f"most recent change {recent_delta:+.2%} ({delta_basis})"
            f" -- {'improving' if delta_ok else 'not improving'}"
        )

        passed = level_ok and slope_ok and delta_ok

        # Score blends how far above the level threshold the margin sits with
        # how convincingly it is rising.
        level_score = ramp(level, settings.min_level, settings.min_level + 0.25)
        slope_score = ramp(slope, settings.min_slope_per_year, settings.min_slope_per_year + 0.04)
        score = None
        if level_score is not None and slope_score is not None:
            score = 0.6 * level_score + 0.4 * slope_score
            # A noisy trend should not score like a clean one.
            if fit is not None:
                score *= 0.7 + 0.3 * max(0.0, min(1.0, fit))

        gpa = gross_profits_to_assets(annuals[-1]) if annuals else None
        if settings.report_gross_profits_to_assets and gpa is not None:
            reasons.append(
                f"Novy-Marx gross profits / assets: {gpa:.1%}"
            )

        return CriterionResult(
            key=KEY,
            label=LABEL,
            verdict=Verdict.PASS if passed else Verdict.FAIL,
            score=score,
            value=level,
            threshold=threshold,
            detail={
                "gross_margin": level,
                "gross_margin_basis": level_basis,
                "latest_annual_margin": latest_annual_margin,
                "ttm_margin": ttm_margin,
                "prior_ttm_margin": prior_ttm_margin,
                "slope_per_year": slope,
                "r_squared": fit,
                "recent_delta": recent_delta,
                "recent_delta_basis": delta_basis,
                "gross_profits_to_assets": gpa,
                "history": [
                    {"period_end": end, "gross_margin": margin} for end, margin in window
                ],
                "checks": {
                    "level": level_ok,
                    "slope": slope_ok,
                    "recent_improvement": delta_ok,
                },
            },
            reasons=reasons,
        )
