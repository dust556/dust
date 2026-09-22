# ISSUES and CHANGE REQUESTS

**Re-adjudicated 2026-09-22** against the three authority documents
(Master Specification v0.4, G2 Re-Audit Report v0.4, G3研究開始記録).
Evidence and full reasoning: `docs/G4_reconciliation_report.md`.

**Patched 2026-09-22 (Patch-1)** — DEV-001, DEV-002, DEV-003, DEV-004,
DEV-008 and DEV-009..DEV-013, DEV-015, DEV-016 are **FIXED**; see
`docs/G4_patch_report.md` and section H.

**Patched 2026-09-22 (Patch-2)** — Master Specification v0.4.1a Addendum
passed the G2 delta re-audit (BLOCKER 0 / HIGH 0 / PASS), and all seven
remaining design questions are now **IMPLEMENTED**: DEV-005, DEV-006,
DEV-007, DEV-014, DEV-017, ISSUE-003 and ISSUE-013. See
`docs/G4_patch2_report.md` and section I.

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

*(none)*

Superseded entries:
| ISSUE-003 / CR-003 | CLOSED by Addendum F, implemented in Patch-2. |
| DEV-005 / CR-006R | CLOSED by Addendum C, implemented in Patch-2. |
| DEV-006 / CR-015 | CLOSED by Addendum D, implemented in Patch-2. |

## C. Open MEDIUM

| id | issue |
|----|-------|
| N-3 (G2 delta re-audit, non-blocking) | The cross-check windows are chosen on a volatility extreme, which may not be where simultaneous candidates are dense. Implemented as a **disclosure**: the simultaneous candidate count is reported per window and a window below the disclosure level is annotated as of limited representativeness. No new PASS threshold was added. |

## D. Open LOW

| id | issue |
|----|-------|
| LOW-4 (G2 delta re-audit, non-blocking) | There is no third-party procedure that confirms a TECHNICAL_RERUN really was an infrastructure failure. Implemented as a **review queue**: every TECHNICAL_RERUN entry carries `review_required` and is listed in the manifest for later G2/G3 sampling. No new PASS threshold was added. |

Superseded: DEV-014 and DEV-017 were resolved by Addendum A and Addendum B
and implemented in Patch-2.

## I. IMPLEMENTED by Patch-2 (see `docs/G4_patch2_report.md`)

| id | authority | implementation |
|----|-----------|----------------|
| DEV-014 | Addendum A | `OnTick()` runs protective management first and returns before any new signal work under STATE_UNCERTAIN; no forced flat; peak/DD are not written while the state is untrusted. Regression Q-005..Q-007, I-030. |
| DEV-017 | Addendum B | `G3RecoveryPrecheck()` / `G3ManualRecover()` / `G3BuildEpochState()`: operator named, G1 review record required, flat book required, unknown hard stop never cleared, everything audited, restart required before trading resumes. Regression Q-009..Q-013. |
| DEV-005 | Addendum C | `tools/g3research/oat_pipeline.py`: OAT on Research IS only, family venue by kind, complete family report, freeze, diagnostic WF with `wf_iteration_manifest`, Static OOS one-shot. Regression P-300, P-400. |
| DEV-006 | Addendum D | `tools/g3research/stress_replay.py`: closed scenario table, adverse on both legs, stressed geometry restaged, four-condition Base parity gate. Regression P-500. |
| DEV-007 | Addendum E | `G3FakeoutWatch` in `src/ExitManager.mqh` plus the EA observation loop: initial entry / initial SL reference, entry bar is bar 1, exit-mode independent, tri-state with NA. Regression Q-001..Q-008. |
| ISSUE-003 | Addendum F | `SHADOW` records in the EA plus `tools/g3research/portfolio_replay.py`: fixed tie-break order, one shared state machine, cross-check period selection and four-condition gate, N-3 disclosure. Regression P-600..P-900. |
| ISSUE-013 | Addendum G | `tools/g3research/data_intake.py`: 60-71 months trim to the latest 60, surplus excluded from gate performance and from WF folds, manifest records the window. Regression P-100, P-200. |

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
