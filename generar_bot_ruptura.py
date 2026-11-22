"""Bot de MT5 de la estrategia «Ruptura del rango de apertura» (Nueva York, Londres o Tokio).

No duplica el bot de EMA: parte del bot que genera generar_bot.generar_mq5 (protecciones de cuenta, riesgo por operacion, pausas, breakeven, parcial,
cierre por tiempo, fin de semana, noticias, filtros, magic, avisos al celular, variables globales) con una configuracion base sin senal propia, y le
cambia SOLO lo de la ruptura con reemplazos anclados: cada ancla tiene que existir exactamente una vez (si la plantilla cambia, falla fuerte en
lugar de generar un bot distinto del esperado). generar_bot.py no se toca: los bots de EMA/SMA salen identicos.

Lo que agrega al bot (todo en la hora local de la bolsa elegida, con InpServerOffset / InpServerDST):
  - rango de apertura armado con las velas del grafico (CopyRates de LoadData), validez del dia (falta una vela => no opera) y filtro de tamaño;
  - señal: una vela cerrada FUERA del rango; entrada a mercado apenas abre la vela siguiente (en el backtest es al cierre de la vela de la señal);
  - SL (mitad / lado opuesto / ATR) y TP por RR sobre la distancia real al SL; entradas por dia (1 o 2: la segunda solo contraria y solo si la primera
    cerro por su SL original); ultima entrada y cierre forzado («CIERRE POR HORA»);
  - estado del dia en variables globales con el prefijo del magic (rango, entradas, lado, resultado de la primera): un reinicio no duplica entradas;
  - todos los mensajes que el bot escribe en el registro de MT5 llegan tambien al celular (una vez por dia por mensaje repetido).
"""
import dataclasses
import re
from datetime import datetime
from typing import Optional

import generar_bot as gb
import ruptura as rup_mod

_PER_MIN = {"M1": 1, "M2": 2, "M3": 3, "M4": 4, "M5": 5, "M6": 6, "M10": 10, "M12": 12, "M15": 15, "M20": 20, "M30": 30, "H1": 60, "H2": 120,
            "H3": 180, "H4": 240, "H6": 360, "H8": 480, "H12": 720, "D1": 1440}


def _hhmm(m: int) -> str:
    return f"{int(m) // 60:02d}:{int(m) % 60:02d}"


def _magic_ruptura(cfg, simbolo: str) -> int:
    rp = cfg.ruptura
    clave = (f"RUP|{simbolo}|{'' if rp.bolsa == 'ny' else rp.bolsa + '|'}{rp.apertura_min}|{rp.rango_min}|{rp.sl_modo}|{rp.sl_atr_x}|{rp.entradas_dia}|{rp.ultima_min}|{rp.cierre_min}"
             f"|{rp.tam_activo}|{rp.tam_min}|{rp.tam_max}|{rp.tam_n}|{cfg.direccion}|{cfg.rr}")
    h = 0
    for ch in clave:
        h = (h * 31 + ord(ch)) % 90000
    return 800000 + h                       # rango propio: no choca con los magic de los bots de EMA/SMA (710000 a 799999)


# ----------------------------------------------------------------------------------------------------------------------------
# MQL5 que se agrega (inputs, estado, funciones). Mensajes en ASCII, como el resto del bot.
# ----------------------------------------------------------------------------------------------------------------------------
_INPUTS = r'''
// ---------------------------- ruptura del rango de apertura de Nueva York ---------------------------------
const bool            InpRupOn          = true;           // Estrategia de ruptura del rango de apertura (siempre activa en este bot)
const int             InpRupZona        = @@RUP_ZONA@@;   // Bolsa: 0 = EE.UU., 1 = Londres, 2 = Tokio (el rango y los horarios de abajo son hora local de esa bolsa)
const int             InpRupApertura    = @@RUP_AP@@;     // Inicio del rango, minutos desde las 00:00 (hora de Nueva York)
const int             InpRupRango       = @@RUP_DUR@@;    // Duracion del rango (minutos): el maximo y el minimo de las velas que abren dentro de esa ventana
const int             InpRupSL          = @@RUP_SL@@;     // SL: 0 = mitad del rango, 1 = lado opuesto del rango, 2 = multiplo de ATR
const double          InpRupSLAtr       = @@RUP_SL_ATR@@; // Con SL por ATR: multiplo del ATR
const int             InpRupEntradas    = @@RUP_ENT@@;    // Entradas por dia (1 o 2: la segunda solo hacia el lado contrario y solo si la primera cerro por su SL)
const int             InpRupUltima      = @@RUP_ULT@@;    // Ultima entrada: el CIERRE de la vela de la senal tiene que ser a esta hora o antes (hora de Nueva York)
const int             InpRupCierre      = @@RUP_CIE@@;    // Cierre forzado a mercado (hora de Nueva York)
const bool            InpRupTamOn       = @@RUP_TAM_ON@@; // Filtro de tamano: operar solo si el rango mide entre MIN y MAX veces el promedio de los ultimos N dias validos
const double          InpRupTamMin      = @@RUP_TAM_MIN@@;
const double          InpRupTamMax      = @@RUP_TAM_MAX@@;
const int             InpRupTamN        = @@RUP_TAM_N@@;
'''

