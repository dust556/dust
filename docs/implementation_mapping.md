# Implementation Mapping

Master Specification v0.4 section -> implementation file -> function -> test case.

> **Section numbering corrected 2026-09-22.** The first issue of this table used
> the section numbers of the implementation request, not of the authority
> document. The numbers below are those of Master Specification v0.4 itself.
> Known conformance deviations found during that reconciliation are recorded in
> `docs/G4_reconciliation_report.md` (DEV-001 .. DEV-017); rows affected by one
> carry the DEV id.

Test case IDs starting with `T-` are executable host unit tests
(`tests/host/test_main.cpp`, run with `tests/run_unit_tests.sh`).
IDs starting with `I-` are MetaTrader 5 integration tests that can only be
executed inside a terminal (`tests/integration_test_plan.md`).

| Master Spec v0.4 section | file | function(s) | test case |
|---|---|---|---|
| 15.2 account mode (Retail Hedging only) | `src/G3_ResearchEA.mq5` | `OnInit()` account margin mode guard | I-001 test_retail_hedging_guard, I-002 test_netting_rejected |
| 2 / 4 timeframes and universe | `src/G3_ResearchEA.mq5` | `OnInit()` indicator handles (H4/M15/M5) | I-003 test_symbol_universe_instances |
| 4.1 decision_tick | `src/TimeSync.mqh` | `G3IsDecisionTick()` | I-004 test_decision_tick_is_first_tick_of_new_m5_bar |
| 4.1 signal_close_time | `src/TimeSync.mqh` | `G3SignalCloseTime()` | T-001, T-001b |
| 4.1 MTF sync, no forming H4/M15 | `src/TimeSync.mqh` | `G3ResolveClosedBarIndex()`, `G3ResolveHtfBar()` | T-001 test_no_forming_H4_reference, T-002 test_h4_reference_weekend_gap, T-003 test_m15_reference_is_not_fixed_shift1 |
| 4.1 history depth behind reference bar | `src/TimeSync.mqh` | `G3HasDepthBehind()` | T-003b, T-003c |
| 4.1 signal_id | `src/TimeSync.mqh` | `G3BuildSignalId()` | T-004 test_signal_id_format |
| 4.1 consume order (check, consume, flush, evaluate) | `src/StateStore.mqh` | `G3ConsumeSignal()`, `G3PersistState()` | T-005, T-005b, T-005c, I-005 test_consume_before_evaluation_order |
| 4.1 fail-closed exactly once | `src/StateStore.mqh` | `G3SignalAlreadyConsumed()`, `G3ConsumeSignal()` | T-005, I-006 test_crash_between_consume_and_order |
| 4.2 weekend / abnormal gap cooldown (**DEV-002**: not implemented) | `src/TimeSync.mqh` (per 15.1) | *missing* | *no test — feature absent* |
| 5.1 H4 direction gate | `src/SignalH4.mqh` | `G3H4DirectionGate()`, `G3H4Direction()` | T-037, T-037b |
| 5.2 H4 EMA50 slope point | `src/SignalH4.mqh` | `G3H4SlopeValue()`, `G3H4SlopeFlag()` | T-038, T-038c, T-038g |
| 5.2 H4 ADX/DI point | `src/SignalH4.mqh` | `G3H4AdxFlag()` | T-038d, T-038e, T-038f |
| 8.1 H4 score >= 1 | `src/SignalH4.mqh` | `G3H4Score()`, `G3_H4_MIN_SCORE` | T-038b |
| 6 M15 pullback (**DEV-001**: ATR must be same-shift) | `src/SetupM15.mqh` | `G3M15PullbackFlag()` | T-039, T-039b, T-039c, T-039e |
| 6 M15 structure | `src/SetupM15.mqh` | `G3M15StructureFlag()` | T-039d |
| 6 / 8.1 M15 score 0-2 (no minimum) | `src/SetupM15.mqh` | `G3M15Score()` | T-039 |
| 7.1 M5 breakout hard gate | `src/TriggerM5.mqh` | `G3M5BreakoutFlag()` | T-040, T-040b |
| 7.2 M5 candle quality | `src/TriggerM5.mqh` | `G3M5CandleFlag()` | T-041b, T-041c, T-041d |
| 7.2 M5 momentum | `src/TriggerM5.mqh` | `G3M5MomentumFlag()` | T-041e |
| 8.1 M5 score >= 1 | `src/TriggerM5.mqh` | `G3M5Score()`, `G3_M5_MIN_SCORE` | T-041 |
| 8.2 / 15.3 VolRatio and median | `src/MarketFilters.mqh`, `src/G3Types.mqh` | `G3VolRatio()`, `G3Median()` | T-042, T-046, T-046b, T-046c |
| 8.2 volatility point and block | `src/MarketFilters.mqh` | `G3VolScore()`, `G3VolBlocksEntry()` | T-042b, T-042c |
| 8.3 SpreadRatio, point and block | `src/MarketFilters.mqh` | `G3SpreadRatio()`, `G3SpreadScore()`, `G3SpreadBlocksEntry()` | T-043, T-043b, T-043c |
| 8.1 total score (max 8) | `src/MarketFilters.mqh` | `G3TotalScore()` | T-045 |
| 8.1 / 11.1 / 16 effective ScoreThreshold, RESTRICTED = 6 | `src/MarketFilters.mqh` | `G3EffectiveScoreThreshold()` | T-044, T-044b |
| 9.1 raw SL | `src/RiskManager.mqh` | `G3RawStop()` | T-024a, T-024b |
| 9.1 1.0 ATR minimum / 2.5 ATR rejection | `src/RiskManager.mqh` | `G3AdjustStopStrategy()` | T-024, T-024c, T-025, T-025b |
| 9.1 StopLevel correction and re-check | `src/RiskManager.mqh` | `G3AdjustStopBroker()` | T-023, T-023b, T-026 |
| 9.1 / 12 SL logging fields | `src/ResearchLogger.mqh` | `G3LogRecordToLine()` | T-047 |
| 9.2 RiskMoney | `src/RiskManager.mqh` | `G3RiskMoney()`, `G3RiskPctForState()` | T-014f |
| 9.2 / 15.4 OrderCalcProfit canonical 1 lot loss | `src/RiskManager.mqh` | `G3LossForOneLot()` | I-007 test_order_calc_profit_jpy_and_non_jpy |
| 9.2 lot floor onto VolumeStep | `src/G3Types.mqh`, `src/RiskManager.mqh` | `G3FloorToStep()`, `G3NormalizeVolume()`, `G3ComputeLot()` | T-018, T-018b, T-018c |
| 9.2 VolumeMin rejection | `src/RiskManager.mqh` | `G3ComputeLot()` | T-019, T-018d |
| 11.1 drawdown percentage | `src/RiskManager.mqh` | `G3DrawdownPct()` | T-014g |
| 11.1 DD state machine 6/8/10% | `src/RiskManager.mqh` | `G3NextDDState()` | T-011, T-011b, T-012, T-012b, T-013 |
| 11.1 recovery hysteresis 7% / 5% | `src/RiskManager.mqh` | `G3NextDDState()` | T-014, T-014b, T-014c, T-014d |
| 11.1 HARD_STOP latch | `src/RiskManager.mqh` | `G3NextDDState()` | T-013, T-015 |
| 11.1 manual reset (DD < 9% + audit) | `src/RiskManager.mqh`, `src/StateStore.mqh` | `G3ManualResetAdmissible()`, `G3ManualHardStopReset()`, `G3AuditLog()` | T-016, I-008 test_manual_reset_audit_record |
| 11.2 StateStore fields, schema, checksum (**DEV-003**: key must be account+magic) | `src/StateStore.mqh` | `G3StateToRecord()`, `G3StateToLine()`, `G3StateChecksum()`, `G3ParseStateLine()` | T-006, T-007b, T-007c |
| 11.2 dual store (file + global variables) | `src/StateStore.mqh` | `G3WriteStateFile()`, `G3WriteStateGV()`, `G3LoadState()` | I-009 test_dual_store_written, I-010 test_file_corruption_recovery |
| 11.2 mismatch -> conservative | `src/StateStore.mqh` | `G3ReconcileStores()`, `G3MergeConservative()`, `G3MoreConservativeState()` | T-010, T-010b, T-010c, T-010d |
| 11.2 both stores lost -> STATE_UNCERTAIN | `src/StateStore.mqh` | `G3ReconcileStores()` | T-009, T-009b |
| 11.2 corrupt store detection | `src/StateStore.mqh` | `G3ParseStateLine()`, `G3ReadStateGV()` | T-007, T-008 |
| 11.3 DailyEntryLock | `src/RiskManager.mqh`, `src/G3_ResearchEA.mq5` | `G3DailyEntryLocked()`, `RefreshAccountState()` | T-017, I-011 test_daily_lock_does_not_close_positions |
| 11.4 MaxPositions = 3 | `src/PortfolioManager.mqh` | `G3CheckPortfolio()` | T-035 |
| 11.4 MaxTotalInitialRisk = 1.50% | `src/PortfolioManager.mqh` | `G3TotalRiskPct()`, `G3CheckPortfolio()` | T-036 |
| 11.4 currency component exposure <= 1.00% | `src/PortfolioManager.mqh` | `G3CurrencyRiskPct()`, `G3WorstCurrencyRiskPct()` | T-034, T-034b, T-034c, T-034d |
| 11.4 correlation guard, D1 60 bars, log-return Pearson | `src/PortfolioManager.mqh`, `src/G3Types.mqh` | `G3D1Returns()`, `G3BuildCorrMatrix()`, `G3Pearson()` | T-032d, T-032e, T-032f, I-012 test_correlation_window_uses_closed_d1_only |
| 11.4 cluster risk <= 1.00% (side-multiplied signed corr >= 0.70) | `src/PortfolioManager.mqh` | `G3SignedLegCorrelation()`, `G3ClusterRiskPct()` | T-032, T-032b, T-032c |
| 11.4 CORR_WARMUP_UNKNOWN, unknown cluster <= 0.75% | `src/PortfolioManager.mqh` | `G3CheckPortfolio()` | T-033, T-033b |
| 12 correlation logging fields | `src/ResearchLogger.mqh` | `G3LogHeader()` | T-047 |
| 9.3 decision_tick market re-read | `src/OrderManager.mqh` | `G3ReadMarket()` | I-013 test_market_facts_reread_at_decision_tick |
| 9.3 PipSize (3/5 digits) | `src/OrderManager.mqh` | `G3PipSize()` | T-020, T-020b, T-020c, T-020d |
| 9.3 computedDeviationPoints | `src/OrderManager.mqh` | `G3BuildDeviationPlan()` | T-021d, T-021e, T-021f |
| 9.3 / 16 deviation hard cap 2.0 pips | `src/OrderManager.mqh` | `G3DeviationHardCapPoints()` | T-021, T-021b, T-021c |
| 9.3 computed > cap -> no order | `src/OrderManager.mqh` | `G3BuildDeviationPlan()` | T-022 |
| 9.3 one OrderSend per decision_tick, no retry | `src/OrderManager.mqh` | `G3SendMarketOrder()` | I-014 test_single_order_send_no_retry, I-015 test_order_send_failure_logged |
| 9.3 post-fill risk > 105% | `src/RiskManager.mqh`, `src/G3_ResearchEA.mq5` | `G3PostFillRiskRatio()`, `G3RiskCappedVolume()`, `EvaluateDecisionTick()` | T-027, T-027b, T-027c, I-016 test_post_fill_reduce_or_close |
| 10 A: fixed 2.0R TP, fixed SL | `src/ExitManager.mqh` | `G3InitialTakeProfit()`, `G3DesiredStop()` | T-048, T-048b, T-030e |
| 10 / 10.2 B: cost adjusted BE at 1.0R (**DEV-004**) | `src/ExitManager.mqh` | `G3BreakevenPrice()`, `G3DesiredStop()` | T-030d, T-030f |
| 10.1 B: ~50% partial at 1.5R | `src/ExitManager.mqh` | `G3BuildPartialPlan()` | T-028, T-029, T-029b, T-029c, T-029d |
| 10.1 B: partial impossible -> BE + trail on full volume | `src/ExitManager.mqh`, `src/G3_ResearchEA.mq5` | `G3DesiredStop()`, `ManagePositions()` | T-028, T-030g |
| 10 B: ATR x 2.0 trail after partial | `src/ExitManager.mqh` | `G3AtrTrailStop()`, `G3DesiredStop()` | T-030c, T-030g |
| 10.1 B: portfolio exposure recomputed after partial | `src/G3_ResearchEA.mq5`, `src/PortfolioManager.mqh` | `ManagePositions()`, `G3RegisterPositionRisk()` | I-017 test_exposure_after_partial |
| 10 C: ATR x 2.5 chandelier trail | `src/ExitManager.mqh` | `G3DesiredStop()` | T-030h |
| 10.3 trail never reverses | `src/ExitManager.mqh` | `G3MonotonicStop()` | T-030, T-030b |
| 10.3 timeout (OFF/6/12/18/24) | `src/ExitManager.mqh` | `G3TimeoutShouldClose()` | T-031, T-031b, T-031c, T-031d |
| 10.3 MFE_R / MAE_R | `src/ExitManager.mqh` | `G3RMultiple()`, `G3UpdateExcursions()` | T-049a, T-049b, T-050, T-050b |
| 10.3 result_R | `src/ExitManager.mqh` | `G3ResultR()` | T-049 |
| 12 research CSV log (incl. skipped candidates) | `src/ResearchLogger.mqh` | `G3LogHeader()`, `G3LogRecordToLine()`, `G3LoggerWrite()` | T-047, T-047b, T-047d, T-047e, I-018 test_every_decision_tick_logs_a_row |
| 12 / 7.2 fakeout_3 / fakeout_6 (see DEV-007) | `src/ResearchLogger.mqh` | `G3_UNDEFINED_TOKEN` | T-047c |
| 13.4 / 16 G3 registered inputs (see DEV-005) | `src/G3_ResearchEA.mq5`, `config/*.set` | `input` block | I-019 test_input_surface_matches_registration |
| 13.2 / 13.3 research artifacts and manifests | repository layout | `tools/compute_hashes.py` | I-020 test_manifest_reproducible |
| 11.2 restart safety of exits | `src/StateStore.mqh` | `G3SaveTradeStates()`, `G3LoadTradeStates()`, `G3TradeStateFromLine()` | I-021 test_restart_restores_position_state |
| 13.3 Final Holdout untouched | whole repository | `tools/mql5_static_check.py` forbidden-construct scan | T-STATIC (static check, 0 issues) |

## Cross-instance coordination (implementation detail, not a spec change)

Master Specification v0.4 defines the decision_tick as the first tick of a new
M5 bar, which in MQL5 is only observable for the chart symbol. The EA therefore
runs as one instance per symbol. Portfolio-level rules (section 12) remain
global because:

* open positions are read from the terminal, filtered by magic number
  (`G3BuildOpenSnapshot()`);
* each instance publishes the initial risk of its positions in a terminal
  global variable (`G3RegisterPositionRisk()`), with a recomputation fallback;
* the admission check is serialised across instances with a terminal global
  variable lock (`G3PortfolioLock()` / `G3PortfolioUnlock()`).
