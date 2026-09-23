"""Providers: XBRL extraction, point-in-time filtering, ownership parsing."""

import datetime as dt
import json
import os
import tempfile
import unittest

from smallcap.config import Config
from smallcap.providers.fixtures import FixtureProvider
from smallcap.providers.prices import PriceProvider, _parse_price_csv, _weekly_returns
from smallcap.providers.sec_edgar import (
    SECEdgarProvider,
    parse_ownership_document,
)


class FakeHttp:
    """Serves canned payloads; asserts nothing hits the network."""

    def __init__(self, payloads):
        self.payloads = payloads
        self.requested = []

    def get_json(self, url):
        self.requested.append(url)
        for key, value in self.payloads.items():
            if key in url:
                return value
        raise KeyError(url)

    def get_text(self, url, accept="text/plain"):
        self.requested.append(url)
        for key, value in self.payloads.items():
            if key in url:
                return value
        raise KeyError(url)


def fact(start, end, val, filed, form="10-K", fy=None, fp="FY"):
    entry = {"end": end, "val": val, "filed": filed, "form": form, "fy": fy, "fp": fp}
    if start:
        entry["start"] = start
    return entry


COMPANY_FACTS = {
    "cik": 123,
    "entityName": "Test Co",
    "facts": {
        "dei": {
            "EntityCommonStockSharesOutstanding": {
                "units": {
                    "shares": [
                        fact(None, "2024-12-31", 40_000_000, "2025-02-20"),
                        fact(None, "2025-12-31", 41_000_000, "2026-02-20"),
                    ]
                }
            }
        },
        "us-gaap": {
            "Revenues": {
                "units": {
                    "USD": [
                        fact("2024-01-01", "2024-12-31", 1000.0, "2025-02-20"),
                        fact("2025-01-01", "2025-12-31", 1200.0, "2026-02-20"),
                    ]
                }
            },
            "RevenueFromContractWithCustomerExcludingAssessedTax": {
                "units": {
                    "USD": [
                        # The preferred concept for the same period: it wins.
                        fact("2025-01-01", "2025-12-31", 1250.0, "2026-02-20"),
                    ]
                }
            },
            "GrossProfit": {
                "units": {
                    "USD": [
                        fact("2024-01-01", "2024-12-31", 450.0, "2025-02-20"),
                        # Originally filed, then restated upward a year later.
                        fact("2025-01-01", "2025-12-31", 600.0, "2026-02-20"),
                        fact("2025-01-01", "2025-12-31", 625.0, "2027-02-20"),
                    ]
                }
            },
            "Assets": {
                "units": {
                    "USD": [
                        fact(None, "2024-12-31", 2000.0, "2025-02-20"),
                        fact(None, "2025-12-31", 2200.0, "2026-02-20"),
                    ]
                }
            },
            "StockholdersEquity": {
                "units": {
                    "USD": [fact(None, "2025-12-31", 1500.0, "2026-02-20")]
                }
            },
        },
    },
}


class TestSECExtraction(unittest.TestCase):
    def setUp(self):
        self.provider = SECEdgarProvider(Config(), http=FakeHttp({}))

    def test_preferred_concept_wins_over_a_fallback(self):
        periods = self.provider._build_periods(COMPANY_FACTS, as_of=None)
        latest = [p for p in periods if p.end == dt.date(2025, 12, 31)][0]
        self.assertEqual(latest.revenue, 1250.0)

    def test_later_filing_supersedes_an_earlier_one_for_the_same_period(self):
        periods = self.provider._build_periods(COMPANY_FACTS, as_of=None)
        latest = [p for p in periods if p.end == dt.date(2025, 12, 31)][0]
        self.assertEqual(latest.gross_profit, 625.0)

    def test_as_of_excludes_facts_not_yet_filed(self):
        # As of mid-2026 the restatement has not happened yet, so the screen
        # must see the originally reported figure -- this is the whole point
        # of point-in-time filtering.
        periods = self.provider._build_periods(
            COMPANY_FACTS, as_of=dt.date(2026, 6, 30)
        )
        latest = [p for p in periods if p.end == dt.date(2025, 12, 31)][0]
        self.assertEqual(latest.gross_profit, 600.0)

    def test_as_of_excludes_periods_entirely(self):
        periods = self.provider._build_periods(
            COMPANY_FACTS, as_of=dt.date(2025, 6, 30)
        )
        ends = {p.end for p in periods}
        self.assertNotIn(dt.date(2025, 12, 31), ends)
        self.assertIn(dt.date(2024, 12, 31), ends)

    def test_balance_sheet_attaches_to_the_matching_period_end(self):
        periods = self.provider._build_periods(COMPANY_FACTS, as_of=None)
        latest = [p for p in periods if p.end == dt.date(2025, 12, 31)][0]
        self.assertEqual(latest.total_assets, 2200.0)
        self.assertEqual(latest.total_equity, 1500.0)

    def test_cost_of_revenue_is_derived_when_untagged(self):
        periods = self.provider._build_periods(COMPANY_FACTS, as_of=None)
        latest = [p for p in periods if p.end == dt.date(2025, 12, 31)][0]
        self.assertEqual(latest.cost_of_revenue, 1250.0 - 625.0)

    def test_latest_share_count_respects_as_of(self):
        shares, date = self.provider._latest_shares(COMPANY_FACTS, as_of=None)
        self.assertEqual(shares, 41_000_000)
        shares, date = self.provider._latest_shares(
            COMPANY_FACTS, as_of=dt.date(2025, 6, 30)
        )
        self.assertEqual(shares, 40_000_000)
        self.assertEqual(date, dt.date(2024, 12, 31))


