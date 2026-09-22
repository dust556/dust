"""Data model shared by providers, criteria and reports.

The shapes here are deliberately provider-agnostic. A provider's only job is
to fill in a ``CompanyFinancials``; the criteria never know whether the
numbers came from SEC EDGAR, a CSV, or a test fixture.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Optional


class Verdict(str, Enum):
    """Outcome of one criterion for one company."""

    PASS = "PASS"
    FAIL = "FAIL"
    # The data needed to decide was not available. Deliberately distinct from
    # FAIL: "we don't know" must never be reported as "it failed".
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


@dataclass
class FinancialPeriod:
    """One reported fiscal period, as filed.

    ``end`` is the period end date, ``fy``/``fp`` the fiscal year and period
    tag (``FY``, ``Q1``..``Q4``), and ``filed`` the date the figure first
    became public -- ``filed`` is what makes point-in-time screening possible.
    """

    end: dt.date
    fy: Optional[int] = None
    fp: Optional[str] = None
    filed: Optional[dt.date] = None
    form: Optional[str] = None
    duration_days: Optional[int] = None

    # Income statement
    revenue: Optional[float] = None
    cost_of_revenue: Optional[float] = None
    gross_profit: Optional[float] = None
    operating_income: Optional[float] = None
    pretax_income: Optional[float] = None
    income_tax_expense: Optional[float] = None
    net_income: Optional[float] = None
    interest_expense: Optional[float] = None

    # Cash flow
    depreciation_amortization: Optional[float] = None
    capex: Optional[float] = None
    acquisitions: Optional[float] = None
    operating_cash_flow: Optional[float] = None

    # Balance sheet (instantaneous, as of ``end``)
    cash_and_equivalents: Optional[float] = None
    short_term_investments: Optional[float] = None
    short_term_debt: Optional[float] = None
    long_term_debt: Optional[float] = None
    total_equity: Optional[float] = None
    total_assets: Optional[float] = None
    current_assets: Optional[float] = None
    current_liabilities: Optional[float] = None

    def is_annual(self) -> bool:
        if self.fp == "FY":
            return True
        if self.duration_days is not None:
            return 300 <= self.duration_days <= 430
        return False

    def is_quarterly(self) -> bool:
        if self.duration_days is not None:
            return 60 <= self.duration_days <= 120
        return self.fp in {"Q1", "Q2", "Q3", "Q4"}


@dataclass
class InsiderHolding:
    """One insider's reported beneficial holding (SEC Form 3/4/5 derived)."""

    owner_name: str
    owner_cik: Optional[str] = None
    is_officer: bool = False
    is_director: bool = False
    is_ten_percent_owner: bool = False
    shares: Optional[float] = None
    as_of: Optional[dt.date] = None
    source_accession: Optional[str] = None


@dataclass
class InsiderOwnership:
    """Aggregated insider ownership for one company."""

    total_shares: Optional[float] = None
    holdings: List[InsiderHolding] = field(default_factory=list)
    # "form345" (computed from ownership filings) or "proxy" (DEF 14A table,
    # the authoritative source) or "manual" (operator-supplied override).
    basis: str = "form345"
    as_of: Optional[dt.date] = None
    notes: List[str] = field(default_factory=list)


@dataclass
class PricePoint:
    date: dt.date
    close: float


@dataclass
class MarketData:
    ticker: str
    price: Optional[float] = None
    price_date: Optional[dt.date] = None
    shares_outstanding: Optional[float] = None
    shares_date: Optional[dt.date] = None
    market_cap: Optional[float] = None
    # Trailing history, used for the beta estimate feeding WACC.
    history: List[PricePoint] = field(default_factory=list)
    beta: Optional[float] = None
    currency: str = "USD"


@dataclass
class CompanyFinancials:
    """Everything the engine knows about one company."""

    ticker: str
    cik: Optional[str] = None
    name: Optional[str] = None
    sic: Optional[str] = None
    sector: Optional[str] = None
    exchange: Optional[str] = None
    periods: List[FinancialPeriod] = field(default_factory=list)
    market: Optional[MarketData] = None
    insiders: Optional[InsiderOwnership] = None
    # Provider-level warnings (missing concept, stale filing, fallback used).
    warnings: List[str] = field(default_factory=list)
    source: str = "unknown"

    def annual_periods(self) -> List[FinancialPeriod]:
        return sorted(
            (p for p in self.periods if p.is_annual()), key=lambda p: p.end
        )

    def quarterly_periods(self) -> List[FinancialPeriod]:
        return sorted(
            (p for p in self.periods if p.is_quarterly()), key=lambda p: p.end
        )

    def latest_annual(self) -> Optional[FinancialPeriod]:
        annuals = self.annual_periods()
        return annuals[-1] if annuals else None


@dataclass
class CriterionResult:
    """One criterion's decision, with the numbers that produced it."""

    key: str
    label: str
    verdict: Verdict
    # 0..1 quality score within the criterion. None when undecidable.
    score: Optional[float] = None
    # The headline number the threshold was applied to.
    value: Optional[float] = None
    threshold: Optional[str] = None
    detail: Dict[str, Any] = field(default_factory=dict)
    reasons: List[str] = field(default_factory=list)
    missing: List[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.verdict is Verdict.PASS


@dataclass
class ScreenResult:
    """The full verdict for one company."""

    ticker: str
    name: Optional[str] = None
    cik: Optional[str] = None
    criteria: List[CriterionResult] = field(default_factory=list)
    composite_score: Optional[float] = None
    passed_count: int = 0
    decided_count: int = 0
    all_passed: bool = False
    data_quality: Optional[float] = None
    warnings: List[str] = field(default_factory=list)
    error: Optional[str] = None
    ai_review: Optional[Dict[str, Any]] = None
    as_of: Optional[str] = None

    def criterion(self, key: str) -> Optional[CriterionResult]:
        for result in self.criteria:
            if result.key == key:
                return result
        return None

    def to_dict(self) -> Dict[str, Any]:
        return _jsonable(asdict(self))


def _jsonable(obj: Any) -> Any:
    """Recursively convert dates and enums so ``json.dumps`` accepts the tree."""
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, (dt.date, dt.datetime)):
        return obj.isoformat()
    return obj
