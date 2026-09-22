//+------------------------------------------------------------------+
//| test_main.cpp                                                    |
//|                                                                  |
//| Executable unit tests for the PURE specification logic of the     |
//| G3 Research EA. Compiled with the MQL5 shim so the same source    |
//| files that MetaEditor compiles are exercised here.                |
//|                                                                  |
//| Terminal-bound behaviour (OrderSend, file / global variable I/O,  |
//| account mode guard) is NOT covered here - see tests/integration_  |
//| test_plan.md, which must be executed inside MetaTrader 5.         |
//+------------------------------------------------------------------+
#include "mql5_shim.h"

#include "../../src/G3Types.mqh"
#include "../../src/TimeSync.mqh"
#include "../../src/SignalH4.mqh"
#include "../../src/SetupM15.mqh"
#include "../../src/TriggerM5.mqh"
#include "../../src/MarketFilters.mqh"
#include "../../src/RiskManager.mqh"
#include "../../src/PortfolioManager.mqh"
#include "../../src/OrderManager.mqh"
#include "../../src/ExitManager.mqh"
#include "../../src/StateStore.mqh"
#include "../../src/ResearchLogger.mqh"

static int g_pass=0;
static int g_fail=0;

#define CHECK(id,cond)                                                        \
  do {                                                                        \
    if(cond) { g_pass++; std::printf("PASS  %s\n",id); }                       \
    else     { g_fail++; std::printf("FAIL  %s   (line %d)\n",id,__LINE__); }  \
  } while(0)

static bool Near(double a,double b,double eps=1e-9){ return MathAbs(a-b)<eps; }

static const long H4_SEC =4*3600;
static const long M15_SEC=15*60;
static const long M5_SEC =5*60;

//+------------------------------------------------------------------+
//| 4.1 MTF time synchronisation                                     |
//+------------------------------------------------------------------+
static void test_time_sync()
  {
   //--- T-001 a forming H4 bar is never selected
   LongSeries h4;
   h4.n=5;
   h4.v[0]=100000+4*H4_SEC;   // forming bar (opened, not closed)
   h4.v[1]=100000+3*H4_SEC;
   h4.v[2]=100000+2*H4_SEC;
   h4.v[3]=100000+1*H4_SEC;
   h4.v[4]=100000;
   long signal_close=100000+4*H4_SEC+M5_SEC;   // 5 minutes into the forming bar
   int idx=G3ResolveClosedBarIndex(h4,H4_SEC,signal_close);
   CHECK("T-001 test_no_forming_H4_reference", idx==1);

   //--- exactly at the close boundary the bar counts as closed
   idx=G3ResolveClosedBarIndex(h4,H4_SEC,100000+4*H4_SEC);
   CHECK("T-001b boundary_bar_is_closed", idx==1);

   //--- T-002 weekend gap: the last closed bar may be days old
   LongSeries gap;
   gap.n=3;
   gap.v[0]=1000000+3*24*3600;   // Monday bar, forming
   gap.v[1]=1000000;             // Friday bar
   gap.v[2]=1000000-H4_SEC;
   idx=G3ResolveClosedBarIndex(gap,H4_SEC,1000000+3*24*3600);
   CHECK("T-002 test_h4_reference_weekend_gap", idx==1 && gap.v[idx]==1000000);

   //--- T-003 M15 reference is resolved, not assumed to be shift 1.
   //--- Here the M15 series is missing the most recent bars (stale
   //--- history), so the correct reference is NOT index 1.
   LongSeries m15;
   m15.n=4;
   m15.v[0]=2000000;                 // newest known M15 bar open
   m15.v[1]=2000000-M15_SEC;
   m15.v[2]=2000000-2*M15_SEC;
   m15.v[3]=2000000-3*M15_SEC;
   idx=G3ResolveClosedBarIndex(m15,M15_SEC,2000000+M15_SEC);
   CHECK("T-003 test_m15_reference_is_not_fixed_shift1", idx==0);

   //--- insufficient history behind the reference bar is detected
   CHECK("T-003b test_depth_behind_reference", !G3HasDepthBehind(m15,0,10)
         && G3HasDepthBehind(m15,0,4));

   //--- no closed bar at all
   LongSeries empty;
   empty.n=0;
   CHECK("T-003c test_no_bars_returns_minus_one",
         G3ResolveClosedBarIndex(empty,H4_SEC,123)==-1);

   //--- T-004 signal_id format
   CHECK("T-004 test_signal_id_format",
         G3BuildSignalId("EURUSD",1700000000)==string("EURUSD#1700000000"));
  }

//+------------------------------------------------------------------+
//| 10/11 state store                                                |
//+------------------------------------------------------------------+
static void test_state_store()
  {
   G3State s;
   G3StateInit(s);
   s.peak_equity=10000.0;
   s.dd_state=G3_DD_MODERATE;
   s.hard_stop_latched=false;
   s.daily_start_equity=9800.0;
   s.server_date=1700000000;

   string line=G3StateToLine(s);

   //--- T-006 restart: the persisted line restores the same state
   G3State back;
   G3StateInit(back);
   bool ok=G3ParseStateLine(line,back);
   CHECK("T-006 test_state_roundtrip_after_restart",
         ok && Near(back.peak_equity,10000.0,1e-6)
         && back.dd_state==G3_DD_MODERATE
         && Near(back.daily_start_equity,9800.0,1e-6)
         && back.server_date==1700000000);

   //--- DEV-003: the account record carries no symbol scoped field
   CHECK("R-003a test_account_record_has_no_signal_field",
         StringFind(G3StateToRecord(s),"sigid",0)<0
         && StringFind(G3StateToRecord(s),"sigt",0)<0);

   //--- T-007 a corrupted file record is rejected, never half-loaded
   string corrupt=line;
   corrupt=StringSubstr(corrupt,0,StringLen(corrupt)-3)+"999";
   G3State bad;
   G3StateInit(bad);
   CHECK("T-007 test_corrupt_primary_store_fails_safe",
         !G3ParseStateLine(corrupt,bad));
   CHECK("T-007b test_truncated_record_rejected",
         !G3ParseStateLine("v=2|peak=100",bad));
   CHECK("T-007c test_wrong_schema_version_rejected",
         !G3ParseStateLine("v=99|peak=1.00|dd=0|latch=0|dse=1.00|date=0|chk=0",bad));

   //--- T-008 a tampered global-variable store fails its checksum
   G3State gv=s;
   gv.peak_equity=12000.0;           // value changed without new checksum
   string tampered=G3StateToRecord(gv)+"|chk="+DoubleToString(G3StateChecksum(G3StateToRecord(s)),0);
   CHECK("T-008 test_corrupt_gv_store_checksum",
         !G3ParseStateLine(tampered,bad));

   //--- T-009 both stores lost -> STATE_UNCERTAIN
   G3State out;
   G3State dummy;
   G3StateInit(dummy);
   ENUM_G3_STORE_STATUS st=G3ReconcileStores(false,dummy,false,dummy,true,out);
   CHECK("T-009 test_both_stores_lost_state_uncertain",
         st==G3_STORE_BOTH_LOST && out.dd_state==G3_DD_UNCERTAIN);

   //--- a genuinely fresh install is not STATE_UNCERTAIN
   st=G3ReconcileStores(false,dummy,false,dummy,false,out);
   CHECK("T-009b test_fresh_install_is_not_uncertain",
         st==G3_STORE_FRESH && out.dd_state==G3_DD_NORMAL);

   //--- T-010 mismatch -> the more conservative state is adopted
   G3State a=s;
   a.dd_state=G3_DD_NORMAL;
   a.hard_stop_latched=false;
   a.peak_equity=10000.0;
   a.daily_start_equity=9000.0;
   G3State b=s;
   b.dd_state=G3_DD_RESTRICTED;
   b.hard_stop_latched=true;
   b.peak_equity=11000.0;
   b.daily_start_equity=9500.0;
   st=G3ReconcileStores(true,a,true,b,true,out);
   CHECK("T-010 test_store_mismatch_conservative",
         st==G3_STORE_MISMATCH
         && out.dd_state==G3_DD_RESTRICTED
         && out.hard_stop_latched
         && Near(out.peak_equity,11000.0,1e-6)
         && Near(out.daily_start_equity,9500.0,1e-6));

   //--- identical stores -> STORE_OK
   st=G3ReconcileStores(true,a,true,a,true,out);
   CHECK("T-010b test_stores_agree", st==G3_STORE_OK);

   //--- single store survivors
   st=G3ReconcileStores(true,a,false,dummy,true,out);
   CHECK("T-010c test_file_only", st==G3_STORE_FILE_ONLY && out.dd_state==a.dd_state);
   st=G3ReconcileStores(false,dummy,true,b,true,out);
   CHECK("T-010d test_gv_only", st==G3_STORE_GV_ONLY && out.dd_state==b.dd_state);

   //--- R-006 spec 12 names exactly three status values
   CHECK("R-006 test_store_status_spec_values",
         G3StoreStatusToSpec(G3_STORE_OK)==string("OK")
         && G3StoreStatusToSpec(G3_STORE_FRESH)==string("OK")
         && G3StoreStatusToSpec(G3_STORE_FILE_ONLY)==string("RECOVERED")
         && G3StoreStatusToSpec(G3_STORE_GV_ONLY)==string("RECOVERED")
         && G3StoreStatusToSpec(G3_STORE_MISMATCH)==string("RECOVERED")
         && G3StoreStatusToSpec(G3_STORE_BOTH_LOST)==string("UNCERTAIN"));
  }

