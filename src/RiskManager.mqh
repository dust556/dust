//+------------------------------------------------------------------+
//|                                                  RiskManager.mqh |
//|   Master Specification v0.4 sections 9 and 10 -                  |
//|   stop placement, risk money, lot sizing, drawdown state machine.|
//+------------------------------------------------------------------+
#ifndef G3_RISKMANAGER_MQH
#define G3_RISKMANAGER_MQH

#include "G3Types.mqh"

//--- Spec constants (sections 9,10,11). Not parameterised.
#define G3_SL_ATR_BUFFER        0.20
#define G3_SL_MIN_ATR           1.00
#define G3_SL_MAX_ATR           2.50
#define G3_RISK_PCT_NORMAL      0.50
#define G3_RISK_PCT_MODERATE    0.25
#define G3_RISK_PCT_RESTRICTED  0.10
#define G3_DD_MODERATE_ENTER    6.0
#define G3_DD_RESTRICTED_ENTER  8.0
#define G3_DD_HARD_STOP_ENTER   10.0
#define G3_DD_NORMAL_RECOVER    5.0
#define G3_DD_MODERATE_RECOVER  7.0
#define G3_DD_MANUAL_RESET_MAX  9.0
#define G3_DAILY_LOCK_RATIO     0.98
#define G3_POST_FILL_RISK_MAX   1.05

//+------------------------------------------------------------------+
//| PURE - stop placement                                            |
//+------------------------------------------------------------------+

//--- Raw structural stop (section 9).
//---   BUY : Lowest(Low[1..5])  - 0.20*ATR14[1]
//---   SELL: Highest(High[1..5]) + 0.20*ATR14[1]
double G3RawStop(const ENUM_G3_SIDE side,const double lowest_1_5,
                 const double highest_1_5,const double atr_s1)
  {
   if(side==G3_SIDE_BUY)
      return(lowest_1_5-G3_SL_ATR_BUFFER*atr_s1);
   return(highest_1_5+G3_SL_ATR_BUFFER*atr_s1);
  }

//--- Strategy-side adjustment.
//---   distance < 1.0*ATR -> widened to exactly 1.0*ATR (flagged)
//---   distance > 2.5*ATR -> entry rejected
bool G3AdjustStopStrategy(const ENUM_G3_SIDE side,const double entry_price,
                          const double sl_raw,const double atr_s1,
                          double &sl_strategy_out,bool &adjusted_out,
                          ENUM_G3_REASON &reason_out)
  {
   sl_strategy_out=sl_raw;
   adjusted_out=false;
   reason_out=G3_R_NONE;
   if(atr_s1<=0.0)
     {
      reason_out=G3_R_DATA_UNAVAILABLE;
      return(false);
     }
   double dist=MathAbs(entry_price-sl_raw);
   if(dist<G3_SL_MIN_ATR*atr_s1)
     {
      dist=G3_SL_MIN_ATR*atr_s1;
      adjusted_out=true;
     }
   if(dist>G3_SL_MAX_ATR*atr_s1)
     {
      reason_out=G3_R_SL_DISTANCE_ABOVE_MAX;
      return(false);
     }
   sl_strategy_out=(side==G3_SIDE_BUY)?(entry_price-dist):(entry_price+dist);
   return(true);
  }

