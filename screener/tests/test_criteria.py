"""Each condition, including the paths that must not be reported as FAIL."""

import datetime as dt
import unittest

from smallcap.config import Config
from smallcap.criteria import (
    GrossMarginCriterion,
    InsiderOwnershipCriterion,
    LeverageCriterion,
    MarketCapCriterion,
    ReturnsCriterion,
)
from smallcap.models import (
    CompanyFinancials,
    FinancialPeriod,
    InsiderHolding,
    InsiderOwnership,
    MarketData,
    Verdict,
)


def annual(year, **kwargs):
    defaults = dict(
        end=dt.date(year, 12, 31),
        fy=year,
        fp="FY",
        filed=dt.date(year + 1, 2, 20),
        duration_days=365,
    )
    defaults.update(kwargs)
    return FinancialPeriod(**defaults)


class TestMarketCap(unittest.TestCase):
    def setUp(self):
        self.criterion = MarketCapCriterion()
        self.config = Config()

    def company(self, price, shares):
        return CompanyFinancials(
            ticker="TEST",
            market=MarketData(
                ticker="TEST",
                price=price,
                shares_outstanding=shares,
                price_date=dt.date(2026, 3, 31),
                shares_date=dt.date(2026, 2, 20),
                market_cap=price * shares,
            ),
        )

    def test_inside_the_band_passes(self):
        result = self.criterion.evaluate(self.company(20.0, 70e6), self.config)
        self.assertIs(result.verdict, Verdict.PASS)
        self.assertAlmostEqual(result.value, 1.4e9)

    def test_below_the_floor_fails(self):
        result = self.criterion.evaluate(self.company(5.0, 40e6), self.config)
        self.assertIs(result.verdict, Verdict.FAIL)
        self.assertIn("below", result.reasons[0])

    def test_above_the_ceiling_fails(self):
        result = self.criterion.evaluate(self.company(100.0, 200e6), self.config)
        self.assertIs(result.verdict, Verdict.FAIL)
        self.assertIn("exceeds", result.reasons[0])

    def test_missing_price_is_undecidable_not_a_failure(self):
        company = CompanyFinancials(
            ticker="TEST", market=MarketData(ticker="TEST", shares_outstanding=40e6)
        )
        result = self.criterion.evaluate(company, self.config)
        self.assertIs(result.verdict, Verdict.INSUFFICIENT_DATA)
        self.assertIn("price", result.missing)

    def test_score_peaks_mid_band(self):
        middle = self.criterion.evaluate(self.company(20.0, 65e6), self.config)
        edge = self.criterion.evaluate(self.company(20.0, 148e6), self.config)
        self.assertGreater(middle.score, edge.score)


class TestGrossMargin(unittest.TestCase):
    def setUp(self):
        self.criterion = GrossMarginCriterion()
        self.config = Config()

    def company(self, margins, revenue=1000.0):
        periods = []
        for offset, margin in enumerate(margins):
            year = 2021 + offset
            periods.append(
                annual(
                    year,
                    revenue=revenue,
                    gross_profit=revenue * margin,
                    cost_of_revenue=revenue * (1 - margin),
                    total_assets=revenue * 1.5,
                )
            )
        return CompanyFinancials(ticker="TEST", periods=periods)

    def test_high_and_rising_passes(self):
        result = self.criterion.evaluate(
            self.company([0.42, 0.44, 0.46, 0.48, 0.50]), self.config
        )
        self.assertIs(result.verdict, Verdict.PASS)
        self.assertGreater(result.detail["slope_per_year"], 0)

    def test_high_but_falling_fails(self):
        # The point of the condition: level alone is not enough.
        result = self.criterion.evaluate(
            self.company([0.58, 0.56, 0.54, 0.52, 0.50]), self.config
        )
        self.assertIs(result.verdict, Verdict.FAIL)
        self.assertFalse(result.detail["checks"]["slope"])
        self.assertTrue(result.detail["checks"]["level"])

    def test_rising_but_below_the_level_threshold_fails(self):
        result = self.criterion.evaluate(
            self.company([0.20, 0.22, 0.24, 0.26, 0.28]), self.config
        )
        self.assertIs(result.verdict, Verdict.FAIL)
        self.assertFalse(result.detail["checks"]["level"])
        self.assertTrue(result.detail["checks"]["slope"])

    def test_short_history_is_undecidable(self):
        result = self.criterion.evaluate(self.company([0.45, 0.46]), self.config)
        self.assertIs(result.verdict, Verdict.INSUFFICIENT_DATA)

    def test_noisy_trend_scores_below_a_clean_one(self):
        clean = self.criterion.evaluate(
            self.company([0.42, 0.44, 0.46, 0.48, 0.50]), self.config
        )
        noisy = self.criterion.evaluate(
            self.company([0.42, 0.50, 0.44, 0.47, 0.52]), self.config
        )
        self.assertIs(noisy.verdict, Verdict.PASS)
        self.assertGreater(clean.score, noisy.score)

    def test_novy_marx_ratio_is_reported(self):
        result = self.criterion.evaluate(
            self.company([0.42, 0.44, 0.46, 0.48, 0.50]), self.config
        )
        self.assertAlmostEqual(result.detail["gross_profits_to_assets"], 0.50 / 1.5)


