# ISSUES and CHANGE REQUESTS

No item below was resolved by guessing. Where an implementation had to proceed,
the chosen reading is stated, logged in the research CSV, and listed as an
assumption in `docs/known_limitations.md`.

Severity: **BLOCKER** stops G3 numbers from being citable. **HIGH** changes
results materially. **MEDIUM** changes results in identifiable cases.
**LOW** is a clarification.

## ISSUES

| id | severity | issue | current handling |
|----|----------|-------|------------------|
| ISSUE-001 | BLOCKER | Master Specification v0.4, G2 Re-Audit Report v0.4 and the G3 research start record were **not present** in the implementation environment (the repository was empty). The implementation traces to the prompt's restatement of the specification only. `spec_hash` cannot be computed. | Implemented from the prompt text; every constant is centralised in one `#define` block per module so it can be diffed against the authority document. See CR-001. |
| ISSUE-002 | HIGH | Section 12 says "signed correlation >= 0.70". It is not stated whether "signed" means the raw Pearson sign, or the sign adjusted for the trade direction of each leg (so that two positively correlated symbols held in opposite directions do not form a cluster). | Direction adjusted reading implemented for the decision. **Both** values are logged (`corr_cluster_risk`, `corr_cluster_risk_raw`) so the effect is measurable without a rerun. See CR-004. |
| ISSUE-003 | HIGH | The MT5 strategy tester runs exactly one expert. The decision_tick definition of section 4.1 (first tick of a new M5 bar) is only observable for the chart symbol, which forces one instance per symbol, which in turn makes the portfolio rules of section 12 (MaxPositions, total risk, correlation clusters) **untestable in the strategy tester**. | Per-symbol instances implemented; portfolio state shared through terminal global variables so live/forward runs are correct. Portfolio-level backtests are blocked. See CR-003. |
| ISSUE-004 | MEDIUM | Section 10 states `Score>=5` for NORMAL and MODERATE, while section 8 registers ScoreThreshold inputs of 4/5/6. It is undefined whether an input of 4 is admissible in NORMAL/MODERATE or is floored at 5. | Implemented as: the registered input applies, RESTRICTED forces `max(6, input)`. This preserves the 4/5/6 sweep the G3 plan requires. See CR-005. |
| ISSUE-005 | MEDIUM | Section 16 requires `fakeout_3` and `fakeout_6` columns, but no definition of a fakeout exists anywhere in the supplied specification. | Columns emitted with the literal `NA_SPEC_UNDEFINED`. No definition was invented. See CR-002. |
| ISSUE-006 | MEDIUM | Section 17 requires "OAT target parameters", "Safety stress parameters" and "Execution stress parameters" to be inputs, but the pre-registered list was not supplied. | Only execution stress inputs that cannot change strategy logic were added (`InpStressExtraSpreadPoints`, `InpStressCommissionPerLot`, both neutral by default). No safety-stress parameter was invented; the spec-fixed risk and drawdown constants remain constants. See CR-006. |
| ISSUE-007 | MEDIUM | The timeframe of `ATR14` in sections 8, 9 and 13, and the shift of the ATR used by the M15 pullback band in section 6, are not stated explicitly. | M5 ATR14 shift 1 for sections 8/9/13 (A-04); M15 ATR14 shift 1 for section 6 (A-03). Both are logged (`atr_m5`, `atr_m15`, `atr_h4`). See CR-007. |
| ISSUE-008 | MEDIUM | Section 10 gives drawdown thresholds but no drawdown definition (peak equity vs. initial equity vs. balance, and the reset rule for the peak). | `DD% = (PeakEquity - Equity) / PeakEquity * 100`, peak tracked on equity and never reset (A-01, A-12). Logged as `dd_pct` and `peak_equity`. See CR-007. |
| ISSUE-009 | LOW | Section 13 states both "computed > HardCap -> do not send the order" and "sent deviation = max(1, min(computed, HardCap))". The `min()` branch is unreachable. | Implemented literally: above the cap nothing is sent and `deviation_cap_hit` is set; otherwise `max(1, min(computed, cap))`. See CR-012. |
| ISSUE-010 | MEDIUM | "cost-adjusted BE" (section 14 B) does not enumerate its cost components (spread only, spread + commission, swap?). | Spread plus the optional commission input, converted to price (A-06). See CR-010. |
| ISSUE-011 | LOW | Sections 5 and 7 state minimum scores (H4 >= 1, M5 >= 1) but section 6 states no minimum for M15. | Implemented with no M15 minimum, exactly as written. Confirmation requested in CR-011. |
| ISSUE-012 | BLOCKER | The G3 data inputs are missing: primary tick feed, second independent feed, symbol specifications, initial equity, account currency, data start/end dates, and the Research EA hash. | No backtest was run and no result was fabricated (section 22). See CR-009. |
| ISSUE-013 | BLOCKER | If only 61-71 months of data exist, Master Specification v0.4 defines no IS / OOS / Walk-Forward split. | No split was invented. See CR-008. |
| ISSUE-014 | MEDIUM | The correlation input series is unspecified (prices, simple returns or log returns; 60 bars or 60 returns). | D1 close-to-close log returns, 60 returns from 61 closed bars (A-05); `corr_warmup_days` is logged. See CR-007. |
| ISSUE-015 | LOW | No exit procedure is defined for `STATE_UNCERTAIN`. | The EA refuses all new entries and keeps managing open positions. See CR-013. |
| ISSUE-016 | BLOCKER | Section 21 requires a compile gate of 0 errors / 0 warnings. No MQL5 compiler exists in this environment (Linux container, no MetaEditor, no Wine). | Compile status reported as NOT_RUN. A static structural check plus an executable host test harness for the pure logic are provided in place of, not instead of, the compile gate. See CR-014. |
| ISSUE-017 | LOW | Whether MaxPositions = 3 is per account or per symbol is not stated. | Account-wide across all positions carrying the EA magic number. |

