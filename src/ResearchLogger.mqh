//+------------------------------------------------------------------+
//|                                               ResearchLogger.mqh |
//|   Master Specification v0.4 section 16 - research CSV log.       |
//|                                                                  |
//|   Every decision_tick produces an EVAL record, including the     |
//|   candidates that are skipped. Executed orders add an ENTRY      |
//|   record and, on close, an EXIT record. All three record types   |
//|   share one schema and are joined on signal_id.                  |
//|                                                                  |
//|   The exact column list is mirrored in schema/research_log_schema.md
//+------------------------------------------------------------------+
#ifndef G3_RESEARCHLOGGER_MQH
#define G3_RESEARCHLOGGER_MQH

#include "G3Types.mqh"
#include "PortfolioManager.mqh"
#include "ExitManager.mqh"

#define G3_LOG_SCHEMA_VERSION "1"
//--- Master Specification v0.4 does not define fakeout_3 / fakeout_6.
//--- The columns exist but are never populated with an invented value.
//--- See docs/change_requests.md CR-002.
#define G3_UNDEFINED_TOKEN "NA_SPEC_UNDEFINED"

struct G3LogRecord
  {
   string            record_type;        // EVAL | ENTRY | EXIT
   long              time_server;
   long              time_utc;
   string            symbol;
   ENUM_G3_SIDE      side;
   string            signal_id;
   //--- scores
   int               h4_score;
   int               m15_score;
   int               m5_score;
   int               vol_score;
   int               spread_score;
   int               total_score;
   int               score_threshold_effective;
   int               score_threshold_input;
   //--- bar synchronisation
   long              h4_bar_time;
   long              m15_bar_time;
   long              m5_bar_time;
   long              signal_close_time;
   //--- market context
   double            atr_m5;
   double            atr_m15;
   double            atr_h4;
   double            vol_ratio;
   double            spread_ratio;
   //--- feature flags
   bool              f_h4_direction;
   bool              f_h4_slope;
   bool              f_h4_adx;
   bool              f_m15_pullback;
   bool              f_m15_structure;
   bool              f_m5_breakout;
   bool              f_m5_candle;
   bool              f_m5_momentum;
   bool              f_vol_point;
   bool              f_spread_point;
   bool              f_vol_block;
   bool              f_spread_block;
   double            h4_slope_value;
   double            adx_value;
   double            plus_di;
   double            minus_di;
   //--- stops
   double            sl_raw;
   double            sl_strategy;
   double            sl_final;
   bool              sl_strategy_adjusted;
   bool              sl_broker_adjusted;
   long              stops_level;
   long              freeze_level;
   //--- sizing
   double            risk_pct;
   double            risk_money;
   double            raw_lot;
   double            final_lot;
   bool              lot_capped_by_max;
   double            order_calc_profit_1lot;
   //--- execution
   long              deviation_computed;
   long              deviation_hard_cap;
   long              deviation_points;
   bool              deviation_cap_hit;
   double            requested_price;
   double            fill_price;
   double            slippage_points;
   bool              execution_risk_violation;
   double            post_fill_risk_ratio;
   //--- exit management
   int               exit_mode;
   int               timeout_bars;
   string            partial_status;
   double            partial_close_ratio;
   double            mfe_r;
   double            mae_r;
   double            mfe_r_3bars;
   double            mae_r_3bars;
   double            mfe_r_6bars;
   double            mae_r_6bars;
   int               holding_bars;
   string            exit_reason;
   double            result_r;
   double            realized_pl;
   //--- account / state
   double            dd_pct;
   ENUM_G3_DD_STATE  dd_state;
   bool              daily_lock;
   bool              hard_stop_latched;
   double            peak_equity;
   double            equity;
   double            balance;
   //--- portfolio
   double            total_risk_pct;
   double            currency_exposure_pct;
   double            corr_cluster_risk;
   double            corr_cluster_risk_raw;
   ENUM_G3_CORR_STATE corr_state;
   int               corr_warmup_days;
   double            unknown_cluster_risk;
   int               open_positions;
   //--- outcome / diagnostics
   ENUM_G3_REASON    skip_reason;
   uint              retcode;
   ENUM_G3_STORE_STATUS store_status;
   string            run_id;
  };

