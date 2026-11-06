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
    for frag in ["void OnTimer()", "EventSetTimer(30)", "ar.hour == InpAvisoHoraAR", "InpAvisoHoraAR    = 20", "TimeGMT() - 3 * 3600",
                 "SIN CONEXION", "CONEXION RECUPERADA", "TRADING ALGORITMICO DESACTIVADO", "BOT DETENIDO",
                 "REINICIO:", "CHEQUEO DIARIO OK", "CHEQUEO DIARIO CON PROBLEMAS", '"INICIADO"', '"RECARGADO"', "que + \" pero DETENIDO", "FRENO DIARIO", "FRENO TOTAL", "abierta a", "TP ALCANZADO", "SL ALCANZADO", "cerrada a", "ya esta por debajo del limite de perdida total", "FiltrosTxt", "Senal descartada por los filtros", "Pullback caduco sin ejecutarse"]:
        assert frag in t, frag


def _serie(n=1500, seed=3):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2024-01-01", periods=n, freq="h")
    cl = 2000 + np.cumsum(rng.normal(0, 2, n))
    return idx, cl


@pytest.mark.skipif(not HAY_GPP, reason="sin g++")
@pytest.mark.parametrize("tipo,modo", [("sma", "cruce"), ("sma", "precio"), ("ema", "precio"), ("ema", "cruce")])
def test_senal_sma_y_precio_coincide_con_python(tipo, modo):
    c = _cfg(media_tipo=tipo, modo_senal=modo, ema_corta=9, ema_larga=21, media_unica=30)
    t = _gen(c, "XAUUSD", "H1", 0.1)
    assert "@@" not in t and t.count("{") == t.count("}")
    main = '''int main(){int n;std::cin>>n;g_m=n;g_time.resize(n);g_h.resize(n);g_l.resize(n);g_c.resize(n);g_tv.resize(n);
 for(int i=0;i<n;i++){long long tt;std::cin>>tt>>g_c[i];g_time[i]=tt;g_h[i]=g_c[i];g_l[i]=g_c[i];g_tv[i]=1;}
 if(InpSigMode==1){ if(InpMaType==1)CalcSMA(g_c,g_m,InpMaSingle,g_ef); else CalcEMA(g_c,g_m,InpMaSingle,g_ef); ArrayCopy(g_es,g_ef);}
 else if(InpMaType==1){CalcSMA(g_c,g_m,InpEmaFast,g_ef);CalcSMA(g_c,g_m,InpEmaSlow,g_es);}
 else {CalcEMA(g_c,g_m,InpEmaFast,g_ef);CalcEMA(g_c,g_m,InpEmaSlow,g_es);}
 for(int i=0;i<n;i++)printf("%d\\n",CrossAt(i));}'''
    idx, cl = _serie()
    n = len(cl)
    with tempfile.TemporaryDirectory() as d:
        exe = _compilar(t, main, d)
        inp = f"{n}\n" + "\n".join(f"{int(ts.timestamp())} {float(x)!r}" for ts, x in zip(idx, cl))
        out = subprocess.run([exe], input=inp, capture_output=True, text=True).stdout.split()
    got = np.array([int(x) for x in out])
    med = ind.sma if tipo == "sma" else ind.ema
    if modo == "precio":
        m = med(cl, 30); diff = cl - m; warm = 31
    else:
        diff = med(cl, 9) - med(cl, 21); warm = 22
    dp = np.r_[np.nan, diff[:-1]]
    exp = np.where((diff > 0) & (dp <= 0), 1, np.where((diff < 0) & (dp >= 0), -1, 0))
    exp[:warm] = 0
    assert (got == exp).all()
    assert (got != 0).sum() > 5


def test_magic_ema_cruce_no_cambia_y_sma_distinto():
    a = gb._magic(_cfg(), "XAUUSD")
    assert gb._magic(_cfg(media_tipo="sma"), "XAUUSD") != a
    assert gb._magic(_cfg(modo_senal="precio"), "XAUUSD") != a


def test_cabecera_y_rechazos_modo_precio():
    t = _gen(_cfg(media_tipo="sma", modo_senal="precio", media_unica=50), "XAUUSD", "H1", 0.1)
    assert "precio cruza la SMA 50" in t and "InpMaSingle       = 50" in t and "InpMaType         = 1" in t
    with pytest.raises(ValueError):
        _gen(_cfg(media_tipo="sma", modo_senal="cruce", ema_corta=30, ema_larga=20), "X", "H1", 0.1)


