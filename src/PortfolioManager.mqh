//+------------------------------------------------------------------+
//|                                             PortfolioManager.mqh |
//|   Master Specification v0.4 section 12 - portfolio limits and    |
//|   the correlation guard.                                         |
//|                                                                  |
//|   MaxPositions          = 3                                      |
//|   MaxTotalInitialRisk   = 1.50%                                  |
//|   same currency component, same direction   <= 1.00%             |
//|   correlation cluster (signed corr >= 0.70) <= 1.00%             |
//|   unknown cluster (correlation warm-up)     <= 0.75%             |
//+------------------------------------------------------------------+
#ifndef G3_PORTFOLIOMANAGER_MQH
#define G3_PORTFOLIOMANAGER_MQH

#include "G3Types.mqh"

#define G3_MAX_POSITIONS            3
#define G3_MAX_TOTAL_RISK_PCT       1.50
#define G3_MAX_CURRENCY_RISK_PCT    1.00
#define G3_MAX_CLUSTER_RISK_PCT     1.00
#define G3_MAX_UNKNOWN_CLUSTER_PCT  0.75
#define G3_CORR_THRESHOLD           0.70
#define G3_CORR_REQUIRED_BARS       60
#define G3_MAX_LEGS                 16

//--- One risk-bearing leg: an open position, or the entry candidate.
struct PortfolioLeg
  {
   string            symbol;
   ENUM_G3_SIDE      side;
   double            initial_risk_pct;   // initial risk as % of equity
  };

struct PortfolioSnapshot
  {
   PortfolioLeg      leg[G3_MAX_LEGS];
   int               n;
  };

//--- Pairwise correlation of the legs (index 0..n-1 of the snapshot).
struct CorrMatrix
  {
   double            m[G3_MAX_LEGS*G3_MAX_LEGS];
   int               n;
   bool              ready;              // false -> CORR_WARMUP_UNKNOWN
   int               warmup_days;        // complete D1 bars actually available
  };

//--- Result of the portfolio admission check.
struct PortfolioDecision
  {
   bool              accepted;
   ENUM_G3_REASON    reason;
   double            total_risk_pct;
   double            currency_risk_pct;      // worst matching component
   double            corr_cluster_risk_pct;
   double            corr_cluster_risk_raw_pct; // direction-agnostic reading
   double            unknown_cluster_risk_pct;
   ENUM_G3_CORR_STATE corr_state;
   int               corr_warmup_days;
   int               open_positions;
  };

//+------------------------------------------------------------------+
//| PURE - helpers                                                   |
//+------------------------------------------------------------------+

//--- Currency components of a 6-letter FX symbol. Broker suffixes
//--- (e.g. "EURUSD.m") are ignored: only the first 6 characters are
//--- interpreted. See known_limitations.md L-05.
string G3BaseCurrency(const string symbol)
  {
   return(StringSubstr(symbol,0,3));
  }

string G3QuoteCurrency(const string symbol)
  {
   return(StringSubstr(symbol,3,3));
  }

//--- +1 long / -1 short of the given currency component for a leg.
int G3CurrencyDirection(const ENUM_G3_SIDE side,const bool is_base)
  {
   int d=(side==G3_SIDE_BUY)?1:-1;
   return(is_base?d:-d);
  }

int G3SideSign(const ENUM_G3_SIDE side)
  {
   return((side==G3_SIDE_BUY)?1:-1);
  }

//--- Total initial risk of all legs in the snapshot.
double G3TotalRiskPct(const PortfolioSnapshot &snap)
  {
   double sum=0.0;
   for(int i=0;i<snap.n;i++)
      sum+=snap.leg[i].initial_risk_pct;
   return(sum);
  }

//--- Summed initial risk of every leg that is exposed to `currency`
//--- in direction `direction` (+1 long, -1 short).
double G3CurrencyRiskPct(const PortfolioSnapshot &snap,const string currency,
                         const int direction)
  {
   double sum=0.0;
   for(int i=0;i<snap.n;i++)
     {
      string base=G3BaseCurrency(snap.leg[i].symbol);
      string quote=G3QuoteCurrency(snap.leg[i].symbol);
      if(base==currency && G3CurrencyDirection(snap.leg[i].side,true)==direction)
         sum+=snap.leg[i].initial_risk_pct;
      else
         if(quote==currency && G3CurrencyDirection(snap.leg[i].side,false)==direction)
            sum+=snap.leg[i].initial_risk_pct;
     }
   return(sum);
  }

