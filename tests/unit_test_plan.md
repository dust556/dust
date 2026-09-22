# Unit Test Plan (host, executable)

Scope: the pure specification logic of the G3 Research EA, compiled
from the same `src/*.mqh` files that MetaEditor compiles, through the
MQL5 shim in `tests/host/mql5_shim.h`.

Run: `tests/run_unit_tests.sh` (C++17 compiler only, no MetaTrader).
The build uses `-Wall -Wextra -Werror`.

Terminal-bound behaviour is **not** in scope here; see
`tests/integration_test_plan.md`.

Total assertions: **142**.

## test_time_sync

Specification: 4.1 MTF time synchronisation, decision_tick, signal_id

| test id | assertion |
|---------|-----------|
| `T-001` | test_no_forming_H4_reference |
| `T-001b` | boundary_bar_is_closed |
| `T-002` | test_h4_reference_weekend_gap |
| `T-003` | test_m15_reference_is_not_fixed_shift1 |
| `T-003b` | test_depth_behind_reference |
| `T-003c` | test_no_bars_returns_minus_one |
| `T-004` | test_signal_id_format |

## test_state_store

Specification: 10 StateStore, dual store reconciliation, exactly-once consume

| test id | assertion |
|---------|-----------|
| `T-006` | test_state_roundtrip_after_restart |
| `T-007` | test_corrupt_primary_store_fails_safe |
| `T-007b` | test_truncated_record_rejected |
| `T-007c` | test_wrong_schema_version_rejected |
| `T-008` | test_corrupt_gv_store_checksum |
| `T-009` | test_both_stores_lost_state_uncertain |
| `T-009b` | test_fresh_install_is_not_uncertain |
| `T-010` | test_store_mismatch_conservative |
| `T-010b` | test_stores_agree |
| `T-010c` | test_file_only |
| `T-010d` | test_gv_only |
| `T-005` | test_signal_id_duplicate_rejected |
| `T-005b` | test_older_signal_rejected |
| `T-005c` | test_new_signal_accepted |

## test_dd_state_machine

Specification: 10/11 drawdown state machine, hysteresis, latch, DailyEntryLock

| test id | assertion |
|---------|-----------|
| `T-011` | test_dd_boundary_6pct_below |
| `T-011b` | test_dd_boundary_6pct_at |
| `T-012` | test_dd_boundary_8pct_below |
| `T-012b` | test_dd_boundary_8pct_at |
| `T-013` | test_dd_boundary_10pct_latch |
| `T-015` | test_hard_stop_latch_not_auto_released |
| `T-014` | test_restricted_holds_above_7 |
| `T-014b` | test_restricted_to_moderate_below_7 |
| `T-014c` | test_moderate_holds_above_5 |
| `T-014d` | test_moderate_to_normal_below_5 |
| `T-014e` | test_uncertain_is_absorbing |
| `T-014f` | test_risk_pct_per_state |
| `T-014g` | test_drawdown_pct |
| `T-016` | test_manual_reset_requires_dd_below_9 |
| `T-017` | test_daily_entry_lock |

## test_risk_and_lots

Specification: 9 stop placement, risk money, lot sizing, post-fill risk

| test id | assertion |
|---------|-----------|
| `T-024a` | test_raw_stop_buy |
| `T-024b` | test_raw_stop_sell |
| `T-024` | test_sl_min_1atr_expansion |
| `T-024c` | test_sl_in_band_untouched |
| `T-025` | test_sl_max_2_5atr_reject |
| `T-025b` | test_sl_exactly_2_5atr_ok |
| `T-023` | test_stop_level_adjustment |
| `T-023b` | test_stop_level_no_change |
| `T-026` | test_sl_broker_adjust_above_max_reject |
| `T-018` | test_lot_floor_to_volume_step |
| `T-018b` | test_lot_floor_no_round_up |
| `T-019` | test_lot_below_volume_min_rejected |
| `T-018c` | test_lot_capped_by_volume_max |
| `T-018d` | test_order_calc_profit_invalid |
| `T-027` | test_post_fill_risk_105_detected |
| `T-027b` | test_post_fill_risk_within_tolerance |
| `T-027c` | test_risk_capped_volume |

## test_deviation

Specification: 13 PipSize, deviation computation and hard cap

| test id | assertion |
|---------|-----------|
| `T-020` | test_pip_size_5_digits |
| `T-020b` | test_pip_size_3_digits_jpy |
| `T-020c` | test_pip_size_4_digits |
| `T-020d` | test_pip_size_2_digits_jpy |
| `T-021` | test_deviation_hard_cap_5_digits |
| `T-021b` | test_deviation_hard_cap_3_digits |
| `T-021c` | test_deviation_hard_cap_4_digits |
| `T-021d` | test_deviation_uses_min_of_spread_and_atr |
| `T-021e` | test_deviation_atr_term |
| `T-021f` | test_deviation_minimum_one_point |
| `T-022` | test_deviation_cap_exceeded_blocks_send |

