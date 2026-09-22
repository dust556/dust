#!/usr/bin/env python3
"""
Regression tests for the G3 research instruments added by Patch-2
(Master Specification v0.4.1a Addendum C, D, F, G).

Run: tests/run_python_tests.sh
"""
import os
import sys
import unittest

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))

from g3research import data_intake as di          # noqa: E402
from g3research import oat_pipeline as op         # noqa: E402
from g3research import portfolio_replay as pr     # noqa: E402
from g3research import spec_constants as sc       # noqa: E402
from g3research import stress_replay as sr        # noqa: E402


class SpecConstantMirror(unittest.TestCase):
    """P-000: the offline instruments must not drift from the EA."""

    def test_mirror_matches_mql5_sources(self):
        self.assertTrue(sc.verify_against_sources())

    def test_restricted_threshold_matches_ea(self):
        self.assertEqual(sc.effective_score_threshold(4, "RESTRICTED"), 6)
        self.assertEqual(sc.effective_score_threshold(4, "NORMAL"), 4)
        self.assertEqual(sc.effective_score_threshold(6, "MODERATE"), 6)

    def test_risk_pct_per_state(self):
        self.assertEqual(sc.risk_pct_for_state("NORMAL"), 0.50)
        self.assertEqual(sc.risk_pct_for_state("MODERATE"), 0.25)
        self.assertEqual(sc.risk_pct_for_state("RESTRICTED"), 0.10)
        self.assertEqual(sc.risk_pct_for_state("HARD_STOP"), 0.0)


class DataIntakeWindow(unittest.TestCase):
    """P-100 .. Addendum G (ISSUE-013): 61-71 months trim to the latest 60."""

    def test_below_floor_cannot_start(self):
        with self.assertRaises(di.DataIntakeError):
            di.canonical_window(59)

    def test_exactly_60_months(self):
        w = di.canonical_window(60)
        self.assertEqual(w["canonical_months"], 60)
        self.assertEqual(w["research_is_months"], 29)
        self.assertEqual(w["static_oos_months"], 19)
        self.assertEqual(w["final_holdout_months"], 12)
        self.assertEqual(w["excluded_oldest_months"], 0)

    def test_61_65_71_months_use_latest_60(self):
        for months in (61, 65, 71):
            w = di.canonical_window(months)
            self.assertEqual(w["canonical_months"], 60, months)
            self.assertEqual(w["research_is_months"], 29, months)
            self.assertEqual(w["static_oos_months"], 19, months)
            self.assertEqual(w["excluded_oldest_months"], months - 60, months)

    def test_72_months_switches_window(self):
        w = di.canonical_window(72)
        self.assertEqual(w["canonical_months"], 72)
        self.assertEqual(w["research_is_months"], 36)
        self.assertEqual(w["static_oos_months"], 24)
        self.assertEqual(w["excluded_oldest_months"], 0)

    def test_71_to_72_boundary_is_noted(self):
        self.assertIn("discontinuous", di.canonical_window(71)["boundary_note"])
        self.assertIn("discontinuous", di.canonical_window(72)["boundary_note"])

    def test_surplus_months_never_add_a_wf_fold(self):
        folds_60 = di.walk_forward_folds(di.canonical_window(60)["development_months"])
        folds_71 = di.walk_forward_folds(di.canonical_window(71)["development_months"])
        self.assertEqual(len(folds_60), len(folds_71))
        for fold in folds_71:
            self.assertEqual(fold["train_end_month"] - fold["train_start_month"], 24)
            self.assertEqual(fold["test_end_month"] - fold["test_start_month"], 6)

    def test_manifest_records_canonical_and_excluded(self):
        m = di.build_manifest(65, "2019-01-01", "2024-06-01", "feed-A", "abc123")
        self.assertEqual(m["canonical_window"]["months"], 60)
        self.assertEqual(m["excluded_oldest_months"], 5)
        self.assertTrue(m["excluded_from_gate_performance"])
        self.assertEqual(m["final_holdout_access"], "NONE")


