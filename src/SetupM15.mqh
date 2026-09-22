//+------------------------------------------------------------------+
//|                                                     SetupM15.mqh |
//|        Master Specification v0.4 section 6 - M15 setup (0-2)     |
//|                                                                  |
//|  Shift convention: spec shift 1 is the M15 reference bar resolved |
//|  by TimeSync (last bar fully closed at signal_close_time).        |
//|  Spec shift k  ->  series index ref_index + (k-1).                |
//+------------------------------------------------------------------+
#ifndef G3_SETUPM15_MQH
#define G3_SETUPM15_MQH

#include "G3Types.mqh"

struct M15Input
  {
   double            low[3];      // spec shifts 1,2,3
   double            high[3];     // spec shifts 1,2,3
   double            ema20[3];    // spec shifts 1,2,3 (same shift as low/high)
   double            close_s1;    // spec shift 1
   double            ema20_s1;
   double            ema20_s4;
   double            ema50_s1;
   double            atr14_s1;    // ASSUMPTION A-03: ATR14 of spec shift 1
  };

//+------------------------------------------------------------------+
//| PURE                                                             |
//+------------------------------------------------------------------+

//--- Pullback, 1 point. Only spec shifts 1,2,3 are inspected.
//---   BUY : any Low[k] <= EMA20[k] + 0.20*ATR  AND  Close[1] > EMA20[1]
//---   SELL: any High[k] >= EMA20[k] - 0.20*ATR AND  Close[1] < EMA20[1]
bool G3M15PullbackFlag(const M15Input &in,const ENUM_G3_SIDE side)
  {
   if(in.atr14_s1<=0.0)
      return(false);
   double band=0.20*in.atr14_s1;
   if(side==G3_SIDE_BUY)
     {
      if(!(in.close_s1>in.ema20_s1))
         return(false);
      for(int k=0;k<3;k++)
        {
         if(in.low[k]<=in.ema20[k]+band)
            return(true);
        }
      return(false);
     }
   if(side==G3_SIDE_SELL)
     {
      if(!(in.close_s1<in.ema20_s1))
         return(false);
      for(int k=0;k<3;k++)
        {
         if(in.high[k]>=in.ema20[k]-band)
            return(true);
        }
      return(false);
     }
   return(false);
  }

//--- Structure, 1 point.
//---   BUY : EMA20[1] > EMA50[1] AND EMA20[1] > EMA20[4]
//---   SELL: EMA20[1] < EMA50[1] AND EMA20[1] < EMA20[4]
bool G3M15StructureFlag(const M15Input &in,const ENUM_G3_SIDE side)
  {
   if(side==G3_SIDE_BUY)
      return(in.ema20_s1>in.ema50_s1 && in.ema20_s1>in.ema20_s4);
   if(side==G3_SIDE_SELL)
      return(in.ema20_s1<in.ema50_s1 && in.ema20_s1<in.ema20_s4);
   return(false);
  }

//--- M15 setup score, 0..2. Master Specification v0.4 states no
//--- minimum for M15 (only H4 >= 1 and M5 >= 1 are hard minimums).
int G3M15Score(const M15Input &in,const ENUM_G3_SIDE side,
               bool &pullback_flag_out,bool &structure_flag_out)
  {
   pullback_flag_out=G3M15PullbackFlag(in,side);
   structure_flag_out=G3M15StructureFlag(in,side);
   int score=0;
   if(pullback_flag_out)  score++;
   if(structure_flag_out) score++;
   return(score);
  }

#endif // G3_SETUPM15_MQH
//+------------------------------------------------------------------+
