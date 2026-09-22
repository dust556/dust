//+------------------------------------------------------------------+
//|                                                G3_ResearchEA.mq5 |
//|                                                                  |
//|  G3 Research Expert Advisor                                      |
//|  Faithful implementation of Master Specification v0.4 for the     |
//|  purpose of generating IS / OOS / Walk-Forward / Stress /         |
//|  Monte-Carlo / sensitivity research data.                         |
//|                                                                  |
//|  This EA makes no judgement about profitability. It does not      |
//|  optimise, it does not adapt, and it never touches Final Holdout  |
//|  data.                                                            |
//|                                                                  |
//|  Deployment: ONE instance per symbol (the decision_tick is the    |
//|  first tick of a new M5 bar of the chart symbol). Portfolio       |
//|  limits are evaluated across all instances that share InpMagic.   |
//+------------------------------------------------------------------+
#property copyright "G3 Research"
#property version   "0.4"
#property description "G3 Research EA - Master Specification v0.4 research build"

#include "G3Types.mqh"
#include "TimeSync.mqh"
#include "SignalH4.mqh"
#include "SetupM15.mqh"
#include "TriggerM5.mqh"
#include "MarketFilters.mqh"
#include "RiskManager.mqh"
#include "PortfolioManager.mqh"
#include "OrderManager.mqh"
#include "ExitManager.mqh"
#include "StateStore.mqh"
#include "ResearchLogger.mqh"

#define G3_EA_VERSION       "0.4.0-research"
#define G3_SPEC_VERSION     "MasterSpec-v0.4"
#define G3_MAX_TRACKED      16
#define G3_H4_HISTORY       260
#define G3_M15_HISTORY      120
#define G3_ATR_MEDIAN_COUNT 100
#define G3_LOCK_TIMEOUT_MS  1000

//+------------------------------------------------------------------+
//| G3 registered inputs (section 17).                               |
//| No optimisation grid, no search helper, no hidden parameters.     |
//+------------------------------------------------------------------+
input ENUM_G3_SCORE_THRESHOLD InpScoreThreshold = G3_SCORE_TH_5;   // ScoreThreshold (4/5/6, baseline 5)
input ENUM_G3_EXIT_MODE       InpExitMode       = G3_EXIT_A;       // ExitMode A/B/C
input ENUM_G3_TIMEOUT         InpTimeout        = G3_TIMEOUT_OFF;  // Timeout in M5 bars

//--- Execution stress parameters (section 17). Neutral by default;
//--- a non-zero value is a stress scenario, not a strategy change.
input int    InpStressExtraSpreadPoints = 0;      // execution stress: extra spread (points)
input double InpStressCommissionPerLot  = 0.0;    // execution stress: commission per 1.0 lot (account ccy)

//--- Research infrastructure (not strategy parameters).
input long   InpMagic                   = 940400; // magic number
input string InpRunId                   = "R000"; // research run id (log file tag)
input bool   InpManualHardStopReset     = false;  // audited manual HARD_STOP reset (section 10)

//+------------------------------------------------------------------+
//| Globals                                                          |
//+------------------------------------------------------------------+
int    h_h4_ema50=INVALID_HANDLE, h_h4_ema200=INVALID_HANDLE;
int    h_h4_atr  =INVALID_HANDLE, h_h4_adx   =INVALID_HANDLE;
int    h_m15_ema20=INVALID_HANDLE,h_m15_ema50=INVALID_HANDLE,h_m15_atr=INVALID_HANDLE;
int    h_m5_ema9 =INVALID_HANDLE, h_m5_ema20 =INVALID_HANDLE,h_m5_atr =INVALID_HANDLE;

G3StoreContext g_ctx;
G3State        g_state;          // shared: account_login + magic (11.2)
G3SignalState  g_sig;            // per symbol signal ledger (4.1)
G3Logger       g_logger;
ENUM_G3_STORE_STATUS g_store_status=G3_STORE_FRESH;
ENUM_G3_STORE_STATUS g_sig_status=G3_STORE_FRESH;

G3TradeState   g_trades[G3_MAX_TRACKED];
int            g_trade_count=0;
bool           g_timeout_close[G3_MAX_TRACKED];

datetime       g_last_m5_open=0;
bool           g_init_ok=false;

double         g_equity=0.0;
double         g_dd_pct=0.0;
bool           g_daily_lock=false;

//+------------------------------------------------------------------+
//| Helpers                                                          |
//+------------------------------------------------------------------+
bool CopyBufSeries(const int handle,const int buffer,const int start,
                   const int count,double &dst[])
  {
   ArraySetAsSeries(dst,true);
   if(handle==INVALID_HANDLE || count<=0)
      return(false);
   return(CopyBuffer(handle,buffer,start,count,dst)==count);
  }

bool CopyHighSeries(const string symbol,const ENUM_TIMEFRAMES tf,const int start,
                    const int count,double &dst[])
  {
   ArraySetAsSeries(dst,true);
   return(CopyHigh(symbol,tf,start,count,dst)==count);
  }

bool CopyLowSeries(const string symbol,const ENUM_TIMEFRAMES tf,const int start,
                   const int count,double &dst[])
  {
   ArraySetAsSeries(dst,true);
   return(CopyLow(symbol,tf,start,count,dst)==count);
  }

//--- convert a money amount into a price distance for `volume` lots
double MoneyToPriceDistance(const string symbol,const double money,const double volume)
  {
   if(money<=0.0 || volume<=0.0)
      return(0.0);
   double p=SymbolInfoDouble(symbol,SYMBOL_BID);
   if(p<=0.0)
      return(0.0);
   double profit=0.0;
   if(!OrderCalcProfit(ORDER_TYPE_BUY,symbol,volume,p,p+1.0,profit))
      return(0.0);
   double value_per_price_unit=MathAbs(profit);
   if(value_per_price_unit<=0.0)
      return(0.0);
   return(money/value_per_price_unit);
  }

//--- Round-turn commission per 1.0 lot in account currency.
//--- Master Specification v0.4 section 9.2 ("Commission見積りを利用可能なら
//--- 事前riskに加える") and 10.2 ("実commissionがdeal historyから取得できる
//--- 場合は実値を優先。broker fee scheduleが明示される場合はそちらを優先").
//--- The explicit fee schedule input wins; otherwise the estimate is
//--- derived from this symbol's recent closed deals. 0 when unavailable.
double CommissionPerLotRoundTurn(const string symbol,const long magic)
  {
   if(InpStressCommissionPerLot>0.0)
      return(InpStressCommissionPerLot);
   datetime to=TimeCurrent();
   datetime from=(datetime)((long)to-30*24*3600);
   if(!HistorySelect(from,to))
      return(0.0);
   double commission=0.0,volume=0.0;
   int total=HistoryDealsTotal();
   for(int i=0;i<total;i++)
     {
      ulong d=HistoryDealGetTicket(i);
      if(d==0)
         continue;
      if(HistoryDealGetString(d,DEAL_SYMBOL)!=symbol)
         continue;
      if(HistoryDealGetInteger(d,DEAL_MAGIC)!=magic)
         continue;
      commission+=MathAbs(HistoryDealGetDouble(d,DEAL_COMMISSION));
      volume+=HistoryDealGetDouble(d,DEAL_VOLUME);
     }
   if(volume<=0.0 || commission<=0.0)
      return(0.0);
   //--- commission/volume is the per-lot cost of ONE leg on average;
   //--- a round turn is entry plus exit.
   return(2.0*commission/volume);
  }

