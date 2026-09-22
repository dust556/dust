# Known Scenarios

Reference scenarios for reviewing the research log. Each one states what the
specification requires, so a reviewer can confirm the behaviour from the CSV
without reading the code.

## S-01 Forming higher timeframe bar

A decision_tick at 09:02 server time with H4 bars opening at 04:00 and 08:00
must use the **04:00** bar: the 08:00 bar is still forming.
Check: `h4_bar_time + 14400 <= signal_close_time` on every row.

## S-02 Weekend gap

The first decision_tick of the trading week must reference the last H4/M15 bar
that closed on Friday. `h4_bar_time` therefore jumps by more than one period.
No evaluation row exists while the market is closed.

## S-03 Duplicate signal after restart

Restarting inside an M5 bar must not produce a second evaluation of that bar.
Check: `signal_id` is unique across the whole log, and the bar in progress at
restart produces no EVAL row.

## S-04 Drawdown ladder

As `dd_pct` crosses 6, 8 and 10, `dd_state` must move
NORMAL -> MODERATE -> RESTRICTED -> HARD_STOP and `risk_pct` must step
0.50 -> 0.25 -> 0.10 -> 0. Below 7 the state returns to MODERATE, below 5 to
NORMAL. Once HARD_STOP is latched it never clears without an audit record.

## S-05 RESTRICTED threshold

While `dd_state=RESTRICTED`, `score_threshold_effective` must be 6 regardless
of the registered input.

## S-06 Volatility and spread blocks

`vol_ratio > 2.50` must appear with `skip_reason=VOL_BLOCK` and no order.
`spread_ratio > 0.20` must appear with `skip_reason=SPREAD_BLOCK`.
A `vol_ratio` of 1.9 scores 0 but does not block.

## S-07 Stop adjustment chain

For every entry: `sl_raw` -> `sl_strategy` -> `sl_final`.
`sl_strategy_adjusted=1` only when the raw distance was below 1.0 ATR.
`sl_broker_adjusted=1` only when the strategy stop was inside the stop level.
No entry exists with `|fill_price - sl_final| > 2.5 * atr_m5`.

## S-08 Lot sizing

`final_lot <= raw_lot` always (floor only). No entry exists where
`final_lot * |order_calc_profit_1lot| > risk_money` unless
`execution_risk_violation=1`, which must be followed by a reduction or a close.

## S-09 Deviation cap

`deviation_points <= deviation_hard_cap` on every ENTRY row, and every row with
`deviation_cap_hit=1` has no fill.

## S-10 Correlation warm-up

While `corr_state=CORR_WARMUP_UNKNOWN`, the admitted total risk never exceeds
0.75%, and `corr_warmup_days` is below 60.

## S-11 Exit mode A purity

With `exit_mode=0` there must be no `PARTIAL` row, no `EXIT_BE`, and no
`EXIT_TRAIL`; only `EXIT_TP`, `EXIT_SL` or `EXIT_TIMEOUT` occur.

## S-12 Timeout

Every `EXIT_TIMEOUT` row has `mfe_r < 0.75` and `holding_bars >= timeout_bars`.
No `EXIT_TIMEOUT` exists when `timeout_bars=0`.

## S-13 Partial band

Every `PARTIAL` row has `partial_close_ratio` inside [0.40, 0.60].
A position of exactly `VolumeMin` never produces a `PARTIAL` row.

## S-14 Portfolio ceilings

No ENTRY row exists with `open_positions >= 3`, `total_risk > 1.50`,
`currency_exposure > 1.00`, or `corr_cluster_risk > 1.00`.

## S-15 Final Holdout

The log contains no reference to a holdout period, and no holdout directory
exists in the research environment.