class TestLeverage(unittest.TestCase):
    def setUp(self):
        self.criterion = LeverageCriterion()
        self.config = Config()

    def company(self, debt, operating_income, da=0.0, cash=0.0):
        return CompanyFinancials(
            ticker="TEST",
            periods=[
                annual(
                    2025,
                    operating_income=operating_income,
                    depreciation_amortization=da,
                    short_term_debt=debt * 0.1 if debt else 0.0,
                    long_term_debt=debt * 0.9 if debt else 0.0,
                    cash_and_equivalents=cash,
                )
            ],
        )

    def test_inside_the_ceiling_passes(self):
        result = self.criterion.evaluate(self.company(200.0, 80.0, da=20.0), self.config)
        self.assertIs(result.verdict, Verdict.PASS)
        self.assertAlmostEqual(result.value, 2.0)

    def test_above_the_ceiling_fails(self):
        result = self.criterion.evaluate(self.company(500.0, 80.0, da=20.0), self.config)
        self.assertIs(result.verdict, Verdict.FAIL)
        self.assertAlmostEqual(result.value, 5.0)

    def test_debt_free_passes_trivially(self):
        result = self.criterion.evaluate(self.company(0.0, 80.0, da=20.0), self.config)
        self.assertIs(result.verdict, Verdict.PASS)
        self.assertEqual(result.value, 0.0)
        self.assertEqual(result.score, 1.0)

    def test_debt_with_negative_ebitda_fails_rather_than_abstains(self):
        # There is no ratio to compute, but the condition is plainly not met.
        result = self.criterion.evaluate(self.company(300.0, -50.0), self.config)
        self.assertIs(result.verdict, Verdict.FAIL)

    def test_missing_operating_income_is_undecidable(self):
        company = CompanyFinancials(
            ticker="TEST", periods=[annual(2025, long_term_debt=100.0)]
        )
        result = self.criterion.evaluate(company, self.config)
        self.assertIs(result.verdict, Verdict.INSUFFICIENT_DATA)

    def test_net_debt_basis_is_configurable(self):
        config = Config()
        config.leverage.use_net_debt = True
        result = self.criterion.evaluate(
            self.company(500.0, 80.0, da=20.0, cash=400.0), config
        )
        self.assertIs(result.verdict, Verdict.PASS)
        self.assertAlmostEqual(result.value, 1.0)

    def test_gross_basis_ignores_the_cash_pile_by_default(self):
        result = self.criterion.evaluate(
            self.company(500.0, 80.0, da=20.0, cash=400.0), self.config
        )
        self.assertIs(result.verdict, Verdict.FAIL)