FORM4_XML = """<?xml version="1.0"?>
<ownershipDocument>
  <periodOfReport>2026-02-01</periodOfReport>
  <issuer><issuerCik>0000000123</issuerCik></issuer>
  <reportingOwner>
    <reportingOwnerId>
      <rptOwnerCik>0000000777</rptOwnerCik>
      <rptOwnerName>Founder Jane</rptOwnerName>
    </reportingOwnerId>
    <reportingOwnerRelationship>
      <isDirector>1</isDirector>
      <isOfficer>1</isOfficer>
      <isTenPercentOwner>0</isTenPercentOwner>
    </reportingOwnerRelationship>
  </reportingOwner>
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      <transactionDate><value>2026-02-01</value></transactionDate>
      <postTransactionAmounts>
        <sharesOwnedFollowingTransaction><value>5000000</value></sharesOwnedFollowingTransaction>
      </postTransactionAmounts>
      <ownershipNature>
        <directOrIndirectOwnership><value>D</value></directOrIndirectOwnership>
      </ownershipNature>
    </nonDerivativeTransaction>
    <nonDerivativeHolding>
      <postTransactionAmounts>
        <sharesOwnedFollowingTransaction><value>1200000</value></sharesOwnedFollowingTransaction>
      </postTransactionAmounts>
      <ownershipNature>
        <directOrIndirectOwnership><value>I</value></directOrIndirectOwnership>
        <natureOfOwnership><value>By family trust</value></natureOfOwnership>
      </ownershipNature>
    </nonDerivativeHolding>
  </nonDerivativeTable>
</ownershipDocument>
"""


class TestOwnershipParsing(unittest.TestCase):
    def test_parses_owner_identity_and_relationship(self):
        rows = parse_ownership_document(FORM4_XML)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["owner_name"], "Founder Jane")
        self.assertTrue(rows[0]["is_officer"])
        self.assertTrue(rows[0]["is_director"])
        self.assertFalse(rows[0]["is_ten_percent_owner"])

    def test_direct_and_indirect_holdings_are_separate_rows(self):
        rows = parse_ownership_document(FORM4_XML)
        forms = {row["ownership"]: row["shares"] for row in rows}
        self.assertEqual(forms["D"], 5_000_000.0)
        self.assertEqual(forms["I"], 1_200_000.0)

    def test_period_of_report_is_captured(self):
        rows = parse_ownership_document(FORM4_XML)
        self.assertEqual(rows[0]["as_of"], dt.date(2026, 2, 1))

    def test_sgml_wrapper_is_tolerated(self):
        wrapped = "<SEC-DOCUMENT>junk\n" + FORM4_XML + "\nmore junk</SEC-DOCUMENT>"
        self.assertEqual(len(parse_ownership_document(wrapped)), 2)

    def test_document_without_owners_yields_nothing(self):
        self.assertEqual(
            parse_ownership_document(
                "<ownershipDocument><periodOfReport>2026-01-01</periodOfReport></ownershipDocument>"
            ),
            [],
        )


