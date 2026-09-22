# G3 Research Log Reason Codes

Authority: Master Specification v0.4.

Generated from `ENUM_G3_REASON` in `src/G3Types.mqh` by
`tools/gen_reason_codes.py`. Do not edit by hand.

`skip_reason` carries the code on `EVAL` rows; `exit_reason` carries the
`EXIT_*` codes on `PARTIAL` and `EXIT` rows.

| code | spec section | meaning |
|------|--------------|---------|
| `NONE` | - | no rejection; the record is an accepted entry or a non-skip record |
| `NO_H4_DIRECTION` | 5 | neither the BUY nor the SELL H4 direction gate is satisfied |
| `H4_SCORE_BELOW_MIN` | 5 | H4 quality score < 1 |
| `M5_BREAKOUT_FAIL` | 7 | the M5 breakout hard gate failed |
| `M5_SCORE_BELOW_MIN` | 7 | M5 trigger quality score < 1 |
| `TOTAL_SCORE_BELOW_THRESHOLD` | 8 | market quality total below the effective ScoreThreshold |
| `VOL_BLOCK` | 8 | VolRatio > 2.50: new entries forbidden |
| `SPREAD_BLOCK` | 8 | SpreadRatio > 0.20: new entries forbidden |
| `DATA_UNAVAILABLE` | 4.1 | price history or tick data could not be read |
| `HTF_BAR_UNRESOLVED` | 4.1 | no H4/M15 bar is fully closed at signal_close_time, or history depth is insufficient |
| `POST_GAP_COOLDOWN` | 4.2 | the H4 reference bar is the first bar completed after a gap wider than twice the period; no new signal is issued |
| `INDICATOR_NOT_READY` | 5-8 | an indicator buffer has not produced enough values yet |
| `SIGNAL_ALREADY_CONSUMED` | 4.1 | the signal_id was consumed before; duplicate orders are refused |
| `STATE_UNCERTAIN` | 10 | both state stores are unrecoverable; all new entries are refused |
| `HARD_STOP_LATCHED` | 10 | the 10% drawdown hard stop is latched; only a manual audited reset clears it |
| `DAILY_ENTRY_LOCK` | 11 | equity is at or below 98% of the daily start equity |
| `SL_DISTANCE_ABOVE_MAX` | 9 | stop distance above 2.5 ATR before the broker correction |
| `SL_BROKER_ADJ_ABOVE_MAX` | 9 | stop distance above 2.5 ATR after the StopLevel correction |
| `LOT_BELOW_MIN_VOLUME` | 9 | floored volume is below VolumeMin |
| `RISK_MONEY_EXCEEDED_AT_MIN_VOLUME` | 9 | even VolumeMin would risk more than RiskMoney |
| `ORDER_CALC_PROFIT_INVALID` | 9 | OrderCalcProfit did not return a usable 1 lot loss |
| `MAX_POSITIONS` | 12 | three positions are already open |
| `MAX_TOTAL_RISK` | 12 | total initial risk would exceed 1.50% |
| `CURRENCY_EXPOSURE` | 12 | same currency component, same direction risk would exceed 1.00% |
| `CORR_CLUSTER_RISK` | 12 | correlation cluster risk would exceed 1.00% |
| `UNKNOWN_CLUSTER_RISK` | 12 | correlation warm-up: unknown cluster risk would exceed 0.75% |
| `PORTFOLIO_LOCK_BUSY` | 12 | another EA instance held the portfolio admission lock; the opportunity is dropped |
| `DUPLICATE_SIGNAL_ID` | 4.1 | the atomic consume could not be made durable; fail-closed drop |
| `DEVIATION_CAP_EXCEEDED` | 13 | computed deviation exceeds the 2.0 pip hard cap; no order is sent |
| `MARKET_CLOSED` | 13 | the market is not open for the symbol |
| `TRADE_MODE_DISABLED` | 13 | SYMBOL_TRADE_MODE is not full trading |
| `FREEZE_LEVEL` | 13 | the intended price is inside the broker freeze level |
| `ORDER_SEND_FAILED` | 13 | OrderSend was rejected; exactly one attempt is made, never a retry loop |
| `EXECUTION_RISK_VIOLATION` | 13 | post-fill risk exceeded 105% of RiskMoney; the position was reduced or closed |
| `EXIT_TP` | 14 | take profit reached (exit mode A) |
| `EXIT_SL` | 14 | initial stop loss hit |
| `EXIT_BE` | 14 | cost adjusted break-even stop hit |
| `EXIT_TRAIL` | 14 | trailing stop hit |
| `EXIT_PARTIAL` | 14 | partial close executed |
| `EXIT_TIMEOUT` | 15 | timeout close: MFE stayed below 0.75R |
| `EXIT_MANUAL_OR_EXTERNAL` | - | the position was closed outside the EA logic |
| `UNMAPPED` | - | defensive fallback; must never appear in a research log |