void G3LogRecordInit(G3LogRecord &r)
  {
   r.record_type="EVAL";
   r.time_server=0;             r.time_utc=0;
   r.symbol="";                 r.side=G3_SIDE_NONE;
   r.signal_id="";
   r.h4_score=0;  r.m15_score=0; r.m5_score=0;
   r.vol_score=0; r.spread_score=0; r.total_score=0;
   r.score_threshold_effective=0; r.score_threshold_input=0;
   r.h4_bar_time=0; r.m15_bar_time=0; r.m5_bar_time=0; r.signal_close_time=0;
   r.atr_m5=0.0; r.atr_m15=0.0; r.atr_h4=0.0;
   r.vol_ratio=0.0; r.spread_ratio=0.0;
   r.f_h4_direction=false; r.f_h4_slope=false; r.f_h4_adx=false;
   r.f_m15_pullback=false; r.f_m15_structure=false;
   r.f_m5_breakout=false;  r.f_m5_candle=false; r.f_m5_momentum=false;
   r.f_vol_point=false;    r.f_spread_point=false;
   r.f_vol_block=false;    r.f_spread_block=false;
   r.h4_slope_value=0.0; r.adx_value=0.0; r.plus_di=0.0; r.minus_di=0.0;
   r.sl_raw=0.0; r.sl_strategy=0.0; r.sl_final=0.0;
   r.sl_strategy_adjusted=false; r.sl_broker_adjusted=false;
   r.stops_level=0; r.freeze_level=0;
   r.risk_pct=0.0; r.risk_money=0.0; r.raw_lot=0.0; r.final_lot=0.0;
   r.lot_capped_by_max=false; r.order_calc_profit_1lot=0.0;
   r.deviation_computed=0; r.deviation_hard_cap=0; r.deviation_points=0;
   r.deviation_cap_hit=false;
   r.requested_price=0.0; r.fill_price=0.0; r.slippage_points=0.0;
   r.execution_risk_violation=false; r.post_fill_risk_ratio=0.0;
   r.exit_mode=0; r.timeout_bars=0;
   r.partial_status="NONE"; r.partial_close_ratio=0.0;
   r.mfe_r=0.0; r.mae_r=0.0;
   r.mfe_r_3bars=0.0; r.mae_r_3bars=0.0;
   r.mfe_r_6bars=0.0; r.mae_r_6bars=0.0;
   r.holding_bars=0; r.exit_reason=""; r.result_r=0.0; r.realized_pl=0.0;
   r.dd_pct=0.0; r.dd_state=G3_DD_NORMAL; r.daily_lock=false;
   r.hard_stop_latched=false;
   r.peak_equity=0.0; r.equity=0.0; r.balance=0.0;
   r.total_risk_pct=0.0; r.currency_exposure_pct=0.0;
   r.corr_cluster_risk=0.0; r.corr_cluster_risk_raw=0.0;
   r.corr_state=G3_CORR_READY; r.corr_warmup_days=0;
   r.unknown_cluster_risk=0.0; r.open_positions=0;
   r.skip_reason=G3_R_NONE; r.retcode=0;
   r.store_status=G3_STORE_FRESH; r.run_id="";
  }

//+------------------------------------------------------------------+
//| PURE - schema                                                    |
//+------------------------------------------------------------------+
string G3LogHeader()
  {
   string h="";
   h=h+"record_type,time_server,time_utc,symbol,side,signal_id,";
   h=h+"h4_score,m15_score,m5_score,vol_score,spread_score,total_score,";
   h=h+"score_threshold_effective,score_threshold_input,";
   h=h+"h4_bar_time,m15_bar_time,m5_bar_time,signal_close_time,";
   h=h+"atr_m5,atr_m15,atr_h4,vol_ratio,spread_ratio,";
   h=h+"f_h4_direction,f_h4_slope,f_h4_adx,f_m15_pullback,f_m15_structure,";
   h=h+"f_m5_breakout,f_m5_candle,f_m5_momentum,f_vol_point,f_spread_point,";
   h=h+"f_vol_block,f_spread_block,";
   h=h+"h4_slope_value,adx_value,plus_di,minus_di,";
   h=h+"sl_raw,sl_strategy,sl_final,sl_strategy_adjusted,sl_broker_adjusted,";
   h=h+"stops_level,freeze_level,";
   h=h+"risk_pct,risk_money,raw_lot,final_lot,lot_capped_by_max,order_calc_profit_1lot,";
   h=h+"deviation_computed,deviation_hard_cap,deviation_points,deviation_cap_hit,";
   h=h+"requested_price,fill_price,slippage_points,execution_risk_violation,post_fill_risk_ratio,";
   h=h+"exit_mode,timeout_bars,partial_status,partial_close_ratio,";
   h=h+"mfe_r,mae_r,mfe_r_3bars,mae_r_3bars,mfe_r_6bars,mae_r_6bars,";
   h=h+"fakeout_3,fakeout_6,";
   h=h+"holding_bars,exit_reason,result_R,realized_pl,";
   h=h+"dd_pct,dd_state,daily_lock,hard_stop_latched,peak_equity,equity,balance,";
   h=h+"total_risk,currency_exposure,corr_cluster_risk,corr_cluster_risk_raw,";
   h=h+"corr_state,corr_warmup_days,unknown_cluster_risk,open_positions,";
   h=h+"skip_reason,retcode,state_store_status,run_id";
   return(h);
  }

