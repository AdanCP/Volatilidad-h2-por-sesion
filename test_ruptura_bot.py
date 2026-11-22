"""Bot de MT5 de la ruptura (generar_bot_ruptura.py): contenido del codigo generado y, si hay g++, paridad con el backtest.

El codigo MQL5 generado se compila contra el stub de MQL5 (mql_stub.h, con funciones de precio, ordenes, posiciones y variables globales reales
para esta prueba) y se compara con el motor: validez del dia (rango completo, tamaño, historial), vela de la señal, distancia del SL, TP, segunda
entrada y cierre forzado, incluso con el cambio de hora de EE.UU. No reemplaza compilar en MetaEditor ni correr el probador de estrategias de MT5."""
import os
import re
import shutil
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import engine as eng
import generar_bot as gb
import generar_bot_ruptura as gbr
import ruptura as rup
from test_generar_bot import _a_cpp

AQUI = os.path.dirname(os.path.abspath(__file__))
HAY_GPP = shutil.which("g++") is not None
VD = {"nivel": "ok", "titulo": "Valida para intentar"}
OFF = pd.Timedelta(hours=7)                     # servidor = NY + 7 h (desfase 2 con el cambio de hora de EE.UU.)


def _cfg(**rp):
    return eng.Config(media_tipo="ema", sl_modo="precio", sl_valor=1.0, salida_modo="rr", rr=2.0, servidor_offset_horas=2.0, servidor_dst_eeuu=True,
                      ruptura=rup.ConfigRup(**rp))


def _bot(cfg=None, tf="M5", **k):
    return gbr.generar_mq5_ruptura(cfg or _cfg(), "US30", tf, 0.1, veredicto=VD, **k)


# ----------------------------------------------------------------------------- contenido del codigo generado
def test_el_bot_contiene_la_logica_de_la_ruptura():
    t = _bot(_cfg(entradas_dia=2, sl_modo="opuesto", tam_activo=True, tam_n=10))
    assert "@@" not in t and t.count("{") == t.count("}")
    for frag in ["InpRupApertura    = 570", "InpRupRango       = 15", "InpRupSL          = 1", "InpRupEntradas    = 2", "InpRupUltima      = 720",
                 "InpRupCierre      = 750", "InpRupTamOn       = true", "InpRupTamN        = 10", "int NyFecha(", "void RupEvaluarDia(", "bool RupPrepararDia(",
                 "bool RupCierreHora(", "void RupEvaluar(", "CIERRE POR HORA", "RupGuardar()", "RupCargar()", 'g_gv + "RUPN"', 'g_gv + "RUPLADO"', 'g_gv + "RUPSL"',
                 'g_gv + "RUPHI"', 'g_gv + "RUPDIA"', "InpServerOffset", "InpServerDST", "InpVerdictOK      = true", "SendNotification"]:
        assert frag in t, frag
    assert not re.search(r"^input ", t, flags=re.M)                                  # parametros fijos
    cuerpo = t[t.index("void OnNewBar()"):t.index("// ============================ eventos")]
    assert "RupEvaluar(i)" in cuerpo and "RupCierreHora(i)" in cuerpo
    assert "CrossAt" not in cuerpo and "PlacePullback" not in cuerpo               # el cruce de medias ya no decide nada


def test_magic_propio_y_distinto_del_de_los_bots_de_ema():
    m = int(re.search(r"InpMagic\s+= (\d+);", _bot()).group(1))
    assert 800000 <= m < 890000
    assert m != int(re.search(r"InpMagic\s+= (\d+);", _bot(_cfg(entradas_dia=2))).group(1))      # otra configuracion, otro magic
    assert m == int(re.search(r"InpMagic\s+= (\d+);", _bot()).group(1))                          # estable
    ema = gb.generar_mq5(eng.Config(), "US30", "M5", 0.1, veredicto=VD)
    assert int(re.search(r"InpMagic\s+= (\d+);", ema).group(1)) < 800000