## CHANGE REQUESTS

| id | request | blocks |
|----|---------|--------|
| CR-001 | Supply Master Specification v0.4, G2 Re-Audit Report v0.4 and the G3 research start record, together with their SHA-256 hashes, so that the implementation can be re-verified line by line and `manifests/spec_hash.txt` can be filled in. | ISSUE-001 |
| CR-002 | Define `fakeout_3` and `fakeout_6`: the reference level, the window (M5 bars? from entry or from the signal bar?), and whether the value is a flag or a magnitude. | ISSUE-005 |
| CR-003 | Define how portfolio-level research data is to be produced given that the MT5 strategy tester runs one expert. Options for the authority to choose from: (a) a single-instance multi-symbol research mode where the decision point is the first tick **observed** after a new M5 bar of each symbol (a documented deviation from section 4.1); (b) per-symbol backtests plus an offline portfolio simulator that replays the EVAL/ENTRY/EXIT logs under section 12; (c) restrict G3 portfolio evidence to forward/live runs. The implementation will not choose. | ISSUE-003 |
| CR-004 | Define "signed correlation": raw Pearson sign, or sign adjusted by the direction of each leg. | ISSUE-002 |
| CR-005 | Define the interaction between the registered ScoreThreshold input (4/5/6) and the per-state minimum scores of the drawdown table. | ISSUE-004 |
| CR-006 | Publish the pre-registered OAT parameter list and the safety-stress and execution-stress parameter lists, including admissible values. Until then, no additional input will be added. | ISSUE-006 |
| CR-007 | Confirm the ATR timeframes and shifts (sections 6, 8, 9, 13), the drawdown definition and peak rule (section 10), and the correlation input series (section 12). | ISSUE-007, ISSUE-008, ISSUE-014 |
| CR-008 | Define the IS / OOS / Walk-Forward / Final Holdout split for a 61-71 month dataset, or state the minimum dataset length under which G3 may not start. | ISSUE-013 |
| CR-009 | Supply the primary tick feed, the second independent feed, symbol specifications, initial equity, account currency and data start/end dates. | ISSUE-012 |
| CR-010 | Enumerate the components of the cost-adjusted break-even. | ISSUE-010 |
| CR-011 | Confirm that M15 has no minimum score. | ISSUE-011 |
| CR-012 | Confirm that the deviation `min()` expression in section 13 is redundant and that "do not send above the cap" is the governing rule. | ISSUE-009 |
| CR-013 | Define the procedure for leaving `STATE_UNCERTAIN` (and whether it requires the same audit trail as a manual HARD_STOP reset). | ISSUE-015 |
| CR-014 | Nominate a machine with MetaEditor / MQL5 for the section 21 compile gate and record the resulting `.ex5` SHA-256 in `manifests/EA_hash.txt`. | ISSUE-016 |

## Rejected by design

The following were considered and deliberately **not** implemented, because
they are not in the specification:

* Any additional entry filter, session filter or news filter.
* Any result-driven parameter change, symbol selection or threshold tuning.
* Any optimiser-friendly input surface or search helper.
* Any Final Holdout access, directory or reference.