class TestInsiderAggregation(unittest.TestCase):
    def test_holdings_are_summed_per_owner_across_ownership_forms(self):
        submissions = {
            "filings": {
                "recent": {
                    "form": ["4", "10-K"],
                    "accessionNumber": ["0000000123-26-000001", "0000000123-26-000002"],
                    "primaryDocument": ["form4.xml", "10k.htm"],
                    "reportDate": ["2026-02-01", "2025-12-31"],
                    "filingDate": ["2026-02-03", "2026-02-20"],
                }
            }
        }
        http = FakeHttp({"submissions": submissions, "form4.xml": FORM4_XML})
        provider = SECEdgarProvider(Config(), http=http)
        ownership = provider.fetch_insider_ownership(
            "0000000123", shares_outstanding=50e6, as_of=dt.date(2026, 3, 1)
        )
        self.assertEqual(ownership.total_shares, 6_200_000.0)
        self.assertEqual(len(ownership.holdings), 1)
        self.assertEqual(ownership.basis, "form345")
        self.assertTrue(any("lower bound" in n for n in ownership.notes))

    def test_filings_after_as_of_are_ignored(self):
        submissions = {
            "filings": {
                "recent": {
                    "form": ["4"],
                    "accessionNumber": ["0000000123-26-000001"],
                    "primaryDocument": ["form4.xml"],
                    "reportDate": ["2026-02-01"],
                    "filingDate": ["2026-02-03"],
                }
            }
        }
        http = FakeHttp({"submissions": submissions, "form4.xml": FORM4_XML})
        provider = SECEdgarProvider(Config(), http=http)
        ownership = provider.fetch_insider_ownership(
            "0000000123", shares_outstanding=50e6, as_of=dt.date(2026, 1, 1)
        )
        self.assertIsNone(ownership.total_shares)

    def test_external_ten_percent_holders_are_excluded_by_default(self):
        xml = FORM4_XML.replace("<isOfficer>1</isOfficer>", "<isOfficer>0</isOfficer>")
        xml = xml.replace("<isDirector>1</isDirector>", "<isDirector>0</isDirector>")
        xml = xml.replace(
            "<isTenPercentOwner>0</isTenPercentOwner>",
            "<isTenPercentOwner>1</isTenPercentOwner>",
        )
        submissions = {
            "filings": {
                "recent": {
                    "form": ["4"],
                    "accessionNumber": ["0000000123-26-000001"],
                    "primaryDocument": ["form4.xml"],
                    "reportDate": ["2026-02-01"],
                    "filingDate": ["2026-02-03"],
                }
            }
        }
        provider = SECEdgarProvider(
            Config(), http=FakeHttp({"submissions": submissions, "form4.xml": xml})
        )
        ownership = provider.fetch_insider_ownership(
            "0000000123", shares_outstanding=50e6, as_of=dt.date(2026, 3, 1)
        )
        self.assertIsNone(ownership.total_shares)


class TestPrices(unittest.TestCase):
    def test_csv_parsing_skips_malformed_rows(self):
        text = (
            "Date,Open,High,Low,Close,Volume\n"
            "2024-01-02,1,1,1,10.0,100\n"
            "bad,1,1,1,11.0,100\n"
            "2024-01-09,1,1,1,-5.0,100\n"
            "2024-01-16,1,1,1,12.1,100\n"
        )
        points = _parse_price_csv(text)
        self.assertEqual(len(points), 2)
        self.assertEqual(points[-1].close, 12.1)

    def test_weekly_returns_use_the_last_close_of_each_week(self):
        text = "Date,Close\n2024-01-02,10.0\n2024-01-03,10.5\n2024-01-09,11.0\n"
        returns = _weekly_returns(_parse_price_csv(text))
        self.assertEqual(len(returns), 1)
        self.assertAlmostEqual(list(returns.values())[0], 11.0 / 10.5 - 1.0)

    def test_beta_of_a_stock_that_tracks_the_benchmark_is_one(self):
        with tempfile.TemporaryDirectory() as directory:
            rows = ["Date,Close"]
            level = 100.0
            date = dt.date(2024, 1, 5)
            for week in range(120):
                level *= 1.0 + 0.01 * ((week % 5) - 2)
                rows.append(f"{(date + dt.timedelta(weeks=week)).isoformat()},{level:.4f}")
            text = "\n".join(rows) + "\n"
            for name in ("TEST", "SPY"):
                with open(os.path.join(directory, f"{name}.csv"), "w") as handle:
                    handle.write(text)
            provider = PriceProvider(prices_dir=directory, allow_network=False)
            beta = provider.estimate_beta(provider.history("TEST"))
            self.assertAlmostEqual(beta, 1.0, places=6)

    def test_missing_price_file_leaves_market_data_untouched(self):
        from smallcap.models import MarketData

        with tempfile.TemporaryDirectory() as directory:
            provider = PriceProvider(prices_dir=directory, allow_network=False)
            market = MarketData(ticker="NOPE")
            provider.enrich(market)
            self.assertIsNone(market.price)


