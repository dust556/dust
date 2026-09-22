"""Numeric helpers: the None-propagation contract matters most here."""

import unittest

from smallcap.util.stats import (
    average_balance,
    clamp,
    mean,
    ols_slope,
    r_squared,
    ramp,
    safe_add,
    safe_div,
    sum_present,
)


class TestSafeArithmetic(unittest.TestCase):
    def test_safe_div_returns_none_rather_than_raising(self):
        self.assertIsNone(safe_div(1.0, 0.0))
        self.assertIsNone(safe_div(None, 2.0))
        self.assertIsNone(safe_div(2.0, None))
        self.assertAlmostEqual(safe_div(1.0, 4.0), 0.25)

    def test_safe_add_treats_missing_as_unknown_not_zero(self):
        # A missing component makes the whole sum unknown; returning 3.0 here
        # would let a company with an untagged debt line look debt-light.
        self.assertIsNone(safe_add(1.0, 2.0, None))
        self.assertEqual(safe_add(1.0, 2.0), 3.0)

    def test_sum_present_ignores_missing_components(self):
        self.assertEqual(sum_present(1.0, None, 2.0), 3.0)
        self.assertIsNone(sum_present(None, None))

    def test_average_balance_falls_back_to_a_single_endpoint(self):
        self.assertEqual(average_balance(100.0, 200.0), 150.0)
        self.assertEqual(average_balance(100.0, None), 100.0)
        self.assertEqual(average_balance(None, 200.0), 200.0)
        self.assertIsNone(average_balance(None, None))


class TestRegression(unittest.TestCase):
    def test_slope_of_a_clean_line(self):
        self.assertAlmostEqual(ols_slope([0, 1, 2, 3], [0.40, 0.42, 0.44, 0.46]), 0.02)

    def test_negative_slope_is_detected(self):
        slope = ols_slope([0, 1, 2, 3], [0.50, 0.48, 0.46, 0.44])
        self.assertLess(slope, 0)

    def test_slope_needs_two_points_and_x_variance(self):
        self.assertIsNone(ols_slope([1], [0.4]))
        self.assertIsNone(ols_slope([2, 2, 2], [0.4, 0.5, 0.6]))

    def test_r_squared_is_one_for_a_perfect_fit(self):
        self.assertAlmostEqual(r_squared([0, 1, 2, 3], [1, 2, 3, 4]), 1.0)

    def test_r_squared_falls_for_a_noisy_series(self):
        noisy = r_squared([0, 1, 2, 3, 4], [0.40, 0.50, 0.41, 0.52, 0.42])
        self.assertLess(noisy, 0.5)


class TestScaling(unittest.TestCase):
    def test_ramp_maps_onto_the_unit_interval(self):
        self.assertEqual(ramp(0.40, 0.40, 0.60), 0.0)
        self.assertEqual(ramp(0.60, 0.40, 0.60), 1.0)
        self.assertAlmostEqual(ramp(0.50, 0.40, 0.60), 0.5)

    def test_ramp_supports_an_inverted_metric(self):
        # Leverage: 0x is perfect, the 3x ceiling scores zero.
        self.assertEqual(ramp(0.0, 3.0, 0.0), 1.0)
        self.assertEqual(ramp(3.0, 3.0, 0.0), 0.0)
        self.assertAlmostEqual(ramp(1.5, 3.0, 0.0), 0.5)

    def test_ramp_clamps_outside_the_anchors(self):
        self.assertEqual(ramp(0.9, 0.4, 0.6), 1.0)
        self.assertEqual(ramp(0.1, 0.4, 0.6), 0.0)

    def test_clamp_and_mean_skip_missing(self):
        self.assertEqual(clamp(5.0, 0.0, 1.0), 1.0)
        self.assertEqual(mean([1.0, None, 3.0]), 2.0)
        self.assertIsNone(mean([None]))


if __name__ == "__main__":
    unittest.main()
