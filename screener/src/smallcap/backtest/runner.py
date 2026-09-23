"""The backtest loop.

At each rebalance date the screen is re-run with ``--as-of`` set to that
date, the survivors are formed into a portfolio, and the portfolio is held
until the next rebalance date. Nothing from the future enters the decision.

**What this cannot fix: survivorship bias.** The universe comes from the
provider's *current* ticker list. Companies that went bankrupt, were taken
private, or were acquired between the start date and today are simply not in
it. Because failures leave the list and successes stay, a backtest run this
way is biased upward, and the bias is largest over exactly the long horizons
that look most convincing. Running it on a point-in-time universe file (one
snapshot per rebalance date, built from listings at the time) is the only
real fix; ``--universe-history`` accepts one. Without that, every report says
so at the top, because a survivorship-biased result presented without the
caveat is worse than no result.
"""

from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence

from ..config import Config
from ..criteria import ALL_CRITERIA, CRITERION_KEYS
from ..engine import ScreeningEngine
from ..models import PricePoint
from .calendar import FREQUENCIES, rebalance_dates
from .factors import DEFAULT_FACTORS, FactorData, RISK_FREE_COLUMN
from .performance import (
    FactorRegression,
    PerformanceStats,
    factor_regression,
    summarise_performance,
)
from .portfolio import Period, build_period

LOGGER = logging.getLogger("smallcap.backtest")


@dataclass
class BacktestConfig:
    start: dt.date
    end: dt.date
    frequency: str = "quarterly"
    reporting_lag_days: int = 75
    max_holdings: Optional[int] = None
    weighting: str = "equal"
    missing_price_policy: str = "drop"
    benchmark: str = "SPY"
    factors: Optional[str] = None
    factor_names: List[str] = field(default_factory=lambda: list(DEFAULT_FACTORS))
    # A universe snapshot per rebalance date, {ISO date: [tickers]}. Supplying
    # one is the only way to remove survivorship bias.
    universe_history: Optional[Dict[str, List[str]]] = None

    def periods_per_year(self) -> float:
        return 12.0 / FREQUENCIES[self.frequency]