//--- Broker-side adjustment against SYMBOL_TRADE_STOPS_LEVEL.
//--- The stop is only ever moved to the safer (further) side, by
//--- StopLevel + 1 point, and the 2.5*ATR ceiling is re-checked after
//--- the broker correction.
//--- `stop_reference_price` is Bid for a BUY and Ask for a SELL.
bool G3AdjustStopBroker(const ENUM_G3_SIDE side,const double entry_price,
                        const double sl_strategy,const double atr_s1,
                        const double stop_reference_price,
                        const long stops_level_points,const double point,
                        double &sl_final_out,bool &adjusted_out,
                        ENUM_G3_REASON &reason_out)
  {
   sl_final_out=sl_strategy;
   adjusted_out=false;
   reason_out=G3_R_NONE;
   if(point<=0.0 || atr_s1<=0.0)
     {
      reason_out=G3_R_DATA_UNAVAILABLE;
      return(false);
     }
   double min_dist=((double)stops_level_points)*point;
   if(min_dist>0.0)
     {
      double cur_dist=MathAbs(stop_reference_price-sl_strategy);
      if(cur_dist<min_dist)
        {
         double safe_dist=min_dist+point;          // StopLevel + 1 point
         sl_final_out=(side==G3_SIDE_BUY)
                      ?(stop_reference_price-safe_dist)
                      :(stop_reference_price+safe_dist);
         adjusted_out=true;
        }
     }
   if(MathAbs(entry_price-sl_final_out)>G3_SL_MAX_ATR*atr_s1)
     {
      reason_out=G3_R_SL_BROKER_ADJ_ABOVE_MAX;
      return(false);
     }
   return(true);
  }

//+------------------------------------------------------------------+
//| PURE - risk and lot sizing                                       |
//+------------------------------------------------------------------+

//--- Risk percentage attached to a drawdown state (section 10).
double G3RiskPctForState(const ENUM_G3_DD_STATE state)
  {
   switch(state)
     {
      case G3_DD_NORMAL:     return(G3_RISK_PCT_NORMAL);
      case G3_DD_MODERATE:   return(G3_RISK_PCT_MODERATE);
      case G3_DD_RESTRICTED: return(G3_RISK_PCT_RESTRICTED);
      case G3_DD_HARD_STOP:  return(0.0);
      case G3_DD_UNCERTAIN:  return(0.0);
     }
   return(0.0);
  }

double G3RiskMoney(const double equity,const double risk_pct)
  {
   if(equity<=0.0 || risk_pct<=0.0)
      return(0.0);
   return(equity*risk_pct/100.0);
  }

//--- Lot sizing. `loss_for_1lot` is |OrderCalcProfit(entry -> SL, 1 lot)|
//--- which is the canonical method mandated by section 9.
//--- Rounding onto the volume step is always floor.
bool G3ComputeLot(const double risk_money,const double loss_for_1lot,
                  const double volume_step,const double volume_min,
                  const double volume_max,
                  double &raw_lot_out,double &final_lot_out,
                  bool &capped_by_max_out,ENUM_G3_REASON &reason_out)
  {
   raw_lot_out=0.0;
   final_lot_out=0.0;
   capped_by_max_out=false;
   reason_out=G3_R_NONE;
   if(loss_for_1lot<=0.0)
     {
      reason_out=G3_R_ORDER_CALC_PROFIT_INVALID;
      return(false);
     }
   if(risk_money<=0.0)
     {
      reason_out=G3_R_HARD_STOP_LATCHED;
      return(false);
     }
   raw_lot_out=risk_money/loss_for_1lot;
   double lot=G3NormalizeVolume(raw_lot_out,volume_step);
   if(volume_max>0.0 && lot>volume_max)
     {
      lot=G3NormalizeVolume(volume_max,volume_step);
      capped_by_max_out=true;
     }
   if(lot<volume_min-1e-12)
     {
      //--- the smallest tradable volume already exceeds RiskMoney
      if(volume_min*loss_for_1lot>risk_money)
         reason_out=G3_R_RISK_MONEY_EXCEEDED_AT_MIN_VOLUME;
      else
         reason_out=G3_R_LOT_BELOW_MIN_VOLUME;
      return(false);
     }
   final_lot_out=lot;
   return(true);
  }

//--- Realised risk of a filled position relative to the risk target.
double G3PostFillRiskRatio(const double loss_for_1lot_at_fill,
                           const double volume,const double risk_money)
  {
   if(risk_money<=0.0)
      return(0.0);
   return((loss_for_1lot_at_fill*volume)/risk_money);
  }

//--- Largest volume that keeps the filled risk within 105% of target.
double G3RiskCappedVolume(const double loss_for_1lot_at_fill,
                          const double risk_money,const double volume_step)
  {
   if(loss_for_1lot_at_fill<=0.0)
      return(0.0);
   double allowed=(risk_money*G3_POST_FILL_RISK_MAX)/loss_for_1lot_at_fill;
   return(G3NormalizeVolume(allowed,volume_step));
  }