def test_los_mensajes_del_registro_llegan_al_celular():
    t = _bot()
    # ningun Print suelto salvo los de adentro de Avisar/AvisarDia y los de diagnostico de arranque o de datos (que se repetirian en cada vela)
    sueltos = [l.strip() for l in t.split("\n") if re.search(r"\bPrint\(", l) and not l.strip().startswith("//")]
    for l in sueltos:
        assert any(s in l for s in ("Print(txt)", "No se pudo enviar la notificacion", "Pocas velas", "Tendencia mayor: pocas velas", "Bot iniciado",
                                    "AVISO: el calendario economico", 'Print("Bot " + _Symbol')), l
    assert "bool AvisarDia(" in t and t.count("AvisarDia(") > 20
    assert 'Avisar("RUPTURA: rango "' in t or "Avisar(\"RUPTURA: rango \"" in t.replace("Avisar(\"RUPTURA: rango \" + rg", "Avisar(\"RUPTURA: rango \"")
    assert "CIERRE POR HORA (cierre forzado de la ruptura)" in t                    # el cierre por hora tambien avisa al cerrarse la operacion


def test_el_bot_no_cambia_a_los_de_ema_ni_sma():
    for tipo in ("ema", "sma"):
        t = gb.generar_mq5(eng.Config(media_tipo=tipo), "XAUUSD", "H1", 0.1, veredicto=VD)
        assert "Rup" not in t and "AvisarDia" not in t


def test_rechazos():
    with pytest.raises(ValueError):                                                  # sin veredicto
        gbr.generar_mq5_ruptura(_cfg(), "US30", "M5", 0.1)
    with pytest.raises(ValueError):                                                  # el veredicto no lo respalda
        gbr.generar_mq5_ruptura(_cfg(), "US30", "M5", 0.1, veredicto={"nivel": "nc", "titulo": "x"})
    with pytest.raises(ValueError):                                                  # velas de 60 minutos: el rango de 15 no se arma
        _bot(tf="H1")
    with pytest.raises(ValueError):                                                  # sin configuracion de ruptura
        gbr.generar_mq5_ruptura(eng.Config(), "US30", "M5", 0.1, veredicto=VD)
    with pytest.raises(ValueError):                                                  # sin desfase del servidor no se ubica la apertura
        gbr.generar_mq5_ruptura(eng.Config(media_tipo="ema", sl_modo="precio", ruptura=rup.ConfigRup()), "US30", "M5", 0.1, veredicto=VD)


def test_m15_con_rango_de_15_y_m5_con_rango_de_30():
    assert "PERIOD_M15" in _bot(tf="M15")
    assert "InpRupRango       = 30" in _bot(_cfg(rango_min=30, ultima_min=12 * 60))


def test_si_la_plantilla_cambia_falla_fuerte(monkeypatch):
    monkeypatch.setattr(gb, "_PLANTILLA", gb._PLANTILLA.replace("void OnNewBar()\n{", "void OnNewBar2()\n{"))
    with pytest.raises(RuntimeError):
        _bot()