@dataclass
class BacktestResult:
    config: Dict
    periods: List[Period] = field(default_factory=list)
    stats: Optional[PerformanceStats] = None
    regression: Optional[FactorRegression] = None
    ablation: Dict[str, PerformanceStats] = field(default_factory=dict)
    biases: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class Backtester:
    def __init__(
        self,
        provider,
        config: Optional[Config] = None,
        backtest: Optional[BacktestConfig] = None,
    ):
        self.provider = provider
        self.config = config or Config()
        self.backtest = backtest
        self._price_cache: Dict[str, List[PricePoint]] = {}

    # ------------------------------------------------------------------
    def price_history(self, ticker: str) -> List[PricePoint]:
        """Full (un-rewound) price history, used to settle positions.

        Settling a period that has already been *entered* needs prices after
        the rebalance date, so this deliberately does not apply ``as_of``.
        It is never consulted by the screen itself.
        """
        key = ticker.upper()
        if key in self._price_cache:
            return self._price_cache[key]
        history: List[PricePoint] = []
        try:
            company = self.provider.fetch(key, as_of=None)
            if company.market and company.market.history:
                history = sorted(company.market.history, key=lambda p: p.date)
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("no price history for %s: %s", key, exc)
        self._price_cache[key] = history
        return history

    # ------------------------------------------------------------------
    def universe_at(self, date: dt.date, default: Sequence[str]) -> List[str]:
        """The tickers investable at ``date``."""
        history = self.backtest.universe_history if self.backtest else None
        if not history:
            return list(default)
        # Use the most recent snapshot at or before the rebalance date.
        eligible = [d for d in sorted(history) if dt.date.fromisoformat(d) <= date]
        if not eligible:
            return list(default)
        return list(history[eligible[-1]])

    # ------------------------------------------------------------------
    def run(
        self,
        tickers: Sequence[str],
        criteria: Optional[Sequence] = None,
        progress: Optional[Callable[[int, int, Period], None]] = None,
    ) -> List[Period]:
        """Run the screen at every rebalance date and settle each period."""
        assert self.backtest is not None, "a BacktestConfig is required"
        dates = rebalance_dates(
            self.backtest.start,
            self.backtest.end,
            self.backtest.frequency,
            self.backtest.reporting_lag_days,
        )
        if len(dates) < 2:
            raise ValueError(
                f"{len(dates)} rebalance date(s) between {self.backtest.start} and "
                f"{self.backtest.end}: widen the window or shorten the frequency"
            )

        benchmark_history = self.price_history(self.backtest.benchmark)
        periods: List[Period] = []
        previous_weights: Optional[Dict[str, float]] = None

        # The final date opens no position: there is nothing after it to
        # settle against, so it is the last exit rather than an entry.
        for index, (entry_date, exit_date) in enumerate(zip(dates, dates[1:]), start=1):
            period_config = _config_at(self.config, entry_date)
            engine = ScreeningEngine(self.provider, period_config, criteria=criteria)
            candidates = self.universe_at(entry_date, tickers)
            results = engine.screen(candidates)
            ranked = engine.rank(results)

            period = build_period(
                entry_date,
                exit_date,
                ranked,
                self.price_history,
                max_holdings=self.backtest.max_holdings,
                weighting=self.backtest.weighting,
                missing_price_policy=self.backtest.missing_price_policy,
                previous_weights=previous_weights,
            )
            period.screened = len(results)
            period.benchmark_return = _benchmark_return(
                benchmark_history, entry_date, exit_date
            )
            if period.benchmark_return is None and benchmark_history:
                period.notes.append(
                    f"benchmark {self.backtest.benchmark} had no price for this window"
                )
            if not ranked:
                period.notes.append(
                    "no company cleared the screen; the portfolio was in cash"
                )
                # Cash earns nothing here; the risk-free rate is applied in
                # the factor regression, not silently baked into returns.
                period.portfolio_return = 0.0

            periods.append(period)
            previous_weights = {p.ticker: p.weight for p in period.positions}
            if progress:
                progress(index, len(dates) - 1, period)

        return periods

    # ------------------------------------------------------------------
    def analyse(
        self,
        periods: Sequence[Period],
        factor_data: Optional[FactorData] = None,
    ) -> BacktestResult:
        """Turn a list of settled periods into statistics."""
        assert self.backtest is not None
        per_year = self.backtest.periods_per_year()
        portfolio_returns = [p.portfolio_return for p in periods]
        benchmark_returns = [p.benchmark_return for p in periods]

        stats = summarise_performance(
            portfolio_returns,
            benchmark_returns,
            periods_per_year=per_year,
            risk_free_rate=self.config.returns.risk_free_rate,
            holdings_counts=[len(p.positions) for p in periods],
            turnovers=[p.turnover for p in periods],
        )

        result = BacktestResult(
            config=_backtest_config_dict(self.backtest), periods=list(periods), stats=stats
        )
        result.biases = self._bias_notes(periods)

        if factor_data is not None:
            names = [
                n for n in self.backtest.factor_names if n in factor_data.columns
            ]
            missing = [n for n in self.backtest.factor_names if n not in factor_data.columns]
            factor_rows = []
            risk_free_rows = []
            for period in periods:
                factor_rows.append(
                    factor_data.compound_between(
                        period.rebalance_date, period.exit_date, names
                    )
                    or {}
                )
                risk_free_rows.append(
                    factor_data.risk_free_between(
                        period.rebalance_date, period.exit_date
                    )
                )
            result.regression = factor_regression(
                portfolio_returns,
                factor_rows,
                risk_free_rows,
                periods_per_year=per_year,
                factor_names=names,
            )
            result.regression.warnings.insert(0, factor_data.scale_note)
            if missing:
                result.regression.warnings.append(
                    f"factors not present in the file and therefore not "
                    f"controlled for: {', '.join(missing)}"
                )
            if RISK_FREE_COLUMN not in factor_data.columns:
                result.regression.warnings.append(
                    f"no {RISK_FREE_COLUMN} column: excess returns were computed "
                    "against a zero risk-free rate"
                )
        else:
            result.warnings.append(
                "no factor file supplied: the return below is not adjusted for "
                "market, size or value exposure, so it cannot be attributed to "
                "the screen. Pass --factors to test for alpha."
            )
        return result

    # ------------------------------------------------------------------
    def _bias_notes(self, periods: Sequence[Period]) -> List[str]:
        """Biases that remain in the result, stated whether or not they bind."""
        notes: List[str] = []
        if not (self.backtest and self.backtest.universe_history):
            notes.append(
                "SURVIVORSHIP BIAS: the universe is today's ticker list, so "
                "companies that delisted, failed or were acquired during the "
                "period are absent. Returns are biased upward. Supply "
                "--universe-history with a point-in-time listing per rebalance "
                "date to remove this."
            )
        unresolved = sum(p.unresolved for p in periods)
        if unresolved:
            policy = self.backtest.missing_price_policy if self.backtest else "drop"
            notes.append(
                f"{unresolved} position-periods had no usable exit price and were "
                f"handled with policy '{policy}'"
                + (
                    ". 'drop' excludes them, which flatters the result if they "
                    "are delistings; rerun with --missing-price-policy zero to "
                    "see the pessimistic bound."
                    if policy == "drop"
                    else "."
                )
            )
        notes.append(
            "NO COSTS: returns are gross. Commission, spread and market impact "
            "are not deducted. On a small-cap universe the spread alone can "
            "exceed the excess return being measured."
        )
        notes.append(
            "The thresholds were not fitted to this data, but they were chosen "
            "with knowledge of the published literature. Treat a single "
            "favourable configuration as a hypothesis, not a finding."
        )
        return notes

    # ------------------------------------------------------------------
    def ablation(
        self, tickers: Sequence[str], factor_data: Optional[FactorData] = None
    ) -> Dict[str, PerformanceStats]:
        """Re-run the backtest with each condition removed in turn.

        If dropping a condition leaves performance unchanged, that condition
        is doing no work in this sample -- which is worth knowing before
        defending it. If dropping it *improves* performance, more so.
        """
        results: Dict[str, PerformanceStats] = {}
        for key in CRITERION_KEYS:
            subset = [c for c in ALL_CRITERIA if c.key != key]
            LOGGER.info("ablation: running without %s", key)
            periods = self.run(tickers, criteria=subset)
            analysis = self.analyse(periods, factor_data=factor_data)
            results[f"without_{key}"] = analysis.stats
        return results


# ----------------------------------------------------------------------
def _config_at(config: Config, date: dt.date) -> Config:
    """A copy of the config pinned to one rebalance date."""
    import copy

    pinned = copy.deepcopy(config)
    pinned.as_of = date.isoformat()
    return pinned


def _benchmark_return(
    history: Sequence[PricePoint], start: dt.date, end: dt.date
) -> Optional[float]:
    from .portfolio import price_on_or_before

    entry = price_on_or_before(history, start)
    exit_point = price_on_or_before(history, end)
    if entry is None or exit_point is None or entry.close <= 0:
        return None
    if exit_point.date <= entry.date:
        return None
    return exit_point.close / entry.close - 1.0


def _backtest_config_dict(config: BacktestConfig) -> Dict:
    return {
        "start": config.start.isoformat(),
        "end": config.end.isoformat(),
        "frequency": config.frequency,
        "reporting_lag_days": config.reporting_lag_days,
        "max_holdings": config.max_holdings,
        "weighting": config.weighting,
        "missing_price_policy": config.missing_price_policy,
        "benchmark": config.benchmark,
        "factors": config.factors,
        "factor_names": list(config.factor_names),
        "point_in_time_universe": bool(config.universe_history),
    }