//--- Commission already booked on an open position (negative money).
double PositionCommissionIncurred(const ulong position_ticket)
  {
   if(!HistorySelectByPosition(position_ticket))
      return(0.0);
   double sum=0.0;
   int deals=HistoryDealsTotal();
   for(int i=0;i<deals;i++)
     {
      ulong d=HistoryDealGetTicket(i);
      if(d==0)
         continue;
      sum+=HistoryDealGetDouble(d,DEAL_COMMISSION);
     }
   return(sum);
  }

//--- server midnight of a server timestamp
long ServerDateOf(const datetime t)
  {
   MqlDateTime dt;
   TimeToStruct(t,dt);
   dt.hour=0;
   dt.min=0;
   dt.sec=0;
   return((long)StructToTime(dt));
  }

//+------------------------------------------------------------------+
//| OnInit                                                           |
//+------------------------------------------------------------------+
int OnInit()
  {
   g_init_ok=false;
   g_logger.handle=INVALID_HANDLE;

   //--- Section 3: hedging accounts only.
   long margin_mode=AccountInfoInteger(ACCOUNT_MARGIN_MODE);
   if(margin_mode!=ACCOUNT_MARGIN_MODE_RETAIL_HEDGING)
     {
      Print("G3: ACCOUNT_MARGIN_MODE_RETAIL_HEDGING required. Found mode=",margin_mode);
      return(INIT_FAILED);
     }

   string sym=_Symbol;

   h_h4_ema50 =iMA(sym,PERIOD_H4,50,0,MODE_EMA,PRICE_CLOSE);
   h_h4_ema200=iMA(sym,PERIOD_H4,200,0,MODE_EMA,PRICE_CLOSE);
   h_h4_atr   =iATR(sym,PERIOD_H4,14);
   h_h4_adx   =iADX(sym,PERIOD_H4,14);
   h_m15_ema20=iMA(sym,PERIOD_M15,20,0,MODE_EMA,PRICE_CLOSE);
   h_m15_ema50=iMA(sym,PERIOD_M15,50,0,MODE_EMA,PRICE_CLOSE);
   h_m15_atr  =iATR(sym,PERIOD_M15,14);
   h_m5_ema9  =iMA(sym,PERIOD_M5,9,0,MODE_EMA,PRICE_CLOSE);
   h_m5_ema20 =iMA(sym,PERIOD_M5,20,0,MODE_EMA,PRICE_CLOSE);
   h_m5_atr   =iATR(sym,PERIOD_M5,14);

   if(h_h4_ema50==INVALID_HANDLE || h_h4_ema200==INVALID_HANDLE ||
      h_h4_atr==INVALID_HANDLE   || h_h4_adx==INVALID_HANDLE    ||
      h_m15_ema20==INVALID_HANDLE|| h_m15_ema50==INVALID_HANDLE ||
      h_m15_atr==INVALID_HANDLE  || h_m5_ema9==INVALID_HANDLE   ||
      h_m5_ema20==INVALID_HANDLE || h_m5_atr==INVALID_HANDLE)
     {
      Print("G3: indicator handle creation failed");
      return(INIT_FAILED);
     }

   G3StoreContextInit(g_ctx,sym,InpMagic);
   g_store_status=G3LoadState(g_ctx,g_state);
   g_sig_status=G3LoadSignalState(g_ctx,g_sig);
   if(g_store_status==G3_STORE_BOTH_LOST)
      Print("G3: both state stores unrecoverable -> STATE_UNCERTAIN, no new entries");
   if(g_store_status==G3_STORE_MISMATCH)
      Print("G3: state store mismatch -> conservative state adopted");

   double equity=AccountInfoDouble(ACCOUNT_EQUITY);
   if(g_state.peak_equity<=0.0)
      g_state.peak_equity=equity;
   if(g_state.daily_start_equity<=0.0)
     {
      g_state.daily_start_equity=equity;
      g_state.server_date=ServerDateOf(TimeCurrent());
     }

   if(InpManualHardStopReset)
     {
      double dd=G3DrawdownPct(g_state.peak_equity,equity);
      bool done=G3ManualHardStopReset(g_ctx,g_state,dd);
      Print("G3: manual HARD_STOP reset requested, applied=",done," dd=",dd);
     }

   g_trade_count=G3LoadTradeStates(g_ctx,g_trades,G3_MAX_TRACKED);
   for(int i=0;i<G3_MAX_TRACKED;i++)
      g_timeout_close[i]=false;

   if(!G3LoggerOpen(g_logger,sym,InpMagic,InpRunId))
     {
      Print("G3: research log could not be opened");
      return(INIT_FAILED);
     }

   if(!G3PersistState(g_ctx,g_state))
      Print("G3: warning - initial state flush failed");
   if(!G3PersistSignalState(g_ctx,g_sig))
      Print("G3: warning - initial signal ledger flush failed");

   g_last_m5_open=0;
   g_init_ok=true;
   PrintFormat("G3 Research EA %s (%s) started on %s, magic=%d, run=%s, "
               "account store=%s, signal ledger=%s",
               G3_EA_VERSION,G3_SPEC_VERSION,sym,(int)InpMagic,InpRunId,
               G3StoreStatusToString(g_store_status),
               G3StoreStatusToString(g_sig_status));
   return(INIT_SUCCEEDED);
  }

//+------------------------------------------------------------------+
//| OnDeinit                                                         |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   if(g_init_ok)
     {
      G3SaveTradeStates(g_ctx,g_trades,g_trade_count);
      G3PersistState(g_ctx,g_state);
      G3PersistSignalState(g_ctx,g_sig);
     }
   G3LoggerClose(g_logger);
   if(h_h4_ema50 !=INVALID_HANDLE) IndicatorRelease(h_h4_ema50);
   if(h_h4_ema200!=INVALID_HANDLE) IndicatorRelease(h_h4_ema200);
   if(h_h4_atr   !=INVALID_HANDLE) IndicatorRelease(h_h4_atr);
   if(h_h4_adx   !=INVALID_HANDLE) IndicatorRelease(h_h4_adx);
   if(h_m15_ema20!=INVALID_HANDLE) IndicatorRelease(h_m15_ema20);
   if(h_m15_ema50!=INVALID_HANDLE) IndicatorRelease(h_m15_ema50);
   if(h_m15_atr  !=INVALID_HANDLE) IndicatorRelease(h_m15_atr);
   if(h_m5_ema9  !=INVALID_HANDLE) IndicatorRelease(h_m5_ema9);
   if(h_m5_ema20 !=INVALID_HANDLE) IndicatorRelease(h_m5_ema20);
   if(h_m5_atr   !=INVALID_HANDLE) IndicatorRelease(h_m5_atr);
  }