# ----------------------------------------------------------------------------- compilacion y paridad con el backtest (g++ + stub)
_PRE = r'''#define SymbolInfoDouble SymbolInfoDouble_o
#define OrderSend OrderSend_o
#define PositionsTotal PositionsTotal_o
#define PositionGetSymbol PositionGetSymbol_o
#define PositionGetInteger PositionGetInteger_o
#define GlobalVariableCheck GlobalVariableCheck_o
#define GlobalVariableGet GlobalVariableGet_o
#define GlobalVariableSet GlobalVariableSet_o
#define EnumToString EnumToString_o
#include "mql_stub.h"
#undef SymbolInfoDouble
#undef OrderSend
#undef PositionsTotal
#undef PositionGetSymbol
#undef PositionGetInteger
#undef GlobalVariableCheck
#undef GlobalVariableGet
#undef GlobalVariableSet
#undef EnumToString
#include <map>
inline std::string EnumToString(int v){ return "PERIOD_M" + std::to_string(v); }
static double stub_ask = 1, stub_bid = 1; static int stub_nord = 0; static MqlTradeRequest stub_rq; static int stub_npos = 0; static long stub_ptime = 0; static long stub_magic_pos = -1;
static std::map<std::string, double> stub_gv;
inline double SymbolInfoDouble(const std::string&s, int p){ if(p==SYMBOL_ASK) return stub_ask; if(p==SYMBOL_BID) return stub_bid; return SymbolInfoDouble_o(s,p); }
inline bool OrderSend(MqlTradeRequest&r, MqlTradeResult&s){ stub_rq = r; stub_nord++; s.retcode = TRADE_RETCODE_DONE; return true; }
inline int PositionsTotal(){ return stub_npos; }
inline std::string PositionGetSymbol(int){ return _Symbol; }
inline long PositionGetInteger(int p){ if(p==POSITION_MAGIC) return stub_magic_pos; if(p==POSITION_TIME) return stub_ptime; return 0; }
inline bool GlobalVariableCheck(const std::string&n){ return stub_gv.count(n) > 0; }
inline double GlobalVariableGet(const std::string&n){ return stub_gv.count(n) ? stub_gv[n] : 0.0; }
inline void GlobalVariableSet(const std::string&n, double v){ stub_gv[n] = v; }
inline std::string _S(const std::string&s){ return s; } inline std::string _S(const char*s){ return s; } template<class T> std::string _S(T v){ return std::to_string(v); }
'''

# lee las velas (epoch del servidor, h, l, c, atr, spread) y evalua cada una como "ultima vela cerrada"
_MAIN_SENAL = r'''
int main()
{
   int n; if(scanf("%d", &n) != 1) return 1;
   g_time.resize(n); g_h.resize(n); g_l.resize(n); g_c.resize(n); g_atr.resize(n);
   std::vector<double> sp(n);
   for(int i = 0; i < n; i++) { long long t; double h, l, c, a, s; if(scanf("%lld %lf %lf %lf %lf %lf", &t, &h, &l, &c, &a, &s) != 6) return 2; g_time[i] = t; g_h[i] = h; g_l[i] = l; g_c[i] = c; g_atr[i] = a; sp[i] = s; }
   g_psec = 300; g_m = n; g_gv = "BOT_"; stub_magic_pos = InpMagic;
   int ultimo = 0;
   for(int i = 0; i < n; i++)
   {
      stub_ask = g_c[i] + sp[i]; stub_bid = g_c[i]; stub_nord = 0;
      const int antes = g_rupN;
      RupEvaluar(i);
      if(g_rupEst != 0 && ultimo != g_rupDia) { printf("DIA %d %d\n", g_rupDia, g_rupEst); ultimo = g_rupDia; }
      if(g_rupN > antes) printf("ENT %d %d %.10f %.10f %.10f\n", i, stub_rq.type == ORDER_TYPE_BUY ? 1 : -1, stub_rq.price, stub_rq.sl, stub_rq.tp);
   }
   return 0;
}
'''

# misma lectura; abre una posicion a las 10:00 de NY de cada dia y dice en que vela pide el cierre forzado
_MAIN_CIERRE = r'''
int main()
{
   int n; if(scanf("%d", &n) != 1) return 1;
   g_time.resize(n); g_h.resize(n); g_l.resize(n); g_c.resize(n); g_atr.resize(n);
   for(int i = 0; i < n; i++) { long long t; double h, l, c, a, s; if(scanf("%lld %lf %lf %lf %lf %lf", &t, &h, &l, &c, &a, &s) != 6) return 2; g_time[i] = t; g_h[i] = h; g_l[i] = l; g_c[i] = c; g_atr[i] = a; }
   g_psec = 300; g_m = n; g_gv = "BOT_"; stub_magic_pos = InpMagic; stub_npos = 1;
   int dia = 0;
   for(int i = 0; i < n; i++)
   {
      int mm, dw; const int key = NyFecha(g_time[i], mm, dw);
      if(key != dia) { dia = key; stub_ptime = 0; g_rupHora = false; }
      if(stub_ptime == 0)                                    // la posicion se "abre" en la primera vela de las 10:00 NY o despues
      {
         if(mm >= InpRupApertura + 30) stub_ptime = g_time[i];
         continue;
      }
      if(g_rupHora) continue;
      stub_nord = 0;
      if(RupCierreHora(i)) printf("CIERRE %d %d\n", i, stub_nord);
   }
   return 0;
}
'''