class FinalHoldoutGuard(unittest.TestCase):
    """P-200: no instrument may reach the Final Holdout."""

    def test_oat_refuses_final_holdout(self):
        with self.assertRaises(op.HoldoutAccessError):
            op.assert_oat_dataset(op.DATASET_FINAL_HOLDOUT)

    def test_intake_manifest_declares_no_access(self):
        m = di.build_manifest(72, "2018-01-01", "2024-01-01", "feed-A", "h")
        self.assertEqual(m["final_holdout_access"], "NONE")


class OatOrdering(unittest.TestCase):
    """P-300 .. Addendum C (DEV-005)."""

    def fresh(self):
        p = op.OatPipeline()
        p.run_baseline_is()
        return p

    def test_oat_is_research_is_only(self):
        p = self.fresh()
        self.assertEqual(p.run_oat(op.FAMILY_PAIR_LOCAL, op.DATASET_RESEARCH_IS),
                         op.VENUE_SINGLE_PAIR_IS)
        with self.assertRaises(op.PipelineOrderError):
            p.run_oat(op.FAMILY_PAIR_LOCAL, op.DATASET_DEVELOPMENT)
        with self.assertRaises(op.PipelineOrderError):
            p.run_oat(op.FAMILY_PAIR_LOCAL, op.DATASET_STATIC_OOS)

    def test_portfolio_families_go_to_offline_replay(self):
        p = self.fresh()
        self.assertEqual(p.run_oat(op.FAMILY_PORTFOLIO_SHARED, op.DATASET_RESEARCH_IS),
                         op.VENUE_OFFLINE_PORTFOLIO_REPLAY)

    def test_wf_requires_freeze_first(self):
        p = self.fresh()
        p.run_oat(op.FAMILY_PAIR_LOCAL, op.DATASET_RESEARCH_IS)
        with self.assertRaises(op.PipelineOrderError):
            p.run_walk_forward("v1", "s", "c", "d", {"m": 48}, "t", {})

    def test_oat_stops_after_freeze(self):
        p = self.fresh()
        p.run_oat(op.FAMILY_PAIR_LOCAL, op.DATASET_RESEARCH_IS)
        p.report_oat_families([{"family": "H4 Slope", "reported": True}])
        p.freeze_baseline()
        with self.assertRaises(op.PipelineOrderError):
            p.run_oat(op.FAMILY_PAIR_LOCAL, op.DATASET_RESEARCH_IS)

    def test_incomplete_oat_report_is_refused(self):
        p = self.fresh()
        p.run_oat(op.FAMILY_PAIR_LOCAL, op.DATASET_RESEARCH_IS)
        with self.assertRaises(op.PipelineOrderError):
            p.report_oat_families([{"family": "H4 Slope", "reported": True},
                                   {"family": "M5 Breakout", "reported": False}])

    def test_wf_cannot_select_parameters(self):
        p = self.fresh()
        with self.assertRaises(op.PipelineOrderError):
            p.adopt_walk_forward_parameter("H4 Slope Threshold", 0.13)

    def test_static_oos_needs_wf_and_is_one_shot(self):
        p = self.fresh()
        p.run_oat(op.FAMILY_PAIR_LOCAL, op.DATASET_RESEARCH_IS)
        p.report_oat_families([{"family": "H4 Slope", "reported": True}])
        with self.assertRaises(op.PipelineOrderError):
            p.open_static_oos(False)
        p.freeze_baseline()
        p.run_walk_forward("v1", "s", "c", "d", {"m": 48}, "t", {})
        with self.assertRaises(op.PipelineOrderError):
            p.open_static_oos(True)          # spec changed after WF
        self.assertTrue(p.open_static_oos(False))
        with self.assertRaises(op.PipelineOrderError):
            p.open_static_oos(False)         # second read

    def test_change_after_oos_marks_contamination(self):
        p = self.fresh()
        p.run_oat(op.FAMILY_PAIR_LOCAL, op.DATASET_RESEARCH_IS)
        p.report_oat_families([{"family": "H4 Slope", "reported": True}])
        p.freeze_baseline()
        p.run_walk_forward("v1", "s", "c", "d", {"m": 48}, "t", {})
        p.open_static_oos(False)
        self.assertFalse(p.mark_change_after_oos(["documentation"]))
        self.assertTrue(p.mark_change_after_oos(["threshold"]))


