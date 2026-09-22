//+------------------------------------------------------------------+
//|                                                   StateStore.mqh |
//|   Master Specification v0.4 sections 4.1, 11.2 and 11.3 -        |
//|   durable state, dual store reconciliation and the fail-closed   |
//|   exactly-once signal consumption protocol.                      |
//|                                                                  |
//|   Section 11.2 keys the store on account_login + MagicNumber, so  |
//|   the account level fields are SHARED by every symbol instance:   |
//|     PeakEquity, DDState, HardStopLatched, DailyStartEquity,       |
//|     ServerDate, schema_version, checksum                          |
//|   (DEV-003 fix: the previous build put the symbol into the key,   |
//|   which split the drawdown state across instances.)               |
//|                                                                   |
//|   The signal consumption ledger (last_signal_id) is inherently    |
//|   per symbol, because signal_id is symbol + M5 bar open time. It  |
//|   is stored under account_login + MagicNumber + symbol.           |
//|                                                                  |
//|   Both records are written to two independent stores on every     |
//|   flush: a file in the terminal common folder and terminal Global |
//|   Variables. On disagreement the MORE CONSERVATIVE state is       |
//|   adopted. If both stores are unrecoverable the EA enters         |
//|   STATE_UNCERTAIN and refuses every new entry.                    |
//+------------------------------------------------------------------+
#ifndef G3_STATESTORE_MQH
#define G3_STATESTORE_MQH

#include "G3Types.mqh"
#include "RiskManager.mqh"
#include "ExitManager.mqh"

#define G3_STATE_SCHEMA_VERSION 2
#define G3_CHECKSUM_MOD         1000000007

//--- account level record, key = account_login + MagicNumber
struct G3State
  {
   int               schema_version;
   double            peak_equity;
   ENUM_G3_DD_STATE  dd_state;
   bool              hard_stop_latched;
   double            daily_start_equity;
   long              server_date;        // server midnight of the current day
   double            checksum;
  };

//--- signal ledger, key = account_login + MagicNumber + symbol
struct G3SignalState
  {
   int               schema_version;
   long              last_signal_time;   // M5 bar open time of the last consumed signal
   string            last_signal_id;
   double            checksum;
  };

//+------------------------------------------------------------------+
//| PURE - serialisation                                             |
//+------------------------------------------------------------------+

//--- Value of "key=value" inside a "|" separated record, or "" .
string G3ExtractField(const string record,const string key)
  {
   string needle=key+"=";
   int at=StringFind(record,needle,0);
   if(at<0)
      return("");
   int from=at+StringLen(needle);
   int end=StringFind(record,"|",from);
   if(end<0)
      end=StringLen(record);
   return(StringSubstr(record,from,end-from));
  }

//--- Checksum kept inside the exact double range (GV stores doubles).
double G3StateChecksum(const string record)
  {
   ulong h=G3Fnv1a(record);
   return((double)(h%(ulong)G3_CHECKSUM_MOD));
  }

void G3StateInit(G3State &s)
  {
   s.schema_version=G3_STATE_SCHEMA_VERSION;
   s.peak_equity=0.0;
   s.dd_state=G3_DD_NORMAL;
   s.hard_stop_latched=false;
   s.daily_start_equity=0.0;
   s.server_date=0;
   s.checksum=0.0;
  }

void G3SignalStateInit(G3SignalState &s)
  {
   s.schema_version=G3_STATE_SCHEMA_VERSION;
   s.last_signal_time=0;
   s.last_signal_id="";
   s.checksum=0.0;
  }

//--- Canonical account record WITHOUT the checksum field.
string G3StateToRecord(const G3State &s)
  {
   string r="";
   r=r+"v="+IntegerToString(s.schema_version);
   r=r+"|peak="+DoubleToString(s.peak_equity,2);
   r=r+"|dd="+IntegerToString((int)s.dd_state);
   r=r+"|latch="+IntegerToString(s.hard_stop_latched?1:0);
   r=r+"|dse="+DoubleToString(s.daily_start_equity,2);
   r=r+"|date="+IntegerToString(s.server_date);
   return(r);
  }

