"""Condition 4 -- interest-bearing debt / EBITDA at or below 3x.

The brief's reasoning is a funding-cost argument rather than a solvency one:
small caps borrow at wider spreads and roll debt in smaller, less liquid
markets, so a leveraged small cap is structurally the first to be squeezed
when rates rise. The ceiling is a filter against that fragility.

Two deliberate choices:

* **Gross debt, not net.** The brief says 有利子負債 (interest-bearing debt).
  Cash can be spent, pledged, or trapped in a foreign subsidiary; the
  obligation cannot. Net debt is computed and reported alongside, and
  ``leverage.use_net_debt`` switches the gate if you disagree.
* **Reported EBITDA, not adjusted.** Add-backs are management's opinion of
  which costs were unusual. A leverage test is the last place to accept that.
"""

from __future__ import annotations

from typing import List

from ..config import Config
from ..metrics import cash_and_investments, ebitda, net_debt, total_debt
from ..models import CompanyFinancials, CriterionResult, Verdict
from ..util.stats import ramp, safe_div
from .base import insufficient

KEY = "leverage"
LABEL = "Interest-bearing debt / EBITDA within ceiling"


class LeverageCriterion:
    key = KEY
    label = LABEL

    def evaluate(self, company: CompanyFinancials, config: Config) -> CriterionResult:
        settings = config.leverage
        basis = "net debt" if settings.use_net_debt else "interest-bearing debt"
        threshold = f"{basis} / EBITDA <= {settings.max_debt_to_ebitda:.1f}x"

        annuals = company.annual_periods()
        if not annuals:
            return insufficient(KEY, LABEL, ["annual financials"], threshold)
        latest = annuals[-1]

        gross = total_debt(latest)
        net = net_debt(latest)
        earnings = ebitda(latest)
        debt = net if settings.use_net_debt else gross

        if debt is None:
            return insufficient(KEY, LABEL, ["debt balances"], threshold)
        if earnings is None:
            return insufficient(KEY, LABEL, ["EBITDA (needs operating income)"], threshold)

        reasons: List[str] = []
        detail = {
            "total_debt": gross,
            "net_debt": net,
            "cash_and_investments": cash_and_investments(latest),
            "ebitda": earnings,
            "operating_income": latest.operating_income,
            "depreciation_amortization": latest.depreciation_amortization,
            "period_end": latest.end,
            "basis": basis,
        }

        # A company with no debt clears a debt ceiling by construction.
        if debt <= 0:
            reasons.append(
                f"no {basis} outstanding; the leverage ceiling is met trivially"
            )
            if net is not None and net < 0:
                reasons.append(f"net cash position of ${abs(net) / 1e6:,.0f}M")
            detail["ratio"] = 0.0
            return CriterionResult(
                key=KEY,
                label=LABEL,
                verdict=Verdict.PASS if settings.debt_free_passes else Verdict.FAIL,
                score=1.0,
                value=0.0,
                threshold=threshold,
                detail=detail,
                reasons=reasons,
            )

        if earnings <= 0:
            # Debt outstanding and no earnings to service it from: the
            # condition is failed, not undecidable.
            detail["ratio"] = None
            reasons.append(
                f"EBITDA is ${earnings / 1e6:,.0f}M (not positive) while "
                f"${debt / 1e6:,.0f}M of {basis} is outstanding"
            )
            verdict = (
                Verdict.FAIL
                if settings.treat_negative_ebitda_as_fail
                else Verdict.INSUFFICIENT_DATA
            )
            return CriterionResult(
                key=KEY,
                label=LABEL,
                verdict=verdict,
                score=0.0 if verdict is Verdict.FAIL else None,
                value=None,
                threshold=threshold,
                detail=detail,
                reasons=reasons,
            )

        ratio = safe_div(debt, earnings)
        if ratio is None:
            return insufficient(KEY, LABEL, ["debt / EBITDA"], threshold)
        detail["ratio"] = ratio

        passed = ratio <= settings.max_debt_to_ebitda
        reasons.append(
            f"{basis} / EBITDA is {ratio:.2f}x against a {settings.max_debt_to_ebitda:.1f}x ceiling"
        )
        if net is not None and gross is not None and net < gross:
            net_ratio = safe_div(net, earnings)
            if net_ratio is not None:
                reasons.append(f"net debt / EBITDA is {net_ratio:.2f}x")
                detail["net_ratio"] = net_ratio

        # Lower is better: full marks at zero leverage, zero at the ceiling.
        score = ramp(ratio, settings.max_debt_to_ebitda, 0.0)

        return CriterionResult(
            key=KEY,
            label=LABEL,
            verdict=Verdict.PASS if passed else Verdict.FAIL,
            score=score,
            value=ratio,
            threshold=threshold,
            detail=detail,
            reasons=reasons,
        )
