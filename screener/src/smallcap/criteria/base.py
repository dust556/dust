"""Criterion interface.

A criterion looks at one :class:`CompanyFinancials` and returns one
:class:`CriterionResult`. It must never raise on missing data and never
return ``FAIL`` for data it simply does not have -- ``INSUFFICIENT_DATA``
exists precisely so that a thin-coverage company is excluded for the right
reason and shows up as such in the report.
"""

from __future__ import annotations

from typing import List, Optional, Protocol

from ..config import Config
from ..models import CompanyFinancials, CriterionResult, Verdict


class Criterion(Protocol):
    key: str
    label: str

    def evaluate(
        self, company: CompanyFinancials, config: Config
    ) -> CriterionResult:
        ...


def insufficient(
    key: str,
    label: str,
    missing: List[str],
    threshold: Optional[str] = None,
    reasons: Optional[List[str]] = None,
) -> CriterionResult:
    """Build the standard 'we could not decide' result."""
    return CriterionResult(
        key=key,
        label=label,
        verdict=Verdict.INSUFFICIENT_DATA,
        score=None,
        value=None,
        threshold=threshold,
        missing=missing,
        reasons=reasons or [f"missing required inputs: {', '.join(missing)}"],
    )