//+------------------------------------------------------------------+
//| Account / drawdown state refresh                                 |
//+------------------------------------------------------------------+
void RefreshAccountState(double &equity_out,double &dd_pct_out,bool &daily_lock_out)
  {
   equity_out=AccountInfoDouble(ACCOUNT_EQUITY);

   //--- The account record is shared by every symbol instance
   //--- (spec 11.2: key = account_login + MagicNumber), so the
   //--- read-modify-write is serialised and refreshed from the store.
   bool locked=G3PortfolioLock(g_ctx,G3_LOCK_TIMEOUT_MS);
   if(locked)
      G3RefreshSharedState(g_ctx,g_state);

   bool changed=false;

   //--- Server day rollover (spec 11.3). Only a FORWARD date change
   //--- starts a new day: spec 15.4 requires that a clock regression or
   //--- a reconnection never triggers a second reset of the same day.
   long today=ServerDateOf(TimeCurrent());
   if(today>g_state.server_date)
     {
      g_state.server_date=today;
      g_state.daily_start_equity=equity_out;
      changed=true;
     }
   if(g_state.daily_start_equity<=0.0 && equity_out>0.0)
     {
      g_state.daily_start_equity=equity_out;
      changed=true;
     }
   if(equity_out>g_state.peak_equity)
     {
      g_state.peak_equity=equity_out;
      changed=true;
     }
   dd_pct_out=G3DrawdownPct(g_state.peak_equity,equity_out);
   if(g_state.dd_state!=G3_DD_UNCERTAIN)
     {
      bool latched=g_state.hard_stop_latched;
      ENUM_G3_DD_STATE next=G3NextDDState(g_state.dd_state,dd_pct_out,latched);
      if(next!=g_state.dd_state || latched!=g_state.hard_stop_latched)
        {
         g_state.dd_state=next;
         g_state.hard_stop_latched=latched;
         changed=true;
        }
     }
   if(changed && locked)
      G3PersistState(g_ctx,g_state);
   if(locked)
      G3PortfolioUnlock(g_ctx);

   daily_lock_out=G3DailyEntryLocked(g_state.daily_start_equity,equity_out);
  }

//+------------------------------------------------------------------+
//| Log helpers                                                      |
//+------------------------------------------------------------------+
void FillAccountFields(G3LogRecord &rec,const double equity,const double dd_pct,
                       const bool daily_lock)
  {
   rec.time_server=(long)TimeCurrent();
   rec.time_utc=(long)TimeGMT();
   rec.symbol=_Symbol;
   rec.equity=equity;
   rec.balance=AccountInfoDouble(ACCOUNT_BALANCE);
   rec.peak_equity=g_state.peak_equity;
   rec.dd_pct=dd_pct;
   rec.dd_state=g_state.dd_state;
   rec.daily_lock=daily_lock;
   rec.hard_stop_latched=g_state.hard_stop_latched;
   rec.store_status=g_store_status;
   rec.exit_mode=(int)InpExitMode;
   rec.timeout_bars=(int)InpTimeout;
   rec.score_threshold_input=(int)InpScoreThreshold;
  }

void EmitRecord(G3LogRecord &rec,const ENUM_G3_REASON reason)
  {
   rec.skip_reason=reason;
   G3LoggerWrite(g_logger,rec);
  }