class WfIterationManifestRules(unittest.TestCase):
    """P-400 .. N-1 and LOW-4."""

    def test_one_confirmatory_run_per_triple(self):
        m = op.WfIterationManifest()
        self.assertTrue(m.can_run_confirmatory("s", "c", "d"))
        m.record_confirmatory("v1", "s", "c", "d", {"m": 48}, "t1", {"netR": 1.0})
        self.assertFalse(m.can_run_confirmatory("s", "c", "d"))
        with self.assertRaises(op.PipelineOrderError):
            m.record_confirmatory("v1", "s", "c", "d", {"m": 48}, "t2", {})
        # a different data hash is a different experiment
        self.assertTrue(m.can_run_confirmatory("s", "c", "d2"))

    def test_technical_rerun_requires_reason_and_evidence(self):
        m = op.WfIterationManifest()
        m.record_confirmatory("v1", "s", "c", "d", {"m": 48}, "t1", {})
        with self.assertRaises(op.PipelineOrderError):
            m.record_technical_rerun("v1", "s", "c", "d", {"m": 48}, "t2",
                                     "", "evidence", {})
        with self.assertRaises(op.PipelineOrderError):
            m.record_technical_rerun("v1", "s", "c", "d", {"m": 48}, "t2",
                                     "tester crash", "", {})

    def test_technical_rerun_must_not_change_the_window(self):
        m = op.WfIterationManifest()
        m.record_confirmatory("v1", "s", "c", "d", {"m": 48}, "t1", {})
        with self.assertRaises(op.PipelineOrderError):
            m.record_technical_rerun("v1", "s", "c", "d", {"m": 60}, "t2",
                                     "tester crash", "log.txt", {})

    def test_technical_rerun_without_prior_run_is_refused(self):
        m = op.WfIterationManifest()
        with self.assertRaises(op.PipelineOrderError):
            m.record_technical_rerun("v1", "s", "c", "d", {"m": 48}, "t",
                                     "crash", "log", {})

    def test_technical_rerun_is_queued_for_review(self):
        m = op.WfIterationManifest()
        m.record_confirmatory("v1", "s", "c", "d", {"m": 48}, "t1", {})
        entry = m.record_technical_rerun("v1", "s", "c", "d", {"m": 48}, "t2",
                                         "VPS power loss", "syslog#412", {})
        self.assertTrue(entry["review_required"])
        self.assertEqual(len(m.review_queue()), 1)
        self.assertIn("technical_rerun_review_queue", m.to_manifest())


