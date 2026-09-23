"""Backtesting: run the screen through history and measure what it produced.

The point of this package is not to produce a good-looking equity curve. It
is to answer one question -- does anything survive the benchmark, the known
factors, and an honest accounting of the biases? -- and to make the biases
impossible to omit from the answer.
"""

from .calendar import rebalance_dates
from .factors import FactorData, load_factors
from .performance import FactorRegression, PerformanceStats
from .portfolio import Period, Position
from .runner import BacktestConfig, BacktestResult, Backtester

__all__ = [
    "Backtester",
    "BacktestConfig",
    "BacktestResult",
    "Period",
    "Position",
    "PerformanceStats",
    "FactorRegression",
    "FactorData",
    "load_factors",
    "rebalance_dates",
]
