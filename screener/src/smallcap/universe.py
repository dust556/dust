"""Point-in-time universe construction from EDGAR's full index.

**The problem this addresses.** A backtest run against today's ticker list
only ever considers companies that still exist. Everything that went
bankrupt, was taken private, or was acquired between the start date and now
is missing, and since failures leave the list while survivors stay, the
result is biased upward.

**What this does about it.** EDGAR publishes a quarterly index of every
filing ever made. The set of companies that filed a 10-K in a given year is
the set of SEC-reporting operating companies that existed that year --
including the ones that later disappeared. Rebuilding the universe from that
index restores the companies a current ticker list has deleted.

**What it still cannot do, and the number it gives you instead.** The index
identifies filers by CIK. Mapping a CIK to a ticker uses the SEC's current
ticker file, which by construction has no entry for a company that has since
delisted -- so those names are recovered as *existing* but not as
*investable*, because without a ticker there is no price series to trade
them with. That is a real remaining gap, so instead of hiding it, the
builder reports it: ``coverage`` states, per period, how many filers of the
day cannot be mapped to a ticker today. **That percentage is a direct
estimate of how much survivorship bias is left in the backtest**, which is
considerably more useful than an unquantified warning.

To close the gap entirely you need a ticker-and-price source that covers
dead names (CRSP, or a vendor with delisting data); point ``--prices-dir``
at it and supply your own universe file.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Set, Tuple

from .util.http import HttpClient, HTTPError

LOGGER = logging.getLogger("smallcap.universe")

FULL_INDEX_URL = (
    "https://www.sec.gov/Archives/edgar/full-index/{year}/QTR{quarter}/master.idx"
)

# Annual reports filed by domestic operating companies. 20-F and 40-F are
# excluded: foreign private issuers report under different accounting rules,
# so their XBRL does not line up with the us-gaap concepts the screen reads.
ANNUAL_FORMS = {"10-K", "10-K405", "10-KSB", "10-K/A", "10-KSB/A"}


@dataclass
class UniverseSnapshot:
    """The filers on record as of one date."""

    date: dt.date
    ciks: Set[str] = field(default_factory=set)
    tickers: List[str] = field(default_factory=list)
    unmapped_ciks: List[str] = field(default_factory=list)

    @property
    def coverage(self) -> Optional[float]:
        """Share of that period's filers that map to a ticker today."""
        if not self.ciks:
            return None
        return len(self.tickers) / len(self.ciks)


def parse_master_index(text: str, forms: Optional[Set[str]] = None) -> List[Tuple[str, str, dt.date]]:
    """Parse a ``master.idx`` into (CIK, form, filing date) rows.

    The file is pipe-delimited under a short header::

        CIK|Company Name|Form Type|Date Filed|Filename
    """
    wanted = forms if forms is not None else ANNUAL_FORMS
    rows: List[Tuple[str, str, dt.date]] = []
    for line in text.splitlines():
        parts = line.split("|")
        if len(parts) < 5:
            continue
        cik, _name, form, filed, _path = parts[0], parts[1], parts[2], parts[3], parts[4]
        if not cik.strip().isdigit():
            continue  # header or separator row
        form = form.strip()
        if form not in wanted:
            continue
        try:
            filing_date = dt.date.fromisoformat(filed.strip()[:10])
        except ValueError:
            continue
        rows.append((cik.strip().zfill(10), form, filing_date))
    return rows


