"""The five screening conditions.

Order matters only for presentation: every criterion is evaluated for every
company so the report can show *why* a company failed, not just that it did.
"""

from .base import Criterion, insufficient
from .c1_market_cap import MarketCapCriterion
from .c2_gross_margin import GrossMarginCriterion
from .c3_returns import ReturnsCriterion
from .c4_leverage import LeverageCriterion
from .c5_insider import InsiderOwnershipCriterion

ALL_CRITERIA = [
    MarketCapCriterion(),
    GrossMarginCriterion(),
    ReturnsCriterion(),
    LeverageCriterion(),
    InsiderOwnershipCriterion(),
]

CRITERION_KEYS = [c.key for c in ALL_CRITERIA]

__all__ = [
    "Criterion",
    "insufficient",
    "MarketCapCriterion",
    "GrossMarginCriterion",
    "ReturnsCriterion",
    "LeverageCriterion",
    "InsiderOwnershipCriterion",
    "ALL_CRITERIA",
    "CRITERION_KEYS",
]
