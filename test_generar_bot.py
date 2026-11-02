"""Pruebas del generador del EA. Si hay g++, tambien compila la plantilla contra un stub de MQL5
y compara los indicadores y las sesiones del EA con los de Python."""
import os, re, shutil, subprocess, sys, tempfile
import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import engine as eng
import generar_bot as gb
import indicators as ind
import sessions as ses

AQUI = os.path.dirname(os.path.abspath(__file__))
HAY_GPP = shutil.which("g++") is not None


VD = {"nivel": "ok", "titulo": "Valida para intentar"}


def _cfg(**k):
    return eng.Config(**k)


def _gen(c, sim, tf, lotes, **k):
    k.setdefault("veredicto", VD)
    return gb.generar_mq5(c, sim, tf, lotes, **k)


def test_sin_campos_pendientes_y_llaves_balanceadas():
    t = _gen(_cfg(sesion_activo=True, servidor_offset_horas=2.0, pullback_activo=True, vwap_activo=True,
                            adx_activo=True, adx_max=40.0, atr_activo=True, atr_min=0.1), "XAUUSD", "H1", 0.1)
    assert "@@" not in t
    assert t.count("{") == t.count("}")
    assert "InpEmaFast        = 13" in t and "InpEmaSlow        = 34" in t


def test_valores_y_enums():
    t = _gen(_cfg(ema_corta=8, ema_larga=21, direccion="cortos", rr=3.0, sl_modo="pct", sl_valor=0.5,
                            pullback_activo=True, pullback_pct=40, pullback_ema="larga", pullback_velas=7,
                            sesiones=("Londres",), sesion_activo=True, servidor_offset_horas=3.0,
                            servidor_dst_eeuu=False), "EURUSD", "M15", 0.25)
    for frag in ["= 8;", "= 21;", "BOT_CORTOS", "BOT_SL_PCT", "PERIOD_M15", "= true;      // Entrar en pullback",
                 "BOT_PB_LARGA", "= 7;", "InpSesLondres     = true", "InpSesTokio       = false",
                 "InpServerOffset   = 3.0", "InpServerDST      = false", "InpLots           = 0.25"]:
        assert frag in t, frag


def test_sl_en_dolares_exige_monto_y_lo_pasa():
    c = _cfg(sl_modo="precio", sl_valor=2.0)
    with pytest.raises(ValueError):
        _gen(c, "XAUUSD", "H1", 0.1)
    t = _gen(c, "XAUUSD", "H1", 0.1, sl_usd=150.0)
    assert "BOT_SL_USD" in t and "InpSLUsd          = 150.0" in t


@pytest.mark.parametrize("nivel", ["nc", "pierde", "sin", "dudosa"])
def test_veredicto_negativo_no_genera(nivel):
    with pytest.raises(ValueError):
        gb.generar_mq5(_cfg(), "XAUUSD", "H1", 0.1, veredicto={"nivel": nivel, "titulo": "x"})


def test_sin_veredicto_o_sin_temporalidad_no_genera():
    with pytest.raises(ValueError):
        gb.generar_mq5(_cfg(), "XAUUSD", "H1", 0.1)
    with pytest.raises(ValueError):
        gb.generar_mq5(_cfg(), "XAUUSD", "", 0.1, veredicto=VD)


def test_parametros_fijos_y_compuertas():
    t = _gen(_cfg(), "XAUUSD", "H1", 0.1, capital=50000, limite_pct=10)
    assert not re.search(r"^input ", t, flags=re.M)         # nada editable desde MT5
    assert "InpVerdictOK      = true" in t
    assert "InpInitialBalance = 50000.0" in t and "InpMaxTotalLossPct = 8.0" in t
    assert "RECHAZADO" in t


def test_nombre_de_archivo():
    assert gb.nombre_archivo("XAUUSD", "H1") == "Bot_XAUUSD_H1.mq5"
    assert gb.nombre_archivo("SINT1", "") == "Bot_SINT1.mq5"
    assert gb.nombre_archivo("US 500.cash", "M5") == "Bot_US500cash_M5.mq5"


def test_parametros_invalidos():
    with pytest.raises(ValueError):
        _gen(_cfg(ema_corta=30, ema_larga=10), "X", "H1", 0.1)
    with pytest.raises(ValueError):
        _gen(_cfg(), "X", "H1", 0)


def _a_cpp(t):
    t = re.sub(r"const double &(\w+)\[\]", r"const Arr &\1", t)
    t = re.sub(r"double &(\w+)\[\]", r"Arr &\1", t)
    t = t.replace("datetime g_time[];", "ArrT g_time;")
    t = re.sub(r"^double\s+(g_\w+\[\].*)$", lambda m: "Arr " + re.sub(r"\[\]", "", m.group(1)).replace("double ", ""),
               t, flags=re.M)
    t = re.sub(r"\bdouble ((?:\w+\[\](?:, )?)+);", lambda m: "Arr " + re.sub(r"\[\]", "", m.group(1)) + ";", t)
    t = t.replace("MqlRates r[];", "std::vector<MqlRates> r;").replace("ulong", "unsigned long")
    return re.sub(r"^#property.*", "", t, flags=re.M)