_GLOBALES = r'''
// ============================ ruptura: estado del dia =========================
int      g_rupDia   = 0;               // fecha de Nueva York (aaaammdd) a la que pertenece el estado de abajo
int      g_rupEst   = 0;               // 0 = sin evaluar, 1 = rango valido, 2 = falta una vela del rango, 3 = sin historial para el filtro de tamano, 4 = tamano fuera de rango
double   g_rupHi    = 0.0;             // maximo y minimo del rango de apertura del dia
double   g_rupLo    = 0.0;
int      g_rupN     = 0;               // entradas hechas hoy
int      g_rupLado  = 0;               // lado de la primera entrada del dia (+1 compra, -1 venta)
int      g_rupSL    = 0;               // 1 = la primera operacion cerro por su SL original (no breakeven, hora, tiempo ni parcial)
bool     g_rupHora  = false;           // el cierre en curso es el cierre forzado por hora (para el aviso)
int      g_rupFH    = 0;               // dia en que ya se aviso una ruptura fuera del horario de entrada
int      g_avDia    = 0;               // avisos repetidos: solo el primero del dia llega al celular
string   g_avTxt[];
'''

_AVISAR_DIA = r'''
int DayKeyNow();                       // se define mas abajo (corte del dia de la cuenta)

// Igual que Avisar, pero un mensaje identico se manda al celular una sola vez por dia (los repetidos solo quedan en el registro).
bool AvisarDia(const string msg)
{
   const int k = DayKeyNow();
   if(k != g_avDia) { g_avDia = k; ArrayResize(g_avTxt, 0); }
   for(int j = 0; j < ArraySize(g_avTxt); j++)
      if(g_avTxt[j] == msg) { Print("Bot " + _Symbol + ": " + msg); return true; }
   const int n = ArraySize(g_avTxt);
   ArrayResize(g_avTxt, n + 1);
   g_avTxt[n] = msg;
   return Avisar(msg);
}
'''

