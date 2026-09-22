# G3 Research Log Schema

Authority: Master Specification v0.4 section 16.

This file is generated from `G3LogHeader()` in `src/ResearchLogger.mqh`
by `tools/gen_log_schema.py`. Do not edit it by hand.

* Format: CSV, comma separated, ANSI, CRLF line endings.
* Location: `<terminal common folder>/Files/G3RSRCH/log_<account>_<magic>_<symbol>_<run_id>.csv`.
* One file per symbol instance per run.
* Every decision_tick writes exactly one `EVAL` row, including
  candidates that are skipped, so rejection statistics are complete.
* A candidate that clears every strategy gate also writes a `SHADOW`
  row BEFORE any portfolio guard can drop it. The offline
  chronological portfolio replay of v0.4.1a Addendum F re-decides
  those rows against the shared state.
* Executed signals add an `ENTRY` row, partial closes a `PARTIAL` row,
  and the close of a position an `EXIT` row.
* A `FAKEOUT` row closes the 6 bar diagnostic window of Addendum E,
  which keeps running after the position itself has closed.
* Rows are joined on `signal_id`.
* Times are integer epoch seconds; `time_server` is broker time.
* Field names follow Master Specification v0.4 section 12.

Column count: **106**.

| # | column | unit | meaning |
|---|--------|------|---------|
| 1 | `record_type` | string | EVAL (decision_tick evaluation, including skipped candidates), ENTRY (order sent), PARTIAL (partial close), EXIT (position closed) |
| 2 | `time_server` | epoch s | broker server time of the record |
| 3 | `time_utc` | epoch s | UTC time of the record |
| 4 | `symbol` | string | traded symbol |
| 5 | `side` | enum | BUY / SELL / NONE |
| 6 | `signal_id` | string | symbol + '#' + M5 bar open time; join key between EVAL/ENTRY/PARTIAL/EXIT rows |
| 7 | `h4_score` | 0..2 | Master Spec 5 H4 quality score |
| 8 | `m15_score` | 0..2 | Master Spec 6 M15 setup score |
| 9 | `m5_score` | 0..2 | Master Spec 7 M5 trigger quality score |
| 10 | `vol_score` | 0..1 | Master Spec 8 volatility point |
| 11 | `spread_score` | 0..1 | Master Spec 8 spread point |
| 12 | `total_score` | 0..8 | market quality total |
| 13 | `score_threshold_effective` | 4..6 | threshold actually applied (RESTRICTED forces 6) |
| 14 | `score_threshold_input` | 4..6 | registered G3 input value |
| 15 | `h4_bar_time` | epoch s | open time of the resolved H4 reference bar (never a forming bar) |
| 16 | `m15_bar_time` | epoch s | open time of the resolved M15 reference bar (never a forming bar) |
| 17 | `m5_bar_time` | epoch s | open time of the M5 bar whose first tick is the decision_tick |
| 18 | `signal_close_time` | epoch s | close time of the preceding M5 bar (Master Spec 4.1) |
| 19 | `atr_m5` | price | ATR14 of M5 shift 1; the canonical ATR of sections 8, 9 and 13 |
| 20 | `atr_m15` | price | ATR14 of the M15 reference bar (pullback band) |
| 21 | `atr_h4` | price | ATR14 of the H4 reference bar (slope normalisation) |
| 22 | `vol_ratio` | ratio | ATR14[1] / median(ATR14 shifts 2..101) |
| 23 | `spread_ratio` | ratio | (Ask-Bid) / ATR14[1], including execution stress spread |
| 24 | `h4_direction` | 0/1 | H4 direction gate passed |
| 25 | `h4_slope` | 0/1 | H4 EMA50 slope point |
| 26 | `h4_adx` | 0/1 | H4 ADX/DI point |
| 27 | `m15_pullback` | 0/1 | M15 pullback point; each shift is tested against the EMA20 and the ATR14 of that same shift (spec 6) |
| 28 | `m15_structure` | 0/1 | M15 structure point |
| 29 | `breakout_gate` | 0/1 | M5 breakout hard gate passed |
| 30 | `m5_candle` | 0/1 | M5 candle quality point |
| 31 | `m5_momentum` | 0/1 | M5 momentum point |
| 32 | `vol_point` | 0/1 | VolRatio inside [0.80,1.80] |
| 33 | `spread_point` | 0/1 | SpreadRatio <= 0.12 |
| 34 | `vol_block` | 0/1 | VolRatio > 2.50, new entries forbidden |
| 35 | `spread_block` | 0/1 | SpreadRatio > 0.20, new entries forbidden |
| 36 | `post_gap` | 0/1 | the H4 reference bar is the first bar completed after a gap of more than twice the period; no new signal is issued (spec 4.2) and the subgroup is reported (spec 13.6) |
| 37 | `h4_slope_value` | ratio | (EMA50[c]-EMA50[c-3]) / ATR14[c] |
| 38 | `adx_value` | value | ADX14 of the H4 reference bar |
| 39 | `plus_di` | value | +DI of the H4 reference bar |
| 40 | `minus_di` | value | -DI of the H4 reference bar |
| 41 | `sl_raw` | price | structural stop before any adjustment |
| 42 | `sl_strategy` | price | stop after the 1.0 ATR minimum expansion |
| 43 | `sl_final` | price | stop after the broker StopLevel correction |
| 44 | `sl_raw_distance` | price | |entry - sl_raw| (spec 9.1) |
| 45 | `sl_final_distance` | price | |entry - sl_final| (spec 9.1) |
| 46 | `sl_strategy_adjusted` | 0/1 | the 1.0 ATR minimum was applied |
| 47 | `sl_broker_adjusted` | 0/1 | the StopLevel+1 point correction was applied |
| 48 | `stop_level` | points | SYMBOL_TRADE_STOPS_LEVEL at the decision_tick |
| 49 | `freeze_level` | points | SYMBOL_TRADE_FREEZE_LEVEL at the decision_tick |
| 50 | `risk_pct` | % | EffectiveRiskPct of the current drawdown state |
| 51 | `risk_money` | account ccy | Equity * EffectiveRiskPct |
| 52 | `raw_lot` | lots | RiskMoney / |1 lot loss|, before step rounding |
| 53 | `final_lot` | lots | raw_lot floored onto VolumeStep |
| 54 | `lot_capped_by_max` | 0/1 | the broker VolumeMax limited the size |
| 55 | `risk_1lot_calc` | account ccy | OrderCalcProfit entry->SL for 1.00 lot (signed loss) |
| 56 | `commission_per_lot_est` | account ccy | round-turn commission estimate per 1.00 lot added to pre-trade risk (spec 9.2) |
| 57 | `tick_value_profit` | account ccy | SYMBOL_TRADE_TICK_VALUE_PROFIT, recorded for cross-checking (spec 9.2) |
| 58 | `tick_value_loss` | account ccy | SYMBOL_TRADE_TICK_VALUE_LOSS, recorded for cross-checking (spec 9.2) |
| 59 | `deviation_computed` | points | floor(min(1.0*spread, 0.05*ATR14[1]) / Point) |
| 60 | `deviation_hard_cap` | points | 2.0 pips expressed in points |
| 61 | `deviation_points` | points | deviation actually sent, max(1,min(computed,cap)) |
| 62 | `deviation_cap_hit` | 0/1 | computed exceeded the hard cap; no order was sent |
| 63 | `requested_price` | price | price submitted with OrderSend |
| 64 | `fill_price` | price | executed price |
| 65 | `slippage` | points | positive = filled worse than requested |
| 66 | `execution_risk_violation` | 0/1 | post-fill risk exceeded 105% of RiskMoney |
| 67 | `post_fill_risk_ratio` | ratio | realised risk / target RiskMoney after the fill |
| 68 | `exit_mode` | 0/1/2 | A / B / C |
| 69 | `timeout_bars` | M5 bars | 0 = OFF, otherwise 6/12/18/24 |
| 70 | `partial_status` | string | NONE / DONE / SKIPPED |
| 71 | `partial_close_ratio` | ratio | realised partial close fraction (valid range 0.40..0.60) |
| 72 | `mfe_r` | R | maximum favourable excursion in R |
| 73 | `mae_r` | R | maximum adverse excursion in R (negative) |
| 74 | `mfe_3bars` | R | MFE within the first 3 M5 bars |
| 75 | `mae_3bars` | R | MAE within the first 3 M5 bars |
| 76 | `mfe_6bars` | R | MFE within the first 6 M5 bars |
| 77 | `mae_6bars` | R | MAE within the first 6 M5 bars |
| 78 | `fakeout_3` | TRUE/FALSE/NA | v0.4.1a Addendum E: the price reached the INITIAL SL within 3 M5 bars of entry (BUY on the Bid, SELL on the Ask), independent of the exit mode. NA when the window could not be fully observed |
| 79 | `fakeout_6` | TRUE/FALSE/NA | v0.4.1a Addendum E: same over 6 M5 bars. NA is never collapsed to FALSE |
| 80 | `holding_bars` | M5 bars | M5 bars between entry and the record |
| 81 | `exit_reason` | string | EXIT_TP / EXIT_SL / EXIT_BE / EXIT_TRAIL / EXIT_PARTIAL / EXIT_TIMEOUT / EXIT_MANUAL_OR_EXTERNAL |
| 82 | `result_r` | R | total realised P/L divided by the initial RiskMoney |
| 83 | `realized_pl` | account ccy | realised profit incl. swap and commission |
| 84 | `dd_pct` | % | (PeakEquity - Equity) / PeakEquity * 100 |
| 85 | `dd_state` | enum | NORMAL / MODERATE / RESTRICTED / HARD_STOP / STATE_UNCERTAIN |
| 86 | `daily_lock` | 0/1 | DailyEntryLock active (Equity <= DailyStartEquity * 0.98) |
| 87 | `hard_stop_latched` | 0/1 | the 10% hard stop latch is set |
| 88 | `peak_equity` | account ccy | stored peak equity |
| 89 | `equity` | account ccy | account equity at the record |
| 90 | `balance` | account ccy | account balance at the record |
| 91 | `total_risk` | % | summed initial risk of open positions plus the candidate |
| 92 | `currency_exposure` | % | worst same currency component, same direction exposure |
| 93 | `corr_cluster_risk` | % | risk of the correlation cluster containing the candidate (direction adjusted) |
| 94 | `corr_cluster_risk_raw` | % | same cluster computed on raw Pearson sign, logged for ISSUE-002 |
| 95 | `corr_state` | enum | CORR_READY / CORR_WARMUP_UNKNOWN |
| 96 | `corr_unavailable` | 0/1 | 1 while the correlation window is not yet available (spec 11.4) |
| 97 | `corr_warmup_days` | bars | complete D1 bars available for the correlation window |
| 98 | `unknown_cluster_risk` | % | candidate plus all open positions while correlation is unknown |
| 99 | `open_positions` | count | open positions carrying the EA magic number |
| 100 | `skip_reason` | enum | reason code, NONE when the record is not a skip (see reason_codes.md) |
| 101 | `retcode` | int | MT5 trade server return code |
| 102 | `state_store_status` | enum | OK / RECOVERED / UNCERTAIN, exactly as named by spec 12 |
| 103 | `state_store_detail` | enum | internal detail: STORE_OK / STORE_FILE_ONLY / STORE_GV_ONLY / STORE_MISMATCH_CONSERVATIVE / STORE_BOTH_LOST / STORE_FRESH |
| 104 | `state_epoch` | int | state epoch id; incremented only by an audited manual recovery (v0.4.1a Addendum B). Performance must not be aggregated across epochs |
| 105 | `recovery_result` | enum | outcome of an operator requested recovery on this run (NOT_REQUESTED / RECONCILED_AUDITED / EPOCH_CREATED / REFUSED_*) |
| 106 | `run_id` | string | research run identifier from InpRunId |

## Tri-state fields

`fakeout_3` and `fakeout_6` are TRUE, FALSE or NA. NA means the six bar
observation window could not be completed - for example the EA was
restarted inside it - and is never written as FALSE. A row whose
window is still open also reads NA; the closing verdict arrives on the
`FAKEOUT` row for that `signal_id`.
