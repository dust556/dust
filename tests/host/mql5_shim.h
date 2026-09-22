//+------------------------------------------------------------------+
//| mql5_shim.h                                                      |
//|                                                                  |
//| Minimal MQL5 compatibility layer that lets a host C++ compiler    |
//| build the PURE sections of the G3 Research EA headers (everything |
//| outside "#ifndef G3_HOST_TEST").                                  |
//|                                                                  |
//| It exists so the specification arithmetic can be executed and     |
//| asserted on a machine without MetaTrader. It is NOT a MetaTrader  |
//| emulator and it is never compiled into the EA.                    |
//+------------------------------------------------------------------+
#ifndef G3_MQL5_SHIM_H
#define G3_MQL5_SHIM_H

#define G3_HOST_TEST 1

#include <string>
#include <cmath>
#include <cstdio>
#include <cstdlib>

typedef std::string        string;
typedef unsigned long      ulong;
typedef unsigned int       uint;
typedef unsigned short     ushort;
typedef long long          datetime;

//--- math -----------------------------------------------------------
inline double MathAbs(const double v)   { return (v<0.0)?-v:v; }
inline double MathSqrt(const double v)  { return std::sqrt(v); }
inline double MathFloor(const double v) { return std::floor(v); }
inline double MathLog(const double v)   { return std::log(v); }
inline double MathMax(const double a,const double b) { return (a>b)?a:b; }
inline double MathMin(const double a,const double b) { return (a<b)?a:b; }

//--- strings --------------------------------------------------------
inline int    StringLen(const string &s) { return (int)s.size(); }
inline ushort StringGetCharacter(const string &s,const int i)
  {
   if(i<0 || i>=(int)s.size()) return 0;
   return (ushort)(unsigned char)s[i];
  }
inline int StringFind(const string &s,const string &needle,const int start=0)
  {
   if(start<0 || start>(int)s.size()) return -1;
   size_t p=s.find(needle,(size_t)start);
   return (p==string::npos)?-1:(int)p;
  }
inline string StringSubstr(const string &s,const int start,const int count=-1)
  {
   if(start<0 || start>=(int)s.size()) return string("");
   if(count<0) return s.substr((size_t)start);
   return s.substr((size_t)start,(size_t)count);
  }
inline double StringToDouble(const string &s) { return std::atof(s.c_str()); }
inline long   StringToInteger(const string &s) { return std::atoll(s.c_str()); }

inline string IntegerToString(const long long v)
  {
   char buf[32];
   std::snprintf(buf,sizeof(buf),"%lld",v);
   return string(buf);
  }
inline string IntegerToString(const long v)      { return IntegerToString((long long)v); }
inline string IntegerToString(const int v)       { return IntegerToString((long long)v); }
inline string IntegerToString(const ulong v)     { return IntegerToString((long long)v); }

inline string DoubleToString(const double v,const int digits=8)
  {
   char fmt[16];
   char buf[64];
   std::snprintf(fmt,sizeof(fmt),"%%.%df",(digits<0)?8:digits);
   std::snprintf(buf,sizeof(buf),fmt,v);
   return string(buf);
  }

#endif // G3_MQL5_SHIM_H
