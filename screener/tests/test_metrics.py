"""Financial derivations, checked against hand-computed values."""

import datetime as dt
import unittest

from smallcap.config import ReturnsConfig
from smallcap.metrics import (
    cost_of_debt,
    ebitda,
    effective_tax_rate,
    gross_margin,
    gross_profits_to_assets,
    implied_growth,
    invested_capital,
    net_debt,
    nopat,
    operating_working_capital,
    reinvestment_balance,
    reinvestment_cashflow,
    reinvestment_rate,
    roic,
    total_debt,
    trailing_twelve_months,
    wacc,
)
from smallcap.models import FinancialPeriod


def period(**kwargs) -> FinancialPeriod:
    defaults = dict(end=dt.date(2025, 12, 31), fp="FY", duration_days=365)
    defaults.update(kwargs)
    return FinancialPeriod(**defaults)


class TestIncomeStatement(unittest.TestCase):
    def test_gross_margin(self):
        self.assertAlmostEqual(
            gross_margin(period(revenue=1000.0, gross_profit=450.0)), 0.45
        )

    def test_gross_margin_derived_from_cost_of_revenue(self):
        self.assertAlmostEqual(
            gross_margin(period(revenue=1000.0, cost_of_revenue=550.0)), 0.45
        )

    def test_gross_margin_missing_revenue_is_none(self):
        self.assertIsNone(gross_margin(period(gross_profit=450.0)))

    def test_gross_profits_to_assets_is_the_novy_marx_ratio(self):
        self.assertAlmostEqual(
            gross_profits_to_assets(
                period(revenue=1000.0, gross_profit=450.0, total_assets=1800.0)
            ),
            0.25,
        )

    def test_ebitda_adds_back_depreciation(self):
        self.assertEqual(
            ebitda(period(operating_income=200.0, depreciation_amortization=50.0)), 250.0
        )

    def test_ebitda_falls_back_to_ebit_when_da_is_untagged(self):
        # Understating EBITDA makes the leverage test stricter, which is the
        # safe direction for an error.
        self.assertEqual(ebitda(period(operating_income=200.0)), 200.0)

    def test_ebitda_without_operating_income_is_none(self):
        self.assertIsNone(ebitda(period(depreciation_amortization=50.0)))


class TestTaxAndNopat(unittest.TestCase):
    def setUp(self):
        self.config = ReturnsConfig()

    def test_effective_tax_rate(self):
        rate = effective_tax_rate(
            period(pretax_income=1000.0, income_tax_expense=240.0), self.config
        )
        self.assertAlmostEqual(rate, 0.24)

    def test_loss_year_falls_back_to_the_statutory_rate(self):
        rate = effective_tax_rate(
            period(pretax_income=-500.0, income_tax_expense=-50.0), self.config
        )
        self.assertEqual(rate, self.config.default_tax_rate)

    def test_absurd_rate_is_clamped(self):
        rate = effective_tax_rate(
            period(pretax_income=100.0, income_tax_expense=900.0), self.config
        )
        self.assertEqual(rate, self.config.tax_rate_max)

    def test_nopat(self):
        value = nopat(
            period(operating_income=1000.0, pretax_income=1000.0, income_tax_expense=250.0),
            self.config,
        )
        self.assertAlmostEqual(value, 750.0)


class TestBalanceSheet(unittest.TestCase):
    def test_total_debt_sums_both_maturities(self):
        self.assertEqual(
            total_debt(period(short_term_debt=100.0, long_term_debt=400.0)), 500.0
        )

    def test_total_debt_with_only_one_line_present(self):
        self.assertEqual(total_debt(period(long_term_debt=400.0)), 400.0)
        self.assertIsNone(total_debt(period()))

    def test_net_debt_subtracts_cash_and_investments(self):
        value = net_debt(
            period(
                short_term_debt=100.0,
                long_term_debt=400.0,
                cash_and_equivalents=150.0,
                short_term_investments=50.0,
            )
        )
        self.assertEqual(value, 300.0)

    def test_invested_capital(self):
        value = invested_capital(
            period(
                short_term_debt=100.0,
                long_term_debt=400.0,
                total_equity=1000.0,
                cash_and_equivalents=200.0,
            )
        )
        self.assertEqual(value, 1300.0)

    def test_operating_working_capital_excludes_cash_and_short_debt(self):
        value = operating_working_capital(
            period(
                current_assets=500.0,
                current_liabilities=300.0,
                cash_and_equivalents=100.0,
                short_term_debt=50.0,
            )
        )
        self.assertEqual(value, 150.0)


