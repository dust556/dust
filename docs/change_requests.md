# ISSUES and CHANGE REQUESTS

**Re-adjudicated 2026-09-22** against the three authority documents
(Master Specification v0.4, G2 Re-Audit Report v0.4, G3研究開始記録).
Evidence and full reasoning: `docs/G4_reconciliation_report.md`.

**Patched 2026-09-22** — DEV-001, DEV-002, DEV-003, DEV-004, DEV-008 and
DEV-009..DEV-013, DEV-015, DEV-016 are now **FIXED** in the source; see
`docs/G4_patch_report.md` and section H below.

Severity: **BLOCKER** stops G3 numbers from being citable. **HIGH** changes
results materially. **MEDIUM** changes results in identifiable cases.
**LOW** is a clarification.

---

## A. Open BLOCKER

| id | issue | why it is still open |
|----|-------|----------------------|
| ISSUE-016 / CR-014 | The section 21 compile gate (MetaEditor, 0 errors / 0 warnings) has not been executed; the 29 integration cases have not been run. | No MQL5 toolchain in this environment. Held open by instruction. |
| ISSUE-012 / CR-009 | Primary tick feed, second independent feed, symbol specifications, initial equity, account currency and cost information are not supplied (spec 13.1). | Not received. The G3 start record states the same gap. Held open by instruction. |
| ISSUE-013 / CR-008 | No fixed data split exists for a 61-71 month dataset. Spec 13.2 defines only the 72 month case and the "60 months only" fallback. | The G3 start record states explicitly: "61〜71か月…の固定分割はv0.4に明示されていない。分割を推測して研究を開始しない。G1への仕様照会又はCRの対象として保留する". Held open by instruction. |

## B. Open HIGH

| id | issue | note |
|----|-------|------|
| ISSUE-003 / CR-003 | The MT5 strategy tester runs exactly one expert, so the portfolio rules of spec 11.4 cannot be produced in a backtest with one instance per symbol. | Held open by instruction. Options (a) single-instance multi-symbol research mode, (b) offline portfolio replay of the EVAL/ENTRY/EXIT logs, (c) forward/live only. The implementation does not choose. |
| **DEV-005** / CR-006R | Spec 16 registers 41 parameters with a provenance class; every H-class parameter requires OAT sensitivity (13.4), and spec 14.1 fails G3 if any registered OAT parameter or test is unreported. The EA exposes three inputs; RESTRICTED ScoreThreshold (16: baseline 6, OAT 5/6/7) and Deviation Hard Cap (9.3 / 16: 1.0/2.0/3.0 pips) are compile-time constants. | The execution method must be decided by G1/G2: EA inputs, or one build per OAT point. 13.4 forbids a brute-force grid, so simply exposing 30 inputs is not automatically correct. |
| **DEV-006** / CR-015 | Spec 13.5 and the G3 start record define execution stress as a spread **multiplier** (x1.5 / x2.0 / x3.0) plus adverse slippage of 0.25 / 0.50 / 1.00 x observed spread on entry and exit. The EA offers an absolute extra-spread input and no slippage model. | Spec 14.1 requires Expectancy_R > 0 under Stress-1, which cannot currently be evaluated. |

## C. Open MEDIUM

| id | issue |
|----|-------|
| **DEV-007** / CR-016 | Spec 12 defines `fakeout_3 / fakeout_6` as "breakout後3/6本以内反転SL等の診断flag" and 7.2 refers to the reversal-SL rate within 3/6 bars after entry. The EA emits `NA_SPEC_UNDEFINED`. The residual ambiguity is whether "反転SL等" covers only an SL fill, and whether the origin is entry or breakout — hence CR-016. Spec 13.6 and the G3 start record require a fakeout subgroup analysis. |

## D. Open LOW

| id | issue |
|----|-------|
| DEV-014 | Appendix A returns before `manage_open_positions()` under STATE_UNCERTAIN; the implementation follows 11.2 and keeps managing open positions while refusing new entries. Not uniquely determined by the text, so it was left unchanged; which reading governs should be confirmed. |
| DEV-017 | Spec 11.2 requires manual recovery from STATE_UNCERTAIN but does not give the procedure. The implementation never resumes automatically, which satisfies 14.2. |

## H. FIXED in the source (see `docs/G4_patch_report.md`)

