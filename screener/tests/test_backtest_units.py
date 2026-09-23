"""Calendar, portfolio construction and performance maths."""

import datetime as dt
import math
import unittest

from smallcap.backtest.calendar import rebalance_dates
from smallcap.backtest.performance import (
    MIN_USEFUL_PERIODS,
    annualise,
    compound,
    factor_regression,
    max_drawdown,
    ols_multivariate,
    sample_warnings,
    solve_linear_system,
    summarise_performance,
)
from smallcap.backtest.portfolio import (
    Position,
    assign_weights,
    build_period,
    compute_position_return,
    price_on_or_before,
    _turnover,
    _weighted_return,
)
from smallcap.models import PricePoint, ScreenResult


class TestCalendar(unittest.TestCase):
    def test_quarterly_dates_are_about_three_months_apart(self):
        dates = rebalance_dates(dt.date(2021, 1, 1), dt.date(2025, 12, 31))
        self.assertGreater(len(dates), 15)
        gaps = [(b - a).days for a, b in zip(dates, dates[1:])]
        self.assertTrue(all(85 <= g <= 95 for g in gaps), gaps)

    def test_reporting_lag_is_applied(self):
        # With a 75-day lag, the December period end becomes mid-March.
        dates = rebalance_dates(
            dt.date(2024, 1, 1), dt.date(2024, 12, 31), reporting_lag_days=75
        )
        self.assertEqual(dates[0], dt.date(2023, 12, 31) + dt.timedelta(days=75))

    def test_zero_lag_lands_on_period_ends(self):
        dates = rebalance_dates(
            dt.date(2024, 1, 1), dt.date(2024, 12, 31), reporting_lag_days=0
        )
        self.assertIn(dt.date(2024, 3, 31), dates)
        self.assertIn(dt.date(2024, 12, 31), dates)

    def test_annual_frequency_yields_one_date_per_year(self):
        dates = rebalance_dates(dt.date(2021, 1, 1), dt.date(2025, 12, 31), "annual")
        self.assertEqual(len(dates), 5)
        self.assertEqual(len({d.year for d in dates}), 5)

    def test_unknown_frequency_is_rejected(self):
        with self.assertRaises(ValueError):
            rebalance_dates(dt.date(2021, 1, 1), dt.date(2022, 1, 1), "hourly")

    def test_narrow_window_yields_nothing(self):
        dates = rebalance_dates(dt.date(2024, 4, 1), dt.date(2024, 4, 10))
        self.assertEqual(dates, [])


class TestWeighting(unittest.TestCase):
    def results(self, *pairs):
        return [
            ScreenResult(ticker=t, composite_score=s) for t, s in pairs
        ]

    def test_equal_weights_sum_to_one(self):
        weights = assign_weights(self.results(("A", 0.9), ("B", 0.1), ("C", 0.5)))
        self.assertAlmostEqual(sum(weights.values()), 1.0)
        self.assertAlmostEqual(weights["A"], weights["B"])

    def test_score_weighting_is_proportional(self):
        weights = assign_weights(
            self.results(("A", 0.75), ("B", 0.25)), scheme="score"
        )
        self.assertAlmostEqual(weights["A"], 0.75)
        self.assertAlmostEqual(weights["B"], 0.25)

    def test_score_weighting_falls_back_when_all_scores_are_zero(self):
        weights = assign_weights(self.results(("A", 0.0), ("B", 0.0)), scheme="score")
        self.assertAlmostEqual(weights["A"], 0.5)

    def test_empty_holdings_produce_no_weights(self):
        self.assertEqual(assign_weights([]), {})

    def test_unknown_scheme_is_rejected(self):
        with self.assertRaises(ValueError):
            assign_weights(self.results(("A", 1.0)), scheme="inverse-vol")