//+------------------------------------------------------------------+
//| 4.1 per-symbol signal ledger (DEV-003)                           |
//+------------------------------------------------------------------+
static void test_signal_ledger()
  {
   G3SignalState s;
   G3SignalStateInit(s);
   s.last_signal_time=1700003000;
   s.last_signal_id="EURUSD#1700003000";

   G3SignalState back;
   G3SignalStateInit(back);
   CHECK("R-003b test_signal_ledger_roundtrip",
         G3ParseSignalStateLine(G3SignalStateToLine(s),back)
         && back.last_signal_time==1700003000
         && back.last_signal_id==string("EURUSD#1700003000"));

   G3SignalState bad;
   G3SignalStateInit(bad);
   CHECK("R-003c test_signal_ledger_corrupt_rejected",
         !G3ParseSignalStateLine("v=2|sigt=1|sigid=X|chk=1",bad));

   //--- conservative merge never re-arms an older signal
   G3SignalState older;
   G3SignalStateInit(older);
   older.last_signal_time=1700002700;
   older.last_signal_id="EURUSD#1700002700";
   G3SignalState merged=G3MergeSignalConservative(older,s);
   CHECK("R-003d test_signal_ledger_merge_takes_later",
         merged.last_signal_time==1700003000
         && merged.last_signal_id==string("EURUSD#1700003000"));
   merged=G3MergeSignalConservative(s,older);
   CHECK("R-003e test_signal_ledger_merge_keeps_later",
         merged.last_signal_time==1700003000);

   G3SignalState out;
   ENUM_G3_STORE_STATUS st=G3ReconcileSignalStores(true,older,true,s,true,out);
   CHECK("R-003f test_signal_store_mismatch_conservative",
         st==G3_STORE_MISMATCH && out.last_signal_time==1700003000);
   st=G3ReconcileSignalStores(false,older,false,s,false,out);
   CHECK("R-003g test_signal_store_fresh",
         st==G3_STORE_FRESH && out.last_signal_time==0);

   //--- T-005 duplicate signal_id is refused (fail closed)
   CHECK("T-005 test_signal_id_duplicate_rejected",
         G3SignalAlreadyConsumed(s,"EURUSD#1700003000",1700003000));
   CHECK("T-005b test_older_signal_rejected",
         G3SignalAlreadyConsumed(s,"EURUSD#1700002700",1700002700));
   CHECK("T-005c test_new_signal_accepted",
         !G3SignalAlreadyConsumed(s,"EURUSD#1700003300",1700003300));
  }

//+------------------------------------------------------------------+
//| 10 drawdown state machine                                        |
//+------------------------------------------------------------------+
static void test_dd_state_machine()
  {
   bool latched=false;

   //--- T-011 6% boundary: NORMAL -> MODERATE at exactly 6.0
   CHECK("T-011 test_dd_boundary_6pct_below",
         G3NextDDState(G3_DD_NORMAL,5.999,latched)==G3_DD_NORMAL);
   CHECK("T-011b test_dd_boundary_6pct_at",
         G3NextDDState(G3_DD_NORMAL,6.0,latched)==G3_DD_MODERATE);

   //--- T-012 8% boundary
   CHECK("T-012 test_dd_boundary_8pct_below",
         G3NextDDState(G3_DD_MODERATE,7.999,latched)==G3_DD_MODERATE);
   CHECK("T-012b test_dd_boundary_8pct_at",
         G3NextDDState(G3_DD_MODERATE,8.0,latched)==G3_DD_RESTRICTED);

   //--- T-013 10% latches HARD_STOP
   latched=false;
   ENUM_G3_DD_STATE st=G3NextDDState(G3_DD_RESTRICTED,10.0,latched);
   CHECK("T-013 test_dd_boundary_10pct_latch", st==G3_DD_HARD_STOP && latched);

   //--- T-015 the latch is never released automatically
   CHECK("T-015 test_hard_stop_latch_not_auto_released",
         G3NextDDState(G3_DD_HARD_STOP,0.0,latched)==G3_DD_HARD_STOP && latched);

   //--- T-014 recovery hysteresis
   latched=false;
   CHECK("T-014 test_restricted_holds_above_7",
         G3NextDDState(G3_DD_RESTRICTED,7.0,latched)==G3_DD_RESTRICTED);
   CHECK("T-014b test_restricted_to_moderate_below_7",
         G3NextDDState(G3_DD_RESTRICTED,6.999,latched)==G3_DD_MODERATE);
   CHECK("T-014c test_moderate_holds_above_5",
         G3NextDDState(G3_DD_MODERATE,5.0,latched)==G3_DD_MODERATE);
   CHECK("T-014d test_moderate_to_normal_below_5",
         G3NextDDState(G3_DD_MODERATE,4.999,latched)==G3_DD_NORMAL);

   //--- STATE_UNCERTAIN is absorbing
   CHECK("T-014e test_uncertain_is_absorbing",
         G3NextDDState(G3_DD_UNCERTAIN,0.0,latched)==G3_DD_UNCERTAIN);

   //--- risk percentages per state
   CHECK("T-014f test_risk_pct_per_state",
         Near(G3RiskPctForState(G3_DD_NORMAL),0.50)
         && Near(G3RiskPctForState(G3_DD_MODERATE),0.25)
         && Near(G3RiskPctForState(G3_DD_RESTRICTED),0.10)
         && Near(G3RiskPctForState(G3_DD_HARD_STOP),0.0)
         && Near(G3RiskPctForState(G3_DD_UNCERTAIN),0.0));

   //--- drawdown arithmetic
   CHECK("T-014g test_drawdown_pct",
         Near(G3DrawdownPct(10000.0,9400.0),6.0,1e-9)
         && Near(G3DrawdownPct(10000.0,10500.0),0.0));

   //--- T-016 manual reset admissibility
   CHECK("T-016 test_manual_reset_requires_dd_below_9",
         G3ManualResetAdmissible(8.999) && !G3ManualResetAdmissible(9.0));

   //--- T-017 DailyEntryLock at -2% of the daily start equity
   CHECK("T-017 test_daily_entry_lock",
         !G3DailyEntryLocked(10000.0,9801.0)
         && G3DailyEntryLocked(10000.0,9800.0)
         && G3DailyEntryLocked(10000.0,9700.0));
  }