//+------------------------------------------------------------------+
//| Decision tick evaluation (Master Specification 4.1 order)         |
//+------------------------------------------------------------------+
void EvaluateDecisionTick(const datetime m5_bar_open)
  {
   //--- account state is refreshed on every tick by OnTick(); the
   //--- decision uses the values as of this tick.
   double equity=g_equity;
   double dd_pct=g_dd_pct;
   bool   daily_lock=g_daily_lock;

   G3LogRecord rec;
   G3LogRecordInit(rec);
   FillAccountFields(rec,equity,dd_pct,daily_lock);

   datetime signal_close_time=G3SignalCloseTime(m5_bar_open);
   rec.m5_bar_time=(long)m5_bar_open;
   rec.signal_close_time=(long)signal_close_time;
   string signal_id=G3BuildSignalId(_Symbol,(long)m5_bar_open);
   rec.signal_id=signal_id;

   //--- 1..3: consumed check, atomic consume, flush to both stores.
   ENUM_G3_REASON consume_reason=G3_R_NONE;
   if(!G3ConsumeSignal(g_ctx,g_sig,signal_id,(long)m5_bar_open,consume_reason))
     {
      EmitRecord(rec,consume_reason);
      return;
     }

   //--- 4: only now is the signal evaluated. Order follows appendix A.
   if(g_state.dd_state==G3_DD_UNCERTAIN || g_store_status==G3_STORE_BOTH_LOST)
     {
      EmitRecord(rec,G3_R_STATE_UNCERTAIN);
      return;
     }
   if(g_state.hard_stop_latched || g_state.dd_state==G3_DD_HARD_STOP)
     {
      EmitRecord(rec,G3_R_HARD_STOP_LATCHED);
      return;
     }
   if(daily_lock)
     {
      EmitRecord(rec,G3_R_DAILY_ENTRY_LOCK);
      return;
     }

   //--- market snapshot re-read at the decision tick (section 9.3)
   MarketSnapshot mk;
   if(!G3ReadMarket(_Symbol,mk))
     {
      EmitRecord(rec,G3_R_DATA_UNAVAILABLE);
      return;
     }
   rec.stop_level=mk.stops_level;
   rec.freeze_level=mk.freeze_level;
   rec.tick_value_profit=SymbolInfoDouble(_Symbol,SYMBOL_TRADE_TICK_VALUE_PROFIT);
   rec.tick_value_loss  =SymbolInfoDouble(_Symbol,SYMBOL_TRADE_TICK_VALUE_LOSS);
   if(!mk.tradable)
     {
      EmitRecord(rec,G3_R_TRADE_MODE_DISABLED);
      return;
     }
   //--- execution stress: additional spread, applied to the observed
   //--- spread used by the filters and by the deviation computation.
   double spread_price=mk.spread_price+((double)InpStressExtraSpreadPoints)*mk.point;

   //--- ---------------- higher timeframe reference bars -------------
   int h4_idx=-1,m15_idx=-1;
   datetime h4_time=0,m15_time=0;
   bool h4_post_gap=false,m15_post_gap=false;
   if(!G3ResolveHtfBar(_Symbol,PERIOD_H4,signal_close_time,G3_H4_HISTORY,
                       h4_idx,h4_time,h4_post_gap))
     {
      EmitRecord(rec,G3_R_HTF_BAR_UNRESOLVED);
      return;
     }
   rec.h4_bar_time=(long)h4_time;
   if(!G3ResolveHtfBar(_Symbol,PERIOD_M15,signal_close_time,G3_M15_HISTORY,
                       m15_idx,m15_time,m15_post_gap))
     {
      EmitRecord(rec,G3_R_HTF_BAR_UNRESOLVED);
      return;
     }
   rec.m15_bar_time=(long)m15_time;

   //--- Section 4.2: no new signal on the first H4 bar completed after a
   //--- gap wider than twice the normal period.
   rec.post_gap=h4_post_gap;
   if(h4_post_gap)
     {
      EmitRecord(rec,G3_R_POST_GAP_COOLDOWN);
      return;
     }

   //--- ---------------- H4 direction gate (5.1) ---------------------
   double h4_ema50[],h4_ema200[],h4_atr[],h4_adx[],h4_pdi[],h4_mdi[],h4_close[];
   if(!CopyBufSeries(h_h4_ema50,0,h4_idx,4,h4_ema50)   ||
      !CopyBufSeries(h_h4_ema200,0,h4_idx,1,h4_ema200) ||
      !CopyBufSeries(h_h4_atr,0,h4_idx,1,h4_atr)       ||
      !CopyBufSeries(h_h4_adx,0,h4_idx,1,h4_adx)       ||
      !CopyBufSeries(h_h4_adx,1,h4_idx,1,h4_pdi)       ||
      !CopyBufSeries(h_h4_adx,2,h4_idx,1,h4_mdi))
     {
      EmitRecord(rec,G3_R_INDICATOR_NOT_READY);
      return;
     }
   ArraySetAsSeries(h4_close,true);
   if(CopyClose(_Symbol,PERIOD_H4,h4_idx,1,h4_close)!=1)
     {
      EmitRecord(rec,G3_R_DATA_UNAVAILABLE);
      return;
     }

   H4Input h4;
   h4.close_ref       =h4_close[0];
   h4.ema50_ref       =h4_ema50[0];
   h4.ema50_ref_minus3=h4_ema50[3];
   h4.ema200_ref      =h4_ema200[0];
   h4.atr14_ref       =h4_atr[0];
   h4.adx14_ref       =h4_adx[0];
   h4.plus_di_ref     =h4_pdi[0];
   h4.minus_di_ref    =h4_mdi[0];
   rec.atr_h4         =h4.atr14_ref;
   rec.adx_value      =h4.adx14_ref;
   rec.plus_di        =h4.plus_di_ref;
   rec.minus_di       =h4.minus_di_ref;

   ENUM_G3_SIDE side=G3H4Direction(h4);
   rec.side=side;
   rec.h4_direction=(side!=G3_SIDE_NONE);
   if(side==G3_SIDE_NONE)
     {
      EmitRecord(rec,G3_R_NO_H4_DIRECTION);
      return;
     }

   //--- ---------------- M5 breakout hard gate (7.1) -----------------
   double m5_atr[],m5_ema9[],m5_ema20[],m5_high[],m5_low[],m5_open[],m5_close[];
   if(!CopyBufSeries(h_m5_atr,0,1,1,m5_atr)    ||
      !CopyBufSeries(h_m5_ema9,0,1,4,m5_ema9)  ||
      !CopyBufSeries(h_m5_ema20,0,1,1,m5_ema20))
     {
      EmitRecord(rec,G3_R_INDICATOR_NOT_READY);
      return;
     }
   if(!CopyHighSeries(_Symbol,PERIOD_M5,1,6,m5_high) ||
      !CopyLowSeries(_Symbol,PERIOD_M5,1,6,m5_low))
     {
      EmitRecord(rec,G3_R_DATA_UNAVAILABLE);
      return;
     }
   ArraySetAsSeries(m5_open,true);
   ArraySetAsSeries(m5_close,true);
   if(CopyOpen(_Symbol,PERIOD_M5,1,1,m5_open)!=1 ||
      CopyClose(_Symbol,PERIOD_M5,1,1,m5_close)!=1)
     {
      EmitRecord(rec,G3_R_DATA_UNAVAILABLE);
      return;
     }

   double atr_s1=m5_atr[0];
   rec.atr_m5=atr_s1;
   if(atr_s1<=0.0)
     {
      EmitRecord(rec,G3_R_INDICATOR_NOT_READY);
      return;
     }

   //--- Highest(High[2..6]) / Lowest(Low[2..6]); index 0 of the copied
   //--- arrays is spec shift 1, so shifts 2..6 are indices 1..5.
   double highest_2_6=m5_high[1];
   double lowest_2_6 =m5_low[1];
   for(int i=1;i<6;i++)
     {
      if(m5_high[i]>highest_2_6) highest_2_6=m5_high[i];
      if(m5_low[i] <lowest_2_6 ) lowest_2_6 =m5_low[i];
     }
   //--- Lowest(Low[1..5]) / Highest(High[1..5]) for the raw stop
   double highest_1_5=m5_high[0];
   double lowest_1_5 =m5_low[0];
   for(int i=0;i<5;i++)
     {
      if(m5_high[i]>highest_1_5) highest_1_5=m5_high[i];
      if(m5_low[i] <lowest_1_5 ) lowest_1_5 =m5_low[i];
     }

   M5Input m5;
   m5.open_s1    =m5_open[0];
   m5.high_s1    =m5_high[0];
   m5.low_s1     =m5_low[0];
   m5.close_s1   =m5_close[0];
   m5.highest_2_6=highest_2_6;
   m5.lowest_2_6 =lowest_2_6;
   m5.ema9_s1    =m5_ema9[0];
   m5.ema9_s4    =m5_ema9[3];
   m5.ema20_s1   =m5_ema20[0];

   rec.breakout_gate=G3M5BreakoutFlag(m5,side);
   if(!rec.breakout_gate)
     {
      EmitRecord(rec,G3_R_M5_BREAKOUT_FAIL);
      return;
     }

   //--- ---------------- quality scores (5.2 / 6 / 7.2) --------------
   bool f_slope=false,f_adx=false;
   double slope=0.0;
   G3H4SlopeValue(h4,slope);
   rec.h4_slope_value=slope;
   rec.h4_score=G3H4Score(h4,side,f_slope,f_adx);
   rec.h4_slope=f_slope;
   rec.h4_adx=f_adx;

   double m15_ema20[],m15_ema50[],m15_atr[],m15_low[],m15_high[],m15_close[];
   if(!CopyBufSeries(h_m15_ema20,0,m15_idx,4,m15_ema20) ||
      !CopyBufSeries(h_m15_ema50,0,m15_idx,1,m15_ema50) ||
      !CopyBufSeries(h_m15_atr,0,m15_idx,3,m15_atr))
     {
      EmitRecord(rec,G3_R_INDICATOR_NOT_READY);
      return;
     }
   if(!CopyLowSeries(_Symbol,PERIOD_M15,m15_idx,3,m15_low) ||
      !CopyHighSeries(_Symbol,PERIOD_M15,m15_idx,3,m15_high))
     {
      EmitRecord(rec,G3_R_DATA_UNAVAILABLE);
      return;
     }
   ArraySetAsSeries(m15_close,true);
   if(CopyClose(_Symbol,PERIOD_M15,m15_idx,1,m15_close)!=1)
     {
      EmitRecord(rec,G3_R_DATA_UNAVAILABLE);
      return;
     }

   M15Input m15;
   for(int k=0;k<3;k++)
     {
      m15.low[k]  =m15_low[k];
      m15.high[k] =m15_high[k];
      m15.ema20[k]=m15_ema20[k];
      m15.atr14[k]=m15_atr[k];      // same shift as Low/High (section 6)
     }
   m15.close_s1=m15_close[0];
   m15.ema20_s1=m15_ema20[0];
   m15.ema20_s4=m15_ema20[3];
   m15.ema50_s1=m15_ema50[0];
   rec.atr_m15 =m15_atr[0];

   bool f_pull=false,f_struct=false;
   rec.m15_score=G3M15Score(m15,side,f_pull,f_struct);
   rec.m15_pullback=f_pull;
   rec.m15_structure=f_struct;

   bool f_candle=false,f_mom=false;
   rec.m5_score=G3M5Score(m5,side,f_candle,f_mom);
   rec.m5_candle=f_candle;
   rec.m5_momentum=f_mom;

   //--- volatility and spread quality (8.2 / 8.3)
   double atr_hist[];
   if(!CopyBufSeries(h_m5_atr,0,2,G3_ATR_MEDIAN_COUNT,atr_hist))
     {
      EmitRecord(rec,G3_R_INDICATOR_NOT_READY);
      return;
     }
   DoubleSeries atr_series;
   atr_series.n=G3_ATR_MEDIAN_COUNT;
   for(int i=0;i<G3_ATR_MEDIAN_COUNT;i++)
      atr_series.v[i]=atr_hist[i];
   double vol_ratio=0.0;
   if(!G3VolRatio(atr_s1,atr_series,vol_ratio))
     {
      EmitRecord(rec,G3_R_INDICATOR_NOT_READY);
      return;
     }
   rec.vol_ratio=vol_ratio;
   rec.vol_score=G3VolScore(vol_ratio);
   rec.vol_point=(rec.vol_score==1);
   rec.vol_block=G3VolBlocksEntry(vol_ratio);

   double spread_ratio=0.0;
   if(!G3SpreadRatio(mk.bid+spread_price,mk.bid,atr_s1,spread_ratio))
     {
      EmitRecord(rec,G3_R_DATA_UNAVAILABLE);
      return;
     }
   rec.spread_ratio=spread_ratio;
   rec.spread_score=G3SpreadScore(spread_ratio);
   rec.spread_point=(rec.spread_score==1);
   rec.spread_block=G3SpreadBlocksEntry(spread_ratio);

   rec.total_score=G3TotalScore(rec.h4_score,rec.m15_score,rec.m5_score,
                                rec.vol_score,rec.spread_score);
   rec.score_threshold_effective=G3EffectiveScoreThreshold((int)InpScoreThreshold,
                                                           g_state.dd_state);

   //--- appendix A: minimum scores and the threshold are checked first,
   //--- the volatility / spread hard filters immediately afterwards.
   if(rec.h4_score<G3_H4_MIN_SCORE)
     {
      EmitRecord(rec,G3_R_H4_SCORE_BELOW_MIN);
      return;
     }
   if(rec.m5_score<G3_M5_MIN_SCORE)
     {
      EmitRecord(rec,G3_R_M5_SCORE_BELOW_MIN);
      return;
     }
   if(rec.total_score<rec.score_threshold_effective)
     {
      EmitRecord(rec,G3_R_TOTAL_SCORE_BELOW_THRESHOLD);
      return;
     }
   if(rec.vol_block)
     {
      EmitRecord(rec,G3_R_VOL_BLOCK);
      return;
     }
   if(rec.spread_block)
     {
      EmitRecord(rec,G3_R_SPREAD_BLOCK);
      return;
     }

   //--- ---------------- stop placement (section 9.1) ----------------
   double entry_price=(side==G3_SIDE_BUY)?mk.ask:mk.bid;
   rec.sl_raw=G3RawStop(side,lowest_1_5,highest_1_5,atr_s1);
   rec.sl_raw_distance=MathAbs(entry_price-rec.sl_raw);

   double sl_strategy=0.0,sl_final=0.0;
   bool   adj_strategy=false,adj_broker=false;
   ENUM_G3_REASON reason=G3_R_NONE;
   if(!G3AdjustStopStrategy(side,entry_price,rec.sl_raw,atr_s1,sl_strategy,
                            adj_strategy,reason))
     {
      rec.sl_strategy=sl_strategy;
      rec.sl_strategy_adjusted=adj_strategy;
      EmitRecord(rec,reason);
      return;
     }
   rec.sl_strategy=sl_strategy;
   rec.sl_strategy_adjusted=adj_strategy;

   double stop_ref=(side==G3_SIDE_BUY)?mk.bid:mk.ask;
   if(!G3AdjustStopBroker(side,entry_price,sl_strategy,atr_s1,stop_ref,
                          mk.stops_level,mk.point,sl_final,adj_broker,reason))
     {
      rec.sl_final=sl_final;
      rec.sl_broker_adjusted=adj_broker;
      EmitRecord(rec,reason);
      return;
     }
   sl_final=NormalizeDouble(sl_final,mk.digits);
   rec.sl_final=sl_final;
   rec.sl_final_distance=MathAbs(entry_price-sl_final);
   rec.sl_broker_adjusted=adj_broker;

   //--- ---------------- risk and lot (section 9.2) ------------------
   double risk_pct=G3RiskPctForState(g_state.dd_state);
   double risk_money=G3RiskMoney(equity,risk_pct);
   rec.risk_pct=risk_pct;
   rec.risk_money=risk_money;

   double loss_1lot=0.0;
   if(!G3LossForOneLot(_Symbol,side,entry_price,sl_final,loss_1lot))
     {
      EmitRecord(rec,G3_R_ORDER_CALC_PROFIT_INVALID);
      return;
     }
   rec.risk_1lot_calc=-loss_1lot;   // logged as the signed loss

   //--- section 9.2: add the commission estimate to pre-trade risk.
   double commission_per_lot=CommissionPerLotRoundTurn(_Symbol,InpMagic);
   rec.commission_per_lot_est=commission_per_lot;
   double risk_1lot_total=loss_1lot+commission_per_lot;

   double raw_lot=0.0,final_lot=0.0;
   bool capped=false;
   if(!G3ComputeLot(risk_money,risk_1lot_total,mk.volume_step,mk.volume_min,
                    mk.volume_max,raw_lot,final_lot,capped,reason))
     {
      rec.raw_lot=raw_lot;
      EmitRecord(rec,reason);
      return;
     }
   rec.raw_lot=raw_lot;
   rec.final_lot=final_lot;
   rec.lot_capped_by_max=capped;

   //--- ---------------- portfolio limits (section 11.4) -------------
   bool locked=G3PortfolioLock(g_ctx,G3_LOCK_TIMEOUT_MS);
   if(!locked)
     {
      EmitRecord(rec,G3_R_PORTFOLIO_LOCK_BUSY);
      return;
     }

   PortfolioSnapshot snap;
   G3BuildOpenSnapshot(InpMagic,equity,snap);
   double candidate_risk_pct=(equity>0.0)?(final_lot*risk_1lot_total/equity*100.0):0.0;
   int candidate_index=-1;
   if(snap.n<G3_MAX_LEGS)
     {
      snap.leg[snap.n].symbol=_Symbol;
      snap.leg[snap.n].side=side;
      snap.leg[snap.n].initial_risk_pct=candidate_risk_pct;
      candidate_index=snap.n;
      snap.n++;
     }

   CorrMatrix corr;
   G3BuildCorrMatrix(snap,signal_close_time,corr);
   PortfolioDecision pd=G3CheckPortfolio(snap,corr,candidate_index);

   rec.total_risk_pct       =pd.total_risk_pct;
   rec.currency_exposure_pct=pd.currency_risk_pct;
   rec.corr_cluster_risk    =pd.corr_cluster_risk_pct;
   rec.corr_cluster_risk_raw=pd.corr_cluster_risk_raw_pct;
   rec.unknown_cluster_risk =pd.unknown_cluster_risk_pct;
   rec.corr_state           =pd.corr_state;
   rec.corr_unavailable     =(pd.corr_state==G3_CORR_WARMUP_UNKNOWN);
   rec.corr_warmup_days     =pd.corr_warmup_days;
   rec.open_positions       =pd.open_positions;

   if(!pd.accepted)
     {
      G3PortfolioUnlock(g_ctx);
      EmitRecord(rec,pd.reason);
      return;
     }

   //--- ---------------- execution (section 9.3) ---------------------
   DeviationPlan dev=G3BuildDeviationPlan(spread_price,atr_s1,mk.digits,mk.point);
   rec.deviation_computed=dev.computed_points;
   rec.deviation_hard_cap=dev.hard_cap_points;
   rec.deviation_points  =dev.send_points;
   rec.deviation_cap_hit =dev.cap_hit;
   if(!dev.send_allowed)
     {
      G3PortfolioUnlock(g_ctx);
      EmitRecord(rec,G3_R_DEVIATION_CAP_EXCEEDED);
      return;
     }

   double r_distance=MathAbs(entry_price-sl_final);
   double tp=G3InitialTakeProfit(InpExitMode,side,entry_price,r_distance);
   if(tp>0.0)
      tp=NormalizeDouble(tp,mk.digits);

   OrderOutcome oc;
   bool sent=G3SendMarketOrder(_Symbol,side,final_lot,sl_final,tp,dev,mk,
                               InpMagic,"G3_"+InpRunId,oc);
   rec.record_type="ENTRY";
   rec.requested_price=oc.requested_price;
   rec.fill_price=oc.fill_price;
   rec.slippage=oc.slippage_points;
   rec.retcode=oc.retcode;
   if(!sent || !oc.filled)
     {
      G3PortfolioUnlock(g_ctx);
      EmitRecord(rec,G3_R_ORDER_SEND_FAILED);
      return;
     }

   //--- resolve the position ticket created by the deal
   ulong position_ticket=0;
   if(PositionSelectByTicket(oc.ticket))
      position_ticket=oc.ticket;
   else
     {
      if(HistorySelectByPosition(oc.ticket))
         position_ticket=oc.ticket;
      if(position_ticket==0 && PositionSelect(_Symbol))
         position_ticket=(ulong)PositionGetInteger(POSITION_TICKET);
     }

   //--- post-fill risk verification (section 9.3)
   double loss_1lot_fill=0.0;
   double post_ratio=0.0;
   bool   exec_violation=false;
   if(G3LossForOneLot(_Symbol,side,oc.fill_price,sl_final,loss_1lot_fill))
     {
      double risk_1lot_fill=loss_1lot_fill+commission_per_lot;
      post_ratio=G3PostFillRiskRatio(risk_1lot_fill,oc.volume,risk_money);
      if(post_ratio>G3_POST_FILL_RISK_MAX)
        {
         exec_violation=true;
         double allowed=G3RiskCappedVolume(risk_1lot_fill,risk_money,mk.volume_step);
         uint rc=0;
         if(allowed>=mk.volume_min && allowed<oc.volume)
           {
            if(G3ClosePositionVolume(_Symbol,position_ticket,oc.volume-allowed,
                                     InpMagic,dev,rc))
               oc.volume=allowed;
           }
         else
           {
            if(G3ClosePositionVolume(_Symbol,position_ticket,oc.volume,InpMagic,dev,rc))
               oc.volume=0.0;
           }
         rec.retcode=rc;
        }
     }
   rec.post_fill_risk_ratio=post_ratio;
   rec.execution_risk_violation=exec_violation;

   //--- track the position
   if(oc.volume>0.0 && g_trade_count<G3_MAX_TRACKED)
     {
      G3TradeState t;
      t.active               =true;
      t.ticket               =position_ticket;
      t.symbol               =_Symbol;
      t.signal_id            =signal_id;
      t.side                 =side;
      t.entry_time           =(long)TimeCurrent();
      t.entry_m5_bar         =(long)m5_bar_open;
      t.entry_price          =oc.fill_price;
      t.initial_sl           =sl_final;
      t.initial_tp           =tp;
      t.initial_volume       =oc.volume;
      t.current_volume       =oc.volume;
      t.initial_risk_money   =risk_money;
      t.initial_risk_pct     =(equity>0.0)?(oc.volume*risk_1lot_total/equity*100.0):0.0;
      t.r_distance           =MathAbs(oc.fill_price-sl_final);
      t.atr_at_entry         =atr_s1;
      t.mfe_r=0.0;  t.mae_r=0.0;
      t.mfe_r_3bars=0.0; t.mae_r_3bars=0.0;
      t.mfe_r_6bars=0.0; t.mae_r_6bars=0.0;
      t.trail_stop           =0.0;
      t.extreme_price        =oc.fill_price;
      t.realized_pl          =0.0;
      t.partial_closed_volume=0.0;
      t.bars_held            =0;
      t.be_done              =false;
      t.partial_done         =false;
      t.partial_skipped      =false;
      g_trades[g_trade_count]=t;
      g_timeout_close[g_trade_count]=false;
      g_trade_count++;
      G3RegisterPositionRisk(InpMagic,position_ticket,t.initial_risk_pct);
      G3SaveTradeStates(g_ctx,g_trades,g_trade_count);
      rec.mfe_r=0.0;
     }

   G3PortfolioUnlock(g_ctx);
   EmitRecord(rec,exec_violation?G3_R_EXECUTION_RISK_VIOLATION:G3_R_NONE);
  }

