//+------------------------------------------------------------------+
//|                                                MarketFilters.mqh |
//|   Master Specification v0.4 section 8 - volatility / spread      |
//|   filters, market quality score and the effective threshold.     |
//|                                                                  |
//|   Total score is 8 points: H4 0-2, M15 0-2, M5 0-2,              |
//|   Volatility 0-1, Spread 0-1.                                    |
//+------------------------------------------------------------------+
#ifndef G3_MARKETFILTERS_MQH
#define G3_MARKETFILTERS_MQH

#include "G3Types.mqh"

//--- Spec constants (section 8). Not parameterised.
#define G3_VOL_RATIO_MIN        0.80
#define G3_VOL_RATIO_MAX        1.80
#define G3_VOL_RATIO_BLOCK      2.50
#define G3_SPREAD_RATIO_POINT   0.12
#define G3_SPREAD_RATIO_ZERO    0.20
#define G3_SCORE_MAX            8
#define G3_RESTRICTED_SCORE_TH  6

//+------------------------------------------------------------------+
//| PURE                                                             |
//+------------------------------------------------------------------+

//--- VolRatio = ATR14[1] / median(ATR14 of shifts 2..101)
bool G3VolRatio(const double atr_s1,const DoubleSeries &atr_2_101,double &ratio_out)
  {
   ratio_out=0.0;
   double med=0.0;
   if(!G3Median(atr_2_101,med))
      return(false);
   if(med<=0.0)
      return(false);
   ratio_out=atr_s1/med;
   return(true);
  }

//--- 1 point inside [0.80,1.80], otherwise 0.
int G3VolScore(const double vol_ratio)
  {
   if(vol_ratio>=G3_VOL_RATIO_MIN && vol_ratio<=G3_VOL_RATIO_MAX)
      return(1);
   return(0);
  }

//--- VolRatio > 2.50 forbids new entries entirely.
bool G3VolBlocksEntry(const double vol_ratio)
  {
   return(vol_ratio>G3_VOL_RATIO_BLOCK);
  }

//--- SpreadRatio = (Ask-Bid) / ATR14[1]
bool G3SpreadRatio(const double ask,const double bid,const double atr_s1,double &ratio_out)
  {
   ratio_out=0.0;
   if(atr_s1<=0.0)
      return(false);
   double spread=ask-bid;
   if(spread<0.0)
      return(false);
   ratio_out=spread/atr_s1;
   return(true);
  }

//--- 1 point when SpreadRatio <= 0.12, 0 points in (0.12,0.20].
int G3SpreadScore(const double spread_ratio)
  {
   if(spread_ratio<=G3_SPREAD_RATIO_POINT)
      return(1);
   return(0);
  }

//--- SpreadRatio > 0.20 forbids new entries entirely.
bool G3SpreadBlocksEntry(const double spread_ratio)
  {
   return(spread_ratio>G3_SPREAD_RATIO_ZERO);
  }

//--- Market quality total score (0..8).
int G3TotalScore(const int h4,const int m15,const int m5,
                 const int vol,const int spread)
  {
   return(h4+m15+m5+vol+spread);
  }

//--- Effective score threshold.
//--- Master Specification v0.4 section 8/10: the RESTRICTED drawdown
//--- state forces ScoreThreshold = 6; otherwise the G3 registered input
//--- (4/5/6, baseline 5) applies. See ISSUE-004 for the documented
//--- reading of the interaction between the input and the DD table.
int G3EffectiveScoreThreshold(const int input_threshold,const ENUM_G3_DD_STATE dd_state)
  {
   if(dd_state==G3_DD_RESTRICTED)
      return((input_threshold>G3_RESTRICTED_SCORE_TH)?input_threshold:G3_RESTRICTED_SCORE_TH);
   return(input_threshold);
  }

#endif // G3_MARKETFILTERS_MQH
//+------------------------------------------------------------------+
