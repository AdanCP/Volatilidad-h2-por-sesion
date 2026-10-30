"""Tests de la etapa (a). Ejecutar:  python test_backtester.py   (o: pytest)"""
import os
import sys
import tempfile
from dataclasses import replace

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import data as dt
import engine as eng
import indicators as ind
import metrics as met
import sessions as ses

try:
    import cruce_minimo as cm
except ImportError:
    cm = None


def P_manual(h, l, sp=None, c0=100.0, atr=2.0, mult=1.0):
    n = len(h)
    return eng.Preparado(np.asarray(h, float), np.asarray(l, float), np.full(n, c0),
                         np.zeros(n) if sp is None else np.asarray(sp, float),
                         np.full(n, atr), np.full(n, atr * mult),
                         pd.date_range("2024-01-01", periods=n, freq="h"), [], 0.0)


def sim(P, sig, rr=2.0, extra=0.0):
    return eng.simular(P, sig, rr, extra)


# ------------------------------------------------------------- simulacion
def test_largo_tp_y_sl():
    assert sim(P_manual([100, 101, 104.5], [100, 99, 100]), [(0, 1)])[0].iloc[0]["res"] == "TP"
    assert sim(P_manual([100, 101, 102], [100, 99, 97.5]), [(0, 1)])[0].iloc[0]["res"] == "SL"


def test_corto_tp_y_sl():
    assert sim(P_manual([100, 101, 101], [100, 99, 95.5]), [(0, -1)])[0].iloc[0]["res"] == "TP"
    assert sim(P_manual([100, 101, 102.5], [100, 99, 99]), [(0, -1)])[0].iloc[0]["res"] == "SL"


def test_vela_ambigua_es_sl():
    t = sim(P_manual([100, 105], [100, 97]), [(0, 1)])[0].iloc[0]
    assert t["res"] == "SL" and t["amb"]


def test_abierta_no_cuenta():
    t, _ = sim(P_manual([100, 101, 101], [100, 99.5, 99.5]), [(0, 1)])
    r = met.resumen(t, 2.0)
    assert t.iloc[0]["res"] == "ABIERTA" and r["resueltas"] == 0 and r["abiertas"] == 1


def test_spread_largo_y_corto():
    a = P_manual([100, 101, 104.2, 104.2], [100, 99, 100, 100], sp=[0.5] * 4)
    assert sim(replace(a, sp=np.zeros(4)), [(0, 1)])[0].iloc[0]["res"] == "TP"
    assert sim(a, [(0, 1)])[0].iloc[0]["res"] == "ABIERTA"
    b = P_manual([100, 101, 101], [100, 99, 95.8], sp=[0.5] * 3)
    assert sim(replace(b, sp=np.zeros(3)), [(0, -1)])[0].iloc[0]["res"] == "TP"
    assert sim(b, [(0, -1)])[0].iloc[0]["res"] == "ABIERTA"


def test_una_operacion_a_la_vez_e_ignoradas():
    a = P_manual([100, 101, 101, 104.5, 100, 100, 104.5, 104.5], [100, 99.5, 99.5, 100, 100, 99.5, 100, 100])
    t, ign = sim(a, [(0, 1), (1, 1), (4, 1)])
    assert list(t["i"]) == [0, 4] and ign == 1


def test_costo_extra_resta_r():
    a = P_manual([100, 101, 104.5], [100, 99, 100])
    assert abs(sim(a, [(0, 1)], extra=0.4)[0].iloc[0]["R"] - (2.0 - 0.4 / 2.0)) < 1e-9


# ------------------------------------------------------------ indicadores
def test_ema_sma_contra_calculo_manual():
    x = np.random.default_rng(0).normal(100, 3, 200)
    e = np.empty_like(x); e[0] = x[0]; k = 2 / 11
    for i in range(1, len(x)):
        e[i] = e[i - 1] + k * (x[i] - e[i - 1])
    assert np.allclose(ind.ema(x, 10), e)
    s = ind.sma(x, 20)
    assert np.isnan(s[18]) and abs(s[19] - x[:20].mean()) < 1e-12 and abs(s[50] - x[31:51].mean()) < 1e-12


def _wilder(x, n):
    o = np.empty_like(x); o[0] = x[0]
    for i in range(1, len(x)):
        o[i] = o[i - 1] + (x[i] - o[i - 1]) / n
    return o