class UniverseBuilder:
    """Builds point-in-time ticker universes from the EDGAR full index."""

    def __init__(
        self,
        http: HttpClient,
        ticker_index: Optional[Dict[str, Dict[str, object]]] = None,
        lookback_months: int = 15,
    ):
        self.http = http
        # {TICKER: {"cik": ..., "name": ..., "exchange": ...}}, from the SEC
        # ticker file. Used to map a historical CIK to something tradeable.
        self.ticker_index = ticker_index or {}
        # A company counts as active at date D if it filed an annual report
        # within this many months before D. 15 months allows for a late
        # filer without keeping a company alive long after it stopped
        # reporting.
        self.lookback_months = lookback_months
        self._filings: Dict[Tuple[int, int], List[Tuple[str, str, dt.date]]] = {}

    # ------------------------------------------------------------------
    def cik_to_ticker(self) -> Dict[str, str]:
        """Invert the ticker index. Multiple tickers per CIK: take the first."""
        mapping: Dict[str, str] = {}
        for ticker, meta in sorted(self.ticker_index.items()):
            cik = str(meta.get("cik") or "").zfill(10)
            if cik and cik not in mapping:
                mapping[cik] = ticker
        return mapping

    # ------------------------------------------------------------------
    def quarter_filings(self, year: int, quarter: int) -> List[Tuple[str, str, dt.date]]:
        key = (year, quarter)
        if key in self._filings:
            return self._filings[key]
        url = FULL_INDEX_URL.format(year=year, quarter=quarter)
        try:
            text = self.http.get_text(url, accept="text/plain")
        except HTTPError as exc:
            # A quarter in the future, or one EDGAR has not published, is not
            # an error -- it just contributes nothing.
            LOGGER.warning("full index %sQTR%s unavailable: %s", year, quarter, exc)
            self._filings[key] = []
            return []
        rows = parse_master_index(text)
        self._filings[key] = rows
        return rows

    # ------------------------------------------------------------------
    def annual_filers(
        self, start: dt.date, end: dt.date
    ) -> List[Tuple[str, dt.date]]:
        """Every (CIK, filing date) annual report filed in the window."""
        filings: List[Tuple[str, dt.date]] = []
        year = start.year
        while year <= end.year:
            for quarter in (1, 2, 3, 4):
                for cik, _form, filed in self.quarter_filings(year, quarter):
                    if start <= filed <= end:
                        filings.append((cik, filed))
            year += 1
        return filings

    # ------------------------------------------------------------------
    def snapshot(
        self, date: dt.date, filings: Sequence[Tuple[str, dt.date]]
    ) -> UniverseSnapshot:
        """The companies reporting as of ``date``."""
        window_start = _subtract_months(date, self.lookback_months)
        active = {
            cik for cik, filed in filings if window_start <= filed <= date
        }
        mapping = self.cik_to_ticker()
        tickers = sorted({mapping[cik] for cik in active if cik in mapping})
        unmapped = sorted(cik for cik in active if cik not in mapping)
        return UniverseSnapshot(
            date=date, ciks=active, tickers=tickers, unmapped_ciks=unmapped
        )

    # ------------------------------------------------------------------
    def build(
        self, dates: Sequence[dt.date], progress=None
    ) -> Dict[dt.date, UniverseSnapshot]:
        """Snapshots for every supplied date."""
        if not dates:
            return {}
        ordered = sorted(dates)
        # Pull the index once over the widest window any snapshot needs.
        earliest = _subtract_months(ordered[0], self.lookback_months)
        filings = self.annual_filers(earliest, ordered[-1])
        snapshots: Dict[dt.date, UniverseSnapshot] = {}
        for index, date in enumerate(ordered, start=1):
            snapshots[date] = self.snapshot(date, filings)
            if progress:
                progress(index, len(ordered), snapshots[date])
        return snapshots


def _subtract_months(date: dt.date, months: int) -> dt.date:
    total = date.year * 12 + (date.month - 1) - months
    year, month = total // 12, total % 12 + 1
    if month == 12:
        last_day = 31
    else:
        last_day = (dt.date(year, month + 1, 1) - dt.timedelta(days=1)).day
    return dt.date(year, month, min(date.day, last_day))


# ----------------------------------------------------------------------
def to_universe_history(snapshots: Dict[dt.date, UniverseSnapshot]) -> Dict[str, List[str]]:
    """The ``--universe-history`` mapping the backtester consumes."""
    return {
        date.isoformat(): snapshot.tickers
        for date, snapshot in sorted(snapshots.items())
    }


def coverage_report(snapshots: Dict[dt.date, UniverseSnapshot]) -> Dict[str, object]:
    """Quantify the survivorship gap this universe still carries.

    ``unmapped`` counts companies that were filing annual reports at the time
    but have no ticker today -- overwhelmingly delistings, bankruptcies and
    acquisitions. The share they represent is the portion of the universe a
    backtest is still blind to.
    """
    rows = []
    for date, snapshot in sorted(snapshots.items()):
        rows.append(
            {
                "date": date.isoformat(),
                "filers": len(snapshot.ciks),
                "investable": len(snapshot.tickers),
                "unmapped": len(snapshot.unmapped_ciks),
                "coverage": snapshot.coverage,
            }
        )
    coverages = [r["coverage"] for r in rows if r["coverage"] is not None]
    worst = min(coverages) if coverages else None
    return {
        "periods": rows,
        "mean_coverage": (sum(coverages) / len(coverages)) if coverages else None,
        "worst_coverage": worst,
        "interpretation": (
            "'unmapped' companies were filing annual reports at the time but "
            "have no ticker in the SEC's current file -- almost all of them "
            "delisted, failed or were acquired. The share they represent is "
            "the survivorship bias remaining in a backtest run on this "
            "universe. Closing it needs a price source covering dead tickers."
        ),
    }


def write_universe_history(
    path: str, snapshots: Dict[dt.date, UniverseSnapshot]
) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(to_universe_history(snapshots), handle, indent=2, sort_keys=True)
        handle.write("\n")