//+------------------------------------------------------------------+
//| 9 stops, risk and lot sizing                                     |
//+------------------------------------------------------------------+
static void test_risk_and_lots()
  {
   const double atr=0.0010;

   //--- raw stop placement
   double raw_buy=G3RawStop(G3_SIDE_BUY,1.09500,1.09800,atr);
   CHECK("T-024a test_raw_stop_buy", Near(raw_buy,1.09500-0.0002,1e-12));
   double raw_sell=G3RawStop(G3_SIDE_SELL,1.09500,1.09800,atr);
   CHECK("T-024b test_raw_stop_sell", Near(raw_sell,1.09800+0.0002,1e-12));

   //--- T-024 a stop closer than 1.0 ATR is widened to exactly 1.0 ATR
   double sl=0.0;
   bool adj=false;
   ENUM_G3_REASON why=G3_R_NONE;
   bool ok=G3AdjustStopStrategy(G3_SIDE_BUY,1.10000,1.09950,atr,sl,adj,why);
   CHECK("T-024 test_sl_min_1atr_expansion",
         ok && adj && Near(sl,1.10000-atr,1e-12));

   //--- a stop inside the band is untouched
   ok=G3AdjustStopStrategy(G3_SIDE_BUY,1.10000,1.09850,atr,sl,adj,why);
   CHECK("T-024c test_sl_in_band_untouched",
         ok && !adj && Near(sl,1.09850,1e-12));

   //--- T-025 beyond 2.5 ATR the entry is rejected
   ok=G3AdjustStopStrategy(G3_SIDE_BUY,1.10000,1.09700,atr,sl,adj,why);
   CHECK("T-025 test_sl_max_2_5atr_reject",
         !ok && why==G3_R_SL_DISTANCE_ABOVE_MAX);

   //--- exactly 2.5 ATR is still admissible
   ok=G3AdjustStopStrategy(G3_SIDE_BUY,1.10000,1.10000-2.5*atr,atr,sl,adj,why);
   CHECK("T-025b test_sl_exactly_2_5atr_ok", ok);

   //--- T-023 broker stop level pushes the stop to the safer side
   double sl_final=0.0;
   bool badj=false;
   //--- strategy stop 15 points away, StopsLevel = 30 points
   ok=G3AdjustStopBroker(G3_SIDE_BUY,1.10000,1.09985,atr,1.09995,30,0.00001,
                         sl_final,badj,why);
   CHECK("T-023 test_stop_level_adjustment",
         ok && badj && Near(sl_final,1.09995-31*0.00001,1e-12));

   //--- a stop already outside the stop level is not moved
   ok=G3AdjustStopBroker(G3_SIDE_BUY,1.10000,1.09900,atr,1.09995,30,0.00001,
                         sl_final,badj,why);
   CHECK("T-023b test_stop_level_no_change", ok && !badj && Near(sl_final,1.09900,1e-12));

   //--- T-026 if the broker correction breaks the 2.5 ATR ceiling -> reject
   ok=G3AdjustStopBroker(G3_SIDE_BUY,1.10000,1.09980,atr,1.09995,400,0.00001,
                         sl_final,badj,why);
   CHECK("T-026 test_sl_broker_adjust_above_max_reject",
         !ok && why==G3_R_SL_BROKER_ADJ_ABOVE_MAX);

   //--- T-018 lot sizing floors onto the volume step
   double raw_lot=0.0,final_lot=0.0;
   bool capped=false;
   //--- risk 50 money units, 1 lot loses 100 -> 0.5 lot, step 0.03 -> 0.48
   ok=G3ComputeLot(50.0,100.0,0.03,0.01,100.0,raw_lot,final_lot,capped,why);
   CHECK("T-018 test_lot_floor_to_volume_step",
         ok && Near(raw_lot,0.5,1e-12) && Near(final_lot,0.48,1e-9));

   //--- standard 0.01 step never rounds up
   ok=G3ComputeLot(19.9,100.0,0.01,0.01,100.0,raw_lot,final_lot,capped,why);
   CHECK("T-018b test_lot_floor_no_round_up",
         ok && Near(final_lot,0.19,1e-9));

   //--- T-019 the minimum volume already exceeds RiskMoney -> refuse
   ok=G3ComputeLot(0.5,100.0,0.01,0.01,100.0,raw_lot,final_lot,capped,why);
   CHECK("T-019 test_lot_below_volume_min_rejected",
         !ok && why==G3_R_RISK_MONEY_EXCEEDED_AT_MIN_VOLUME && Near(final_lot,0.0));

   //--- broker volume ceiling
   ok=G3ComputeLot(100000.0,100.0,0.01,0.01,5.0,raw_lot,final_lot,capped,why);
   CHECK("T-018c test_lot_capped_by_volume_max",
         ok && capped && Near(final_lot,5.0,1e-9));

   //--- invalid OrderCalcProfit result
   ok=G3ComputeLot(100.0,0.0,0.01,0.01,5.0,raw_lot,final_lot,capped,why);
   CHECK("T-018d test_order_calc_profit_invalid",
         !ok && why==G3_R_ORDER_CALC_PROFIT_INVALID);

   //--- T-027 post-fill risk over 105% is detected and can be resized
   double ratio=G3PostFillRiskRatio(110.0,1.0,100.0);
   CHECK("T-027 test_post_fill_risk_105_detected", Near(ratio,1.10,1e-12));
   CHECK("T-027b test_post_fill_risk_within_tolerance",
         G3PostFillRiskRatio(104.0,1.0,100.0)<=G3_POST_FILL_RISK_MAX);
   double allowed=G3RiskCappedVolume(110.0,100.0,0.01);
   CHECK("T-027c test_risk_capped_volume", Near(allowed,0.95,1e-9));
  }

//+------------------------------------------------------------------+
//| 13 deviation                                                     |
//+------------------------------------------------------------------+
static void test_deviation()
  {
   //--- T-020 PipSize for 3/5 digit and 2/4 digit symbols
   CHECK("T-020 test_pip_size_5_digits", Near(G3PipSize(5,0.00001),0.0001,1e-12));
   CHECK("T-020b test_pip_size_3_digits_jpy", Near(G3PipSize(3,0.001),0.01,1e-12));
   CHECK("T-020c test_pip_size_4_digits", Near(G3PipSize(4,0.0001),0.0001,1e-12));
   CHECK("T-020d test_pip_size_2_digits_jpy", Near(G3PipSize(2,0.01),0.01,1e-12));

   //--- T-021 hard cap is 2.0 pips expressed in points
   CHECK("T-021 test_deviation_hard_cap_5_digits",
         G3DeviationHardCapPoints(5,0.00001)==20);
   CHECK("T-021b test_deviation_hard_cap_3_digits",
         G3DeviationHardCapPoints(3,0.001)==20);
   CHECK("T-021c test_deviation_hard_cap_4_digits",
         G3DeviationHardCapPoints(4,0.0001)==2);

   //--- spread is the binding term: 1.2 pips spread, wide ATR
   DeviationPlan p=G3BuildDeviationPlan(0.00012,0.0010,5,0.00001);
   CHECK("T-021d test_deviation_uses_min_of_spread_and_atr",
         p.computed_points==5 && p.send_allowed && p.send_points==5 && !p.cap_hit);

   //--- ATR is the binding term
   p=G3BuildDeviationPlan(0.00050,0.00040,5,0.00001);
   CHECK("T-021e test_deviation_atr_term", p.computed_points==2 && p.send_points==2);

   //--- the floor never sends 0
   p=G3BuildDeviationPlan(0.000005,0.0010,5,0.00001);
   CHECK("T-021f test_deviation_minimum_one_point",
         p.computed_points==0 && p.send_allowed && p.send_points==1);

   //--- T-022 computed above the hard cap blocks the order entirely
   p=G3BuildDeviationPlan(0.00300,0.10000,5,0.00001);
   CHECK("T-022 test_deviation_cap_exceeded_blocks_send",
         p.cap_hit && !p.send_allowed && p.computed_points>p.hard_cap_points);
  }

