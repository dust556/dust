"""Config loading, overrides and the CLI wiring."""

import json
import os
import tempfile
import unittest

from smallcap.cli import build_parser, main, read_tickers
from smallcap.config import Config


class TestConfig(unittest.TestCase):
    def test_defaults_encode_the_five_conditions(self):
        config = Config()
        self.assertEqual(config.market_cap.min_usd, 500_000_000.0)
        self.assertEqual(config.market_cap.max_usd, 3_000_000_000.0)
        self.assertEqual(config.gross_margin.min_level, 0.40)
        self.assertEqual(config.leverage.max_debt_to_ebitda, 3.0)
        self.assertEqual(config.insider.min_ownership, 0.10)

    def test_override_coerces_to_the_target_type(self):
        config = Config()
        config.override("returns.min_roic", "0.15")
        self.assertEqual(config.returns.min_roic, 0.15)
        config.override("leverage.use_net_debt", "true")
        self.assertIs(config.leverage.use_net_debt, True)
        config.override("workers", "8")
        self.assertEqual(config.workers, 8)

    def test_override_reaches_into_the_weights_mapping(self):
        config = Config()
        config.override("scoring.weights.returns", "0.5")
        self.assertEqual(config.scoring.weights["returns"], 0.5)

    def test_unknown_key_is_rejected_rather_than_silently_ignored(self):
        config = Config()
        with self.assertRaises(KeyError):
            config.override("returns.no_such_setting", "1")

    def test_json_config_file_overlays_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "config.json")
            with open(path, "w") as handle:
                json.dump(
                    {"leverage": {"max_debt_to_ebitda": 2.0}, "workers": 2}, handle
                )
            config = Config.load(path)
            self.assertEqual(config.leverage.max_debt_to_ebitda, 2.0)
            self.assertEqual(config.workers, 2)
            # Untouched settings keep their defaults.
            self.assertEqual(config.insider.min_ownership, 0.10)

    def test_unknown_key_in_a_config_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "config.json")
            with open(path, "w") as handle:
                json.dump({"leverage": {"typo_here": 2.0}}, handle)
            with self.assertRaises(KeyError):
                Config.load(path)


class TestCli(unittest.TestCase):
    def test_tickers_are_deduplicated_and_uppercased(self):
        args = build_parser().parse_args(
            ["screen", "--tickers", "ideal,NOSKIN,ideal", "--provider", "fixtures"]
        )
        self.assertEqual(read_tickers(args), ["IDEAL", "NOSKIN"])

    def test_universe_file_comments_are_stripped(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "universe.txt")
            with open(path, "w") as handle:
                handle.write("# header\nIDEAL\n\nNOSKIN  # inline\n")
            args = build_parser().parse_args(
                ["screen", "--universe-file", path, "--provider", "fixtures"]
            )
            self.assertEqual(read_tickers(args), ["IDEAL", "NOSKIN"])

    def test_screen_writes_reports_end_to_end(self):
        fixtures = os.path.join(os.path.dirname(__file__), "..", "data", "fixtures")
        with tempfile.TemporaryDirectory() as directory:
            code = main(
                [
                    "screen",
                    "--provider", "fixtures",
                    "--fixtures", fixtures,
                    "--tickers", "IDEAL,NOSKIN",
                    "--out", directory,
                    "--quiet",
                ]
            )
            self.assertEqual(code, 0)
            with open(os.path.join(directory, "results.json")) as handle:
                payload = json.load(handle)
            self.assertEqual(payload["ranking"], ["IDEAL"])
            # The config is echoed so the run can be reproduced.
            self.assertEqual(payload["config"]["market_cap"]["max_usd"], 3e9)

    def test_set_override_changes_the_outcome(self):
        fixtures = os.path.join(os.path.dirname(__file__), "..", "data", "fixtures")
        with tempfile.TemporaryDirectory() as directory:
            main(
                [
                    "screen",
                    "--provider", "fixtures",
                    "--fixtures", fixtures,
                    "--tickers", "BIGCAP",
                    "--set", "market_cap.max_usd=20000000000",
                    "--out", directory,
                    "--quiet",
                ]
            )
            with open(os.path.join(directory, "results.json")) as handle:
                payload = json.load(handle)
            # Raising the ceiling lets the otherwise-qualifying large company through.
            self.assertEqual(payload["ranking"], ["BIGCAP"])

    def test_backtest_writes_reports_end_to_end(self):
        fixtures = os.path.join(os.path.dirname(__file__), "..", "data", "fixtures")
        with tempfile.TemporaryDirectory() as directory:
            code = main(
                [
                    "backtest",
                    "--provider", "fixtures",
                    "--fixtures", fixtures,
                    "--start", "2022-01-01",
                    "--end", "2026-03-31",
                    "--benchmark", "BIGCAP",
                    "--out", directory,
                    "--quiet",
                ]
            )
            self.assertEqual(code, 0)
            with open(os.path.join(directory, "backtest.json")) as handle:
                payload = json.load(handle)
            self.assertGreater(len(payload["periods"]), 10)
            self.assertTrue(
                any("SURVIVORSHIP" in b for b in payload["biases"])
            )

    def test_backtest_missing_price_policy_reaches_the_runner(self):
        fixtures = os.path.join(os.path.dirname(__file__), "..", "data", "fixtures")
        with tempfile.TemporaryDirectory() as directory:
            main(
                [
                    "backtest",
                    "--provider", "fixtures",
                    "--fixtures", fixtures,
                    "--start", "2022-01-01",
                    "--end", "2026-03-31",
                    "--benchmark", "BIGCAP",
                    "--missing-price-policy", "zero",
                    "--out", directory,
                    "--quiet",
                ]
            )
            with open(os.path.join(directory, "backtest.json")) as handle:
                payload = json.load(handle)
            self.assertEqual(
                payload["backtest_config"]["missing_price_policy"], "zero"
            )

    def test_universe_history_must_be_a_date_keyed_object(self):
        from smallcap.cli import _load_universe_history

        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "u.json")
            with open(path, "w") as handle:
                json.dump(["IDEAL"], handle)
            with self.assertRaises(ValueError):
                _load_universe_history(path)

            with open(path, "w") as handle:
                json.dump({"not-a-date": ["IDEAL"]}, handle)
            with self.assertRaises(ValueError):
                _load_universe_history(path)

            with open(path, "w") as handle:
                json.dump({"2022-01-01": ["ideal", "noskin"]}, handle)
            self.assertEqual(
                _load_universe_history(path), {"2022-01-01": ["IDEAL", "NOSKIN"]}
            )

    def test_malformed_as_of_is_rejected(self):
        code = main(["screen", "--provider", "fixtures", "--as-of", "not-a-date",
                     "--tickers", "IDEAL", "--quiet"])
        self.assertEqual(code, 2)

    def test_explain_returns_nonzero_for_an_unknown_ticker(self):
        fixtures = os.path.join(os.path.dirname(__file__), "..", "data", "fixtures")
        code = main(
            ["explain", "NOSUCHTICKER", "--provider", "fixtures", "--fixtures", fixtures]
        )
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()