_FUNCIONES = r'''
// ============================ ruptura del rango de apertura de Nueva York =====
// Fecha (aaaammdd), minuto del dia (0 a 1439) y dia de la semana (0 = domingo) en la bolsa elegida (InpRupZona) de un instante del servidor,
// con el horario de verano de esa plaza: EE.UU., Londres (ultimo domingo de marzo a ultimo de octubre, 01:00 UTC), Tokio (UTC+9, sin cambio).
int NyFecha(const datetime ts, int &minutos, int &dow)
{
   const datetime utc = ServidorAUtc(ts);
   MqlDateTime u;
   TimeToStruct(utc, u);
   double horas = 9.0;                                                    // Tokio
   if(InpRupZona == 0)
   {
      const bool edt = (utc >= NthSunday(u.year, 3, 2) + 7 * 3600 && utc < NthSunday(u.year, 11, 1) + 6 * 3600);
      horas = edt ? -4.0 : -5.0;
   }
   else if(InpRupZona == 1)
   {
      const bool bst = (utc >= LastSunday(u.year, 3) + 3600 && utc < LastSunday(u.year, 10) + 3600);
      horas = bst ? 1.0 : 0.0;
   }
   const datetime loc = utc + (datetime)(horas * 3600.0);
   MqlDateTime s;
   TimeToStruct(loc, s);
   minutos = s.hour * 60 + s.min;
   dow = s.day_of_week;
   return s.year * 10000 + s.mon * 100 + s.day;
}

string RupHM(const int m)
{
   return StringSubstr(IntegerToString(100 + m / 60), 1, 2) + ":" + StringSubstr(IntegerToString(100 + m % 60), 1, 2);
}

void RupGuardar()
{
   GlobalVariableSet(g_gv + "RUPDIA", (double)g_rupDia);
   GlobalVariableSet(g_gv + "RUPEST", (double)g_rupEst);
   GlobalVariableSet(g_gv + "RUPHI", g_rupHi);
   GlobalVariableSet(g_gv + "RUPLO", g_rupLo);
   GlobalVariableSet(g_gv + "RUPN", (double)g_rupN);
   GlobalVariableSet(g_gv + "RUPLADO", (double)g_rupLado);
   GlobalVariableSet(g_gv + "RUPSL", (double)g_rupSL);
}

// al arrancar: recupera el estado del dia (rango, entradas, lado y resultado de la primera) para que un reinicio no duplique entradas
void RupCargar()
{
   if(!GlobalVariableCheck(g_gv + "RUPDIA")) return;
   g_rupDia   = (int)GlobalVariableGet(g_gv + "RUPDIA");
   g_rupEst   = GlobalVariableCheck(g_gv + "RUPEST")  ? (int)GlobalVariableGet(g_gv + "RUPEST")  : 0;
   g_rupHi    = GlobalVariableCheck(g_gv + "RUPHI")   ? GlobalVariableGet(g_gv + "RUPHI")        : 0.0;
   g_rupLo    = GlobalVariableCheck(g_gv + "RUPLO")   ? GlobalVariableGet(g_gv + "RUPLO")        : 0.0;
   g_rupN     = GlobalVariableCheck(g_gv + "RUPN")    ? (int)GlobalVariableGet(g_gv + "RUPN")    : 0;
   g_rupLado  = GlobalVariableCheck(g_gv + "RUPLADO") ? (int)GlobalVariableGet(g_gv + "RUPLADO") : 0;
   g_rupSL    = GlobalVariableCheck(g_gv + "RUPSL")   ? (int)GlobalVariableGet(g_gv + "RUPSL")   : 0;
}

// maximo, minimo y cantidad de velas del rango entre las velas a..b (todas del mismo dia de Nueva York)
void RupRangoDe(const int a, const int b, int &cnt, double &hi, double &lo)
{
   cnt = 0;
   hi = -1.0e300;
   lo = 1.0e300;
   for(int k = a; k <= b; k++)
   {
      int mm, dw;
      NyFecha(g_time[k], mm, dw);
      if(mm >= InpRupApertura && mm < InpRupApertura + InpRupRango)
      {
         cnt++;
         if(g_h[k] > hi) hi = g_h[k];
         if(g_l[k] < lo) lo = g_l[k];
      }
   }
}

// primera vela del dia de Nueva York al que pertenece la vela b
int RupInicioDia(const int b)
{
   int mm, dw;
   const int key = NyFecha(g_time[b], mm, dw);
   int a = b;
   while(a > 0)
   {
      int m2, d2;
      if(NyFecha(g_time[a - 1], m2, d2) != key) break;
      a--;
   }
   return a;
}

// Rango y validez del dia de la vela i. est: 1 valido, 2 falta una vela del rango, 3 sin historial para el filtro de tamano, 4 tamano fuera de rango.
// El historial del filtro de tamano son los N dias de mercado ANTERIORES con rango completo (el de hoy no entra: no se mira el futuro).
void RupEvaluarDia(const int i, int &est, double &hi, double &lo, double &tam, double &ratio)
{
   const int per = PeriodSeconds() / 60;
   const int esperadas = InpRupRango / per;
   const int a = RupInicioDia(i);
   int cnt;
   RupRangoDe(a, i, cnt, hi, lo);
   tam = hi - lo;
   ratio = 0.0;
   if(cnt != esperadas) { est = 2; return; }
   est = 1;
   if(!InpRupTamOn) return;
   double suma = 0.0;
   int nd = 0;
   int b = a - 1;
   while(b >= 0 && nd < InpRupTamN)
   {
      int m3, d3;
      NyFecha(g_time[b], m3, d3);
      const int a3 = RupInicioDia(b);
      if(d3 != 0 && d3 != 6)
      {
         int c3;
         double h3, l3;
         RupRangoDe(a3, b, c3, h3, l3);
         if(c3 == esperadas) { suma += h3 - l3; nd++; }
      }
      b = a3 - 1;
   }
   if(nd < InpRupTamN) { est = 3; return; }
   const double prom = suma / nd;
   ratio = (prom > 0.0) ? tam / prom : 0.0;
   if(!(prom > 0.0) || ratio < InpRupTamMin || ratio > InpRupTamMax) est = 4;
}

// Estado del dia de la vela i: una vez por dia, cuando el rango ya termino. Devuelve true si el dia tiene rango valido.
bool RupPrepararDia(const int i)
{
   int mm, dw;
   const int key = NyFecha(g_time[i], mm, dw);
   if(key != g_rupDia)                       // dia nuevo: se reinicia todo
   {
      g_rupDia = key;
      g_rupEst = 0;
      g_rupHi = 0.0;
      g_rupLo = 0.0;
      g_rupN = 0;
      g_rupLado = 0;
      g_rupSL = 0;
      g_rupHora = false;
      RupGuardar();
   }
   if(g_rupEst != 0) return g_rupEst == 1;
   if(mm + PeriodSeconds() / 60 < InpRupApertura + InpRupRango) return false;       // el rango todavia no termino
   int est;
   double hi, lo, tam, ratio;
   RupEvaluarDia(i, est, hi, lo, tam, ratio);
   g_rupEst = est;
   g_rupHi = hi;
   g_rupLo = lo;
   RupGuardar();
   const string rg = RupHM(InpRupApertura) + "-" + RupHM(InpRupApertura + InpRupRango) + " NY";
   const int dig = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
   if(est == 1)
      Avisar("RUPTURA: rango " + rg + " armado: maximo " + DoubleToString(hi, dig) + ", minimo " + DoubleToString(lo, dig) + ", tamano " + DoubleToString(tam, dig)
             + (InpRupTamOn ? " (" + DoubleToString(ratio, 2) + " veces el promedio)" : "") + ". Espera una vela que cierre fuera.");
   else if(est == 2)
      Avisar("RUPTURA: hoy NO se opera: falta alguna vela del rango " + rg + " (feriado, cierre anticipado o hueco en los datos).");
   else if(est == 3)
      Avisar("RUPTURA: hoy NO se opera: todavia no hay " + IntegerToString(InpRupTamN) + " dias de historia para el filtro de tamano del rango.");
   else
      Avisar("RUPTURA: hoy NO se opera: el rango mide " + DoubleToString(ratio, 2) + " veces el promedio, fuera de " + DoubleToString(InpRupTamMin, 2) + " a "
             + DoubleToString(InpRupTamMax, 2) + ".");
   return est == 1;
}

// Cierre forzado: a la hora elegida (o si la posicion quedo abierta de un dia anterior) se cierra todo a mercado. true = se pidio el cierre.
bool RupCierreHora(const int i)
{
   if(!HasPosition()) return false;
   int mm, dw;
   const int key = NyFecha(g_time[i], mm, dw);
   bool cerrar = (mm + PeriodSeconds() / 60 >= InpRupCierre);
   if(!cerrar)
      for(int k = PositionsTotal() - 1; k >= 0; k--)
      {
         if(PositionGetSymbol(k) != _Symbol || PositionGetInteger(POSITION_MAGIC) != InpMagic) continue;
         int m2, d2;
         if(NyFecha((datetime)PositionGetInteger(POSITION_TIME), m2, d2) != key) cerrar = true;
      }
   if(!cerrar) return false;
   g_rupHora = true;
   Avisar("CIERRE POR HORA: llego el cierre forzado de las " + RupHM(InpRupCierre) + " NY. Se cierra la operacion a mercado.");
   CloseAll();
   return true;
}

// Evalua la ultima vela cerrada (i) como vela de senal de la ruptura. Se llama al abrir cada vela nueva, sin posicion abierta.
void RupEvaluar(const int i)
{
   const int per = PeriodSeconds() / 60;
   int mm, dw;
   const int key = NyFecha(g_time[i], mm, dw);
   if(dw == 0 || dw == 6) return;                                          // sabado y domingo no son dias de mercado
   const int cierreV = mm + per;                                           // minuto de Nueva York en que cerro la vela
   if(cierreV < InpRupApertura + InpRupRango) return;                      // todavia dentro del rango
   if(!RupPrepararDia(i)) return;                                          // arma el dia (y avisa) una sola vez; sin rango valido no se opera
   if(mm < InpRupApertura + InpRupRango) return;                           // la ultima vela del rango solo arma el rango: no es vela de senal
   if(cierreV > InpRupCierre) return;                                      // despues del cierre forzado
   const int lado = (g_c[i] > g_rupHi) ? 1 : ((g_c[i] < g_rupLo) ? -1 : 0);
   if(lado == 0) return;                                                   // una mecha fuera del rango no cuenta: tiene que CERRAR fuera
   const int dig = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
   const string quien = string(lado == 1 ? "RUPTURA ALCISTA" : "RUPTURA BAJISTA") + " (vela de las " + RupHM(cierreV) + " NY, cierre " + DoubleToString(g_c[i], dig) + ")";
   if(cierreV > InpRupUltima)
   {
      if(g_rupFH != key) { g_rupFH = key; AvisarDia(quien + ": fuera del horario de entrada (ultima " + RupHM(InpRupUltima) + " NY). No se opera."); }
      return;
   }
   if(g_rupN >= InpRupEntradas) return;                                    // ya se hicieron las entradas del dia
   if(g_rupN == 1)
   {
      if(lado != -g_rupLado) return;                                       // la segunda entrada solo va hacia el lado contrario...
      if(g_rupSL != 1) return;                                             // ...y solo si la primera cerro por su SL original
   }
   if(!DirectionAllows(lado)) { AvisarDia(quien + ": direccion no permitida, no se opera."); return; }
   if(!PassFilters(i, lado, true)) { AvisarDia(quien + ": descartada por los filtros. " + FiltrosTxt(i, lado, true)); return; }
   if(NewsBlockEntry(iTime(_Symbol, _Period, 0), iTime(_Symbol, _Period, 0))) return;
   if(PauseBlocks(i, lado)) { AvisarDia(quien + ": descartada, dentro del tiempo minimo tras una operacion perdedora."); return; }
   if(PauseWinBlocks(i, lado)) { AvisarDia(quien + ": descartada, dentro del tiempo minimo tras una operacion ganadora."); return; }
   if(WinRetraceBlocks(i, lado, (lado == 1) ? SymbolInfoDouble(_Symbol, SYMBOL_ASK) : SymbolInfoDouble(_Symbol, SYMBOL_BID)))
   {
      AvisarDia(quien + ": descartada, el precio todavia no retrocedio lo pedido desde la ultima ganadora.");
      return;
   }
   const double px = (lado == 1) ? SymbolInfoDouble(_Symbol, SYMBOL_ASK) : SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double lvl = 0.0, d = 0.0;
   if(InpRupSL == 2) d = g_atr[i] * InpRupSLAtr;
   else
   {
      lvl = (InpRupSL == 0) ? (g_rupHi + g_rupLo) / 2.0 : ((lado == 1) ? g_rupLo : g_rupHi);
      d = lado * (px - lvl);
   }
   if(!(d > 0.0)) { AvisarDia(quien + ": descartada, el precio ya esta del lado equivocado del SL."); return; }
   if(!AccountRulesOK(d)) return;
   Avisar(quien + ": entrada a mercado, SL a " + DoubleToString(d, dig) + " del precio, TP a " + DoubleToString(d * InpRR, dig) + " (1:" + DoubleToString(InpRR, 2) + ").");
   if(MarketEntry(lado, d, lvl))
   {
      g_rupN++;
      if(g_rupN == 1) g_rupLado = lado;
      RupGuardar();
   }
}
'''