class StressReplay(unittest.TestCase):
    """P-500 .. Addendum D (DEV-006)."""

    def test_only_preregistered_scenarios_exist(self):
        self.assertEqual(sorted(sr.SCENARIOS),
                         ["BASE", "STRESS_1", "STRESS_2", "STRESS_3"])
        with self.assertRaises(sr.StressScenarioError):
            sr.scenario("STRESS_4")

    def test_scenario_values_match_v04_section_13_5(self):
        self.assertEqual(sr.SCENARIOS["STRESS_1"]["spread_multiplier"], 1.5)
        self.assertEqual(sr.SCENARIOS["STRESS_1"]["adverse_slippage_fraction"], 0.25)
        self.assertEqual(sr.SCENARIOS["STRESS_2"]["spread_multiplier"], 2.0)
        self.assertEqual(sr.SCENARIOS["STRESS_2"]["adverse_slippage_fraction"], 0.50)
        self.assertEqual(sr.SCENARIOS["STRESS_3"]["spread_multiplier"], 3.0)
        self.assertEqual(sr.SCENARIOS["STRESS_3"]["adverse_slippage_fraction"], 1.00)

    def test_base_scenario_is_neutral(self):
        self.assertEqual(sr.stressed_spread(0.00012, "BASE"), 0.00012)
        self.assertEqual(sr.adverse_slippage(0.00012, "BASE"), 0.0)

    def test_stress_moves_both_legs_against_the_position(self):
        buy = sr.stressed_prices("BUY", 1.10000, 1.10012, 0.00012, "STRESS_2")
        self.assertGreater(buy["entry_price"], 1.10012)
        self.assertLess(buy["exit_price"], 1.10000)
        sell = sr.stressed_prices("SELL", 1.10000, 1.10012, 0.00012, "STRESS_2")
        self.assertLess(sell["entry_price"], 1.10000)
        self.assertGreater(sell["exit_price"], 1.10012)

    def test_stressed_spread_beyond_hard_max_rejects_entry(self):
        atr = 0.0010
        self.assertFalse(sr.spread_blocks_entry(sr.stressed_spread(0.00010, "BASE"), atr))
        # 0.00010 * 3.0 = 0.00030 -> ratio 0.30 > 0.20 hard max
        self.assertTrue(sr.spread_blocks_entry(sr.stressed_spread(0.00010, "STRESS_3"), atr))

    def test_geometry_is_restaged_not_just_deducted(self):
        base = sr.restage_trade("BUY", 1.10000, 1.09900, "A", 12, 0.0010)
        stressed = sr.restage_trade("BUY", 1.10020, 1.09900, "A", 12, 0.0010)
        self.assertAlmostEqual(base["r_distance"], 0.00100, places=10)
        self.assertAlmostEqual(stressed["r_distance"], 0.00120, places=10)
        self.assertNotAlmostEqual(base["take_profit"], stressed["take_profit"])
        self.assertAlmostEqual(stressed["take_profit"], 1.10020 + 2 * 0.00120, places=10)

    def test_mode_b_triggers_move_with_the_entry(self):
        g = sr.restage_trade("BUY", 1.10020, 1.09900, "B", 0, 0.0010)
        self.assertAlmostEqual(g["breakeven_trigger"], 1.10020 + 1.0 * 0.00120, places=10)
        self.assertAlmostEqual(g["partial_trigger"], 1.10020 + 1.5 * 0.00120, places=10)
        self.assertEqual(g["trail_atr_multiple"], 2.0)
        self.assertIsNone(g["take_profit"])

    def test_mode_c_has_no_fixed_tp(self):
        g = sr.restage_trade("SELL", 1.10000, 1.10100, "C", 0, 0.0010)
        self.assertIsNone(g["take_profit"])
        self.assertEqual(g["trail_atr_multiple"], 2.5)

    def test_parity_gate_all_four_conditions(self):
        self.assertTrue(sr.base_parity_gate(99.0, 98.0, 0.05, 10.2, 10.0)["pass"])
        self.assertFalse(sr.base_parity_gate(98.9, 98.0, 0.05, 10.0, 10.0)["pass"])
        self.assertFalse(sr.base_parity_gate(99.0, 97.9, 0.05, 10.0, 10.0)["pass"])
        self.assertFalse(sr.base_parity_gate(99.0, 98.0, 0.051, 10.0, 10.0)["pass"])
        self.assertFalse(sr.base_parity_gate(99.0, 98.0, 0.05, 10.3, 10.0)["pass"])

    def test_net_r_denominator_floor_avoids_division_by_zero(self):
        self.assertAlmostEqual(sr.net_r_relative_diff_pct(0.02, 0.0), 2.0, places=10)
        self.assertAlmostEqual(sr.net_r_relative_diff_pct(0.5, 0.4), 10.0, places=10)

    def test_parity_failure_blocks_stress_evidence(self):
        gate = sr.base_parity_gate(98.0, 98.0, 0.05, 10.0, 10.0)
        self.assertFalse(gate["stress_results_usable_as_g3_pass_evidence"])