//+------------------------------------------------------------------+
//| Position management                                              |
//+------------------------------------------------------------------+
void EmitExitRecord(const G3TradeState &t,const string exit_reason,
                    const double result_r,const double realized_pl,
                    const string record_type,const double partial_ratio)
  {
   double equity=AccountInfoDouble(ACCOUNT_EQUITY);
   double dd=G3DrawdownPct(g_state.peak_equity,equity);
   G3LogRecord rec;
   G3LogRecordInit(rec);
   FillAccountFields(rec,equity,dd,
                     G3DailyEntryLocked(g_state.daily_start_equity,equity));
   rec.record_type   =record_type;
   rec.symbol        =t.symbol;
   rec.side          =t.side;
   rec.signal_id     =t.signal_id;
   rec.m5_bar_time   =t.entry_m5_bar;
   rec.fill_price    =t.entry_price;
   rec.sl_final      =t.initial_sl;
   rec.sl_final_distance=t.r_distance;
   rec.final_lot     =t.initial_volume;
   rec.risk_money    =t.initial_risk_money;
   rec.risk_pct      =t.initial_risk_pct;
   rec.atr_m5        =t.atr_at_entry;
   rec.mfe_r         =t.mfe_r;
   rec.mae_r         =t.mae_r;
   rec.mfe_3bars     =t.mfe_r_3bars;
   rec.mae_3bars     =t.mae_r_3bars;
   rec.mfe_6bars     =t.mfe_r_6bars;
   rec.mae_6bars     =t.mae_r_6bars;
   rec.holding_bars  =t.bars_held;
   rec.exit_reason   =exit_reason;
   rec.result_r      =result_r;
   rec.realized_pl   =realized_pl;
   rec.partial_status=(t.partial_done?"DONE":(t.partial_skipped?"SKIPPED":"NONE"));
   rec.partial_close_ratio=partial_ratio;
   G3LoggerWrite(g_logger,rec);
  }

