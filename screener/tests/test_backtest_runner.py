"""End-to-end backtest behaviour, including the look-ahead guarantee."""

import datetime as dt
import json
import os
import tempfile
import unittest

from smallcap.backtest import BacktestConfig, Backtester, load_factors
from smallcap.backtest import report as backtest_report
from smallcap.backtest.factors import FactorData
from smallcap.config import Config
from smallcap.providers.fixtures import FixtureProvider

FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "fixtures")

KEN_FRENCH_SAMPLE = """This file was created by CMPT_ME_BEVME_RETS using the 202603 CRSP database.

,Mkt-RF,SMB,HML,RF
202201,   -0.11,   -0.06,    6.27,    0.00
202202,   -2.29,    2.20,    3.11,    0.00
202203,    3.06,   -1.85,   -1.85,    0.01

Annual Factors: January-December
,Mkt-RF,SMB,HML,RF
2022, -21.63,  -6.20,  25.95,   1.43
"""


def make_config(workers=1):
    config = Config()
    config.workers = workers
    return config


def make_backtest(**overrides):
    params = dict(
        start=dt.date(2022, 1, 1),
        end=dt.date(2026, 3, 31),
        benchmark="BIGCAP",
    )
    params.update(overrides)
    return BacktestConfig(**params)


class RecordingProvider:
    """Wraps a provider and records every as-of date it is asked for."""

    def __init__(self, inner):
        self.inner = inner
        self.requests = []

    def fetch(self, ticker, as_of=None):
        self.requests.append((ticker, as_of))
        return self.inner.fetch(ticker, as_of=as_of)

    def universe(self):
        return self.inner.universe()