//+------------------------------------------------------------------+
//| 14/15 exits                                                      |
//+------------------------------------------------------------------+
static void test_exits()
  {
   //--- T-048 exit mode A take profit is exactly 2.0R, B and C have none
   CHECK("T-048 test_exit_a_tp_2r",
         Near(G3InitialTakeProfit(G3_EXIT_A,G3_SIDE_BUY,1.10000,0.0010),1.10200,1e-12));
   CHECK("T-048b test_exit_a_tp_2r_sell",
         Near(G3InitialTakeProfit(G3_EXIT_A,G3_SIDE_SELL,1.10000,0.0010),1.09800,1e-12));
   CHECK("T-048c test_exit_b_c_no_fixed_tp",
         Near(G3InitialTakeProfit(G3_EXIT_B,G3_SIDE_BUY,1.1,0.001),0.0)
         && Near(G3InitialTakeProfit(G3_EXIT_C,G3_SIDE_BUY,1.1,0.001),0.0));

   //--- R multiples
   CHECK("T-049a test_r_multiple_buy",
         Near(G3RMultiple(G3_SIDE_BUY,1.10150,1.10000,0.0010),1.5,1e-9));
   CHECK("T-049b test_r_multiple_sell",
         Near(G3RMultiple(G3_SIDE_SELL,1.09850,1.10000,0.0010),1.5,1e-9));

   //--- T-049 result_R is realised P/L over the initial RiskMoney
   CHECK("T-049 test_result_r_definition",
         Near(G3ResultR(150.0,100.0),1.5,1e-12) && Near(G3ResultR(150.0,0.0),0.0));

   //--- T-028 a 0.01 lot position cannot be partially closed
   PartialPlan pp=G3BuildPartialPlan(0.01,0.01,0.01);
   CHECK("T-028 test_partial_impossible_min_volume", !pp.valid);

   //--- T-029 partial ratio boundary behaviour
   pp=G3BuildPartialPlan(0.02,0.01,0.01);
   CHECK("T-029 test_partial_exact_50pct",
         pp.valid && Near(pp.close_volume,0.01,1e-9)
         && Near(pp.remaining_volume,0.01,1e-9) && Near(pp.close_ratio,0.5,1e-9));

   //--- 0.03 lots -> floor(0.015)=0.01 -> ratio 0.3333 -> outside 40..60%
   pp=G3BuildPartialPlan(0.03,0.01,0.01);
   CHECK("T-029b test_partial_ratio_below_40pct_skipped", !pp.valid);

   //--- 0.05 lots -> 0.02 closed -> ratio 0.40 -> admissible boundary
   pp=G3BuildPartialPlan(0.05,0.01,0.01);
   CHECK("T-029c test_partial_ratio_at_40pct_boundary",
         pp.valid && Near(pp.close_ratio,0.4,1e-9));

   //--- 1.00 lot with a 0.5 step -> exactly 50%
   pp=G3BuildPartialPlan(1.00,0.50,0.50);
   CHECK("T-029d test_partial_coarse_step", pp.valid && Near(pp.close_volume,0.5,1e-9));

   //--- T-030 a trail never moves against the position
   CHECK("T-030 test_trail_never_reverses_buy",
         Near(G3MonotonicStop(G3_SIDE_BUY,1.10500,1.10400),1.10500,1e-12)
         && Near(G3MonotonicStop(G3_SIDE_BUY,1.10500,1.10600),1.10600,1e-12));
   CHECK("T-030b test_trail_never_reverses_sell",
         Near(G3MonotonicStop(G3_SIDE_SELL,1.09500,1.09600),1.09500,1e-12)
         && Near(G3MonotonicStop(G3_SIDE_SELL,1.09500,1.09400),1.09400,1e-12));

   //--- ATR trail anchors
   CHECK("T-030c test_atr_trail_distance",
         Near(G3AtrTrailStop(G3_SIDE_BUY,1.10500,0.0010,2.0),1.10300,1e-12)
         && Near(G3AtrTrailStop(G3_SIDE_SELL,1.09500,0.0010,2.5),1.09750,1e-12));

   //--- cost adjusted break even sits beyond the entry, never at it
   CHECK("T-030d test_cost_adjusted_breakeven",
         Near(G3BreakevenPrice(G3_SIDE_BUY,1.10000,0.00002),1.10002,1e-12)
         && Near(G3BreakevenPrice(G3_SIDE_SELL,1.10000,0.00002),1.09998,1e-12));

   //--- exit mode A must never move the stop
   G3TradeState t;
   t.active=true; t.ticket=1; t.symbol="EURUSD"; t.signal_id="x";
   t.side=G3_SIDE_BUY; t.entry_time=0; t.entry_m5_bar=0;
   t.entry_price=1.10000; t.initial_sl=1.09900; t.initial_tp=1.10200;
   t.initial_volume=0.10; t.current_volume=0.10;
   t.initial_risk_money=100.0; t.initial_risk_pct=0.5;
   t.r_distance=0.0010; t.atr_at_entry=0.0010;
   t.mfe_r=3.0; t.mae_r=0.0;
   t.mfe_r_3bars=0.0; t.mae_r_3bars=0.0; t.mfe_r_6bars=0.0; t.mae_r_6bars=0.0;
   t.trail_stop=0.0; t.extreme_price=1.10300; t.realized_pl=0.0;
   t.partial_closed_volume=0.0; t.bars_held=5;
   t.be_done=false; t.partial_done=false; t.partial_skipped=false;
   CHECK("T-030e test_exit_a_stop_is_fixed",
         Near(G3DesiredStop(G3_EXIT_A,t,0.0010,0.00002),1.09900,1e-12));

   //--- exit mode B moves to cost adjusted break even past 1.0R
   G3TradeState b=t;
   b.mfe_r=1.2;
   b.extreme_price=1.10120;
   CHECK("T-030f test_exit_b_breakeven_after_1r",
         Near(G3DesiredStop(G3_EXIT_B,b,0.0010,0.00002),1.10002,1e-12));

   //--- exit mode B trails only once the partial is done or skipped
   b.partial_done=true;
   b.extreme_price=1.10500;
   b.trail_stop=1.10002;
   CHECK("T-030g test_exit_b_trail_after_partial",
         Near(G3DesiredStop(G3_EXIT_B,b,0.0010,0.00002),1.10300,1e-12));

   //--- exit mode C chandelier trail at 2.5 ATR
   G3TradeState c=t;
   c.trail_stop=0.0;
   c.extreme_price=1.10500;
   CHECK("T-030h test_exit_c_chandelier",
         Near(G3DesiredStop(G3_EXIT_C,c,0.0010,0.0),1.10250,1e-12));

   //--- T-031 timeout only closes positions whose MFE stayed below 0.75R
   CHECK("T-031 test_timeout_off", !G3TimeoutShouldClose(G3_TIMEOUT_OFF,100,0.0));
   CHECK("T-031b test_timeout_not_reached",
         !G3TimeoutShouldClose(G3_TIMEOUT_12,11,0.0));
   CHECK("T-031c test_timeout_closes_low_mfe",
         G3TimeoutShouldClose(G3_TIMEOUT_12,12,0.74));
   CHECK("T-031d test_timeout_keeps_high_mfe",
         !G3TimeoutShouldClose(G3_TIMEOUT_12,12,0.75));

   //--- T-050 excursion tracking
   G3TradeState e=t;
   e.mfe_r=0.0; e.mae_r=0.0; e.bars_held=1;
   e.mfe_r_3bars=0.0; e.mae_r_3bars=0.0; e.mfe_r_6bars=0.0; e.mae_r_6bars=0.0;
   e.extreme_price=e.entry_price;
   G3UpdateExcursions(e,1.10200,1.09950);
   bool early=Near(e.mfe_r,2.0,1e-9) && Near(e.mae_r,-0.5,1e-9)
              && Near(e.mfe_r_3bars,2.0,1e-9) && Near(e.mfe_r_6bars,2.0,1e-9);
   e.bars_held=8;
   G3UpdateExcursions(e,1.10400,1.09900);
   bool late=Near(e.mfe_r,4.0,1e-9) && Near(e.mae_r,-1.0,1e-9)
             && Near(e.mfe_r_3bars,2.0,1e-9) && Near(e.mfe_r_6bars,2.0,1e-9);
   CHECK("T-050 test_mfe_mae_tracking", early && late);
   CHECK("T-050b test_extreme_price_monotonic", Near(e.extreme_price,1.10400,1e-12));
  }

//+------------------------------------------------------------------+
//| 12 portfolio                                                     |
//+------------------------------------------------------------------+
static void ClearCorr(CorrMatrix &c,const int n,const bool ready)
  {
   c.n=n;
   c.ready=ready;
   c.warmup_days=ready?60:10;
   for(int i=0;i<G3_MAX_LEGS*G3_MAX_LEGS;i++)
      c.m[i]=0.0;
   for(int i=0;i<n;i++)
      G3CorrSet(c,i,i,1.0);
  }