string G3Bool(const bool b)
  {
   return(b?"1":"0");
  }

string G3LogRecordToLine(const G3LogRecord &r)
  {
   string s="";
   s=s+r.record_type+",";
   s=s+IntegerToString(r.time_server)+","+IntegerToString(r.time_utc)+",";
   s=s+r.symbol+","+G3SideToString(r.side)+","+r.signal_id+",";
   s=s+IntegerToString(r.h4_score)+","+IntegerToString(r.m15_score)+","
      +IntegerToString(r.m5_score)+","+IntegerToString(r.vol_score)+","
      +IntegerToString(r.spread_score)+","+IntegerToString(r.total_score)+",";
   s=s+IntegerToString(r.score_threshold_effective)+","
      +IntegerToString(r.score_threshold_input)+",";
   s=s+IntegerToString(r.h4_bar_time)+","+IntegerToString(r.m15_bar_time)+","
      +IntegerToString(r.m5_bar_time)+","+IntegerToString(r.signal_close_time)+",";
   s=s+DoubleToString(r.atr_m5,8)+","+DoubleToString(r.atr_m15,8)+","
      +DoubleToString(r.atr_h4,8)+","+DoubleToString(r.vol_ratio,6)+","
      +DoubleToString(r.spread_ratio,6)+",";
   s=s+G3Bool(r.f_h4_direction)+","+G3Bool(r.f_h4_slope)+","+G3Bool(r.f_h4_adx)+","
      +G3Bool(r.f_m15_pullback)+","+G3Bool(r.f_m15_structure)+",";
   s=s+G3Bool(r.f_m5_breakout)+","+G3Bool(r.f_m5_candle)+","+G3Bool(r.f_m5_momentum)+","
      +G3Bool(r.f_vol_point)+","+G3Bool(r.f_spread_point)+",";
   s=s+G3Bool(r.f_vol_block)+","+G3Bool(r.f_spread_block)+",";
   s=s+DoubleToString(r.h4_slope_value,6)+","+DoubleToString(r.adx_value,4)+","
      +DoubleToString(r.plus_di,4)+","+DoubleToString(r.minus_di,4)+",";
   s=s+DoubleToString(r.sl_raw,8)+","+DoubleToString(r.sl_strategy,8)+","
      +DoubleToString(r.sl_final,8)+","+G3Bool(r.sl_strategy_adjusted)+","
      +G3Bool(r.sl_broker_adjusted)+",";
   s=s+IntegerToString(r.stops_level)+","+IntegerToString(r.freeze_level)+",";
   s=s+DoubleToString(r.risk_pct,4)+","+DoubleToString(r.risk_money,4)+","
      +DoubleToString(r.raw_lot,6)+","+DoubleToString(r.final_lot,4)+","
      +G3Bool(r.lot_capped_by_max)+","+DoubleToString(r.order_calc_profit_1lot,6)+",";
   s=s+IntegerToString(r.deviation_computed)+","+IntegerToString(r.deviation_hard_cap)+","
      +IntegerToString(r.deviation_points)+","+G3Bool(r.deviation_cap_hit)+",";
   s=s+DoubleToString(r.requested_price,8)+","+DoubleToString(r.fill_price,8)+","
      +DoubleToString(r.slippage_points,3)+","+G3Bool(r.execution_risk_violation)+","
      +DoubleToString(r.post_fill_risk_ratio,6)+",";
   s=s+IntegerToString(r.exit_mode)+","+IntegerToString(r.timeout_bars)+","
      +r.partial_status+","+DoubleToString(r.partial_close_ratio,4)+",";
   s=s+DoubleToString(r.mfe_r,6)+","+DoubleToString(r.mae_r,6)+","
      +DoubleToString(r.mfe_r_3bars,6)+","+DoubleToString(r.mae_r_3bars,6)+","
      +DoubleToString(r.mfe_r_6bars,6)+","+DoubleToString(r.mae_r_6bars,6)+",";
   s=s+G3_UNDEFINED_TOKEN+","+G3_UNDEFINED_TOKEN+",";
   s=s+IntegerToString(r.holding_bars)+","+r.exit_reason+","
      +DoubleToString(r.result_r,6)+","+DoubleToString(r.realized_pl,4)+",";
   s=s+DoubleToString(r.dd_pct,4)+","+G3DDStateToString(r.dd_state)+","
      +G3Bool(r.daily_lock)+","+G3Bool(r.hard_stop_latched)+","
      +DoubleToString(r.peak_equity,2)+","+DoubleToString(r.equity,2)+","
      +DoubleToString(r.balance,2)+",";
   s=s+DoubleToString(r.total_risk_pct,4)+","+DoubleToString(r.currency_exposure_pct,4)+","
      +DoubleToString(r.corr_cluster_risk,4)+","+DoubleToString(r.corr_cluster_risk_raw,4)+",";
   s=s+G3CorrStateToString(r.corr_state)+","+IntegerToString(r.corr_warmup_days)+","
      +DoubleToString(r.unknown_cluster_risk,4)+","+IntegerToString(r.open_positions)+",";
   s=s+G3ReasonToString(r.skip_reason)+","+IntegerToString((long)r.retcode)+","
      +G3StoreStatusToString(r.store_status)+","+r.run_id;
   return(s);
  }

