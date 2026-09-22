"""Composite scoring and data-quality accounting.

The five conditions are a gate, not a ranking: a company either clears them
or it does not. But a list of forty survivors still needs an order, and the
order should reflect *how far* past each threshold a company sits, not just
that it got past.

Two safeguards keep the score honest:

* A criterion that could not be decided contributes nothing and its weight is
  removed from the denominator, so a company with two missing inputs is not
  quietly rewarded for the ones it does have.
* ``data_quality`` reports what fraction of the conditions were decidable at
  all, and the engine refuses to rank anything below the configured floor.
  Thin coverage is a reason to abstain, not to extrapolate.
"""

from __future__ import annotations

from typing import Optional, Sequence

from .config import ScoringConfig
from .models import CriterionResult, ScreenResult, Verdict


def data_quality(results: Sequence[CriterionResult]) -> Optional[float]:
    """Fraction of criteria that could be decided from the available data."""
    if not results:
        return None
    decided = sum(
        1 for r in results if r.verdict is not Verdict.INSUFFICIENT_DATA
    )
    return decided / len(results)


def composite_score(
    result: ScreenResult, config: ScoringConfig
) -> Optional[float]:
    """Weighted mean of the per-criterion scores, over decidable criteria."""
    total_weight = 0.0
    accumulated = 0.0
    for criterion in result.criteria:
        if criterion.verdict is Verdict.INSUFFICIENT_DATA:
            continue
        if criterion.score is None:
            continue
        weight = config.weights.get(criterion.key, 0.0)
        if weight <= 0:
            continue
        total_weight += weight
        accumulated += weight * criterion.score
    if total_weight <= 0:
        return None
    return accumulated / total_weight


def summarise(results: Sequence[ScreenResult]) -> dict:
    """Run-level counts, including why companies dropped out.

    The per-criterion failure tally is the most useful diagnostic in the whole
    report: if 95% of the universe fails on insider ownership, that is far
    more likely to be a data-coverage problem than a finding about American
    corporate governance.
    """
    total = len(results)
    errored = sum(1 for r in results if r.error)
    evaluated = total - errored
    passing = sum(1 for r in results if r.all_passed and not r.error)

    failures: dict = {}
    undecided: dict = {}
    for result in results:
        if result.error:
            continue
        for criterion in result.criteria:
            if criterion.verdict is Verdict.FAIL:
                failures[criterion.key] = failures.get(criterion.key, 0) + 1
            elif criterion.verdict is Verdict.INSUFFICIENT_DATA:
                undecided[criterion.key] = undecided.get(criterion.key, 0) + 1

    return {
        "universe_size": total,
        "evaluated": evaluated,
        "fetch_errors": errored,
        "passed_all": passing,
        "pass_rate": (passing / evaluated) if evaluated else None,
        "failures_by_criterion": dict(sorted(failures.items(), key=lambda kv: -kv[1])),
        "undecidable_by_criterion": dict(
            sorted(undecided.items(), key=lambda kv: -kv[1])
        ),
    }