static void test_portfolio()
  {
   //--- currency component helpers
   CHECK("T-034a test_currency_components",
         G3BaseCurrency("EURUSD")==string("EUR")
         && G3QuoteCurrency("EURUSD")==string("USD")
         && G3BaseCurrency("EURUSD.m")==string("EUR"));

   //--- T-034 same currency component, same direction, limit 1.00%
   PortfolioSnapshot s;
   s.n=0;
   s.leg[0].symbol="EURUSD"; s.leg[0].side=G3_SIDE_BUY; s.leg[0].initial_risk_pct=0.50;
   s.leg[1].symbol="EURJPY"; s.leg[1].side=G3_SIDE_BUY; s.leg[1].initial_risk_pct=0.50;
   s.leg[2].symbol="EURGBP"; s.leg[2].side=G3_SIDE_BUY; s.leg[2].initial_risk_pct=0.50;
   s.n=3;
   CHECK("T-034 test_currency_exposure_same_direction",
         Near(G3CurrencyRiskPct(s,"EUR",1),1.50,1e-9));
   //--- a short EURUSD is short EUR, so it does not add to the long EUR side
   PortfolioSnapshot o;
   o.leg[0]=s.leg[0];
   o.leg[1].symbol="EURUSD"; o.leg[1].side=G3_SIDE_SELL; o.leg[1].initial_risk_pct=0.50;
   o.n=2;
   CHECK("T-034b test_currency_exposure_opposite_direction",
         Near(G3CurrencyRiskPct(o,"EUR",1),0.50,1e-9)
         && Near(G3CurrencyRiskPct(o,"EUR",-1),0.50,1e-9));
   //--- USD quote exposure of a long EURUSD is short USD
   CHECK("T-034c test_quote_currency_direction",
         Near(G3CurrencyRiskPct(s,"USD",-1),0.50,1e-9));

   CorrMatrix c;
   ClearCorr(c,3,true);
   PortfolioDecision d=G3CheckPortfolio(s,c,2);
   CHECK("T-034d test_currency_limit_blocks", !d.accepted
         && d.reason==G3_R_CURRENCY_EXPOSURE);

   //--- T-035 MaxPositions = 3
   PortfolioSnapshot full;
   full.leg[0].symbol="EURUSD"; full.leg[0].side=G3_SIDE_BUY; full.leg[0].initial_risk_pct=0.10;
   full.leg[1].symbol="GBPJPY"; full.leg[1].side=G3_SIDE_BUY; full.leg[1].initial_risk_pct=0.10;
   full.leg[2].symbol="AUDCAD"; full.leg[2].side=G3_SIDE_BUY; full.leg[2].initial_risk_pct=0.10;
   full.leg[3].symbol="NZDCHF"; full.leg[3].side=G3_SIDE_BUY; full.leg[3].initial_risk_pct=0.10;
   full.n=4;
   ClearCorr(c,4,true);
   d=G3CheckPortfolio(full,c,3);
   CHECK("T-035 test_max_positions", !d.accepted && d.reason==G3_R_MAX_POSITIONS
         && d.open_positions==3);

   //--- T-036 MaxTotalInitialRisk = 1.50%
   PortfolioSnapshot big;
   big.leg[0].symbol="EURUSD"; big.leg[0].side=G3_SIDE_BUY; big.leg[0].initial_risk_pct=0.70;
   big.leg[1].symbol="GBPJPY"; big.leg[1].side=G3_SIDE_BUY; big.leg[1].initial_risk_pct=0.70;
   big.leg[2].symbol="AUDCAD"; big.leg[2].side=G3_SIDE_BUY; big.leg[2].initial_risk_pct=0.20;
   big.n=3;
   ClearCorr(c,3,true);
   d=G3CheckPortfolio(big,c,2);
   CHECK("T-036 test_max_total_risk", !d.accepted && d.reason==G3_R_MAX_TOTAL_RISK);

   //--- T-032 correlation cluster limit 1.00%
   PortfolioSnapshot cl;
   cl.leg[0].symbol="EURUSD"; cl.leg[0].side=G3_SIDE_BUY; cl.leg[0].initial_risk_pct=0.50;
   cl.leg[1].symbol="AUDCAD"; cl.leg[1].side=G3_SIDE_BUY; cl.leg[1].initial_risk_pct=0.50;
   cl.leg[2].symbol="NZDCHF"; cl.leg[2].side=G3_SIDE_BUY; cl.leg[2].initial_risk_pct=0.40;
   cl.n=3;
   ClearCorr(c,3,true);
   G3CorrSet(c,0,1,0.85);
   G3CorrSet(c,0,2,0.75);
   d=G3CheckPortfolio(cl,c,2);
   CHECK("T-032 test_correlation_cluster_blocks",
         !d.accepted && d.reason==G3_R_CORR_CLUSTER_RISK
         && Near(d.corr_cluster_risk_pct,1.40,1e-9)
         && d.corr_state==G3_CORR_READY);

   //--- below the 0.70 threshold there is no cluster
   ClearCorr(c,3,true);
   G3CorrSet(c,0,1,0.69);
   G3CorrSet(c,0,2,0.10);
   G3CorrSet(c,1,2,0.10);
   d=G3CheckPortfolio(cl,c,2);
   CHECK("T-032b test_correlation_below_threshold_no_cluster",
         d.accepted && Near(d.corr_cluster_risk_pct,0.40,1e-9));

   //--- direction adjusted signed correlation: opposite sides do not cluster
   PortfolioSnapshot opp=cl;
   opp.leg[1].side=G3_SIDE_SELL;
   ClearCorr(c,3,true);
   G3CorrSet(c,0,1,0.95);
   G3CorrSet(c,0,2,0.10);
   G3CorrSet(c,1,2,0.10);
   d=G3CheckPortfolio(opp,c,2);
   CHECK("T-032c test_signed_correlation_direction_adjusted",
         d.accepted && Near(d.corr_cluster_risk_pct,0.40,1e-9));

   //--- T-033 warm-up: correlation is never treated as zero
   PortfolioSnapshot w;
   w.leg[0].symbol="EURUSD"; w.leg[0].side=G3_SIDE_BUY; w.leg[0].initial_risk_pct=0.50;
   w.leg[1].symbol="AUDCAD"; w.leg[1].side=G3_SIDE_BUY; w.leg[1].initial_risk_pct=0.50;
   w.n=2;
   ClearCorr(c,2,false);
   d=G3CheckPortfolio(w,c,1);
   CHECK("T-033 test_corr_warmup_unknown_blocks",
         !d.accepted && d.reason==G3_R_UNKNOWN_CLUSTER_RISK
         && d.corr_state==G3_CORR_WARMUP_UNKNOWN
         && Near(d.unknown_cluster_risk_pct,1.00,1e-9));

   //--- within the unknown cluster budget the entry is admitted
   w.leg[0].initial_risk_pct=0.50;
   w.leg[1].initial_risk_pct=0.25;
   ClearCorr(c,2,false);
   d=G3CheckPortfolio(w,c,1);
   CHECK("T-033b test_corr_warmup_within_budget",
         d.accepted && Near(d.unknown_cluster_risk_pct,0.75,1e-9)
         && d.corr_warmup_days==10);

   //--- Pearson correlation itself
   DoubleSeries a,b;
   a.n=5; b.n=5;
   for(int i=0;i<5;i++)
     {
      a.v[i]=(double)i;
      b.v[i]=2.0*(double)i+1.0;
     }
   double r=0.0;
   CHECK("T-032d test_pearson_perfect_positive",
         G3Pearson(a,b,r) && Near(r,1.0,1e-12));
   for(int i=0;i<5;i++)
      b.v[i]=-3.0*(double)i;
   CHECK("T-032e test_pearson_perfect_negative",
         G3Pearson(a,b,r) && Near(r,-1.0,1e-12));
   DoubleSeries flat;
   flat.n=5;
   for(int i=0;i<5;i++)
      flat.v[i]=1.0;
   CHECK("T-032f test_pearson_zero_variance_undefined", !G3Pearson(a,flat,r));
  }