def _compilar(t, main, d):
    shutil.copy(os.path.join(AQUI, "mql_stub.h"), os.path.join(d, "mql.h"))
    with open(os.path.join(d, "b.cpp"), "w") as f:
        f.write('#include "mql.h"\n' + _a_cpp(t) + main)
    r = subprocess.run(["g++", "-std=c++17", "-O1", "-o", os.path.join(d, "b"), os.path.join(d, "b.cpp")],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[:2000]
    return os.path.join(d, "b")


@pytest.mark.skipif(not HAY_GPP, reason="sin g++")
def test_compila_y_los_indicadores_coinciden():
    c = _cfg(ema_corta=9, ema_larga=21, sma_activo=True, sma_periodo=50, vwap_activo=True, adx_activo=True,
             adx_periodo=10, atr_activo=True, atr_rel_n=20, atr_periodo=12, sesion_activo=True,
             servidor_offset_horas=2.0)
    t = _gen(c, "XAUUSD", "H1", 0.1)
    main = '''int main(){int n;std::cin>>n;g_m=n;g_time.resize(n);g_h.resize(n);g_l.resize(n);g_c.resize(n);g_tv.resize(n);
 for(int i=0;i<n;i++){long long tt;std::cin>>tt>>g_h[i]>>g_l[i]>>g_c[i]>>g_tv[i];g_time[i]=tt;}
 CalcEMA(g_c,g_m,InpEmaFast,g_ef);CalcEMA(g_c,g_m,InpEmaSlow,g_es);Arr tr;CalcTR(tr);CalcWilder(tr,g_m,InpAtrPeriod,g_atr);
 CalcSMA(g_c,g_m,InpSmaPeriod,g_sma);CalcADX(InpAdxPeriod,g_adx);CalcVWAP(PeriodSeconds());CalcRollingMean(g_atr,g_m,InpAtrRelN,g_atrm);
 for(int i=0;i<n;i++)printf("%.12g %.12g %.12g %.12g %.12g %.12g %.12g %.12g\\n",g_ef[i],g_es[i],g_atr[i],g_sma[i],g_adx[i],g_vwap[i],g_vmin[i],g_atrm[i]);}'''
    idx = pd.date_range("2024-01-01", "2024-09-01", freq="h")
    idx = idx[idx.dayofweek < 5]
    rng = np.random.default_rng(1)
    n = len(idx)
    cl = 2000 + np.cumsum(rng.normal(0, 2, n))
    h, l = cl + rng.uniform(0, 3, n), cl - rng.uniform(0, 3, n)
    v = rng.integers(0, 500, n).astype(float)
    with tempfile.TemporaryDirectory() as d:
        exe = _compilar(t, main, d)
        inp = f"{n}\n" + "\n".join(f"{int(ts.timestamp())} {float(a)!r} {float(b)!r} {float(cc)!r} {float(vv)!r}" for ts, a, b, cc, vv in zip(idx, h, l, cl, v))
        out = subprocess.run([exe], input=inp, capture_output=True, text=True).stdout.split("\n")
    M = np.array([[float(x) for x in ln.split()] for ln in out if ln.strip()])
    M = np.where(M < -1e299, np.nan, M)
    vw, _ = ind.vwap_diario(h, l, cl, v, idx.normalize().to_numpy())
    esperado = [ind.ema(cl, 9), ind.ema(cl, 21), ind.atr_wilder(h, l, cl, 12), ind.sma(cl, 50),
                ind.adx_wilder(h, l, cl, 10)[0], vw,
                np.asarray(((idx - idx.normalize()) + pd.Timedelta(hours=1)) / pd.Timedelta(minutes=1), float),
                pd.Series(ind.atr_wilder(h, l, cl, 12)).rolling(20).mean().to_numpy()]
    for k, e in enumerate(esperado):
        assert np.allclose(M[:, k], e, rtol=1e-9, atol=1e-8, equal_nan=True), k


@pytest.mark.skipif(not HAY_GPP, reason="sin g++")
@pytest.mark.parametrize("sess,off,dst", [(("Tokio", "Londres", "Nueva York"), 2.0, True), (("Londres",), 3.0, False),
                                          (("Nueva York",), 2.0, True), (("Tokio",), 0.0, False)])
def test_sesiones_coinciden(sess, off, dst):
    c = _cfg(sesion_activo=True, sesiones=sess, servidor_offset_horas=off, servidor_dst_eeuu=dst)
    t = _gen(c, "X", "H1", 0.1)
    main = 'int main(){int n;std::cin>>n;for(int i=0;i<n;i++){long long tt;std::cin>>tt;printf("%d\\n",(int)InSession(tt));}}'
    idx = pd.date_range("2024-01-01", "2025-06-30", freq="30min")
    idx = idx[idx.dayofweek < 5]
    with tempfile.TemporaryDirectory() as d:
        exe = _compilar(t, main, d)
        o = subprocess.run([exe], input=f"{len(idx)}\n" + "\n".join(str(int(x.timestamp())) for x in idx),
                           capture_output=True, text=True).stdout.split()
    esperado = ses.mascara_sesiones(ses.servidor_a_utc(idx, off, dst), sess)
    assert (esperado == (np.array(o) == "1")).all()


def test_avisos_de_vigilancia_presentes():
    t = _gen(_cfg(), "XAUUSD", "H1", 0.1)
    for frag in ["void OnTimer()", "EventSetTimer(30)", "ar.hour == 19", "TimeGMT() - 3 * 3600",
                 "SIN CONEXION", "CONEXION RECUPERADA", "TRADING ALGORITMICO DESACTIVADO", "BOT DETENIDO",
                 "REINICIO:", "ACTIVO (", "INICIADO.", "FRENO DIARIO", "FRENO TOTAL", "abierta a", "TP ALCANZADO", "SL ALCANZADO", "cerrada a", "ya esta por debajo del limite de perdida total"]:
        assert frag in t, frag