//--- realised P/L of a closed position, including swap and commission
double RealizedPL(const ulong position_ticket)
  {
   double sum=0.0;
   if(!HistorySelectByPosition(position_ticket))
      return(0.0);
   int deals=HistoryDealsTotal();
   for(int i=0;i<deals;i++)
     {
      ulong d=HistoryDealGetTicket(i);
      if(d==0)
         continue;
      if(HistoryDealGetInteger(d,DEAL_ENTRY)==DEAL_ENTRY_IN)
         continue;
      sum+=HistoryDealGetDouble(d,DEAL_PROFIT);
      sum+=HistoryDealGetDouble(d,DEAL_SWAP);
      sum+=HistoryDealGetDouble(d,DEAL_COMMISSION);
     }
   return(sum);
  }

string ResolveExitReason(const G3TradeState &t,const int slot)
  {
   if(slot>=0 && slot<G3_MAX_TRACKED && g_timeout_close[slot])
      return(G3ReasonToString(G3_R_EXIT_TIMEOUT));
   if(!HistorySelectByPosition(t.ticket))
      return(G3ReasonToString(G3_R_EXIT_MANUAL_OR_EXTERNAL));
   int deals=HistoryDealsTotal();
   long reason=-1;
   for(int i=deals-1;i>=0;i--)
     {
      ulong d=HistoryDealGetTicket(i);
      if(d==0)
         continue;
      if(HistoryDealGetInteger(d,DEAL_ENTRY)==DEAL_ENTRY_IN)
         continue;
      reason=HistoryDealGetInteger(d,DEAL_REASON);
      break;
     }
   if(reason==DEAL_REASON_TP)
      return(G3ReasonToString(G3_R_EXIT_TP));
   if(reason==DEAL_REASON_SL)
     {
      if(t.trail_stop!=0.0)
         return(G3ReasonToString(G3_R_EXIT_TRAIL));
      if(t.be_done)
         return(G3ReasonToString(G3_R_EXIT_BE));
      return(G3ReasonToString(G3_R_EXIT_SL));
     }
   return(G3ReasonToString(G3_R_EXIT_MANUAL_OR_EXTERNAL));
  }