//--- Worst same-currency same-direction exposure created by the
//--- candidate leg, which is expected to be the LAST leg of `snap`.
double G3WorstCurrencyRiskPct(const PortfolioSnapshot &snap,const int candidate_index)
  {
   if(candidate_index<0 || candidate_index>=snap.n)
      return(0.0);
   string sym=snap.leg[candidate_index].symbol;
   ENUM_G3_SIDE side=snap.leg[candidate_index].side;
   double a=G3CurrencyRiskPct(snap,G3BaseCurrency(sym),G3CurrencyDirection(side,true));
   double b=G3CurrencyRiskPct(snap,G3QuoteCurrency(sym),G3CurrencyDirection(side,false));
   return((a>=b)?a:b);
  }

//+------------------------------------------------------------------+
//| PURE - correlation clustering                                    |
//+------------------------------------------------------------------+

double G3CorrAt(const CorrMatrix &c,const int i,const int j)
  {
   if(i<0 || j<0 || i>=c.n || j>=c.n)
      return(0.0);
   return(c.m[i*G3_MAX_LEGS+j]);
  }

void G3CorrSet(CorrMatrix &c,const int i,const int j,const double v)
  {
   if(i<0 || j<0 || i>=G3_MAX_LEGS || j>=G3_MAX_LEGS)
      return;
   c.m[i*G3_MAX_LEGS+j]=v;
   c.m[j*G3_MAX_LEGS+i]=v;
  }

//--- Signed correlation between two legs.
//--- ISSUE-002: the implemented reading is direction adjusted, i.e.
//--- corr(i,j) * sign(side_i) * sign(side_j), so that two positively
//--- correlated symbols held in opposite directions do not form a
//--- risk cluster. `direction_adjusted=false` returns the raw Pearson
//--- value, which is logged alongside for G3 evaluation.
double G3SignedLegCorrelation(const PortfolioSnapshot &snap,const CorrMatrix &c,
                              const int i,const int j,const bool direction_adjusted)
  {
   double r=G3CorrAt(c,i,j);
   if(!direction_adjusted)
      return(r);
   return(r*(double)G3SideSign(snap.leg[i].side)*(double)G3SideSign(snap.leg[j].side));
  }

//--- Union-find over legs linked by signed correlation >= 0.70 and the
//--- summed initial risk of the cluster containing `member_index`.
double G3ClusterRiskPct(const PortfolioSnapshot &snap,const CorrMatrix &c,
                        const int member_index,const bool direction_adjusted)
  {
   if(member_index<0 || member_index>=snap.n)
      return(0.0);
   int parent[G3_MAX_LEGS];
   for(int i=0;i<snap.n;i++)
      parent[i]=i;
   //--- link
   for(int i=0;i<snap.n;i++)
     {
      for(int j=i+1;j<snap.n;j++)
        {
         if(G3SignedLegCorrelation(snap,c,i,j,direction_adjusted)>=G3_CORR_THRESHOLD)
           {
            int ri=i;
            while(parent[ri]!=ri) ri=parent[ri];
            int rj=j;
            while(parent[rj]!=rj) rj=parent[rj];
            if(ri!=rj)
               parent[rj]=ri;
           }
        }
     }
   //--- root of the member
   int rm=member_index;
   while(parent[rm]!=rm) rm=parent[rm];
   double sum=0.0;
   for(int i=0;i<snap.n;i++)
     {
      int r=i;
      while(parent[r]!=r) r=parent[r];
      if(r==rm)
         sum+=snap.leg[i].initial_risk_pct;
     }
   return(sum);
  }

//+------------------------------------------------------------------+
//| PURE - admission check                                           |
//+------------------------------------------------------------------+

