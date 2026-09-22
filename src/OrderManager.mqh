//+------------------------------------------------------------------+
//|                                                 OrderManager.mqh |
//|   Master Specification v0.4 section 13 - execution and deviation.|
//|                                                                  |
//|   * every market fact is re-read at the decision_tick            |
//|   * computedDeviationPoints =                                    |
//|       floor( min(1.0*spread_price, 0.05*ATR14[1]) / Point )      |
//|   * HardCap = 2.0 pips expressed in points                       |
//|   * computed > HardCap  -> the order is NOT sent                 |
//|   * at most ONE OrderSend per decision_tick, no retry loop       |
//+------------------------------------------------------------------+
#ifndef G3_ORDERMANAGER_MQH
#define G3_ORDERMANAGER_MQH

#include "G3Types.mqh"
#include "RiskManager.mqh"

#define G3_DEVIATION_SPREAD_MULT  1.00
#define G3_DEVIATION_ATR_MULT     0.05
#define G3_DEVIATION_HARDCAP_PIPS 2.0

struct DeviationPlan
  {
   long              computed_points;
   long              hard_cap_points;
   long              send_points;
   bool              cap_hit;          // computed > HardCap
   bool              send_allowed;
  };

//+------------------------------------------------------------------+
//| PURE                                                             |
//+------------------------------------------------------------------+

//--- PipSize: 3/5 digit symbols use 10*Point, everything else Point.
double G3PipSize(const int digits,const double point)
  {
   if(digits==3 || digits==5)
      return(10.0*point);
   return(point);
  }

//--- HardCap of 2.0 pips expressed in points.
long G3DeviationHardCapPoints(const int digits,const double point)
  {
   if(point<=0.0)
      return(0);
   double pip=G3PipSize(digits,point);
   return((long)MathFloor(G3_DEVIATION_HARDCAP_PIPS*pip/point+1e-9));
  }

//--- Deviation plan for one decision_tick.
DeviationPlan G3BuildDeviationPlan(const double spread_price,const double atr_s1,
                                   const int digits,const double point)
  {
   DeviationPlan p;
   p.computed_points=0;
   p.hard_cap_points=G3DeviationHardCapPoints(digits,point);
   p.send_points=0;
   p.cap_hit=false;
   p.send_allowed=false;
   if(point<=0.0 || atr_s1<=0.0 || spread_price<0.0)
      return(p);
   double a=G3_DEVIATION_SPREAD_MULT*spread_price;
   double b=G3_DEVIATION_ATR_MULT*atr_s1;
   double smaller=(a<b)?a:b;
   p.computed_points=(long)MathFloor(smaller/point);
   if(p.computed_points>p.hard_cap_points)
     {
      p.cap_hit=true;
      p.send_allowed=false;
      return(p);
     }
   long send=p.computed_points;
   if(send>p.hard_cap_points)
      send=p.hard_cap_points;
   if(send<1)
      send=1;
   p.send_points=send;
   p.send_allowed=true;
   return(p);
  }

//+------------------------------------------------------------------+
//| TERMINAL (excluded from the host test harness)                   |
//+------------------------------------------------------------------+
#ifndef G3_HOST_TEST

//--- Market facts re-read at the decision_tick (section 13).
struct MarketSnapshot
  {
   double            bid;
   double            ask;
   double            spread_price;
   int               digits;
   double            point;
   double            volume_step;
   double            volume_min;
   double            volume_max;
   long              stops_level;
   long              freeze_level;
   long              trade_mode;
   bool              tradable;
  };

bool G3ReadMarket(const string symbol,MarketSnapshot &m)
  {
   MqlTick tick;
   if(!SymbolInfoTick(symbol,tick))
      return(false);
   m.bid=tick.bid;
   m.ask=tick.ask;
   if(m.bid<=0.0 || m.ask<=0.0)
      return(false);
   m.spread_price=m.ask-m.bid;
   m.digits=(int)SymbolInfoInteger(symbol,SYMBOL_DIGITS);
   m.point=SymbolInfoDouble(symbol,SYMBOL_POINT);
   m.volume_step=SymbolInfoDouble(symbol,SYMBOL_VOLUME_STEP);
   m.volume_min=SymbolInfoDouble(symbol,SYMBOL_VOLUME_MIN);
   m.volume_max=SymbolInfoDouble(symbol,SYMBOL_VOLUME_MAX);
   m.stops_level=SymbolInfoInteger(symbol,SYMBOL_TRADE_STOPS_LEVEL);
   m.freeze_level=SymbolInfoInteger(symbol,SYMBOL_TRADE_FREEZE_LEVEL);
   m.trade_mode=SymbolInfoInteger(symbol,SYMBOL_TRADE_MODE);
   m.tradable=(m.trade_mode==SYMBOL_TRADE_MODE_FULL);
   return(true);
  }

