//+------------------------------------------------------------------+
//|                                                      G3Types.mqh |
//|        Shared enums, structs, reason codes and portable math.    |
//|                                                                  |
//|  Spec authority : Master Specification v0.4                      |
//|  Research stage : G3 (numerical research data generation)        |
//|                                                                  |
//|  Everything in this header is pure (no terminal calls), so it is |
//|  compiled both by MetaEditor and by the host test harness        |
//|  (tests/host) which defines G3_HOST_TEST.                        |
//+------------------------------------------------------------------+
#ifndef G3_TYPES_MQH
#define G3_TYPES_MQH

//--- maximum length of any series handed to the pure helpers.
//--- 101 ATR values (VolRatio) and 61 D1 closes (correlation) are the
//--- largest windows required by Master Specification v0.4.
#define G3_MAX_SERIES 512

//+------------------------------------------------------------------+
//| Portable fixed-capacity series containers                        |
//+------------------------------------------------------------------+
struct DoubleSeries
  {
   double            v[G3_MAX_SERIES];
   int               n;
  };

struct LongSeries
  {
   long              v[G3_MAX_SERIES];
   int               n;
  };

//+------------------------------------------------------------------+
//| Enumerations                                                     |
//+------------------------------------------------------------------+
enum ENUM_G3_SIDE
  {
   G3_SIDE_NONE = 0,
   G3_SIDE_BUY  = 1,
   G3_SIDE_SELL = 2
  };

enum ENUM_G3_DD_STATE
  {
   G3_DD_NORMAL     = 0,
   G3_DD_MODERATE   = 1,
   G3_DD_RESTRICTED = 2,
   G3_DD_HARD_STOP  = 3,
   G3_DD_UNCERTAIN  = 4     // StateStore unrecoverable -> no new trades
  };

enum ENUM_G3_CORR_STATE
  {
   G3_CORR_READY         = 0,
   G3_CORR_WARMUP_UNKNOWN= 1
  };

enum ENUM_G3_EXIT_MODE
  {
   G3_EXIT_A = 0,   // fixed 2.0R TP, fixed initial SL
   G3_EXIT_B = 1,   // BE @1.0R, ~50% partial @1.5R, ATR*2.0 trail
   G3_EXIT_C = 2    // no fixed TP, ATR*2.5 chandelier trail
  };

enum ENUM_G3_TIMEOUT
  {
   G3_TIMEOUT_OFF = 0,
   G3_TIMEOUT_6   = 6,
   G3_TIMEOUT_12  = 12,
   G3_TIMEOUT_18  = 18,
   G3_TIMEOUT_24  = 24
  };

enum ENUM_G3_SCORE_THRESHOLD
  {
   G3_SCORE_TH_4 = 4,
   G3_SCORE_TH_5 = 5,   // Master Specification v0.4 baseline
   G3_SCORE_TH_6 = 6
  };

enum ENUM_G3_STORE_STATUS
  {
   G3_STORE_OK              = 0,  // both stores agree
   G3_STORE_FILE_ONLY       = 1,  // GV missing/corrupt, file valid
   G3_STORE_GV_ONLY         = 2,  // file missing/corrupt, GV valid
   G3_STORE_MISMATCH        = 3,  // both valid, disagree -> conservative
   G3_STORE_BOTH_LOST       = 4,  // both unrecoverable -> STATE_UNCERTAIN
   G3_STORE_FRESH           = 5   // first run, nothing stored yet
  };