string G3StateToLine(const G3State &s)
  {
   string body=G3StateToRecord(s);
   return(body+"|chk="+DoubleToString(G3StateChecksum(body),0));
  }

//--- Canonical signal record WITHOUT the checksum field.
string G3SignalStateToRecord(const G3SignalState &s)
  {
   string r="";
   r=r+"v="+IntegerToString(s.schema_version);
   r=r+"|sigt="+IntegerToString(s.last_signal_time);
   r=r+"|sigid="+s.last_signal_id;
   return(r);
  }

string G3SignalStateToLine(const G3SignalState &s)
  {
   string body=G3SignalStateToRecord(s);
   return(body+"|chk="+DoubleToString(G3StateChecksum(body),0));
  }

//--- Split a stored line into its body and its checksum, validating both.
bool G3SplitCheckedLine(const string line,string &body_out)
  {
   body_out="";
   if(StringLen(line)<8)
      return(false);
   int at=StringFind(line,"|chk=",0);
   if(at<0)
      return(false);
   string body=StringSubstr(line,0,at);
   string chk=StringSubstr(line,at+5);
   if(MathAbs(G3StateChecksum(body)-StringToDouble(chk))>0.5)
      return(false);
   body_out=body;
   return(true);
  }

//--- Parse and validate a stored account record. False on any corruption.
bool G3ParseStateLine(const string line,G3State &out)
  {
   string body="";
   if(!G3SplitCheckedLine(line,body))
      return(false);
   string v=G3ExtractField(body,"v");
   if(v=="")
      return(false);
   out.schema_version=(int)StringToInteger(v);
   if(out.schema_version!=G3_STATE_SCHEMA_VERSION)
      return(false);
   out.peak_equity=StringToDouble(G3ExtractField(body,"peak"));
   int dd=(int)StringToInteger(G3ExtractField(body,"dd"));
   if(dd<0 || dd>4)
      return(false);
   out.dd_state=(ENUM_G3_DD_STATE)dd;
   out.hard_stop_latched=(StringToInteger(G3ExtractField(body,"latch"))!=0);
   out.daily_start_equity=StringToDouble(G3ExtractField(body,"dse"));
   out.server_date=(long)StringToInteger(G3ExtractField(body,"date"));
   out.checksum=G3StateChecksum(body);
   if(out.peak_equity<0.0 || out.daily_start_equity<0.0)
      return(false);
   return(true);
  }

//--- Parse and validate a stored signal ledger record.
bool G3ParseSignalStateLine(const string line,G3SignalState &out)
  {
   string body="";
   if(!G3SplitCheckedLine(line,body))
      return(false);
   string v=G3ExtractField(body,"v");
   if(v=="")
      return(false);
   out.schema_version=(int)StringToInteger(v);
   if(out.schema_version!=G3_STATE_SCHEMA_VERSION)
      return(false);
   out.last_signal_time=(long)StringToInteger(G3ExtractField(body,"sigt"));
   out.last_signal_id=G3ExtractField(body,"sigid");
   out.checksum=G3StateChecksum(body);
   if(out.last_signal_time<0)
      return(false);
   return(true);
  }

//+------------------------------------------------------------------+
//| PURE - dual store reconciliation                                 |
//+------------------------------------------------------------------+