| id | old severity | fix |
|----|--------------|-----|
| DEV-001 | BLOCKER | `M15Input.atr14[3]`; each shift is tested against its own ATR14 (spec 6). Regression R-001a..d. |
| DEV-002 | BLOCKER | `G3IsPostGapBar()` in TimeSync; the first H4 bar completed after a gap of more than twice the period issues no signal (`POST_GAP_COOLDOWN`), and `post_gap` is logged for the 13.6 subgroup. Regression R-002a..f. |
| DEV-003 | BLOCKER | The account record is keyed on account_login + MagicNumber and shared by all symbol instances; the signal ledger is a separate per-symbol record. Updates are serialised under the cross-instance lock. Regression R-003a..g. |
| DEV-004 | HIGH | Break-even cost = incurred commission + swap + estimated exit commission; the spread is no longer added (spec 10.2). Regression R-004a..f. |
| DEV-008 | MEDIUM | `CommissionPerLotRoundTurn()` is added to pre-trade risk (spec 9.2) and logged as `commission_per_lot_est`. |
| DEV-009 | LOW | `state_store_status` now carries OK / RECOVERED / UNCERTAIN; the internal value moved to `state_store_detail`. Regression R-006, R-007j/k. |
| DEV-010 | LOW | `sl_raw_distance` and `sl_final_distance` columns added. Regression R-007c. |
| DEV-011 | LOW | `tick_value_profit` / `tick_value_loss` columns added. Regression R-007d. |
| DEV-012 | LOW | The daily reset triggers only on a forward server-date change (spec 15.4). |
| DEV-013 | LOW | The correlation window is 60 complete D1 bars (59 log returns), so exactly 60 bars is READY. Regression R-005a/b. |
| DEV-015 | LOW | The evaluation order now follows appendix A: direction, breakout gate, scores, minimums and threshold, then the volatility / spread hard filters. |
| DEV-016 | LOW | Log column names follow spec 12. Regression R-007a..h. |

---

## E. CLOSED by the authority documents

| old id | old severity | resolution |
|--------|--------------|------------|
| ISSUE-001 / CR-001 | BLOCKER | **CLOSED.** All three documents received and read in full. `spec_hash` fixed at `229f2992…7ff965` and verified against the hash table printed in the G3 start record. |
| ISSUE-002 / CR-004 | HIGH | **CLOSED.** Spec 11.4: "position sideを掛けたsigned correlation >=0.70". The implementation is direction adjusted and therefore **correct**. |
| ISSUE-004 / CR-005 | MEDIUM | **CLOSED.** Spec 11.1 + 8.1 + appendix A (`threshold = (dd_state == RESTRICTED ? 6 : 5)`) + spec 16, which registers RESTRICTED ScoreThreshold as its own parameter. The implementation is **equivalent within the registered value range**. |
| ISSUE-005 / CR-002 | MEDIUM | **CLOSED.** A definition exists in spec 12 and 7.2. The non-population is re-filed as DEV-007 and the residual wording ambiguity as CR-016. |
| ISSUE-006 / CR-006 | MEDIUM | **CLOSED.** Spec 16 supplies the full 41-row registry and 13.5 the stress scenarios. The input-surface gap is re-filed as DEV-005 / DEV-006. |
| ISSUE-007 / CR-007 | MEDIUM | **CLOSED.** Spec 8.2 / 8.3 say "M5 ATR14[1]" — the implementation is **correct**. Spec 6 requires the same-shift ATR on M15, which the implementation gets wrong: re-filed as DEV-001. |
| ISSUE-008 / CR-007 | MEDIUM | **CLOSED.** Spec 11.1: `DD = (PeakEquity - CurrentEquity) / PeakEquity`. The implementation is **correct**. |
| ISSUE-009 / CR-012 | LOW | **CLOSED.** Spec 9.3 carries both clauses verbatim; the literal reading in the implementation is **correct**. |
| ISSUE-010 / CR-010 | MEDIUM | **CLOSED.** Spec 10.2 defines the cost. The implementation deviates: re-filed as DEV-004. |
| ISSUE-011 / CR-011 | LOW | **CLOSED.** Spec 8.1: "M15 Setup | 0-2 | 最低点なし". The implementation is **correct**. |
| ISSUE-014 / CR-007 | MEDIUM | **CLOSED.** Spec 11.4: D1, 60 complete bars, log-return Pearson. The implementation is **correct**; the one-bar window difference is DEV-013. |
| ISSUE-015 / CR-013 | LOW | **CLOSED.** Spec 11.2 requires manual recovery and 14.2 makes an automatic resume an automatic FAIL. The implementation **complies**; the missing procedure is DEV-017. |
| ISSUE-017 | LOW | **CLOSED.** Spec 11.4 "Max positions = 3" is a portfolio-level limit; the account-wide reading in the implementation is **correct**. |

## F. New CHANGE REQUESTS

| id | request | blocks |
|----|---------|--------|
| CR-006R | Specify how the spec 16 OAT sensitivity is to be executed for the ~30 H-class parameters: EA inputs, or one build per OAT point. 13.4 forbids a brute-force grid, so the method must be chosen by G1/G2, not by the implementation. | DEV-005 |
| CR-015 | Specify where the 13.5 execution stress (spread multiplier, adverse slippage) is realised: inside the EA, in tester settings, or in post-processing. | DEV-006 |
| CR-016 | Give the exact definition of `fakeout_3` / `fakeout_6`: does "反転SL等" mean an SL fill only, is the origin the entry or the breakout bar, and is it a flag or a magnitude. | DEV-007 |

## G. Rejected by design (unchanged)

* Any additional entry filter, session filter or news filter.
* Any result-driven parameter change, symbol selection or threshold tuning.
* Any optimiser-friendly input surface or search helper beyond what spec 16
  registers, and only once CR-006R has specified the method.
* Any Final Holdout access, directory or reference.
