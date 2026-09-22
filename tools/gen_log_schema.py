#!/usr/bin/env python3
"""
Generate schema/research_log_schema.md directly from G3LogHeader() in
src/ResearchLogger.mqh so the documented schema can never drift from the
emitted CSV. Fails if a column has no description.
"""
import os
import re
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
SRC = os.path.join(ROOT, "src", "ResearchLogger.mqh")
OUT = os.path.join(ROOT, "schema", "research_log_schema.md")

DESC = {
 "record_type": ("string", "EVAL (decision_tick evaluation, including skipped candidates), ENTRY (order sent), PARTIAL (partial close), EXIT (position closed)"),
 "time_server": ("epoch s", "broker server time of the record"),
 "time_utc": ("epoch s", "UTC time of the record"),
 "symbol": ("string", "traded symbol"),
 "side": ("enum", "BUY / SELL / NONE"),
 "signal_id": ("string", "symbol + '#' + M5 bar open time; join key between EVAL/ENTRY/PARTIAL/EXIT rows"),
 "h4_score": ("0..2", "Master Spec 5 H4 quality score"),
 "m15_score": ("0..2", "Master Spec 6 M15 setup score"),
 "m5_score": ("0..2", "Master Spec 7 M5 trigger quality score"),
 "vol_score": ("0..1", "Master Spec 8 volatility point"),
 "spread_score": ("0..1", "Master Spec 8 spread point"),
 "total_score": ("0..8", "market quality total"),
 "score_threshold_effective": ("4..6", "threshold actually applied (RESTRICTED forces 6)"),
 "score_threshold_input": ("4..6", "registered G3 input value"),
 "h4_bar_time": ("epoch s", "open time of the resolved H4 reference bar (never a forming bar)"),
 "m15_bar_time": ("epoch s", "open time of the resolved M15 reference bar (never a forming bar)"),
 "m5_bar_time": ("epoch s", "open time of the M5 bar whose first tick is the decision_tick"),
 "signal_close_time": ("epoch s", "close time of the preceding M5 bar (Master Spec 4.1)"),
 "atr_m5": ("price", "ATR14 of M5 shift 1; the canonical ATR of sections 8, 9 and 13"),
 "atr_m15": ("price", "ATR14 of the M15 reference bar (pullback band)"),
 "atr_h4": ("price", "ATR14 of the H4 reference bar (slope normalisation)"),
 "vol_ratio": ("ratio", "ATR14[1] / median(ATR14 shifts 2..101)"),
 "spread_ratio": ("ratio", "(Ask-Bid) / ATR14[1], including execution stress spread"),
 "h4_direction": ("0/1", "H4 direction gate passed"),
 "h4_slope": ("0/1", "H4 EMA50 slope point"),
 "h4_adx": ("0/1", "H4 ADX/DI point"),
 "m15_pullback": ("0/1", "M15 pullback point; each shift is tested against the EMA20 and the ATR14 of that same shift (spec 6)"),
 "m15_structure": ("0/1", "M15 structure point"),
 "breakout_gate": ("0/1", "M5 breakout hard gate passed"),
 "m5_candle": ("0/1", "M5 candle quality point"),
 "m5_momentum": ("0/1", "M5 momentum point"),
 "vol_point": ("0/1", "VolRatio inside [0.80,1.80]"),
 "spread_point": ("0/1", "SpreadRatio <= 0.12"),
 "vol_block": ("0/1", "VolRatio > 2.50, new entries forbidden"),
 "spread_block": ("0/1", "SpreadRatio > 0.20, new entries forbidden"),
 "post_gap": ("0/1", "the H4 reference bar is the first bar completed after a gap of more than twice the period; no new signal is issued (spec 4.2) and the subgroup is reported (spec 13.6)"),
 "h4_slope_value": ("ratio", "(EMA50[c]-EMA50[c-3]) / ATR14[c]"),
 "adx_value": ("value", "ADX14 of the H4 reference bar"),
 "plus_di": ("value", "+DI of the H4 reference bar"),
 "minus_di": ("value", "-DI of the H4 reference bar"),
 "sl_raw": ("price", "structural stop before any adjustment"),
 "sl_strategy": ("price", "stop after the 1.0 ATR minimum expansion"),
 "sl_final": ("price", "stop after the broker StopLevel correction"),
 "sl_raw_distance": ("price", "|entry - sl_raw| (spec 9.1)"),
 "sl_final_distance": ("price", "|entry - sl_final| (spec 9.1)"),
 "sl_strategy_adjusted": ("0/1", "the 1.0 ATR minimum was applied"),
 "sl_broker_adjusted": ("0/1", "the StopLevel+1 point correction was applied"),
 "stop_level": ("points", "SYMBOL_TRADE_STOPS_LEVEL at the decision_tick"),
 "freeze_level": ("points", "SYMBOL_TRADE_FREEZE_LEVEL at the decision_tick"),
 "risk_pct": ("%", "EffectiveRiskPct of the current drawdown state"),
 "risk_money": ("account ccy", "Equity * EffectiveRiskPct"),
 "raw_lot": ("lots", "RiskMoney / |1 lot loss|, before step rounding"),
 "final_lot": ("lots", "raw_lot floored onto VolumeStep"),
 "lot_capped_by_max": ("0/1", "the broker VolumeMax limited the size"),
 "risk_1lot_calc": ("account ccy", "OrderCalcProfit entry->SL for 1.00 lot (signed loss)"),
 "commission_per_lot_est": ("account ccy", "round-turn commission estimate per 1.00 lot added to pre-trade risk (spec 9.2)"),
 "tick_value_profit": ("account ccy", "SYMBOL_TRADE_TICK_VALUE_PROFIT, recorded for cross-checking (spec 9.2)"),
 "tick_value_loss": ("account ccy", "SYMBOL_TRADE_TICK_VALUE_LOSS, recorded for cross-checking (spec 9.2)"),
 "deviation_computed": ("points", "floor(min(1.0*spread, 0.05*ATR14[1]) / Point)"),
 "deviation_hard_cap": ("points", "2.0 pips expressed in points"),
 "deviation_points": ("points", "deviation actually sent, max(1,min(computed,cap))"),
 "deviation_cap_hit": ("0/1", "computed exceeded the hard cap; no order was sent"),
 "requested_price": ("price", "price submitted with OrderSend"),
 "fill_price": ("price", "executed price"),
 "slippage": ("points", "positive = filled worse than requested"),
 "execution_risk_violation": ("0/1", "post-fill risk exceeded 105% of RiskMoney"),
 "post_fill_risk_ratio": ("ratio", "realised risk / target RiskMoney after the fill"),
 "exit_mode": ("0/1/2", "A / B / C"),
 "timeout_bars": ("M5 bars", "0 = OFF, otherwise 6/12/18/24"),
 "partial_status": ("string", "NONE / DONE / SKIPPED"),
 "partial_close_ratio": ("ratio", "realised partial close fraction (valid range 0.40..0.60)"),
 "mfe_r": ("R", "maximum favourable excursion in R"),
 "mae_r": ("R", "maximum adverse excursion in R (negative)"),
 "mfe_3bars": ("R", "MFE within the first 3 M5 bars"),
 "mae_3bars": ("R", "MAE within the first 3 M5 bars"),
 "mfe_6bars": ("R", "MFE within the first 6 M5 bars"),
 "mae_6bars": ("R", "MAE within the first 6 M5 bars"),
 "fakeout_3": ("TRUE/FALSE/NA", "v0.4.1a Addendum E: the price reached the INITIAL SL within 3 M5 bars of entry (BUY on the Bid, SELL on the Ask), independent of the exit mode. NA when the window could not be fully observed"),
 "fakeout_6": ("TRUE/FALSE/NA", "v0.4.1a Addendum E: same over 6 M5 bars. NA is never collapsed to FALSE"),
 "holding_bars": ("M5 bars", "M5 bars between entry and the record"),
 "exit_reason": ("string", "EXIT_TP / EXIT_SL / EXIT_BE / EXIT_TRAIL / EXIT_PARTIAL / EXIT_TIMEOUT / EXIT_MANUAL_OR_EXTERNAL"),
 "result_r": ("R", "total realised P/L divided by the initial RiskMoney"),
 "realized_pl": ("account ccy", "realised profit incl. swap and commission"),
 "dd_pct": ("%", "(PeakEquity - Equity) / PeakEquity * 100"),
 "dd_state": ("enum", "NORMAL / MODERATE / RESTRICTED / HARD_STOP / STATE_UNCERTAIN"),
 "daily_lock": ("0/1", "DailyEntryLock active (Equity <= DailyStartEquity * 0.98)"),
 "hard_stop_latched": ("0/1", "the 10% hard stop latch is set"),
 "peak_equity": ("account ccy", "stored peak equity"),
 "equity": ("account ccy", "account equity at the record"),
 "balance": ("account ccy", "account balance at the record"),
 "total_risk": ("%", "summed initial risk of open positions plus the candidate"),
 "currency_exposure": ("%", "worst same currency component, same direction exposure"),
 "corr_cluster_risk": ("%", "risk of the correlation cluster containing the candidate (direction adjusted)"),
 "corr_cluster_risk_raw": ("%", "same cluster computed on raw Pearson sign, logged for ISSUE-002"),
 "corr_state": ("enum", "CORR_READY / CORR_WARMUP_UNKNOWN"),
 "corr_unavailable": ("0/1", "1 while the correlation window is not yet available (spec 11.4)"),
 "corr_warmup_days": ("bars", "complete D1 bars available for the correlation window"),
 "unknown_cluster_risk": ("%", "candidate plus all open positions while correlation is unknown"),
 "open_positions": ("count", "open positions carrying the EA magic number"),
 "skip_reason": ("enum", "reason code, NONE when the record is not a skip (see reason_codes.md)"),
 "retcode": ("int", "MT5 trade server return code"),
 "state_store_status": ("enum", "OK / RECOVERED / UNCERTAIN, exactly as named by spec 12"),
 "state_store_detail": ("enum", "internal detail: STORE_OK / STORE_FILE_ONLY / STORE_GV_ONLY / STORE_MISMATCH_CONSERVATIVE / STORE_BOTH_LOST / STORE_FRESH"),
 "state_epoch": ("int", "state epoch id; incremented only by an audited manual recovery (v0.4.1a Addendum B). Performance must not be aggregated across epochs"),
 "recovery_result": ("enum", "outcome of an operator requested recovery on this run (NOT_REQUESTED / RECONCILED_AUDITED / EPOCH_CREATED / REFUSED_*)"),
 "run_id": ("string", "research run identifier from InpRunId"),
}