def test_salida_por_senal_en_la_plantilla():
    t = _gen(_cfg(salida_modo="senal", media_tipo="sma", modo_senal="precio", media_unica=200), "XAUUSD", "M5", 0.1)
    assert "@@" not in t and t.count("{") == t.count("}")
    assert "InpExitSignal     = 1" in t and "salida por cambio de lado (sin TP)" in t and "SalidaPorSenal" in t
    t0 = _gen(_cfg(), "XAUUSD", "M5", 0.1)
    assert "InpExitSignal     = 0" in t0 and "RR 2.0 " in t0
    assert gb._magic(_cfg(salida_modo="senal"), "XAUUSD") != gb._magic(_cfg(), "XAUUSD")


@pytest.mark.skipif(not HAY_GPP, reason="sin g++")
@pytest.mark.parametrize("pb", [False, True])
@pytest.mark.parametrize("modo,tipo", [("precio", "sma"), ("cruce", "ema")])
def test_salida_por_senal_coincide_con_el_backtester(pb, modo, tipo):
    idx = pd.date_range("2024-01-01", periods=1200, freq="5min")
    rng = np.random.default_rng(11)
    c = 2000 + np.cumsum(rng.normal(0, 1.5, 1200))
    df = pd.DataFrame({"Open": c, "High": c + 1, "Low": c - 1, "Close": c, "Volume": 1.0}, index=idx)
    cfg = _cfg(media_tipo=tipo, modo_senal=modo, media_unica=40, ema_corta=9, ema_larga=21, salida_modo="senal",
               sl_valor=4.0, spread="ninguno", pullback_activo=pb, pullback_pct=50, pullback_velas=6)
    tr = eng.ejecutar(eng.preparar(df, cfg), cfg).trades
    tr = tr[tr["motivo"] == "senal"]
    assert len(tr) >= 3
    t = _gen(cfg, "XAUUSD", "M5", 0.1)
    main = '''int main(){int n;std::cin>>n;std::vector<double> cc(n);std::vector<long long> tt(n);
 for(int i=0;i<n;i++)std::cin>>tt[i]>>cc[i];
 g_psec=300;int q;std::cin>>q;
 while(q--){int side,m,pbk;long long ab;std::cin>>side>>ab>>pbk>>m;
  g_m=m;g_time.assign(tt.begin(),tt.begin()+m);g_c.assign(cc.begin(),cc.begin()+m);
  if(InpSigMode==1){ if(InpMaType==1)CalcSMA(g_c,g_m,InpMaSingle,g_ef); else CalcEMA(g_c,g_m,InpMaSingle,g_ef); g_es=g_ef;}
  else {CalcEMA(g_c,g_m,InpEmaFast,g_ef);CalcEMA(g_c,g_m,InpEmaSlow,g_es);}
  printf("%d\\n",SalidaPorSenal(side,ab,pbk==1)?1:0);}}'''
    qs = []
    for _, f in tr.iterrows():
        k, j = int(f["i"]), int(f["salida"])
        ab = int(idx[k].timestamp()) + (60 if pb else 5 * 60)       # pullback: se llena dentro de la vela k; mercado: abre la vela siguiente
        if not pb:
            ab = int(idx[k + 1].timestamp()) + 1
        for m in (j, j + 1):
            qs.append((int(f["lado"]), ab, int(pb), m))
    with tempfile.TemporaryDirectory() as d:
        exe = _compilar(t, main, d)
        inp = f"{len(c)}\n" + "\n".join(f"{int(ts.timestamp())} {float(x)!r}" for ts, x in zip(idx, c)) \
              + f"\n{len(qs)}\n" + "\n".join(" ".join(map(str, q)) for q in qs)
        out = subprocess.run([exe], input=inp, capture_output=True, text=True).stdout.split()
    got = [int(x) for x in out]
    assert got == [0, 1] * len(tr)


