"""Provider interface.

A provider turns a ticker into a :class:`CompanyFinancials`. Everything
downstream -- criteria, scoring, reporting -- is written against that one
shape, so swapping SEC EDGAR for a vendor feed, a CSV dump, or a test fixture
touches nothing but this layer.
"""

from __future__ import annotations

import datetime as dt
from typing import List, Optional, Protocol, runtime_checkable

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
