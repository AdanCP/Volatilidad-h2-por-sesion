#include <vector>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <ctime>
#include <string>
#include <algorithm>
#include <iostream>
typedef long long datetime; typedef std::string string; typedef unsigned long long ulong_; typedef std::vector<double> Arr; typedef std::vector<datetime> ArrT;
#define input
#define MathMax std::max
#define MathMin std::min
#define MathAbs std::fabs
#define MathFloor std::floor
struct MqlDateTime{int year,mon,day,hour,min,sec,day_of_week,day_of_year;};
inline void TimeToStruct(datetime t, MqlDateTime&s){time_t tt=t;tm g;gmtime_r(&tt,&g);s.year=g.tm_year+1900;s.mon=g.tm_mon+1;s.day=g.tm_mday;s.hour=g.tm_hour;s.min=g.tm_min;s.sec=g.tm_sec;s.day_of_week=g.tm_wday;}
inline datetime StructToTime(MqlDateTime&s){tm g{};g.tm_year=s.year-1900;g.tm_mon=s.mon-1;g.tm_mday=s.day;g.tm_hour=s.hour;g.tm_min=s.min;g.tm_sec=s.sec;return timegm(&g);}
template<class T> void ArrayResize(std::vector<T>&a,int n){a.resize(n);}
template<class T> int ArrayCopy(std::vector<T>&d,const std::vector<T>&s){d=s;return (int)s.size();}
template<class T> int ArraySize(const std::vector<T>&a){return (int)a.size();}
template<class T> void ArraySetAsSeries(std::vector<T>&,bool){}
enum ENUM_TIMEFRAMES{PERIOD_CURRENT=0,PERIOD_M1=1,PERIOD_M5=5,PERIOD_M15=15,PERIOD_M30=30,PERIOD_H1=60,PERIOD_H4=240,PERIOD_D1=1440};
struct MqlRates{datetime time;double open,high,low,close;long tick_volume;int spread;long real_volume;};
struct MqlTradeRequest{int action;unsigned long order,position;std::string symbol,comment;double volume,price,sl,tp;int type,type_filling,type_time;long magic;int deviation;};
struct MqlTradeResult{int retcode;};
inline void ZeroMemory(MqlTradeRequest&r){r=MqlTradeRequest();} inline void ZeroMemory(MqlTradeResult&r){r.retcode=0;}
enum{TRADE_ACTION_DEAL,TRADE_ACTION_PENDING,TRADE_ACTION_REMOVE,ORDER_TYPE_BUY,ORDER_TYPE_SELL,ORDER_TYPE_BUY_LIMIT,ORDER_TYPE_SELL_LIMIT,ORDER_FILLING_FOK,ORDER_FILLING_IOC,ORDER_FILLING_RETURN,ORDER_TIME_GTC,TRADE_RETCODE_DONE,TRADE_RETCODE_PLACED,INIT_SUCCEEDED,INIT_FAILED,INIT_PARAMETERS_INCORRECT,POSITION_TYPE_BUY,POSITION_MAGIC,POSITION_TYPE,POSITION_TICKET,POSITION_VOLUME,ORDER_SYMBOL,ORDER_MAGIC,SYMBOL_FILLING_MODE,SYMBOL_FILLING_FOK,SYMBOL_FILLING_IOC,SYMBOL_DIGITS,SYMBOL_VOLUME_STEP,SYMBOL_VOLUME_MIN,SYMBOL_VOLUME_MAX,SYMBOL_BID,SYMBOL_ASK,SYMBOL_TRADE_TICK_SIZE,SYMBOL_TRADE_TICK_VALUE,ACCOUNT_EQUITY,ACCOUNT_BALANCE};
typedef int ENUM_ORDER_TYPE_FILLING; typedef int ENUM_ORDER_TYPE;
#define ENUM_ORDER_TYPE_FILLING int
inline bool OrderSend(MqlTradeRequest&,MqlTradeResult&){return true;}
inline int PositionsTotal(){return 0;} inline int OrdersTotal(){return 0;}
inline std::string PositionGetSymbol(int){return "";} inline long PositionGetInteger(int){return 0;} inline double PositionGetDouble(int){return 0;}
inline unsigned long OrderGetTicket(int){return 0;} inline std::string OrderGetString(int){return "";} inline long OrderGetInteger(int){return 0;}
inline double SymbolInfoDouble(const std::string&,int){return 1;} inline long SymbolInfoInteger(const std::string&,int){return 0;}
inline double NormalizeDouble(double v,int){return v;}
inline double AccountInfoDouble(int){return 100000;}
inline bool GlobalVariableCheck(const std::string&){return false;} inline double GlobalVariableGet(const std::string&){return 0;} inline void GlobalVariableSet(const std::string&,double){}
inline datetime iTime(const std::string&,int,int){return 0;} inline datetime TimeCurrent(){return 0;} static int g_psec=3600; inline int PeriodSeconds(){return g_psec;} inline int PeriodSeconds(int tf){return tf*60;}
inline bool CopyRates(...){return false;}
inline void Print(...){}
template<class A,class... R> void Print(A,R...){}
static std::string _Symbol="X"; static int _Period=60;
inline std::string IntegerToString(int v){return std::to_string(v);}