//+------------------------------------------------------------------+
//| 5/6/7/8 signal logic                                             |
//+------------------------------------------------------------------+
static void test_signal_logic()
  {
   //--- T-037 H4 direction gate
   H4Input h;
   h.close_ref=1.1050; h.ema50_ref=1.1040; h.ema50_ref_minus3=1.1020;
   h.ema200_ref=1.1000; h.atr14_ref=0.0010;
   h.adx14_ref=25.0; h.plus_di_ref=30.0; h.minus_di_ref=10.0;
   CHECK("T-037 test_h4_direction_gate_buy",
         G3H4DirectionGate(h,G3_SIDE_BUY) && !G3H4DirectionGate(h,G3_SIDE_SELL)
         && G3H4Direction(h)==G3_SIDE_BUY);
   //--- close below EMA200 breaks the gate even with EMA50 above
   H4Input h2=h;
   h2.close_ref=1.0990;
   CHECK("T-037b test_h4_gate_requires_close_and_ema",
         !G3H4DirectionGate(h2,G3_SIDE_BUY) && G3H4Direction(h2)==G3_SIDE_NONE);

   //--- T-038 slope and ADX components
   double slope=0.0;
   G3H4SlopeValue(h,slope);
   CHECK("T-038 test_h4_slope_value", Near(slope,2.0,1e-9));
   bool f1=false,f2=false;
   CHECK("T-038b test_h4_score_two_points", G3H4Score(h,G3_SIDE_BUY,f1,f2)==2 && f1 && f2);
   //--- slope exactly at +0.10 does not score (strictly greater)
   H4Input flat=h;
   flat.ema50_ref_minus3=h.ema50_ref-0.10*h.atr14_ref;
   CHECK("T-038c test_h4_slope_boundary_excluded",
         !G3H4SlopeFlag(flat,G3_SIDE_BUY));
   //--- ADX exactly 20 scores, 19.99 does not
   H4Input adx=h;
   adx.adx14_ref=20.0;
   CHECK("T-038d test_h4_adx_boundary_included", G3H4AdxFlag(adx,G3_SIDE_BUY));
   adx.adx14_ref=19.99;
   CHECK("T-038e test_h4_adx_boundary_excluded", !G3H4AdxFlag(adx,G3_SIDE_BUY));
   //--- DI must agree with the side
   H4Input di=h;
   di.plus_di_ref=10.0; di.minus_di_ref=30.0;
   CHECK("T-038f test_h4_adx_di_direction", !G3H4AdxFlag(di,G3_SIDE_BUY)
         && G3H4AdxFlag(di,G3_SIDE_SELL));
   //--- zero ATR cannot produce a slope point
   H4Input za=h;
   za.atr14_ref=0.0;
   CHECK("T-038g test_h4_slope_zero_atr", !G3H4SlopeFlag(za,G3_SIDE_BUY));

   //--- T-039 M15 pullback and structure
   M15Input m;
   m.low[0]=1.1000; m.low[1]=1.0995; m.low[2]=1.0990;
   m.high[0]=1.1030; m.high[1]=1.1025; m.high[2]=1.1020;
   m.ema20[0]=1.1005; m.ema20[1]=1.1002; m.ema20[2]=1.1000;
   m.close_s1=1.1020; m.ema20_s1=1.1005; m.ema20_s4=1.0990; m.ema50_s1=1.1000;
   m.atr14[0]=0.0010; m.atr14[1]=0.0010; m.atr14[2]=0.0010;
   bool p=false,st=false;
   CHECK("T-039 test_m15_score_two_points", G3M15Score(m,G3_SIDE_BUY,p,st)==2 && p && st);
   //--- only shifts 1..3 are inspected: move every low far above the band
   M15Input far=m;
   far.low[0]=1.1025; far.low[1]=1.1024; far.low[2]=1.1023;
   CHECK("T-039b test_m15_pullback_window_limited",
         !G3M15PullbackFlag(far,G3_SIDE_BUY));
   //--- close below EMA20 invalidates a BUY pullback
   M15Input cb=m;
   cb.close_s1=1.1000;
   CHECK("T-039c test_m15_pullback_needs_close_above_ema",
         !G3M15PullbackFlag(cb,G3_SIDE_BUY));
   //--- structure requires both EMA relations
   M15Input sb=m;
   sb.ema50_s1=1.1010;
   CHECK("T-039d test_m15_structure_requires_ema50",
         !G3M15StructureFlag(sb,G3_SIDE_BUY));
   //--- the 0.20 ATR band boundary is inclusive
   M15Input band=m;
   band.low[0]=band.ema20[0]+0.20*band.atr14[0];
   band.low[1]=1.1100; band.low[2]=1.1100;
   CHECK("T-039e test_m15_pullback_band_inclusive",
         G3M15PullbackFlag(band,G3_SIDE_BUY));

   //--- T-040 M5 breakout hard gate
   M5Input t;
   t.open_s1=1.1000; t.high_s1=1.1030; t.low_s1=1.0998; t.close_s1=1.1028;
   t.highest_2_6=1.1020; t.lowest_2_6=1.0990;
   t.ema9_s1=1.1015; t.ema9_s4=1.1005; t.ema20_s1=1.1010;
   CHECK("T-040 test_m5_breakout_hard_gate",
         G3M5BreakoutFlag(t,G3_SIDE_BUY) && !G3M5BreakoutFlag(t,G3_SIDE_SELL));
   //--- equality is not a breakout
   M5Input eq=t;
   eq.close_s1=eq.highest_2_6;
   CHECK("T-040b test_m5_breakout_strict", !G3M5BreakoutFlag(eq,G3_SIDE_BUY));

   //--- T-041 candle and momentum
   bool cq=false,mo=false;
   CHECK("T-041 test_m5_score_two_points", G3M5Score(t,G3_SIDE_BUY,cq,mo)==2 && cq && mo);
   //--- body ratio below 0.60 scores nothing
   M5Input weak=t;
   weak.open_s1=1.1025;
   CHECK("T-041b test_m5_body_ratio", !G3M5CandleFlag(weak,G3_SIDE_BUY));
   //--- close outside the leading 25% of the range scores nothing
   M5Input tail=t;
   tail.open_s1=1.0999; tail.close_s1=1.1018; tail.high_s1=1.1030; tail.low_s1=1.0998;
   CHECK("T-041c test_m5_close_position", !G3M5CandleFlag(tail,G3_SIDE_BUY));
   //--- zero range candle is rejected, never divided by zero
   M5Input zero=t;
   zero.high_s1=1.1000; zero.low_s1=1.1000; zero.open_s1=1.1000; zero.close_s1=1.1000;
   CHECK("T-041d test_m5_zero_range", !G3M5CandleFlag(zero,G3_SIDE_BUY));
   //--- momentum requires both EMA relations
   M5Input mm=t;
   mm.ema9_s4=1.1020;
   CHECK("T-041e test_m5_momentum_slope", !G3M5MomentumFlag(mm,G3_SIDE_BUY));

   //--- T-042 volatility ratio and block
   DoubleSeries atr;
   atr.n=100;
   for(int i=0;i<100;i++)
      atr.v[i]=0.0010;
   double vr=0.0;
   CHECK("T-042 test_vol_ratio", G3VolRatio(0.0012,atr,vr) && Near(vr,1.2,1e-9));
   CHECK("T-042b test_vol_score_band",
         G3VolScore(0.80)==1 && G3VolScore(1.80)==1
         && G3VolScore(0.799)==0 && G3VolScore(1.801)==0);
   CHECK("T-042c test_vol_block_above_2_5",
         !G3VolBlocksEntry(2.50) && G3VolBlocksEntry(2.501));

   //--- T-046 median of an even sample averages the two central values
   DoubleSeries even;
   even.n=4;
   even.v[0]=4.0; even.v[1]=1.0; even.v[2]=3.0; even.v[3]=2.0;
   double med=0.0;
   CHECK("T-046 test_atr_median_even_sample", G3Median(even,med) && Near(med,2.5,1e-12));
   DoubleSeries odd;
   odd.n=5;
   odd.v[0]=5.0; odd.v[1]=1.0; odd.v[2]=4.0; odd.v[3]=2.0; odd.v[4]=3.0;
   CHECK("T-046b test_median_odd_sample", G3Median(odd,med) && Near(med,3.0,1e-12));
   DoubleSeries none;
   none.n=0;
   CHECK("T-046c test_median_empty_rejected", !G3Median(none,med));

   //--- T-043 spread ratio and block
   double sr=0.0;
   CHECK("T-043 test_spread_ratio",
         G3SpreadRatio(1.10012,1.10000,0.0010,sr) && Near(sr,0.12,1e-9));
   CHECK("T-043b test_spread_score_boundary",
         G3SpreadScore(0.12)==1 && G3SpreadScore(0.1201)==0);
   CHECK("T-043c test_spread_block_above_0_20",
         !G3SpreadBlocksEntry(0.20) && G3SpreadBlocksEntry(0.2001));

   //--- T-045 total score is capped at 8 by construction
   CHECK("T-045 test_total_score_max_8", G3TotalScore(2,2,2,1,1)==G3_SCORE_MAX);

   //--- T-044 RESTRICTED forces threshold 6
   CHECK("T-044 test_effective_threshold_restricted",
         G3EffectiveScoreThreshold(4,G3_DD_RESTRICTED)==6
         && G3EffectiveScoreThreshold(5,G3_DD_RESTRICTED)==6
         && G3EffectiveScoreThreshold(6,G3_DD_RESTRICTED)==6);
   CHECK("T-044b test_effective_threshold_other_states",
         G3EffectiveScoreThreshold(4,G3_DD_NORMAL)==4
         && G3EffectiveScoreThreshold(5,G3_DD_MODERATE)==5
         && G3EffectiveScoreThreshold(6,G3_DD_NORMAL)==6);
  }

//+------------------------------------------------------------------+
//| 16 research log schema                                           |
//+------------------------------------------------------------------+
static void test_log_schema()
  {
   G3LogRecord r;
   G3LogRecordInit(r);
   r.symbol="EURUSD";
   r.side=G3_SIDE_BUY;
   r.signal_id="EURUSD#1700000000";
   r.record_type="EVAL";
   r.skip_reason=G3_R_TOTAL_SCORE_BELOW_THRESHOLD;
   string line=G3LogRecordToLine(r);
   int head=G3LogColumnCount();
   int cols=G3LogLineColumnCount(line);
   CHECK("T-047 test_log_schema_column_count_matches", head==cols);
   CHECK("T-047b test_log_has_all_spec_fields", head>=80);
   //--- Addendum E: the fakeout columns carry a tri-state, and an
   //--- unresolved window is NA rather than a guessed FALSE.
   CHECK("T-047c test_fakeout_columns_are_tristate",
         StringFind(line,"NA",0)>0 && StringFind(line,"NA_SPEC_UNDEFINED",0)<0);
   //--- reason codes are never emitted as raw integers
   CHECK("T-047d test_reason_code_text",
         StringFind(line,"TOTAL_SCORE_BELOW_THRESHOLD",0)>0);
   CHECK("T-047e test_side_text", StringFind(line,"BUY",0)>0);
  }

