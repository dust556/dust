"""Portfolio construction and holding-period returns.

The two decisions here that most affect the headline number:

**Weighting.** Equal weight is the default. Weighting by the composite score
would be weighting by a number that has never been validated -- the score
exists to order a shortlist for a human, not to size positions. Equal weight
also keeps the result attributable to the *screen* rather than to a weighting
scheme layered on top.

**Missing end-of-period prices.** This is where backtests quietly lie. A name
that disappears from the price file is usually a delisting, and delistings
skew heavily toward failure; dropping those positions silently is how a
strategy "returns" 20% a year on paper. Every policy here is biased in some
direction, so the choice is explicit, and the count of affected positions is
reported on every single run rather than buried.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from ..models import PricePoint, ScreenResult

# What to do when a holding has no price at the end of the period.
MISSING_PRICE_POLICIES = ("drop", "zero", "flat")


@dataclass
class Position:
    ticker: str
    weight: float
    entry_price: Optional[float] = None
    exit_price: Optional[float] = None
    entry_date: Optional[dt.date] = None
    exit_date: Optional[dt.date] = None
    period_return: Optional[float] = None
    # Set when the exit price had to be imputed rather than observed.
    resolution: str = "observed"


@dataclass
class Period:
    """One rebalance period: what was held and what it returned."""

    rebalance_date: dt.date
    exit_date: dt.date
    positions: List[Position] = field(default_factory=list)
    portfolio_return: Optional[float] = None
    benchmark_return: Optional[float] = None
    candidates: int = 0
    screened: int = 0
    # Positions whose exit price was missing, by resolution.
    unresolved: int = 0
    turnover: Optional[float] = None
    notes: List[str] = field(default_factory=list)

    @property
    def excess_return(self) -> Optional[float]:
        if self.portfolio_return is None or self.benchmark_return is None:
            return None
        return self.portfolio_return - self.benchmark_return


def price_on_or_before(
    history: Sequence[PricePoint], date: dt.date
) -> Optional[PricePoint]:
    """Last close at or before ``date``; None if the series starts later."""
    chosen: Optional[PricePoint] = None
    for point in history:
        if point.date <= date:
            if chosen is None or point.date > chosen.date:
                chosen = point
        # History is normally sorted, but do not rely on it.
    return chosen


def stale_by_days(point: Optional[PricePoint], date: dt.date) -> Optional[int]:
    if point is None:
        return None
    return (date - point.date).days


def select_holdings(
    ranked: Sequence[ScreenResult], max_holdings: Optional[int] = None
) -> List[ScreenResult]:
    """Take the top N of an already-ranked list."""
    if max_holdings is None or max_holdings <= 0:
        return list(ranked)
    return list(ranked[:max_holdings])


def assign_weights(
    holdings: Sequence[ScreenResult], scheme: str = "equal"
) -> Dict[str, float]:
    """Map each holding to a portfolio weight summing to 1."""
    if not holdings:
        return {}
    if scheme == "equal":
        weight = 1.0 / len(holdings)
        return {h.ticker: weight for h in holdings}
    if scheme == "score":
        scores = {h.ticker: (h.composite_score or 0.0) for h in holdings}
        total = sum(scores.values())
        if total <= 0:
            # Every score zero or missing: fall back rather than divide by zero.
            weight = 1.0 / len(holdings)
            return {h.ticker: weight for h in holdings}
        return {ticker: score / total for ticker, score in scores.items()}
    raise ValueError(f"unknown weighting scheme: {scheme}")


def compute_position_return(
    position: Position, policy: str
) -> Position:
    """Fill ``period_return`` according to the missing-price policy."""
    if position.entry_price is None or position.entry_price <= 0:
        position.period_return = None
        position.resolution = "no_entry_price"
        return position

    if position.exit_price is not None and position.exit_price > 0:
        position.period_return = position.exit_price / position.entry_price - 1.0
        position.resolution = "observed"
        return position

    if policy == "zero":
        # Assume the position was wiped out. Pessimistic, and the only policy
        # that cannot flatter the result.
        position.period_return = -1.0
        position.resolution = "imputed_total_loss"
    elif policy == "flat":
        position.period_return = 0.0
        position.resolution = "imputed_flat"
    else:  # "drop"
        position.period_return = None
        position.resolution = "dropped"
    return position


def build_period(
    rebalance_date: dt.date,
    exit_date: dt.date,
    ranked: Sequence[ScreenResult],
    price_lookup,
    *,
    max_holdings: Optional[int] = None,
    weighting: str = "equal",
    missing_price_policy: str = "drop",
    previous_weights: Optional[Dict[str, float]] = None,
    max_price_staleness_days: int = 10,
) -> Period:
    """Form the portfolio at ``rebalance_date`` and settle it at ``exit_date``.

    ``price_lookup(ticker)`` returns that company's price history.
    """
    if missing_price_policy not in MISSING_PRICE_POLICIES:
        raise ValueError(
            f"unknown missing_price_policy {missing_price_policy!r}; "
            f"expected one of {MISSING_PRICE_POLICIES}"
        )

    period = Period(
        rebalance_date=rebalance_date,
        exit_date=exit_date,
        candidates=len(ranked),
    )
    holdings = select_holdings(ranked, max_holdings)
    weights = assign_weights(holdings, weighting)

    for result in holdings:
        history = price_lookup(result.ticker) or []
        entry = price_on_or_before(history, rebalance_date)
        exit_point = price_on_or_before(history, exit_date)

        # A quote from long before the rebalance date is not a tradeable
        # entry price; treat it as absent rather than pretend it is current.
        entry_staleness = stale_by_days(entry, rebalance_date)
        if entry_staleness is not None and entry_staleness > max_price_staleness_days:
            entry = None

        # The same test on the exit side, and it is the one that matters.
        # When a company delists, its last close simply stops updating, so
        # `price_on_or_before` keeps returning that stale quote for every
        # subsequent period -- silently settling the position at its final
        # traded price forever. That is the missing-price case wearing a
        # disguise, and without this check the policy below never fires.
        exit_staleness = stale_by_days(exit_point, exit_date)
        if exit_staleness is not None and exit_staleness > max_price_staleness_days:
            exit_point = None

        # An exit quote that predates the entry cannot settle the period.
        if exit_point is not None and entry is not None and exit_point.date <= entry.date:
            exit_point = None

        position = Position(
            ticker=result.ticker,
            weight=weights.get(result.ticker, 0.0),
            entry_price=entry.close if entry else None,
            exit_price=exit_point.close if exit_point else None,
            entry_date=entry.date if entry else None,
            exit_date=exit_point.date if exit_point else None,
        )
        period.positions.append(compute_position_return(position, missing_price_policy))

    period.unresolved = sum(
        1 for p in period.positions if p.resolution != "observed"
    )
    if period.unresolved:
        period.notes.append(
            f"{period.unresolved} of {len(period.positions)} positions had no "
            f"usable exit price (policy: {missing_price_policy})"
        )

    period.portfolio_return = _weighted_return(period.positions)
    period.turnover = _turnover(weights, previous_weights)
    return period


def _weighted_return(positions: Sequence[Position]) -> Optional[float]:
    """Weighted return over positions that resolved.

    Weights are renormalised across the resolved positions so a dropped name
    does not silently count as a zero return -- it is excluded, which is what
    'drop' means, and the exclusion is visible in ``unresolved``.
    """
    usable = [p for p in positions if p.period_return is not None and p.weight > 0]
    if not usable:
        return None
    total_weight = sum(p.weight for p in usable)
    if total_weight <= 0:
        return None
    return sum(p.weight * p.period_return for p in usable) / total_weight


def _turnover(
    weights: Dict[str, float], previous: Optional[Dict[str, float]]
) -> Optional[float]:
    """One-sided turnover: half the sum of absolute weight changes."""
    if previous is None:
        return None
    tickers = set(weights) | set(previous)
    return 0.5 * sum(
        abs(weights.get(t, 0.0) - previous.get(t, 0.0)) for t in tickers
    )
