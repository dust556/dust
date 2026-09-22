//+------------------------------------------------------------------+
//|                                                  ExitManager.mqh |
//|   Master Specification v0.4 sections 14 and 15 -                 |
//|   exit modes A/B/C, partial close, monotonic trailing, timeout.  |
//+------------------------------------------------------------------+
#ifndef G3_EXITMANAGER_MQH
#define G3_EXITMANAGER_MQH

#include "G3Types.mqh"

//--- Spec constants (sections 14,15). Not parameterised.
#define G3_EXIT_A_TP_R           2.0
#define G3_EXIT_B_BE_R           1.0
#define G3_EXIT_B_PARTIAL_R      1.5
#define G3_EXIT_B_PARTIAL_FRAC   0.50
#define G3_EXIT_B_TRAIL_ATR      2.0
#define G3_EXIT_C_TRAIL_ATR      2.5
#define G3_PARTIAL_RATIO_MIN     0.40
#define G3_PARTIAL_RATIO_MAX     0.60
#define G3_TIMEOUT_MFE_R         0.75

//--- Runtime state of one managed position. Persisted by StateStore so
//--- that exits survive an EA restart.
struct G3TradeState
  {
   bool              active;
   ulong             ticket;
   string            symbol;
   string            signal_id;
   ENUM_G3_SIDE      side;
   long              entry_time;
   long              entry_m5_bar;
   double            entry_price;
   double            initial_sl;
   double            initial_tp;
   double            initial_volume;
   double            current_volume;
   double            initial_risk_money;
   double            initial_risk_pct;
   double            r_distance;        // |entry - initial SL| in price
   double            atr_at_entry;
   double            mfe_r;
   double            mae_r;
   double            mfe_r_3bars;
   double            mae_r_3bars;
   double            mfe_r_6bars;
   double            mae_r_6bars;
   double            trail_stop;
   double            extreme_price;     // highest high / lowest low since entry
   double            realized_pl;
   double            partial_closed_volume;
   int               bars_held;
   bool              be_done;
   bool              partial_done;
   bool              partial_skipped;
  };

struct PartialPlan
  {
   bool              valid;
   double            close_volume;
   double            remaining_volume;
   double            close_ratio;
  };

//+------------------------------------------------------------------+
//| Addendum E (DEV-007) - fakeout_3 / fakeout_6                     |
//|                                                                  |
//| The flag is exit-mode independent: it asks whether the price      |
//| would have reached the INITIAL SL within the first N M5 bars      |
//| after entry, whatever actually closed the position. The bar that  |
//| contains the entry counts as bar 1. A window that could not be    |
//| observed in full yields NA, never false.                          |
//+------------------------------------------------------------------+
#define G3_FAKEOUT_N3 3
#define G3_FAKEOUT_N6 6

struct G3FakeoutWatch
  {
   bool              active;
   bool              completed;
   ulong             ticket;
   string            symbol;
   string            signal_id;
   ENUM_G3_SIDE      side;
   double            entry_price;
   double            initial_sl;
   long              entry_m5_bar;
   int               bars_observed;      // 1-based index of the newest observed bar
   bool              observation_gap;    // one or more bars of the window were missed
   ENUM_G3_TRISTATE  fakeout_3;
   ENUM_G3_TRISTATE  fakeout_6;
  };

//--- Addendum E: BUY touches the initial SL on the Bid side, SELL on
//--- the Ask side.
bool G3FakeoutTouched(const ENUM_G3_SIDE side,const double bid,const double ask,
                      const double initial_sl)
  {
   if(initial_sl<=0.0)
      return(false);
   if(side==G3_SIDE_BUY)
      return(bid<=initial_sl);
   if(side==G3_SIDE_SELL)
      return(ask>=initial_sl);
   return(false);
  }

void G3FakeoutInit(G3FakeoutWatch &w,const ulong ticket,const string symbol,
                   const string signal_id,const ENUM_G3_SIDE side,
                   const double entry_price,const double initial_sl,
                   const long entry_m5_bar)
  {
   w.active         =true;
   w.completed      =false;
   w.ticket         =ticket;
   w.symbol         =symbol;
   w.signal_id      =signal_id;
   w.side           =side;
   w.entry_price    =entry_price;
   w.initial_sl     =initial_sl;
   w.entry_m5_bar   =entry_m5_bar;
   w.bars_observed  =1;               // the entry bar itself is bar 1
   w.observation_gap=false;
   w.fakeout_3      =G3_TRI_NA;
   w.fakeout_6      =G3_TRI_NA;
  }

