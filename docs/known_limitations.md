# Known Limitations and Documented Assumptions

Authority order: Master Specification v0.4 > G2 Re-Audit Report v0.4 >
G3 research start record > the implementation prompt.

**None of the three authority documents was available in this implementation
environment** (see `docs/change_requests.md`, ISSUE-001). Everything below is
stated so that Manus can verify it against the authority documents before any
G3 number is accepted.

## A. Assumptions made where the supplied text is silent

Every assumption is minimal, conservative, and logged in the research CSV so
that its effect can be measured.

| id | assumption | where | why it was needed |
|----|------------|-------|-------------------|
| A-01 | Drawdown is measured against stored peak **equity**: `DD% = (PeakEquity - Equity) / PeakEquity * 100`. | `G3DrawdownPct()` | Section 10 names the thresholds but not the drawdown basis; `PeakEquity` is a mandated StateStore field, which makes peak-equity drawdown the only consistent reading. |
| A-02 | Median of an even sample = mean of the two central order statistics. | `G3Median()` | `median(ATR14 shifts 2..101)` is a 100 element sample; the tie rule is not stated. |
| A-03 | The `0.20 x ATR` pullback band uses M15 `ATR14` of spec shift 1. | `M15Input.atr14_s1` | Section 6 says "same shift EMA20" but does not bind the ATR shift. |
| A-04 | `ATR14[1]` in sections 8, 9 and 13 is the **M5** ATR14 of shift 1. | `MarketFilters`, `RiskManager`, `OrderManager` | These sections operate on the M5 trigger context (M5 highs/lows, spread at the decision tick). |
| A-05 | Correlation uses D1 **close-to-close log returns**; 60 returns are taken from 61 fully closed D1 bars. | `G3D1Returns()` | Section 12 says "D1 complete bars 60" and "Pearson correlation" without naming the series. |
| A-06 | Cost adjusted break-even cost = current spread in price, plus the optional commission input converted to price. | `G3BreakevenPrice()`, `MoneyPerLotToPrice()` | Section 14 B says "cost-adjusted BE" without listing the cost components. |
| A-07 | `SYMBOL_TRADE_STOPS_LEVEL` is measured against Bid for a BUY and Ask for a SELL. | `G3AdjustStopBroker()` | MT5 convention; not restated by the spec. |
| A-08 | "Same currency component, same direction" means signed per-currency exposure: a long EURUSD is long EUR and short USD. | `G3CurrencyRiskPct()` | Section 12 does not spell out the direction algebra. |
| A-09 | On store mismatch the conservative merge is: more severe DD state, latch OR, higher PeakEquity, higher DailyStartEquity, later ServerDate, later consumed signal. | `G3MergeConservative()` | Section 10 says "adopt the more conservative state" without a field level rule. |
| A-10 | RESTRICTED forces `ScoreThreshold = max(6, input)`; the other states use the registered input. | `G3EffectiveScoreThreshold()` | See ISSUE-004. |
| A-11 | Drawdown state recovery moves one state per evaluation (RESTRICTED -> MODERATE -> NORMAL), each guarded by its own hysteresis level. | `G3NextDDState()` | Section 10 gives two separate recovery rules and no skip rule. |
| A-12 | Peak equity tracks account **equity**, not balance, and is updated on every evaluation. | `RefreshAccountState()` | Consistent with A-01 and with `RiskMoney = Equity x EffectiveRiskPct`. |
| A-13 | `DailyStartEquity` is captured on the first processed tick after the broker server date changes. | `RefreshAccountState()` | Section 11 says "at the start of the broker server date". |
| A-14 | Signal consumption is monotonic per symbol: a signal whose M5 bar time is not newer than the last consumed one is refused. | `G3SignalAlreadyConsumed()` | Fail-closed reading of "duplicate orders are never acceptable". |

## B. Limitations of this build

| id | limitation | impact on G3 |
|----|------------|--------------|
| L-01 | **No MQL5 toolchain exists in this environment** (no MetaEditor, no Wine). The compile gate of section 21 could not be executed. A static pre-compile check (`tools/mql5_static_check.py`) is provided instead and reports 0 issues. | Compile status is NOT_RUN, not PASS. The EA must be compiled in MetaEditor before any G3 run. |
| L-02 | Host unit tests cover the pure specification logic only. Terminal-bound behaviour (OrderSend, file and global-variable I/O, the account mode guard) is specified in `tests/integration_test_plan.md` but cannot be executed here. | Integration test status is NOT_RUN. |
| L-03 | One EA instance per symbol. Portfolio state is shared through terminal global variables plus a recomputation fallback. If terminal global variables are wiped while positions are open, exposure is recomputed from the live stops, which can differ slightly from the risk booked at entry. | Logged in `total_risk` / `currency_exposure`; check `state_store_status`. |
| L-04 | MFE/MAE are updated per tick from the position's close-side price (Bid for BUY, Ask for SELL), not from completed M5 bar extremes. | Excursion resolution depends on tick density of the feed. |
| L-05 | Currency components are parsed from the first six characters of the symbol name, so broker suffixes (`EURUSD.m`) are handled but exotic naming schemes are not. | Verify symbol naming before a run. |
| L-06 | Execution stress is limited to additional spread and a commission input. Slippage cannot be injected into the MT5 strategy tester by an EA. | Slippage stress needs a tester-side or feed-side mechanism; see ISSUE-006. |
| L-07 | `realized_pl` is summed from `HistorySelectByPosition()` including swap and commission; brokers differ in how commission is booked. | Compare against the tester report before accepting money-based statistics. |
| L-08 | `fakeout_3` / `fakeout_6` are emitted as `NA_SPEC_UNDEFINED` because the specification does not define them. | See CR-002. |
| L-09 | The MT5 strategy tester runs exactly one expert, so a per-symbol-instance design cannot produce portfolio-level (MaxPositions, total risk, correlation cluster) backtest results in the tester. | **Blocking for portfolio-level G3 runs.** See ISSUE-003 / CR-003. |
| L-10 | There is no defined procedure for leaving `STATE_UNCERTAIN`; the EA simply refuses new entries. | See ISSUE-015 / CR-013. |
| L-11 | `G3_MAX_LEGS` is 16 and `G3_MAX_TRACKED` is 16; both exceed the specified MaxPositions of 3 but bound memory. | No effect at the specified limits. |

## C. What this build deliberately does NOT do

* No Final Holdout data, directory, path, reference or computation exists
  anywhere in this repository (section 24). The static check scans for it.
* No optimiser-friendly input surface, no genetic / Bayesian / grid search
  helper, no profit-driven parameter (section 17, section 2).
* No netting account support, no averaging down, no martingale, no post-loss
  size increase, no news filter, no external realtime decision source.
* No backtest result of any kind is reported, because no primary tick feed,
  symbol specification, initial equity, account currency or data range was
  supplied (section 22).