//--- `snap` must already contain every open position plus the
//--- candidate as its last leg; `candidate_index` = snap.n-1.
PortfolioDecision G3CheckPortfolio(const PortfolioSnapshot &snap,const CorrMatrix &c,
                                   const int candidate_index)
  {
   PortfolioDecision d;
   d.accepted=false;
   d.reason=G3_R_NONE;
   d.total_risk_pct=G3TotalRiskPct(snap);
   d.currency_risk_pct=G3WorstCurrencyRiskPct(snap,candidate_index);
   d.corr_cluster_risk_pct=0.0;
   d.corr_cluster_risk_raw_pct=0.0;
   d.unknown_cluster_risk_pct=0.0;
   d.corr_state=(c.ready?G3_CORR_READY:G3_CORR_WARMUP_UNKNOWN);
   d.corr_warmup_days=c.warmup_days;
   d.open_positions=(candidate_index>=0)?(snap.n-1):snap.n;

   if(d.open_positions>=G3_MAX_POSITIONS)
     {
      d.reason=G3_R_MAX_POSITIONS;
      return(d);
     }
   if(d.total_risk_pct>G3_MAX_TOTAL_RISK_PCT+1e-9)
     {
      d.reason=G3_R_MAX_TOTAL_RISK;
      return(d);
     }
   if(d.currency_risk_pct>G3_MAX_CURRENCY_RISK_PCT+1e-9)
     {
      d.reason=G3_R_CURRENCY_EXPOSURE;
      return(d);
     }
   if(c.ready)
     {
      d.corr_cluster_risk_pct=G3ClusterRiskPct(snap,c,candidate_index,true);
      d.corr_cluster_risk_raw_pct=G3ClusterRiskPct(snap,c,candidate_index,false);
      if(d.corr_cluster_risk_pct>G3_MAX_CLUSTER_RISK_PCT+1e-9)
        {
         d.reason=G3_R_CORR_CLUSTER_RISK;
         return(d);
        }
     }
   else
     {
      //--- correlation unknown: candidate + every open position form a
      //--- single unknown cluster. Correlation is never treated as zero.
      d.unknown_cluster_risk_pct=d.total_risk_pct;
      if(d.unknown_cluster_risk_pct>G3_MAX_UNKNOWN_CLUSTER_PCT+1e-9)
        {
         d.reason=G3_R_UNKNOWN_CLUSTER_RISK;
         return(d);
        }
     }
   d.accepted=true;
   return(d);
  }

//+------------------------------------------------------------------+
//| TERMINAL (excluded from the host test harness)                   |
//+------------------------------------------------------------------+
#ifndef G3_HOST_TEST

//--- Close-to-close log returns over complete D1 bars only.
//--- `G3_CORR_REQUIRED_BARS` returns require one extra closed bar.
//--- ASSUMPTION A-05: Pearson correlation is computed on D1 log returns.
bool G3D1Returns(const string symbol,const datetime signal_close_time,
                 DoubleSeries &out,int &bars_available)
  {
   out.n=0;
   bars_available=0;
   int need=G3_CORR_REQUIRED_BARS+1;
   datetime times[];
   double closes[];
   ArraySetAsSeries(times,true);
   ArraySetAsSeries(closes,true);
   int depth=need+5;
   //--- G3-CHECK: shift0-safe - index 0 (the forming D1 bar) is copied only
   //--- so that `start` below can skip it; no forming bar value is ever used.
   if(CopyTime(symbol,PERIOD_D1,0,depth,times)<need)
      return(false);
   if(CopyClose(symbol,PERIOD_D1,0,depth,closes)<need)
      return(false);
   //--- first fully closed D1 bar at signal_close_time
   int start=-1;
   long day=(long)PeriodSeconds(PERIOD_D1);
   for(int i=0;i<ArraySize(times);i++)
     {
      if((long)times[i]+day<=(long)signal_close_time)
        {
         start=i;
         break;
        }
     }
   if(start<0)
      return(false);
   int avail=ArraySize(closes)-start-1;
   bars_available=(avail>0)?avail:0;
   if(bars_available<G3_CORR_REQUIRED_BARS)
      return(false);
   for(int k=0;k<G3_CORR_REQUIRED_BARS;k++)
     {
      double c0=closes[start+k];
      double c1=closes[start+k+1];
      if(c0<=0.0 || c1<=0.0)
         return(false);
      out.v[k]=MathLog(c0/c1);
     }
   out.n=G3_CORR_REQUIRED_BARS;
   return(true);
  }