//--- One observation at `bar_index` (1-based, the entry bar is 1).
//--- A bar index that skips ahead by more than one marks the window as
//--- incompletely observed.
void G3FakeoutObserve(G3FakeoutWatch &w,const int bar_index,
                      const double bid,const double ask)
  {
   if(!w.active || w.completed)
      return;
   if(bar_index<1)
      return;
   if(bar_index>w.bars_observed)
     {
      if(bar_index>w.bars_observed+1)
         w.observation_gap=true;
      w.bars_observed=bar_index;
     }
   if(bar_index>G3_FAKEOUT_N6)
      return;
   if(!G3FakeoutTouched(w.side,bid,ask,w.initial_sl))
      return;
   if(bar_index<=G3_FAKEOUT_N3 && w.fakeout_3!=G3_TRI_TRUE)
      w.fakeout_3=G3_TRI_TRUE;
   if(bar_index<=G3_FAKEOUT_N6 && w.fakeout_6!=G3_TRI_TRUE)
      w.fakeout_6=G3_TRI_TRUE;
  }

//--- Close out the windows once they are behind us. An unresolved window
//--- becomes FALSE only when every bar of it was actually observed;
//--- otherwise it stays NA.
//--- Returns true on the call that completes the 6 bar window.
bool G3FakeoutFinalise(G3FakeoutWatch &w,const int current_bar_index)
  {
   if(!w.active || w.completed)
      return(false);
   if(current_bar_index>G3_FAKEOUT_N3 && w.fakeout_3==G3_TRI_NA && !w.observation_gap)
      w.fakeout_3=G3_TRI_FALSE;
   if(current_bar_index>G3_FAKEOUT_N6)
     {
      if(w.fakeout_6==G3_TRI_NA && !w.observation_gap)
         w.fakeout_6=G3_TRI_FALSE;
      w.completed=true;
      return(true);
     }
   return(false);
  }

//--- A restart cannot prove what happened while the EA was down.
void G3FakeoutMarkObservationGap(G3FakeoutWatch &w)
  {
   if(w.active && !w.completed)
      w.observation_gap=true;
  }

//+------------------------------------------------------------------+
//| PURE                                                             |
//+------------------------------------------------------------------+

//--- R multiple of `price` relative to the initial entry / SL distance.
double G3RMultiple(const ENUM_G3_SIDE side,const double price,
                   const double entry_price,const double r_distance)
  {
   if(r_distance<=0.0)
      return(0.0);
   double diff=(side==G3_SIDE_BUY)?(price-entry_price):(entry_price-price);
   return(diff/r_distance);
  }

//--- Price at a given R multiple.
double G3PriceAtR(const ENUM_G3_SIDE side,const double entry_price,
                  const double r_distance,const double r)
  {
   double off=r*r_distance;
   return((side==G3_SIDE_BUY)?(entry_price+off):(entry_price-off));
  }

//--- Cost adjusted break-even (Master Specification v0.4 section 10.2).
//--- The BUY break-even stop is the lowest price at which closing the
//--- position still leaves P/L >= 0 after deducting
//---   already incurred commission + swap + estimated exit commission.
//--- The SPREAD IS NOT ADDED: section 10.2 states that it is already
//--- contained in the Ask/Bid execution relationship and must not be
//--- counted twice (DEV-004 fix).
//--- `cost_price` is that money amount already converted to a price
//--- distance by the caller, and is never negative.
double G3BreakevenPrice(const ENUM_G3_SIDE side,const double entry_price,
                        const double cost_price)
  {
   double c=(cost_price>0.0)?cost_price:0.0;
   return((side==G3_SIDE_BUY)?(entry_price+c):(entry_price-c));
  }

//--- Money amount that the break-even stop has to recover, from the
//--- signed money terms of section 10.2. Commission values are negative
//--- costs and swap is signed; a net credit yields 0, never a discount.
double G3BreakevenCostMoney(const double commission_incurred,const double swap_accrued,
                            const double commission_exit_estimate)
  {
   double net=commission_incurred+swap_accrued+commission_exit_estimate;
   return((net<0.0)?(-net):0.0);
  }

//--- ATR trail anchored on the extreme reached since entry.
double G3AtrTrailStop(const ENUM_G3_SIDE side,const double extreme_price,
                      const double atr,const double mult)
  {
   double off=atr*mult;
   return((side==G3_SIDE_BUY)?(extreme_price-off):(extreme_price+off));
  }

//--- A trail may never move against the position.
double G3MonotonicStop(const ENUM_G3_SIDE side,const double current_stop,
                       const double candidate_stop)
  {
   if(current_stop==0.0)
      return(candidate_stop);
   if(side==G3_SIDE_BUY)
      return((candidate_stop>current_stop)?candidate_stop:current_stop);
   return((candidate_stop<current_stop)?candidate_stop:current_stop);
  }