# ---------------------------------------------------------------- reglas de cuenta en el bot
def test_reglas_de_cuenta_en_la_plantilla():
    c = _cfg(capital=25000.0, usd_por_unidad=10.0, perd_dia_pct=5.0, perd_dia_modo="estatico", perd_tot_pct=10.0,
             perd_tot_modo="trailing", colchon_pct=1.0, proteger_sl=False, riesgo_op_activo=True, riesgo_op_pct=0.5,
             pausa_activa=True, pausa_min=45.0, pausa_gan_activa=True, pausa_gan_min=20.0,
             pausa_sentido="contrario", pausa_gan_sentido="mismo", comision_op_usd=3.5)
    t = _gen(c, "XAUUSD", "M5", 0.1)
    assert "@@" not in t and t.count("{") == t.count("}")
    for frag in ["InpMaxDailyLossPct = 4.0", "InpMaxTotalLossPct = 9.0", "InpInitialBalance = 25000.0", "InpDailyMode      = 1",
                 "InpTotalMode      = 1", "InpProtectSL      = false", "InpRiskOn         = true", "InpRiskPct        = 0.5",
                 "InpPauseOn        = true", "InpPauseMin       = 45.0", "InpCommissionUsd  = 3.5",
                 "InpPauseWinOn     = true", "InpPauseWinMin    = 20.0", "if(PauseWinBlocks(i, cr))", "if(PauseBlocks(i, cr))", "LASTWIN_B", "LASTLOSS_S",
                 "InpPauseDir       = 2", "InpPauseWinDir    = 1"]:
        assert frag in t, frag
    sin = _gen(_cfg(), "XAUUSD", "M5", 0.1, capital=25000.0)               # sin capital en la config: limites de siempre
    assert "InpMaxDailyLossPct = 4.0" in sin and "InpMaxTotalLossPct = 8.0" in sin and "InpInitialBalance = 25000.0" in sin
    libre = _gen(_cfg(capital=25000.0, perd_dia_pct=0.0, perd_tot_pct=0.0), "XAUUSD", "M5", 0.1)
    assert "InpMaxDailyLossPct = 0.0" in libre and "InpMaxTotalLossPct = 0.0" in libre


@pytest.mark.skipif(not HAY_GPP, reason="sin g++")
@pytest.mark.parametrize("dia,tot", [("trailing", "estatico"), ("estatico", "trailing"), ("trailing", "trailing")])
def test_pisos_y_dia_cet_coinciden_con_el_backtester(dia, tot):
    c = _cfg(capital=25000.0, usd_por_unidad=10.0, perd_dia_pct=5.0, perd_dia_modo=dia, perd_tot_pct=10.0, perd_tot_modo=tot,
             colchon_pct=1.0, riesgo_op_activo=True, riesgo_op_pct=0.5, pausa_activa=True, pausa_min=45.0,
             servidor_offset_horas=2.0)
    t = _gen(c, "XAUUSD", "M5", 0.1)
    main = '''int main(){int q;std::cin>>q;g_initBal=InpInitialBalance;
 while(q--){double bd,pk;long long u;std::cin>>bd>>pk>>u;g_dayBal=bd;g_peak=pk;
  printf("%.6f %.6f %d\\n",FloorDay(),FloorTotal(),DayKeyCET(u));}
 g_time.assign(3,0);g_time[0]=1000;g_time[1]=1000+60*30;g_time[2]=1000+60*60;g_lastLoss[0]=1000;
 printf("%d %d %d\\n",PauseBlocks(0,1)?1:0,PauseBlocks(1,1)?1:0,PauseBlocks(2,1)?1:0);}'''
    casos = [(25000.0, 25000.0, "2026-01-15 12:00"), (25800.0, 26500.0, "2026-03-29 00:30"), (24000.0, 25200.0, "2026-10-25 01:30"),
             (25300.0, 25300.0, "2026-11-03 23:30"), (25000.0, 25900.0, "2026-07-01 22:30")]
    entrada = f"{len(casos)}\n" + "\n".join(f"{bd} {pk} {int(pd.Timestamp(ts).timestamp())}" for bd, pk, ts in casos)
    with tempfile.TemporaryDirectory() as d:
        exe = _compilar(t, main, d)
        out = subprocess.run([exe], input=entrada, capture_output=True, text=True).stdout.strip().split("\n")
    for (bd, pk, ts), ln in zip(casos, out):
        fd, ft, key = ln.split()
        p_dia, p_tot = 4.0, 9.0
        esp_d = bd * (1 - p_dia / 100) if dia == "trailing" else bd - p_dia / 100 * 25000.0
        esp_t = (pk if tot == "trailing" else 25000.0) * (1 - p_tot / 100)
        assert abs(float(fd) - esp_d) < 1e-3 and abs(float(ft) - esp_t) < 1e-3
        # el dia del bot = dia CET que calcula el backtester al pasar un instante UTC (servidor UTC+0 para esta prueba)
        idx = pd.DatetimeIndex([pd.Timestamp(ts)])
        esperado = int(eng.claves_dia(idx, eng.Config(servidor_offset_horas=0.0, servidor_dst_eeuu=False))[0])
        y, m, dd = 1970, 1, 1
        from datetime import date as _d
        k = _d.fromordinal(_d(1970, 1, 1).toordinal() + esperado)
        assert int(key) == k.year * 10000 + k.month * 100 + k.day
    assert out[-1] == "1 1 0"                                          # 0 y 30 min dentro de 45; 60 min ya no


