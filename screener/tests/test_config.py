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
