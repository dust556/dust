# Integration Test Plan (MetaTrader 5 terminal)

These tests exercise the terminal-bound half of the EA and **cannot be run in
the implementation environment** (no MetaEditor, no MT5). Status of every case
below is therefore **NOT_RUN**. Each one must be executed and recorded before a
G3 run is accepted.

Preconditions for every case unless stated otherwise:

* Account: `ACCOUNT_MARGIN_MODE_RETAIL_HEDGING`.
* EA: `G3_ResearchEA.ex5`, magic `940400`, `config/baseline.set`.
* Common folder cleaned of `G3RSRCH/` before the run.
* Journal and `G3RSRCH/log_*.csv` retained as evidence.

| id | case | procedure | expected result | status |
|----|------|-----------|-----------------|--------|
| I-001 | test_retail_hedging_guard | Attach the EA on a hedging account. | `OnInit` returns `INIT_SUCCEEDED`; journal prints the start line. | NOT_RUN |
| I-002 | test_netting_rejected | Attach the EA on a netting account. | `OnInit` returns `INIT_FAILED`; journal states the required margin mode; no order is ever sent. | NOT_RUN |
| I-003 | test_symbol_universe_instances | Attach one instance to each of EURUSD, GBPUSD, USDJPY, AUDUSD, USDCAD, USDCHF, NZDUSD with the same magic. | Seven independent log files; one shared audit file; no cross-instance state corruption. | NOT_RUN |
| I-004 | test_decision_tick_is_first_tick_of_new_m5_bar | Run in "every tick based on real ticks" and count EVAL rows. | Exactly one EVAL row per M5 bar per symbol; `m5_bar_time` strictly increasing; the first bar after attach produces no evaluation (detector priming). | NOT_RUN |
| I-005 | test_consume_before_evaluation_order | Inspect `G3RSRCH/state_*.txt` after each bar. | `sigt` advances before any order is sent; the value survives in both the file and the terminal global variables. | NOT_RUN |
| I-006 | test_crash_between_consume_and_order | Kill the terminal process immediately after a consume (or force `FileMove` to fail). | On restart the same `signal_id` is refused (`SIGNAL_ALREADY_CONSUMED`); no duplicate order; the opportunity is lost, which is the accepted trade-off. | NOT_RUN |
| I-007 | test_order_calc_profit_jpy_and_non_jpy | Compare `order_calc_profit_1lot` and `final_lot` for EURUSD (5 digit) and USDJPY (3 digit) with a known equity. | Risk money realised within one volume step on both; no JPY-specific pip hard coding. | NOT_RUN |
| I-008 | test_manual_reset_audit_record | Latch HARD_STOP, then restart with `InpManualHardStopReset=true` at DD >= 9% and again at DD < 9%. | Refused above 9% with `MANUAL_RESET_REFUSED` in the audit log; applied below 9% with `MANUAL_RESET_APPLIED`; never automatic. | NOT_RUN |
| I-009 | test_dual_store_written | After any evaluation, inspect the state file and the terminal global variables. | Both stores hold the same record and the same checksum. | NOT_RUN |
| I-010 | test_file_corruption_recovery | Corrupt one byte of `state_*.txt` and restart. | `state_store_status=STORE_GV_ONLY`; trading continues from the global-variable state. | NOT_RUN |
| I-010b | test_gv_corruption_recovery | Delete or alter one `G3_*` global variable and restart. | `STORE_FILE_ONLY`; trading continues from the file state. | NOT_RUN |
| I-010c | test_both_stores_lost | Corrupt the file and delete the global variables, leaving a non-empty history. | `STORE_BOTH_LOST`, `dd_state=STATE_UNCERTAIN`, every EVAL row carries `skip_reason=STATE_UNCERTAIN`, no new order. | NOT_RUN |
| I-011 | test_daily_lock_does_not_close_positions | Drive equity to `DailyStartEquity * 0.98` with an open position. | `daily_lock=1`, new entries refused with `DAILY_ENTRY_LOCK`, the open position is **not** force closed. | NOT_RUN |
| I-012 | test_correlation_window_uses_closed_d1_only | Log `corr_warmup_days` from the first day of a fresh symbol. | `CORR_WARMUP_UNKNOWN` until 60 complete D1 returns exist, then `CORR_READY`; correlation is never treated as zero while unknown. | NOT_RUN |
| I-013 | test_market_facts_reread_at_decision_tick | Compare `stops_level`, `freeze_level`, `spread_ratio` against the terminal at the same timestamp. | Values match the decision_tick snapshot, not a cached one. | NOT_RUN |
| I-014 | test_single_order_send_no_retry | Force a requote / invalid price condition. | Exactly one `OrderSend` per decision_tick in the journal; no retry loop; `retcode` logged. | NOT_RUN |
| I-015 | test_order_send_failure_logged | Disable trading for the symbol, then trigger a signal. | EVAL/ENTRY row with `skip_reason=ORDER_SEND_FAILED` or `TRADE_MODE_DISABLED` and the server retcode. | NOT_RUN |
| I-016 | test_post_fill_reduce_or_close | Force a fill far from the requested price (wide slippage). | `post_fill_risk_ratio` logged; if above 1.05 the volume is reduced to the largest compliant size, or the whole position is closed when it cannot be; `execution_risk_violation=1`. | NOT_RUN |
| I-017 | test_exposure_after_partial | Exit mode B, take a position past 1.5R. | A `PARTIAL` row is written, the registry global variable is rewritten with the reduced risk, and subsequent `total_risk` values reflect the reduction. | NOT_RUN |
| I-018 | test_every_decision_tick_logs_a_row | Compare the EVAL row count with the M5 bar count of the test window. | Equal (minus the priming bar); skipped candidates all carry a reason code. | NOT_RUN |
| I-019 | test_input_surface_matches_registration | Open the EA inputs dialog. | Only the registered inputs are present: ScoreThreshold, ExitMode, Timeout, the two execution stress inputs, and the three research infrastructure inputs. No strategy constant is exposed. | NOT_RUN |
| I-020 | test_manifest_reproducible | Run `tools/compute_hashes.py` twice and compile twice. | Identical `source_hash`; the `.ex5` hash recorded in `manifests/EA_hash.txt`. | NOT_RUN |
| I-021 | test_restart_restores_position_state | Restart the terminal with an open managed position. | `trades_*.csv` restores ticket, initial SL, R distance, MFE/MAE and partial flags; the trail never jumps backwards after the restart. | NOT_RUN |
| I-022 | test_stop_level_and_freeze_level | Use a symbol with a non-zero `STOPS_LEVEL` and `FREEZE_LEVEL`. | Entry stops are pushed to `StopLevel + 1 point`; stop modifications inside the freeze level are skipped rather than rejected by the server. | NOT_RUN |
| I-023 | test_dst_and_server_timezone | Run across a DST change of the broker server. | `h4_bar_time` and `m15_bar_time` always satisfy `bar_time + period <= signal_close_time`; no forming bar is ever referenced. | NOT_RUN |
| I-024 | test_weekend_gap | Run across a Friday-Monday boundary. | The first Monday evaluation references the last closed Friday H4/M15 bar; no evaluation happens while the market is closed. | NOT_RUN |
| I-025 | test_timeout_closes_remaining_lot_only | Exit mode B with `InpTimeout=12`, a position that partials then stalls below 0.75R. | Only the remaining lot is closed at the timeout; `exit_reason=EXIT_TIMEOUT`. | NOT_RUN |
| I-026 | test_trail_never_reverses_live | Exit mode C on a retracing market. | `POSITION_SL` is monotonic for the life of the position. | NOT_RUN |
| I-027 | test_partial_impossible_min_volume_live | Exit mode B on a position of exactly `VolumeMin`. | No partial is attempted; `partial_status=SKIPPED`; the full volume is managed with break-even and trail. | NOT_RUN |
| I-028 | test_hard_stop_blocks_new_entries | Drive drawdown to 10%. | `dd_state=HARD_STOP`, `hard_stop_latched=1`, every later EVAL row carries `HARD_STOP_LATCHED`, and the latch survives restart. | NOT_RUN |
| I-029 | test_no_holdout_artifacts | Search the terminal common folder and the repository after a run. | No Final Holdout directory, file or reference exists. | NOT_RUN |