class TestReturns(unittest.TestCase):
    def setUp(self):
        self.config = ReturnsConfig()
        self.prior = period(
            end=dt.date(2024, 12, 31),
            total_equity=900.0,
            long_term_debt=300.0,
            cash_and_equivalents=200.0,
            current_assets=400.0,
            current_liabilities=250.0,
        )
        self.latest = period(
            operating_income=200.0,
            pretax_income=180.0,
            income_tax_expense=45.0,
            depreciation_amortization=40.0,
            capex=90.0,
            total_equity=1000.0,
            long_term_debt=300.0,
            cash_and_equivalents=200.0,
            current_assets=460.0,
            current_liabilities=260.0,
        )

    def test_roic_uses_average_invested_capital(self):
        # NOPAT = 200 x (1 - 0.25) = 150.
        # IC: prior 1000, latest 1100 -> average 1050. 150/1050 = 14.29%.
        self.assertAlmostEqual(roic(self.latest, self.config, self.prior), 150 / 1050)

    def test_roic_is_none_when_invested_capital_is_negative(self):
        cash_pile = period(
            operating_income=100.0,
            total_equity=100.0,
            cash_and_equivalents=900.0,
        )
        self.assertIsNone(roic(cash_pile, self.config))

    def test_reinvestment_cashflow_nets_out_maintenance_capex(self):
        # growth capex 90 - 40 = 50; working capital 200 -> 250, so +50.
        self.assertAlmostEqual(
            reinvestment_cashflow(self.latest, self.prior), 100.0
        )

    def test_reinvestment_balance_is_the_change_in_invested_capital(self):
        self.assertAlmostEqual(reinvestment_balance(self.latest, self.prior), 100.0)

    def test_reinvestment_rate_is_none_when_nopat_is_negative(self):
        losing = period(operating_income=-50.0, capex=10.0, total_equity=100.0)
        self.assertIsNone(reinvestment_rate(losing, self.prior, self.config))

    def test_implied_growth_is_the_product(self):
        self.assertAlmostEqual(implied_growth(0.20, 0.40), 0.08)
        self.assertIsNone(implied_growth(None, 0.40))


class TestCostOfCapital(unittest.TestCase):
    def setUp(self):
        self.config = ReturnsConfig()

    def test_cost_of_debt_from_interest_expense(self):
        latest = period(interest_expense=30.0, long_term_debt=500.0)
        prior = period(end=dt.date(2024, 12, 31), long_term_debt=500.0)
        self.assertAlmostEqual(cost_of_debt(latest, prior, self.config), 0.06)

    def test_implausible_implied_rate_falls_back(self):
        latest = period(interest_expense=400.0, long_term_debt=500.0)
        prior = period(end=dt.date(2024, 12, 31), long_term_debt=500.0)
        self.assertAlmostEqual(
            cost_of_debt(latest, prior, self.config),
            self.config.risk_free_rate + self.config.default_credit_spread,
        )

    def test_wacc_weights_by_market_value(self):
        latest = period(
            operating_income=200.0,
            pretax_income=180.0,
            income_tax_expense=45.0,
            interest_expense=30.0,
            long_term_debt=500.0,
            total_equity=1000.0,
        )
        prior = period(end=dt.date(2024, 12, 31), long_term_debt=500.0)
        result = wacc(latest, prior, market_cap=1500.0, beta=1.0, config=self.config)
        # Re = 4.2% + 1.0 x 5.5% + 2.0% = 11.7%; Rd after tax = 6% x 0.75 = 4.5%.
        # Weights: E 1500/2000 = 0.75, D 500/2000 = 0.25.
        self.assertAlmostEqual(result.cost_of_equity, 0.117)
        self.assertAlmostEqual(result.wacc, 0.75 * 0.117 + 0.25 * 0.045, places=6)
        self.assertEqual(result.beta_source, "regression")

    def test_missing_beta_uses_the_small_cap_default(self):
        latest = period(operating_income=100.0, total_equity=500.0)
        result = wacc(latest, None, market_cap=1000.0, beta=None, config=self.config)
        self.assertEqual(result.beta, self.config.default_beta)
        self.assertEqual(result.beta_source, "default")

    def test_wacc_is_none_without_a_market_value(self):
        latest = period(operating_income=100.0, total_equity=500.0)
        result = wacc(latest, None, market_cap=None, beta=1.0, config=self.config)
        self.assertIsNone(result.wacc)

    def test_wacc_is_floored(self):
        config = ReturnsConfig(wacc_floor=0.20)
        latest = period(operating_income=100.0, total_equity=500.0)
        result = wacc(latest, None, market_cap=1000.0, beta=0.5, config=config)
        self.assertEqual(result.wacc, 0.20)
        self.assertTrue(result.floored)


class TestTrailingTwelveMonths(unittest.TestCase):
    def quarters(self, count=4, revenue=100.0):
        out = []
        for i in range(count):
            end = dt.date(2024, 3, 31) + dt.timedelta(days=91 * i)
            out.append(
                FinancialPeriod(
                    end=end,
                    fp=f"Q{(i % 4) + 1}",
                    duration_days=91,
                    revenue=revenue,
                    gross_profit=revenue * 0.5,
                    total_equity=1000.0 + i,
                )
            )
        return out

    def test_ttm_sums_flows_and_carries_stocks(self):
        ttm = trailing_twelve_months(self.quarters())
        self.assertIsNotNone(ttm)
        self.assertEqual(ttm.revenue, 400.0)
        self.assertEqual(ttm.gross_profit, 200.0)
        # Equity is a stock: the latest balance, never the sum.
        self.assertEqual(ttm.total_equity, 1003.0)
        self.assertEqual(ttm.fp, "TTM")

    def test_ttm_needs_four_quarters(self):
        self.assertIsNone(trailing_twelve_months(self.quarters(count=3)))

    def test_ttm_rejects_a_window_that_does_not_span_a_year(self):
        # A missing Q4 must not quietly produce a nine-month "year".
        short = self.quarters()
        for quarter in short:
            quarter.duration_days = 60
        self.assertIsNone(trailing_twelve_months(short))


if __name__ == "__main__":
    unittest.main()