//--- Conservative merge of two recovered account records (section 11.2:
//--- "より保守的なstate（高いPeak、厳しいDD state、HardStop=trueを優先）"):
//---   peak_equity        -> the higher peak (implies the deeper DD)
//---   dd_state           -> the more severe one
//---   hard_stop_latched  -> logical OR
//---   daily_start_equity -> the higher value (locks earlier)
//---   server_date        -> the later date
G3State G3MergeConservative(const G3State &a,const G3State &b)
  {
   G3State o=a;
   o.dd_state=G3MoreConservativeState(a.dd_state,b.dd_state);
   o.hard_stop_latched=(a.hard_stop_latched||b.hard_stop_latched);
   o.peak_equity=(a.peak_equity>=b.peak_equity)?a.peak_equity:b.peak_equity;
   o.daily_start_equity=(a.daily_start_equity>=b.daily_start_equity)
                        ?a.daily_start_equity:b.daily_start_equity;
   o.server_date=(a.server_date>=b.server_date)?a.server_date:b.server_date;
   o.checksum=G3StateChecksum(G3StateToRecord(o));
   return(o);
  }

//--- Conservative merge of two signal ledgers: never re-arm a signal.
G3SignalState G3MergeSignalConservative(const G3SignalState &a,const G3SignalState &b)
  {
   G3SignalState o=a;
   if(b.last_signal_time>a.last_signal_time)
     {
      o.last_signal_time=b.last_signal_time;
      o.last_signal_id=b.last_signal_id;
     }
   o.checksum=G3StateChecksum(G3SignalStateToRecord(o));
   return(o);
  }

//--- Decide the effective account state from the two stores.
ENUM_G3_STORE_STATUS G3ReconcileStores(const bool file_ok,const G3State &file_state,
                                       const bool gv_ok,const G3State &gv_state,
                                       const bool anything_stored,
                                       G3State &out)
  {
   if(file_ok && gv_ok)
     {
      if(G3StateToRecord(file_state)==G3StateToRecord(gv_state))
        {
         out=file_state;
         return(G3_STORE_OK);
        }
      out=G3MergeConservative(file_state,gv_state);
      return(G3_STORE_MISMATCH);
     }
   if(file_ok)
     {
      out=file_state;
      return(G3_STORE_FILE_ONLY);
     }
   if(gv_ok)
     {
      out=gv_state;
      return(G3_STORE_GV_ONLY);
     }
   if(!anything_stored)
     {
      G3StateInit(out);
      return(G3_STORE_FRESH);
     }
   G3StateInit(out);
   out.dd_state=G3_DD_UNCERTAIN;
   return(G3_STORE_BOTH_LOST);
  }

//--- Decide the effective signal ledger from the two stores.
ENUM_G3_STORE_STATUS G3ReconcileSignalStores(const bool file_ok,const G3SignalState &file_state,
                                             const bool gv_ok,const G3SignalState &gv_state,
                                             const bool anything_stored,
                                             G3SignalState &out)
  {
   if(file_ok && gv_ok)
     {
      if(G3SignalStateToRecord(file_state)==G3SignalStateToRecord(gv_state))
        {
         out=file_state;
         return(G3_STORE_OK);
        }
      out=G3MergeSignalConservative(file_state,gv_state);
      return(G3_STORE_MISMATCH);
     }
   if(file_ok)
     {
      out=file_state;
      return(G3_STORE_FILE_ONLY);
     }
   if(gv_ok)
     {
      out=gv_state;
      return(G3_STORE_GV_ONLY);
     }
   G3SignalStateInit(out);
   return(anything_stored?G3_STORE_BOTH_LOST:G3_STORE_FRESH);
  }

//--- Exactly-once guard: a signal whose M5 bar time is not newer than
//--- the last consumed one is refused (fail closed).
bool G3SignalAlreadyConsumed(const G3SignalState &s,const string signal_id,
                             const long m5_bar_time)
  {
   if(s.last_signal_id==signal_id)
      return(true);
   return(m5_bar_time<=s.last_signal_time);
  }

//+------------------------------------------------------------------+
//| TERMINAL (excluded from the host test harness)                   |
//+------------------------------------------------------------------+
#ifndef G3_HOST_TEST

#define G3_STORE_FOLDER "G3RSRCH"

