"""Backtest reporting.

The layout is deliberate: **the biases come first, before any number.** A
reader who stops after the headline CAGR should have already been told why
that CAGR is too high. Putting the caveats in a footnote is how a
survivorship-biased backtest ends up quoted as a fact.
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import asdict
from typing import Dict, List, Optional

from ..models import _jsonable
from .runner import BacktestResult


def _pct(value: Optional[float], digits: int = 2) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.{digits}f}%"


def _num(value: Optional[float], digits: int = 2) -> str:
    if value is None:
        return "n/a"
    return f"{value:.{digits}f}"


def to_json(result: BacktestResult) -> str:
    payload = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "backtest_config": result.config,
        "biases": result.biases,
        "warnings": result.warnings,
        "stats": asdict(result.stats) if result.stats else None,
        "factor_regression": asdict(result.regression) if result.regression else None,
        "ablation": {k: asdict(v) for k, v in result.ablation.items() if v},
        "periods": [_period_dict(p) for p in result.periods],
    }
    return json.dumps(_jsonable(payload), indent=2, ensure_ascii=False)


def _period_dict(period) -> Dict:
    data = asdict(period)
    data["excess_return"] = period.excess_return
    return data


def to_csv(result: BacktestResult) -> str:
    """One row per rebalance period."""
    import csv
    import io

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "rebalance_date",
            "exit_date",
            "holdings",
            "candidates",
            "screened",
            "portfolio_return",
            "benchmark_return",
            "excess_return",
            "unresolved_positions",
            "turnover",
            "tickers",
        ]
    )
    for period in result.periods:
        writer.writerow(
            [
                period.rebalance_date,
                period.exit_date,
                len(period.positions),
                period.candidates,
                period.screened,
                "" if period.portfolio_return is None else f"{period.portfolio_return:.6f}",
                "" if period.benchmark_return is None else f"{period.benchmark_return:.6f}",
                "" if period.excess_return is None else f"{period.excess_return:.6f}",
                period.unresolved,
                "" if period.turnover is None else f"{period.turnover:.4f}",
                " ".join(p.ticker for p in period.positions),
            ]
        )
    return buffer.getvalue()


def to_markdown(result: BacktestResult, max_periods: int = 40) -> str:
    lines: List[str] = ["# Backtest report", ""]
    config = result.config
    lines.append(
        f"{config['start']} to {config['end']} | {config['frequency']} rebalance "
        f"with a {config['reporting_lag_days']}-day reporting lag | "
        f"benchmark {config['benchmark']}"
    )
    lines.append("")

    # ---- Biases first, before any performance number. ----
    lines.append("## Read this before the numbers")
    lines.append("")
    for note in result.biases:
        lines.append(f"- **{note}**")
    for note in result.warnings:
        lines.append(f"- {note}")
    if result.stats:
        for note in result.stats.warnings:
            lines.append(f"- {note}")
    lines.append("")

    stats = result.stats
    if stats:
        lines.append("## Performance")
        lines.append("")
        lines.append("| metric | portfolio | benchmark |")
        lines.append("|---|---:|---:|")
        lines.append(
            f"| total return | {_pct(stats.total_return)} | {_pct(stats.benchmark_total_return)} |"
        )
        lines.append(f"| CAGR | {_pct(stats.cagr)} | {_pct(stats.benchmark_cagr)} |")
        lines.append(f"| annualised volatility | {_pct(stats.annualised_volatility)} | |")
        lines.append(f"| Sharpe | {_num(stats.sharpe)} | |")
        lines.append(f"| max drawdown | {_pct(stats.max_drawdown)} | |")
        lines.append(f"| best / worst period | {_pct(stats.best_period)} / {_pct(stats.worst_period)} | |")
        lines.append("")
        lines.append("| versus benchmark | value |")
        lines.append("|---|---:|")
        lines.append(f"| excess CAGR | {_pct(stats.excess_cagr)} |")
        lines.append(f"| tracking error | {_pct(stats.tracking_error)} |")
        lines.append(f"| information ratio | {_num(stats.information_ratio)} |")
        lines.append(f"| periods beating benchmark | {_pct(stats.win_rate_vs_benchmark)} |")
        lines.append("")
        lines.append("| sample | value |")
        lines.append("|---|---:|")
        lines.append(f"| rebalance periods | {stats.periods} |")
        lines.append(f"| average holdings | {_num(stats.average_holdings)} |")
        lines.append(f"| average turnover | {_pct(stats.average_turnover)} |")
        lines.append("")

    regression = result.regression
    if regression:
        lines.append("## Factor attribution")
        lines.append("")
        lines.append(
            "A small-cap screen is built to load on the size factor, so beating "
            "a broad index is expected whenever small caps do well. Alpha is "
            "what remains after paying for that exposure."
        )
        lines.append("")
        if regression.betas:
            lines.append("| term | coefficient | t-stat |")
            lines.append("|---|---:|---:|")
            lines.append(
                f"| alpha (per period) | {_pct(regression.alpha, 3)} | {_num(regression.alpha_t_stat)} |"
            )
            lines.append(
                f"| alpha (annualised) | {_pct(regression.alpha_annualised)} | |"
            )
            for name, beta in regression.betas.items():
                lines.append(
                    f"| {name} | {_num(beta, 3)} | {_num(regression.t_stats.get(name))} |"
                )
            lines.append("")
            lines.append(
                f"R² {_num(regression.r_squared, 3)} over {regression.observations} observations."
            )
            lines.append("")
        for note in regression.warnings:
            lines.append(f"- {note}")
        lines.append("")

    if result.ablation:
        lines.append("## Condition ablation")
        lines.append("")
        lines.append(
            "Each row removes one condition and re-runs everything else. A "
            "condition whose removal changes nothing is doing no work in this "
            "sample; one whose removal *improves* the result is costing you."
        )
        lines.append("")
        base = result.stats.cagr if result.stats else None
        lines.append("| configuration | CAGR | change | avg holdings |")
        lines.append("|---|---:|---:|---:|")
        if base is not None:
            lines.append(
                f"| all five conditions | {_pct(base)} | — | "
                f"{_num(result.stats.average_holdings)} |"
            )
        for name, stat in result.ablation.items():
            if stat is None:
                continue
            delta = (
                stat.cagr - base if (stat.cagr is not None and base is not None) else None
            )
            change = "n/a" if delta is None else f"{delta * 100:+.2f}pp"
            lines.append(
                f"| {name.replace('_', ' ')} | {_pct(stat.cagr)} | {change} | "
                f"{_num(stat.average_holdings)} |"
            )
        lines.append("")

    lines.append("## Periods")
    lines.append("")
    lines.append("| rebalance | exit | holdings | portfolio | benchmark | excess | names |")
    lines.append("|---|---|---:|---:|---:|---:|---|")
    for period in result.periods[:max_periods]:
        names = ", ".join(p.ticker for p in period.positions) or "(cash)"
        lines.append(
            f"| {period.rebalance_date} | {period.exit_date} | {len(period.positions)} | "
            f"{_pct(period.portfolio_return)} | {_pct(period.benchmark_return)} | "
            f"{_pct(period.excess_return)} | {names[:60]} |"
        )
    if len(result.periods) > max_periods:
        lines.append(f"| ... | | | | | | {len(result.periods) - max_periods} more |")
    lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(
        "A backtest measures what a rule would have produced on one history, "
        "gross of costs, on a universe that excludes the companies that failed. "
        "It is evidence about the past, and weak evidence about the future. "
        "This is research output, not investment advice."
    )
    lines.append("")
    return "\n".join(lines)


def write_reports(out_dir: str, result: BacktestResult) -> Dict[str, str]:
    import os

    os.makedirs(out_dir, exist_ok=True)
    paths = {
        "json": os.path.join(out_dir, "backtest.json"),
        "csv": os.path.join(out_dir, "backtest_periods.csv"),
        "markdown": os.path.join(out_dir, "backtest.md"),
    }
    with open(paths["json"], "w", encoding="utf-8") as handle:
        handle.write(to_json(result))
    with open(paths["csv"], "w", encoding="utf-8", newline="") as handle:
        handle.write(to_csv(result))
    with open(paths["markdown"], "w", encoding="utf-8") as handle:
        handle.write(to_markdown(result))
    return paths


def format_console(result: BacktestResult) -> str:
    stats = result.stats
    lines = []
    for note in result.biases:
        lines.append(f"! {note}")
    lines.append("")
    if stats:
        lines.append(
            f"CAGR {_pct(stats.cagr)} vs benchmark {_pct(stats.benchmark_cagr)} "
            f"(excess {_pct(stats.excess_cagr)})"
        )
        lines.append(
            f"vol {_pct(stats.annualised_volatility)} | Sharpe {_num(stats.sharpe)} | "
            f"max DD {_pct(stats.max_drawdown)} | IR {_num(stats.information_ratio)}"
        )
        lines.append(
            f"{stats.periods} periods | avg {_num(stats.average_holdings)} holdings | "
            f"turnover {_pct(stats.average_turnover)}"
        )
        for note in stats.warnings:
            lines.append(f"  warning: {note}")
    if result.regression and result.regression.betas:
        lines.append(
            f"alpha {_pct(result.regression.alpha_annualised)}/yr "
            f"(t={_num(result.regression.alpha_t_stat)}) after "
            f"{', '.join(result.regression.betas)}"
        )
    return "\n".join(lines)