//+------------------------------------------------------------------+
//| Reason / skip codes (see schema/reason_codes.md)                 |
//+------------------------------------------------------------------+
enum ENUM_G3_REASON
  {
   G3_R_NONE = 0,
   //--- evaluation gates
   G3_R_NO_H4_DIRECTION,
   G3_R_H4_SCORE_BELOW_MIN,
   G3_R_M5_BREAKOUT_FAIL,
   G3_R_M5_SCORE_BELOW_MIN,
   G3_R_TOTAL_SCORE_BELOW_THRESHOLD,
   G3_R_VOL_BLOCK,
   G3_R_SPREAD_BLOCK,
   //--- data / synchronisation
   G3_R_DATA_UNAVAILABLE,
   G3_R_HTF_BAR_UNRESOLVED,
   G3_R_POST_GAP_COOLDOWN,
   G3_R_INDICATOR_NOT_READY,
   G3_R_SIGNAL_ALREADY_CONSUMED,
   //--- risk / state
   G3_R_STATE_UNCERTAIN,
   G3_R_HARD_STOP_LATCHED,
   G3_R_DAILY_ENTRY_LOCK,
   G3_R_SL_DISTANCE_ABOVE_MAX,
   G3_R_SL_BROKER_ADJ_ABOVE_MAX,
   G3_R_LOT_BELOW_MIN_VOLUME,
   G3_R_RISK_MONEY_EXCEEDED_AT_MIN_VOLUME,
   G3_R_ORDER_CALC_PROFIT_INVALID,
   //--- portfolio
   G3_R_MAX_POSITIONS,
   G3_R_MAX_TOTAL_RISK,
   G3_R_CURRENCY_EXPOSURE,
   G3_R_CORR_CLUSTER_RISK,
   G3_R_UNKNOWN_CLUSTER_RISK,
   G3_R_PORTFOLIO_LOCK_BUSY,
   G3_R_DUPLICATE_SIGNAL_ID,
   //--- execution
   G3_R_DEVIATION_CAP_EXCEEDED,
   G3_R_MARKET_CLOSED,
   G3_R_TRADE_MODE_DISABLED,
   G3_R_FREEZE_LEVEL,
   G3_R_ORDER_SEND_FAILED,
   G3_R_EXECUTION_RISK_VIOLATION,
   //--- exits (used on EXIT records)
   G3_R_EXIT_TP,
   G3_R_EXIT_SL,
   G3_R_EXIT_BE,
   G3_R_EXIT_TRAIL,
   G3_R_EXIT_PARTIAL,
   G3_R_EXIT_TIMEOUT,
   G3_R_EXIT_MANUAL_OR_EXTERNAL
  };

