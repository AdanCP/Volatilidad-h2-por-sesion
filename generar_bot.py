"""Genera el Expert Advisor (.mq5) a partir de los parametros cargados en el backtester.

Solo arma texto: no necesita MT5 ni compilador, asi que funciona tambien en la version online.
El archivo se compila en MetaEditor (F7) y se arrastra a un grafico. Las reglas del EA replican
las del backtester (ver plantilla_bot.mq5); aun asi hay que compararlo en el Strategy Tester.
"""
import re
from datetime import datetime
from typing import Optional


_TF = {"M1": "PERIOD_M1", "M5": "PERIOD_M5", "M15": "PERIOD_M15", "M30": "PERIOD_M30",
       "H1": "PERIOD_H1", "H4": "PERIOD_H4", "D1": "PERIOD_D1"}
_DIR = {"ambas": "BOT_AMBAS", "largos": "BOT_LARGOS", "cortos": "BOT_CORTOS"}
_SL = {"atr": "BOT_SL_ATR", "pct": "BOT_SL_PCT", "usd": "BOT_SL_USD"}
_PBEMA = {"corta": "BOT_PB_CORTA", "larga": "BOT_PB_LARGA"}


def _b(x) -> str:
    return "true" if x else "false"


def _f(x, dec: int = 6) -> str:
    s = f"{float(x):.{dec}f}".rstrip("0").rstrip(".")
    return s if "." in s else s + ".0"


def _sin_ascii(s: str) -> str:
    return s.encode("ascii", "ignore").decode()


def nombre_archivo(simbolo: str, tf: str) -> str:
    base = re.sub(r"[^A-Za-z0-9_]+", "", f"Bot_{simbolo}_{tf}").rstrip("_") or "Bot"
    return base + ".mq5"


def _magic(cfg, simbolo: str) -> int:
    """Magic number estable: mismos parametros -> mismo numero (sirve para distinguir bots en la cuenta)."""
    clave = f"{simbolo}|{cfg.ema_corta}|{cfg.ema_larga}|{cfg.direccion}|{cfg.rr}|{cfg.sl_modo}|{cfg.sl_valor}"
    h = 0
    for ch in clave:
        h = (h * 31 + ord(ch)) % 90000
    return 710000 + h


NIVELES_APTOS = ("solida", "ok")      # veredictos que habilitan el bot; con cualquier otro no se genera


def motivo_rechazo(veredicto: Optional[dict], tf: str) -> Optional[str]:
    """None si se puede generar el bot; si no, el motivo (el bot solo opera si el backtest lo respalda)."""
    if tf not in _TF:
        return "Falta la temporalidad: elegí una en «Datos» o en «Remuestrear a»."
    if not veredicto:
        return "Corré el backtest con estos valores: el bot solo se genera si el veredicto lo respalda."
    if veredicto.get("nivel") not in NIVELES_APTOS:
        return "El veredicto no respalda la estrategia (" + veredicto.get("titulo", "") + "): no se genera el bot."
    return None


