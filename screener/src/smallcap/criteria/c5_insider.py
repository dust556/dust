"""Condition 5 -- management holds at least 10% of the shares.

Jensen and Meckling (1976) formalised the agency problem: a manager who is
not an owner bears none of the cost of the decisions they take. Equity
ownership realigns that, and the effect is largest in small caps, where a
single executive's stake is a meaningful fraction of the company and where
external monitoring (analysts, activist funds, index scrutiny) is thinnest.

**The data caveat is the important part of this file.** The authoritative
number is the beneficial-ownership table in the annual DEF 14A proxy
statement, which is prose in an HTML exhibit, not tagged data. What this
engine computes instead is the sum of the most recent Form 3/4/5 holdings
per insider, which is a *lower bound*: it misses insiders who have not filed
since their initial Form 3, shares held through vehicles reported only in the
proxy, and unexercised options. A company just under the threshold on this
basis deserves a manual look at the proxy rather than automatic rejection --
which is why a near-miss is flagged explicitly in the reasons.
"""

from __future__ import annotations

from typing import List

from ..config import Config
from ..models import CompanyFinancials, CriterionResult, Verdict
from ..util.stats import ramp, safe_div
from .base import insufficient

KEY = "insider"
LABEL = "Insider ownership at or above threshold"

# Within this distance of the threshold, the Form 3/4/5 lower bound is not
# precise enough to reject on; the result says so.
NEAR_MISS_BAND = 0.03


class InsiderOwnershipCriterion:
    key = KEY
    label = LABEL

    def evaluate(self, company: CompanyFinancials, config: Config) -> CriterionResult:
        settings = config.insider
        threshold = f"insider ownership >= {settings.min_ownership:.0%}"

        ownership = company.insiders
        shares_outstanding = (
            company.market.shares_outstanding if company.market else None
        )

        missing = []
        if ownership is None or ownership.total_shares is None:
            missing.append("insider holdings")
        if shares_outstanding is None:
            missing.append("shares outstanding")
        if missing:
            return insufficient(KEY, LABEL, missing, threshold)

        assert ownership is not None
        fraction = safe_div(ownership.total_shares, shares_outstanding)
        if fraction is None:
            return insufficient(KEY, LABEL, ["insider ownership fraction"], threshold)

        passed = fraction >= settings.min_ownership
        reasons: List[str] = [
            f"insiders hold {ownership.total_shares:,.0f} of "
            f"{shares_outstanding:,.0f} shares ({fraction:.1%}) "
            f"against a {settings.min_ownership:.0%} threshold"
        ]

        officers = [h for h in ownership.holdings if h.is_officer or h.is_director]
        if officers:
            top = officers[0]
            top_fraction = safe_div(top.shares, shares_outstanding)
            if top_fraction is not None:
                reasons.append(
                    f"largest insider holding: {top.owner_name} at {top_fraction:.1%}"
                )
            reasons.append(f"{len(officers)} officers/directors with reported holdings")

        if ownership.basis == "form345":
            reasons.append(
                "computed from Forms 3/4/5, which understate true insider "
                "ownership; the DEF 14A proxy table is authoritative"
            )
            if not passed and fraction >= settings.min_ownership - NEAR_MISS_BAND:
                reasons.append(
                    f"NEAR MISS: {fraction:.1%} is within {NEAR_MISS_BAND:.0%} of the "
                    "threshold on a lower-bound measure -- check the proxy before rejecting"
                )
        if not settings.include_ten_percent_owners:
            reasons.append(
                "external 10% holders are excluded; this measures management "
                "alignment, not concentration of the register"
            )
        reasons.extend(ownership.notes)

        # Alignment improves steeply from 0 to about 30%; beyond that the
        # marginal incentive effect flattens and entrenchment risk rises.
        score = ramp(fraction, 0.0, 0.30)

        return CriterionResult(
            key=KEY,
            label=LABEL,
            verdict=Verdict.PASS if passed else Verdict.FAIL,
            score=score,
            value=fraction,
            threshold=threshold,
            detail={
                "insider_fraction": fraction,
                "insider_shares": ownership.total_shares,
                "shares_outstanding": shares_outstanding,
                "basis": ownership.basis,
                "as_of": ownership.as_of,
                "holder_count": len(ownership.holdings),
                "near_miss": (
                    not passed and fraction >= settings.min_ownership - NEAR_MISS_BAND
                ),
                "holders": [
                    {
                        "name": h.owner_name,
                        "shares": h.shares,
                        "fraction": safe_div(h.shares, shares_outstanding),
                        "is_officer": h.is_officer,
                        "is_director": h.is_director,
                        "as_of": h.as_of,
                    }
                    for h in ownership.holdings[:10]
                ],
            },
            reasons=reasons,
        )