//--- number of columns produced by G3LogHeader()
int G3LogColumnCount()
  {
   string h=G3LogHeader();
   int n=1;
   int len=StringLen(h);
   for(int i=0;i<len;i++)
     {
      if(StringGetCharacter(h,i)==44)   // ','
         n++;
     }
   return(n);
  }

int G3LogLineColumnCount(const string line)
  {
   int n=1;
   int len=StringLen(line);
   for(int i=0;i<len;i++)
     {
      if(StringGetCharacter(line,i)==44)
         n++;
     }
   return(n);
  }

//+------------------------------------------------------------------+
//| TERMINAL (excluded from the host test harness)                   |
//+------------------------------------------------------------------+
#ifndef G3_HOST_TEST

struct G3Logger
  {
   int               handle;
   string            path;
   string            run_id;
   int               pending;
  };

bool G3LoggerOpen(G3Logger &lg,const string symbol,const long magic,const string run_id)
  {
   lg.handle=INVALID_HANDLE;
   lg.run_id=run_id;
   lg.pending=0;
   long account=AccountInfoInteger(ACCOUNT_LOGIN);
   lg.path="G3RSRCH\\log_"+IntegerToString(account)+"_"+IntegerToString(magic)+"_"
           +symbol+"_"+run_id+".csv";
   bool fresh=!FileIsExist(lg.path,FILE_COMMON);
   lg.handle=FileOpen(lg.path,FILE_READ|FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_COMMON,',');
   if(lg.handle==INVALID_HANDLE)
      return(false);
   FileSeek(lg.handle,0,SEEK_END);
   if(fresh)
     {
      FileWriteString(lg.handle,G3LogHeader()+"\r\n");
      FileFlush(lg.handle);
     }
   return(true);
  }

void G3LoggerWrite(G3Logger &lg,G3LogRecord &r)
  {
   if(lg.handle==INVALID_HANDLE)
      return;
   r.run_id=lg.run_id;
   FileWriteString(lg.handle,G3LogRecordToLine(r)+"\r\n");
   lg.pending++;
   if(lg.pending>=50)
     {
      FileFlush(lg.handle);
      lg.pending=0;
     }
  }

void G3LoggerClose(G3Logger &lg)
  {
   if(lg.handle!=INVALID_HANDLE)
     {
      FileFlush(lg.handle);
      FileClose(lg.handle);
      lg.handle=INVALID_HANDLE;
     }
  }

#endif // G3_HOST_TEST

#endif // G3_RESEARCHLOGGER_MQH
//+------------------------------------------------------------------+