# ----------------------------------------------------------------------------------------------------------------------------
_ON_TRADE_RUP = r'''      if(g_rupHora && motivo == DEAL_REASON_EXPERT) que = "CIERRE POR HORA (cierre forzado de la ruptura)";
      g_rupHora = false;
      if(g_rupN == 1)                                 // resultado de la primera operacion del dia: la segunda entrada solo se habilita si salio por su SL original
      {
         g_rupSL = (motivo == DEAL_REASON_SL && !esBe && !conParcial) ? 1 : 0;
         RupGuardar();
      }
'''

_SALTAR_PRINT = ("Pocas velas", "Tendencia mayor: pocas velas", "No se pudo enviar la notificacion", "Bot iniciado", "AVISO: el calendario economico no existe")


def _una(txt: str, ancla: str, nuevo: str, que: str) -> str:
    n = txt.count(ancla)
    if n != 1:
        raise RuntimeError(f"Bot de ruptura: la plantilla cambio ({que}: {n} coincidencias). Revisar generar_bot_ruptura.py.")
    return txt.replace(ancla, nuevo)


_una_base = _una


def _args_toplevel(s: str):
    """Divide los argumentos de una llamada por las comas de primer nivel (respeta parentesis y comillas)."""
    args, prof, cur, i, q = [], 0, [], 0, False
    while i < len(s):
        ch = s[i]
        if q:
            cur.append(ch)
            if ch == "\\" and i + 1 < len(s):
                cur.append(s[i + 1])
                i += 1
            elif ch == '"':
                q = False
        elif ch == '"':
            q = True
            cur.append(ch)
        elif ch in "([":
            prof += 1
            cur.append(ch)
        elif ch in ")]":
            prof -= 1
            cur.append(ch)
        elif ch == "," and prof == 0:
            args.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
        i += 1
    args.append("".join(cur).strip())
    return args


