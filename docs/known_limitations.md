# Known Limitations and Documented Assumptions

Authority order: Master Specification v0.4 > G2 Re-Audit Report v0.4 >
G3 research start record > the implementation prompt.

**Updated 2026-09-22.** The three authority documents have since been received
and read in full (ISSUE-001 CLOSED). Section A below is no longer a list of
open assumptions: each one has been checked against the authority text and is
marked CONFIRMED or REFUTED. A refuted assumption became a conformance
deviation, recorded in `docs/G4_reconciliation_report.md`.

## A. Assumptions, re-adjudicated against Master Specification v0.4

Every assumption is minimal, conservative, and logged in the research CSV so
that its effect can be measured.

| id | assumption | verdict against the authority text |
|----|------------|------------------------------------|
| A-01 | `DD% = (PeakEquity - Equity) / PeakEquity * 100` | **CONFIRMED** — spec 11.1 states this formula verbatim. |
| A-02 | Median of an even sample = mean of the two central order statistics | **NOT ADDRESSED** by the spec (15.3 only fixes the window as shifts 2..101). Remains a documented convention; no deviation. |
| A-03 | The 0.20 x ATR pullback band uses the M15 ATR14 of spec shift 1 | **REFUTED** — spec 6 requires "EMA20同shift + 0.20×ATR同shift". Was DEV-001 (BLOCKER), **now FIXED**: each shift uses its own ATR14. |
| A-04 | `ATR14[1]` in the volatility, spread, SL and deviation rules is the M5 ATR14 | **CONFIRMED** — spec 8.2 and 8.3 say "M5 ATR14[1]" explicitly. |
| A-05 | Correlation uses D1 close-to-close log returns | **CONFIRMED** — spec 11.4 says "D1の直近60 complete barsのlog return Pearson correlation". The window was corrected from 61 to 60 complete bars (DEV-013 fixed). |
| A-06 | Cost adjusted BE cost = current spread + optional commission | **REFUTED** — spec 10.2 defines the cost as 既発生commission + swap + 推定exit commission and states that the spread must **not** be added. Was DEV-004 (HIGH), **now FIXED**. |
| A-07 | StopsLevel is measured against Bid for a BUY and Ask for a SELL | **NOT CONTRADICTED** — spec 9.1 leaves the reference price to MT5 convention. |
| A-08 | Signed per-currency exposure: a long EURUSD is long EUR and short USD | **CONFIRMED** — spec 11.4: "BUY EURUSDはEUR + / USD -として両通貨へ符号付きriskを配賦する". |
| A-09 | Conservative merge on store mismatch | **CONFIRMED** — spec 11.2: "より保守的なstate（高いPeak、厳しいDD state、HardStop=trueを優先）". |
| A-10 | RESTRICTED forces `max(6, input)`, other states use the registered input | **CONFIRMED (equivalent)** — appendix A: `threshold = (dd_state == RESTRICTED ? 6 : 5)`; spec 16 registers RESTRICTED ScoreThreshold separately. Within the registered ranges the two are identical. Exposing that parameter is DEV-005. |
| A-11 | Recovery moves one state per evaluation | **CONFIRMED** — spec 11.1 gives one hysteresis rule per step and no skip rule. |
| A-12 | Peak tracks equity and is never reset | **CONFIRMED** — spec 11.1 and 11.2 (PeakEquity is a persisted field, "高いPeak"を優先). |
| A-13 | DailyStartEquity is captured at the server date change | **CONFIRMED** — spec 11.3 and 15.4 (日次境界はBroker server date). The 15.4 double-reset guard is now implemented (DEV-012 fixed): only a forward date change starts a new day. |
| A-14 | Signal consumption is monotonic per symbol | **CONFIRMED** — spec 4.1 requires fail-closed exactly-once. The ledger is now a separate per-symbol record while the account record follows the 11.2 key (DEV-003 fixed). |

## B. Limitations of this build

| id | limitation | impact on G3 |
|----|------------|--------------|
| L-01 | **No MQL5 toolchain exists in this environment** (no MetaEditor, no Wine). The compile gate of section 21 could not be executed. A static pre-compile check (`tools/mql5_static_check.py`) is provided instead and reports 0 issues. | Compile status is NOT_RUN, not PASS. The EA must be compiled in MetaEditor before any G3 run. |
| L-02 | Host unit tests cover the pure specification logic only. Terminal-bound behaviour (OrderSend, file and global-variable I/O, the account mode guard) is specified in `tests/integration_test_plan.md` but cannot be executed here. | Integration test status is NOT_RUN. |
| L-03 | One EA instance per symbol. The account record (peak equity, DD state, daily start equity, hard stop latch) is shared under the 11.2 key and updated under a cross-instance lock; open-position exposure is published through terminal global variables with a recomputation fallback. If terminal global variables are wiped while positions are open, exposure is recomputed from the live stops, which can differ slightly from the risk booked at entry. | Logged in `total_risk` / `currency_exposure`; check `state_store_status`. |
| L-04 | MFE/MAE are updated per tick from the position's close-side price (Bid for BUY, Ask for SELL), not from completed M5 bar extremes. | Excursion resolution depends on tick density of the feed. |
| L-05 | Currency components are parsed from the first six characters of the symbol name, so broker suffixes (`EURUSD.m`) are handled but exotic naming schemes are not. | Verify symbol naming before a run. |
| L-06 | Execution stress is an absolute extra-spread input with no slippage model. Spec 13.5 requires a spread multiplier plus adverse slippage. | See DEV-006 / CR-015. |
| L-07 | `realized_pl` is summed from `HistorySelectByPosition()` including swap and commission; brokers differ in how commission is booked. | Compare against the tester report before accepting money-based statistics. |
| L-08 | `fakeout_3` / `fakeout_6` are emitted as `NA_SPEC_UNDEFINED`. The specification **does** define them (12, 7.2), but the exact reading of "反転SL等" is still open, so no definition was invented. | See DEV-007 / CR-016. |
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
  supplied (spec 13.1; the G3 start record records the same gap).