def test_atr_y_adx_contra_referencia_independiente():
    r = np.random.default_rng(1)
    c = 2000 + np.cumsum(r.normal(0, 2, 400))
    h, l = c + np.abs(r.normal(0, 1, 400)), c - np.abs(r.normal(0, 1, 400))
    pc = np.r_[c[0], c[:-1]]
    tr = np.maximum.reduce([h - l, np.abs(h - pc), np.abs(l - pc)])
    assert np.allclose(ind.atr_wilder(h, l, c, 14), _wilder(tr, 14))
    up, dn = np.r_[0, np.diff(h)], np.r_[0, -np.diff(l)]
    mas, menos = np.where((up > dn) & (up > 0), up, 0.0), np.where((dn > up) & (dn > 0), dn, 0.0)
    pdi, ndi = 100 * _wilder(mas, 14) / _wilder(tr, 14), 100 * _wilder(menos, 14) / _wilder(tr, 14)
    with np.errstate(divide="ignore", invalid="ignore"):
        dx = 100 * np.abs(pdi - ndi) / (pdi + ndi)
    adx, p2, n2 = ind.adx_wilder(h, l, c, 14)
    assert np.allclose(adx, _wilder(np.nan_to_num(dx), 14)) and np.allclose(p2, pdi) and np.allclose(n2, ndi)


def test_adx_alto_en_tendencia_y_bajo_en_rango():
    t = np.arange(300, dtype=float)
    tend = 100 + t
    adx_t = ind.adx_wilder(tend + 0.5, tend - 0.5, tend, 14)[0]
    rango = 100 + np.sin(t / 3) * 2
    adx_r = ind.adx_wilder(rango + 0.5, rango - 0.5, rango, 14)[0]
    assert adx_t[-1] > 80 and adx_r[-1] < 40


# ---------------------------------------------------------------- sesiones
def test_dst_eeuu_y_conversion_a_utc():
    idx = pd.DatetimeIndex(["2026-03-07", "2026-03-09", "2026-10-31", "2026-11-02"])
    assert list(ses.en_dst_eeuu(idx)) == [False, True, True, False]
    invierno, verano = pd.DatetimeIndex(["2026-01-15 12:00"]), pd.DatetimeIndex(["2026-07-15 12:00"])
    assert ses.servidor_a_utc(invierno, 2)[0] == pd.Timestamp("2026-01-15 10:00")
    assert ses.servidor_a_utc(verano, 2)[0] == pd.Timestamp("2026-07-15 09:00")


def test_mascara_sesiones_con_horario_de_verano():
    m = lambda s, n: bool(ses.mascara_sesiones(pd.DatetimeIndex([s]), n)[0])
    assert m("2026-01-15 10:00", ["Londres"]) and not m("2026-01-15 18:00", ["Londres"])
    assert m("2026-07-15 07:00", ["Londres"]) and not m("2026-07-15 06:59", ["Londres"])  # BST: 08:00 local
    assert m("2026-01-15 00:00", ["Tokio"]) and not m("2026-01-15 09:00", ["Tokio"])
    assert m("2026-07-15 13:00", ["Londres", "Nueva York"]) and not m("2026-07-15 22:30", ["Londres", "Nueva York"])


def test_ventana_que_cruza_medianoche():
    h = {"Nocturna": ("UTC", 22.0, 2.0)}
    r = ses.mascara_sesiones(pd.DatetimeIndex(["2026-01-01 23:00", "2026-01-01 01:00", "2026-01-01 12:00"]), ["Nocturna"], h)
    assert list(r) == [True, True, False]


# ---------------------------------------------------------------- filtros
def _df(n=6000, t=0.1, seed=3):
    return dt.sintetico(n=n, tendencia=t, seed=seed)


def test_conteo_cruces_consistente_y_motivo_primero():
    df = _df()
    cfg = eng.Config(sma_activo=True, adx_activo=True, atr_activo=True, atr_min=0.01, atr_max=9.0,
                     sesion_activo=True, servidor_offset_horas=2)
    P = eng.preparar(df, cfg)
    r = eng.ejecutar(P, cfg)
    assert r.cruces == r.tomados + sum(r.descartes.values()) and r.cruces > 20
    # sesion fuera de cualquier ventana: todo se descarta por 'sesion' aunque SMA/ADX tambien fallen
    cfg2 = replace(cfg, sesiones=("Tokio",), horarios={"Tokio": ("UTC", 3.0, 3.5)})
    d = eng.ejecutar(eng.preparar(df, cfg2), cfg2).descartes
    assert d.get("sesion", 0) >= 0.9 * eng.ejecutar(eng.preparar(df, cfg2), cfg2).cruces


def test_filtro_sma_solo_deja_señales_a_favor():
    df = _df()
    cfg = eng.Config(sma_activo=True, sma_periodo=50)
    P = eng.preparar(df, cfg)
    sma = ind.sma(P.c, 50)
    ok = [(i, lado) for i, lado, m in P.cruces if m is None]
    assert ok and all((P.c[i] - sma[i]) * lado > 0 for i, lado in ok)
    contra = [(i, lado) for i, lado, m in P.cruces if m == "sma"]
    assert contra and all(np.isnan(sma[i]) or (P.c[i] - sma[i]) * lado <= 0 for i, lado in contra)


