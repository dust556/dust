//+------------------------------------------------------------------+
//|                                                    TriggerM5.mqh |
//|        Master Specification v0.4 section 7 - M5 trigger          |
//|                                                                  |
//|  M5 shifts are literal series shifts of the decision_tick symbol: |
//|  shift 0 is the forming bar and is never used for a decision,     |
//|  shift 1 is the signal bar, shifts 2..6 are the breakout window.  |
//+------------------------------------------------------------------+
#ifndef G3_TRIGGERM5_MQH
#define G3_TRIGGERM5_MQH

#include "G3Types.mqh"

struct M5Input
  {
   double            open_s1;
   double            high_s1;
   double            low_s1;
   double            close_s1;
   double            highest_2_6;   // Highest(High[2..6])
   double            lowest_2_6;    // Lowest(Low[2..6])
   double            ema9_s1;
   double            ema9_s4;
   double            ema20_s1;
  };

//+------------------------------------------------------------------+
//| PURE                                                             |
//+------------------------------------------------------------------+

//--- Hard gate: breakout of the 2..6 reference window.
bool G3M5BreakoutFlag(const M5Input &in,const ENUM_G3_SIDE side)
  {
   if(side==G3_SIDE_BUY)
      return(in.close_s1>in.highest_2_6);
   if(side==G3_SIDE_SELL)
      return(in.close_s1<in.lowest_2_6);
   return(false);
  }

//--- Candle quality, 1 point:
//---   body/range >= 0.60 AND close inside the leading 25% of the range.
bool G3M5CandleFlag(const M5Input &in,const ENUM_G3_SIDE side)
  {
   double range=in.high_s1-in.low_s1;
   if(range<=0.0)
      return(false);
   double body=MathAbs(in.close_s1-in.open_s1);
   if((body/range)<0.60)
      return(false);
   if(side==G3_SIDE_BUY)
      return(in.close_s1>=in.high_s1-0.25*range);
   if(side==G3_SIDE_SELL)
      return(in.close_s1<=in.low_s1+0.25*range);
   return(false);
  }

//--- Momentum, 1 point:
//---   BUY : EMA9[1] > EMA20[1] AND EMA9[1] > EMA9[4]
//---   SELL: EMA9[1] < EMA20[1] AND EMA9[1] < EMA9[4]
bool G3M5MomentumFlag(const M5Input &in,const ENUM_G3_SIDE side)
  {
   if(side==G3_SIDE_BUY)
      return(in.ema9_s1>in.ema20_s1 && in.ema9_s1>in.ema9_s4);
   if(side==G3_SIDE_SELL)
      return(in.ema9_s1<in.ema20_s1 && in.ema9_s1<in.ema9_s4);
   return(false);
  }

//--- M5 trigger quality score, 0..2. Minimum required by the spec is 1.
int G3M5Score(const M5Input &in,const ENUM_G3_SIDE side,
              bool &candle_flag_out,bool &momentum_flag_out)
  {
   candle_flag_out=G3M5CandleFlag(in,side);
   momentum_flag_out=G3M5MomentumFlag(in,side);
   int score=0;
   if(candle_flag_out)   score++;
   if(momentum_flag_out) score++;
   return(score);
  }

#define G3_M5_MIN_SCORE 1

#endif // G3_TRIGGERM5_MQH
//+------------------------------------------------------------------+