struct G3StoreContext
  {
   string            symbol;
   long              magic;
   //--- account level (account_login + magic)
   string            state_file;
   string            state_tmp;
   string            state_gv;
   //--- per symbol signal ledger (account_login + magic + symbol)
   string            signal_file;
   string            signal_tmp;
   string            signal_gv;
   //--- per symbol runtime position tracking
   string            trade_file;
   string            trade_tmp;
   string            audit_file;
   string            lock_name;
  };

void G3StoreContextInit(G3StoreContext &ctx,const string symbol,const long magic)
  {
   long account=AccountInfoInteger(ACCOUNT_LOGIN);
   string acc=IntegerToString(account);
   string mag=IntegerToString(magic);
   string tag=acc+"_"+mag;
   ctx.symbol     =symbol;
   ctx.magic      =magic;
   ctx.state_file =G3_STORE_FOLDER+"\\state_"+tag+".txt";
   ctx.state_tmp  =G3_STORE_FOLDER+"\\state_"+tag+".tmp";
   ctx.state_gv   ="G3_"+mag+"_";
   ctx.signal_file=G3_STORE_FOLDER+"\\signal_"+tag+"_"+symbol+".txt";
   ctx.signal_tmp =G3_STORE_FOLDER+"\\signal_"+tag+"_"+symbol+".tmp";
   ctx.signal_gv  ="G3S_"+mag+"_"+symbol+"_";
   ctx.trade_file =G3_STORE_FOLDER+"\\trades_"+tag+"_"+symbol+".csv";
   ctx.trade_tmp  =G3_STORE_FOLDER+"\\trades_"+tag+"_"+symbol+".tmp";
   ctx.audit_file =G3_STORE_FOLDER+"\\audit_"+tag+".log";
   ctx.lock_name  ="G3LOCK_"+mag;
  }

//+------------------------------------------------------------------+
//| File store                                                       |
//+------------------------------------------------------------------+
bool G3WriteLineFile(const string tmp_path,const string final_path,const string line)
  {
   int h=FileOpen(tmp_path,FILE_WRITE|FILE_TXT|FILE_ANSI|FILE_COMMON);
   if(h==INVALID_HANDLE)
      return(false);
   FileWriteString(h,line+"\r\n");
   FileFlush(h);
   FileClose(h);
   //--- atomic-ish publish: replace the primary file with the temp file
   if(FileIsExist(final_path,FILE_COMMON))
      FileDelete(final_path,FILE_COMMON);
   return(FileMove(tmp_path,FILE_COMMON,final_path,FILE_REWRITE|FILE_COMMON));
  }

bool G3ReadLineFile(const string path,string &line_out,bool &existed)
  {
   line_out="";
   existed=FileIsExist(path,FILE_COMMON);
   if(!existed)
      return(false);
   int h=FileOpen(path,FILE_READ|FILE_TXT|FILE_ANSI|FILE_COMMON);
   if(h==INVALID_HANDLE)
      return(false);
   line_out=FileReadString(h);
   FileClose(h);
   return(true);
  }

//+------------------------------------------------------------------+
//| Terminal Global Variable store                                   |
//+------------------------------------------------------------------+
bool G3WriteStateGV(const G3StoreContext &ctx,const G3State &s)
  {
   string body=G3StateToRecord(s);
   bool ok=true;
   ok=ok && GlobalVariableSet(ctx.state_gv+"V",(double)s.schema_version)>0;
   ok=ok && GlobalVariableSet(ctx.state_gv+"PEAK",s.peak_equity)>0;
   ok=ok && GlobalVariableSet(ctx.state_gv+"DD",(double)s.dd_state)>0;
   ok=ok && GlobalVariableSet(ctx.state_gv+"LATCH",s.hard_stop_latched?1.0:0.0)>0;
   ok=ok && GlobalVariableSet(ctx.state_gv+"DSE",s.daily_start_equity)>0;
   ok=ok && GlobalVariableSet(ctx.state_gv+"DATE",(double)s.server_date)>0;
   ok=ok && GlobalVariableSet(ctx.state_gv+"CHK",G3StateChecksum(body))>0;
   return(ok);
  }