def _print_a_avisar(txt: str) -> str:
    """Todo `Print(a, b, ...)` del bot pasa a `AvisarDia(a + b + ...)`: el registro de MT5 tambien llega al celular."""
    salida, pos = [], 0
    for m in re.finditer(r"\bPrint\(", txt):
        if m.start() < pos:
            continue
        ini = txt.rfind("\n", 0, m.start()) + 1
        if txt[ini:m.start()].lstrip().startswith("//"):
            continue
        j, prof, q = m.end(), 1, False
        while j < len(txt) and prof:
            ch = txt[j]
            if q:
                if ch == "\\":
                    j += 1
                elif ch == '"':
                    q = False
            elif ch == '"':
                q = True
            elif ch == "(":
                prof += 1
            elif ch == ")":
                prof -= 1
            j += 1
        cuerpo = txt[m.end():j - 1]
        if cuerpo.strip() == "txt" or any(s in cuerpo for s in _SALTAR_PRINT):
            continue
        partes = []
        for a in _args_toplevel(cuerpo):
            partes.append(a if re.fullmatch(r'"(?:[^"\\]|\\.)*"', a) else f"(string)({a})")
        salida.append(txt[pos:m.start()])
        salida.append("AvisarDia(" + " + ".join(partes) + ")")
        pos = j
    salida.append(txt[pos:])
    return "".join(salida)


