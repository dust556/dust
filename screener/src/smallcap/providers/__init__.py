"""Data providers.

``sec_edgar`` is the production source (SEC XBRL company facts + ownership
filings); ``fixtures`` replays recorded JSON for tests and offline demos.
"""

from .base import FinancialsProvider, ProviderError
from .fixtures import FixtureProvider
from .sec_edgar import SECEdgarProvider

__all__ = [
    "FinancialsProvider",
    "ProviderError",
    "FixtureProvider",
    "SECEdgarProvider",
    "build_provider",
]


def build_provider(name: str, config, **kwargs):
    """Construct a provider by name."""
    key = name.lower()
    if key in {"sec", "edgar", "sec_edgar"}:
        return SECEdgarProvider(config, **kwargs)
    if key in {"fixture", "fixtures", "offline"}:
        return FixtureProvider(**kwargs)
    raise ValueError(f"unknown provider: {name}")