class TestWithoutFlag(unittest.TestCase):
    """Skipping a condition must skip its fetching, not just its evaluation."""

    def setUp(self):
        self.fixtures = os.path.join(
            os.path.dirname(__file__), "..", "data", "fixtures"
        )

    def parse(self, *extra):
        return build_parser().parse_args(
            ["screen", "--provider", "fixtures", *extra]
        )

    def test_selected_criteria_drops_the_named_condition(self):
        from smallcap.cli import selected_criteria

        criteria, excluded = selected_criteria(self.parse("--without", "insider"))
        self.assertEqual(excluded, {"insider"})
        self.assertNotIn("insider", [c.key for c in criteria])
        self.assertEqual(len(criteria), 4)

    def test_multiple_exclusions_are_repeatable(self):
        from smallcap.cli import selected_criteria

        criteria, excluded = selected_criteria(
            self.parse("--without", "insider", "--without", "leverage")
        )
        self.assertEqual(excluded, {"insider", "leverage"})
        self.assertEqual(len(criteria), 3)

    def test_unknown_criterion_is_rejected_with_the_valid_keys(self):
        from smallcap.cli import selected_criteria

        with self.assertRaises(SystemExit) as caught:
            selected_criteria(self.parse("--without", "insdier"))
        self.assertIn("market_cap", str(caught.exception))

    def test_excluding_everything_is_rejected(self):
        from smallcap.cli import selected_criteria

        args = self.parse(
            *sum(
                [["--without", k] for k in
                 ["market_cap", "gross_margin", "returns", "leverage", "insider"]],
                [],
            )
        )
        with self.assertRaises(SystemExit):
            selected_criteria(args)

    def test_sec_provider_is_built_without_ownership_fetching(self):
        from smallcap.cli import build_provider
        from smallcap.providers.sec_edgar import SECEdgarProvider

        args = build_parser().parse_args(
            ["screen", "--provider", "sec", "--without", "insider"]
        )
        provider = build_provider(args, Config())
        self.assertIsInstance(provider, SECEdgarProvider)
        self.assertFalse(provider.fetch_insiders)

        args = build_parser().parse_args(["screen", "--provider", "sec"])
        self.assertTrue(build_provider(args, Config()).fetch_insiders)

    def test_screen_reports_only_the_kept_conditions(self):
        with tempfile.TemporaryDirectory() as directory:
            main([
                "screen", "--provider", "fixtures", "--fixtures", self.fixtures,
                "--tickers", "IDEAL", "--without", "insider",
                "--out", directory, "--quiet",
            ])
            with open(os.path.join(directory, "results.json")) as handle:
                payload = json.load(handle)
            keys = [c["key"] for c in payload["results"][0]["criteria"]]
            self.assertNotIn("insider", keys)
            self.assertEqual(len(keys), 4)

    def test_backtest_marks_a_partial_screen_prominently(self):
        with tempfile.TemporaryDirectory() as directory:
            main([
                "backtest", "--provider", "fixtures", "--fixtures", self.fixtures,
                "--start", "2022-01-01", "--end", "2026-03-31",
                "--benchmark", "BIGCAP", "--without", "insider",
                "--out", directory, "--quiet",
            ])
            with open(os.path.join(directory, "backtest.json")) as handle:
                payload = json.load(handle)
        # It must be the first thing a reader sees, ahead of survivorship.
        self.assertIn("PARTIAL SCREEN", payload["biases"][0])
        self.assertIn("not comparable to a full run", payload["biases"][0])

    def test_dropping_a_condition_changes_the_backtest_result(self):
        outputs = {}
        for label, extra in (("full", []), ("partial", ["--without", "insider"])):
            with tempfile.TemporaryDirectory() as directory:
                main([
                    "backtest", "--provider", "fixtures", "--fixtures", self.fixtures,
                    "--start", "2022-01-01", "--end", "2026-03-31",
                    "--benchmark", "BIGCAP", *extra,
                    "--out", directory, "--quiet",
                ])
                with open(os.path.join(directory, "backtest.json")) as handle:
                    outputs[label] = json.load(handle)["stats"]["cagr"]
        self.assertNotAlmostEqual(outputs["full"], outputs["partial"])