def generar_mq5(cfg, simbolo: str, tf: str, lotes: float, sl_usd: Optional[float] = None,
                veredicto: Optional[dict] = None, fecha: Optional[datetime] = None,
                capital: float = 0.0, limite_pct: float = 10.0) -> str:
    """cfg: engine.Config tal como lo usa el backtester (SL en dolares llega como modo 'precio');
    sl_usd: monto en dolares del SL si el usuario lo cargo asi (el EA lo convierte a precio con el tick del broker)."""
    cfg.validar()
    motivo = motivo_rechazo(veredicto, tf)
    if motivo:
        raise ValueError(motivo)
    if lotes <= 0:
        raise ValueError("Los lotes deben ser mayores que 0.")
    if cfg.sl_modo == "precio":
        if not sl_usd or sl_usd <= 0:
            raise ValueError("Con SL fijo hace falta el monto en dolares.")
        sl_modo, sl_valor, usd = "usd", 1.0, float(sl_usd)
    else:
        sl_modo, sl_valor, usd = cfg.sl_modo, float(cfg.sl_valor), 0.0
    fecha = fecha or datetime.now()

    cab = [
        "//--------------------------------------------------------------------",
        f"// Generado: {fecha:%Y-%m-%d %H:%M}   Simbolo del backtest: {_sin_ascii(simbolo)}   Temporalidad: {tf or 'no indicada'}",
        f"// EMAs {cfg.ema_corta}/{cfg.ema_larga} | direccion: {cfg.direccion} | RR {_f(cfg.rr, 2)} | lotes {_f(lotes, 2)}",
    ]
    if sl_modo == "usd":
        cab.append(f"// SL: US${_f(usd, 2)} por operacion (se convierte a precio con el valor del tick del broker)")
    elif sl_modo == "pct":
        cab.append(f"// SL: {_f(sl_valor, 3)} % del precio")
    else:
        cab.append(f"// SL: {_f(sl_valor, 3)} x ATR({cfg.atr_periodo})")
    act = [n for n, on in (("SMA", cfg.sma_activo), ("VWAP", cfg.vwap_activo), ("ADX", cfg.adx_activo),
                           ("ATR", cfg.atr_activo), ("sesion", cfg.sesion_activo), ("pullback", cfg.pb_efectivo())) if on]
    cab.append("// Filtros/opciones activos: " + (", ".join(act) if act else "ninguno"))
    cab.append(f"// Veredicto del backtester: {_sin_ascii(veredicto.get('titulo', ''))}")
    cab.append("// Parametros FIJOS: para cambiarlos hay que regenerar el bot desde la app (no se editan a mano).")
    cab += [
        "// Pasos: 1) compilar en MetaEditor (F7)  2) correr en el Strategy Tester y comparar con la app",
        "//        3) probar en demo antes de cualquier cuenta real. Es un punto de partida, no una garantia.",
        "//--------------------------------------------------------------------",
    ]

    sesiones = set(cfg.sesiones)
    valores = {
        "NOMBRE": f"Bot {_sin_ascii(simbolo)} {tf}".strip(),
        "CABECERA": "\n".join(cab),
        "MAGIC": str(_magic(cfg, simbolo)),
        "SIMBOLO": _sin_ascii(simbolo).replace('"', ""),
        "TF": _TF.get(tf, "PERIOD_CURRENT"),
        "EMA_C": str(int(cfg.ema_corta)), "EMA_L": str(int(cfg.ema_larga)),
        "DIR": _DIR[cfg.direccion], "RR": _f(cfg.rr, 4),
        "SL_MODO": _SL[sl_modo], "SL_VALOR": _f(sl_valor, 6), "SL_USD": _f(usd, 4),
        "ATR_PER": str(int(cfg.atr_periodo)), "LOTES": _f(lotes, 4),
        "PB_ON": _b(cfg.pb_efectivo()), "PB_PCT": _f(cfg.pullback_pct, 4), "PB_EMA": _PBEMA[cfg.pullback_ema],
        "PB_VELAS": str(int(cfg.pullback_velas)),
        "SMA_ON": _b(cfg.sma_activo), "SMA_PER": str(int(cfg.sma_periodo)),
        "SMA_DIST": _f(cfg.sma_dist_min_atr, 4), "SMA_PEND": str(int(cfg.sma_pendiente_n)),
        "VWAP_ON": _b(cfg.vwap_activo), "VWAP_DIST": _f(cfg.vwap_dist_min_atr, 4), "VWAP_MIN": _f(cfg.vwap_min_minutos, 2),
        "ADX_ON": _b(cfg.adx_activo), "ADX_PER": str(int(cfg.adx_periodo)), "ADX_MIN": _f(cfg.adx_min, 4),
        "ADX_MAX": _f(cfg.adx_max or 0.0, 4), "ADX_CRE": str(int(cfg.adx_creciente_n)),
        "ATR_ON": _b(cfg.atr_activo), "ATR_MIN": _f(cfg.atr_min or 0.0, 6), "ATR_MAX": _f(cfg.atr_max or 0.0, 6),
        "ATR_REL_N": str(int(cfg.atr_rel_n)), "ATR_REL_MIN": _f(cfg.atr_rel_min or 0.0, 4),
        "ATR_REL_MAX": _f(cfg.atr_rel_max or 0.0, 4),
        "SES_ON": _b(cfg.sesion_activo), "SES_TOKIO": _b("Tokio" in sesiones),
        "SES_LONDRES": _b("Londres" in sesiones), "SES_NY": _b("Nueva York" in sesiones),
        "SRV_OFFSET": _f(cfg.servidor_offset_horas if cfg.servidor_offset_horas is not None else 2.0, 2),
        "SRV_DST": _b(cfg.servidor_dst_eeuu),
        "VEREDICTO_OK": "true",
        "CAPITAL": _f(capital, 2),
        "GUARD_DIA": "4.0",
        "GUARD_TOT": _f(min(8.0, limite_pct * 0.8) if limite_pct > 0 else 8.0, 2),
    }
    txt = _PLANTILLA
    for k, v in valores.items():
        txt = txt.replace(f"@@{k}@@", v)
    pend = re.findall(r"@@[A-Z_]+@@", txt)
    if pend:
        raise RuntimeError(f"Quedaron campos sin completar en la plantilla: {sorted(set(pend))}")
    return txt


