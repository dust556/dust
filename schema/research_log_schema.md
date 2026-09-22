# G3 Research Log Schema

Authority: Master Specification v0.4 section 16.

This file is generated from `G3LogHeader()` in `src/ResearchLogger.mqh`
by `tools/gen_log_schema.py`. Do not edit it by hand.

* Format: CSV, comma separated, ANSI, CRLF line endings.
* Location: `<terminal common folder>/Files/G3RSRCH/log_<account>_<magic>_<symbol>_<run_id>.csv`.
* One file per symbol instance per run.
* Every decision_tick writes exactly one `EVAL` row, including
  candidates that are skipped, so rejection statistics are complete.
* Executed signals add an `ENTRY` row, partial closes a `PARTIAL` row,
  and the close of a position an `EXIT` row.
* Rows are joined on `signal_id`.
* Times are integer epoch seconds; `time_server` is broker time.

Column count: **96**.

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
| 24 | `f_h4_direction` | 0/1 | H4 direction gate passed |
| 25 | `f_h4_slope` | 0/1 | H4 EMA50 slope point |
| 26 | `f_h4_adx` | 0/1 | H4 ADX/DI point |
| 27 | `f_m15_pullback` | 0/1 | M15 pullback point |
| 28 | `f_m15_structure` | 0/1 | M15 structure point |
| 29 | `f_m5_breakout` | 0/1 | M5 breakout hard gate passed |
| 30 | `f_m5_candle` | 0/1 | M5 candle quality point |
| 31 | `f_m5_momentum` | 0/1 | M5 momentum point |
| 32 | `f_vol_point` | 0/1 | VolRatio inside [0.80,1.80] |
| 33 | `f_spread_point` | 0/1 | SpreadRatio <= 0.12 |
| 34 | `f_vol_block` | 0/1 | VolRatio > 2.50, new entries forbidden |
| 35 | `f_spread_block` | 0/1 | SpreadRatio > 0.20, new entries forbidden |
| 36 | `h4_slope_value` | ratio | (EMA50[c]-EMA50[c-3]) / ATR14[c] |
| 37 | `adx_value` | value | ADX14 of the H4 reference bar |
| 38 | `plus_di` | value | +DI of the H4 reference bar |
| 39 | `minus_di` | value | -DI of the H4 reference bar |
| 40 | `sl_raw` | price | structural stop before any adjustment |
| 41 | `sl_strategy` | price | stop after the 1.0 ATR minimum expansion |
| 42 | `sl_final` | price | stop after the broker StopLevel correction |
| 43 | `sl_strategy_adjusted` | 0/1 | the 1.0 ATR minimum was applied |
| 44 | `sl_broker_adjusted` | 0/1 | the StopLevel+1 point correction was applied |
| 45 | `stops_level` | points | SYMBOL_TRADE_STOPS_LEVEL at the decision_tick |
| 46 | `freeze_level` | points | SYMBOL_TRADE_FREEZE_LEVEL at the decision_tick |
| 47 | `risk_pct` | % | EffectiveRiskPct of the current drawdown state |
| 48 | `risk_money` | account ccy | Equity * EffectiveRiskPct |
| 49 | `raw_lot` | lots | RiskMoney / |1 lot loss|, before step rounding |
| 50 | `final_lot` | lots | raw_lot floored onto VolumeStep |
| 51 | `lot_capped_by_max` | 0/1 | the broker VolumeMax limited the size |
| 52 | `order_calc_profit_1lot` | account ccy | OrderCalcProfit entry->SL for 1.00 lot (signed loss) |
| 53 | `deviation_computed` | points | floor(min(1.0*spread, 0.05*ATR14[1]) / Point) |
| 54 | `deviation_hard_cap` | points | 2.0 pips expressed in points |
| 55 | `deviation_points` | points | deviation actually sent, max(1,min(computed,cap)) |
| 56 | `deviation_cap_hit` | 0/1 | computed exceeded the hard cap; no order was sent |
| 57 | `requested_price` | price | price submitted with OrderSend |
| 58 | `fill_price` | price | executed price |
| 59 | `slippage_points` | points | positive = filled worse than requested |
| 60 | `execution_risk_violation` | 0/1 | post-fill risk exceeded 105% of RiskMoney |
| 61 | `post_fill_risk_ratio` | ratio | realised risk / target RiskMoney after the fill |
| 62 | `exit_mode` | 0/1/2 | A / B / C |
| 63 | `timeout_bars` | M5 bars | 0 = OFF, otherwise 6/12/18/24 |
| 64 | `partial_status` | string | NONE / DONE / SKIPPED |
| 65 | `partial_close_ratio` | ratio | realised partial close fraction (valid range 0.40..0.60) |
| 66 | `mfe_r` | R | maximum favourable excursion in R |
| 67 | `mae_r` | R | maximum adverse excursion in R (negative) |
| 68 | `mfe_r_3bars` | R | MFE within the first 3 M5 bars |
| 69 | `mae_r_3bars` | R | MAE within the first 3 M5 bars |
| 70 | `mfe_r_6bars` | R | MFE within the first 6 M5 bars |
| 71 | `mae_r_6bars` | R | MAE within the first 6 M5 bars |
| 72 | `fakeout_3` | NA | NOT DEFINED by Master Specification v0.4 - always NA_SPEC_UNDEFINED, see CR-002 |
| 73 | `fakeout_6` | NA | NOT DEFINED by Master Specification v0.4 - always NA_SPEC_UNDEFINED, see CR-002 |
| 74 | `holding_bars` | M5 bars | M5 bars between entry and the record |
| 75 | `exit_reason` | string | EXIT_TP / EXIT_SL / EXIT_BE / EXIT_TRAIL / EXIT_PARTIAL / EXIT_TIMEOUT / EXIT_MANUAL_OR_EXTERNAL |
| 76 | `result_R` | R | total realised P/L divided by the initial RiskMoney |
| 77 | `realized_pl` | account ccy | realised profit incl. swap and commission |
| 78 | `dd_pct` | % | (PeakEquity - Equity) / PeakEquity * 100 |
| 79 | `dd_state` | enum | NORMAL / MODERATE / RESTRICTED / HARD_STOP / STATE_UNCERTAIN |
| 80 | `daily_lock` | 0/1 | DailyEntryLock active (Equity <= DailyStartEquity * 0.98) |
| 81 | `hard_stop_latched` | 0/1 | the 10% hard stop latch is set |
| 82 | `peak_equity` | account ccy | stored peak equity |
| 83 | `equity` | account ccy | account equity at the record |
| 84 | `balance` | account ccy | account balance at the record |
| 85 | `total_risk` | % | summed initial risk of open positions plus the candidate |
| 86 | `currency_exposure` | % | worst same currency component, same direction exposure |
| 87 | `corr_cluster_risk` | % | risk of the correlation cluster containing the candidate (direction adjusted) |
| 88 | `corr_cluster_risk_raw` | % | same cluster computed on raw Pearson sign, logged for ISSUE-002 |
| 89 | `corr_state` | enum | CORR_READY / CORR_WARMUP_UNKNOWN |
| 90 | `corr_warmup_days` | bars | complete D1 bars available for the correlation window |
| 91 | `unknown_cluster_risk` | % | candidate plus all open positions while correlation is unknown |
| 92 | `open_positions` | count | open positions carrying the EA magic number |
| 93 | `skip_reason` | enum | reason code, NONE when the record is not a skip (see reason_codes.md) |
| 94 | `retcode` | int | MT5 trade server return code |
| 95 | `state_store_status` | enum | STORE_OK / STORE_FILE_ONLY / STORE_GV_ONLY / STORE_MISMATCH_CONSERVATIVE / STORE_BOTH_LOST / STORE_FRESH |
| 96 | `run_id` | string | research run identifier from InpRunId |

## Fields not populated

`fakeout_3` and `fakeout_6` are required by section 16 but are not
defined anywhere in Master Specification v0.4. The columns are emitted
with the literal token `NA_SPEC_UNDEFINED` and are never filled with an
invented definition. See `docs/change_requests.md` CR-002.