string G3ReasonToString(const ENUM_G3_REASON r)
  {
   switch(r)
     {
      case G3_R_NONE:                           return("NONE");
      case G3_R_NO_H4_DIRECTION:                return("NO_H4_DIRECTION");
      case G3_R_H4_SCORE_BELOW_MIN:             return("H4_SCORE_BELOW_MIN");
      case G3_R_M5_BREAKOUT_FAIL:               return("M5_BREAKOUT_FAIL");
      case G3_R_M5_SCORE_BELOW_MIN:             return("M5_SCORE_BELOW_MIN");
      case G3_R_TOTAL_SCORE_BELOW_THRESHOLD:    return("TOTAL_SCORE_BELOW_THRESHOLD");
      case G3_R_VOL_BLOCK:                      return("VOL_BLOCK");
      case G3_R_SPREAD_BLOCK:                   return("SPREAD_BLOCK");
      case G3_R_DATA_UNAVAILABLE:               return("DATA_UNAVAILABLE");
      case G3_R_HTF_BAR_UNRESOLVED:             return("HTF_BAR_UNRESOLVED");
      case G3_R_POST_GAP_COOLDOWN:              return("POST_GAP_COOLDOWN");
      case G3_R_INDICATOR_NOT_READY:            return("INDICATOR_NOT_READY");
      case G3_R_SIGNAL_ALREADY_CONSUMED:        return("SIGNAL_ALREADY_CONSUMED");
      case G3_R_STATE_UNCERTAIN:                return("STATE_UNCERTAIN");
      case G3_R_HARD_STOP_LATCHED:              return("HARD_STOP_LATCHED");
      case G3_R_DAILY_ENTRY_LOCK:               return("DAILY_ENTRY_LOCK");
      case G3_R_SL_DISTANCE_ABOVE_MAX:          return("SL_DISTANCE_ABOVE_MAX");
      case G3_R_SL_BROKER_ADJ_ABOVE_MAX:        return("SL_BROKER_ADJ_ABOVE_MAX");
      case G3_R_LOT_BELOW_MIN_VOLUME:           return("LOT_BELOW_MIN_VOLUME");
      case G3_R_RISK_MONEY_EXCEEDED_AT_MIN_VOLUME: return("RISK_MONEY_EXCEEDED_AT_MIN_VOLUME");
      case G3_R_ORDER_CALC_PROFIT_INVALID:      return("ORDER_CALC_PROFIT_INVALID");
      case G3_R_MAX_POSITIONS:                  return("MAX_POSITIONS");
      case G3_R_MAX_TOTAL_RISK:                 return("MAX_TOTAL_RISK");
      case G3_R_CURRENCY_EXPOSURE:              return("CURRENCY_EXPOSURE");
      case G3_R_CORR_CLUSTER_RISK:              return("CORR_CLUSTER_RISK");
      case G3_R_UNKNOWN_CLUSTER_RISK:           return("UNKNOWN_CLUSTER_RISK");
      case G3_R_PORTFOLIO_LOCK_BUSY:            return("PORTFOLIO_LOCK_BUSY");
      case G3_R_DUPLICATE_SIGNAL_ID:            return("DUPLICATE_SIGNAL_ID");
      case G3_R_DEVIATION_CAP_EXCEEDED:         return("DEVIATION_CAP_EXCEEDED");
      case G3_R_MARKET_CLOSED:                  return("MARKET_CLOSED");
      case G3_R_TRADE_MODE_DISABLED:            return("TRADE_MODE_DISABLED");
      case G3_R_FREEZE_LEVEL:                   return("FREEZE_LEVEL");
      case G3_R_ORDER_SEND_FAILED:              return("ORDER_SEND_FAILED");
      case G3_R_EXECUTION_RISK_VIOLATION:       return("EXECUTION_RISK_VIOLATION");
      case G3_R_EXIT_TP:                        return("EXIT_TP");
      case G3_R_EXIT_SL:                        return("EXIT_SL");
      case G3_R_EXIT_BE:                        return("EXIT_BE");
      case G3_R_EXIT_TRAIL:                     return("EXIT_TRAIL");
      case G3_R_EXIT_PARTIAL:                   return("EXIT_PARTIAL");
      case G3_R_EXIT_TIMEOUT:                   return("EXIT_TIMEOUT");
      case G3_R_EXIT_MANUAL_OR_EXTERNAL:        return("EXIT_MANUAL_OR_EXTERNAL");
     }
   return("UNMAPPED");
  }

string G3SideToString(const ENUM_G3_SIDE s)
  {
   if(s==G3_SIDE_BUY)  return("BUY");
   if(s==G3_SIDE_SELL) return("SELL");
   return("NONE");
  }

string G3DDStateToString(const ENUM_G3_DD_STATE s)
  {
   switch(s)
     {
      case G3_DD_NORMAL:     return("NORMAL");
      case G3_DD_MODERATE:   return("MODERATE");
      case G3_DD_RESTRICTED: return("RESTRICTED");
      case G3_DD_HARD_STOP:  return("HARD_STOP");
      case G3_DD_UNCERTAIN:  return("STATE_UNCERTAIN");
     }
   return("UNMAPPED");
  }

string G3CorrStateToString(const ENUM_G3_CORR_STATE s)
  {
   if(s==G3_CORR_READY) return("CORR_READY");
   return("CORR_WARMUP_UNKNOWN");
  }

//--- Master Specification v0.4 section 12 names exactly three values for
//--- the state_store_status log field. The richer internal status is
//--- logged separately as state_store_detail.
string G3StoreStatusToSpec(const ENUM_G3_STORE_STATUS s)
  {
   switch(s)
     {
      case G3_STORE_OK:
      case G3_STORE_FRESH:
         return("OK");
      case G3_STORE_FILE_ONLY:
      case G3_STORE_GV_ONLY:
      case G3_STORE_MISMATCH:
         return("RECOVERED");
      case G3_STORE_BOTH_LOST:
         return("UNCERTAIN");
     }
   return("UNCERTAIN");
  }

string G3StoreStatusToString(const ENUM_G3_STORE_STATUS s)
  {
   switch(s)
     {
      case G3_STORE_OK:        return("STORE_OK");
      case G3_STORE_FILE_ONLY: return("STORE_FILE_ONLY");
      case G3_STORE_GV_ONLY:   return("STORE_GV_ONLY");
      case G3_STORE_MISMATCH:  return("STORE_MISMATCH_CONSERVATIVE");
      case G3_STORE_BOTH_LOST: return("STORE_BOTH_LOST");
      case G3_STORE_FRESH:     return("STORE_FRESH");
     }
   return("UNMAPPED");
  }