# Plantilla del EA (incluida aca para que la app no dependa de un archivo aparte).
_PLANTILLA = r'''//+------------------------------------------------------------------+
//| @@NOMBRE@@
//| Expert Advisor generado por la app de backtesting (cruce de EMAs)|
//+------------------------------------------------------------------+
#property copyright "Generado automaticamente por la app de backtesting"
#property version   "1.00"
#property description "Cruce de EMAs con filtros, SL/TP, pullback y proteccion de cuenta. Parametros fijos: para cambiarlos, regenerar desde la app."

@@CABECERA@@

enum ENUM_BOT_DIR   { BOT_AMBAS = 0, BOT_LARGOS = 1, BOT_CORTOS = 2 };
enum ENUM_BOT_SL    { BOT_SL_ATR = 0, BOT_SL_PCT = 1, BOT_SL_USD = 2 };
enum ENUM_BOT_PBEMA { BOT_PB_CORTA = 0, BOT_PB_LARGA = 1 };

// ---------------------------- identificacion --------------------------------
const bool            InpVerdictOK      = @@VEREDICTO_OK@@;  // El backtest respalda esta estrategia (si es false el bot no arranca)
const long            InpMagic          = @@MAGIC@@;      // Magic number (identifica las ordenes del bot)
const string          InpExpectedSymbol = "@@SIMBOLO@@";  // Simbolo con el que se hizo el backtest (solo aviso)
const ENUM_TIMEFRAMES InpExpectedTF     = @@TF@@;         // Temporalidad del backtest (PERIOD_CURRENT = sin aviso)
const int             InpHistBars       = 2000;           // Velas de historia para calcular los indicadores
const int             InpDeviation      = 20;             // Deslizamiento maximo permitido (puntos)

// ---------------------------- senal y gestion -------------------------------
const int             InpEmaFast        = @@EMA_C@@;      // EMA corta
const int             InpEmaSlow        = @@EMA_L@@;      // EMA larga
const ENUM_BOT_DIR    InpDir            = @@DIR@@;        // Direccion
const double          InpRR             = @@RR@@;         // Relacion TP/SL (TP = SL x RR)
const ENUM_BOT_SL     InpSLMode         = @@SL_MODO@@;    // SL en: ATR / % del precio / dolares fijos
const double          InpSLValue        = @@SL_VALOR@@;   // Valor del SL (multiplo de ATR o % del precio)
const double          InpSLUsd          = @@SL_USD@@;     // SL en dolares por operacion (con SL en dolares)
const int             InpAtrPeriod      = @@ATR_PER@@;    // Periodo del ATR
const double          InpLots           = @@LOTES@@;      // Lotes

// ---------------------------- pullback (opcional) ---------------------------
const bool            InpPB             = @@PB_ON@@;      // Entrar en pullback a la EMA
const double          InpPBPct          = @@PB_PCT@@;     // Retroceso hacia la EMA (0-100 %)
const ENUM_BOT_PBEMA  InpPBEma          = @@PB_EMA@@;     // EMA de referencia
const int             InpPBBars         = @@PB_VELAS@@;   // Caducidad de la orden (velas)

// ---------------------------- filtros ---------------------------------------
const bool            InpSmaOn          = @@SMA_ON@@;     // Filtro SMA
const int             InpSmaPeriod      = @@SMA_PER@@;    // SMA: periodo
const double          InpSmaDistAtr     = @@SMA_DIST@@;   // SMA: distancia minima al cierre (x ATR, 0 = sin)
const int             InpSmaSlopeN      = @@SMA_PEND@@;   // SMA: pendiente a favor en N velas (0 = sin)

const bool            InpVwapOn         = @@VWAP_ON@@;    // Filtro VWAP diario
const double          InpVwapDistAtr    = @@VWAP_DIST@@;  // VWAP: distancia minima (x ATR, 0 = sin)
const double          InpVwapMinMin     = @@VWAP_MIN@@;   // VWAP: minutos minimos desde el inicio del dia

const bool            InpAdxOn          = @@ADX_ON@@;     // Filtro ADX
const int             InpAdxPeriod      = @@ADX_PER@@;    // ADX: periodo
const double          InpAdxMin         = @@ADX_MIN@@;    // ADX: minimo
const double          InpAdxMax         = @@ADX_MAX@@;    // ADX: maximo (0 = sin)
const int             InpAdxRisingN     = @@ADX_CRE@@;    // ADX: creciente en N velas (0 = sin)

const bool            InpAtrOn          = @@ATR_ON@@;     // Filtro ATR
const double          InpAtrMinPct      = @@ATR_MIN@@;    // ATR minimo (% del precio, 0 = sin)
const double          InpAtrMaxPct      = @@ATR_MAX@@;    // ATR maximo (% del precio, 0 = sin)
const int             InpAtrRelN        = @@ATR_REL_N@@;  // ATR relativo: N velas (0 = sin)
const double          InpAtrRelMin      = @@ATR_REL_MIN@@; // ATR relativo: minimo (0 = sin)
const double          InpAtrRelMax      = @@ATR_REL_MAX@@; // ATR relativo: maximo (0 = sin)

const bool            InpSesOn          = @@SES_ON@@;     // Filtro de sesion
const bool            InpSesTokio       = @@SES_TOKIO@@;  // Sesion Tokio (09-18 hora local)
const bool            InpSesLondres     = @@SES_LONDRES@@; // Sesion Londres (08-17 hora local)
const bool            InpSesNY          = @@SES_NY@@;     // Sesion Nueva York (08-17 hora local)
const double          InpServerOffset   = @@SRV_OFFSET@@; // Desfase del servidor en INVIERNO respecto de GMT (GMT+2 -> 2)
const bool            InpServerDST      = @@SRV_DST@@;    // El servidor cambia de hora con EE.UU. (GMT+2/+3)

// ---------------------------- proteccion de la cuenta -----------------------
const bool            InpGuards         = true;           // Activar proteccion de cuenta
const double          InpMaxDailyLossPct = @@GUARD_DIA@@;           // Perdida diaria maxima (% del balance al inicio del dia)
const double          InpMaxTotalLossPct = @@GUARD_TOT@@;           // Perdida total maxima (% del balance inicial)
const double          InpInitialBalance = @@CAPITAL@@;            // Balance inicial de la cuenta (0 = el de la primera vez que arranca)

// ============================ estado ==========================================
const double SENT = -1.0e300;          // "sin dato" (equivale a NaN en el backtester)

datetime g_time[];
double   g_h[], g_l[], g_c[], g_tv[];
double   g_ef[], g_es[], g_atr[], g_sma[], g_adx[], g_vwap[], g_vmin[], g_atrm[];
int      g_m = 0;                      // velas CERRADAS disponibles (la ultima es la senal)
datetime g_lastBar = 0;

bool     g_pbActive = false;           // hay una orden de pullback en espera
int      g_pbSide   = 0;
int      g_pbBars   = 0;
double   g_pbExt    = 0.0;

bool     g_stopTotal = false;
int      g_blockDay  = 0;
int      g_dayKey    = 0;
double   g_initBal   = 0.0;
double   g_dayBal    = 0.0;
string   g_gv        = "";

bool V(const double x) { return x > -1.0e299; }

// ============================ indicadores =====================================
// Mismas formulas que el backtester (suavizados recursivos con semilla en el primer valor).
void CalcEMA(const double &x[], const int m, const int span, double &out[])
{
   ArrayResize(out, m);
   const double a = 2.0 / (span + 1.0);
   out[0] = x[0];
   for(int t = 1; t < m; t++)
      out[t] = a * x[t] + (1.0 - a) * out[t - 1];
}

void CalcSMA(const double &x[], const int m, const int p, double &out[])
{
   ArrayResize(out, m);
   double suma = 0.0;
   for(int t = 0; t < m; t++)
   {
      suma += x[t];
      if(t >= p) suma -= x[t - p];
      out[t] = (t >= p - 1) ? suma / p : SENT;
   }
}

void CalcTR(double &tr[])
{
   ArrayResize(tr, g_m);
   for(int t = 0; t < g_m; t++)
   {
      const double prev = (t == 0) ? g_c[0] : g_c[t - 1];
      tr[t] = MathMax(g_h[t] - g_l[t], MathMax(MathAbs(g_h[t] - prev), MathAbs(g_l[t] - prev)));
   }
}

void CalcWilder(const double &x[], const int m, const int p, double &out[])
{
   ArrayResize(out, m);
   const double a = 1.0 / p;
   out[0] = x[0];
   for(int t = 1; t < m; t++)
      out[t] = a * x[t] + (1.0 - a) * out[t - 1];
}

void CalcADX(const int p, double &adx[])
{
   double tr[], mas[], menos[], trS[], masS[], menosS[], dx[];
   CalcTR(tr);
   ArrayResize(mas, g_m);
   ArrayResize(menos, g_m);
   mas[0] = 0.0;
   menos[0] = 0.0;
   for(int t = 1; t < g_m; t++)
   {
      const double arriba = g_h[t] - g_h[t - 1];
      const double abajo  = g_l[t - 1] - g_l[t];
      mas[t]   = (arriba > abajo && arriba > 0.0) ? arriba : 0.0;
      menos[t] = (abajo > arriba && abajo > 0.0) ? abajo : 0.0;
   }
   CalcWilder(tr, g_m, p, trS);
   CalcWilder(mas, g_m, p, masS);
   CalcWilder(menos, g_m, p, menosS);
   ArrayResize(dx, g_m);
   for(int t = 0; t < g_m; t++)
   {
      const double pdi = (trS[t] > 0.0) ? 100.0 * masS[t] / trS[t] : 0.0;
      const double ndi = (trS[t] > 0.0) ? 100.0 * menosS[t] / trS[t] : 0.0;
      const double s = pdi + ndi;
      dx[t] = (s > 0.0) ? 100.0 * MathAbs(pdi - ndi) / s : 0.0;
   }
   CalcWilder(dx, g_m, p, adx);
}

void CalcRollingMean(const double &x[], const int m, const int n, double &out[])
{
   ArrayResize(out, m);
   double suma = 0.0;
   for(int t = 0; t < m; t++)
   {
      suma += x[t];
      if(t >= n) suma -= x[t - n];
      out[t] = (t >= n - 1) ? suma / n : SENT;
   }
}

int DayKeyOf(const datetime t)
{
   MqlDateTime s;
   TimeToStruct(t, s);
   return s.year * 10000 + s.mon * 100 + s.day;
}

// VWAP del dia (se reinicia a las 00:00 del servidor): precio tipico ponderado por volumen de ticks.
void CalcVWAP(const int paso_seg)
{
   ArrayResize(g_vwap, g_m);
   ArrayResize(g_vmin, g_m);
   double cpv = 0.0, cv = 0.0;
   int diaPrev = -1;
   for(int t = 0; t < g_m; t++)
   {
      MqlDateTime s;
      TimeToStruct(g_time[t], s);
      const int key = s.year * 10000 + s.mon * 100 + s.day;
      if(key != diaPrev) { cpv = 0.0; cv = 0.0; diaPrev = key; }
      const double tp = (g_h[t] + g_l[t] + g_c[t]) / 3.0;
      const double w = (g_tv[t] > 0.0) ? g_tv[t] : 1.0;
      cpv += tp * w;
      cv  += w;
      g_vwap[t] = cpv / cv;
      g_vmin[t] = s.hour * 60.0 + s.min + s.sec / 60.0 + paso_seg / 60.0;   // minutos hasta el CIERRE de la vela
   }
}

// ============================ sesiones ========================================
datetime NthSunday(const int year, const int mon, const int n)
{
   MqlDateTime s;
   s.year = year; s.mon = mon; s.day = 1; s.hour = 0; s.min = 0; s.sec = 0;
   const datetime d1 = StructToTime(s);
   MqlDateTime w;
   TimeToStruct(d1, w);
   const datetime primero = d1 + (datetime)(((7 - w.day_of_week) % 7) * 86400);
   return primero + (datetime)((n - 1) * 7 * 86400);
}

datetime LastSunday(const int year, const int mon)
{
   MqlDateTime s;
   s.year = (mon == 12) ? year + 1 : year;
   s.mon  = (mon == 12) ? 1 : mon + 1;
   s.day = 1; s.hour = 0; s.min = 0; s.sec = 0;
   const datetime ultimo = StructToTime(s) - 86400;
   MqlDateTime w;
   TimeToStruct(ultimo, w);
   return ultimo - (datetime)(w.day_of_week * 86400);
}

// 1 si el dia (hora del servidor) cae en el horario de verano de EE.UU. (2.o domingo de marzo al 1.o de noviembre)
int UsDstServidor(const datetime t)
{
   MqlDateTime s;
   TimeToStruct(t, s);
   const datetime dia = t - (datetime)(s.hour * 3600 + s.min * 60 + s.sec);
   return (dia >= NthSunday(s.year, 3, 2) && dia < NthSunday(s.year, 11, 1)) ? 1 : 0;
}

datetime ServidorAUtc(const datetime t)
{
   const double off = InpServerOffset + ((InpServerDST && UsDstServidor(t) == 1) ? 1.0 : 0.0);
   return t - (datetime)(off * 3600.0);
}

double HoraLocal(const datetime utc, const double offset_h)
{
   const datetime loc = utc + (datetime)(offset_h * 3600.0);
   MqlDateTime s;
   TimeToStruct(loc, s);
   return s.hour + s.min / 60.0;
}

bool InSession(const datetime t_servidor)
{
   const datetime utc = ServidorAUtc(t_servidor);
   MqlDateTime u;
   TimeToStruct(utc, u);
   if(InpSesTokio)
   {
      const double h = HoraLocal(utc, 9.0);
      if(h >= 9.0 && h < 18.0) return true;
   }
   if(InpSesLondres)
   {
      const bool bst = (utc >= LastSunday(u.year, 3) + 3600 && utc < LastSunday(u.year, 10) + 3600);
      const double h = HoraLocal(utc, bst ? 1.0 : 0.0);
      if(h >= 8.0 && h < 17.0) return true;
   }
   if(InpSesNY)
   {
      const bool edt = (utc >= NthSunday(u.year, 3, 2) + 7 * 3600 && utc < NthSunday(u.year, 11, 1) + 6 * 3600);
      const double h = HoraLocal(utc, edt ? -4.0 : -5.0);
      if(h >= 8.0 && h < 17.0) return true;
   }
   return false;
}

// ============================ datos y senal ===================================
int MaxWarm()
{
   int w = InpEmaSlow + 1;
   if(InpSmaOn) w = MathMax(w, InpSmaPeriod + MathMax(InpSmaSlopeN, 0));
   if(InpAdxOn) w = MathMax(w, 2 * InpAdxPeriod + MathMax(InpAdxRisingN, 0) + 1);
   if(InpAtrOn && InpAtrRelN > 0) w = MathMax(w, InpAtrRelN + InpAtrPeriod);
   return w;
}

bool LoadData()
{
   MqlRates r[];
   ArraySetAsSeries(r, false);
   const int n = CopyRates(_Symbol, _Period, 0, InpHistBars, r);
   if(n < MaxWarm() + 50)
   {
      Print("Pocas velas disponibles (", n, "). Abri el grafico y deja que MT5 descargue la historia.");
      return false;
   }
   g_m = n - 1;                        // la ultima vela esta en formacion: no se usa
   ArrayResize(g_time, g_m);
   ArrayResize(g_h, g_m);
   ArrayResize(g_l, g_m);
   ArrayResize(g_c, g_m);
   ArrayResize(g_tv, g_m);
   for(int t = 0; t < g_m; t++)
   {
      g_time[t] = r[t].time;
      g_h[t] = r[t].high;
      g_l[t] = r[t].low;
      g_c[t] = r[t].close;
      g_tv[t] = (double)r[t].tick_volume;
   }
   CalcEMA(g_c, g_m, InpEmaFast, g_ef);
   CalcEMA(g_c, g_m, InpEmaSlow, g_es);
   double tr[];
   CalcTR(tr);
   CalcWilder(tr, g_m, InpAtrPeriod, g_atr);
   if(InpSmaOn) CalcSMA(g_c, g_m, InpSmaPeriod, g_sma);
   if(InpAdxOn) CalcADX(InpAdxPeriod, g_adx);
   if(InpVwapOn) CalcVWAP(PeriodSeconds());
   if(InpAtrOn && InpAtrRelN > 0) CalcRollingMean(g_atr, g_m, InpAtrRelN, g_atrm);
   return true;
}

// +1 cruce alcista, -1 bajista, 0 nada (en la vela i, sin mirar filtros ni direccion)
int CrossAt(const int i)
{
   if(i < MaxWarm() || i < 1) return 0;
   const double d  = g_ef[i] - g_es[i];
   const double dp = g_ef[i - 1] - g_es[i - 1];
   if(d > 0.0 && dp <= 0.0) return 1;
   if(d < 0.0 && dp >= 0.0) return -1;
   return 0;
}

bool Between(const double v, const double lo, const double hi, const bool useLo, const bool useHi)
{
   if(!V(v)) return false;
   if(useLo && v < lo) return false;
   if(useHi && v > hi) return false;
   return true;
}

bool OkSma(const int i, const int side)
{
   const double s = g_sma[i];
   if(!V(s) || (g_c[i] - s) * side <= 0.0) return false;
   if(InpSmaDistAtr > 0.0 && MathAbs(g_c[i] - s) < InpSmaDistAtr * g_atr[i]) return false;
   if(InpSmaSlopeN > 0)
   {
      if(i - InpSmaSlopeN < 0) return false;
      const double s0 = g_sma[i - InpSmaSlopeN];
      if(!V(s0)) return false;
      return (s - s0) * side > 0.0;
   }
   return true;
}

bool OkVwap(const int i, const int side)
{
   if(g_vmin[i] < InpVwapMinMin || (g_c[i] - g_vwap[i]) * side <= 0.0) return false;
   return !(InpVwapDistAtr > 0.0 && MathAbs(g_c[i] - g_vwap[i]) < InpVwapDistAtr * g_atr[i]);
}

bool OkAdx(const int i)
{
   if(!Between(g_adx[i], InpAdxMin, InpAdxMax, true, InpAdxMax > 0.0)) return false;
   if(InpAdxRisingN <= 0) return true;
   if(i - InpAdxRisingN < 0) return false;
   return g_adx[i] > g_adx[i - InpAdxRisingN];
}

bool OkAtr(const int i)
{
   const double v = g_atr[i] / g_c[i] * 100.0;
   if(!Between(v, InpAtrMinPct, InpAtrMaxPct, InpAtrMinPct > 0.0, InpAtrMaxPct > 0.0)) return false;
   if(InpAtrRelN > 0)
   {
      const double med = g_atrm[i];
      if(!V(med) || med <= 0.0) return false;
      return Between(g_atr[i] / med, InpAtrRelMin, InpAtrRelMax, InpAtrRelMin > 0.0, InpAtrRelMax > 0.0);
   }
   return true;
}

// orden de los filtros = el del backtester: sesion, SMA, VWAP, ADX, ATR
bool PassFilters(const int i, const int side, const bool withSession)
{
   if(InpSesOn && withSession && !InSession(g_time[i])) return false;
   if(InpSmaOn && !OkSma(i, side)) return false;
   if(InpVwapOn && !OkVwap(i, side)) return false;
   if(InpAdxOn && !OkAdx(i)) return false;
   if(InpAtrOn && !OkAtr(i)) return false;
   return true;
}

bool DirectionAllows(const int side)
{
   if(InpDir == BOT_AMBAS) return true;
   if(InpDir == BOT_LARGOS) return side == 1;
   return side == -1;
}

// ============================ ordenes =========================================
// el lote del backtest debe ser exactamente operable en este broker: si no lo es, el bot no arranca
bool VolumenValido()
{
   const double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   const double vmin = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   const double vmax = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   if(InpLots < vmin - 1.0e-9 || InpLots > vmax + 1.0e-9) return false;
   if(step > 0.0)
   {
      const double k = InpLots / step;
      if(MathAbs(k - MathRound(k)) > 1.0e-6) return false;
   }
   return true;
}

double Px(const double price)
{
   return NormalizeDouble(price, (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS));
}

// distancia de precio del SL (misma regla que el backtester, medida en la vela de la senal)
double SlDistance(const int i)
{
   if(InpSLMode == BOT_SL_ATR) return g_atr[i] * InpSLValue;
   if(InpSLMode == BOT_SL_PCT) return g_c[i] * InpSLValue / 100.0;
   const double tickSize  = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   const double tickValue = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   if(tickSize <= 0.0 || tickValue <= 0.0 || InpLots <= 0.0) return 0.0;
   return InpSLUsd / ((tickValue / tickSize) * InpLots);       // US$ -> distancia de precio con este lote
}

ENUM_ORDER_TYPE_FILLING FillingMarket()
{
   const long fm = SymbolInfoInteger(_Symbol, SYMBOL_FILLING_MODE);
   if((fm & SYMBOL_FILLING_FOK) != 0) return ORDER_FILLING_FOK;
   if((fm & SYMBOL_FILLING_IOC) != 0) return ORDER_FILLING_IOC;
   return ORDER_FILLING_RETURN;
}

bool HasPosition()
{
   for(int k = PositionsTotal() - 1; k >= 0; k--)
      if(PositionGetSymbol(k) == _Symbol && PositionGetInteger(POSITION_MAGIC) == InpMagic) return true;
   return false;
}

void DeletePending()
{
   for(int k = OrdersTotal() - 1; k >= 0; k--)
   {
      const ulong ticket = OrderGetTicket(k);
      if(ticket == 0) continue;
      if(OrderGetString(ORDER_SYMBOL) != _Symbol || OrderGetInteger(ORDER_MAGIC) != InpMagic) continue;
      MqlTradeRequest rq;
      MqlTradeResult  rs;
      ZeroMemory(rq);
      ZeroMemory(rs);
      rq.action = TRADE_ACTION_REMOVE;
      rq.order  = ticket;
      if(!OrderSend(rq, rs)) Print("No se pudo borrar la orden ", ticket, ": ", rs.retcode);
   }
}

void CloseAll()
{
   DeletePending();
   for(int k = PositionsTotal() - 1; k >= 0; k--)
   {
      if(PositionGetSymbol(k) != _Symbol || PositionGetInteger(POSITION_MAGIC) != InpMagic) continue;
      const ulong ticket = PositionGetInteger(POSITION_TICKET);
      const long tipo = PositionGetInteger(POSITION_TYPE);
      MqlTradeRequest rq;
      MqlTradeResult  rs;
      ZeroMemory(rq);
      ZeroMemory(rs);
      rq.action    = TRADE_ACTION_DEAL;
      rq.position  = ticket;
      rq.symbol    = _Symbol;
      rq.volume    = PositionGetDouble(POSITION_VOLUME);
      rq.type      = (tipo == POSITION_TYPE_BUY) ? ORDER_TYPE_SELL : ORDER_TYPE_BUY;
      rq.price     = (tipo == POSITION_TYPE_BUY) ? SymbolInfoDouble(_Symbol, SYMBOL_BID) : SymbolInfoDouble(_Symbol, SYMBOL_ASK);
      rq.deviation = InpDeviation;
      rq.magic     = InpMagic;
      rq.type_filling = FillingMarket();
      if(!OrderSend(rq, rs)) Print("No se pudo cerrar la posicion ", ticket, ": ", rs.retcode);
   }
}

// entrada a mercado: largo al ask, corto al bid; SL/TP desde ese precio (igual que el backtester)
bool MarketEntry(const int side, const double d)
{
   if(d <= 0.0) return false;
   const double price = (side == 1) ? SymbolInfoDouble(_Symbol, SYMBOL_ASK) : SymbolInfoDouble(_Symbol, SYMBOL_BID);
   MqlTradeRequest rq;
   MqlTradeResult  rs;
   ZeroMemory(rq);
   ZeroMemory(rs);
   rq.action    = TRADE_ACTION_DEAL;
   rq.symbol    = _Symbol;
   rq.volume    = InpLots;
   rq.type      = (side == 1) ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
   rq.price     = Px(price);
   rq.sl        = Px(price - side * d);
   rq.tp        = Px(price + side * d * InpRR);
   rq.deviation = InpDeviation;
   rq.magic     = InpMagic;
   rq.comment   = "EMA bot";
   rq.type_filling = FillingMarket();
   const bool ok = OrderSend(rq, rs);
   if(!ok || (rs.retcode != TRADE_RETCODE_DONE && rs.retcode != TRADE_RETCODE_PLACED))
   {
      Print("Entrada rechazada (", rs.retcode, ")");
      return false;
   }
   return true;
}

// orden limite de pullback para la vela que esta por abrir
void PlacePullback(const int i)
{
   DeletePending();
   if(InpSesOn && !InSession(iTime(_Symbol, _Period, 0))) return;       // fuera de sesion no se deja orden (sigue contando la caducidad)
   const double d = SlDistance(i);
   if(d <= 0.0) return;
   const double ema  = (InpPBEma == BOT_PB_CORTA) ? g_ef[i] : g_es[i];
   const double frac = InpPBPct / 100.0;
   const double bid  = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   const double ask  = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double nivel, price;
   if(g_pbSide == 1)
   {
      nivel = g_pbExt - frac * MathMax(g_pbExt - ema, 0.0);
      price = nivel + (ask - bid);                 // el nivel esta medido en BID; el largo paga el ask
      if(price >= ask)                              // el precio ya esta en el nivel: se entra a mercado
      {
         if(MarketEntry(1, d)) g_pbActive = false;
         return;
      }
   }
   else
   {
      nivel = g_pbExt + frac * MathMax(ema - g_pbExt, 0.0);
      price = nivel;
      if(price <= bid)
      {
         if(MarketEntry(-1, d)) g_pbActive = false;
         return;
      }
   }
   MqlTradeRequest rq;
   MqlTradeResult  rs;
   ZeroMemory(rq);
   ZeroMemory(rs);
   rq.action = TRADE_ACTION_PENDING;
   rq.symbol = _Symbol;
   rq.volume = InpLots;
   rq.type   = (g_pbSide == 1) ? ORDER_TYPE_BUY_LIMIT : ORDER_TYPE_SELL_LIMIT;
   rq.price  = Px(price);
   rq.sl     = Px(price - g_pbSide * d);
   rq.tp     = Px(price + g_pbSide * d * InpRR);
   rq.magic  = InpMagic;
   rq.comment = "EMA bot pullback";
   rq.type_filling = ORDER_FILLING_RETURN;
   rq.type_time = ORDER_TIME_GTC;
   if(!OrderSend(rq, rs) || (rs.retcode != TRADE_RETCODE_DONE && rs.retcode != TRADE_RETCODE_PLACED))
      Print("Orden de pullback rechazada (", rs.retcode, ")");
}

// ============================ proteccion de la cuenta =========================
bool GuardsOK()
{
   if(!InpGuards) return true;
   if(g_stopTotal) return false;
   const double eq = AccountInfoDouble(ACCOUNT_EQUITY);
   if(eq <= g_initBal * (1.0 - InpMaxTotalLossPct / 100.0))
   {
      Print("PROTECCION: perdida total maxima alcanzada. Se cierra todo y el bot queda detenido. ",
            "Para reanudarlo, borra la variable global ", g_gv, "STOP (F3 en MT5) y reinicia el bot.");
      CloseAll();
      g_stopTotal = true;
      GlobalVariableSet(g_gv + "STOP", 1.0);
      return false;
   }
   const int key = DayKeyOf(TimeCurrent());
   if(key != g_dayKey)
   {
      g_dayKey = key;
      g_dayBal = AccountInfoDouble(ACCOUNT_BALANCE);
      g_blockDay = 0;
      GlobalVariableSet(g_gv + "DAYKEY", (double)key);
      GlobalVariableSet(g_gv + "DAYBAL", g_dayBal);
   }
   if(g_blockDay == key) return false;
   if(eq <= g_dayBal * (1.0 - InpMaxDailyLossPct / 100.0))
   {
      Print("PROTECCION: perdida diaria maxima alcanzada. Se cierra todo hasta el proximo dia.");
      CloseAll();
      g_pbActive = false;
      g_blockDay = key;
      return false;
   }
   return true;
}

// ============================ logica por vela =================================
void OnNewBar()
{
   if(!LoadData()) return;
   const int i = g_m - 1;                      // ultima vela cerrada = vela de la senal

   if(HasPosition())                           // una operacion a la vez: SL y TP ya estan puestos
   {
      g_pbActive = false;
      DeletePending();
      return;
   }

   const int cr = CrossAt(i);

   if(g_pbActive)                              // orden de pullback en espera
   {
      g_pbBars++;
      const bool contrario = (cr == -g_pbSide);
      if(contrario)
      {
         g_pbActive = false;                   // cruce contrario: se descarta y puede ser una senal nueva
         DeletePending();
      }
      else if(g_pbBars >= InpPBBars)
      {
         g_pbActive = false;                   // caduco
         DeletePending();
         return;
      }
      else
      {
         g_pbExt = (g_pbSide == 1) ? MathMax(g_pbExt, g_h[i]) : MathMin(g_pbExt, g_l[i]);
         PlacePullback(i);
         return;
      }
   }

   if(cr == 0 || !DirectionAllows(cr)) return;
   const bool conPullback = (InpPB && InpPBPct > 0.0);
   if(!PassFilters(i, cr, !conPullback)) return;   // con pullback la sesion se mira al ejecutar

   if(!conPullback)
   {
      MarketEntry(cr, SlDistance(i));
      return;
   }
   g_pbActive = true;
   g_pbSide = cr;
   g_pbBars = 0;
   g_pbExt = (cr == 1) ? g_h[i] : g_l[i];
   PlacePullback(i);
}

// ============================ eventos =========================================
int OnInit()
{
   if(!InpVerdictOK) { Print("RECHAZADO: el backtest no respalda esta estrategia. El bot no opera."); return INIT_FAILED; }
   if(InpEmaFast >= InpEmaSlow) { Print("RECHAZADO: la EMA corta debe ser menor que la larga."); return INIT_PARAMETERS_INCORRECT; }
   if(InpPBPct < 0.0 || InpPBPct > 100.0) { Print("RECHAZADO: el pullback debe estar entre 0 y 100."); return INIT_PARAMETERS_INCORRECT; }
   if(InpExpectedSymbol != _Symbol)
   {
      Print("RECHAZADO: el bot es para ", InpExpectedSymbol, " y este grafico es ", _Symbol, ".");
      return INIT_FAILED;
   }
   if(InpExpectedTF != _Period)
   {
      Print("RECHAZADO: el bot es para otra temporalidad. Ponelo en un grafico ", EnumToString(InpExpectedTF), ".");
      return INIT_FAILED;
   }
   if(!VolumenValido())
   {
      Print("RECHAZADO: el lote ", InpLots, " no es operable en este simbolo (minimo/maximo/paso).");
      return INIT_FAILED;
   }
   if(InpSLMode == BOT_SL_USD && (SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE) <= 0.0 || SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE) <= 0.0))
   {
      Print("RECHAZADO: no se puede convertir el SL en dolares (sin tick size/value).");
      return INIT_FAILED;
   }
   if(InpSesOn)
   {
      const datetime srv = TimeTradeServer();
      const double medido = MathRound((double)(srv - TimeGMT()) / 3600.0);
      const double esperado = InpServerOffset + ((InpServerDST && UsDstServidor(srv) == 1) ? 1.0 : 0.0);
      if(MathAbs(medido - esperado) > 0.01)
      {
         Print("RECHAZADO: el desfase del servidor medido (", medido, " h) no coincide con el del backtest (", esperado, " h). ",
               "Las sesiones quedarian corridas. Revisa el desfase en la app y regenera el bot.");
         return INIT_FAILED;
      }
   }

   g_gv = "BOT" + IntegerToString((int)InpMagic) + "_";
   g_stopTotal = (GlobalVariableCheck(g_gv + "STOP") && GlobalVariableGet(g_gv + "STOP") > 0.5);
   if(InpInitialBalance > 0.0) g_initBal = InpInitialBalance;
   else if(GlobalVariableCheck(g_gv + "INIT")) g_initBal = GlobalVariableGet(g_gv + "INIT");
   else { g_initBal = AccountInfoDouble(ACCOUNT_BALANCE); GlobalVariableSet(g_gv + "INIT", g_initBal); }
   g_dayKey = DayKeyOf(TimeCurrent());
   if(GlobalVariableCheck(g_gv + "DAYKEY") && (int)GlobalVariableGet(g_gv + "DAYKEY") == g_dayKey)
      g_dayBal = GlobalVariableGet(g_gv + "DAYBAL");
   else
   {
      g_dayBal = AccountInfoDouble(ACCOUNT_BALANCE);
      GlobalVariableSet(g_gv + "DAYKEY", (double)g_dayKey);
      GlobalVariableSet(g_gv + "DAYBAL", g_dayBal);
   }
   Print("Bot iniciado. Balance inicial para la proteccion: ", g_initBal);
   return INIT_SUCCEEDED;
}

void OnTick()
{
   if(!GuardsOK()) return;
   const datetime t0 = iTime(_Symbol, _Period, 0);
   if(g_lastBar == 0) { g_lastBar = t0; return; }   // primera vez: se espera una vela nueva
   if(t0 == g_lastBar) return;
   g_lastBar = t0;
   OnNewBar();
}
'''
