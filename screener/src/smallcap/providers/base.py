"""Provider interface.

A provider turns a ticker into a :class:`CompanyFinancials`. Everything
downstream -- criteria, scoring, reporting -- is written against that one
shape, so swapping SEC EDGAR for a vendor feed, a CSV dump, or a test fixture
touches nothing but this layer.
"""

from __future__ import annotations

import datetime as dt
from typing import Dict, List, Optional, Protocol, Sequence, runtime_checkable

from ..models import CompanyFinancials


class ProviderError(RuntimeError):
    """The provider could not produce data for this company."""


@runtime_checkable
class FinancialsProvider(Protocol):
    """Source of fundamental, market and ownership data."""

    name: str

    def fetch(
        self, ticker: str, as_of: Optional[dt.date] = None
    ) -> CompanyFinancials:
        """Return everything known about ``ticker`` as of ``as_of``.

        Implementations must honour ``as_of`` by excluding any figure whose
        filing date is later than it. Screening on data that was not public at
        the time is the single easiest way to manufacture a backtest that
        cannot be traded.
        """
        ...

    def universe(self) -> List[str]:
        """Return the tickers this provider can enumerate."""
        ...


def fetch_series(
    provider, ticker: str, as_of_dates: Sequence[Optional[dt.date]]
) -> Dict[Optional[dt.date], CompanyFinancials]:
    """Point-in-time views of one company at several dates.

    Providers may implement ``fetch_series`` to read and parse their source
    documents once and reuse them across every date -- which for SEC EDGAR is
    the difference between one multi-megabyte parse per company and one per
    company *per rebalance date*. Providers that do not are driven through
    ``fetch`` one date at a time, which is correct but slower.
    """
    native = getattr(provider, "fetch_series", None)
    if callable(native):
        return native(ticker, as_of_dates)
    return {as_of: provider.fetch(ticker, as_of=as_of) for as_of in as_of_dates}
