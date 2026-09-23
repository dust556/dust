"""Performance statistics and factor attribution.

The headline number of a backtest (total return) is the least informative
thing in it. What decides whether a screen is worth trading is whether the
return survives (a) the benchmark, (b) the known factors, and (c) an honest
count of how few positions and periods produced it.

All of this is computed on **period** returns at the rebalance frequency, so
a quarterly run has roughly four observations a year. With five years of
data that is twenty points: enough to describe, nowhere near enough to
conclude. ``sample_warnings`` exists to keep that in view.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from ..util.stats import mean, stdev

# Below this many observations, a t-statistic on quarterly data is
# decorative rather than evidential.
MIN_USEFUL_PERIODS = 20


@dataclass
class PerformanceStats:
    periods: int = 0
    total_return: Optional[float] = None
    cagr: Optional[float] = None
    annualised_volatility: Optional[float] = None
    sharpe: Optional[float] = None
    max_drawdown: Optional[float] = None
    best_period: Optional[float] = None
    worst_period: Optional[float] = None
    hit_rate: Optional[float] = None
    average_holdings: Optional[float] = None
    average_turnover: Optional[float] = None
    # Versus the benchmark
    benchmark_total_return: Optional[float] = None
    benchmark_cagr: Optional[float] = None
    excess_cagr: Optional[float] = None
    tracking_error: Optional[float] = None
    information_ratio: Optional[float] = None
    win_rate_vs_benchmark: Optional[float] = None
    warnings: List[str] = field(default_factory=list)


@dataclass
class FactorRegression:
    """OLS of excess portfolio returns on factor returns."""

    alpha: Optional[float] = None
    alpha_annualised: Optional[float] = None
    alpha_t_stat: Optional[float] = None
    betas: Dict[str, float] = field(default_factory=dict)
    t_stats: Dict[str, float] = field(default_factory=dict)
    r_squared: Optional[float] = None
    observations: int = 0
    factors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


# ----------------------------------------------------------------------
def compound(returns: Sequence[float]) -> Optional[float]:
    """Cumulative return from a series of period returns."""
    usable = [r for r in returns if r is not None]
    if not usable:
        return None
    total = 1.0
    for value in usable:
        total *= 1.0 + value
        if total <= 0:
            # A total wipe-out; compounding further is meaningless.
            return -1.0
    return total - 1.0


def annualise(total_return: Optional[float], years: float) -> Optional[float]:
    if total_return is None or years <= 0:
        return None
    base = 1.0 + total_return
    if base <= 0:
        return -1.0
    return base ** (1.0 / years) - 1.0


def max_drawdown(returns: Sequence[float]) -> Optional[float]:
    """Largest peak-to-trough decline of the cumulative series."""
    usable = [r for r in returns if r is not None]
    if not usable:
        return None
    level = 1.0
    peak = 1.0
    worst = 0.0
    for value in usable:
        level *= 1.0 + value
        peak = max(peak, level)
        if peak > 0:
            worst = min(worst, level / peak - 1.0)
    return worst


def summarise_performance(
    period_returns: Sequence[Optional[float]],
    benchmark_returns: Sequence[Optional[float]],
    periods_per_year: float,
    risk_free_rate: float = 0.0,
    holdings_counts: Optional[Sequence[int]] = None,
    turnovers: Optional[Sequence[Optional[float]]] = None,
) -> PerformanceStats:
    """Describe a return series against its benchmark."""
    portfolio = [r for r in period_returns if r is not None]
    stats = PerformanceStats(periods=len(portfolio))
    if not portfolio:
        stats.warnings.append("no period produced a return; nothing to measure")
        return stats

    years = len(portfolio) / periods_per_year if periods_per_year > 0 else 0.0
    stats.total_return = compound(portfolio)
    stats.cagr = annualise(stats.total_return, years)
    stats.best_period = max(portfolio)
    stats.worst_period = min(portfolio)
    stats.max_drawdown = max_drawdown(portfolio)
    stats.hit_rate = sum(1 for r in portfolio if r > 0) / len(portfolio)

    period_vol = stdev(portfolio)
    if period_vol is not None and periods_per_year > 0:
        stats.annualised_volatility = period_vol * math.sqrt(periods_per_year)
        if stats.annualised_volatility and stats.cagr is not None:
            stats.sharpe = (stats.cagr - risk_free_rate) / stats.annualised_volatility

    # Benchmark comparison uses only periods where both series exist.
    paired = [
        (p, b)
        for p, b in zip(period_returns, benchmark_returns)
        if p is not None and b is not None
    ]
    if paired:
        bench = [b for _, b in paired]
        port = [p for p, _ in paired]
        bench_years = len(paired) / periods_per_year if periods_per_year > 0 else 0.0
        stats.benchmark_total_return = compound(bench)
        stats.benchmark_cagr = annualise(stats.benchmark_total_return, bench_years)
        if stats.cagr is not None and stats.benchmark_cagr is not None:
            stats.excess_cagr = stats.cagr - stats.benchmark_cagr
        active = [p - b for p, b in zip(port, bench)]
        active_vol = stdev(active)
        if active_vol is not None and periods_per_year > 0:
            stats.tracking_error = active_vol * math.sqrt(periods_per_year)
            active_mean = mean(active)
            if stats.tracking_error and active_mean is not None:
                stats.information_ratio = (
                    active_mean * periods_per_year
                ) / stats.tracking_error
        stats.win_rate_vs_benchmark = sum(1 for a in active if a > 0) / len(active)

    if holdings_counts:
        stats.average_holdings = mean([float(c) for c in holdings_counts])
    if turnovers:
        stats.average_turnover = mean([t for t in turnovers if t is not None])

    stats.warnings.extend(
        sample_warnings(len(portfolio), stats.average_holdings, periods_per_year)
    )
    return stats


def sample_warnings(
    periods: int, average_holdings: Optional[float], periods_per_year: float
) -> List[str]:
    """State plainly when the sample is too small to support a conclusion."""
    warnings: List[str] = []
    if periods < MIN_USEFUL_PERIODS:
        years = periods / periods_per_year if periods_per_year else 0
        warnings.append(
            f"only {periods} rebalance periods ({years:.1f} years): far too few to "
            "distinguish skill from luck. Treat every statistic below as "
            "descriptive, not evidential."
        )
    if average_holdings is not None and average_holdings < 5:
        warnings.append(
            f"average of {average_holdings:.1f} holdings per period: the result is "
            "driven by a handful of names and is mostly idiosyncratic risk, "
            "not the screen."
        )
    return warnings


# ----------------------------------------------------------------------
# Multivariate OLS (stdlib only)
# ----------------------------------------------------------------------
def solve_linear_system(matrix: List[List[float]], rhs: List[float]) -> Optional[List[float]]:
    """Gaussian elimination with partial pivoting. None if singular."""
    size = len(matrix)
    augmented = [row[:] + [rhs[i]] for i, row in enumerate(matrix)]
    for column in range(size):
        pivot_row = max(range(column, size), key=lambda r: abs(augmented[r][column]))
        if abs(augmented[pivot_row][column]) < 1e-12:
            return None  # singular: collinear factors
        augmented[column], augmented[pivot_row] = augmented[pivot_row], augmented[column]
        pivot = augmented[column][column]
        for row in range(column + 1, size):
            factor = augmented[row][column] / pivot
            if factor == 0:
                continue
            for col in range(column, size + 1):
                augmented[row][col] -= factor * augmented[column][col]
    solution = [0.0] * size
    for row in range(size - 1, -1, -1):
        total = augmented[row][size]
        for col in range(row + 1, size):
            total -= augmented[row][col] * solution[col]
        solution[row] = total / augmented[row][row]
    return solution


def ols_multivariate(
    y: Sequence[float], columns: Dict[str, Sequence[float]]
) -> Optional[Dict[str, object]]:
    """Regress ``y`` on the named columns plus an intercept.

    Returns coefficients, t-statistics and R^2. The t-statistics assume
    independent, homoskedastic residuals; with overlapping or autocorrelated
    period returns they are optimistic. Callers say so in their output.
    """
    names = list(columns)
    observations = len(y)
    predictors = len(names) + 1
    if observations <= predictors:
        return None

    # Design matrix with a leading intercept column.
    design = [[1.0] + [float(columns[name][i]) for name in names] for i in range(observations)]

    # Normal equations: (X'X) b = X'y
    xtx = [
        [sum(design[r][i] * design[r][j] for r in range(observations)) for j in range(predictors)]
        for i in range(predictors)
    ]
    xty = [sum(design[r][i] * y[r] for r in range(observations)) for i in range(predictors)]
    coefficients = solve_linear_system(xtx, xty)
    if coefficients is None:
        return None

    fitted = [
        sum(coefficients[i] * design[r][i] for i in range(predictors))
        for r in range(observations)
    ]
    residuals = [y[r] - fitted[r] for r in range(observations)]
    mean_y = sum(y) / observations
    ss_total = sum((value - mean_y) ** 2 for value in y)
    ss_residual = sum(r * r for r in residuals)
    degrees_of_freedom = observations - predictors
    sigma_squared = ss_residual / degrees_of_freedom if degrees_of_freedom > 0 else None

    t_stats: List[Optional[float]] = [None] * predictors
    if sigma_squared is not None and sigma_squared > 0:
        # Standard errors need the diagonal of (X'X)^-1, obtained by solving
        # against each unit vector rather than inverting the whole matrix.
        for i in range(predictors):
            unit = [1.0 if j == i else 0.0 for j in range(predictors)]
            column = solve_linear_system([row[:] for row in xtx], unit)
            if column is None:
                continue
            variance = sigma_squared * column[i]
            if variance > 0:
                t_stats[i] = coefficients[i] / math.sqrt(variance)

    return {
        "intercept": coefficients[0],
        "intercept_t": t_stats[0],
        "coefficients": {name: coefficients[i + 1] for i, name in enumerate(names)},
        "t_stats": {name: t_stats[i + 1] for i, name in enumerate(names)},
        "r_squared": (1.0 - ss_residual / ss_total) if ss_total > 0 else None,
        "observations": observations,
    }


def factor_regression(
    period_returns: Sequence[Optional[float]],
    factor_returns: Sequence[Dict[str, float]],
    risk_free_returns: Sequence[Optional[float]],
    periods_per_year: float,
    factor_names: Optional[Sequence[str]] = None,
) -> FactorRegression:
    """Regress excess portfolio returns on factor returns.

    A positive raw return proves nothing on its own: a small-cap screen is
    *designed* to load on the size factor, so it should beat a broad index
    whenever small caps do. Alpha here is what is left after paying for that
    exposure, which is the only part attributable to the screen itself.
    """
    rows = []
    for portfolio, factors, risk_free in zip(
        period_returns, factor_returns, risk_free_returns
    ):
        if portfolio is None or not factors:
            continue
        rows.append((portfolio - (risk_free or 0.0), factors))

    result = FactorRegression()
    if not rows:
        result.warnings.append("no overlapping factor observations")
        return result

    names = list(factor_names) if factor_names else sorted(rows[0][1])
    usable = [(excess, f) for excess, f in rows if all(n in f for n in names)]
    if not usable:
        result.warnings.append(
            f"factor file does not cover the requested factors: {names}"
        )
        return result

    y = [excess for excess, _ in usable]
    columns = {name: [f[name] for _, f in usable] for name in names}
    fit = ols_multivariate(y, columns)
    result.observations = len(usable)
    result.factors = names
    if fit is None:
        result.warnings.append(
            "regression could not be solved: too few observations, or "
            "collinear factors"
        )
        return result

    result.alpha = float(fit["intercept"])
    result.alpha_t_stat = fit["intercept_t"]
    result.alpha_annualised = (1.0 + result.alpha) ** periods_per_year - 1.0
    result.betas = {k: float(v) for k, v in fit["coefficients"].items()}
    result.t_stats = {k: v for k, v in fit["t_stats"].items()}
    result.r_squared = fit["r_squared"]
    if result.observations < MIN_USEFUL_PERIODS:
        result.warnings.append(
            f"{result.observations} observations: the t-statistics below are "
            "not meaningful at this sample size"
        )
    result.warnings.append(
        "t-statistics assume independent, homoskedastic residuals; they are "
        "optimistic if period returns are autocorrelated"
    )
    return result
