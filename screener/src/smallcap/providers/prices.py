"""Price history, market price and the beta estimate that feeds WACC.

Two sources, in order of preference:

* a local CSV directory (``--prices-dir``), which is what you want for a
  reproducible research run -- prices pinned to a file, not to whatever a web
  endpoint returns today;
* Stooq's free daily CSV endpoint, for convenience when you just want to run
  the screen against today's market.

Both produce the same :class:`MarketData` shape. If neither is available the
market-cap criterion reports ``INSUFFICIENT_DATA`` rather than guessing.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import os
from typing import Dict, List, Optional

from ..models import MarketData, PricePoint
from ..util.http import HttpClient, HTTPError
from ..util.stats import ols_slope, stdev

STOOQ_URL = "https://stooq.com/q/d/l/?s={symbol}.us&i=d"
DEFAULT_BENCHMARK = "SPY"


def _parse_price_csv(text: str) -> List[PricePoint]:
    """Parse a Date,Open,High,Low,Close[,Volume] daily CSV."""
    points: List[PricePoint] = []
    reader = csv.DictReader(io.StringIO(text))
    for row in reader:
        raw_date = row.get("Date") or row.get("date")
        raw_close = row.get("Close") or row.get("close") or row.get("Adj Close")
        if not raw_date or not raw_close:
            continue
        try:
            date = dt.date.fromisoformat(raw_date[:10])
            close = float(raw_close)
        except ValueError:
            continue
        if close <= 0:
            continue
        points.append(PricePoint(date=date, close=close))
    points.sort(key=lambda p: p.date)
    return points


class PriceProvider:
    """Supplies the last close on or before ``as_of``, plus trailing history."""

    name = "prices"

    def __init__(
        self,
        http: Optional[HttpClient] = None,
        prices_dir: Optional[str] = None,
        benchmark: str = DEFAULT_BENCHMARK,
        history_days: int = 730,
        allow_network: bool = True,
    ):
        self.http = http
        self.prices_dir = prices_dir
        self.benchmark = benchmark
        self.history_days = history_days
        self.allow_network = allow_network
        self._cache: Dict[str, List[PricePoint]] = {}

    # ------------------------------------------------------------------
    def history(self, ticker: str) -> List[PricePoint]:
        key = ticker.upper()
        if key in self._cache:
            return self._cache[key]

        points: List[PricePoint] = []
        if self.prices_dir:
            path = os.path.join(self.prices_dir, f"{key}.csv")
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as handle:
                    points = _parse_price_csv(handle.read())
        if not points and self.allow_network and self.http is not None:
            try:
                text = self.http.get_text(
                    STOOQ_URL.format(symbol=key.lower()), accept="text/csv"
                )
                points = _parse_price_csv(text)
            except HTTPError:
                points = []

        self._cache[key] = points
        return points

    # ------------------------------------------------------------------
    def enrich(self, market: MarketData, as_of: Optional[dt.date] = None) -> MarketData:
        """Fill price, price date, trailing history and beta."""
        points = self.history(market.ticker)
        if not points:
            return market

        if as_of is not None:
            points = [p for p in points if p.date <= as_of]
        if not points:
            return market

        market.price = points[-1].close
        market.price_date = points[-1].date

        start = points[-1].date - dt.timedelta(days=self.history_days)
        market.history = [p for p in points if p.date >= start]
        market.beta = self.estimate_beta(market.history, as_of=as_of)
        return market

    # ------------------------------------------------------------------
    def estimate_beta(
        self, history: List[PricePoint], as_of: Optional[dt.date] = None
    ) -> Optional[float]:
        """OLS beta of weekly stock returns on benchmark returns.

        Weekly rather than daily: small caps trade thinly, and daily data
        drags beta toward zero through non-synchronous trading (the Scholes-
        Williams problem). Weekly sampling blunts that without needing a
        lead-lag correction.
        """
        if len(history) < 60:
            return None
        benchmark = self.history(self.benchmark)
        if as_of is not None:
            benchmark = [p for p in benchmark if p.date <= as_of]
        if len(benchmark) < 60:
            return None

        stock_weekly = _weekly_returns(history)
        bench_weekly = _weekly_returns(benchmark)
        common = sorted(set(stock_weekly) & set(bench_weekly))
        if len(common) < 30:
            return None
        xs = [bench_weekly[week] for week in common]
        ys = [stock_weekly[week] for week in common]
        # Guard against a degenerate series (a stock that never moved).
        if not stdev(ys):
            return None
        return ols_slope(xs, ys)


def _weekly_returns(points: List[PricePoint]) -> Dict[tuple, float]:
    """Last close of each ISO week -> that week's return."""
    by_week: Dict[tuple, PricePoint] = {}
    for point in points:
        iso = point.date.isocalendar()
        key = (iso[0], iso[1])
        existing = by_week.get(key)
        if existing is None or point.date > existing.date:
            by_week[key] = point
    weeks = sorted(by_week)
    returns: Dict[tuple, float] = {}
    for previous, current in zip(weeks, weeks[1:]):
        prior_close = by_week[previous].close
        if prior_close > 0:
            returns[current] = by_week[current].close / prior_close - 1.0
    return returns