class TestMissingPricePolicy(unittest.TestCase):
    def position(self, exit_price=None):
        return Position(ticker="X", weight=1.0, entry_price=10.0, exit_price=exit_price)

    def test_observed_price_gives_the_real_return(self):
        result = compute_position_return(self.position(12.0), "drop")
        self.assertAlmostEqual(result.period_return, 0.2)
        self.assertEqual(result.resolution, "observed")

    def test_drop_leaves_the_return_undefined(self):
        result = compute_position_return(self.position(None), "drop")
        self.assertIsNone(result.period_return)
        self.assertEqual(result.resolution, "dropped")

    def test_zero_policy_assumes_a_total_loss(self):
        result = compute_position_return(self.position(None), "zero")
        self.assertEqual(result.period_return, -1.0)
        self.assertEqual(result.resolution, "imputed_total_loss")

    def test_flat_policy_assumes_no_change(self):
        result = compute_position_return(self.position(None), "flat")
        self.assertEqual(result.period_return, 0.0)

    def test_missing_entry_price_is_never_imputed(self):
        # Without an entry there was no position; inventing a return would be
        # fabricating a trade.
        position = Position(ticker="X", weight=1.0, entry_price=None, exit_price=12.0)
        result = compute_position_return(position, "zero")
        self.assertIsNone(result.period_return)
        self.assertEqual(result.resolution, "no_entry_price")

    def test_policy_choice_changes_the_portfolio_return(self):
        history = {
            "GOOD": [PricePoint(dt.date(2024, 1, 5), 10.0), PricePoint(dt.date(2024, 4, 5), 12.0)],
            "GONE": [PricePoint(dt.date(2024, 1, 5), 10.0)],
        }
        ranked = [ScreenResult(ticker="GOOD"), ScreenResult(ticker="GONE")]
        common = dict(
            rebalance_date=dt.date(2024, 1, 8),
            exit_date=dt.date(2024, 4, 8),
            ranked=ranked,
            price_lookup=lambda t: history.get(t, []),
        )
        dropped = build_period(**common, missing_price_policy="drop")
        wiped = build_period(**common, missing_price_policy="zero")
        # Dropping the delisted name reports +20%; assuming a wipe-out reports -40%.
        self.assertAlmostEqual(dropped.portfolio_return, 0.2)
        self.assertAlmostEqual(wiped.portfolio_return, -0.4)
        self.assertEqual(dropped.unresolved, 1)
        self.assertTrue(dropped.notes)

    def test_unknown_policy_is_rejected(self):
        with self.assertRaises(ValueError):
            build_period(
                dt.date(2024, 1, 8), dt.date(2024, 4, 8), [], lambda t: [],
                missing_price_policy="hope",
            )


class TestPeriodMechanics(unittest.TestCase):
    def test_price_on_or_before_picks_the_latest_eligible_close(self):
        history = [
            PricePoint(dt.date(2024, 1, 5), 10.0),
            PricePoint(dt.date(2024, 2, 5), 11.0),
            PricePoint(dt.date(2024, 3, 5), 12.0),
        ]
        self.assertEqual(price_on_or_before(history, dt.date(2024, 2, 20)).close, 11.0)
        self.assertIsNone(price_on_or_before(history, dt.date(2023, 1, 1)))

    def test_stale_entry_price_is_not_treated_as_tradeable(self):
        history = {"OLD": [PricePoint(dt.date(2023, 1, 5), 10.0)]}
        period = build_period(
            dt.date(2024, 1, 8),
            dt.date(2024, 4, 8),
            [ScreenResult(ticker="OLD")],
            lambda t: history.get(t, []),
            max_price_staleness_days=10,
        )
        self.assertIsNone(period.positions[0].entry_price)
        self.assertIsNone(period.portfolio_return)

    def test_weighted_return_renormalises_over_resolved_positions(self):
        positions = [
            Position(ticker="A", weight=0.5, period_return=0.10),
            Position(ticker="B", weight=0.5, period_return=None),
        ]
        # B is excluded, so the answer is A's return, not half of it.
        self.assertAlmostEqual(_weighted_return(positions), 0.10)

    def test_turnover_is_one_sided(self):
        self.assertAlmostEqual(_turnover({"A": 1.0}, {"B": 1.0}), 1.0)
        self.assertAlmostEqual(_turnover({"A": 0.5, "B": 0.5}, {"A": 1.0}), 0.5)
        self.assertIsNone(_turnover({"A": 1.0}, None))

    def test_max_holdings_caps_the_portfolio(self):
        ranked = [ScreenResult(ticker=f"T{i}") for i in range(10)]
        period = build_period(
            dt.date(2024, 1, 8), dt.date(2024, 4, 8), ranked, lambda t: [],
            max_holdings=3,
        )
        self.assertEqual(len(period.positions), 3)
        self.assertEqual(period.candidates, 10)