//--- Supported filling mode for the symbol.
ENUM_ORDER_TYPE_FILLING G3FillingMode(const string symbol)
  {
   long filling=SymbolInfoInteger(symbol,SYMBOL_FILLING_MODE);
   if((filling&SYMBOL_FILLING_FOK)==SYMBOL_FILLING_FOK)
      return(ORDER_FILLING_FOK);
   if((filling&SYMBOL_FILLING_IOC)==SYMBOL_FILLING_IOC)
      return(ORDER_FILLING_IOC);
   return(ORDER_FILLING_RETURN);
  }

struct OrderOutcome
  {
   bool              sent;
   bool              filled;
   uint              retcode;
   ulong             ticket;
   double            requested_price;
   double            fill_price;
   double            slippage_points;
   double            volume;
  };

//--- Exactly one OrderSend. No retry, no re-quote loop.
bool G3SendMarketOrder(const string symbol,const ENUM_G3_SIDE side,
                       const double volume,const double sl_price,
                       const double tp_price,const DeviationPlan &dev,
                       const MarketSnapshot &m,const long magic,
                       const string comment,OrderOutcome &out)
  {
   out.sent=false;
   out.filled=false;
   out.retcode=0;
   out.ticket=0;
   out.requested_price=(side==G3_SIDE_BUY)?m.ask:m.bid;
   out.fill_price=0.0;
   out.slippage_points=0.0;
   out.volume=volume;
   if(!dev.send_allowed)
      return(false);

   MqlTradeRequest req;
   MqlTradeResult  res;
   ZeroMemory(req);
   ZeroMemory(res);
   req.action      =TRADE_ACTION_DEAL;
   req.symbol      =symbol;
   req.volume      =volume;
   req.type        =(side==G3_SIDE_BUY)?ORDER_TYPE_BUY:ORDER_TYPE_SELL;
   req.price       =out.requested_price;
   req.sl          =sl_price;
   req.tp          =tp_price;
   req.deviation   =(ulong)dev.send_points;
   req.magic       =(ulong)magic;
   req.comment     =comment;
   req.type_filling=G3FillingMode(symbol);
   req.type_time   =ORDER_TIME_GTC;

   out.sent=true;
   bool ok=OrderSend(req,res);
   out.retcode=res.retcode;
   out.ticket=res.order;
   if(!ok)
      return(false);
   if(res.retcode!=TRADE_RETCODE_DONE && res.retcode!=TRADE_RETCODE_PLACED)
      return(false);
   out.filled=true;
   out.fill_price=(res.price>0.0)?res.price:out.requested_price;
   out.volume=(res.volume>0.0)?res.volume:volume;
   if(m.point>0.0)
     {
      double diff=(side==G3_SIDE_BUY)
                  ?(out.fill_price-out.requested_price)
                  :(out.requested_price-out.fill_price);
      out.slippage_points=diff/m.point;     // positive = worse than requested
     }
   return(true);
  }

//--- Close a fraction (or all) of a hedging position by ticket.
bool G3ClosePositionVolume(const string symbol,const ulong ticket,
                           const double volume,const long magic,
                           const DeviationPlan &dev,uint &retcode_out)
  {
   retcode_out=0;
   if(!PositionSelectByTicket(ticket))
      return(false);
   long ptype=PositionGetInteger(POSITION_TYPE);
   MqlTick tick;
   if(!SymbolInfoTick(symbol,tick))
      return(false);
   MqlTradeRequest req;
   MqlTradeResult  res;
   ZeroMemory(req);
   ZeroMemory(res);
   req.action      =TRADE_ACTION_DEAL;
   req.symbol      =symbol;
   req.position    =ticket;
   req.volume      =volume;
   req.magic       =(ulong)magic;
   req.deviation   =(ulong)((dev.send_points>0)?dev.send_points:1);
   req.type_filling=G3FillingMode(symbol);
   if(ptype==POSITION_TYPE_BUY)
     {
      req.type =ORDER_TYPE_SELL;
      req.price=tick.bid;
     }
   else
     {
      req.type =ORDER_TYPE_BUY;
      req.price=tick.ask;
     }
   bool ok=OrderSend(req,res);
   retcode_out=res.retcode;
   return(ok && (res.retcode==TRADE_RETCODE_DONE || res.retcode==TRADE_RETCODE_PLACED));
  }

//--- Modify the stop loss of an open position.
bool G3ModifyStop(const string symbol,const ulong ticket,const double sl,
                  const double tp,uint &retcode_out)
  {
   retcode_out=0;
   if(!PositionSelectByTicket(ticket))
      return(false);
   MqlTradeRequest req;
   MqlTradeResult  res;
   ZeroMemory(req);
   ZeroMemory(res);
   req.action  =TRADE_ACTION_SLTP;
   req.symbol  =symbol;
   req.position=ticket;
   req.sl      =sl;
   req.tp      =tp;
   bool ok=OrderSend(req,res);
   retcode_out=res.retcode;
   return(ok && res.retcode==TRADE_RETCODE_DONE);
  }

#endif // G3_HOST_TEST

#endif // G3_ORDERMANAGER_MQH
//+------------------------------------------------------------------+