class TestBacktestLoop(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        provider = FixtureProvider(FIXTURE_DIR)
        cls.tester = Backtester(provider, make_config(), make_backtest())
        cls.periods = cls.tester.run(provider.universe())

    def test_produces_one_period_per_rebalance_interval(self):
        self.assertGreater(len(self.periods), 10)
        for period in self.periods:
            self.assertLess(period.rebalance_date, period.exit_date)

    def test_periods_are_contiguous(self):
        # Each period must start where the previous one ended, or returns
        # would be double-counted or silently skipped.
        for earlier, later in zip(self.periods, self.periods[1:]):
            self.assertEqual(earlier.exit_date, later.rebalance_date)

    def test_point_in_time_screening_delays_qualification(self):
        # IDEAL cannot clear the screen until it has enough filed history and
        # a market cap above the floor.
        held = {
            period.rebalance_date: [p.ticker for p in period.positions]
            for period in self.periods
        }
        first_held = min((d for d, names in held.items() if names), default=None)
        self.assertIsNotNone(first_held)
        self.assertGreater(first_held, dt.date(2022, 6, 1))
        # And earlier periods must genuinely hold nothing.
        self.assertEqual(held[min(held)], [])

    def test_empty_periods_sit_in_cash_rather_than_reporting_nothing(self):
        empty = [p for p in self.periods if not p.positions]
        self.assertTrue(empty)
        for period in empty:
            self.assertEqual(period.portfolio_return, 0.0)
            self.assertTrue(any("cash" in n for n in period.notes))

    def test_benchmark_return_is_measured_over_the_same_window(self):
        for period in self.periods:
            self.assertIsNotNone(period.benchmark_return)


class TestNoLookAhead(unittest.TestCase):
    def test_the_screen_is_only_ever_asked_for_the_rebalance_date(self):
        """The core guarantee: no fetch may carry a future as-of date."""
        inner = FixtureProvider(FIXTURE_DIR)
        provider = RecordingProvider(inner)
        tester = Backtester(provider, make_config(), make_backtest())
        periods = tester.run(inner.universe())

        rebalance_dates = {p.rebalance_date for p in periods}
        screening_dates = {
            as_of for _, as_of in provider.requests if as_of is not None
        }
        self.assertTrue(screening_dates)
        # Every screening fetch used a real rebalance date, never a later one.
        self.assertTrue(screening_dates.issubset(rebalance_dates))

    def test_price_history_lookups_are_kept_separate_from_screening(self):
        # Settling a period needs prices after the rebalance date, so those
        # lookups pass as_of=None -- but they must never feed the screen.
        inner = FixtureProvider(FIXTURE_DIR)
        provider = RecordingProvider(inner)
        tester = Backtester(provider, make_config(), make_backtest())
        tester.run(inner.universe())
        unrestricted = [t for t, as_of in provider.requests if as_of is None]
        self.assertTrue(unrestricted)

    def test_screened_market_cap_never_uses_a_future_price(self):
        provider = FixtureProvider(FIXTURE_DIR)
        for as_of in (dt.date(2022, 6, 30), dt.date(2024, 6, 30)):
            company = provider.fetch("IDEAL", as_of=as_of)
            self.assertLessEqual(company.market.price_date, as_of)
            for period in company.periods:
                self.assertLessEqual(period.filed, as_of)


class TestAnalysis(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        provider = FixtureProvider(FIXTURE_DIR)
        cls.tester = Backtester(provider, make_config(), make_backtest())
        cls.periods = cls.tester.run(provider.universe())
        cls.result = cls.tester.analyse(cls.periods)

    def test_statistics_are_produced(self):
        stats = self.result.stats
        self.assertGreater(stats.periods, 10)
        self.assertIsNotNone(stats.cagr)
        self.assertIsNotNone(stats.benchmark_cagr)
        self.assertIsNotNone(stats.information_ratio)

    def test_survivorship_bias_is_always_stated(self):
        self.assertTrue(
            any("SURVIVORSHIP BIAS" in note for note in self.result.biases)
        )

    def test_cost_omission_is_always_stated(self):
        self.assertTrue(any("NO COSTS" in note for note in self.result.biases))

    def test_missing_factor_file_is_called_out(self):
        self.assertTrue(
            any("not adjusted for" in w for w in self.result.warnings)
        )

    def test_point_in_time_universe_removes_the_survivorship_note(self):
        provider = FixtureProvider(FIXTURE_DIR)
        history = {"2022-01-01": provider.universe()}
        tester = Backtester(
            provider, make_config(), make_backtest(universe_history=history)
        )
        result = tester.analyse(tester.run(provider.universe()))
        self.assertFalse(
            any("SURVIVORSHIP BIAS" in note for note in result.biases)
        )
        self.assertTrue(result.config["point_in_time_universe"])

    def test_universe_history_restricts_the_candidates(self):
        provider = FixtureProvider(FIXTURE_DIR)
        history = {"2022-01-01": ["NOSKIN"]}
        tester = Backtester(
            provider, make_config(), make_backtest(universe_history=history)
        )
        periods = tester.run(provider.universe())
        # IDEAL is excluded from the listing, so it can never be held.
        for period in periods:
            self.assertNotIn("IDEAL", [p.ticker for p in period.positions])

    def test_too_short_a_window_is_rejected(self):
        provider = FixtureProvider(FIXTURE_DIR)
        tester = Backtester(
            provider,
            make_config(),
            make_backtest(start=dt.date(2024, 1, 1), end=dt.date(2024, 2, 1)),
        )
        with self.assertRaises(ValueError):
            tester.run(provider.universe())


class TestDelistingHandling(unittest.TestCase):
    """The fixture DELISTED stops trading in 2024; that must not go unnoticed."""

    def run_with(self, policy):
        provider = FixtureProvider(FIXTURE_DIR)
        tester = Backtester(
            provider, make_config(), make_backtest(missing_price_policy=policy)
        )
        periods = tester.run(provider.universe())
        return tester.analyse(periods)

    def test_a_stale_last_price_is_not_reused_as_an_exit_price(self):
        # Once a company delists its last close stops updating, so a naive
        # lookup keeps settling the position at that price forever.
        result = self.run_with("drop")
        self.assertGreater(sum(p.unresolved for p in result.periods), 0)

    def test_the_policy_materially_changes_the_result(self):
        dropped = self.run_with("drop").stats.cagr
        wiped = self.run_with("zero").stats.cagr
        # Same strategy, same data: the only difference is how delistings are
        # settled, and it is the difference between a good and a bad result.
        self.assertGreater(dropped, wiped)
        self.assertGreater(dropped - wiped, 0.05)

    def test_the_drop_policy_warns_that_it_flatters_the_result(self):
        result = self.run_with("drop")
        self.assertTrue(
            any("flatters the result" in note for note in result.biases)
        )

    def test_the_delisted_name_is_actually_held_before_it_disappears(self):
        result = self.run_with("drop")
        held = {p.ticker for period in result.periods for p in period.positions}
        self.assertIn("DELISTED", held)


class TestAblation(unittest.TestCase):
    def test_each_condition_is_removed_in_turn(self):
        provider = FixtureProvider(FIXTURE_DIR)
        tester = Backtester(provider, make_config(), make_backtest())
        ablation = tester.ablation(provider.universe())
        self.assertEqual(
            sorted(ablation),
            [
                "without_gross_margin",
                "without_insider",
                "without_leverage",
                "without_market_cap",
                "without_returns",
            ],
        )

    def test_removing_a_condition_cannot_shrink_the_candidate_set(self):
        provider = FixtureProvider(FIXTURE_DIR)
        tester = Backtester(provider, make_config(), make_backtest())
        base = tester.analyse(tester.run(provider.universe())).stats
        for stats in tester.ablation(provider.universe()).values():
            self.assertGreaterEqual(
                stats.average_holdings, base.average_holdings
            )


class TestFactorLoading(unittest.TestCase):
    def load(self, text):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "factors.csv")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(text)
            return load_factors(path)

    def test_ken_french_header_and_footer_are_skipped(self):
        data = self.load(KEN_FRENCH_SAMPLE)
        self.assertEqual(len(data.rows), 3)
        self.assertIn("Mkt-RF", data.columns)
        # The annual table below the monthly rows must not be ingested.
        self.assertEqual(max(data.rows), dt.date(2022, 3, 31))

    def test_percentages_are_converted_to_decimals(self):
        data = self.load(KEN_FRENCH_SAMPLE)
        self.assertAlmostEqual(data.rows[dt.date(2022, 2, 28)]["Mkt-RF"], -0.0229)
        self.assertIn("percentages", data.scale_note)

    def test_decimal_files_are_left_alone(self):
        text = ",Mkt-RF,SMB,HML,RF\n202201,0.0121,0.0032,-0.0044,0.0001\n"
        data = self.load(text)
        self.assertAlmostEqual(data.rows[dt.date(2022, 1, 31)]["Mkt-RF"], 0.0121)
        self.assertIn("decimals", data.scale_note)

    def test_missing_data_sentinels_are_dropped(self):
        text = ",Mkt-RF,SMB,HML,RF\n202201,-99.99,2.20,3.11,0.01\n"
        data = self.load(text)
        self.assertNotIn("Mkt-RF", data.rows[dt.date(2022, 1, 31)])

    def test_compounding_requires_full_coverage_of_the_window(self):
        data = self.load(KEN_FRENCH_SAMPLE)
        covered = data.compound_between(
            dt.date(2021, 12, 31), dt.date(2022, 3, 31), ["Mkt-RF"]
        )
        self.assertIsNotNone(covered)
        # A window running past the last month of data must refuse, not
        # silently compound a shorter period and overstate alpha.
        self.assertIsNone(
            data.compound_between(
                dt.date(2021, 12, 31), dt.date(2022, 9, 30), ["Mkt-RF"]
            )
        )

    def test_compounding_is_multiplicative(self):
        data = self.load(KEN_FRENCH_SAMPLE)
        result = data.compound_between(
            dt.date(2021, 12, 31), dt.date(2022, 2, 28), ["Mkt-RF"]
        )
        expected = (1 - 0.0011) * (1 - 0.0229) - 1
        self.assertAlmostEqual(result["Mkt-RF"], expected)

    def test_a_file_without_factor_columns_is_rejected(self):
        with self.assertRaises(ValueError):
            self.load("date,value\n202201,1.0\n")

    def test_a_missing_file_is_reported(self):
        with self.assertRaises(FileNotFoundError):
            load_factors("/nonexistent/factors.csv")


class TestBacktestReporting(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        provider = FixtureProvider(FIXTURE_DIR)
        cls.tester = Backtester(provider, make_config(), make_backtest())
        periods = cls.tester.run(provider.universe())
        cls.result = cls.tester.analyse(periods)

    def test_json_round_trips(self):
        payload = json.loads(backtest_report.to_json(self.result))
        self.assertIn("biases", payload)
        self.assertEqual(len(payload["periods"]), len(self.result.periods))
        self.assertEqual(payload["backtest_config"]["frequency"], "quarterly")

    def test_csv_has_one_row_per_period(self):
        lines = [l for l in backtest_report.to_csv(self.result).splitlines() if l.strip()]
        self.assertEqual(len(lines), len(self.result.periods) + 1)

    def test_markdown_puts_the_biases_before_the_performance(self):
        text = backtest_report.to_markdown(self.result)
        self.assertIn("Read this before the numbers", text)
        self.assertLess(
            text.index("SURVIVORSHIP BIAS"), text.index("## Performance")
        )

    def test_markdown_states_it_is_not_advice(self):
        text = backtest_report.to_markdown(self.result)
        self.assertIn("not investment advice", text)

    def test_write_reports_creates_all_three_files(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = backtest_report.write_reports(directory, self.result)
            for path in paths.values():
                self.assertTrue(os.path.exists(path))
                self.assertGreater(os.path.getsize(path), 0)

    def test_console_summary_leads_with_the_biases(self):
        text = backtest_report.format_console(self.result)
        self.assertTrue(text.startswith("! SURVIVORSHIP BIAS"))


if __name__ == "__main__":
    unittest.main()