_cache = {}


def _compilar_bot(clave, cfg, main, tf="M5"):
    if (clave, main) in _cache:
        return _cache[(clave, main)]
    d = os.path.join(os.environ.get("TMPDIR", "/tmp"), f"rupbot_{os.getpid()}_{len(_cache)}")
    os.makedirs(d, exist_ok=True)
    t = _bot(cfg, tf=tf).replace("string   g_avTxt[];", "std::vector<std::string> g_avTxt;")
    t = _a_cpp(t).replace("(string)(", "_S(")
    shutil.copy(os.path.join(AQUI, "mql_stub.h"), os.path.join(d, "mql_stub.h"))
    with open(os.path.join(d, "mql.h"), "w") as f:
        f.write(_PRE)
    with open(os.path.join(d, "b.cpp"), "w") as f:
        f.write('#include "mql.h"\n' + t + main)
    r = subprocess.run(["g++", "-std=c++17", "-O1", "-o", os.path.join(d, "b"), os.path.join(d, "b.cpp")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[:3000]
    _cache[(clave, main)] = os.path.join(d, "b")
    return _cache[(clave, main)]


def _a_servidor(idx_local, zona):
    """Hora local de la bolsa -> hora del servidor (UTC + 2 h, +1 h con el horario de verano de EE.UU.)."""
    utc = idx_local.tz_localize(zona, ambiguous="NaT", nonexistent="NaT").tz_convert("UTC")
    ny = utc.tz_convert("America/New_York")
    return (utc.tz_localize(None) + pd.to_timedelta([2 + (1 if t.dst() else 0) for t in ny], unit="h"))


def _datos(desde, dias, seed, sin_vela=(), feriados=(), bolsa="ny"):
    """Velas M5 desde 3 h antes de la apertura hasta 8 h despues (5:00 a 13:00 en NY; indice en hora del servidor), caminata al azar con volatilidad distinta por dia."""
    b = rup.BOLSAS[bolsa]
    ini_h = b["apertura"] // 60 - 4 if bolsa == "ny" else b["apertura"] // 60 - 3
    fin_h = ini_h + 8
    ap = f"{b['apertura'] // 60:02d}:{b['apertura'] % 60 + 5:02d}"
    rng = np.random.default_rng(seed)
    partes, precio = [], 100.0
    for f in pd.bdate_range(desde, periods=dias):
        if f.strftime("%Y-%m-%d") in feriados:
            continue
        idx = pd.date_range(f"{f:%Y-%m-%d} {ini_h:02d}:00", f"{f:%Y-%m-%d} {fin_h:02d}:00", freq="5min", inclusive="left")
        esc = rng.uniform(0.4, 2.0)
        c = precio + np.cumsum(rng.normal(0, 0.12 * esc, len(idx)))
        o = np.r_[precio, c[:-1]]
        h = np.maximum(o, c) + np.abs(rng.normal(0, 0.05 * esc, len(idx)))
        l = np.minimum(o, c) - np.abs(rng.normal(0, 0.05 * esc, len(idx)))
        idx_srv = (idx + OFF) if bolsa == "ny" else _a_servidor(idx, b["zona"])
        d = pd.DataFrame({"Open": o, "High": h, "Low": l, "Close": c, "Volume": 100.0, "Spread": 0.0}, index=idx_srv)
        if f.strftime("%Y-%m-%d") in sin_vela:
            d = d.drop(pd.Timestamp(f"{f:%Y-%m-%d} {ap}") + OFF if bolsa == "ny" else _a_servidor(pd.DatetimeIndex([f"{f:%Y-%m-%d} {ap}"]), b["zona"])[0])
        partes.append(d)
        precio = c[-1]
    return pd.concat(partes)


def _entrada(df, atr, sp):
    lineas = [str(len(df))]
    for t, h, l, c, a, s in zip(df.index, df["High"], df["Low"], df["Close"], atr, sp):
        lineas.append(f"{int(t.value // 10**9)} {float(h)!r} {float(l)!r} {float(c)!r} {float(a)!r} {float(s)!r}")
    return "\n".join(lineas) + "\n"


def _correr(exe, df, atr, sp):
    r = subprocess.run([exe], input=_entrada(df, atr, sp), capture_output=True, text=True)
    assert r.returncode == 0, r.stdout[-500:] + r.stderr[-500:]
    return r.stdout.split("\n")


def _esperado(df, cfg, atr, sp):
    """Lo que dice el backtest: estado de cada dia y la primera señal valida (vela, lado, distancia del SL)."""
    s = rup.senales(df, cfg, cfg.ruptura, sp, atr)
    dias = {}
    for _, f in s["dias"].iterrows():
        dias[int(f["fecha"])] = {"sin_vela": 2, "historial": 3, "tamano": 4}.get(f["motivo"], 1) if f["estado"] == "ok" else 2
    ent = []
    for g in range(s["n_grupos"]):
        vi = np.flatnonzero((s["grupo"] == g) & (s["sube"] | s["baja"]) & np.array([p is None for p in s["pre"]]))
        if len(vi):
            i = int(vi[0])
            ent.append((i, 1 if s["sube"][i] else -1, float(s["dist"][i])))
    return dias, ent, s


VARIANTES = {
    "mitad": dict(),
    "opuesto_tam": dict(sl_modo="opuesto", tam_activo=True, tam_min=0.6, tam_max=1.4, tam_n=5),
    "atr_ultima": dict(sl_modo="atr", sl_atr_x=1.5, ultima_min=11 * 60 + 30, cierre_min=12 * 60),
}


@pytest.mark.skipif(not HAY_GPP, reason="hace falta g++")
@pytest.mark.parametrize("nombre", list(VARIANTES))
@pytest.mark.parametrize("ventana", [("2024-02-26", 40, 3), ("2024-10-14", 40, 5)])     # incluye el cambio de hora de EE.UU. (10 de marzo y 3 de noviembre)
def test_el_bot_arma_el_dia_y_entra_igual_que_el_backtest(nombre, ventana):
    desde, n, seed = ventana
    df = _datos(desde, n, seed, sin_vela=(str(pd.bdate_range(desde, periods=n)[7].date()),), feriados=(str(pd.bdate_range(desde, periods=n)[12].date()),))
    cfg = _cfg(**VARIANTES[nombre])
    atr = np.full(len(df), 0.35)
    sp = np.where(np.arange(len(df)) % 3 == 0, 0.02, 0.0)
    dias, ent, s = _esperado(df, cfg, atr, sp)
    sal = _correr(_compilar_bot(nombre, cfg, _MAIN_SENAL), df, atr, sp)
    dias_bot = {int(l.split()[1]): int(l.split()[2]) for l in sal if l.startswith("DIA")}
    ent_bot = [(int(l.split()[1]), int(l.split()[2]), float(l.split()[3]), float(l.split()[4]), float(l.split()[5])) for l in sal if l.startswith("ENT")]
    # estado de cada dia (1 valido, 2 falta una vela, 3 sin historial, 4 tamaño fuera de rango)
    assert dias_bot == {k: v for k, v in dias.items() if k in dias_bot}
    assert set(dias_bot) == set(dias)
    assert any(v == 2 for v in dias.values())                                              # el dia sin la vela de las 9:35 quedo descartado
    if nombre == "opuesto_tam":
        assert 3 in dias.values() and 4 in dias.values() and 1 in dias.values()           # historial, tamaño y validos: las tres ramas
    # señales: misma vela, mismo lado, misma distancia al SL y TP a RR sobre esa distancia
    assert [(i, lado) for i, lado, *_ in ent_bot] == [(i, lado) for i, lado, _ in ent] and len(ent) >= 5
    for (i, lado, precio, sl, tp), (_, _, dist) in zip(ent_bot, ent):
        assert lado * (precio - sl) == pytest.approx(dist, abs=1e-9)
        assert (tp - precio) * lado == pytest.approx(2.0 * dist, abs=1e-9)


@pytest.mark.skipif(not HAY_GPP, reason="hace falta g++")
@pytest.mark.parametrize("ventana", [("2024-02-26", 30, 11), ("2024-10-21", 30, 13)])
def test_el_cierre_forzado_cae_en_la_misma_vela_que_el_backtest(ventana):
    desde, n, seed = ventana
    df = _datos(desde, n, seed)
    cfg = _cfg(cierre_min=12 * 60 + 30)
    atr = np.full(len(df), 0.3)
    sp = np.zeros(len(df))
    s = rup.senales(df, cfg, cfg.ruptura, sp, atr)
    sal = _correr(_compilar_bot("mitad", cfg, _MAIN_CIERRE), df, atr, sp)
    cierres = [int(l.split()[1]) for l in sal if l.startswith("CIERRE")]
    esperadas = [int(i) for i in np.flatnonzero(s["hcierre"])]
    assert cierres == esperadas and len(cierres) >= 20


@pytest.mark.skipif(not HAY_GPP, reason="hace falta g++")
def test_segunda_entrada_y_reinicio():
    """2 entradas por dia: la segunda solo hacia el lado contrario y solo si la primera salio por su SL; un reinicio recupera el estado."""
    main = r'''
#define EV(k) { stub_ask = stub_bid = g_c[k]; RupEvaluar(k); }
int main()
{
   g_time.resize(40); g_h.resize(40); g_l.resize(40); g_c.resize(40); g_atr.resize(40);
   for(int k = 0; k < 40; k++) { g_time[k] = 1709251200 + 16 * 3600 + 30 * 60 + (k - 3) * 300; g_h[k] = 100.2; g_l[k] = 99.8; g_c[k] = 100.0; g_atr[k] = 0.3; }
   g_psec = 300; g_m = 40; g_gv = "BOT_"; stub_magic_pos = InpMagic; stub_ask = 100.0; stub_bid = 100.0;
   // la vela 3 es la de las 9:30; velas 3..5 = rango; la 6 (9:45) es la primera de señal
   g_c[6] = 100.5; g_h[6] = 100.6;                                        // ruptura alcista
   stub_nord = 0; EV(5);  printf("A %d %d\n", g_rupEst, g_rupN);   // la ultima vela del rango: solo arma
   stub_nord = 0; EV(6);  printf("B %d %d %d\n", g_rupN, g_rupLado, stub_nord);
   g_c[7] = 99.4; g_l[7] = 99.3;                                          // ruptura bajista, con la primera todavia sin resultado
   stub_nord = 0; EV(7);  printf("C %d %d\n", g_rupN, stub_nord);
   g_rupSL = 0; stub_nord = 0; EV(7); printf("D %d %d\n", g_rupN, stub_nord);   // primera cerro por TP/BE/hora: no hay segunda
   g_c[8] = 100.6; g_h[8] = 100.7;
   g_rupSL = 1; stub_nord = 0; EV(8); printf("E %d %d\n", g_rupN, stub_nord);    // misma direccion que la primera: no
   g_rupSL = 1; stub_nord = 0; EV(7); printf("F %d %d %d\n", g_rupN, stub_nord, stub_rq.type == ORDER_TYPE_SELL ? 1 : 0);   // contraria y la primera cerro por SL: si
   EV(7); printf("G %d\n", g_rupN);                                // ya van dos: no hay mas
   // reinicio: se pierde el estado en memoria y se recupera de las variables globales
   const int n = g_rupN, lado = g_rupLado, sl = g_rupSL; const double hi = g_rupHi;
   g_rupDia = 0; g_rupN = 0; g_rupLado = 0; g_rupSL = 0; g_rupHi = 0; g_rupEst = 0;
   RupCargar(); printf("H %d %d %d %d %d\n", g_rupN == n, g_rupLado == lado, g_rupSL == sl, g_rupHi == hi, g_rupEst);
   return 0;
}
'''
    exe = _compilar_bot("dos", _cfg(entradas_dia=2), main)
    sal = {l.split()[0]: l.split()[1:] for l in subprocess.run([exe], capture_output=True, text=True).stdout.strip().split("\n")}
    assert sal["A"] == ["1", "0"]                      # el rango se arma, sin entrada
    assert sal["B"] == ["1", "1", "1"]                 # primera entrada: compra
    assert sal["C"] == ["1", "0"]                      # la primera no tiene resultado de SL: no hay segunda
    assert sal["D"] == ["1", "0"]
    assert sal["E"] == ["1", "0"]                      # mismo sentido: no
    assert sal["F"] == ["2", "1", "1"]                 # contraria y la primera cerro por SL: venta
    assert sal["G"] == ["2"]
    assert sal["H"] == ["1", "1", "1", "1", "1"]       # el reinicio recupera rango, entradas, lado y resultado


@pytest.mark.skipif(not HAY_GPP, reason="hace falta g++")
def test_ultima_entrada_y_mecha_fuera_del_rango():
    main = r'''
#define EV(k) { stub_ask = stub_bid = g_c[k]; RupEvaluar(k); }
int main()
{
   g_time.resize(40); g_h.resize(40); g_l.resize(40); g_c.resize(40); g_atr.resize(40);
   for(int k = 0; k < 40; k++) { g_time[k] = 1709251200 + 16 * 3600 + 30 * 60 + (k - 3) * 300; g_h[k] = 100.2; g_l[k] = 99.8; g_c[k] = 100.0; g_atr[k] = 0.3; }
   g_psec = 300; g_m = 40; g_gv = "BOT_"; stub_magic_pos = InpMagic; stub_ask = 100.0; stub_bid = 100.0;
   g_h[6] = 101.0;                                                         // mecha fuera del rango con cierre adentro: no es señal
   stub_nord = 0; EV(5); EV(6); printf("A %d\n", stub_nord);
   g_c[33] = 100.6;                                                        // vela de las 12:00 NY (abre 12:00, cierra 12:05): fuera del horario de entrada
   stub_nord = 0; EV(33); printf("B %d\n", stub_nord);
   g_c[32] = 100.6;                                                        // vela de las 11:55 NY (cierra 12:00 en punto): entra (<= ultima entrada)
   stub_nord = 0; EV(32); printf("C %d\n", stub_nord);
   return 0;
}
'''
    exe = _compilar_bot("mitad", _cfg(), main)
    sal = {l.split()[0]: l.split()[1] for l in subprocess.run([exe], capture_output=True, text=True).stdout.strip().split("\n")}
    assert sal == {"A": "0", "B": "0", "C": "1"}


# ----------------------------------------------------------------------------- Londres y Tokio
def _cfg_b(bolsa, **k):
    b = rup.BOLSAS[bolsa]
    return _cfg(bolsa=bolsa, apertura_min=b["apertura"], ultima_min=b["ultima"], cierre_min=b["cierre"], **k)


def test_el_bot_de_otra_bolsa_usa_su_zona_su_magic_y_sus_textos():
    ny, lo, tk = _bot(_cfg_b("ny")), _bot(_cfg_b("londres")), _bot(_cfg_b("tokio"))
    assert "InpRupZona        = 0;" in ny and "InpRupZona        = 1;" in lo and "InpRupZona        = 2;" in tk
    assert "InpRupApertura    = 480" in lo and "InpRupApertura    = 540" in tk
    ms = [int(re.search(r"InpMagic\s+= (\d+);", t).group(1)) for t in (ny, lo, tk)]
    assert len(set(ms)) == 3 and all(800000 <= m < 890000 for m in ms)
    assert "hora de Londres" in lo and "hora de Tokio" in tk and "hora de Tokio" not in lo and "hora de Londres" not in tk
    assert "apertura de Nueva York" not in lo and "apertura de Nueva York" not in tk
    assert " NY\"" not in lo.split("int NyFecha")[1].split("void OnNewBar")[0]       # los avisos del rango dicen la bolsa elegida
    assert "@@" not in lo and lo.count("{") == lo.count("}")


@pytest.mark.skipif(not HAY_GPP, reason="hace falta g++")
@pytest.mark.parametrize("bolsa", ["londres", "tokio"])
@pytest.mark.parametrize("variante", ["mitad", "opuesto_tam"])
@pytest.mark.parametrize("ventana", [("2024-03-18", 40, 7), ("2024-10-14", 40, 9)])     # cambios de hora: Londres 31/3 y 27/10, EE.UU. 10/3 y 3/11 (semanas en que no coinciden)
def test_londres_y_tokio_el_bot_arma_el_dia_y_entra_igual_que_el_backtest(bolsa, variante, ventana):
    desde, n, seed = ventana
    dias_h = pd.bdate_range(desde, periods=n)
    df = _datos(desde, n, seed, sin_vela=(str(dias_h[7].date()),), feriados=(str(dias_h[12].date()),), bolsa=bolsa)
    cfg = _cfg_b(bolsa, **VARIANTES[variante] if variante == "opuesto_tam" else {})
    atr = np.full(len(df), 0.35)
    sp = np.where(np.arange(len(df)) % 3 == 0, 0.02, 0.0)
    dias, ent, s = _esperado(df, cfg, atr, sp)
    sal = _correr(_compilar_bot(f"{bolsa}_{variante}", cfg, _MAIN_SENAL), df, atr, sp)
    dias_bot = {int(l.split()[1]): int(l.split()[2]) for l in sal if l.startswith("DIA")}
    ent_bot = [(int(l.split()[1]), int(l.split()[2]), float(l.split()[3]), float(l.split()[4]), float(l.split()[5])) for l in sal if l.startswith("ENT")]
    assert set(dias_bot) == set(dias) and dias_bot == dias
    assert any(v == 2 for v in dias.values()) and any(v == 1 for v in dias.values())
    assert [(i, lado) for i, lado, *_ in ent_bot] == [(i, lado) for i, lado, _ in ent] and len(ent) >= 5
    for (i, lado, precio, sl, tp), (_, _, dist) in zip(ent_bot, ent):
        assert lado * (precio - sl) == pytest.approx(dist, abs=1e-9)
        assert (tp - precio) * lado == pytest.approx(2.0 * dist, abs=1e-9)


@pytest.mark.skipif(not HAY_GPP, reason="hace falta g++")
@pytest.mark.parametrize("bolsa", ["londres", "tokio"])
def test_londres_y_tokio_el_cierre_forzado_cae_en_la_misma_vela_que_el_backtest(bolsa):
    df = _datos("2024-03-18", 30, 21, bolsa=bolsa)
    cfg = _cfg_b(bolsa)
    atr = np.full(len(df), 0.3)
    sp = np.zeros(len(df))
    s = rup.senales(df, cfg, cfg.ruptura, sp, atr)
    sal = _correr(_compilar_bot(f"{bolsa}_cierre", cfg, _MAIN_CIERRE), df, atr, sp)
    cierres = [int(l.split()[1]) for l in sal if l.startswith("CIERRE")]
    assert cierres == [int(i) for i in np.flatnonzero(s["hcierre"])] and len(cierres) >= 20