bool G3ReadStateGV(const G3StoreContext &ctx,G3State &s,bool &existed)
  {
   existed=GlobalVariableCheck(ctx.state_gv+"CHK");
   if(!existed)
      return(false);
   G3StateInit(s);
   if(!GlobalVariableCheck(ctx.state_gv+"V"))
      return(false);
   s.schema_version=(int)GlobalVariableGet(ctx.state_gv+"V");
   if(s.schema_version!=G3_STATE_SCHEMA_VERSION)
      return(false);
   s.peak_equity=GlobalVariableGet(ctx.state_gv+"PEAK");
   int dd=(int)GlobalVariableGet(ctx.state_gv+"DD");
   if(dd<0 || dd>4)
      return(false);
   s.dd_state=(ENUM_G3_DD_STATE)dd;
   s.hard_stop_latched=(GlobalVariableGet(ctx.state_gv+"LATCH")!=0.0);
   s.daily_start_equity=GlobalVariableGet(ctx.state_gv+"DSE");
   s.server_date=(long)GlobalVariableGet(ctx.state_gv+"DATE");
   double stored=GlobalVariableGet(ctx.state_gv+"CHK");
   double expect=G3StateChecksum(G3StateToRecord(s));
   if(MathAbs(stored-expect)>0.5)
      return(false);
   s.checksum=expect;
   return(true);
  }

bool G3WriteSignalGV(const G3StoreContext &ctx,const G3SignalState &s)
  {
   string body=G3SignalStateToRecord(s);
   bool ok=true;
   ok=ok && GlobalVariableSet(ctx.signal_gv+"V",(double)s.schema_version)>0;
   ok=ok && GlobalVariableSet(ctx.signal_gv+"SIGT",(double)s.last_signal_time)>0;
   ok=ok && GlobalVariableSet(ctx.signal_gv+"CHK",G3StateChecksum(body))>0;
   return(ok);
  }

bool G3ReadSignalGV(const G3StoreContext &ctx,G3SignalState &s,bool &existed)
  {
   existed=GlobalVariableCheck(ctx.signal_gv+"CHK");
   if(!existed)
      return(false);
   G3SignalStateInit(s);
   if(!GlobalVariableCheck(ctx.signal_gv+"V"))
      return(false);
   s.schema_version=(int)GlobalVariableGet(ctx.signal_gv+"V");
   if(s.schema_version!=G3_STATE_SCHEMA_VERSION)
      return(false);
   s.last_signal_time=(long)GlobalVariableGet(ctx.signal_gv+"SIGT");
   s.last_signal_id=(s.last_signal_time>0)
                    ?(ctx.symbol+"#"+IntegerToString(s.last_signal_time)):"";
   double stored=GlobalVariableGet(ctx.signal_gv+"CHK");
   double expect=G3StateChecksum(G3SignalStateToRecord(s));
   if(MathAbs(stored-expect)>0.5)
      return(false);
   s.checksum=expect;
   return(true);
  }

//+------------------------------------------------------------------+
//| Combined load / flush                                            |
//+------------------------------------------------------------------+
ENUM_G3_STORE_STATUS G3LoadState(const G3StoreContext &ctx,G3State &out)
  {
   G3State fs,gs;
   G3StateInit(fs);
   G3StateInit(gs);
   string line="";
   bool f_existed=false,g_existed=false;
   bool f_ok=(G3ReadLineFile(ctx.state_file,line,f_existed) && G3ParseStateLine(line,fs));
   bool g_ok=G3ReadStateGV(ctx,gs,g_existed);
   return(G3ReconcileStores(f_ok,fs,g_ok,gs,(f_existed||g_existed),out));
  }