class PortfolioReplayOrdering(unittest.TestCase):
    """P-600 .. Addendum F (ISSUE-003) tie-break."""

    def test_initial_seven_order_is_the_addendum_order(self):
        self.assertEqual(pr.UNIVERSE_ORDER_INITIAL7,
                         ["AUDUSD", "EURUSD", "GBPUSD", "NZDUSD",
                          "USDCAD", "USDCHF", "USDJPY"])

    def test_simultaneous_candidates_use_the_fixed_order(self):
        cands = [{"symbol": s, "decision_time": 100} for s in
                 ["USDJPY", "EURUSD", "AUDUSD", "GBPUSD"]]
        ordered = [c["symbol"] for c in pr.sort_candidates(cands)]
        self.assertEqual(ordered, ["AUDUSD", "EURUSD", "GBPUSD", "USDJPY"])

    def test_stage2_symbols_come_after_and_sort_ascii(self):
        cands = [{"symbol": s, "decision_time": 100} for s in
                 ["EURJPY", "AUDCAD", "USDJPY"]]
        ordered = [c["symbol"] for c in pr.sort_candidates(cands)]
        self.assertEqual(ordered, ["USDJPY", "AUDCAD", "EURJPY"])

    def test_decision_time_dominates_universe_order(self):
        cands = [{"symbol": "USDJPY", "decision_time": 100},
                 {"symbol": "AUDUSD", "decision_time": 200}]
        ordered = [c["symbol"] for c in pr.sort_candidates(cands)]
        self.assertEqual(ordered, ["USDJPY", "AUDUSD"])

    def test_simultaneous_counts_and_conflict_rejections(self):
        cands = [{"symbol": "AUDUSD", "decision_time": 100},
                 {"symbol": "EURUSD", "decision_time": 100},
                 {"symbol": "GBPUSD", "decision_time": 300}]
        counts = pr.simultaneous_candidate_counts(cands)
        self.assertEqual(counts[100], 2)
        self.assertEqual(counts[300], 1)
        decisions = [{"accepted": False, "simultaneous_candidates": 2},
                     {"accepted": False, "simultaneous_candidates": 1},
                     {"accepted": True, "simultaneous_candidates": 2}]
        self.assertEqual(len(pr.order_conflict_rejections(decisions)), 1)


def candidate(symbol, t, side="BUY", score=6, result_r=0.0, exit_time=None,
              risk_1lot=1000.0):
    return {"symbol": symbol, "decision_time": t, "side": side,
            "total_score": score, "risk_1lot_money": risk_1lot,
            "volume_step": 0.01, "volume_min": 0.01,
            "result_r": result_r, "exit_time": exit_time or (t + 60)}