void ManagePositions()
  {
   if(g_trade_count<=0)
      return;
   MqlTick tick;
   if(!SymbolInfoTick(_Symbol,tick))
      return;
   double atr_now=0.0;
   double atr_buf[];
   if(CopyBufSeries(h_m5_atr,0,1,1,atr_buf))
      atr_now=atr_buf[0];

   //--- Master Specification v0.4 section 10.2: the break-even cost is
   //--- the incurred commission plus swap plus the estimated exit
   //--- commission. The SPREAD IS NOT ADDED (DEV-004 fix): it is already
   //--- contained in the Ask/Bid execution relationship.
   double commission_round_turn=CommissionPerLotRoundTurn(_Symbol,InpMagic);

   bool dirty=false;
   for(int i=0;i<g_trade_count;i++)
     {
      if(!g_trades[i].active)
         continue;
      if(g_trades[i].symbol!=_Symbol)
         continue;

      //--- closed?
      if(!PositionSelectByTicket(g_trades[i].ticket))
        {
         double pl=RealizedPL(g_trades[i].ticket);
         g_trades[i].realized_pl=pl;
         string why=ResolveExitReason(g_trades[i],i);
         EmitExitRecord(g_trades[i],why,
                        G3ResultR(pl,g_trades[i].initial_risk_money),pl,"EXIT",0.0);
         G3UnregisterPositionRisk(InpMagic,g_trades[i].ticket);
         g_trades[i].active=false;
         dirty=true;
         continue;
        }

      double price=(g_trades[i].side==G3_SIDE_BUY)?tick.bid:tick.ask;
      int shift=iBarShift(_Symbol,PERIOD_M5,(datetime)g_trades[i].entry_m5_bar,false);
      if(shift>=0)
         g_trades[i].bars_held=shift;
      G3UpdateExcursions(g_trades[i],price,price);
      g_trades[i].current_volume=PositionGetDouble(POSITION_VOLUME);

      //--- partial close (exit mode B only)
      if(InpExitMode==G3_EXIT_B && !g_trades[i].partial_done &&
         !g_trades[i].partial_skipped &&
         g_trades[i].mfe_r>=G3_EXIT_B_PARTIAL_R)
        {
         double step=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_STEP);
         double vmin=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MIN);
         PartialPlan pp=G3BuildPartialPlan(g_trades[i].current_volume,step,vmin);
         if(pp.valid)
           {
            DeviationPlan dev=G3BuildDeviationPlan(tick.ask-tick.bid,
                                                   (atr_now>0.0)?atr_now:g_trades[i].atr_at_entry,
                                                   (int)SymbolInfoInteger(_Symbol,SYMBOL_DIGITS),
                                                   SymbolInfoDouble(_Symbol,SYMBOL_POINT));
            uint rc=0;
            if(G3ClosePositionVolume(_Symbol,g_trades[i].ticket,pp.close_volume,
                                     InpMagic,dev,rc))
              {
               g_trades[i].partial_done=true;
               g_trades[i].partial_closed_volume=pp.close_volume;
               g_trades[i].current_volume=pp.remaining_volume;
               g_trades[i].realized_pl=RealizedPL(g_trades[i].ticket);
               EmitExitRecord(g_trades[i],G3ReasonToString(G3_R_EXIT_PARTIAL),
                              G3ResultR(g_trades[i].realized_pl,
                                        g_trades[i].initial_risk_money),
                              g_trades[i].realized_pl,"PARTIAL",pp.close_ratio);
               //--- portfolio exposure is recomputed from the reduced volume
               double eq=AccountInfoDouble(ACCOUNT_EQUITY);
               double l1=0.0;
               if(G3LossForOneLot(_Symbol,g_trades[i].side,g_trades[i].entry_price,
                                  g_trades[i].initial_sl,l1) && eq>0.0)
                  G3RegisterPositionRisk(InpMagic,g_trades[i].ticket,
                                         pp.remaining_volume*l1/eq*100.0);
               dirty=true;
              }
           }
         else
           {
            //--- no admissible partial: the full volume stays under
            //--- break-even + trail management (section 14 B).
            g_trades[i].partial_skipped=true;
            dirty=true;
           }
        }

      //--- break-even cost of this position (section 10.2)
      double cost_price=0.0;
      if(InpExitMode==G3_EXIT_B)
        {
         double swap_accrued=PositionGetDouble(POSITION_SWAP);
         double commission_incurred=PositionCommissionIncurred(g_trades[i].ticket);
         double per_leg_per_lot=0.0;
         if(commission_incurred<0.0 && g_trades[i].initial_volume>0.0)
            per_leg_per_lot=MathAbs(commission_incurred)/g_trades[i].initial_volume;
         else
            per_leg_per_lot=0.5*commission_round_turn;
         //--- the exit commission is assumed equal to the entry side
         //--- commission per lot (section 10.2 baseline).
         double commission_exit_estimate=-per_leg_per_lot*g_trades[i].current_volume;
         if(commission_incurred>=0.0 && per_leg_per_lot>0.0)
            commission_incurred=-per_leg_per_lot*g_trades[i].initial_volume;
         double cost_money=G3BreakevenCostMoney(commission_incurred,swap_accrued,
                                                commission_exit_estimate);
         cost_price=MoneyToPriceDistance(_Symbol,cost_money,g_trades[i].current_volume);
        }

      //--- stop management
      double desired=G3DesiredStop(InpExitMode,g_trades[i],atr_now,cost_price);
      if(InpExitMode!=G3_EXIT_A && desired!=0.0)
        {
         double current_sl=PositionGetDouble(POSITION_SL);
         double monotonic=G3MonotonicStop(g_trades[i].side,
                                          (current_sl!=0.0)?current_sl:g_trades[i].initial_sl,
                                          desired);
         int digits=(int)SymbolInfoInteger(_Symbol,SYMBOL_DIGITS);
         monotonic=NormalizeDouble(monotonic,digits);
         double point=SymbolInfoDouble(_Symbol,SYMBOL_POINT);
         long stops=SymbolInfoInteger(_Symbol,SYMBOL_TRADE_STOPS_LEVEL);
         long freeze=SymbolInfoInteger(_Symbol,SYMBOL_TRADE_FREEZE_LEVEL);
         double ref=(g_trades[i].side==G3_SIDE_BUY)?tick.bid:tick.ask;
         bool respects_stops=(MathAbs(ref-monotonic)>=((double)stops)*point);
         bool outside_freeze=(MathAbs(ref-monotonic)>((double)freeze)*point);
         if(monotonic!=NormalizeDouble(current_sl,digits) && respects_stops && outside_freeze)
           {
            uint rc=0;
            if(G3ModifyStop(_Symbol,g_trades[i].ticket,monotonic,
                            PositionGetDouble(POSITION_TP),rc))
              {
               g_trades[i].trail_stop=monotonic;
               if(g_trades[i].mfe_r>=G3_EXIT_B_BE_R)
                  g_trades[i].be_done=true;
               dirty=true;
              }
           }
        }

      //--- timeout (section 15)
      if(G3TimeoutShouldClose(InpTimeout,g_trades[i].bars_held,g_trades[i].mfe_r))
        {
         DeviationPlan dev=G3BuildDeviationPlan(tick.ask-tick.bid,
                                                (atr_now>0.0)?atr_now:g_trades[i].atr_at_entry,
                                                (int)SymbolInfoInteger(_Symbol,SYMBOL_DIGITS),
                                                SymbolInfoDouble(_Symbol,SYMBOL_POINT));
         uint rc=0;
         g_timeout_close[i]=true;
         if(!G3ClosePositionVolume(_Symbol,g_trades[i].ticket,
                                   g_trades[i].current_volume,InpMagic,dev,rc))
            g_timeout_close[i]=false;
         else
            dirty=true;
        }
     }

   //--- compact the tracking array
   if(dirty)
     {
      int w=0;
      for(int i=0;i<g_trade_count;i++)
        {
         if(!g_trades[i].active)
            continue;
         if(w!=i)
           {
            g_trades[w]=g_trades[i];
            g_timeout_close[w]=g_timeout_close[i];
           }
         w++;
        }
      g_trade_count=w;
      G3SaveTradeStates(g_ctx,g_trades,g_trade_count);
     }
  }

//+------------------------------------------------------------------+
//| OnTick                                                           |
//+------------------------------------------------------------------+
void OnTick()
  {
   if(!g_init_ok)
      return;

   RefreshAccountState(g_equity,g_dd_pct,g_daily_lock);
   ManagePositions();

   datetime m5_open=0;
   if(!G3IsDecisionTick(_Symbol,g_last_m5_open,m5_open))
      return;
   //--- the very first observed bar only primes the detector; a bar
   //--- whose first tick was not observed is never traded.
   static bool primed=false;
   if(!primed)
     {
      primed=true;
      return;
     }
   EvaluateDecisionTick(m5_open);
  }
//+------------------------------------------------------------------+