//--- Build the pairwise correlation matrix for the snapshot legs.
//--- Any leg without a full 60-return window puts the whole matrix
//--- into CORR_WARMUP_UNKNOWN.
bool G3BuildCorrMatrix(const PortfolioSnapshot &snap,const datetime signal_close_time,
                       CorrMatrix &c)
  {
   c.n=snap.n;
   c.ready=true;
   c.warmup_days=G3_CORR_REQUIRED_BARS;
   for(int i=0;i<G3_MAX_LEGS*G3_MAX_LEGS;i++)
      c.m[i]=0.0;
   if(snap.n<=0 || snap.n>G3_MAX_LEGS)
     {
      c.ready=false;
      c.warmup_days=0;
      return(false);
     }
   DoubleSeries series[G3_MAX_LEGS];
   int min_bars=G3_CORR_REQUIRED_BARS;
   for(int i=0;i<snap.n;i++)
     {
      int avail=0;
      if(!G3D1Returns(snap.leg[i].symbol,signal_close_time,series[i],avail))
        {
         c.ready=false;
         if(avail<min_bars)
            min_bars=avail;
        }
      else
         if(avail<min_bars)
            min_bars=avail;
     }
   c.warmup_days=min_bars;
   if(!c.ready)
      return(false);
   for(int i=0;i<snap.n;i++)
     {
      G3CorrSet(c,i,i,1.0);
      for(int j=i+1;j<snap.n;j++)
        {
         double r=0.0;
         if(!G3Pearson(series[i],series[j],r))
           {
            c.ready=false;
            return(false);
           }
         G3CorrSet(c,i,j,r);
        }
     }
   return(true);
  }

//+------------------------------------------------------------------+
//| Cross-instance position risk registry                            |
//| Each EA instance owns one symbol, so the initial risk of a        |
//| position is published in a terminal global variable to make the   |
//| portfolio limits computable from every instance.                  |
//+------------------------------------------------------------------+
string G3PositionRiskGVName(const long magic,const ulong ticket)
  {
   return("G3POS_"+IntegerToString(magic)+"_"+IntegerToString((long)ticket));
  }

bool G3RegisterPositionRisk(const long magic,const ulong ticket,const double risk_pct)
  {
   return(GlobalVariableSet(G3PositionRiskGVName(magic,ticket),risk_pct)>0);
  }

void G3UnregisterPositionRisk(const long magic,const ulong ticket)
  {
   string n=G3PositionRiskGVName(magic,ticket);
   if(GlobalVariableCheck(n))
      GlobalVariableDel(n);
  }

//--- Fallback when the registry entry is missing (e.g. terminal global
//--- variables were lost): recompute the open risk from the live stop.
double G3PositionRiskPctFallback(const string symbol,const ENUM_G3_SIDE side,
                                 const double volume,const double entry,
                                 const double sl,const double equity)
  {
   if(equity<=0.0 || sl<=0.0 || volume<=0.0)
      return(0.0);
   ENUM_ORDER_TYPE t=(side==G3_SIDE_BUY)?ORDER_TYPE_BUY:ORDER_TYPE_SELL;
   double profit=0.0;
   if(!OrderCalcProfit(t,symbol,volume,entry,sl,profit))
      return(0.0);
   return(MathAbs(profit)/equity*100.0);
  }

//--- Build the snapshot of every open position carrying our magic.
int G3BuildOpenSnapshot(const long magic,const double equity,PortfolioSnapshot &snap)
  {
   snap.n=0;
   int total=PositionsTotal();
   for(int i=0;i<total && snap.n<G3_MAX_LEGS;i++)
     {
      ulong ticket=PositionGetTicket(i);
      if(ticket==0)
         continue;
      if(!PositionSelectByTicket(ticket))
         continue;
      if(PositionGetInteger(POSITION_MAGIC)!=magic)
         continue;
      string sym=PositionGetString(POSITION_SYMBOL);
      ENUM_G3_SIDE side=(PositionGetInteger(POSITION_TYPE)==POSITION_TYPE_BUY)
                        ?G3_SIDE_BUY:G3_SIDE_SELL;
      double risk_pct=0.0;
      string gv=G3PositionRiskGVName(magic,ticket);
      if(GlobalVariableCheck(gv))
         risk_pct=GlobalVariableGet(gv);
      else
         risk_pct=G3PositionRiskPctFallback(sym,side,
                                            PositionGetDouble(POSITION_VOLUME),
                                            PositionGetDouble(POSITION_PRICE_OPEN),
                                            PositionGetDouble(POSITION_SL),equity);
      snap.leg[snap.n].symbol=sym;
      snap.leg[snap.n].side=side;
      snap.leg[snap.n].initial_risk_pct=risk_pct;
      snap.n++;
     }
   return(snap.n);
  }

#endif // G3_HOST_TEST

#endif // G3_PORTFOLIOMANAGER_MQH
//+------------------------------------------------------------------+