//+------------------------------------------------------------------+
//| PURE - drawdown state machine                                    |
//+------------------------------------------------------------------+

//--- ASSUMPTION A-01: drawdown is measured against the stored peak
//--- equity:  DD% = (PeakEquity - Equity) / PeakEquity * 100.
double G3DrawdownPct(const double peak_equity,const double equity)
  {
   if(peak_equity<=0.0)
      return(0.0);
   double dd=(peak_equity-equity)/peak_equity*100.0;
   if(dd<0.0)
      dd=0.0;
   return(dd);
  }

//--- One transition step of the drawdown state machine.
//--- Escalation is immediate; recovery uses the specified hysteresis
//--- and moves one state per evaluation
//--- (RESTRICTED -> MODERATE at DD<7, MODERATE -> NORMAL at DD<5).
//--- DD >= 10% latches HARD_STOP permanently (manual reset only).
ENUM_G3_DD_STATE G3NextDDState(const ENUM_G3_DD_STATE current,const double dd_pct,
                               bool &hard_stop_latched)
  {
   if(current==G3_DD_UNCERTAIN)
      return(G3_DD_UNCERTAIN);
   if(dd_pct>=G3_DD_HARD_STOP_ENTER)
     {
      hard_stop_latched=true;
      return(G3_DD_HARD_STOP);
     }
   if(hard_stop_latched)
      return(G3_DD_HARD_STOP);
   switch(current)
     {
      case G3_DD_NORMAL:
         if(dd_pct>=G3_DD_RESTRICTED_ENTER) return(G3_DD_RESTRICTED);
         if(dd_pct>=G3_DD_MODERATE_ENTER)   return(G3_DD_MODERATE);
         return(G3_DD_NORMAL);
      case G3_DD_MODERATE:
         if(dd_pct>=G3_DD_RESTRICTED_ENTER) return(G3_DD_RESTRICTED);
         if(dd_pct<G3_DD_NORMAL_RECOVER)    return(G3_DD_NORMAL);
         return(G3_DD_MODERATE);
      case G3_DD_RESTRICTED:
         if(dd_pct<G3_DD_MODERATE_RECOVER)  return(G3_DD_MODERATE);
         return(G3_DD_RESTRICTED);
      case G3_DD_HARD_STOP:
         return(G3_DD_HARD_STOP);
      default:
         break;
     }
   return(current);
  }

//--- Manual HARD_STOP reset is only admissible below 9% drawdown and
//--- always writes an audit record (see StateStore.mqh).
bool G3ManualResetAdmissible(const double dd_pct)
  {
   return(dd_pct<G3_DD_MANUAL_RESET_MAX);
  }

//--- DailyEntryLock (section 11).
bool G3DailyEntryLocked(const double daily_start_equity,const double equity)
  {
   if(daily_start_equity<=0.0)
      return(false);
   return(equity<=daily_start_equity*G3_DAILY_LOCK_RATIO);
  }

//+------------------------------------------------------------------+
//| TERMINAL (excluded from the host test harness)                   |
//+------------------------------------------------------------------+
#ifndef G3_HOST_TEST

//--- Canonical 1-lot loss for the entry -> SL leg.
bool G3LossForOneLot(const string symbol,const ENUM_G3_SIDE side,
                     const double entry_price,const double sl_price,
                     double &loss_out)
  {
   loss_out=0.0;
   ENUM_ORDER_TYPE type=(side==G3_SIDE_BUY)?ORDER_TYPE_BUY:ORDER_TYPE_SELL;
   double profit=0.0;
   if(!OrderCalcProfit(type,symbol,1.0,entry_price,sl_price,profit))
      return(false);
   loss_out=MathAbs(profit);
   return(loss_out>0.0);
  }

#endif // G3_HOST_TEST

#endif // G3_RISKMANAGER_MQH
//+------------------------------------------------------------------+