## test_exits

Specification: 14/15 exit modes A/B/C, partial, trail, timeout, MFE/MAE

| test id | assertion |
|---------|-----------|
| `T-048` | test_exit_a_tp_2r |
| `T-048b` | test_exit_a_tp_2r_sell |
| `T-048c` | test_exit_b_c_no_fixed_tp |
| `T-049a` | test_r_multiple_buy |
| `T-049b` | test_r_multiple_sell |
| `T-049` | test_result_r_definition |
| `T-028` | test_partial_impossible_min_volume |
| `T-029` | test_partial_exact_50pct |
| `T-029b` | test_partial_ratio_below_40pct_skipped |
| `T-029c` | test_partial_ratio_at_40pct_boundary |
| `T-029d` | test_partial_coarse_step |
| `T-030` | test_trail_never_reverses_buy |
| `T-030b` | test_trail_never_reverses_sell |
| `T-030c` | test_atr_trail_distance |
| `T-030d` | test_cost_adjusted_breakeven |
| `T-030e` | test_exit_a_stop_is_fixed |
| `T-030f` | test_exit_b_breakeven_after_1r |
| `T-030g` | test_exit_b_trail_after_partial |
| `T-030h` | test_exit_c_chandelier |
| `T-031` | test_timeout_off |
| `T-031b` | test_timeout_not_reached |
| `T-031c` | test_timeout_closes_low_mfe |
| `T-031d` | test_timeout_keeps_high_mfe |
| `T-050` | test_mfe_mae_tracking |
| `T-050b` | test_extreme_price_monotonic |

## test_portfolio

Specification: 12 portfolio limits, currency exposure, correlation guard

| test id | assertion |
|---------|-----------|
| `T-034a` | test_currency_components |
| `T-034` | test_currency_exposure_same_direction |
| `T-034b` | test_currency_exposure_opposite_direction |
| `T-034c` | test_quote_currency_direction |
| `T-034d` | test_currency_limit_blocks |
| `T-035` | test_max_positions |
| `T-036` | test_max_total_risk |
| `T-032` | test_correlation_cluster_blocks |
| `T-032b` | test_correlation_below_threshold_no_cluster |
| `T-032c` | test_signed_correlation_direction_adjusted |
| `T-033` | test_corr_warmup_unknown_blocks |
| `T-033b` | test_corr_warmup_within_budget |
| `T-032d` | test_pearson_perfect_positive |
| `T-032e` | test_pearson_perfect_negative |
| `T-032f` | test_pearson_zero_variance_undefined |

## test_signal_logic

Specification: 5/6/7/8 H4, M15, M5 and market quality scoring

| test id | assertion |
|---------|-----------|
| `T-037` | test_h4_direction_gate_buy |
| `T-037b` | test_h4_gate_requires_close_and_ema |
| `T-038` | test_h4_slope_value |
| `T-038b` | test_h4_score_two_points |
| `T-038c` | test_h4_slope_boundary_excluded |
| `T-038d` | test_h4_adx_boundary_included |
| `T-038e` | test_h4_adx_boundary_excluded |
| `T-038f` | test_h4_adx_di_direction |
| `T-038g` | test_h4_slope_zero_atr |
| `T-039` | test_m15_score_two_points |
| `T-039b` | test_m15_pullback_window_limited |
| `T-039c` | test_m15_pullback_needs_close_above_ema |
| `T-039d` | test_m15_structure_requires_ema50 |
| `T-039e` | test_m15_pullback_band_inclusive |
| `T-040` | test_m5_breakout_hard_gate |
| `T-040b` | test_m5_breakout_strict |
| `T-041` | test_m5_score_two_points |
| `T-041b` | test_m5_body_ratio |
| `T-041c` | test_m5_close_position |
| `T-041d` | test_m5_zero_range |
| `T-041e` | test_m5_momentum_slope |
| `T-042` | test_vol_ratio |
| `T-042b` | test_vol_score_band |
| `T-042c` | test_vol_block_above_2_5 |
| `T-046` | test_atr_median_even_sample |
| `T-046b` | test_median_odd_sample |
| `T-046c` | test_median_empty_rejected |
| `T-043` | test_spread_ratio |
| `T-043b` | test_spread_score_boundary |
| `T-043c` | test_spread_block_above_0_20 |
| `T-045` | test_total_score_max_8 |
| `T-044` | test_effective_threshold_restricted |
| `T-044b` | test_effective_threshold_other_states |

## test_log_schema

Specification: 16 research log schema integrity

| test id | assertion |
|---------|-----------|
| `T-047` | test_log_schema_column_count_matches |
| `T-047b` | test_log_has_all_spec_fields |
| `T-047c` | test_fakeout_columns_marked_undefined |
| `T-047d` | test_reason_code_text |
| `T-047e` | test_side_text |
