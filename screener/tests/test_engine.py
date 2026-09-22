"""Engine, scoring and reporting, plus the golden fixture verdicts."""

import datetime as dt
import json
import logging
import os
import tempfile
import unittest

from smallcap.config import Config
from smallcap.engine import ScreeningEngine
from smallcap.models import (
    CompanyFinancials,
    CriterionResult,
    ScreenResult,
    Verdict,
)
from smallcap.providers.base import ProviderError
from smallcap.providers.fixtures import FixtureProvider
from smallcap.report import to_csv, to_json, to_markdown, write_reports
from smallcap.scoring import composite_score, data_quality, summarise

FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "fixtures")


def engine(config=None):
    return ScreeningEngine(FixtureProvider(FIXTURE_DIR), config or Config())


class TestGoldenVerdicts(unittest.TestCase):
    """Each fixture is built to exercise one decision path end to end."""

    @classmethod
    def setUpClass(cls):
        cls.engine = engine()
        cls.results = {
            ticker: cls.engine.screen_one(ticker)
            for ticker in cls.engine.provider.universe()
        }

    def failures(self, ticker):
        return {
            c.key
            for c in self.results[ticker].criteria
            if c.verdict is Verdict.FAIL
        }

    def test_ideal_clears_all_five_conditions(self):
        self.assertTrue(self.results["IDEAL"].all_passed)
        self.assertEqual(self.results["IDEAL"].passed_count, 5)

    def test_large_company_fails_only_on_size(self):
        self.assertEqual(self.failures("BIGCAP"), {"market_cap"})

    def test_thin_margin_fails_on_the_level(self):
        result = self.results["THINMRG"]
        self.assertIn("gross_margin", self.failures("THINMRG"))
        self.assertFalse(result.criterion("gross_margin").detail["checks"]["level"])

    def test_eroding_margin_fails_on_direction_despite_a_high_level(self):
        result = self.results["FADING"]
        margin = result.criterion("gross_margin")
        self.assertIs(margin.verdict, Verdict.FAIL)
        self.assertTrue(margin.detail["checks"]["level"])
        self.assertFalse(margin.detail["checks"]["slope"])

    def test_levered_roll_up_fails_the_debt_ceiling(self):
        leverage = self.results["LEVERED"].criterion("leverage")
        self.assertIs(leverage.verdict, Verdict.FAIL)
        self.assertGreater(leverage.value, 3.0)

    def test_capital_destroyer_fails_only_on_returns(self):
        result = self.results["LOWROIC"]
        self.assertEqual(self.failures("LOWROIC"), {"returns"})
        self.assertLess(result.criterion("returns").detail["spread"], 0)

    def test_unaligned_management_fails_only_on_ownership(self):
        self.assertEqual(self.failures("NOSKIN"), {"insider"})

    def test_thin_data_is_undecidable_never_failed(self):
        result = self.results["THINDATA"]
        self.assertEqual(self.failures("THINDATA"), set())
        undecided = {
            c.key for c in result.criteria if c.verdict is Verdict.INSUFFICIENT_DATA
        }
        self.assertEqual(undecided, {"gross_margin", "returns", "leverage", "insider"})
        self.assertAlmostEqual(result.data_quality, 0.2)

    def test_only_the_ideal_company_is_ranked(self):
        ranked = self.engine.rank(list(self.results.values()))
        self.assertEqual([r.ticker for r in ranked], ["IDEAL"])


class TestEngineRobustness(unittest.TestCase):
    def test_provider_error_becomes_a_result_not_an_exception(self):
        result = engine().screen_one("NOSUCHTICKER")
        self.assertIsNotNone(result.error)
        self.assertEqual(result.criteria, [])

    def test_one_bad_ticker_does_not_abort_the_run(self):
        results = engine().screen(["IDEAL", "NOSUCHTICKER", "NOSKIN"])
        self.assertEqual(len(results), 3)
        self.assertEqual(sum(1 for r in results if r.error), 1)

    def test_a_raising_criterion_is_undecidable_not_a_failure(self):
        class Exploding:
            key = "market_cap"
            label = "Exploding criterion"

            def evaluate(self, company, config):
                raise ValueError("boom")

        screen = ScreeningEngine(
            FixtureProvider(FIXTURE_DIR), Config(), criteria=[Exploding()]
        )
        # The engine logs the traceback; silence it so the deliberate failure
        # does not look like a real one in the test output.
        logging.getLogger("smallcap.engine").setLevel(logging.CRITICAL)
        try:
            result = screen.screen_one("IDEAL")
        finally:
            logging.getLogger("smallcap.engine").setLevel(logging.NOTSET)
        self.assertIs(result.criteria[0].verdict, Verdict.INSUFFICIENT_DATA)
        self.assertIn("boom", result.criteria[0].reasons[0])

    def test_results_preserve_the_requested_order(self):
        tickers = ["NOSKIN", "IDEAL", "BIGCAP"]
        results = engine().screen(tickers)
        self.assertEqual([r.ticker for r in results], tickers)

    def test_parallel_and_serial_runs_agree(self):
        serial_config, parallel_config = Config(), Config()
        serial_config.workers, parallel_config.workers = 1, 4
        tickers = ["IDEAL", "NOSKIN", "BIGCAP", "FADING"]
        serial = ScreeningEngine(FixtureProvider(FIXTURE_DIR), serial_config).screen(tickers)
        parallel = ScreeningEngine(FixtureProvider(FIXTURE_DIR), parallel_config).screen(tickers)
        self.assertEqual(
            [(r.ticker, r.all_passed) for r in serial],
            [(r.ticker, r.all_passed) for r in parallel],
        )

    def test_run_level_prerequisites_fail_fast(self):
        """A missing ticker index must fail once, not once per ticker."""

        class BrokenProvider:
            calls = 0

            def prepare(self):
                raise ProviderError("ticker index unavailable")

            def fetch(self, ticker, as_of=None):
                BrokenProvider.calls += 1
                raise AssertionError("fetch must not run when prepare fails")

        screen = ScreeningEngine(BrokenProvider(), Config())
        with self.assertRaises(ProviderError):
            screen.screen(["IDEAL", "NOSKIN", "BIGCAP"])
        self.assertEqual(BrokenProvider.calls, 0)

    def test_fetch_failures_are_logged_without_a_traceback(self):
        # One unreachable company in a long run should not print a traceback.
        with self.assertLogs("smallcap.engine", level="WARNING") as captured:
            engine().screen_one("NOSUCHTICKER")
        self.assertTrue(any("could not fetch" in line for line in captured.output))
        self.assertFalse(any("Traceback" in line for line in captured.output))

    def test_as_of_is_validated_and_applied(self):
        config = Config()
        config.as_of = "2022-06-30"
        result = ScreeningEngine(FixtureProvider(FIXTURE_DIR), config).screen_one("IDEAL")
        # Only two fiscal years were public by then, so the trend-based
        # conditions cannot be decided.
        self.assertIs(result.criterion("gross_margin").verdict, Verdict.INSUFFICIENT_DATA)