def test_filtros_adx_y_atr_extremos_descartan_todo():
    df = _df()
    P = eng.preparar(df, eng.Config(adx_activo=True, adx_min=99.9))
    assert P.cruces and all(m == "adx" for _, _, m in P.cruces)
    P = eng.preparar(df, eng.Config(atr_activo=True, atr_min=50.0))
    assert P.cruces and all(m == "atr" for _, _, m in P.cruces)


def test_sesion_sin_offset_da_error_claro():
    try:
        eng.preparar(_df(500), eng.Config(sesion_activo=True))
    except ValueError as e:
        assert "desfase" in str(e)
    else:
        raise AssertionError("debia fallar")


def test_sesion_deja_solo_velas_dentro_de_ventana():
    df = _df()
    cfg = eng.Config(sesion_activo=True, servidor_offset_horas=2, sesiones=("Londres",))
    P = eng.preparar(df, cfg)
    utc = ses.servidor_a_utc(df.index, 2)
    m = ses.mascara_sesiones(utc, ["Londres"])
    ok = [i for i, _, mo in P.cruces if mo is None]
    assert ok and all(m[i] for i in ok)


def test_sin_look_ahead_en_cruces_ni_filtros():
    df = _df(5000)
    cfg = eng.Config(sma_activo=True, sma_periodo=50, sma_dist_min_atr=0.2, sma_pendiente_n=5,
                     adx_activo=True, adx_creciente_n=3, atr_activo=True, atr_rel_n=50,
                     atr_rel_min=0.5, atr_rel_max=3.0, sesion_activo=True, servidor_offset_horas=2)
    full = eng.preparar(df, cfg)
    for k in (1500, 3000, 4200):
        pref = eng.preparar(df.iloc[:k], cfg)
        assert pref.cruces == [x for x in full.cruces if x[0] < k], k
        assert np.allclose(pref.dist, full.dist[:k])


# ------------------------------------------------- equivalencia con la linea de base
def test_equivale_a_cruce_minimo_sin_filtros():
    if cm is None:
        print("   (omitido: copia cruce_minimo.py a esta carpeta)")
        return
    for tend, seed in [(0.0, 1), (0.15, 3)]:
        df = cm.sintetico(n=8000, tendencia=tend, seed=seed)
        arr = {"h": df["High"].to_numpy(float), "l": df["Low"].to_numpy(float),
               "c": df["Close"].to_numpy(float), "sp": df["Spread"].to_numpy(float)}
        arr["atr"] = cm.atr_wilder(arr["h"], arr["l"], arr["c"], 14)
        viejo = cm.simular(arr, cm.senales(arr["c"], 13, 34, "ambas"), 2.0, 1.5, True)
        cfg = eng.Config()
        P = eng.preparar(df, cfg)
        nuevo = eng.ejecutar(P, cfg).trades
        for col in ("i", "lado", "res", "amb", "salida"):
            assert list(viejo[col]) == list(nuevo[col]), col
        assert abs(cm.resumen(viejo, 2.0)["exp_R"] - met.resumen(nuevo, 2.0)["exp_R"]) < 1e-12
        a1 = cm.azar(arr, len(viejo), 0, len(df), 2.0, 1.5, True, 20, np.random.default_rng(5), "ambas")
        a2 = met.azar(P, cfg, 0, len(df), len(viejo), 20, np.random.default_rng(5))
        assert np.allclose(a1, a2)


# ------------------------------------------------------------------ dinero
def test_dinero_con_tick_value():
    # oro: tick 0.01, valor 1.0; 0.10 lotes -> $10 por cada $1 de movimiento
    assert abs(met.valor_por_unidad(0.01, 1.0, 0.10) - 10.0) < 1e-9
    tr = pd.DataFrame({"res": ["TP", "SL"], "R": [2.0, -1.0], "dist": [2.0, 2.0]})
    d = met.resumen_dinero(tr, 0.01, 1.0, 0.10, comision_por_lote=7.0)
    assert abs(d["riesgo_medio_por_operacion"] - 20.0) < 1e-9
    assert abs(d["neto"] - (40.0 - 20.0 - 2 * 0.7)) < 1e-9 and abs(d["comisiones"] - 1.4) < 1e-9


def test_validar_lotaje():
    met.validar_lotaje(0.10, 0.01, 100, 0.01)
    for malo in (0.005, 150, 0.015):
        try:
            met.validar_lotaje(malo, 0.01, 100, 0.01)
        except ValueError:
            continue
        raise AssertionError(malo)