//--- Flush the account record to BOTH stores.
bool G3PersistState(const G3StoreContext &ctx,G3State &s)
  {
   s.schema_version=G3_STATE_SCHEMA_VERSION;
   s.checksum=G3StateChecksum(G3StateToRecord(s));
   bool f=G3WriteLineFile(ctx.state_tmp,ctx.state_file,G3StateToLine(s));
   bool g=G3WriteStateGV(ctx,s);
   return(f && g);
  }

ENUM_G3_STORE_STATUS G3LoadSignalState(const G3StoreContext &ctx,G3SignalState &out)
  {
   G3SignalState fs,gs;
   G3SignalStateInit(fs);
   G3SignalStateInit(gs);
   string line="";
   bool f_existed=false,g_existed=false;
   bool f_ok=(G3ReadLineFile(ctx.signal_file,line,f_existed) && G3ParseSignalStateLine(line,fs));
   bool g_ok=G3ReadSignalGV(ctx,gs,g_existed);
   return(G3ReconcileSignalStores(f_ok,fs,g_ok,gs,(f_existed||g_existed),out));
  }

bool G3PersistSignalState(const G3StoreContext &ctx,G3SignalState &s)
  {
   s.schema_version=G3_STATE_SCHEMA_VERSION;
   s.checksum=G3StateChecksum(G3SignalStateToRecord(s));
   bool f=G3WriteLineFile(ctx.signal_tmp,ctx.signal_file,G3SignalStateToLine(s));
   bool g=G3WriteSignalGV(ctx,s);
   return(f && g);
  }

//--- Adopt the account record another instance may have advanced.
//--- The caller holds the portfolio lock. The merge is conservative, and
//--- the drawdown transition is re-evaluated by the caller afterwards.
void G3RefreshSharedState(const G3StoreContext &ctx,G3State &s)
  {
   G3State gv;
   G3StateInit(gv);
   bool existed=false;
   if(!G3ReadStateGV(ctx,gv,existed))
      return;
   s=G3MergeConservative(s,gv);
  }

//--- Atomic consume of a signal_id.
//--- Order mandated by Master Specification 4.1:
//---   1. consumed check
//---   2. atomic consume
//---   3. flush to file + global variables
//---   4. only then evaluate the signal
bool G3ConsumeSignal(const G3StoreContext &ctx,G3SignalState &s,const string signal_id,
                     const long m5_bar_time,ENUM_G3_REASON &reason_out)
  {
   reason_out=G3_R_NONE;
   if(G3SignalAlreadyConsumed(s,signal_id,m5_bar_time))
     {
      reason_out=G3_R_SIGNAL_ALREADY_CONSUMED;
      return(false);
     }
   long prev_time=s.last_signal_time;
   string prev_id=s.last_signal_id;
   s.last_signal_time=m5_bar_time;
   s.last_signal_id=signal_id;
   if(!G3PersistSignalState(ctx,s))
     {
      //--- fail closed: the consume could not be made durable, so the
      //--- opportunity is dropped rather than risking a duplicate.
      s.last_signal_time=prev_time;
      s.last_signal_id=prev_id;
      reason_out=G3_R_DUPLICATE_SIGNAL_ID;
      return(false);
     }
   return(true);
  }

//+------------------------------------------------------------------+
//| Audit log (manual HARD_STOP reset and other audited events)      |
//+------------------------------------------------------------------+
bool G3AuditLog(const G3StoreContext &ctx,const string event,const string detail)
  {
   int h=FileOpen(ctx.audit_file,FILE_READ|FILE_WRITE|FILE_TXT|FILE_ANSI|FILE_COMMON);
   if(h==INVALID_HANDLE)
      return(false);
   FileSeek(h,0,SEEK_END);
   FileWriteString(h,TimeToString(TimeCurrent(),TIME_DATE|TIME_SECONDS)+"\t"+
                   TimeToString(TimeGMT(),TIME_DATE|TIME_SECONDS)+"\t"+
                   ctx.symbol+"\t"+event+"\t"+detail+"\r\n");
   FileFlush(h);
   FileClose(h);
   return(true);
  }