//+------------------------------------------------------------------+
//| Portable math helpers                                            |
//+------------------------------------------------------------------+

//--- ascending insertion sort over a local copy (no ArraySort, so the
//--- helper is identical under MetaEditor and the host harness).
void G3SortAscending(DoubleSeries &s)
  {
   for(int i=1; i<s.n; i++)
     {
      double key=s.v[i];
      int j=i-1;
      while(j>=0 && s.v[j]>key)
        {
         s.v[j+1]=s.v[j];
         j--;
        }
      s.v[j+1]=key;
     }
  }

//--- median of a sample. Even sample size -> mean of the two central
//--- order statistics (ASSUMPTION A-02, see docs/known_limitations.md).
bool G3Median(const DoubleSeries &src,double &median_out)
  {
   median_out=0.0;
   if(src.n<=0 || src.n>G3_MAX_SERIES)
      return(false);
   DoubleSeries tmp=src;
   G3SortAscending(tmp);
   if((tmp.n%2)==1)
      median_out=tmp.v[tmp.n/2];
   else
      median_out=0.5*(tmp.v[tmp.n/2-1]+tmp.v[tmp.n/2]);
   return(true);
  }

//--- Pearson correlation coefficient of two equal-length samples.
bool G3Pearson(const DoubleSeries &a,const DoubleSeries &b,double &corr_out)
  {
   corr_out=0.0;
   if(a.n<2 || a.n!=b.n)
      return(false);
   double sa=0.0,sb=0.0;
   for(int i=0;i<a.n;i++)
     {
      sa+=a.v[i];
      sb+=b.v[i];
     }
   double ma=sa/a.n;
   double mb=sb/b.n;
   double cov=0.0,va=0.0,vb=0.0;
   for(int i=0;i<a.n;i++)
     {
      double da=a.v[i]-ma;
      double db=b.v[i]-mb;
      cov+=da*db;
      va+=da*da;
      vb+=db*db;
     }
   if(va<=0.0 || vb<=0.0)
      return(false);                 // zero variance -> undefined
   corr_out=cov/MathSqrt(va*vb);
   if(corr_out> 1.0) corr_out= 1.0;
   if(corr_out<-1.0) corr_out=-1.0;
   return(true);
  }

//--- floor a volume onto the broker volume step (Master Spec 9: floor only)
double G3FloorToStep(const double raw,const double step)
  {
   if(step<=0.0)
      return(raw);
   double steps=MathFloor(raw/step+1e-9);
   if(steps<0.0)
      steps=0.0;
   return(steps*step);
  }

//--- normalise a volume to the step grid and round-trip through a
//--- string-free integer count to kill binary representation dust.
double G3NormalizeVolume(const double raw,const double step)
  {
   double v=G3FloorToStep(raw,step);
   if(step<=0.0)
      return(v);
   double steps=MathFloor(v/step+0.5);
   return(steps*step);
  }

//--- FNV-1a 64 bit over a string; used as the StateStore checksum.
ulong G3Fnv1a(const string s)
  {
   ulong h=0xCBF29CE484222325;
   int len=StringLen(s);
   for(int i=0;i<len;i++)
     {
      ulong c=(ulong)StringGetCharacter(s,i);
      h=h^c;
      h=h*0x100000001B3;
     }
   return(h);
  }

//--- the more conservative of two recovered DD states (Master Spec 10:
//--- on store mismatch the conservative state wins).
ENUM_G3_DD_STATE G3MoreConservativeState(const ENUM_G3_DD_STATE a,const ENUM_G3_DD_STATE b)
  {
   if(a==G3_DD_UNCERTAIN || b==G3_DD_UNCERTAIN)
      return(G3_DD_UNCERTAIN);
   return((a>=b)?a:b);            // enum order is increasing severity
  }

#endif // G3_TYPES_MQH
//+------------------------------------------------------------------+