def test_filtro_de_rango_en_la_plantilla():
    t = _gen(_cfg(rango_activo=True, rango_ventana=25, rango_min=0.35), "XAUUSD", "M5", 0.1)
    assert re.search(r"InpRangeOn\s+= true;", t) and re.search(r"InpRangeWindow\s+= 25;", t) and re.search(r"InpRangeMin\s+= 0\.35;", t)
    assert "OkRange" in t and "Rango" in t
    t0 = _gen(_cfg(), "XAUUSD", "M5", 0.1)
    assert re.search(r"InpRangeOn\s+= false;", t0)


@pytest.mark.skipif(not HAY_GPP, reason="sin g++")
@pytest.mark.parametrize("ventana,minimo", [(20, 0.30), (7, 0.5), (50, 0.15)])
def test_filtro_de_rango_coincide_con_python(ventana, minimo):
    c = _cfg(rango_activo=True, rango_ventana=ventana, rango_min=minimo)
    t = _gen(c, "XAUUSD", "M5", 0.1)
    main = '''int main(){int n;std::cin>>n;g_m=n;g_c.resize(n);
 for(int i=0;i<n;i++){std::cin>>g_c[i];}
 CalcEfficiency(InpRangeWindow,g_er);
 for(int i=0;i<n;i++)printf("%.12g %d\\n",g_er[i],OkRange(i)?1:0);}'''
    rng = np.random.default_rng(11)
    n = 3000
    cl = 2000 + np.cumsum(rng.normal(0, 2, n))
    cl[1000:1100] = cl[1000]                          # tramo quieto: recorrido 0
    with tempfile.TemporaryDirectory() as d:
        exe = _compilar(t, main, d)
        inp = f"{n}\n" + "\n".join(repr(float(x)) for x in cl)
        out = subprocess.run([exe], input=inp, capture_output=True, text=True).stdout.split("\n")
    M = np.array([[float(x) for x in ln.split()] for ln in out if ln.strip()])
    er = ind.eficiencia(cl, ventana)
    mq = np.where(M[:, 0] < -1e299, np.nan, M[:, 0])
    assert np.allclose(mq, er, rtol=1e-7, atol=1e-9, equal_nan=True)
    esperado = np.where(np.isnan(er), 0, (er >= minimo).astype(int))
    dudosos = np.abs(er - minimo) < 1e-9                  # justo en el umbral: la suma corrida puede diferir en el ultimo decimal
    assert np.array_equal(M[~dudosos, 1].astype(int), esperado[~dudosos])


def test_sl_a_la_media_en_la_plantilla():
    t = _gen(_cfg(sl_modo="ema", sl_valor=2.5, sl_ema_ref="corta"), "XAUUSD", "M5", 0.1)
    assert re.search(r"InpSLMode\s+= BOT_SL_EMA;", t) and re.search(r"InpSLValue\s+= 2\.5;", t) and re.search(r"InpSlEmaRef\s+= 0;", t)
    assert "BOT_SL_EMA = 3" in t and "double SlLevel(" in t and "// SL: fijo en la EMA corta (" in t
    t2 = _gen(_cfg(sl_modo="ema", sl_valor=1.0, sl_ema_ref="larga"), "XAUUSD", "M5", 0.1)
    assert re.search(r"InpSlEmaRef\s+= 1;", t2)
    assert _magic_distinto(_cfg(sl_modo="ema", sl_valor=1.0, sl_ema_ref="larga"), _cfg(sl_modo="ema", sl_valor=1.0, sl_ema_ref="corta"))
    # los modos de siempre no cambian: ATR, %, US$
    assert re.search(r"InpSLMode\s+= BOT_SL_ATR;", _gen(_cfg(), "XAUUSD", "M5", 0.1))


def _magic_distinto(a, b):
    return gb._magic(a, "XAUUSD") != gb._magic(b, "XAUUSD")


