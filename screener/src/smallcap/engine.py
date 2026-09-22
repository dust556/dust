"""The screening engine: fetch, evaluate, score, rank.

Deliberate design points:

* **Every criterion runs for every company**, even after one has already
  failed. Short-circuiting would be faster, but the whole value of a screen
  is being able to ask "how close was it, and on what?" -- a company that
  fails only on insider ownership computed from a lower-bound source is a
  very different candidate from one that fails four conditions.
* **A failure to fetch is a result, not an exception.** One unparseable
  filing must not abort a 2,000-name run, so per-company errors are captured
  into the result and the run continues.
* **Ranking is separate from passing.** The gate is binary; the composite
  score only orders the survivors.
"""

from __future__ import annotations

import datetime as dt
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Dict, Iterable, List, Optional, Sequence

from .config import Config
from .criteria import ALL_CRITERIA
from .models import CompanyFinancials, CriterionResult, ScreenResult, Verdict
from .providers.base import ProviderError
from .util.http import HTTPError
from .scoring import composite_score, data_quality

LOGGER = logging.getLogger("smallcap.engine")


class ScreeningEngine:
    def __init__(
        self,
        provider,
        config: Optional[Config] = None,
        criteria: Optional[Sequence] = None,
    ):
        self.provider = provider
        self.config = config or Config()
        self.criteria = list(criteria if criteria is not None else ALL_CRITERIA)

    # ------------------------------------------------------------------
    def as_of_date(self) -> Optional[dt.date]:
        if not self.config.as_of:
            return None
        return dt.date.fromisoformat(self.config.as_of)

    # ------------------------------------------------------------------
    def evaluate(self, company: CompanyFinancials) -> ScreenResult:
        """Run every criterion against an already-fetched company."""
        results: List[CriterionResult] = []
        for criterion in self.criteria:
            try:
                results.append(criterion.evaluate(company, self.config))
            except Exception as exc:  # noqa: BLE001
                # A bug in one criterion must not take down the whole screen,
                # but it must be loud in the output rather than look like a
                # legitimate FAIL.
                LOGGER.exception(
                    "criterion %s raised for %s", criterion.key, company.ticker
                )
                results.append(
                    CriterionResult(
                        key=criterion.key,
                        label=criterion.label,
                        verdict=Verdict.INSUFFICIENT_DATA,
                        reasons=[f"criterion raised {type(exc).__name__}: {exc}"],
                        missing=["evaluation error"],
                    )
                )

        decided = [r for r in results if r.verdict is not Verdict.INSUFFICIENT_DATA]
        passed = [r for r in results if r.verdict is Verdict.PASS]
        all_passed = len(passed) == len(results)

        result = ScreenResult(
            ticker=company.ticker,
            name=company.name,
            cik=company.cik,
            criteria=results,
            passed_count=len(passed),
            decided_count=len(decided),
            all_passed=all_passed,
            data_quality=data_quality(results),
            warnings=list(company.warnings),
            as_of=self.config.as_of,
        )
        result.composite_score = composite_score(result, self.config.scoring)
        return result

    # ------------------------------------------------------------------
    def screen_one(self, ticker: str) -> ScreenResult:
        as_of = self.as_of_date()
        try:
            company = self.provider.fetch(ticker, as_of=as_of)
        except (ProviderError, HTTPError) as exc:
            # An unreachable endpoint or an absent filer is ordinary data
            # attrition, not a bug: record it and move on quietly. Logging a
            # traceback here would print one per ticker across a whole run.
            LOGGER.warning("could not fetch %s: %s", ticker, exc)
            return ScreenResult(ticker=ticker.upper(), error=str(exc), as_of=self.config.as_of)
        except Exception as exc:  # noqa: BLE001
            # Anything else is unexpected and worth a traceback.
            LOGGER.exception("provider failed for %s", ticker)
            return ScreenResult(
                ticker=ticker.upper(),
                error=f"{type(exc).__name__}: {exc}",
                as_of=self.config.as_of,
            )
        return self.evaluate(company)

    # ------------------------------------------------------------------
    def screen(
        self,
        tickers: Iterable[str],
        progress: Optional[Callable[[int, int, ScreenResult], None]] = None,
    ) -> List[ScreenResult]:
        """Screen many tickers, in parallel where the provider allows it."""
        tickers = [t.strip().upper() for t in tickers if t and t.strip()]
        total = len(tickers)

        # Run-level prerequisites (the SEC ticker index, for instance) are
        # loaded once, on this thread. If they fail the whole run fails with
        # one message rather than N identical per-company errors.
        prepare = getattr(self.provider, "prepare", None)
        if callable(prepare):
            prepare()
        results: Dict[str, ScreenResult] = {}

        workers = max(1, int(self.config.workers))
        if workers == 1 or total <= 1:
            for index, ticker in enumerate(tickers, start=1):
                result = self.screen_one(ticker)
                results[ticker] = result
                if progress:
                    progress(index, total, result)
        else:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {
                    pool.submit(self.screen_one, ticker): ticker for ticker in tickers
                }
                for index, future in enumerate(as_completed(futures), start=1):
                    ticker = futures[future]
                    result = future.result()
                    results[ticker] = result
                    if progress:
                        progress(index, total, result)

        # Preserve the caller's ordering; ranking happens separately.
        return [results[t] for t in tickers if t in results]

    # ------------------------------------------------------------------
    def rank(self, results: Sequence[ScreenResult]) -> List[ScreenResult]:
        """Order the passing, adequately-covered companies by composite score."""
        settings = self.config.scoring
        eligible = []
        for result in results:
            if result.error:
                continue
            if settings.require_all_pass and not result.all_passed:
                continue
            if (
                result.data_quality is not None
                and result.data_quality < settings.min_data_quality
            ):
                continue
            if result.composite_score is None:
                continue
            eligible.append(result)
        return sorted(
            eligible, key=lambda r: (r.composite_score or 0.0), reverse=True
        )