def generar_mq5_ruptura(cfg, simbolo: str, tf: str, lotes: float, veredicto: Optional[dict] = None, fecha: Optional[datetime] = None,
                        capital: float = 0.0, limite_pct: float = 10.0, nombre: str = "", usd_por_unidad_forzado: float = 0.0) -> str:
    """cfg: engine.Config con `ruptura` (ConfigRup) tal como lo arma la pantalla. Mismos requisitos que generar_bot.generar_mq5 (veredicto que lo respalde)."""
    rp = getattr(cfg, "ruptura", None)
    if rp is None:
        raise ValueError("Este generador es solo para la estrategia de ruptura (falta la configuracion de ruptura).")
    cfg.validar()
    per = _PER_MIN.get(tf)
    if per is None:
        raise ValueError("Falta la temporalidad: elegí una en «Datos» o en «Remuestrear a».")
    if per > rp.rango_min or rp.rango_min % per:
        raise ValueError(f"Con velas de {per} minutos el rango de {rp.rango_min} minutos no se puede armar: la duracion tiene que ser multiplo de la vela y no menor.")
    # configuracion base: sin senal propia (el SL/TP reales los pone el codigo de la ruptura); ATR con el multiplo elegido
    bo = rup_mod.BOLSAS[rp.bolsa]
    NOM, COR = bo["nombre"], bo["corto"]

    def _loc(t):                                    # textos propios del bot: la bolsa elegida en lugar de Nueva York / NY (con NY no cambia nada)
        return t.replace("Nueva York", NOM).replace(" NY", " " + COR)

    def _una(t, old, new, que):                     # solo el texto nuevo se localiza; el ancla es del bot base
        return _una_base(t, old, _loc(new), que)

    base = dataclasses.replace(cfg, ruptura=None, sl_modo="atr", sl_valor=float(rp.sl_atr_x) if rp.sl_modo == "atr" else 1.0, salida_modo="rr",
                               modo_senal="cruce", pullback_activo=False, reentrada_activa=False)
    txt = gb.generar_mq5(base, simbolo, tf, lotes, veredicto=veredicto, fecha=fecha, capital=capital, limite_pct=limite_pct,
                         nombre=nombre or f"Ruptura {COR}", usd_por_unidad_forzado=usd_por_unidad_forzado)

    # ---- todo lo que el bot escribe en el registro llega tambien al celular (antes de agregar el codigo propio, que ya usa Avisar/AvisarDia)
    txt = _print_a_avisar(txt)

    # ---- cabecera y nombre
    txt = _una(txt, "Expert Advisor generado por la app de backtesting (cruce de EMAs)|", "Expert Advisor de ruptura del rango de apertura de Nueva York|", "titulo")
    txt = _una(txt, '#property description "Cruce de EMAs con filtros, SL/TP, pullback y proteccion de cuenta.',
               '#property description "Ruptura del rango de apertura de Nueva York con filtros, SL/TP y proteccion de cuenta.', "descripcion")
    sl_txt = {"mitad": "SL en la mitad del rango", "opuesto": "SL en el lado opuesto del rango", "atr": f"SL de {gb._f(rp.sl_atr_x, 2)} x ATR({cfg.atr_periodo})"}[rp.sl_modo]
    cab = [f"// Ruptura del rango de apertura de Nueva York {_hhmm(rp.apertura_min)}-{_hhmm(rp.apertura_min + rp.rango_min)} (hora de NY) | direccion: {cfg.direccion} "
           f"| RR {gb._f(cfg.rr, 2)} | lotes {gb._f(lotes, 2)}",
           f"// {sl_txt}; entradas por dia: {rp.entradas_dia}" + (" (la segunda solo hacia el lado contrario y solo si la primera cerro por su SL)" if rp.entradas_dia == 2 else "")
           + f"; ultima entrada {_hhmm(rp.ultima_min)} y cierre forzado {_hhmm(rp.cierre_min)} (hora de NY)"
           + (f"; filtro de tamano del rango: {gb._f(rp.tam_min, 2)} a {gb._f(rp.tam_max, 2)} veces el promedio de {rp.tam_n} dias" if rp.tam_activo else ""),
           "// Entrada: una vela M5 (o la temporalidad del grafico) CIERRA fuera del rango; el bot entra a mercado apenas abre la vela siguiente (el backtest entra al "
           "cierre de esa vela: ver la guia, diferencias entre backtest y bot).",
           "// Todos los mensajes del registro de MT5 tambien llegan al celular (SendNotification); un mensaje repetido se manda una vez por dia."]
    txt = re.sub(r"^// .*\| direccion: .*\n// SL: .*\n", _loc("\n".join(cab)) + "\n", txt, count=1, flags=re.M)
    if f"Ruptura del rango de apertura de {NOM}" not in txt.split("const bool            InpVerdictOK")[0].split("//----", 1)[1]:
        raise RuntimeError("Bot de ruptura: no se pudo reemplazar la cabecera.")

    # ---- magic propio
    txt = re.sub(r"(const long\s+InpMagic\s+= )\d+;", lambda m: f"{m.group(1)}{_magic_ruptura(cfg, simbolo)};", txt, count=1)

    # ---- inputs
    mapa = {"RUP_ZONA": str(rup_mod.BOLSAS[rp.bolsa]["bot"]), "RUP_AP": str(int(rp.apertura_min)), "RUP_DUR": str(int(rp.rango_min)), "RUP_SL": str(("mitad", "opuesto", "atr").index(rp.sl_modo)),
            "RUP_SL_ATR": gb._f(rp.sl_atr_x, 4), "RUP_ENT": str(int(rp.entradas_dia)), "RUP_ULT": str(int(rp.ultima_min)), "RUP_CIE": str(int(rp.cierre_min)),
            "RUP_TAM_ON": gb._b(rp.tam_activo), "RUP_TAM_MIN": gb._f(rp.tam_min, 4), "RUP_TAM_MAX": gb._f(rp.tam_max, 4), "RUP_TAM_N": str(int(rp.tam_n))}
    inp = _INPUTS
    for k, v in mapa.items():
        inp = inp.replace(f"@@{k}@@", v)
    txt = _una(txt, "const int             InpDeviation      = 20;             // Deslizamiento maximo permitido (puntos)\n",
               "const int             InpDeviation      = 20;             // Deslizamiento maximo permitido (puntos)\n" + inp, "inputs")

    # ---- historia: el filtro de tamano necesita N dias validos anteriores
    txt = _una(txt, "   if(InpVpOn) n = MathMax(n, (int)((InpVpDays + 5) * 86400.0 / PeriodSeconds()) + 200);\n   return n;",
               "   if(InpVpOn) n = MathMax(n, (int)((InpVpDays + 5) * 86400.0 / PeriodSeconds()) + 200);\n"
               "   if(InpRupOn && InpRupTamOn) n = MathMax(n, (int)((InpRupTamN * 1.6 + 6.0) * 86400.0 / PeriodSeconds()) + 300);   // N dias de mercado anteriores del filtro de tamano\n"
               "   return n;", "historia")

    # ---- estado, AvisarDia y funciones
    txt = _una(txt, "bool V(const double x) { return x > -1.0e299; }\n", _GLOBALES + "\nbool V(const double x) { return x > -1.0e299; }\n", "globales")
    txt = _una(txt, "// ============================ indicadores =====================================\n",
               _AVISAR_DIA + "\n// ============================ indicadores =====================================\n", "avisar_dia")
    txt = _una(txt, "void OnNewBar()\n{", _FUNCIONES + "\nvoid OnNewBar()\n{", "funciones")

    # ---- OnNewBar: cierre forzado al principio y señal de la ruptura en lugar del cruce de medias
    txt = _una(txt, "   ReTrack(i);                                 // reentrada: el cruce contrario o la caducidad terminan la tendencia\n",
               "   if(RupCierreHora(i)) return;                // cierre forzado por hora (o posicion de un dia anterior)\n", "cierre_hora")
    ini = txt.index("   const int cr = CrossAt(i);\n   const bool conPullback")
    fin = txt.index("// ============================ eventos =====================================")
    cuerpo = txt[ini:fin]
    if not cuerpo.rstrip().endswith("}"):
        raise RuntimeError("Bot de ruptura: no se reconocio el final de OnNewBar.")
    txt = txt[:ini] + "   RupEvaluar(i);                              // ruptura del rango de apertura: ultima vela cerrada\n}\n\n" + txt[fin:]

    # ---- OnInit: validaciones y recuperacion del estado
    txt = _una(txt, "   if(InpExpectedSymbol != _Symbol)\n",
               "   {\n"
               "      const int perm = PeriodSeconds() / 60;\n"
               "      if(perm < 1 || perm > InpRupRango || (InpRupRango % perm) != 0)\n"
               "      {\n"
               "         Avisar(\"RECHAZADO: con velas de \" + IntegerToString(perm) + \" minutos no se puede armar el rango de apertura de \" + IntegerToString(InpRupRango) + \" minutos.\");\n"
               "         return INIT_PARAMETERS_INCORRECT;\n"
               "      }\n"
               "      const datetime srvR = TimeTradeServer();\n"
               "      const double medidoR = MathRound((double)(srvR - TimeGMT()) / 3600.0);\n"
               "      const double esperadoR = InpServerOffset + ((InpServerDST && UsDstServidor(srvR) == 1) ? 1.0 : 0.0);\n"
               "      if(MathAbs(medidoR - esperadoR) > 0.01)\n"
               "      {\n"
               "         Avisar(\"RECHAZADO: el desfase del servidor (\" + DoubleToString(medidoR, 0) + \" h) no coincide con el del backtest (\" + DoubleToString(esperadoR, 0) + \" h): la apertura de Nueva York quedaria mal ubicada. Revisa el desfase en la app y regenera el bot.\");\n"
               "         return INIT_FAILED;\n"
               "      }\n"
               "   }\n"
               "   if(InpExpectedSymbol != _Symbol)\n", "init_validar")
    txt = _una(txt, "   g_dayKey = DayKeyNow();\n", "   g_dayKey = DayKeyNow();\n   RupCargar();                                   // rango, entradas, lado y resultado de la primera operacion del dia\n", "init_cargar")
    txt = _una(txt, '      Avisar(que + ". Operando con los parametros del backtest.");',
               '      Avisar(que + ". Ruptura del rango " + RupHM(InpRupApertura) + "-" + RupHM(InpRupApertura + InpRupRango) + " NY, ultima entrada " + RupHM(InpRupUltima)\n'
               '             + ", cierre forzado " + RupHM(InpRupCierre) + " NY. Operando con los parametros del backtest.");', "init_aviso")

    # ---- OnTradeTransaction: cierre por hora y resultado de la primera operacion
    txt = _una(txt, "      g_salidaSenal = false;\n      g_beCerrar = false;\n", _ON_TRADE_RUP + "      g_salidaSenal = false;\n      g_beCerrar = false;\n", "ontrade")

    pend = re.findall(r"@@[A-Z_]+@@", txt)
    if pend:
        raise RuntimeError(f"Quedaron campos sin completar en la plantilla: {sorted(set(pend))}")
    if txt.count("{") != txt.count("}"):
        raise RuntimeError("Bot de ruptura: llaves desbalanceadas.")
    return txt