class PortfolioReplaySharedState(unittest.TestCase):
    """P-700 .. one shared state machine, never a per-pair sum."""

    def test_max_positions_is_shared_across_pairs(self):
        r = pr.PortfolioReplay(100000.0, 5)
        # eight distinct currencies, so only MaxPositions can bind here
        cands = [candidate(s, 100 + i, exit_time=100000)
                 for i, s in enumerate(["AUDUSD", "EURJPY", "GBPCHF", "NZDCAD"])]
        decisions = r.run(cands)
        self.assertEqual(sum(1 for d in decisions if d["accepted"]), 3)
        self.assertEqual(decisions[3]["reason"], "MAX_POSITIONS")

    def test_four_usd_quoted_longs_hit_currency_exposure_first(self):
        """The USD leg of four long majors is the binding constraint, not
        MaxPositions: the shared book sees one short-USD exposure."""
        r = pr.PortfolioReplay(100000.0, 5)
        cands = [candidate(s, 100 + i, exit_time=100000)
                 for i, s in enumerate(["AUDUSD", "EURUSD", "GBPUSD", "NZDUSD"])]
        decisions = r.run(cands)
        self.assertEqual(decisions[2]["reason"], "CURRENCY_EXPOSURE")

    def test_currency_exposure_is_shared_across_pairs(self):
        r = pr.PortfolioReplay(100000.0, 5)
        # three long EUR legs at 0.50% each would be 1.50% > 1.00%
        cands = [candidate("EURUSD", 100, exit_time=100000),
                 candidate("EURJPY", 101, exit_time=100000),
                 candidate("EURGBP", 102, exit_time=100000)]
        decisions = r.run(cands)
        self.assertTrue(decisions[0]["accepted"])
        self.assertTrue(decisions[1]["accepted"])
        self.assertFalse(decisions[2]["accepted"])
        self.assertEqual(decisions[2]["reason"], "CURRENCY_EXPOSURE")

    def test_total_risk_ceiling(self):
        r = pr.PortfolioReplay(100000.0, 5)
        # risk_1lot chosen so each leg books ~0.50%; three legs = 1.50% exactly
        cands = [candidate("AUDUSD", 100, exit_time=100000),
                 candidate("GBPJPY", 101, exit_time=100000),
                 candidate("NZDCHF", 102, exit_time=100000)]
        decisions = r.run(cands)
        self.assertEqual(sum(1 for d in decisions if d["accepted"]), 3)
        self.assertLessEqual(sum(d["risk_pct"] for d in decisions if d["accepted"]),
                             pr.SPEC["G3_MAX_TOTAL_RISK_PCT"] + 1e-9)

    def test_shared_dd_state_degrades_risk_for_every_pair(self):
        r = pr.PortfolioReplay(100000.0, 5)
        losing = candidate("AUDUSD", 100, result_r=-14.0, exit_time=150)
        # the next day, so the shared DD state is what binds, not the lock
        later = candidate("EURUSD", 200000, exit_time=300000)
        decisions = r.run([losing, later])
        self.assertTrue(decisions[0]["accepted"])
        # a 7% equity loss puts the shared machine into MODERATE
        self.assertEqual(decisions[1]["dd_state"], "MODERATE")
        self.assertAlmostEqual(decisions[1]["risk_pct"], 0.25, places=2)

    def test_hard_stop_latches_for_the_whole_portfolio(self):
        r = pr.PortfolioReplay(100000.0, 5)
        wipe = candidate("AUDUSD", 100, result_r=-21.0, exit_time=150)
        later = candidate("EURUSD", 200000, exit_time=300000)
        decisions = r.run([wipe, later])
        self.assertFalse(decisions[1]["accepted"])
        self.assertEqual(decisions[1]["reason"], "HARD_STOP_LATCHED")
        self.assertTrue(r.hard_stop_latched)

    def test_daily_entry_lock_is_shared(self):
        r = pr.PortfolioReplay(100000.0, 5)
        loss = candidate("AUDUSD", 100, result_r=-5.0, exit_time=150)
        later = candidate("EURUSD", 200, exit_time=100000)
        decisions = r.run([loss, later])
        self.assertEqual(decisions[1]["reason"], "DAILY_ENTRY_LOCK")

    def test_restricted_state_raises_the_threshold(self):
        r = pr.PortfolioReplay(100000.0, 5)
        loss = candidate("AUDUSD", 100, result_r=-17.0, exit_time=150)
        # score 5 passes in NORMAL but not in RESTRICTED (threshold 6)
        later = candidate("EURUSD", 90000, score=5, exit_time=200000)
        decisions = r.run([loss, later])
        self.assertEqual(decisions[1]["dd_state"], "RESTRICTED")
        self.assertEqual(decisions[1]["reason"], "TOTAL_SCORE_BELOW_THRESHOLD")


class PortfolioReplayCorrelation(unittest.TestCase):
    """P-800 .. correlation guard inside the replay."""

    def test_direction_adjusted_cluster_blocks(self):
        def corr(a, b, t):
            return 0.95, True, 60
        r = pr.PortfolioReplay(100000.0, 5, correlation_provider=corr)
        decisions = r.run([candidate("AUDUSD", 100, exit_time=100000),
                           candidate("NZDCHF", 101, exit_time=100000),
                           candidate("GBPJPY", 102, exit_time=100000)])
        reasons = [d["reason"] for d in decisions]
        self.assertIn("CORR_CLUSTER_RISK", reasons)

    def test_opposite_sides_do_not_cluster(self):
        def corr(a, b, t):
            return 0.95, True, 60
        r = pr.PortfolioReplay(100000.0, 5, correlation_provider=corr)
        decisions = r.run([candidate("AUDUSD", 100, side="BUY", exit_time=100000),
                           candidate("NZDCHF", 101, side="SELL", exit_time=100000)])
        self.assertTrue(all(d["accepted"] for d in decisions))

    def test_warmup_unknown_uses_the_tighter_cap(self):
        def corr(a, b, t):
            return 0.0, False, 10
        r = pr.PortfolioReplay(100000.0, 5, correlation_provider=corr)
        decisions = r.run([candidate("AUDUSD", 100, exit_time=100000),
                           candidate("GBPJPY", 101, exit_time=100000)])
        self.assertEqual(decisions[1]["corr_state"], "CORR_WARMUP_UNKNOWN")
        self.assertEqual(decisions[1]["reason"], "UNKNOWN_CLUSTER_RISK")
        self.assertEqual(decisions[1]["corr_warmup_days"], 10)