//--- Manual reset of a latched HARD_STOP. Admissible only below 9% DD
//--- and always audited. Never called automatically.
bool G3ManualHardStopReset(const G3StoreContext &ctx,G3State &s,const double dd_pct)
  {
   if(!s.hard_stop_latched)
      return(false);
   if(!G3ManualResetAdmissible(dd_pct))
     {
      G3AuditLog(ctx,"MANUAL_RESET_REFUSED","dd_pct="+DoubleToString(dd_pct,3));
      return(false);
     }
   s.hard_stop_latched=false;
   s.dd_state=G3_DD_RESTRICTED;
   bool ok=G3PersistState(ctx,s);
   G3AuditLog(ctx,ok?"MANUAL_RESET_APPLIED":"MANUAL_RESET_PERSIST_FAILED",
              "dd_pct="+DoubleToString(dd_pct,3));
   return(ok);
  }

//+------------------------------------------------------------------+
//| Position state persistence (restart safety for exits)            |
//+------------------------------------------------------------------+
string G3TradeStateToLine(const G3TradeState &t)
  {
   string r="";
   r=r+IntegerToString((long)t.ticket)+";";
   r=r+t.symbol+";";
   r=r+t.signal_id+";";
   r=r+IntegerToString((int)t.side)+";";
   r=r+IntegerToString(t.entry_time)+";";
   r=r+IntegerToString(t.entry_m5_bar)+";";
   r=r+DoubleToString(t.entry_price,8)+";";
   r=r+DoubleToString(t.initial_sl,8)+";";
   r=r+DoubleToString(t.initial_tp,8)+";";
   r=r+DoubleToString(t.initial_volume,4)+";";
   r=r+DoubleToString(t.current_volume,4)+";";
   r=r+DoubleToString(t.initial_risk_money,4)+";";
   r=r+DoubleToString(t.initial_risk_pct,6)+";";
   r=r+DoubleToString(t.r_distance,8)+";";
   r=r+DoubleToString(t.atr_at_entry,8)+";";
   r=r+DoubleToString(t.mfe_r,6)+";";
   r=r+DoubleToString(t.mae_r,6)+";";
   r=r+DoubleToString(t.mfe_r_3bars,6)+";";
   r=r+DoubleToString(t.mae_r_3bars,6)+";";
   r=r+DoubleToString(t.mfe_r_6bars,6)+";";
   r=r+DoubleToString(t.mae_r_6bars,6)+";";
   r=r+DoubleToString(t.trail_stop,8)+";";
   r=r+DoubleToString(t.extreme_price,8)+";";
   r=r+DoubleToString(t.realized_pl,4)+";";
   r=r+DoubleToString(t.partial_closed_volume,4)+";";
   r=r+IntegerToString(t.bars_held)+";";
   r=r+IntegerToString(t.be_done?1:0)+";";
   r=r+IntegerToString(t.partial_done?1:0)+";";
   r=r+IntegerToString(t.partial_skipped?1:0);
   return(r);
  }

