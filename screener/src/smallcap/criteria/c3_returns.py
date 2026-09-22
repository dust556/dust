"""Condition 3 -- ROIC above the cost of capital, with a high reinvestment rate.

Mauboussin's argument, repeated across the Credit Suisse / Morgan Stanley
"Counterpoint Global" notes: over long horizons the shareholder's return
converges on the rate at which the business compounds capital, and that rate
is the product of two terms --

    intrinsic growth = ROIC x reinvestment rate

A high return with nothing to reinvest in returns cash and compounds nothing.
A high reinvestment rate at a return below the cost of capital destroys value
faster the more it invests. Both terms are therefore gated, plus the spread
over WACC that decides which of those two worlds the company is in.

Multi-year averaging (default three years) is used throughout, because a
single year's capex or acquisition can swing the reinvestment rate by more
than the threshold itself.
"""

from __future__ import annotations

from typing import List

from ..config import Config
from ..metrics import (
    implied_growth,
    invested_capital,
    nopat,
    reinvestment_rate,
    roic,
    wacc,
)
from ..models import CompanyFinancials, CriterionResult, Verdict
from ..util.stats import mean, ramp
from .base import insufficient

KEY = "returns"
LABEL = "ROIC above cost of capital with high reinvestment"


class ReturnsCriterion:
    key = KEY
    label = LABEL

    def evaluate(self, company: CompanyFinancials, config: Config) -> CriterionResult:
        settings = config.returns
        threshold = (
            f"ROIC - WACC >= {settings.min_roic_minus_wacc:+.1%}, "
            f"ROIC >= {settings.min_roic:.0%}, "
            f"reinvestment >= {settings.min_reinvestment_rate:.0%}, "
            f"ROIC x reinvestment >= {settings.min_implied_growth:.0%}"
        )

        annuals = company.annual_periods()
        if len(annuals) < settings.min_lookback_years + 1:
            return insufficient(
                KEY,
                LABEL,
                [
                    f"annual history ({len(annuals)} periods; "
                    f"{settings.min_lookback_years + 1} needed)"
                ],
                threshold,
            )

        # Pairs of (period, prior period), newest last.
        pairs = list(zip(annuals[:-1], annuals[1:]))[-settings.lookback_years :]
        roic_values: List[float] = []
        reinvestment_values: List[float] = []
        per_year = []
        for prior, period in pairs:
            year_roic = roic(period, settings, prior)
            year_reinvestment = reinvestment_rate(period, prior, settings)
            if year_roic is not None:
                roic_values.append(year_roic)
            if year_reinvestment is not None:
                reinvestment_values.append(year_reinvestment)
            per_year.append(
                {
                    "period_end": period.end,
                    "roic": year_roic,
                    "reinvestment_rate": year_reinvestment,
                    "nopat": nopat(period, settings),
                    "invested_capital": invested_capital(period),
                }
            )

        missing = []
        if not roic_values:
            missing.append("ROIC (needs operating income and invested capital)")
        if not reinvestment_values:
            missing.append("reinvestment rate (needs capex or invested-capital change)")
        if missing:
            return insufficient(KEY, LABEL, missing, threshold)

        avg_roic = mean(roic_values)
        avg_reinvestment = mean(reinvestment_values)
        latest, prior = annuals[-1], annuals[-2]

        market_cap = company.market.market_cap if company.market else None
        beta = company.market.beta if company.market else None
        breakdown = wacc(latest, prior, market_cap, beta, settings)

        if breakdown.wacc is None:
            return insufficient(
                KEY,
                LABEL,
                ["WACC (needs a market value of equity)"],
                threshold,
                reasons=[
                    "cost of capital could not be computed without a market capitalisation"
                ],
            )

        spread = avg_roic - breakdown.wacc
        growth = implied_growth(avg_roic, avg_reinvestment)

        spread_ok = spread >= settings.min_roic_minus_wacc
        roic_ok = avg_roic >= settings.min_roic
        reinvestment_ok = avg_reinvestment >= settings.min_reinvestment_rate
        growth_ok = growth is not None and growth >= settings.min_implied_growth
        passed = spread_ok and roic_ok and reinvestment_ok and growth_ok

        reasons: List[str] = [
            f"ROIC {avg_roic:.1%} ({len(roic_values)}-year average) vs WACC "
            f"{breakdown.wacc:.1%} -> spread {spread:+.1%}",
            f"reinvestment rate {avg_reinvestment:.0%} "
            f"({'at or above' if reinvestment_ok else 'below'} the "
            f"{settings.min_reinvestment_rate:.0%} threshold)",
        ]
        if growth is not None:
            reasons.append(
                f"implied compounding (ROIC x reinvestment) {growth:.1%}"
            )
        reasons.append(
            f"cost of equity {breakdown.cost_of_equity:.1%} "
            f"(beta {breakdown.beta:.2f}, {breakdown.beta_source}), "
            f"after-tax cost of debt "
            f"{breakdown.cost_of_debt * (1 - (breakdown.tax_rate or 0)):.1%}"
        )
        if breakdown.beta_source == "default":
            reasons.append(
                "beta was not estimable from price history; the small-cap default was used"
            )
        if breakdown.floored:
            reasons.append(
                f"computed WACC was below the {settings.wacc_floor:.0%} floor and was raised to it"
            )

        spread_score = ramp(spread, settings.min_roic_minus_wacc, settings.min_roic_minus_wacc + 0.15)
        reinvestment_score = ramp(
            avg_reinvestment, settings.min_reinvestment_rate, settings.min_reinvestment_rate + 0.50
        )
        growth_score = ramp(growth, settings.min_implied_growth, settings.min_implied_growth + 0.15)
        parts = [p for p in (spread_score, reinvestment_score, growth_score) if p is not None]
        score = sum(parts) / len(parts) if parts else None

        return CriterionResult(
            key=KEY,
            label=LABEL,
            verdict=Verdict.PASS if passed else Verdict.FAIL,
            score=score,
            value=spread,
            threshold=threshold,
            detail={
                "roic_avg": avg_roic,
                "roic_latest": roic_values[-1] if roic_values else None,
                "wacc": breakdown.wacc,
                "spread": spread,
                "reinvestment_rate_avg": avg_reinvestment,
                "implied_growth": growth,
                "cost_of_equity": breakdown.cost_of_equity,
                "cost_of_debt": breakdown.cost_of_debt,
                "beta": breakdown.beta,
                "beta_source": breakdown.beta_source,
                "tax_rate": breakdown.tax_rate,
                "equity_value": breakdown.equity_value,
                "debt_value": breakdown.debt_value,
                "wacc_floored": breakdown.floored,
                "reinvestment_method": settings.reinvestment_method,
                "by_year": per_year,
                "checks": {
                    "spread": spread_ok,
                    "roic_level": roic_ok,
                    "reinvestment": reinvestment_ok,
                    "implied_growth": growth_ok,
                },
            },
            reasons=reasons,
        )