def main():
    text = open(SRC, encoding="utf-8").read()
    body = text.split("string G3LogHeader()", 1)[1].split("return(h);", 1)[0]
    parts = re.findall(r'h=h\+"([^"]*)"', body)
    header = "".join(parts)
    cols = header.split(",")
    missing = [c for c in cols if c not in DESC]
    if missing:
        print("columns without a description: %s" % missing)
        return 1

    lines = []
    lines.append("# G3 Research Log Schema")
    lines.append("")
    lines.append("Authority: Master Specification v0.4 section 16.")
    lines.append("")
    lines.append("This file is generated from `G3LogHeader()` in `src/ResearchLogger.mqh`")
    lines.append("by `tools/gen_log_schema.py`. Do not edit it by hand.")
    lines.append("")
    lines.append("* Format: CSV, comma separated, ANSI, CRLF line endings.")
    lines.append("* Location: `<terminal common folder>/Files/G3RSRCH/log_<account>_<magic>_<symbol>_<run_id>.csv`.")
    lines.append("* One file per symbol instance per run.")
    lines.append("* Every decision_tick writes exactly one `EVAL` row, including")
    lines.append("  candidates that are skipped, so rejection statistics are complete.")
    lines.append("* A candidate that clears every strategy gate also writes a `SHADOW`")
    lines.append("  row BEFORE any portfolio guard can drop it. The offline")
    lines.append("  chronological portfolio replay of v0.4.1a Addendum F re-decides")
    lines.append("  those rows against the shared state.")
    lines.append("* Executed signals add an `ENTRY` row, partial closes a `PARTIAL` row,")
    lines.append("  and the close of a position an `EXIT` row.")
    lines.append("* A `FAKEOUT` row closes the 6 bar diagnostic window of Addendum E,")
    lines.append("  which keeps running after the position itself has closed.")
    lines.append("* Rows are joined on `signal_id`.")
    lines.append("* Times are integer epoch seconds; `time_server` is broker time.")
    lines.append("* Field names follow Master Specification v0.4 section 12.")
    lines.append("")
    lines.append("Column count: **%d**." % len(cols))
    lines.append("")
    lines.append("| # | column | unit | meaning |")
    lines.append("|---|--------|------|---------|")
    for i, c in enumerate(cols, 1):
        unit, desc = DESC[c]
        lines.append("| %d | `%s` | %s | %s |" % (i, c, unit, desc))
    lines.append("")
    lines.append("## Tri-state fields")
    lines.append("")
    lines.append("`fakeout_3` and `fakeout_6` are TRUE, FALSE or NA. NA means the six bar")
    lines.append("observation window could not be completed - for example the EA was")
    lines.append("restarted inside it - and is never written as FALSE. A row whose")
    lines.append("window is still open also reads NA; the closing verdict arrives on the")
    lines.append("`FAKEOUT` row for that `signal_id`.")
    lines.append("")
    open(OUT, "w", encoding="utf-8").write("\n".join(lines))
    print("wrote %s (%d columns)" % (OUT, len(cols)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
