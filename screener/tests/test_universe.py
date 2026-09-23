"""Point-in-time universe construction and the survivorship measurement."""

import datetime as dt
import json
import os
import tempfile
import unittest

from smallcap.universe import (
    ANNUAL_FORMS,
    UniverseBuilder,
    coverage_report,
    parse_master_index,
    to_universe_history,
    _subtract_months,
)

MASTER_IDX = """Description:           Master Index of EDGAR Dissemination Feed
Last Data Received:    March 31, 2018

CIK|Company Name|Form Type|Date Filed|Filename
--------------------------------------------------------------------------------
320193|APPLE INC|10-K|2018-02-02|edgar/data/320193/0000320193-18-000007.txt
789019|MICROSOFT CORP|10-Q|2018-01-31|edgar/data/789019/0000789019-18-000002.txt
111111|GONE BUST INC|10-K|2018-03-01|edgar/data/111111/0000111111-18-000001.txt
222222|SMALL FILER CO|10-KSB|2018-03-15|edgar/data/222222/0000222222-18-000001.txt
333333|FOREIGN ISSUER SA|20-F|2018-03-20|edgar/data/333333/0000333333-18-000001.txt
"""


class FakeHttp:
    def __init__(self, payloads):
        self.payloads = payloads
        self.requested = []

    def get_text(self, url, accept="text/plain"):
        self.requested.append(url)
        for key, value in self.payloads.items():
            if key in url:
                return value
        from smallcap.util.http import HTTPError

        raise HTTPError(url, 404, "not found")


class TestMasterIndexParsing(unittest.TestCase):
    def test_only_domestic_annual_reports_are_kept(self):
        rows = parse_master_index(MASTER_IDX)
        ciks = {cik for cik, _form, _date in rows}
        self.assertEqual(ciks, {"0000320193", "0000111111", "0000222222"})

    def test_quarterly_reports_are_excluded(self):
        forms = {form for _cik, form, _date in parse_master_index(MASTER_IDX)}
        self.assertNotIn("10-Q", forms)

    def test_foreign_private_issuers_are_excluded(self):
        # 20-F filers report under different accounting rules, so their XBRL
        # does not line up with the us-gaap concepts the screen reads.
        rows = parse_master_index(MASTER_IDX)
        self.assertNotIn("0000333333", {cik for cik, _f, _d in rows})

    def test_header_and_separator_rows_are_ignored(self):
        self.assertEqual(len(parse_master_index(MASTER_IDX)), 3)

    def test_cik_is_zero_padded(self):
        for cik, _form, _date in parse_master_index(MASTER_IDX):
            self.assertEqual(len(cik), 10)

    def test_filing_dates_are_parsed(self):
        rows = {cik: date for cik, _form, date in parse_master_index(MASTER_IDX)}
        self.assertEqual(rows["0000320193"], dt.date(2018, 2, 2))

    def test_malformed_lines_do_not_raise(self):
        self.assertEqual(parse_master_index("garbage\n||\n1|2|3\n"), [])

    def test_form_filter_is_configurable(self):
        rows = parse_master_index(MASTER_IDX, forms={"10-Q"})
        self.assertEqual([r[0] for r in rows], ["0000789019"])


