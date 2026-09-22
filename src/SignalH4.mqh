//+------------------------------------------------------------------+
//|                                                     SignalH4.mqh |
//|        Master Specification v0.4 section 5 - H4 direction gate   |
//|        and H4 quality score (0-2).                               |
//|                                                                  |
//|  Index convention: every value handed to the pure functions is    |
//|  taken from the H4 reference bar resolved by TimeSync (the last   |
//|  bar fully closed at signal_close_time). "ref_minus3" means three |
//|  H4 bars older than the reference bar.                            |
//+------------------------------------------------------------------+
#ifndef G3_SIGNALH4_MQH
#define G3_SIGNALH4_MQH

#include "G3Types.mqh"

struct H4Input
  {
   double            close_ref;
   double            ema50_ref;
   double            ema50_ref_minus3;
   double            ema200_ref;
   double            atr14_ref;
   double            adx14_ref;
   double            plus_di_ref;
   double            minus_di_ref;
  };

//+------------------------------------------------------------------+
//| PURE                                                             |
//+------------------------------------------------------------------+

//--- Direction gate. No points are awarded for the gate itself.
//---   BUY : EMA50 > EMA200 AND Close > EMA200
//---   SELL: EMA50 < EMA200 AND Close < EMA200
bool G3H4DirectionGate(const H4Input &in,const ENUM_G3_SIDE side)
  {
   if(side==G3_SIDE_BUY)
      return(in.ema50_ref>in.ema200_ref && in.close_ref>in.ema200_ref);
   if(side==G3_SIDE_SELL)
      return(in.ema50_ref<in.ema200_ref && in.close_ref<in.ema200_ref);
   return(false);
  }

//--- Resolve the direction the H4 gate currently allows (if any).
ENUM_G3_SIDE G3H4Direction(const H4Input &in)
  {
   if(G3H4DirectionGate(in,G3_SIDE_BUY))
      return(G3_SIDE_BUY);
   if(G3H4DirectionGate(in,G3_SIDE_SELL))
      return(G3_SIDE_SELL);
   return(G3_SIDE_NONE);
  }

//--- EMA50 slope normalised by ATR14 of the reference bar.
bool G3H4SlopeValue(const H4Input &in,double &slope_out)
  {
   slope_out=0.0;
   if(in.atr14_ref<=0.0)
      return(false);
   slope_out=(in.ema50_ref-in.ema50_ref_minus3)/in.atr14_ref;
   return(true);
  }

//--- 1 point: BUY slope > +0.10 ; SELL slope < -0.10
bool G3H4SlopeFlag(const H4Input &in,const ENUM_G3_SIDE side)
  {
   double slope=0.0;
   if(!G3H4SlopeValue(in,slope))
      return(false);
   if(side==G3_SIDE_BUY)
      return(slope>0.10);
   if(side==G3_SIDE_SELL)
      return(slope<-0.10);
   return(false);
  }

//--- 1 point: ADX14 >= 20 and the dominant DI agrees with the side.
bool G3H4AdxFlag(const H4Input &in,const ENUM_G3_SIDE side)
  {
   if(in.adx14_ref<20.0)
      return(false);
   if(side==G3_SIDE_BUY)
      return(in.plus_di_ref>in.minus_di_ref);
   if(side==G3_SIDE_SELL)
      return(in.minus_di_ref>in.plus_di_ref);
   return(false);
  }

//--- H4 quality score, 0..2. Minimum required by the spec is 1.
int G3H4Score(const H4Input &in,const ENUM_G3_SIDE side,
              bool &slope_flag_out,bool &adx_flag_out)
  {
   slope_flag_out=G3H4SlopeFlag(in,side);
   adx_flag_out=G3H4AdxFlag(in,side);
   int score=0;
   if(slope_flag_out) score++;
   if(adx_flag_out)   score++;
   return(score);
  }

#define G3_H4_MIN_SCORE 1

#endif // G3_SIGNALH4_MQH
//+------------------------------------------------------------------+
