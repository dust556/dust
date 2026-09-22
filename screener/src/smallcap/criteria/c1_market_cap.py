"""Condition 1 -- market capitalisation between $500M and $3B.

Rationale from the brief: Fama and French (1992) documented the size
premium, and the economic story behind it here is coverage. Below roughly
$3bn a company sits outside most institutional mandates and sell-side
coverage thins out, so prices are formed by fewer informed participants.
Above it, the informational edge is gone.

What the code can and cannot check: it verifies the band. It cannot verify
that coverage is actually thin -- analyst-count data is not in any free feed.
``detail`` therefore carries the raw inputs so a human can sanity-check the
figure against a data terminal.
"""

from __future__ import annotations

from ..config import Config
from ..models import CompanyFinancials, CriterionResult, Verdict
from .base import insufficient

KEY = "market_cap"
LABEL = "Market capitalisation in the small-cap band"


class MarketCapCriterion:
    key = KEY
    label = LABEL

    def evaluate(self, company: CompanyFinancials, config: Config) -> CriterionResult:
        settings = config.market_cap
        threshold = (
            f"${settings.min_usd / 1e9:.1f}B <= market cap <= "
            f"${settings.max_usd / 1e9:.1f}B"
        )
        market = company.market
        missing = []
        if market is None:
            missing.append("market data")
        else:
            if market.price is None:
                missing.append("price")
            if market.shares_outstanding is None:
                missing.append("shares outstanding")
        if missing and (market is None or market.market_cap is None):
            return insufficient(KEY, LABEL, missing, threshold)

        assert market is not None
        cap = market.market_cap
        if cap is None and market.price is not None and market.shares_outstanding is not None:
            cap = market.price * market.shares_outstanding
        if cap is None:
            return insufficient(KEY, LABEL, missing or ["market cap"], threshold)

        in_band = settings.min_usd <= cap <= settings.max_usd
        reasons = []
        if in_band:
            reasons.append(
                f"market cap ${cap / 1e9:.2f}B is inside the "
                f"${settings.min_usd / 1e9:.1f}B-${settings.max_usd / 1e9:.1f}B band"
            )
        elif cap < settings.min_usd:
            reasons.append(
                f"market cap ${cap / 1e9:.2f}B is below the ${settings.min_usd / 1e9:.1f}B floor "
                "(micro-cap: liquidity and disclosure quality fall away)"
            )
        else:
            reasons.append(
                f"market cap ${cap / 1e9:.2f}B exceeds the ${settings.max_usd / 1e9:.1f}B ceiling "
                "(institutional coverage, so no informational edge)"
            )

        # Score highest at the middle of the band, where the coverage argument
        # is strongest, tapering toward both edges.
        if in_band:
            span = settings.max_usd - settings.min_usd
            position = (cap - settings.min_usd) / span if span > 0 else 0.5
            score = 1.0 - abs(position - 0.45) / 0.55
            score = max(0.0, min(1.0, score))
        else:
            score = 0.0

        if market.shares_date and market.price_date:
            gap = abs((market.price_date - market.shares_date).days)
            if gap > settings.shares_max_age_days:
                reasons.append(
                    f"share count is {gap} days from the price date; market cap may be stale"
                )

        return CriterionResult(
            key=KEY,
            label=LABEL,
            verdict=Verdict.PASS if in_band else Verdict.FAIL,
            score=score,
            value=cap,
            threshold=threshold,
            detail={
                "market_cap_usd": cap,
                "price": market.price,
                "price_date": market.price_date,
                "shares_outstanding": market.shares_outstanding,
                "shares_date": market.shares_date,
                "exchange": company.exchange,
            },
            reasons=reasons,
        )
