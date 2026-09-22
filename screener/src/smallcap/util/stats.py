"""Numeric helpers.

Everything here is stdlib-only and total: a computation that cannot be made
returns ``None`` rather than raising or silently producing a wrong number.
A screening engine that quietly turns missing data into ``0.0`` will happily
recommend a company it knows nothing about, so ``None`` is propagated all the
way to the criterion, which then reports ``INSUFFICIENT_DATA``.
"""

from __future__ import annotations

import math
from typing import Iterable, Optional, Sequence

Number = Optional[float]


def safe_div(numerator: Number, denominator: Number) -> Number:
    """Divide, returning None when the result would be meaningless."""
    if numerator is None or denominator is None:
        return None
    if denominator == 0:
        return None
    try:
        value = numerator / denominator
    except (TypeError, ZeroDivisionError):
        return None
    if math.isnan(value) or math.isinf(value):
        return None
    return value


def safe_sub(a: Number, b: Number) -> Number:
    if a is None or b is None:
        return None
    return a - b


def safe_add(*values: Number) -> Number:
    """Sum, treating None as unknown (not zero) -> the sum is unknown."""
    total = 0.0
    for value in values:
        if value is None:
            return None
        total += value
    return total


def sum_present(*values: Number) -> Number:
    """Sum the values that are present; None if every value is missing.

    Used where a missing component genuinely means "this company has none of
    that" -- e.g. a balance sheet that reports no short-term debt line at all.
    """
    present = [v for v in values if v is not None]
    if not present:
        return None
    return float(sum(present))


def mean(values: Sequence[Number]) -> Number:
    present = [v for v in values if v is not None]
    if not present:
        return None
    return sum(present) / len(present)


def average_balance(ending: Number, beginning: Number) -> Number:
    """Average a balance-sheet stock over a period.

    Flow/stock ratios such as ROIC mix an income-statement flow with a
    balance-sheet stock; averaging the opening and closing balance keeps the
    two consistent. Falls back to whichever endpoint exists.
    """
    if ending is not None and beginning is not None:
        return (ending + beginning) / 2.0
    return ending if ending is not None else beginning


def ols_slope(xs: Sequence[float], ys: Sequence[float]) -> Number:
    """Ordinary-least-squares slope of ys on xs.

    Returns None when fewer than two usable points exist or when xs has no
    variance (a vertical fit has no defined slope).
    """
    pairs = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
    n = len(pairs)
    if n < 2:
        return None
    mean_x = sum(p[0] for p in pairs) / n
    mean_y = sum(p[1] for p in pairs) / n
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in pairs)
    denominator = sum((x - mean_x) ** 2 for x, _ in pairs)
    if denominator == 0:
        return None
    return numerator / denominator


def r_squared(xs: Sequence[float], ys: Sequence[float]) -> Number:
    """Goodness of fit of the OLS line, used to grade how clean a trend is."""
    pairs = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
    n = len(pairs)
    if n < 3:
        return None
    slope = ols_slope([p[0] for p in pairs], [p[1] for p in pairs])
    if slope is None:
        return None
    mean_x = sum(p[0] for p in pairs) / n
    mean_y = sum(p[1] for p in pairs) / n
    intercept = mean_y - slope * mean_x
    ss_tot = sum((y - mean_y) ** 2 for _, y in pairs)
    ss_res = sum((y - (slope * x + intercept)) ** 2 for x, y in pairs)
    if ss_tot == 0:
        return None
    return 1.0 - ss_res / ss_tot


def stdev(values: Sequence[float]) -> Number:
    present = [v for v in values if v is not None]
    if len(present) < 2:
        return None
    avg = sum(present) / len(present)
    variance = sum((v - avg) ** 2 for v in present) / (len(present) - 1)
    return math.sqrt(variance)


def clamp(value: Number, low: float, high: float) -> Number:
    if value is None:
        return None
    return max(low, min(high, value))


def ramp(value: Number, zero_at: float, one_at: float) -> Number:
    """Map a raw metric onto 0..1 linearly between two anchor points.

    ``zero_at`` may be greater than ``one_at`` (an inverted metric such as
    leverage, where lower is better).
    """
    if value is None:
        return None
    if zero_at == one_at:
        return 1.0 if value >= one_at else 0.0
    return clamp((value - zero_at) / (one_at - zero_at), 0.0, 1.0)


def pct(value: Number, digits: int = 2) -> Optional[str]:
    if value is None:
        return None
    return f"{value * 100:.{digits}f}%"


def all_present(values: Iterable[Number]) -> bool:
    return all(v is not None for v in values)
