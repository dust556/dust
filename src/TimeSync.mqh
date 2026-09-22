//+------------------------------------------------------------------+
//|                                                     TimeSync.mqh |
//|         Master Specification v0.4 section 4.1 - MTF time sync    |
//|                                                                  |
//|  Rules implemented here:                                         |
//|   * decision_tick     = first tick of a new M5 bar               |
//|   * signal_close_time = close time of the immediately preceding  |
//|                         M5 bar (== open time of the new M5 bar)  |
//|   * H4 / M15 reference bar is NOT a fixed shift=1: it is the     |
//|     last bar that is fully closed at or before signal_close_time |
//|     resolved from the iTime series.                              |
//|   * a forming H4 / M15 bar is never referenced.                  |
//+------------------------------------------------------------------+
#ifndef G3_TIMESYNC_MQH
#define G3_TIMESYNC_MQH

#include "G3Types.mqh"

//+------------------------------------------------------------------+
//| PURE                                                             |
//+------------------------------------------------------------------+

//--- A bar is "fully closed at signal_close_time" when
//---      open_time + period_seconds <= signal_close_time.
//--- open_times must be in series order (index 0 = newest bar, which
//--- is normally the forming bar).
//--- Returns the series index of the newest fully closed bar, or -1.
int G3ResolveClosedBarIndex(const LongSeries &open_times,
                            const long period_seconds,
                            const long signal_close_time)
  {
   if(open_times.n<=0 || period_seconds<=0)
      return(-1);
   for(int i=0;i<open_times.n;i++)
     {
      if(open_times.v[i]+period_seconds<=signal_close_time)
         return(i);
     }
   return(-1);
  }

//--- True when the resolved reference bar is unusable because the
//--- requested history depth behind it is not available.
bool G3HasDepthBehind(const LongSeries &open_times,const int index,const int needed_bars)
  {
   if(index<0)
      return(false);
   return((index+needed_bars)<=open_times.n);
  }

//--- Master Specification v0.4 section 4.2 - gap detection.
//--- A gap is an interval between two consecutive higher timeframe bars
//--- that exceeds twice the normal period of that timeframe. The bar at
//--- `index` is the first bar completed after such a gap when the step
//--- from the previous (older) bar exceeds 2 x period.
//--- When the older neighbour is not available the bar is not flagged;
//--- callers guarantee history depth through G3HasDepthBehind().
bool G3IsPostGapBar(const LongSeries &open_times,const int index,
                    const long period_seconds)
  {
   if(index<0 || period_seconds<=0)
      return(false);
   if(index+1>=open_times.n)
      return(false);
   long delta=open_times.v[index]-open_times.v[index+1];
   return(delta>2*period_seconds);
  }

//--- signal_id text form: "<symbol>#<m5_bar_open_time_seconds>"
string G3BuildSignalId(const string symbol,const long m5_bar_open_time)
  {
   return(symbol+"#"+IntegerToString(m5_bar_open_time));
  }


//+------------------------------------------------------------------+
//| TERMINAL (excluded from the host test harness)                   |
//+------------------------------------------------------------------+
#ifndef G3_HOST_TEST

//--- Copy the newest `count` bar open times of `tf` in series order.
bool G3CopyOpenTimes(const string symbol,const ENUM_TIMEFRAMES tf,
                     const int count,LongSeries &out)
  {
   out.n=0;
   if(count<=0 || count>G3_MAX_SERIES)
      return(false);
   datetime buf[];
   ArraySetAsSeries(buf,true);
   int copied=CopyTime(symbol,tf,0,count,buf);
   if(copied<=0)
      return(false);
   for(int i=0;i<copied;i++)
      out.v[i]=(long)buf[i];
   out.n=copied;
   return(true);
  }

//--- Resolve the higher timeframe reference bar for signal_close_time.
//--- `needed_bars` is the history depth required behind the reference
//--- bar (e.g. EMA200 warm-up, slope look-back).
bool G3ResolveHtfBar(const string symbol,const ENUM_TIMEFRAMES tf,
                     const datetime signal_close_time,const int needed_bars,
                     int &index_out,datetime &bar_open_time_out,
                     bool &post_gap_out)
  {
   index_out=-1;
   bar_open_time_out=0;
   post_gap_out=false;
   LongSeries times;
   int depth=needed_bars+8;
   if(depth>G3_MAX_SERIES)
      depth=G3_MAX_SERIES;
   if(!G3CopyOpenTimes(symbol,tf,depth,times))
      return(false);
   int idx=G3ResolveClosedBarIndex(times,(long)PeriodSeconds(tf),(long)signal_close_time);
   if(idx<0)
      return(false);
   if(!G3HasDepthBehind(times,idx,needed_bars))
      return(false);
   index_out=idx;
   bar_open_time_out=(datetime)times.v[idx];
   post_gap_out=G3IsPostGapBar(times,idx,(long)PeriodSeconds(tf));
   return(true);
  }

//--- decision_tick detection: returns true exactly on the first tick
//--- processed after a new M5 bar has opened.
bool G3IsDecisionTick(const string symbol,datetime &last_seen_m5_open,
                      datetime &m5_open_out)
  {
   datetime t[];
   ArraySetAsSeries(t,true);
   if(CopyTime(symbol,PERIOD_M5,0,1,t)<1)
      return(false);
   m5_open_out=t[0];
   if(t[0]==last_seen_m5_open)
      return(false);
   last_seen_m5_open=t[0];
   return(true);
  }

//--- signal_close_time == close of the previous M5 bar == open of the
//--- M5 bar that has just started.
datetime G3SignalCloseTime(const datetime m5_bar_open)
  {
   return(m5_bar_open);
  }

#endif // G3_HOST_TEST

#endif // G3_TIMESYNC_MQH
//+------------------------------------------------------------------+