class TestFixtureProvider(unittest.TestCase):
    def setUp(self):
        self.directory = os.path.join(
            os.path.dirname(__file__), "..", "data", "fixtures"
        )

    def test_universe_lists_every_fixture(self):
        provider = FixtureProvider(self.directory)
        self.assertIn("IDEAL", provider.universe())

    def test_unknown_ticker_raises_provider_error(self):
        from smallcap.providers.base import ProviderError

        provider = FixtureProvider(self.directory)
        with self.assertRaises(ProviderError):
            provider.fetch("NOSUCHTICKER")

    def test_as_of_filters_periods_not_yet_filed(self):
        provider = FixtureProvider(self.directory)
        full = provider.fetch("IDEAL")
        trimmed = provider.fetch("IDEAL", as_of=dt.date(2023, 1, 1))
        self.assertLess(len(trimmed.periods), len(full.periods))
        self.assertTrue(all(p.filed <= dt.date(2023, 1, 1) for p in trimmed.periods))

    def test_as_of_rewinds_the_price_not_just_the_filings(self):
        """Look-ahead on price would invalidate every backtest number."""
        provider = FixtureProvider(self.directory)
        early = provider.fetch("IDEAL", as_of=dt.date(2021, 6, 30))
        late = provider.fetch("IDEAL", as_of=dt.date(2026, 3, 31))
        self.assertIsNotNone(early.market.price)
        self.assertLess(early.market.price, late.market.price)
        self.assertLessEqual(early.market.price_date, dt.date(2021, 6, 30))

    def test_as_of_uses_the_share_count_on_file_at_the_time(self):
        provider = FixtureProvider(self.directory)
        early = provider.fetch("IDEAL", as_of=dt.date(2021, 6, 30))
        late = provider.fetch("IDEAL", as_of=dt.date(2026, 3, 31))
        # IDEAL buys stock back, so the historical count is the higher one.
        self.assertGreater(
            early.market.shares_outstanding, late.market.shares_outstanding
        )
        self.assertAlmostEqual(
            early.market.market_cap,
            early.market.price * early.market.shares_outstanding,
        )

    def test_repeated_fetches_do_not_corrupt_each_other(self):
        """A backtest fetches the same company at many dates, in any order."""
        provider = FixtureProvider(self.directory)
        first = len(provider.fetch("IDEAL", as_of=dt.date(2021, 6, 30)).market.history)
        provider.fetch("IDEAL", as_of=dt.date(2026, 3, 31))
        again = len(provider.fetch("IDEAL", as_of=dt.date(2021, 6, 30)).market.history)
        self.assertEqual(first, again)
        # The unfiltered company must still be intact afterwards.
        self.assertGreater(len(provider.fetch("IDEAL").market.history), first)

    def test_as_of_drops_insider_holdings_reported_later(self):
        provider = FixtureProvider(self.directory)
        before = provider.fetch("IDEAL", as_of=dt.date(2019, 1, 1))
        self.assertIsNone(before.insiders.total_shares)

    def test_sec_share_history_is_ordered_and_respects_as_of(self):
        provider = SECEdgarProvider(Config(), http=FakeHttp({}))
        history = provider._shares_history(COMPANY_FACTS, as_of=None)
        self.assertEqual([p.shares for p in history], [40_000_000, 41_000_000])
        self.assertEqual([p.date for p in history], sorted(p.date for p in history))
        trimmed = provider._shares_history(COMPANY_FACTS, as_of=dt.date(2025, 6, 30))
        self.assertEqual([p.shares for p in trimmed], [40_000_000])

    def test_round_trips_a_written_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            payload = {
                "ticker": "RT",
                "name": "Round Trip Co",
                "periods": [
                    {
                        "end": "2025-12-31",
                        "fp": "FY",
                        "filed": "2026-02-20",
                        "duration_days": 365,
                        "revenue": 100.0,
                        "gross_profit": 50.0,
                    }
                ],
                "market": {"ticker": "RT", "price": 10.0, "shares_outstanding": 1e6},
            }
            with open(os.path.join(directory, "RT.json"), "w") as handle:
                json.dump(payload, handle)
            company = FixtureProvider(directory).fetch("RT")
            self.assertEqual(company.name, "Round Trip Co")
            self.assertEqual(company.market.market_cap, 10e6)


if __name__ == "__main__":
    unittest.main()