//--- Partial close plan (Exit mode B).
//---   target_close = current_volume * 0.50 floored onto VolumeStep
//---   remaining must be >= VolumeMin
//---   the realised close ratio must land inside [0.40,0.60]
PartialPlan G3BuildPartialPlan(const double current_volume,const double volume_step,
                               const double volume_min)
  {
   PartialPlan p;
   p.valid=false;
   p.close_volume=0.0;
   p.remaining_volume=current_volume;
   p.close_ratio=0.0;
   if(current_volume<=0.0)
      return(p);
   double target=current_volume*G3_EXIT_B_PARTIAL_FRAC;
   double close_vol=G3NormalizeVolume(target,volume_step);
   if(close_vol<=0.0)
      return(p);
   double remaining=G3NormalizeVolume(current_volume-close_vol,volume_step);
   if(remaining<volume_min-1e-12)
      return(p);
   if(close_vol<volume_min-1e-12)
      return(p);
   double ratio=close_vol/current_volume;
   if(ratio<G3_PARTIAL_RATIO_MIN-1e-12 || ratio>G3_PARTIAL_RATIO_MAX+1e-12)
      return(p);
   p.valid=true;
   p.close_volume=close_vol;
   p.remaining_volume=remaining;
   p.close_ratio=ratio;
   return(p);
  }

//--- Initial take profit for the selected exit mode.
//--- Modes B and C have no fixed take profit.
double G3InitialTakeProfit(const ENUM_G3_EXIT_MODE mode,const ENUM_G3_SIDE side,
                           const double entry_price,const double r_distance)
  {
   if(mode==G3_EXIT_A)
      return(G3PriceAtR(side,entry_price,r_distance,G3_EXIT_A_TP_R));
   return(0.0);
  }

//--- Timeout rule (section 15): at the timeout only positions whose
//--- MFE never reached 0.75R are closed, and only the remaining lot.
bool G3TimeoutShouldClose(const ENUM_G3_TIMEOUT timeout,const int bars_held,
                          const double mfe_r)
  {
   if(timeout==G3_TIMEOUT_OFF)
      return(false);
   if(bars_held<(int)timeout)
      return(false);
   return(mfe_r<G3_TIMEOUT_MFE_R);
  }

//--- result_R = total realised P/L / initial RiskMoney (section 15).
double G3ResultR(const double realized_pl,const double initial_risk_money)
  {
   if(initial_risk_money<=0.0)
      return(0.0);
   return(realized_pl/initial_risk_money);
  }

//--- Update the excursion statistics of a live position.
void G3UpdateExcursions(G3TradeState &t,const double high_price,const double low_price)
  {
   if(t.r_distance<=0.0)
      return;
   double fav=(t.side==G3_SIDE_BUY)?high_price:low_price;
   double adv=(t.side==G3_SIDE_BUY)?low_price:high_price;
   double fav_r=G3RMultiple(t.side,fav,t.entry_price,t.r_distance);
   double adv_r=G3RMultiple(t.side,adv,t.entry_price,t.r_distance);
   if(fav_r>t.mfe_r)
      t.mfe_r=fav_r;
   if(adv_r<t.mae_r)
      t.mae_r=adv_r;
   if(t.side==G3_SIDE_BUY)
     {
      if(t.extreme_price==0.0 || fav>t.extreme_price)
         t.extreme_price=fav;
     }
   else
     {
      if(t.extreme_price==0.0 || fav<t.extreme_price)
         t.extreme_price=fav;
     }
   if(t.bars_held<=3)
     {
      if(fav_r>t.mfe_r_3bars) t.mfe_r_3bars=fav_r;
      if(adv_r<t.mae_r_3bars) t.mae_r_3bars=adv_r;
     }
   if(t.bars_held<=6)
     {
      if(fav_r>t.mfe_r_6bars) t.mfe_r_6bars=fav_r;
      if(adv_r<t.mae_r_6bars) t.mae_r_6bars=adv_r;
     }
  }

//--- Desired stop for the current management step.
//--- Returns the stop that should be active now; the caller applies
//--- monotonicity and only sends a modify when the value changed.
double G3DesiredStop(const ENUM_G3_EXIT_MODE mode,const G3TradeState &t,
                     const double atr_now,const double cost_price)
  {
   if(mode==G3_EXIT_A)
      return(t.initial_sl);                       // fixed, never moved

   if(mode==G3_EXIT_C)
     {
      if(t.extreme_price==0.0 || atr_now<=0.0)
         return(t.initial_sl);
      double cand=G3AtrTrailStop(t.side,t.extreme_price,atr_now,G3_EXIT_C_TRAIL_ATR);
      return(G3MonotonicStop(t.side,
                             (t.trail_stop==0.0)?t.initial_sl:t.trail_stop,
                             cand));
     }

   //--- mode B
   double stop=(t.trail_stop==0.0)?t.initial_sl:t.trail_stop;
   double cur_r=t.mfe_r;
   if(cur_r>=G3_EXIT_B_BE_R)
     {
      double be=G3BreakevenPrice(t.side,t.entry_price,cost_price);
      stop=G3MonotonicStop(t.side,stop,be);
     }
   if(t.partial_done || t.partial_skipped)
     {
      if(t.extreme_price!=0.0 && atr_now>0.0)
        {
         double cand=G3AtrTrailStop(t.side,t.extreme_price,atr_now,G3_EXIT_B_TRAIL_ATR);
         stop=G3MonotonicStop(t.side,stop,cand);
        }
     }
   return(stop);
  }

#endif // G3_EXITMANAGER_MQH
//+------------------------------------------------------------------+