# ------------------------------------------------------------------- datos
def _rates(tiempos, spread=10):
    d = np.dtype([("time", "i8"), ("open", "f8"), ("high", "f8"), ("low", "f8"), ("close", "f8"),
                  ("tick_volume", "u8"), ("spread", "i4"), ("real_volume", "u8")])
    a = np.zeros(len(tiempos), d)
    a["time"], a["open"], a["high"], a["low"], a["close"], a["spread"] = tiempos, 1, 2, 0.5, 1.5, spread
    return a


def test_union_de_tramos_sin_repetidas_y_tramos_vacios():
    t = np.arange(0, 100) * 3600
    def fetch(ini, fin):
        a, b = int(ini.timestamp()), int(fin.timestamp())
        if b <= 24 * 3600:
            return None                                   # primer tramo: antes del inicio del historial
        sel = t[(t >= a) & (t <= b)]                      # bordes inclusivos -> repetidas
        return _rates(sel) if len(sel) else None
    from datetime import datetime, timedelta
    ini = datetime(1970, 1, 1)
    r, vacios = dt.descargar_por_tramos(fetch, ini, ini + timedelta(hours=100), 1)
    assert vacios == 1 and len(r) == len(np.unique(r["time"])) and r["time"][0] == 24 * 3600 and r["time"][-1] == 99 * 3600
    assert (np.diff(r["time"]) == 3600).all()


def test_rates_a_df_convierte_spread_a_precio():
    df = dt.rates_a_df(_rates([0, 3600], spread=25), 0.01)
    assert abs(df["Spread"].iloc[0] - 0.25) < 1e-12 and list(df.columns) == dt.COLUMNAS


def test_cargar_csv_formato_mt5():
    d = dt.sintetico(n=300)
    out = pd.DataFrame({"<DATE>": d.index.strftime("%Y.%m.%d"), "<TIME>": d.index.strftime("%H:%M:%S"),
                        "<OPEN>": d.Open.round(2), "<HIGH>": d.High.round(2), "<LOW>": d.Low.round(2),
                        "<CLOSE>": d.Close.round(2), "<TICKVOL>": 1, "<VOL>": 0, "<SPREAD>": 30})
    with tempfile.TemporaryDirectory() as tmp:
        ruta = os.path.join(tmp, "x.csv")
        out.to_csv(ruta, sep="\t", index=False)
        df = dt.cargar_csv(ruta, 0.01)
    assert len(df) == 300 and not df[["Open", "High", "Low", "Close"]].isna().any().any()
    assert abs(df["Spread"].iloc[0] - 0.30) < 1e-9 and df.index[0] == d.index[0]


def test_modos_de_spread():
    df = _df(500)
    df["Spread"] = [0.0, 0.0, 0.2, 0.4] * 125
    sp = lambda m, **k: eng._spread(df, eng.Config(spread=m, **k))
    assert (sp("vela") == df["Spread"].to_numpy()).all()
    raw = df["Spread"].to_numpy()
    assert np.allclose(sp("mediana"), np.where(raw > 0, raw, 0.3))      # solo los ceros pasan a la mediana (0.3)
    assert (sp("fijo", spread_fijo=0.5) == 0.5).all() and (sp("ninguno") == 0).all()


def test_resamplear_4h_y_calidad():
    df = dt.sintetico(n=48)
    r = dt.resamplear(df, "4h")
    g = df.iloc[:4]
    assert len(r) == 12 and r["Open"].iloc[0] == g["Open"].iloc[0] and r["High"].iloc[0] == g["High"].max()
    assert r["Low"].iloc[0] == g["Low"].min() and r["Close"].iloc[0] == g["Close"].iloc[-1]
    q = dt.calidad(dt.sintetico(n=100))
    assert q["velas"] == 100 and q["duplicadas"] == 0 and q["spread_cero_pct"] == 0.0


# ------------------------------------------------------- pipeline completo
def test_evaluar_y_ablacion_humo():
    df = _df(4000)
    c = met.ContadorPruebas()
    r = met.evaluar(df, eng.Config(), azar_veces=10, contador=c)
    t = r["tabla"]
    assert list(t.index) == ["Todo", "In-sample", "Out-of-sample"] and r["prueba"] == 1
    assert t.loc["Todo", "TP"] + t.loc["Todo", "SL"] == t.loc["Todo", "resueltas"]
    ab, omit = met.ablacion(df, eng.Config(), azar_veces=5, contador=c)
    assert "Cruce solo" in ab.index and "+ SMA" in ab.index and omit == ["Sesion"] and c.n == 1 + len(ab)
    ab2, omit2 = met.ablacion(df, eng.Config(servidor_offset_horas=2), azar_veces=5)
    assert omit2 == [] and "Todos juntos" in ab2.index


if __name__ == "__main__":
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    for nombre, f in tests:
        f()
        print("OK ", nombre)
    print(f"\n{len(tests)} tests pasaron.")