bool G3TradeStateFromLine(const string line,G3TradeState &t)
  {
   string f[];
   int n=StringSplit(line,(ushort)';',f);
   if(n<29)
      return(false);
   t.active               =true;
   t.ticket               =(ulong)StringToInteger(f[0]);
   t.symbol               =f[1];
   t.signal_id            =f[2];
   t.side                 =(ENUM_G3_SIDE)StringToInteger(f[3]);
   t.entry_time           =(long)StringToInteger(f[4]);
   t.entry_m5_bar         =(long)StringToInteger(f[5]);
   t.entry_price          =StringToDouble(f[6]);
   t.initial_sl           =StringToDouble(f[7]);
   t.initial_tp           =StringToDouble(f[8]);
   t.initial_volume       =StringToDouble(f[9]);
   t.current_volume       =StringToDouble(f[10]);
   t.initial_risk_money   =StringToDouble(f[11]);
   t.initial_risk_pct     =StringToDouble(f[12]);
   t.r_distance           =StringToDouble(f[13]);
   t.atr_at_entry         =StringToDouble(f[14]);
   t.mfe_r                =StringToDouble(f[15]);
   t.mae_r                =StringToDouble(f[16]);
   t.mfe_r_3bars          =StringToDouble(f[17]);
   t.mae_r_3bars          =StringToDouble(f[18]);
   t.mfe_r_6bars          =StringToDouble(f[19]);
   t.mae_r_6bars          =StringToDouble(f[20]);
   t.trail_stop           =StringToDouble(f[21]);
   t.extreme_price        =StringToDouble(f[22]);
   t.realized_pl          =StringToDouble(f[23]);
   t.partial_closed_volume=StringToDouble(f[24]);
   t.bars_held            =(int)StringToInteger(f[25]);
   t.be_done              =(StringToInteger(f[26])!=0);
   t.partial_done         =(StringToInteger(f[27])!=0);
   t.partial_skipped      =(StringToInteger(f[28])!=0);
   return(t.ticket>0 && t.r_distance>0.0);
  }

bool G3SaveTradeStates(const G3StoreContext &ctx,const G3TradeState &states[],const int count)
  {
   int h=FileOpen(ctx.trade_tmp,FILE_WRITE|FILE_TXT|FILE_ANSI|FILE_COMMON);
   if(h==INVALID_HANDLE)
      return(false);
   for(int i=0;i<count;i++)
     {
      if(!states[i].active)
         continue;
      FileWriteString(h,G3TradeStateToLine(states[i])+"\r\n");
     }
   FileFlush(h);
   FileClose(h);
   if(FileIsExist(ctx.trade_file,FILE_COMMON))
      FileDelete(ctx.trade_file,FILE_COMMON);
   return(FileMove(ctx.trade_tmp,FILE_COMMON,ctx.trade_file,FILE_REWRITE|FILE_COMMON));
  }

int G3LoadTradeStates(const G3StoreContext &ctx,G3TradeState &states[],const int capacity)
  {
   int count=0;
   if(!FileIsExist(ctx.trade_file,FILE_COMMON))
      return(0);
   int h=FileOpen(ctx.trade_file,FILE_READ|FILE_TXT|FILE_ANSI|FILE_COMMON);
   if(h==INVALID_HANDLE)
      return(0);
   while(!FileIsEnding(h) && count<capacity)
     {
      string line=FileReadString(h);
      if(StringLen(line)<10)
         continue;
      G3TradeState t;
      if(G3TradeStateFromLine(line,t))
        {
         states[count]=t;
         count++;
        }
     }
   FileClose(h);
   return(count);
  }

//+------------------------------------------------------------------+
//| Cross-instance lock (terminal global variable)                   |
//| Serialises both the shared account record update and the         |
//| portfolio admission check across symbol instances.               |
//+------------------------------------------------------------------+
bool G3PortfolioLock(const G3StoreContext &ctx,const int timeout_ms)
  {
   uint start=GetTickCount();
   while((int)(GetTickCount()-start)<=timeout_ms)
     {
      if(!GlobalVariableCheck(ctx.lock_name))
        {
         GlobalVariableTemp(ctx.lock_name);
         GlobalVariableSet(ctx.lock_name,0.0);
        }
      if(GlobalVariableSetOnCondition(ctx.lock_name,1.0,0.0))
         return(true);
     }
   return(false);
  }

void G3PortfolioUnlock(const G3StoreContext &ctx)
  {
   GlobalVariableSet(ctx.lock_name,0.0);
  }

#endif // G3_HOST_TEST

#endif // G3_STATESTORE_MQH
//+------------------------------------------------------------------+