class TestSnapshots(unittest.TestCase):
    def builder(self, **kwargs):
        ticker_index = {
            "AAPL": {"cik": "0000320193", "name": "APPLE INC"},
            "SMLL": {"cik": "0000222222", "name": "SMALL FILER CO"},
            # 0000111111 (GONE BUST INC) has no ticker today -- it delisted.
        }
        return UniverseBuilder(
            http=FakeHttp({"2018/QTR1": MASTER_IDX}),
            ticker_index=ticker_index,
            **kwargs,
        )

    def test_snapshot_separates_filers_from_investable_names(self):
        builder = self.builder()
        filings = builder.annual_filers(dt.date(2018, 1, 1), dt.date(2018, 3, 31))
        snapshot = builder.snapshot(dt.date(2018, 6, 30), filings)
        self.assertEqual(len(snapshot.ciks), 3)
        self.assertEqual(snapshot.tickers, ["AAPL", "SMLL"])
        self.assertEqual(snapshot.unmapped_ciks, ["0000111111"])

    def test_coverage_is_the_share_that_still_has_a_ticker(self):
        builder = self.builder()
        filings = builder.annual_filers(dt.date(2018, 1, 1), dt.date(2018, 3, 31))
        snapshot = builder.snapshot(dt.date(2018, 6, 30), filings)
        self.assertAlmostEqual(snapshot.coverage, 2 / 3)

    def test_a_company_ages_out_of_the_lookback_window(self):
        builder = self.builder(lookback_months=3)
        filings = builder.annual_filers(dt.date(2018, 1, 1), dt.date(2018, 3, 31))
        # By 2019 nothing filed in early 2018 is still inside a 3-month window.
        snapshot = builder.snapshot(dt.date(2019, 6, 30), filings)
        self.assertEqual(snapshot.ciks, set())
        self.assertIsNone(snapshot.coverage)

    def test_a_future_filing_is_not_visible(self):
        builder = self.builder()
        filings = builder.annual_filers(dt.date(2018, 1, 1), dt.date(2018, 3, 31))
        # As of mid-February, Apple has filed (2 Feb) but GONE BUST (1 Mar)
        # has not.
        snapshot = builder.snapshot(dt.date(2018, 2, 15), filings)
        self.assertIn("0000320193", snapshot.ciks)
        self.assertNotIn("0000111111", snapshot.ciks)

    def test_missing_quarters_are_tolerated(self):
        builder = self.builder()
        # Only 2018 QTR1 exists in the fake; the rest 404 and contribute nothing.
        filings = builder.annual_filers(dt.date(2018, 1, 1), dt.date(2019, 12, 31))
        self.assertEqual(len(filings), 3)

    def test_the_index_is_fetched_once_per_quarter(self):
        builder = self.builder()
        builder.annual_filers(dt.date(2018, 1, 1), dt.date(2018, 12, 31))
        builder.annual_filers(dt.date(2018, 1, 1), dt.date(2018, 12, 31))
        first_quarter = [u for u in builder.http.requested if "2018/QTR1" in u]
        self.assertEqual(len(first_quarter), 1)

    def test_build_produces_one_snapshot_per_date(self):
        builder = self.builder()
        dates = [dt.date(2018, 6, 30), dt.date(2018, 9, 30)]
        snapshots = builder.build(dates)
        self.assertEqual(sorted(snapshots), dates)


class TestCikMapping(unittest.TestCase):
    def test_multiple_tickers_for_one_cik_resolve_deterministically(self):
        builder = UniverseBuilder(
            http=FakeHttp({}),
            ticker_index={
                "BRKB": {"cik": "0001067983"},
                "BRKA": {"cik": "0001067983"},
            },
        )
        mapping = builder.cik_to_ticker()
        self.assertEqual(mapping["0001067983"], "BRKA")

    def test_unpadded_ciks_in_the_index_still_match(self):
        builder = UniverseBuilder(
            http=FakeHttp({}), ticker_index={"AAPL": {"cik": "320193"}}
        )
        self.assertEqual(builder.cik_to_ticker()["0000320193"], "AAPL")


class TestCoverageReport(unittest.TestCase):
    def setUp(self):
        builder = UniverseBuilder(
            http=FakeHttp({"2018/QTR1": MASTER_IDX}),
            ticker_index={"AAPL": {"cik": "0000320193"}, "SMLL": {"cik": "0000222222"}},
        )
        filings = builder.annual_filers(dt.date(2018, 1, 1), dt.date(2018, 3, 31))
        self.snapshots = {
            dt.date(2018, 6, 30): builder.snapshot(dt.date(2018, 6, 30), filings)
        }

    def test_report_quantifies_the_remaining_bias(self):
        report = coverage_report(self.snapshots)
        row = report["periods"][0]
        self.assertEqual(row["filers"], 3)
        self.assertEqual(row["investable"], 2)
        self.assertEqual(row["unmapped"], 1)
        self.assertAlmostEqual(report["mean_coverage"], 2 / 3)

    def test_report_explains_what_the_number_means(self):
        report = coverage_report(self.snapshots)
        self.assertIn("survivorship", report["interpretation"])

    def test_universe_history_is_the_shape_the_backtester_consumes(self):
        history = to_universe_history(self.snapshots)
        self.assertEqual(history, {"2018-06-30": ["AAPL", "SMLL"]})
        # It must survive a JSON round trip, since that is how it is passed.
        self.assertEqual(json.loads(json.dumps(history)), history)

    def test_the_emitted_history_loads_back_through_the_cli_validator(self):
        from smallcap.cli import _load_universe_history

        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "u.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(to_universe_history(self.snapshots), handle)
            self.assertEqual(
                _load_universe_history(path), {"2018-06-30": ["AAPL", "SMLL"]}
            )


class TestDateArithmetic(unittest.TestCase):
    def test_subtract_months(self):
        self.assertEqual(_subtract_months(dt.date(2024, 3, 15), 15), dt.date(2022, 12, 15))
        self.assertEqual(_subtract_months(dt.date(2024, 1, 31), 1), dt.date(2023, 12, 31))

    def test_subtract_months_clamps_a_short_month(self):
        self.assertEqual(_subtract_months(dt.date(2024, 3, 31), 1), dt.date(2024, 2, 29))


if __name__ == "__main__":
    unittest.main()