class TestInsiderOwnership(unittest.TestCase):
    def setUp(self):
        self.criterion = InsiderOwnershipCriterion()
        self.config = Config()

    def company(self, insider_shares, shares=100e6, basis="form345"):
        return CompanyFinancials(
            ticker="TEST",
            market=MarketData(ticker="TEST", shares_outstanding=shares, price=10.0),
            insiders=InsiderOwnership(
                total_shares=insider_shares,
                basis=basis,
                holdings=[
                    InsiderHolding(
                        owner_name="Founder",
                        shares=insider_shares,
                        is_officer=True,
                        is_director=True,
                    )
                ],
            ),
        )

    def test_above_the_threshold_passes(self):
        result = self.criterion.evaluate(self.company(18e6), self.config)
        self.assertIs(result.verdict, Verdict.PASS)
        self.assertAlmostEqual(result.value, 0.18)

    def test_below_the_threshold_fails(self):
        result = self.criterion.evaluate(self.company(1e6), self.config)
        self.assertIs(result.verdict, Verdict.FAIL)

    def test_near_miss_on_a_lower_bound_source_is_flagged(self):
        # 8.5% measured from Forms 3/4/5 could be above 10% in the proxy;
        # the result must say so rather than reject silently.
        result = self.criterion.evaluate(self.company(8.5e6), self.config)
        self.assertIs(result.verdict, Verdict.FAIL)
        self.assertTrue(result.detail["near_miss"])
        self.assertTrue(any("NEAR MISS" in r for r in result.reasons))

    def test_lower_bound_caveat_is_always_stated(self):
        result = self.criterion.evaluate(self.company(18e6), self.config)
        self.assertTrue(any("understate" in r for r in result.reasons))

    def test_missing_ownership_is_undecidable(self):
        company = CompanyFinancials(
            ticker="TEST",
            market=MarketData(ticker="TEST", shares_outstanding=100e6),
            insiders=None,
        )
        result = self.criterion.evaluate(company, self.config)
        self.assertIs(result.verdict, Verdict.INSUFFICIENT_DATA)


class TestReturns(unittest.TestCase):
    def setUp(self):
        self.criterion = ReturnsCriterion()
        self.config = Config()

    def company(self, operating_income, equity, capex, da, market_cap=1e9):
        periods = []
        for offset in range(4):
            year = 2022 + offset
            periods.append(
                annual(
                    year,
                    operating_income=operating_income * (1.1**offset),
                    pretax_income=operating_income * (1.1**offset),
                    income_tax_expense=operating_income * (1.1**offset) * 0.21,
                    depreciation_amortization=da,
                    capex=capex,
                    total_equity=equity * (1.1**offset),
                    current_assets=equity * 0.3,
                    current_liabilities=equity * 0.15,
                    long_term_debt=0.0,
                )
            )
        return CompanyFinancials(
            ticker="TEST",
            periods=periods,
            market=MarketData(
                ticker="TEST", market_cap=market_cap, beta=1.0, shares_outstanding=50e6
            ),
        )

    def test_high_return_with_reinvestment_passes(self):
        result = self.criterion.evaluate(
            self.company(operating_income=200.0, equity=500.0, capex=120.0, da=30.0),
            self.config,
        )
        self.assertIs(result.verdict, Verdict.PASS)
        self.assertGreater(result.detail["spread"], 0)

    def test_return_below_cost_of_capital_fails(self):
        result = self.criterion.evaluate(
            self.company(operating_income=30.0, equity=2000.0, capex=100.0, da=30.0),
            self.config,
        )
        self.assertIs(result.verdict, Verdict.FAIL)
        self.assertFalse(result.detail["checks"]["spread"])

    def test_high_return_with_no_reinvestment_fails(self):
        # The Mauboussin point: a high return that cannot be redeployed
        # compounds nothing.
        result = self.criterion.evaluate(
            self.company(operating_income=200.0, equity=500.0, capex=5.0, da=30.0),
            self.config,
        )
        self.assertIs(result.verdict, Verdict.FAIL)
        self.assertFalse(result.detail["checks"]["reinvestment"])

    def test_missing_market_cap_is_undecidable(self):
        company = self.company(200.0, 500.0, 120.0, 30.0)
        company.market.market_cap = None
        result = self.criterion.evaluate(company, self.config)
        self.assertIs(result.verdict, Verdict.INSUFFICIENT_DATA)

    def test_short_history_is_undecidable(self):
        company = self.company(200.0, 500.0, 120.0, 30.0)
        company.periods = company.periods[:1]
        result = self.criterion.evaluate(company, self.config)
        self.assertIs(result.verdict, Verdict.INSUFFICIENT_DATA)


if __name__ == "__main__":
    unittest.main()