class TestScoring(unittest.TestCase):
    def result(self, *criteria):
        return ScreenResult(ticker="T", criteria=list(criteria))

    def criterion(self, key, verdict, score):
        return CriterionResult(key=key, label=key, verdict=verdict, score=score)

    def test_data_quality_counts_decidable_criteria(self):
        results = [
            self.criterion("a", Verdict.PASS, 1.0),
            self.criterion("b", Verdict.FAIL, 0.0),
            self.criterion("c", Verdict.INSUFFICIENT_DATA, None),
            self.criterion("d", Verdict.INSUFFICIENT_DATA, None),
        ]
        self.assertEqual(data_quality(results), 0.5)

    def test_undecidable_criteria_do_not_inflate_the_score(self):
        config = Config().scoring
        full = self.result(
            self.criterion("gross_margin", Verdict.PASS, 1.0),
            self.criterion("returns", Verdict.PASS, 0.0),
        )
        partial = self.result(
            self.criterion("gross_margin", Verdict.PASS, 1.0),
            self.criterion("returns", Verdict.INSUFFICIENT_DATA, None),
        )
        # The weight of a criterion that could not be decided is removed from
        # the denominator rather than being scored as zero.
        self.assertLess(composite_score(full, config), composite_score(partial, config))
        self.assertEqual(composite_score(partial, config), 1.0)

    def test_score_is_none_when_nothing_is_decidable(self):
        empty = self.result(self.criterion("returns", Verdict.INSUFFICIENT_DATA, None))
        self.assertIsNone(composite_score(empty, Config().scoring))

    def test_ranking_excludes_thin_coverage(self):
        config = Config()
        config.scoring.require_all_pass = False
        config.scoring.min_data_quality = 0.9
        screen = ScreeningEngine(FixtureProvider(FIXTURE_DIR), config)
        results = [screen.screen_one(t) for t in ("IDEAL", "THINDATA")]
        self.assertEqual([r.ticker for r in screen.rank(results)], ["IDEAL"])

    def test_summary_counts_failures_per_criterion(self):
        screen = engine()
        results = screen.screen(screen.provider.universe())
        stats = summarise(results)
        self.assertEqual(stats["universe_size"], len(results))
        self.assertEqual(stats["passed_all"], 1)
        self.assertGreaterEqual(stats["failures_by_criterion"]["gross_margin"], 2)


class TestReporting(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = engine()
        cls.results = cls.engine.screen(cls.engine.provider.universe())
        cls.ranked = cls.engine.rank(cls.results)

    def test_json_is_parseable_and_carries_the_summary(self):
        payload = json.loads(to_json(self.results, ranked=self.ranked))
        self.assertEqual(payload["summary"]["passed_all"], 1)
        self.assertEqual(payload["ranking"], ["IDEAL"])
        self.assertEqual(len(payload["results"]), len(self.results))

    def test_json_serialises_dates_and_enums(self):
        payload = json.loads(to_json(self.results))
        ideal = [r for r in payload["results"] if r["ticker"] == "IDEAL"][0]
        verdicts = {c["key"]: c["verdict"] for c in ideal["criteria"]}
        self.assertEqual(verdicts["market_cap"], "PASS")

    def test_csv_has_one_row_per_company(self):
        lines = [line for line in to_csv(self.results).splitlines() if line.strip()]
        self.assertEqual(len(lines), len(self.results) + 1)
        self.assertIn("market_cap_verdict", lines[0])

    def test_markdown_names_the_survivor_and_the_dropout_reasons(self):
        text = to_markdown(self.results, self.ranked)
        self.assertIn("IDEAL", text)
        self.assertIn("Where companies dropped out", text)
        self.assertIn("not investment advice", text)

    def test_markdown_handles_an_empty_candidate_list(self):
        text = to_markdown(self.results, [])
        self.assertIn("No company cleared all five conditions", text)

    def test_write_reports_creates_all_three_files(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = write_reports(directory, self.results, self.ranked)
            for path in paths.values():
                self.assertTrue(os.path.exists(path))
                self.assertGreater(os.path.getsize(path), 0)


if __name__ == "__main__":
    unittest.main()
