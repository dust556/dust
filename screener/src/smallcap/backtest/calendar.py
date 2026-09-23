"""Rebalance dates.

The screen's inputs are filings, which arrive four times a year, so the
natural rebalance frequency is quarterly. Anything faster re-trades the same
unchanged fundamentals and pays spread for the privilege -- which on a
small-cap universe is the fastest way to convert a real edge into a loss.

Dates are placed with a **reporting lag** after each period end. A 10-K for
the December quarter is not on file on 1 January; screening as if it were
is look-ahead, and it is the most common way a backtest is accidentally
made untradeable.
"""

from __future__ import annotations

import datetime as dt
from typing import List

FREQUENCIES = {
    "quarterly": 3,
    "semiannual": 6,
    "annual": 12,
    "monthly": 1,
}

# Large accelerated filers have 40 days for a 10-Q and 60 for a 10-K; smaller
# reporting companies get 45 and 90. 75 calendar days is a middle default
# that clears the 10-Q deadline for every filer class and most 10-Ks.
DEFAULT_REPORTING_LAG_DAYS = 75


def _add_months(date: dt.date, months: int) -> dt.date:
    """Advance by whole months, clamping to the end of a short month."""
    total = date.month - 1 + months
    year = date.year + total // 12
    month = total % 12 + 1
    # Step back from the first of the next month to get that month's last day.
    if month == 12:
        last_day = 31
    else:
        last_day = (dt.date(year, month + 1, 1) - dt.timedelta(days=1)).day
    return dt.date(year, month, min(date.day, last_day))


def quarter_ends(start: dt.date, end: dt.date, months: int = 3) -> List[dt.date]:
    """Period ends at the given spacing, from the first on or after ``start``."""
    if months < 1:
        raise ValueError("rebalance spacing must be at least one month")
    dates: List[dt.date] = []
    # Anchor on calendar quarter ends so runs with different start dates line
    # up on the same rebalance grid and remain comparable.
    year = start.year
    candidates = []
    while year <= end.year + 1:
        for month in range(1, 13):
            last_day = (
                dt.date(year + 1, 1, 1) - dt.timedelta(days=1)
                if month == 12
                else dt.date(year, month + 1, 1) - dt.timedelta(days=1)
            )
            candidates.append(last_day)
        year += 1
    anchored = [d for d in candidates if d.month % months == 0] if months <= 12 else candidates
    if not anchored:
        anchored = candidates
    for date in anchored:
        if start <= date <= end:
            dates.append(date)
    return dates


def rebalance_dates(
    start: dt.date,
    end: dt.date,
    frequency: str = "quarterly",
    reporting_lag_days: int = DEFAULT_REPORTING_LAG_DAYS,
) -> List[dt.date]:
    """Dates on which the screen is run and the portfolio is formed.

    Each date is a period end pushed forward by ``reporting_lag_days``, so the
    screen only ever sees filings that had realistically been published.
    """
    if frequency not in FREQUENCIES:
        raise ValueError(
            f"unknown frequency {frequency!r}; expected one of {sorted(FREQUENCIES)}"
        )
    months = FREQUENCIES[frequency]
    lag = dt.timedelta(days=reporting_lag_days)
    # Widen the search backwards so a period ending before `start` can still
    # produce an in-range rebalance date once the lag is applied.
    periods = quarter_ends(start - dt.timedelta(days=reporting_lag_days + 400), end, months)
    dates = []
    for period_end in periods:
        date = period_end + lag
        if start <= date <= end:
            dates.append(date)
    return sorted(set(dates))