class CrossCheckSelection(unittest.TestCase):
    """P-900 .. Addendum F HIGH-2 period selection and gate."""

    def build_series(self, blocks):
        series = []
        day = 0
        for level in blocks:
            for _ in range(63):          # 3 months x 21 days
                series.append({"date": "d%04d" % day, "proxy": level})
                day += 1
        return series

    def test_selection_picks_extreme_blocks_only(self):
        series = self.build_series([1.0, 5.0, 3.0, 0.5])
        chosen = pr.select_crosscheck_periods(series)
        self.assertEqual(chosen["block_count"], 4)
        self.assertEqual(chosen["high_volatility_block"]["proxy_median"], 5.0)
        self.assertEqual(chosen["low_volatility_block"]["proxy_median"], 0.5)

    def test_selection_is_deterministic_on_ties(self):
        series = self.build_series([2.0, 2.0, 1.0, 1.0])
        first = pr.select_crosscheck_periods(series)
        second = pr.select_crosscheck_periods(series)
        self.assertEqual(first["high_volatility_block"]["start_index"],
                         second["high_volatility_block"]["start_index"])
        self.assertEqual(first["high_volatility_block"]["start_index"], 0)
        self.assertEqual(first["low_volatility_block"]["start_index"], 126)

    def test_selection_never_looks_at_performance(self):
        # identical proxy input, wildly different "results" would not change
        # the choice because results are not an argument at all.
        series = self.build_series([1.0, 4.0])
        self.assertEqual(
            pr.select_crosscheck_periods(series)["high_volatility_block"]["proxy_median"],
            4.0)

    def test_volatility_proxy_uses_initial_seven_only(self):
        rows = [{"date": "d1", "values": {"EURUSD": 0.01, "AUDUSD": 0.03,
                                          "EURJPY": 99.0}}]
        series = pr.volatility_proxy_series(rows)
        self.assertAlmostEqual(series[0]["proxy"], 0.02, places=10)

    def test_crosscheck_gate_all_four_conditions(self):
        self.assertTrue(pr.crosscheck_gate(98.0, 0.10, 90.0, 1.0)["pass"])
        self.assertFalse(pr.crosscheck_gate(97.9, 0.10, 90.0, 1.0)["pass"])
        self.assertFalse(pr.crosscheck_gate(98.0, 0.101, 90.0, 1.0)["pass"])
        self.assertFalse(pr.crosscheck_gate(98.0, 0.10, 89.9, 1.0)["pass"])
        self.assertFalse(pr.crosscheck_gate(98.0, 0.10, 90.0, 1.01)["pass"])

    def test_crosscheck_failure_blocks_pass_evidence(self):
        gate = pr.crosscheck_gate(97.0, 0.10, 90.0, 1.0)
        self.assertFalse(gate["usable_as_g3_pass_evidence"])

    def test_n3_representativeness_is_a_disclosure_not_a_gate(self):
        low = pr.representativeness_note(2)
        high = pr.representativeness_note(9)
        self.assertTrue(low["limited_representativeness"])
        self.assertFalse(high["limited_representativeness"])
        self.assertIn("not a PASS condition", low["note"])


if __name__ == "__main__":
    unittest.main(verbosity=1)
