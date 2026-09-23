"""Fama-French factor returns, loaded from a local CSV.

The canonical source is Ken French's data library. It is not fetched
automatically: a research result should depend on a file you can point at and
re-read years later, not on whatever a URL returned the day you ran it.
Download ``F-F_Research_Data_Factors`` (monthly) and pass ``--factors``.

Expected layout -- the Ken French CSV works once its header and footer notes
are stripped:

    date,Mkt-RF,SMB,HML,RF
    202001,-0.11,-0.06,-6.27,0.13

Monthly rows are compounded into whatever rebalance period the backtest uses.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import os
import re
from typing import Dict, List, Optional, Sequence, Tuple

# The standard three, plus the two profitability/investment factors when the
# file happens to carry them.
DEFAULT_FACTORS = ["Mkt-RF", "SMB", "HML"]
RISK_FREE_COLUMN = "RF"


class FactorData:
    """Monthly factor returns, in decimal form."""

    def __init__(self, rows: Dict[dt.date, Dict[str, float]], scale_note: str = ""):
        self.rows = rows
        self.scale_note = scale_note

    @property
    def columns(self) -> List[str]:
        for values in self.rows.values():
            return sorted(values)
        return []

    def span(self) -> Optional[Tuple[dt.date, dt.date]]:
        if not self.rows:
            return None
        dates = sorted(self.rows)
        return dates[0], dates[-1]

    def compound_between(
        self, start: dt.date, end: dt.date, names: Sequence[str]
    ) -> Optional[Dict[str, float]]:
        """Compound monthly factor returns over (start, end].

        Returns None if the window is not fully covered -- a partially
        covered period would silently understate the factor exposure and
        overstate alpha.
        """
        if start >= end:
            return None
        months = [d for d in sorted(self.rows) if start < d <= end]
        if not months:
            return None

        # Require coverage of every month the window touches, allowing for
        # month-end stamping.
        expected = _months_between(start, end)
        if len(months) < expected:
            return None

        compounded: Dict[str, float] = {}
        for name in names:
            total = 1.0
            for month in months:
                value = self.rows[month].get(name)
                if value is None:
                    return None
                total *= 1.0 + value
            compounded[name] = total - 1.0
        return compounded

    def risk_free_between(self, start: dt.date, end: dt.date) -> Optional[float]:
        result = self.compound_between(start, end, [RISK_FREE_COLUMN])
        return result[RISK_FREE_COLUMN] if result else None


def _months_between(start: dt.date, end: dt.date) -> int:
    return max(0, (end.year - start.year) * 12 + (end.month - start.month))


def _parse_period(raw: str) -> Optional[dt.date]:
    """Accept YYYYMM, YYYYMMDD or an ISO date; return the month end."""
    text = raw.strip()
    if not text:
        return None
    if re.fullmatch(r"\d{6}", text):
        year, month = int(text[:4]), int(text[4:6])
    elif re.fullmatch(r"\d{8}", text):
        year, month = int(text[:4]), int(text[4:6])
    else:
        try:
            parsed = dt.date.fromisoformat(text[:10])
        except ValueError:
            return None
        year, month = parsed.year, parsed.month
    if not 1 <= month <= 12:
        return None
    if month == 12:
        return dt.date(year, 12, 31)
    return dt.date(year, month + 1, 1) - dt.timedelta(days=1)


def load_factors(path: str) -> FactorData:
    """Read a factor CSV, tolerating the Ken French header/footer notes."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"factor file not found: {path}")
    with open(path, "r", encoding="utf-8-sig", errors="replace") as handle:
        text = handle.read()

    # Find the header line: the first row whose second field is a factor name.
    lines = text.splitlines()
    header_index = None
    for index, line in enumerate(lines):
        fields = [f.strip() for f in line.split(",")]
        if len(fields) >= 3 and any(f in ("Mkt-RF", "SMB", "HML") for f in fields):
            header_index = index
            break
    if header_index is None:
        raise ValueError(
            f"{path}: no factor header found (expected a row naming Mkt-RF/SMB/HML)"
        )

    header = [f.strip() for f in lines[header_index].split(",")]
    if not header[0]:
        header[0] = "date"
    body = "\n".join([",".join(header)] + lines[header_index + 1 :])

    rows: Dict[dt.date, Dict[str, float]] = {}
    magnitudes: List[float] = []
    for record in csv.DictReader(io.StringIO(body)):
        raw_date = (record.get(header[0]) or "").strip()
        period = _parse_period(raw_date)
        if period is None:
            # Ken French files end with annual tables and footnotes; stop at
            # the first unparseable row rather than trying to interpret them.
            if rows:
                break
            continue
        values: Dict[str, float] = {}
        for name in header[1:]:
            raw = (record.get(name) or "").strip()
            if not raw:
                continue
            try:
                value = float(raw)
            except ValueError:
                continue
            # -99.99 and -999 are the library's missing-data sentinels.
            if value <= -99.0:
                continue
            values[name] = value
            magnitudes.append(abs(value))
        if values:
            rows[period] = values

    if not rows:
        raise ValueError(f"{path}: no usable factor rows")

    # Ken French publishes percentages; other exports use decimals. Monthly
    # factor returns are a few percent, so the two are an order of magnitude
    # apart and the distinction is unambiguous.
    magnitudes.sort()
    median = magnitudes[len(magnitudes) // 2] if magnitudes else 0.0
    if median > 0.5:
        for values in rows.values():
            for name in list(values):
                values[name] = values[name] / 100.0
        note = f"values read as percentages (median |x| = {median:.3f}) and divided by 100"
    else:
        note = f"values read as decimals (median |x| = {median:.5f})"

    return FactorData(rows, scale_note=note)