//+------------------------------------------------------------------+
//| Regression tests for the conformance fixes (DEV-001 .. DEV-016)  |
//+------------------------------------------------------------------+
static void test_dev_regressions()
  {
   //--- DEV-001: the M15 pullback band must use the ATR OF THE SAME
   //--- SHIFT as the Low/High being tested (spec 6). Both cases below
   //--- give the opposite answer under the old shift-1-only behaviour.
   M15Input a;
   for(int k=0;k<3;k++) { a.ema20[k]=1.1000; a.high[k]=1.1100; }
   a.low[0]=1.1010; a.low[1]=1.1008; a.low[2]=1.1006;
   a.atr14[0]=0.0010; a.atr14[1]=0.0010; a.atr14[2]=0.0050;
   a.close_s1=1.1050; a.ema20_s1=1.1000; a.ema20_s4=1.0990; a.ema50_s1=1.0995;
   //--- only shift 3 reaches its own (wider) band
   CHECK("R-001a test_m15_pullback_uses_shift3_atr",
         G3M15PullbackFlag(a,G3_SIDE_BUY));

   M15Input b=a;
   b.low[0]=1.1020; b.low[1]=1.1006; b.low[2]=1.1030;
   b.atr14[0]=0.0050; b.atr14[1]=0.0010; b.atr14[2]=0.0010;
   //--- the wide ATR belongs to shift 1 and must NOT widen shift 2
   CHECK("R-001b test_m15_pullback_does_not_borrow_shift1_atr",
         !G3M15PullbackFlag(b,G3_SIDE_BUY));

   //--- a zero ATR on one shift only skips that shift
   M15Input c=a;
   c.atr14[2]=0.0;
   CHECK("R-001c test_m15_zero_atr_on_one_shift",
         !G3M15PullbackFlag(c,G3_SIDE_BUY));

   //--- SELL side, same rule
   M15Input d;
   for(int k=0;k<3;k++) { d.ema20[k]=1.1000; d.low[k]=1.0900; }
   d.high[0]=1.0990; d.high[1]=1.0992; d.high[2]=1.0994;
   d.atr14[0]=0.0010; d.atr14[1]=0.0010; d.atr14[2]=0.0050;
   d.close_s1=1.0950; d.ema20_s1=1.1000; d.ema20_s4=1.1010; d.ema50_s1=1.1005;
   CHECK("R-001d test_m15_pullback_sell_uses_same_shift_atr",
         G3M15PullbackFlag(d,G3_SIDE_SELL));

   //--- DEV-002: weekend / abnormal gap cooldown (spec 4.2)
   const long H4=4*3600;
   LongSeries g;
   g.n=4;
   g.v[0]=1000000;            // reference bar
   g.v[1]=1000000-H4;         // normal step
   g.v[2]=1000000-2*H4;
   g.v[3]=1000000-3*H4;
   CHECK("R-002a test_no_gap_on_normal_spacing", !G3IsPostGapBar(g,0,H4));

   LongSeries gap;
   gap.n=3;
   gap.v[0]=1000000;
   gap.v[1]=1000000-3*H4;     // step of 3 periods = gap
   gap.v[2]=1000000-4*H4;
   CHECK("R-002b test_gap_detected_beyond_two_periods",
         G3IsPostGapBar(gap,0,H4));
   //--- only the FIRST bar after the gap is flagged
   CHECK("R-002c test_bar_after_the_post_gap_bar_is_clean",
         !G3IsPostGapBar(gap,1,H4));

   LongSeries edge;
   edge.n=2;
   edge.v[0]=1000000;
   edge.v[1]=1000000-2*H4;    // exactly twice the period is not a gap
   CHECK("R-002d test_exactly_two_periods_is_not_a_gap",
         !G3IsPostGapBar(edge,0,H4));

   LongSeries lone;
   lone.n=1;
   lone.v[0]=1000000;
   CHECK("R-002e test_gap_unknown_without_neighbour",
         !G3IsPostGapBar(lone,0,H4));
   CHECK("R-002f test_gap_rejects_bad_arguments",
         !G3IsPostGapBar(g,-1,H4) && !G3IsPostGapBar(g,0,0));

   //--- DEV-004: the break-even cost is commission + swap + estimated
   //--- exit commission, and never the spread (spec 10.2).
   CHECK("R-004a test_be_cost_sums_commission_and_swap",
         Near(G3BreakevenCostMoney(-3.0,-1.5,-3.0),7.5,1e-12));
   CHECK("R-004b test_be_cost_positive_swap_offsets",
         Near(G3BreakevenCostMoney(-3.0,2.0,-3.0),4.0,1e-12));
   CHECK("R-004c test_be_cost_net_credit_is_zero",
         Near(G3BreakevenCostMoney(-3.0,10.0,-3.0),0.0,1e-12));
   CHECK("R-004d test_be_cost_zero_when_no_costs",
         Near(G3BreakevenCostMoney(0.0,0.0,0.0),0.0,1e-12));
   //--- the resulting stop is beyond the entry on both sides
   CHECK("R-004e test_be_price_uses_cost_only",
         G3BreakevenPrice(G3_SIDE_BUY,1.10000,0.00003)>1.10000
         && G3BreakevenPrice(G3_SIDE_SELL,1.10000,0.00003)<1.10000);
   CHECK("R-004f test_be_price_zero_cost_is_entry",
         Near(G3BreakevenPrice(G3_SIDE_BUY,1.10000,0.0),1.10000,1e-12));

   //--- DEV-013: the correlation window is 60 complete D1 bars, so the
   //--- guard must be READY at exactly 60 bars (spec 11.4).
   CHECK("R-005a test_correlation_window_is_60_bars",
         G3_CORR_REQUIRED_BARS==60);
   DoubleSeries x,y;
   x.n=G3_CORR_REQUIRED_BARS-1;
   y.n=G3_CORR_REQUIRED_BARS-1;
   for(int i=0;i<x.n;i++)
     {
      x.v[i]=(double)i;
      y.v[i]=0.5*(double)i+2.0;
     }
   double r=0.0;
   CHECK("R-005b test_pearson_over_59_returns",
         G3Pearson(x,y,r) && Near(r,1.0,1e-9) && x.n==59);

   //--- DEV-009/010/011/016: log schema follows the section 12 names
   CHECK("R-007a test_log_uses_spec_feature_flag_names",
         StringFind(G3LogHeader(),"h4_slope,h4_adx,m15_pullback,m15_structure,breakout_gate",0)>0);
   CHECK("R-007b test_log_has_post_gap_column",
         StringFind(G3LogHeader(),"post_gap",0)>0);
   CHECK("R-007c test_log_has_sl_distance_columns",
         StringFind(G3LogHeader(),"sl_raw_distance",0)>0
         && StringFind(G3LogHeader(),"sl_final_distance",0)>0);
   CHECK("R-007d test_log_has_tick_value_columns",
         StringFind(G3LogHeader(),"tick_value_profit",0)>0
         && StringFind(G3LogHeader(),"tick_value_loss",0)>0);
   CHECK("R-007e test_log_uses_spec_risk_field_name",
         StringFind(G3LogHeader(),"risk_1lot_calc",0)>0
         && StringFind(G3LogHeader(),"order_calc_profit_1lot",0)<0);
   CHECK("R-007f test_log_has_corr_unavailable",
         StringFind(G3LogHeader(),"corr_unavailable",0)>0);
   CHECK("R-007g test_log_uses_spec_stop_level_name",
         StringFind(G3LogHeader(),"stop_level",0)>0
         && StringFind(G3LogHeader(),"stops_level",0)<0);
   CHECK("R-007h test_log_has_commission_estimate",
         StringFind(G3LogHeader(),"commission_per_lot_est",0)>0);

   G3LogRecord rec;
   G3LogRecordInit(rec);
   rec.store_status=G3_STORE_MISMATCH;
   rec.post_gap=true;
   string line=G3LogRecordToLine(rec);
   CHECK("R-007i test_log_row_matches_header_after_changes",
         G3LogColumnCount()==G3LogLineColumnCount(line));
   CHECK("R-007j test_log_row_carries_spec_store_status",
         StringFind(line,"RECOVERED",0)>0);
   //--- the detail column keeps the richer internal status
   CHECK("R-007k test_log_row_keeps_store_detail",
         StringFind(line,"STORE_MISMATCH_CONSERVATIVE",0)>0);
  }