#define MathRound std::round
inline datetime TimeTradeServer(){return 0;} inline datetime TimeGMT(){return 0;}
inline std::string EnumToString(int v){return std::to_string(v);}

#define MQL_TESTER 1
#define MQL_TRADE_ALLOWED 2
inline long MQLInfoInteger(int){return 1;} inline bool SendNotification(const std::string&){return true;} inline int GetLastError(){return 0;}
inline std::string StringSubstr(const std::string&s,int a,int b=-1){return s.substr(a,b<0?std::string::npos:b);}
inline std::string DoubleToString(double v,int){return std::to_string(v);}
struct MqlTradeTransaction{int type;unsigned long deal;};
enum{TRADE_TRANSACTION_DEAL_ADD=100,DEAL_MAGIC,DEAL_ENTRY,DEAL_ENTRY_IN,DEAL_TYPE,DEAL_TYPE_BUY,DEAL_PRICE,DEAL_VOLUME,DEAL_POSITION_ID,POSITION_SL,POSITION_TP};
inline bool HistoryDealSelect(unsigned long){return false;} inline long HistoryDealGetInteger(unsigned long,int){return 0;} inline double HistoryDealGetDouble(unsigned long,int){return 0;}
inline bool PositionSelectByTicket(unsigned long){return false;}

inline void EventSetTimer(int){} inline void EventKillTimer(){}
inline long TerminalInfoInteger(int){return 1;} inline long AccountInfoInteger(int){return 1;}
inline datetime TimeLocal(){return 0;}
inline std::string TimeToString(datetime,int=0){return "";}
enum{TERMINAL_CONNECTED=300,TERMINAL_TRADE_ALLOWED,ACCOUNT_TRADE_EXPERT,TIME_MINUTES,REASON_INITFAILED,REASON_REMOVE,REASON_CHARTCLOSE,REASON_CLOSE,REASON_PROGRAM,REASON_RECOMPILE,REASON_CHARTCHANGE,REASON_TEMPLATE,REASON_ACCOUNT};

enum{DEAL_ENTRY_OUT=400,DEAL_ENTRY_OUT_BY,DEAL_ENTRY_INOUT,DEAL_REASON,DEAL_REASON_TP,DEAL_REASON_SL,DEAL_REASON_SO,DEAL_REASON_EXPERT,DEAL_REASON_CLIENT,DEAL_REASON_MOBILE,DEAL_REASON_WEB,DEAL_PROFIT,DEAL_SWAP,DEAL_COMMISSION,ACCOUNT_CURRENCY,DEAL_TYPE_SELL};
inline std::string AccountInfoString(int){return "USD";}

enum{TIME_DATE=16};

enum{POSITION_TIME=500,POSITION_COMMENT};
inline std::string PositionGetString(int){return "";}
inline int StringFind(const std::string&a,const std::string&b){auto p=a.find(b);return p==std::string::npos?-1:(int)p;}
enum{DEAL_TIME=600};