@pytest.mark.skipif(not HAY_GPP, reason="sin g++")
@pytest.mark.parametrize("ref", ["corta", "larga"])
@pytest.mark.parametrize("modo,tipo", [("cruce", "ema"), ("cruce", "sma"), ("precio", "ema")])
def test_sl_a_la_media_coincide_con_python(ref, modo, tipo):
    c = _cfg(media_tipo=tipo, modo_senal=modo, ema_corta=9, ema_larga=21, media_unica=30, sl_modo="ema", sl_valor=2.75, sl_ema_ref=ref)
    t = _gen(c, "XAUUSD", "M5", 0.1)
    main = '''int main(){int n;std::cin>>n;g_m=n;g_c.resize(n);g_h.resize(n);g_l.resize(n);g_tv.resize(n);g_time.resize(n);
 for(int i=0;i<n;i++){std::cin>>g_c[i];}
 g_ef.resize(n);g_es.resize(n);
 if(InpSigMode==1){ if(InpMaType==1) CalcSMA(g_c,g_m,InpMaSingle,g_ef); else CalcEMA(g_c,g_m,InpMaSingle,g_ef); ArrayCopy(g_es,g_ef); }
 else if(InpMaType==1){ CalcSMA(g_c,g_m,InpEmaFast,g_ef); CalcSMA(g_c,g_m,InpEmaSlow,g_es); }
 else { CalcEMA(g_c,g_m,InpEmaFast,g_ef); CalcEMA(g_c,g_m,InpEmaSlow,g_es); }
 for(int i=0;i<n;i++)printf("%.12g %.12g %.12g %.12g\\n",SlLevel(i,1),SlLevel(i,-1),SlDistance(i,1,g_c[i]+0.3),SlDistance(i,-1,g_c[i]));}'''
    rng = np.random.default_rng(21)
    n = 800
    cl = 2000 + np.cumsum(rng.normal(0, 2, n))
    with tempfile.TemporaryDirectory() as d:
        exe = _compilar(t, main, d)
        inp = f"{n}\n" + "\n".join(repr(float(x)) for x in cl)
        out = subprocess.run([exe], input=inp, capture_output=True, text=True).stdout.split("\n")
    M = np.array([[float(x) for x in ln.split()] for ln in out if ln.strip()])
    media_f = (ind.sma if tipo == "sma" else ind.ema)
    if modo == "precio":
        ref_arr = media_f(cl, 30)
    else:
        ref_arr = media_f(cl, 9 if ref == "corta" else 21)
    ok = ~np.isnan(ref_arr)                       # sin dato (primeras velas de una SMA): el bot devuelve 0 y no opera
    assert (~ok).sum() < 60 and (M[~ok, 0] == 0).all() and (M[~ok, 2] == 0).all() and (M[~ok, 3] == 0).all()
    assert np.allclose(M[ok, 0], ref_arr[ok] - 2.75) and np.allclose(M[ok, 1], ref_arr[ok] + 2.75)
    assert np.allclose(M[ok, 2], (cl[ok] + 0.3) - (ref_arr[ok] - 2.75)) and np.allclose(M[ok, 3], -(cl[ok] - (ref_arr[ok] + 2.75)))
    # y es el mismo nivel que usa el backtester
    P = eng.preparar(pd.DataFrame({"Open": cl, "High": cl + 1, "Low": cl - 1, "Close": cl, "Volume": 1.0},
                                  index=pd.date_range("2024-01-01", periods=n, freq="5min")), c)
    assert np.allclose(P.sl_ref, ref_arr, equal_nan=True)


def test_sl_en_el_cruce_usa_la_referencia_2():
    c = _cfg(sl_modo="ema", sl_valor=2.0, sl_ema_ref="cruce")
    src = _gen(c, "XAUUSD", "H1", 0.1)
    assert "InpSlEmaRef       = 2;" in src
    assert "0.5 * (g_ef[i] + g_es[i])" in src
    assert "cruce de las EMA 13/34" in src
    assert "InpSlEmaRef       = 1;" in _gen(_cfg(sl_modo="ema", sl_valor=2.0, sl_ema_ref="larga"), "XAUUSD", "H1", 0.1)