//+------------------------------------------------------------------+
//| Patch-2 regressions: Master Specification v0.4.1a Addendum A/B/E |
//+------------------------------------------------------------------+
static void test_patch2_regressions()
  {
   //--- Addendum E (DEV-007): the touch rule is side dependent.
   CHECK("Q-001a test_fakeout_touch_buy_uses_bid",
         G3FakeoutTouched(G3_SIDE_BUY,1.09900,1.09912,1.09900)
         && !G3FakeoutTouched(G3_SIDE_BUY,1.09901,1.09913,1.09900));
   CHECK("Q-001b test_fakeout_touch_sell_uses_ask",
         G3FakeoutTouched(G3_SIDE_SELL,1.10088,1.10100,1.10100)
         && !G3FakeoutTouched(G3_SIDE_SELL,1.10087,1.10099,1.10100));
   CHECK("Q-001c test_fakeout_touch_needs_a_stop",
         !G3FakeoutTouched(G3_SIDE_BUY,1.0,1.0,0.0));

   //--- a touch inside the first three bars sets both windows
   G3FakeoutWatch w;
   G3FakeoutInit(w,1,"EURUSD","EURUSD#1",G3_SIDE_BUY,1.10000,1.09900,1700000000);
   CHECK("Q-002a test_fakeout_starts_na",
         w.fakeout_3==G3_TRI_NA && w.fakeout_6==G3_TRI_NA && w.bars_observed==1);
   G3FakeoutObserve(w,1,1.10010,1.10022);
   G3FakeoutObserve(w,2,1.09900,1.09912);
   CHECK("Q-002b test_fakeout_touch_within_3_bars_sets_both",
         w.fakeout_3==G3_TRI_TRUE && w.fakeout_6==G3_TRI_TRUE);

   //--- a touch after bar 3 but inside bar 6 sets only the 6 bar window
   G3FakeoutWatch late;
   G3FakeoutInit(late,2,"EURUSD","EURUSD#2",G3_SIDE_BUY,1.10000,1.09900,1700000000);
   for(int b=1;b<=4;b++)
      G3FakeoutObserve(late,b,1.10010,1.10022);
   G3FakeoutFinalise(late,4);
   CHECK("Q-003a test_fakeout_3_closes_false_after_bar_3",
         late.fakeout_3==G3_TRI_FALSE && late.fakeout_6==G3_TRI_NA);
   G3FakeoutObserve(late,5,1.09890,1.09902);
   CHECK("Q-003b test_fakeout_6_still_catches_a_late_touch",
         late.fakeout_3==G3_TRI_FALSE && late.fakeout_6==G3_TRI_TRUE);

   //--- never touched: both windows close FALSE, and the watch completes
   G3FakeoutWatch clean;
   G3FakeoutInit(clean,3,"EURUSD","EURUSD#3",G3_SIDE_BUY,1.10000,1.09900,1700000000);
   bool completed=false;
   for(int b=1;b<=7;b++)
     {
      G3FakeoutObserve(clean,b,1.10050,1.10062);
      if(G3FakeoutFinalise(clean,b))
         completed=true;
     }
   CHECK("Q-004 test_fakeout_no_touch_closes_false",
         completed && clean.completed
         && clean.fakeout_3==G3_TRI_FALSE && clean.fakeout_6==G3_TRI_FALSE);

   //--- an incompletely observed window is NA, never FALSE
   G3FakeoutWatch gapped;
   G3FakeoutInit(gapped,4,"EURUSD","EURUSD#4",G3_SIDE_BUY,1.10000,1.09900,1700000000);
   G3FakeoutObserve(gapped,1,1.10050,1.10062);
   G3FakeoutObserve(gapped,4,1.10050,1.10062);      // bars 2 and 3 missed
   G3FakeoutFinalise(gapped,4);
   CHECK("Q-005a test_fakeout_gap_detected", gapped.observation_gap);
   CHECK("Q-005b test_fakeout_gap_stays_na", gapped.fakeout_3==G3_TRI_NA);
   for(int b=5;b<=7;b++)
     {
      G3FakeoutObserve(gapped,b,1.10050,1.10062);
      G3FakeoutFinalise(gapped,b);
     }
   CHECK("Q-005c test_fakeout_gap_completes_as_na",
         gapped.completed && gapped.fakeout_6==G3_TRI_NA);

   //--- a positive observation survives a later gap
   G3FakeoutWatch touched;
   G3FakeoutInit(touched,5,"EURUSD","EURUSD#5",G3_SIDE_BUY,1.10000,1.09900,1700000000);
   G3FakeoutObserve(touched,1,1.09880,1.09892);
   G3FakeoutMarkObservationGap(touched);
   G3FakeoutFinalise(touched,7);
   CHECK("Q-006 test_fakeout_true_survives_a_restart",
         touched.fakeout_3==G3_TRI_TRUE && touched.fakeout_6==G3_TRI_TRUE);

   //--- observations past the 6 bar window change nothing
   G3FakeoutWatch closed;
   G3FakeoutInit(closed,6,"EURUSD","EURUSD#6",G3_SIDE_BUY,1.10000,1.09900,1700000000);
   for(int b=1;b<=7;b++)
     {
      G3FakeoutObserve(closed,b,1.10050,1.10062);
      G3FakeoutFinalise(closed,b);
     }
   G3FakeoutObserve(closed,9,1.09000,1.09012);
   CHECK("Q-007 test_fakeout_window_is_closed_after_6_bars",
         closed.fakeout_6==G3_TRI_FALSE && closed.completed);

   CHECK("Q-008 test_tristate_text",
         G3TriStateToString(G3_TRI_TRUE)==string("TRUE")
         && G3TriStateToString(G3_TRI_FALSE)==string("FALSE")
         && G3TriStateToString(G3_TRI_NA)==string("NA"));

   //--- Addendum B (DEV-017): recovery is never automatic.
   CHECK("Q-009a test_recovery_not_requested",
         G3RecoveryPrecheck(G3_RECOVERY_NONE,true,true,true,0)
         ==G3_RECOVERY_NOT_REQUESTED);
   CHECK("Q-009b test_recovery_refused_when_state_is_fine",
         G3RecoveryPrecheck(G3_RECOVERY_NEW_EPOCH,false,true,true,0)
         ==G3_RECOVERY_REFUSED_NOT_UNCERTAIN);
   CHECK("Q-009c test_recovery_needs_a_named_operator",
         G3RecoveryPrecheck(G3_RECOVERY_NEW_EPOCH,true,false,true,0)
         ==G3_RECOVERY_REFUSED_NO_OPERATOR);
   CHECK("Q-009d test_new_epoch_needs_a_g1_review_record",
         G3RecoveryPrecheck(G3_RECOVERY_NEW_EPOCH,true,true,false,0)
         ==G3_RECOVERY_REFUSED_NO_G1_RECORD);
   CHECK("Q-009e test_new_epoch_needs_a_flat_book",
         G3RecoveryPrecheck(G3_RECOVERY_NEW_EPOCH,true,true,true,1)
         ==G3_RECOVERY_REFUSED_OPEN_POSITIONS);
   CHECK("Q-009f test_new_epoch_admissible",
         G3RecoveryPrecheck(G3_RECOVERY_NEW_EPOCH,true,true,true,0)
         ==G3_RECOVERY_EPOCH_CREATED);
   CHECK("Q-009g test_reconcile_is_audit_only",
         G3RecoveryPrecheck(G3_RECOVERY_RECONCILE,true,true,false,3)
         ==G3_RECOVERY_RECONCILED_AUDITED);

   //--- an unknown hard stop is never cleared by a new epoch
   CHECK("Q-010a test_unknown_latch_stays_latched",
         G3NewEpochHardStop(false,false) && G3NewEpochHardStop(false,true));
   CHECK("Q-010b test_known_latch_is_carried_over",
         G3NewEpochHardStop(true,true) && !G3NewEpochHardStop(true,false));

   //--- the epoch rebases the peak but does not erase the latch
   G3State prior;
   G3StateInit(prior);
   prior.epoch_id=2;
   prior.peak_equity=50000.0;
   prior.dd_state=G3_DD_UNCERTAIN;
   G3State epoch=G3BuildEpochState(prior,10000.0,1700000000,true,false);
   CHECK("Q-011a test_epoch_rebases_peak_and_daily",
         epoch.epoch_id==3 && Near(epoch.peak_equity,10000.0,1e-9)
         && Near(epoch.daily_start_equity,10000.0,1e-9)
         && epoch.dd_state==G3_DD_NORMAL && !epoch.hard_stop_latched);
   G3State epoch_unknown=G3BuildEpochState(prior,10000.0,1700000000,false,false);
   CHECK("Q-011b test_epoch_with_unknown_latch_stays_hard_stopped",
         epoch_unknown.hard_stop_latched
         && epoch_unknown.dd_state==G3_DD_HARD_STOP);

   //--- the epoch id survives the store round trip and merges forward
   G3State back;
   G3StateInit(back);
   CHECK("Q-012a test_epoch_survives_round_trip",
         G3ParseStateLine(G3StateToLine(epoch),back) && back.epoch_id==3);
   G3State older=epoch;
   older.epoch_id=1;
   G3State merged=G3MergeConservative(older,epoch);
   CHECK("Q-012b test_merge_keeps_the_newer_epoch", merged.epoch_id==3);

   //--- a schema 2 record is not silently read as schema 3
   CHECK("Q-013 test_schema_2_record_rejected",
         !G3ParseStateLine("v=2|peak=1.00|dd=0|latch=0|dse=1.00|date=0|chk=0",back));
  }

//+------------------------------------------------------------------+
int main()
  {
   std::printf("G3 Research EA - host unit tests (pure specification logic)\n");
   std::printf("-----------------------------------------------------------\n");
   test_time_sync();
   test_state_store();
   test_signal_ledger();
   test_dd_state_machine();
   test_risk_and_lots();
   test_deviation();
   test_exits();
   test_portfolio();
   test_signal_logic();
   test_log_schema();
   test_dev_regressions();
   test_patch2_regressions();
   std::printf("-----------------------------------------------------------\n");
   std::printf("PASSED: %d   FAILED: %d\n",g_pass,g_fail);
   return (g_fail==0)?0:1;
  }