class TestPerformanceMaths(unittest.TestCase):
    def test_compound(self):
        self.assertAlmostEqual(compound([0.1, 0.1]), 0.21)
        self.assertIsNone(compound([]))

    def test_compound_stops_at_a_wipeout(self):
        self.assertEqual(compound([-1.0, 0.5]), -1.0)

    def test_annualise(self):
        self.assertAlmostEqual(annualise(0.21, 2.0), 0.1)
        self.assertIsNone(annualise(0.2, 0))

    def test_max_drawdown(self):
        self.assertAlmostEqual(max_drawdown([0.2, -0.5, 0.1]), -0.5)
        self.assertAlmostEqual(max_drawdown([0.1, 0.1]), 0.0)

    def test_summary_against_a_benchmark(self):
        stats = summarise_performance(
            [0.10, 0.05, -0.02, 0.08],
            [0.04, 0.03, 0.01, 0.02],
            periods_per_year=4.0,
        )
        self.assertEqual(stats.periods, 4)
        self.assertAlmostEqual(stats.hit_rate, 0.75)
        self.assertAlmostEqual(stats.win_rate_vs_benchmark, 0.75)
        self.assertGreater(stats.excess_cagr, 0)

    def test_summary_of_an_empty_series_warns_instead_of_dividing(self):
        stats = summarise_performance([None, None], [0.01, 0.01], periods_per_year=4.0)
        self.assertEqual(stats.periods, 0)
        self.assertIsNone(stats.cagr)
        self.assertTrue(stats.warnings)

    def test_small_sample_and_thin_portfolio_are_flagged(self):
        warnings = sample_warnings(periods=8, average_holdings=2.0, periods_per_year=4.0)
        self.assertEqual(len(warnings), 2)
        self.assertTrue(any("too few" in w for w in warnings))
        self.assertTrue(any("handful of names" in w for w in warnings))

    def test_adequate_sample_is_not_flagged(self):
        self.assertEqual(
            sample_warnings(MIN_USEFUL_PERIODS, 20.0, 4.0), []
        )


class TestRegression(unittest.TestCase):
    def test_ols_recovers_exact_coefficients(self):
        a = [1, 2, 3, 4, 5, 6]
        b = [2, 1, 4, 3, 6, 5]
        y = [1.0 + 2.0 * x + 3.0 * z for x, z in zip(a, b)]
        fit = ols_multivariate(y, {"a": a, "b": b})
        self.assertAlmostEqual(fit["intercept"], 1.0)
        self.assertAlmostEqual(fit["coefficients"]["a"], 2.0)
        self.assertAlmostEqual(fit["coefficients"]["b"], 3.0)
        self.assertAlmostEqual(fit["r_squared"], 1.0)

    def test_ols_needs_more_observations_than_predictors(self):
        self.assertIsNone(ols_multivariate([1.0, 2.0], {"a": [1, 2], "b": [2, 1]}))

    def test_collinear_factors_are_reported_not_silently_solved(self):
        a = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
        duplicate = list(a)
        y = [2.0 * x for x in a]
        self.assertIsNone(ols_multivariate(y, {"a": a, "same": duplicate}))

    def test_singular_system_returns_none(self):
        self.assertIsNone(solve_linear_system([[1.0, 2.0], [2.0, 4.0]], [1.0, 2.0]))

    def test_factor_regression_prices_out_factor_exposure(self):
        # Returns are exactly 1.5x the market factor plus the risk-free rate,
        # so the alpha must be zero and the market beta 1.5.
        market = [0.02, -0.01, 0.03, 0.04, -0.02, 0.01, 0.05, -0.03]
        risk_free = [0.005] * len(market)
        portfolio = [1.5 * m + rf for m, rf in zip(market, risk_free)]
        result = factor_regression(
            portfolio,
            [{"Mkt-RF": m} for m in market],
            risk_free,
            periods_per_year=4.0,
            factor_names=["Mkt-RF"],
        )
        self.assertAlmostEqual(result.alpha, 0.0, places=9)
        self.assertAlmostEqual(result.betas["Mkt-RF"], 1.5)
        self.assertEqual(result.observations, 8)

    def test_factor_regression_reports_when_factors_are_absent(self):
        result = factor_regression(
            [0.01, 0.02], [{"SMB": 0.01}, {"SMB": 0.0}], [0.0, 0.0], 4.0,
            factor_names=["Mkt-RF"],
        )
        self.assertTrue(result.warnings)
        self.assertIsNone(result.alpha)

    def test_factor_regression_with_no_overlap(self):
        result = factor_regression([None, None], [{}, {}], [0.0, 0.0], 4.0)
        self.assertEqual(result.observations, 0)
        self.assertTrue(result.warnings)


if __name__ == "__main__":
    unittest.main()