def test_sl_en_porcentaje_del_nivel():
    src = _gen(_cfg(sl_modo="ema", sl_valor=0.15, sl_ema_pct=True, sl_ema_ref="cruce"), "XAUUSD", "H1", 0.1)
    assert "InpSlEmaPct       = true;" in src
    assert "MathAbs(ref) * InpSLValue / 100.0" in src
    assert "0.15 % del nivel" in src
    assert "InpSlEmaPct       = false;" in _gen(_cfg(sl_modo="ema", sl_valor=2.0, sl_ema_ref="cruce"), "XAUUSD", "H1", 0.1)


def _prueba_pausa(cfg_k, ult_buy, ult_sell, es_ganancia):
    """Compila la plantilla y devuelve (bloquea compra, bloquea venta) para la senal de la vela 0, con la ultima ganadora/perdedora."""
    t = _gen(_cfg(**cfg_k), "XAUUSD", "M5", 0.1)
    arr = "g_lastWin" if es_ganancia else "g_lastLoss"
    fn = "PauseWinBlocks" if es_ganancia else "PauseBlocks"
    main = f'''int main(){{ g_time.assign(2,0);g_time[0]=1000+60*10;g_time[1]=1000+60*90;
 {arr}[0]={ult_buy};{arr}[1]={ult_sell};
 printf("%d %d %d %d\\n",{fn}(0,1)?1:0,{fn}(0,-1)?1:0,{fn}(1,1)?1:0,{fn}(1,-1)?1:0);}}'''
    with tempfile.TemporaryDirectory() as d:
        exe = _compilar(t, main, d)
        return subprocess.run([exe], capture_output=True, text=True).stdout.strip()


def test_sentido_de_las_pausas_en_el_bot():
    # una compra ganadora cerro en t=1000 (la venta nunca); la senal esta 10 min despues (vela 0) y 90 min despues (vela 1); pausa de 30 min
    k = dict(capital=10000.0, usd_por_unidad=10.0, pausa_gan_activa=True, pausa_gan_min=30.0)
    assert _prueba_pausa({**k, "pausa_gan_sentido": "mismo"}, 1000, 0, True) == "1 0 0 0"        # frena la compra, no la venta
    assert _prueba_pausa({**k, "pausa_gan_sentido": "contrario"}, 1000, 0, True) == "0 1 0 0"    # frena la venta, no la compra
    assert _prueba_pausa({**k, "pausa_gan_sentido": "ambos"}, 1000, 0, True) == "1 1 0 0"
    # pausa tras perdida, mismo reloj: una venta perdedora cerro en t=1000
    kp = dict(capital=10000.0, usd_por_unidad=10.0, pausa_activa=True, pausa_min=30.0)
    assert _prueba_pausa({**kp, "pausa_sentido": "contrario"}, 0, 1000, False) == "1 0 0 0"      # venta perdedora frena la compra
    assert _prueba_pausa({**kp, "pausa_sentido": "mismo"}, 0, 1000, False) == "0 1 0 0"


def test_retroceso_tras_ganancia_en_el_bot():
    # compra ganadora cerro en t=1000 a 120 con recorrido 20, 50% -> nivel 110. La senal esta en t=1600 (10 min) o t=6400 (90 min)
    k = dict(capital=10000.0, usd_por_unidad=10.0, pausa_gan_retroceso_activo=True, pausa_gan_retroceso_pct=50.0)

    def prueba(extra, px):
        t = _gen(_cfg(**{**k, **extra}), "XAUUSD", "M5", 0.1)
        main = f'''int main(){{ g_time.assign(2,0);g_time[0]=1000+60*10;g_time[1]=1000+3600*30;
 g_lastWin[0]=1000; g_winRef[0]=120.0; g_winDist[0]=20.0; g_lastWin[1]=0;
 printf("%d %d %d\\n",WinRetraceBlocks(0,1,{px})?1:0,WinRetraceBlocks(0,-1,{px})?1:0,WinRetraceBlocks(1,1,{px})?1:0);}}'''
        with tempfile.TemporaryDirectory() as d:
            return subprocess.run([_compilar(t, main, d)], capture_output=True, text=True).stdout.strip()
    assert prueba({}, 118.0) == "1 0 1"                    # arriba del nivel: bloquea la compra; la venta no tiene ganadora previa
    assert prueba({}, 105.0) == "0 0 0"                    # ya retrocedio
    assert prueba({"pausa_gan_vence": "horas", "pausa_gan_vence_h": 24.0}, 118.0) == "1 0 0"   # a las 30 h ya vencio
    assert prueba({"pausa_gan_retroceso_activo": False}, 118.0) == "0 0 0"
