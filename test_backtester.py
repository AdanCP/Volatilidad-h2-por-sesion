"""Tests de la etapa (a). Ejecutar:  python test_backtester.py   (o: pytest)"""
import os
import sys
import tempfile
from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import data as dt
import engine as eng
import indicators as ind
import metrics as met
import veredicto as vd
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


def test_eficiencia_contra_calculo_manual_y_extremos():
    # tendencia limpia = 1; ida y vuelta = 0; precio quieto = 0 (sin dividir por cero)
    assert np.allclose(ind.eficiencia(np.arange(30, dtype=float), 10)[10:], 1.0)
    zig = np.tile([100.0, 101.0], 20)
    assert np.allclose(ind.eficiencia(zig, 10)[10:], 0.0)
    assert np.allclose(ind.eficiencia(np.full(30, 5.0), 10)[10:], 0.0)
    c = np.array([1, 2, 3, 4, 5, 4, 5, 4, 5, 4.])
    e = ind.eficiencia(c, 4)
    assert np.isnan(e[:4]).all() and np.isclose(e[4], 1.0) and np.isclose(e[5], 0.5) and np.isclose(e[7], 0.0)
    # contra una version lenta e independiente
    rng = np.random.default_rng(5)
    x = 100 + np.cumsum(rng.normal(0, 1, 400))
    lento = [abs(x[i] - x[i - 20]) / sum(abs(x[k] - x[k - 1]) for k in range(i - 19, i + 1)) for i in range(20, 400)]
    assert np.allclose(ind.eficiencia(x, 20)[20:], lento)
    assert np.allclose(ind.eficiencia(x[:10], 20), np.nan, equal_nan=True)


def test_filtro_de_rango_descarta_con_motivo_rango_y_no_mira_el_futuro():
    df = _df()
    base = eng.preparar(df, eng.Config())
    todo = eng.preparar(df, eng.Config(rango_activo=True, rango_min=1.0))        # ratio 1 exacto casi nunca ocurre
    assert todo.cruces and sum(m == "rango" for _, _, m in todo.cruces) > 0.9 * len(todo.cruces)
    nada = eng.preparar(df, eng.Config(rango_activo=True, rango_min=0.0))        # minimo 0: no descarta nada
    assert [m for _, _, m in nada.cruces] == [m for _, _, m in base.cruces]
    # el filtro decide solo con datos hasta la vela de la senal
    cfg = eng.Config(rango_activo=True, rango_ventana=15, rango_min=0.3)
    a = eng.preparar(df, cfg)
    b = eng.preparar(df.iloc[:3000], cfg)
    assert [x for x in a.cruces if x[0] < 3000] == b.cruces
    # y cada senal descartada tiene realmente un ratio bajo
    er = ind.eficiencia(df["Close"].to_numpy(float), 15)
    assert all(er[i] < 0.3 or np.isnan(er[i]) for i, _, m in a.cruces if m == "rango")
    assert all(er[i] >= 0.3 for i, _, m in a.cruces if m is None)


def test_filtro_de_rango_validacion_y_ablacion():
    import pytest
    for k in (dict(rango_ventana=1), dict(rango_min=1.5), dict(rango_min=-0.1)):
        with pytest.raises(ValueError):
            eng.preparar(_df(n=500), eng.Config(rango_activo=True, **k))
    assert "Rango (ratio de eficiencia)" in met.FILTROS_ABLACION
    assert eng.FILTROS_APAGADOS["rango_activo"] is False


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
    assert "Cruce solo" in ab.index and "+ SMA" in ab.index and omit == ["Volume Profile", "Sesion"] and c.n == 1 + len(ab)
    ab2, omit2 = met.ablacion(df, eng.Config(servidor_offset_horas=2), azar_veces=5)
    assert omit2 == [] and "Todos juntos" in ab2.index


# ------------------------------------------------------------ multi-simbolo
def test_tipo_activo_y_deteccion_de_simbolos():
    assert [met.tipo_activo(s) for s in ("XAUUSD", "XAGUSD.a", "BTCUSD", "EURUSD", "USDJPY", "US30.cash",
                                          "GER40", "NAS100", "JP225")] == \
        ["metal", "metal", "cripto", "forex", "forex", "indice", "indice", "indice", "indice"]
    h = dt.detectar_simbolos(["XAUUSD", "XAUUSD.r", "EURUSD", "US30.cash", "BTCUSD", "NADA"])
    assert h["oro"] == "XAUUSD" and h["EURUSD"] == "EURUSD" and h["Dow Jones"] == "US30.cash"
    assert h["plata"] is None and h["Nikkei"] is None


def test_comparar_simbolos_recorte_comun_y_cripto_sin_sesion():
    datos = {"XAUUSD": dt.sintetico(n=5000, seed=1), "BTCUSD": dt.sintetico(n=3000, seed=2),
             "EURUSD": dt.sintetico(n=4000, seed=3)}
    cfg = eng.Config(sesion_activo=True, servidor_offset_horas=2)
    c = met.ContadorPruebas()
    tabla, notas = met.comparar_simbolos(datos, cfg, azar_veces=5, contador=c, recortar_comun=True)
    assert list(tabla.index) == ["XAUUSD", "BTCUSD", "EURUSD"] and c.n == 3
    assert tabla["velas"].nunique() == 1 and tabla["desde"].nunique() == 1
    assert any("BTCUSD" in n and "24/7" in n for n in notas)
    t2, n2 = met.comparar_simbolos(datos, eng.Config(), azar_veces=5)
    assert any("distinto largo" in n for n in n2) and t2["velas"].nunique() == 3


def test_sync_ida_y_vuelta_y_manifest():
    d = dt.sintetico(n=500, spread=0.25)
    spec = {"simbolo": "XAUUSD", "point": 0.01, "tick_size": 0.01, "tick_value": 1.0}
    with tempfile.TemporaryDirectory() as t:
        ruta = dt.guardar_sync(d, spec, t, "XAUUSD", "H1")
        assert ruta.endswith("XAUUSD_H1.csv.gz")
        b1 = open(ruta, "rb").read()
        dt.guardar_sync(d, spec, t, "XAUUSD", "H1")
        assert open(ruta, "rb").read() == b1          # bytes reproducibles: sin cambios inutiles en git
        r = dt.cargar_sync(t, "XAUUSD", "H1")
        assert len(r) == 500 and abs(r["Close"] - d["Close"]).max() < 1e-9
        assert abs(r["Spread"].iloc[0] - 0.25) < 1e-9
        assert dt.leer_manifest(t) == {}
        dt.escribir_manifest(t, {"sincronizado": "x", "simbolos": {"XAUUSD": {"spec": spec, "tfs": {}}}})
        assert dt.leer_manifest(t)["simbolos"]["XAUUSD"]["spec"]["tick_value"] == 1.0
        try:
            dt.cargar_sync(t, "NADA", "H1")
            assert False
        except dt.ErrorDatos:
            pass


def test_subir_git_con_remoto_que_avanzo():
    import subprocess
    import sincronizar_mt5 as sm
    def g(cwd, *a):
        return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True, check=True)
    with tempfile.TemporaryDirectory() as t:
        remoto, a, b = (os.path.join(t, x) for x in ("remoto.git", "a", "b"))
        g(t, "init", "-q", "--bare", "-b", "main", remoto)
        for c in (a, b):
            g(t, "clone", "-q", remoto, c)
            g(c, "config", "user.email", "t@t"); g(c, "config", "user.name", "t")
        open(os.path.join(a, "estado.json"), "w").write("1")
        g(a, "add", "."); g(a, "commit", "-qm", "base"); g(a, "push", "-q", "origin", "HEAD:main")
        g(b, "pull", "-q", "origin", "main")
        open(os.path.join(a, "estado.json"), "w").write("2")        # el "bot" avanza el remoto
        g(a, "commit", "-qam", "bot"); g(a, "push", "-q")
        os.makedirs(os.path.join(b, "datos_mt5"))
        open(os.path.join(b, "datos_mt5", "x.csv.gz"), "w").write("datos")
        cwd = os.getcwd(); os.chdir(b)
        try:
            sm.subir("datos_mt5")
            sm.subir("datos_mt5")                                    # segunda vez: nada que subir
        finally:
            os.chdir(cwd)
        g(a, "pull", "-q"); assert os.path.exists(os.path.join(a, "datos_mt5", "x.csv.gz"))


def test_sl_fijo_en_precio_y_dolares():
    df = dt.sintetico(n=6000, tendencia=0.3, seed=4)
    # 0,10 lotes de oro: tick 0,01 y tick_value 1 -> 100 US$ por cada 1,00 de precio; SL 200 US$ = 2,00 de precio
    vpu = met.valor_por_unidad(0.01, 1.0, 0.10)
    assert abs(vpu - 10.0) < 1e-9
    dist = 200.0 / vpu
    cfg = eng.Config(sl_modo="precio", sl_valor=dist, rr=2.0)
    r = met.evaluar(df, cfg, 0.3, 10)
    tr = r["trades"]
    assert len(tr) > 20 and (abs(tr["dist"] - dist) < 1e-9).all()
    d = met.resumen_dinero(tr, 0.01, 1.0, 0.10)
    assert abs(d["riesgo_medio_por_operacion"] - 200.0) < 1e-6          # el SL fijo es exactamente el riesgo en dinero
    assert abs(d["perdida_media_SL"] + 200.0) < 1e-6 and abs(d["ganancia_media_TP"] - 400.0) < 1e-6
    # relacion TP/SL menor que 1 solo se permite con SL fijo
    eng.Config(sl_modo="precio", sl_valor=2.0, rr=0.5).validar()
    try:
        eng.Config(sl_modo="atr", rr=0.5).validar()
        assert False
    except ValueError:
        pass


def test_comparar_simbolos_con_config_por_simbolo():
    datos = {"A": dt.sintetico(n=4000, seed=1), "B": dt.sintetico(n=4000, seed=2)}
    cfgs = {"A": eng.Config(sl_modo="precio", sl_valor=3.0), "B": eng.Config(sl_modo="precio", sl_valor=6.0)}
    tabla, _ = met.comparar_simbolos(datos, cfgs, azar_veces=5)
    assert list(tabla.index) == ["A", "B"]
    uno, _ = met.comparar_simbolos(datos, eng.Config(), azar_veces=5)         # sigue aceptando una sola Config
    assert list(uno.index) == ["A", "B"]


def _veredicto(df, **kw):
    cfg = eng.Config(sl_modo="precio", sl_valor=10.0, rr=2.0)
    r = met.evaluar(df, cfg, 0.3, 30, 42, met.ContadorPruebas())
    meses = (df.index[-1] - df.index[0]).days / 30.44
    return vd.evaluar_veredicto(r, cfg, meses, usd_por_R=100.0, capital=100000, limite_pct=10, **kw), r, cfg, meses


def test_veredicto_azar_no_es_valida_y_tendencia_si():
    v_azar, *_ = _veredicto(dt.sintetico(n=30000, tendencia=0.0, seed=3))
    assert v_azar["nivel"] in ("sin", "pierde", "dudosa")
    v_ten, r, cfg, meses = _veredicto(dt.sintetico(n=30000, tendencia=0.6, seed=3))
    assert v_ten["nivel"] in ("solida", "ok") and v_ten["puntos"] == v_ten["tope"]
    assert [f["meses"] for f in v_ten["proy_total"]] == [1, 3, 6, 12]
    ps = [f["p_ganar"] for f in v_ten["proy_total"]]
    assert ps == sorted(ps) and ps[-1] > 0.99                         # con ventaja real, más tiempo = más probabilidad
    assert all(0 <= f["p_limite"] <= 1 for f in v_ten["proy_total"])


def test_veredicto_pocas_operaciones_no_concluyente():
    v, *_ = _veredicto(dt.sintetico(n=1500, tendencia=0.6, seed=3))
    assert v["nivel"] == "nc"


def test_veredicto_es_reproducible_y_muchas_pruebas_exigen_mas():
    df = dt.sintetico(n=30000, tendencia=0.0, seed=3)
    a, *_ = _veredicto(df)
    b, *_ = _veredicto(df)
    assert a["proy_total"] == b["proy_total"] and a["prob_ventaja_total"] == b["prob_ventaja_total"]
    c, *_ = _veredicto(dt.sintetico(n=30000, tendencia=0.6, seed=3), pruebas=40)
    assert any("99%" in n_ or "muchas pruebas" in n_ for n_ in c["notas"] + [x[2] for x in c["checks"]])


def test_probabilidad_de_ventaja_y_proyeccion_basicas():
    sin_ventaja = {"w": 100, "l": 200, "gana_R": 2.0, "pierde_R": -1.0, "p_equilibrio": 1 / 3}
    assert 0.3 < vd.prob_ventaja(sin_ventaja) < 0.7                    # 33% de acierto con RR 2: justo el equilibrio
    claro = {"w": 150, "l": 150, "gana_R": 2.0, "pierde_R": -1.0, "p_equilibrio": 1 / 3}
    assert vd.prob_ventaja(claro) > 0.99
    perdedora = {"w": 20, "l": 180, "gana_R": 2.0, "pierde_R": -1.0, "p_equilibrio": 1 / 3}
    pr = vd.proyectar(perdedora, 10, usd_por_R=100.0, limite_usd=1000.0)
    assert pr[-1]["p_ganar"] < 0.05 and pr[-1]["p_limite"] > 0.95       # mala estrategia: casi seguro toca el límite
    assert vd.proyectar(None, 10) == [] and vd.proyectar(claro, 0) == []
    assert vd.prob_ventaja(None) != vd.prob_ventaja(None)               # NaN


def test_descripcion_incluye_los_parametros_marcados():
    df = dt.sintetico(n=8000, seed=2)
    cfg = eng.Config(ema_corta=13, ema_larga=34, sl_modo="precio", sl_valor=5.0, rr=2.0, sma_activo=True, sma_periodo=200,
                     adx_activo=True, adx_min=25.0, sesion_activo=True, sesiones=("Londres",), servidor_offset_horas=2.0,
                     direccion="largos")
    h = vd.describir(cfg, "XAUUSD", "H1", df.index[0], df.index[-1], 12.0, 0.1, -1234.5, 80, 20, 60, -0.3, 2000.0,
                     sl_usd=200.0, tp_usd=400.0)
    for x in ("XAUUSD", "H1", "13/34", "solo largos", "SL de US$200,00", "TP de US$400,00", "SMA 200", "ADX(14) ≥ 25",
              "sesión Londres", "perdido US$1.234,50", "0,10 lotes", "80 operaciones", "-0,30 R"):
        assert x in h, x


def test_rachas():
    import pandas as pd
    idx = pd.date_range("2024-01-01", periods=50, freq="D")
    seq = ["TP","TP","TP","SL","SL","TP","SL","SL","SL","SL","TP","ABIERTA"]
    tr = pd.DataFrame({"i": range(0, 36, 3), "salida": range(1, 37, 3), "res": seq,
                       "R": [2 if x == "TP" else -1 if x == "SL" else 0 for x in seq]})
    r = met.rachas(tr, idx, 5)
    assert [x["largo"] for x in r["TP"]] == [3, 1, 1]
    assert [x["largo"] for x in r["SL"]] == [4, 2]
    assert r["SL"][0]["R"] == -4 and r["TP"][0]["R"] == 6
    assert met.rachas(tr.iloc[0:0], idx)["TP"] == []


def test_frecuencia():
    idx = pd.date_range("2024-01-01", periods=70, freq="D")   # 70 dias
    tr = pd.DataFrame({"i": [0, 0, 5, 10, 20, 30, 40], "res": ["TP"] * 7})
    f = met.frecuencia(tr, idx)
    assert f["n"] == 7 and f["max_dia"] == 2 and f["dias_con_op"] == 6
    assert abs(f["por_dia"] - 0.1) < 1e-9 and abs(f["por_semana"] - 0.7 * 7 / 7 * 1.0) < 0.05
    assert met.frecuencia(tr.iloc[0:0], idx)["por_mes"] == 0.0
    # entradas en los días 0,0,5,10,20,30,40 de 70: el mayor hueco es 40 -> fin (29 días libres hasta el día 69)
    assert f["max_sin_op"] == 29
    # días 0..30 son enero (6 entradas) y el día 40 es febrero (1)
    assert f["max_mes"] == 6 and f["mes_max"] == (2024, 1)
    assert met.frecuencia(tr.iloc[0:0], idx)["max_mes"] == 0


def test_veredicto_seis_estados_alcanzables():
    df0 = dt.sintetico(n=30000, tendencia=0.0, seed=3)
    m = (df0.index[-1] - df0.index[0]).days / 30.44

    def nivel(df, **c):
        cfg = eng.Config(sl_modo="precio", sl_valor=10.0, rr=2.0, **c)
        r = met.evaluar(df, cfg, 0.3, 30, 42, met.ContadorPruebas())
        return vd.evaluar_veredicto(r, cfg, m, usd_por_R=100.0, capital=100000, limite_pct=10)["nivel"]
    assert nivel(df0) == "sin"                                   # sin ventaja: compatible con el azar
    assert nivel(df0, costo_extra=4.0) == "pierde"               # costos > ventaja: expectativa negativa
    assert nivel(dt.sintetico(n=30000, tendencia=0.6, seed=3)) == "solida"
    assert nivel(dt.sintetico(n=1500, tendencia=0.6, seed=3)) == "nc"


def test_extremos_diarios():
    idx = pd.date_range("2024-01-01", periods=10, freq="12h")
    # dias: d0 = TP(+2) y SL(-1) ; d1 = SL,SL ; d2 = TP,TP
    tr = pd.DataFrame({"res": ["TP", "SL", "SL", "SL", "TP", "TP"], "R": [2, -1, -1, -1, 2, 2],
                       "dist": [1.0] * 6, "salida": [0, 1, 2, 3, 4, 5]})
    e = met.extremos_diarios(tr, idx, 1.0, 1.0, 1.0)     # 1 US$ por unidad de precio
    assert e["peor_usd"] == -2.0 and e["peor_ops"] == 2 and e["mejor_usd"] == 4.0 and e["peor_R"] == -2.0
    assert met.extremos_diarios(tr.iloc[0:0], idx, 1, 1, 1) == {}


def _P_pb(h, l, ema=100.0, sube=None, baja=None, ok_ses=None, dist=2.0):
    n = len(h)
    h, l = np.array(h, float), np.array(l, float)
    z = np.zeros(n)
    return eng.Preparado(h, l, (h + l) / 2, z.copy(), z.copy(), np.full(n, dist), pd.date_range("2024-01-01", periods=n, freq="h"),
                         [], 0.0, np.full(n, ema), np.full(n, ema),
                         np.zeros(n, bool) if sube is None else np.array(sube, bool),
                         np.zeros(n, bool) if baja is None else np.array(baja, bool), ok_ses)


def test_pullback_largo_se_ejecuta_en_el_nivel_y_llega_a_tp():
    #            0    1    2    3    4    5
    P = _P_pb([101, 103, 105, 104, 107, 108], [99, 101, 103, 102, 103, 106])
    tr, _ = eng.simular(P, [(2, 1)], 2.0, 0.0, {"pct": 50, "ema": "corta", "velas": 10})
    f = tr.iloc[0]
    # extremo 105, EMA 100 -> nivel 102,5; la vela 3 (minimo 102) lo toca
    assert f["señal"] == 2 and f["i"] == 3 and abs(f["entrada"] - 102.5) < 1e-9
    assert f["res"] == "TP" and f["salida"] == 4 and f["R"] == 2.0
    assert tr.attrs["pb"] == {"ordenes": 1, "llenadas": 1, "caducadas": 0, "cruce_contrario": 0}


def test_pullback_caduca_a_las_n_velas_y_libera_para_la_siguiente_señal():
    h = [101, 103, 105, 106, 107, 108, 109, 110]
    l = [99, 101, 103, 104, 105, 106, 107, 108]            # nunca baja a la EMA (100)
    P = _P_pb(h, l)
    tr, ign = eng.simular(P, [(2, 1)], 2.0, 0.0, {"pct": 100, "ema": "corta", "velas": 3})
    assert len(tr) == 0 and tr.attrs["pb"]["caducadas"] == 1 and tr.attrs["pb"]["llenadas"] == 0


def test_pullback_se_cancela_por_cruce_contrario_y_la_señal_contraria_se_procesa():
    h = [101, 103, 105, 106, 107, 108]
    l = [99, 101, 103, 104, 90, 88]
    # largo en 2 con nivel 100 (100 % de la EMA); en la vela 4 hay cruce bajista -> se cancela; el corto de la vela 4 entra
    P = _P_pb(h, l, baja=[0, 0, 0, 0, 1, 0])
    P.l[4] = 103                                            # la vela 4 no llega al nivel 100: no se llena el largo
    tr, _ = eng.simular(P, [(2, 1), (4, -1)], 2.0, 0.0, {"pct": 100, "ema": "corta", "velas": 10})
    assert tr.attrs["pb"]["cruce_contrario"] == 1
    assert tr.attrs["pb"]["ordenes"] == 2


def test_pullback_en_la_vela_de_entrada_si_toca_sl_cuenta_sl_y_no_mira_tp():
    P = _P_pb([101, 103, 105, 109, 109], [99, 101, 103, 100, 108])
    tr, _ = eng.simular(P, [(2, 1)], 2.0, 0.0, {"pct": 50, "ema": "corta", "velas": 10})
    f = tr.iloc[0]       # nivel 102,5 ; SL 100,5 ; la vela 3 baja a 100: SL (ambigua) aunque luego sube
    assert f["res"] == "SL" and f["amb"] and f["salida"] == 3 and f["R"] == -1.0


def test_pullback_corto_y_filtro_de_sesion_al_ejecutar():
    # corto: extremo (minimo) 95, EMA 100 -> con 50 % el nivel es 97,5
    h = [99, 97, 96, 98, 94, 93]
    l = [97, 95, 95, 96, 92, 90]
    P = _P_pb(h, l)
    tr, _ = eng.simular(P, [(2, -1)], 2.0, 0.0, {"pct": 50, "ema": "corta", "velas": 10})
    assert tr.iloc[0]["i"] == 3 and abs(tr.iloc[0]["entrada"] - 97.5) < 1e-9
    P2 = _P_pb(h, l, ok_ses=np.array([1, 1, 1, 0, 1, 1], bool))   # fuera de sesion en la vela 3: no ejecuta ahi
    tr2, _ = eng.simular(P2, [(2, -1)], 2.0, 0.0, {"pct": 50, "ema": "corta", "velas": 10})
    assert len(tr2) == 0 or tr2.iloc[0]["i"] != 3


def test_pullback_config_y_opcionalidad():
    assert eng.pb_de(eng.Config()) is None                                   # apagado por defecto
    assert eng.pb_de(eng.Config(pullback_activo=True, pullback_pct=0)) is None   # 0 % = entrada al cierre
    assert eng.pb_de(eng.Config(pullback_activo=True, pullback_pct=40, pullback_ema="larga"))["ema"] == "larga"
    for mal in (dict(pullback_pct=101), dict(pullback_ema="x"), dict(pullback_velas=0)):
        try:
            eng.Config(**mal).validar()
            assert False
        except ValueError:
            pass


def test_pullback_integracion_apagado_no_cambia_y_encendido_filtra_operaciones():
    df = dt.sintetico(n=12000, tendencia=0.6, seed=3)
    base = eng.Config(sl_modo="precio", sl_valor=10.0, rr=2.0)
    r0 = met.evaluar(df, base, 0.3, 10, 1)
    r1 = met.evaluar(df, replace(base, pullback_activo=True, pullback_pct=0), 0.3, 10, 1)   # 0 % = igual que apagado
    assert r0["tabla"].loc["Todo", "resueltas"] == r1["tabla"].loc["Todo", "resueltas"]
    r2 = met.evaluar(df, replace(base, pullback_activo=True, pullback_pct=60, pullback_velas=10), 0.3, 10, 1)
    pb = r2["tabla"].loc["Todo", "pb"]
    assert pb["ordenes"] >= pb["llenadas"] > 0 and pb["ordenes"] == pb["llenadas"] + pb["caducadas"] + pb["cruce_contrario"]
    assert (r2["trades"]["i"] >= r2["trades"]["señal"]).all()
    ab, _ = met.ablacion(df, replace(base, pullback_activo=True, pullback_pct=60), azar_veces=5)
    assert "+ Pullback" in ab.index and "Cruce solo" in ab.index


def test_vwap_diario_se_reinicia_y_pondera_por_volumen():
    idx = pd.date_range("2024-01-01 00:00", periods=6, freq="12h")      # 2 velas por dia
    h = np.array([11, 11, 21, 21, 31, 31.0]); l = np.array([9, 9, 19, 19, 29, 29.0]); c = np.array([10, 10, 20, 20, 30, 30.0])
    vol = np.array([1, 3, 1, 1, 0, 0.0])
    v, nro = ind.vwap_diario(h, l, c, vol, idx.normalize().to_numpy())
    assert list(nro) == [1, 2, 1, 2, 1, 2]
    assert v[0] == 10 and v[1] == 10 and v[2] == 20 and v[4] == 30          # cada dia arranca de cero; sin volumen no hay NaN
    v2, _ = ind.vwap_diario([12, 12], [8, 8], [10, 20], [1, 3], [1, 1])      # típicos 10 y 13,33 -> (10*1 + 13,33*3) / 4 = 12,5
    assert abs(v2[1] - 12.5) < 1e-9


def test_filtro_vwap_direccion_y_requisitos():
    df = dt.sintetico(n=6000, tendencia=0.6, seed=3)
    base = eng.Config(sl_modo="precio", sl_valor=10.0, rr=2.0)
    sin = eng.preparar(df, base)
    con = eng.preparar(df, replace(base, vwap_activo=True, vwap_min_minutos=0))
    mot = [m for _, _, m in con.cruces]
    assert mot.count("vwap") > 0 and len(con.cruces) == len(sin.cruces)           # mismos cruces, algunos descartados por VWAP
    dist = eng.preparar(df, replace(base, vwap_activo=True, vwap_min_minutos=0, vwap_dist_min_atr=5.0))
    assert [m for _, _, m in dist.cruces].count("vwap") >= mot.count("vwap")        # exigir distancia nunca descarta menos
    dia = dt.sintetico(n=800, seed=1)
    d1 = dia.resample("1D").agg({"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum", "Spread": "last"}).dropna()
    assert not eng.es_intradia(d1) and eng.es_intradia(df)
    try:
        eng.preparar(d1, replace(base, vwap_activo=True)); assert False
    except ValueError:
        pass
    ab, omitidos = met.ablacion(d1, base, azar_veces=3)
    assert "VWAP" in omitidos


def _tabla_comp(sobre=None):
    base = {"XAUUSD": dict(tipo="metal", desde="2025-01-02", hasta="2026-10-30", resueltas=134, resueltas_OOS=41, sl_atr=1.4,
                           **{"spread_%SL": 4.0}, ops_mes=6.1, exp_R=0.18, exp_R_OOS=0.26, sesion_no_aplica=False),
            "US30": dict(tipo="indice", desde="2025-01-02", hasta="2026-10-30", resueltas=118, resueltas_OOS=22, sl_atr=3.8,
                         **{"spread_%SL": 2.0}, ops_mes=5.4, exp_R=-0.13, exp_R_OOS=-0.73, sesion_no_aplica=True)}
    for (s, k), v in (sobre or {}).items():
        base[s][k] = v
    return pd.DataFrame(base).T


def test_comparabilidad_caso_oro_vs_indice_no_son_comparables():
    r = vd.evaluar_comparabilidad(_tabla_comp())
    est = {n: e for e, n, _ in r["checks"]}
    assert r["nivel"] == "no" and r["n_bad"] == 2
    assert est["Mismo tipo de activo"] == vd.BAD and est["Riesgo equivalente (SL en ATR)"] == vd.BAD
    assert est["Muestra suficiente en cada uno"] == vd.WARN and est["Período común"] == vd.OK
    assert est["Costos comparables (spread / SL)"] == vd.OK and est["Frecuencia parecida"] == vd.OK
    assert est["Filtros aplicables a todos"] == vd.WARN
    assert r["robustez"]["k"] == 1 and r["robustez"]["nivel"] == "sin" and r["robustez"]["N"] == 2


def test_comparabilidad_niveles_con_reservas_y_comparables():
    ok = _tabla_comp({("US30", "tipo"): "metal", ("US30", "sl_atr"): 1.5, ("US30", "resueltas_OOS"): 40,
                         ("US30", "sesion_no_aplica"): False, ("US30", "exp_R"): 0.1, ("US30", "exp_R_OOS"): 0.2})
    assert vd.evaluar_comparabilidad(ok)["nivel"] == "ok"
    assert vd.evaluar_comparabilidad(ok)["robustez"]["nivel"] == "ok"
    res = _tabla_comp({("US30", "tipo"): "metal", ("US30", "sl_atr"): 1.5, ("US30", "resueltas_OOS"): 22,
                          ("US30", "sesion_no_aplica"): False})
    assert vd.evaluar_comparabilidad(res)["nivel"] == "reservas"
    otra_epoca = _tabla_comp({("US30", "tipo"): "metal", ("US30", "sl_atr"): 1.5, ("US30", "resueltas_OOS"): 40,
                                 ("US30", "sesion_no_aplica"): False, ("US30", "desde"): "2022-01-02"})
    assert vd.evaluar_comparabilidad(otra_epoca)["nivel"] == "no"


def test_comparar_simbolos_trae_las_columnas_nuevas():
    datos = {"XAUUSD": dt.sintetico(n=6000, tendencia=0.6, seed=1), "US30": dt.sintetico(n=6000, tendencia=0.6, seed=2)}
    cfg = eng.Config(sl_modo="precio", sl_valor=10.0, rr=2.0)
    tabla, _ = met.comparar_simbolos(datos, cfg, azar_veces=3)
    for c in ("sl_atr", "ops_mes", "maxDD_R", "resueltas_OOS", "sesion_no_aplica"):
        assert c in tabla.columns
    assert (tabla["sl_atr"] > 0).all() and (tabla["ops_mes"] > 0).all()
    r = vd.evaluar_comparabilidad(tabla)
    assert r["nivel"] in ("ok", "reservas", "no") and len(r["checks"]) == 7


if __name__ == "__main__":
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    for nombre, f in tests:
        f()
        print("OK ", nombre)
    print(f"\n{len(tests)} tests pasaron.")


def test_duraciones_y_win_rate():
    import numpy as np
    import pandas as pd
    import metrics as met_
    idx = pd.date_range("2024-01-01", periods=100, freq="h")
    tr = pd.DataFrame({"res": ["TP", "TP", "SL", "SL", "SL", "NO"], "i": [0, 10, 20, 30, 40, 50],
                       "salida": [2, 14, 21, 33, 41, 60]})
    d = met_.duraciones(tr, idx)
    assert d["n_tp"] == 2 and d["n_sl"] == 3 and abs(d["win_rate"] - 40.0) < 1e-9
    assert d["velas_tp"] == 3.0 and abs(d["velas_sl"] - (1 + 3 + 1) / 3) < 1e-9
    assert abs(d["min_tp"] - 180.0) < 1e-9                 # 3 velas de 1 h
    assert met_.fmt_duracion(45) == "45 min" and met_.fmt_duracion(180) == "3,0 h" and met_.fmt_duracion(5000) == "3,5 d"
    vacio = met_.duraciones(tr.iloc[0:0], idx)
    assert vacio["n"] == 0 and np.isnan(vacio["win_rate"])


def test_ciclos_objetivo_retiros():
    import numpy as np
    import pandas as pd
    import metrics as met_
    idx = pd.date_range("2024-01-01", periods=200, freq="D")
    # tick_size 1, tick_value 1, 1 lote -> 1 US$ por unidad de precio; dist=100 -> un SL cuesta 100 US$
    tr = pd.DataFrame({"res": ["TP", "SL", "TP", "TP", "SL", "TP", "NO"],
                       "R": [3.0, -1.0, 3.0, 3.0, -1.0, 3.0, 0.0],
                       "dist": [100.0] * 7,
                       "i": [0, 10, 20, 30, 40, 50, 60], "salida": [5, 15, 25, 35, 45, 55, 65]})
    # objetivo 5 % de 10.000 = 500 US$. Acumulado: 300, 200, 500 (dia 25 -> retiro), 300, 200, 500 (dia 55 -> retiro)
    o = met_.ciclos_objetivo(tr, idx, 1.0, 1.0, 1.0, 0.0, 10_000.0, 5.0)
    assert o["objetivo_usd"] == 500.0 and len(o["ciclos"]) == 2
    c1, c2 = o["ciclos"]
    assert c1["ops"] == 3 and abs(c1["ganado"] - 500.0) < 1e-9 and abs(c1["min"] - 25 * 1440) < 1e-6
    assert c2["desde"] == idx[25] and c2["hasta"] == idx[55] and abs(c2["min"] - 30 * 1440) < 1e-6
    assert o["resumen"]["n"] == 2 and abs(o["resumen"]["medio"] - 27.5 * 1440) < 1e-6 and o["resumen"]["retirado"] == 1000.0
    assert o["en_curso"]["ops"] == 0 and o["en_curso"]["desde"] == idx[55] and o["en_curso"]["hasta"] == idx[-1]
    # las caidas cuentan: con objetivo del 8 % (800) el acumulado 300, 200, 500, 800 lo alcanza recien en la 4.a operacion
    o8 = met_.ciclos_objetivo(tr, idx, 1.0, 1.0, 1.0, 0.0, 10_000.0, 8.0)
    assert len(o8["ciclos"]) == 1 and o8["ciclos"][0]["ops"] == 4 and abs(o8["ciclos"][0]["ganado"] - 800.0) < 1e-9
    assert o8["en_curso"]["ops"] == 2 and abs(o8["en_curso"]["avance"] - 200.0) < 1e-9
    # sin llegar al objetivo: no hay ciclos y el avance queda en curso
    o9 = met_.ciclos_objetivo(tr, idx, 1.0, 1.0, 1.0, 0.0, 10_000.0, 50.0)
    assert o9["ciclos"] == [] and np.isnan(o9["resumen"]["primero"]) and abs(o9["en_curso"]["avance"] - 1000.0) < 1e-9
    # comision por lote se descuenta de cada operacion
    oc = met_.ciclos_objetivo(tr, idx, 1.0, 1.0, 1.0, 10.0, 10_000.0, 5.0)
    assert oc["ciclos"][0]["ops"] == 4
    # sin operaciones o capital 0
    assert met_.ciclos_objetivo(tr.iloc[0:0], idx, 1.0, 1.0, 1.0, 0.0, 10_000.0)["ciclos"] == []
    assert met_.ciclos_objetivo(tr, idx, 1.0, 1.0, 1.0, 0.0, 0.0)["ciclos"] == []


# ------------------------------------------------- SMA y modo "precio"
def _cruces_manual(c, a, b, warm):
    """Cruces de 'a' sobre 'b' (alcista) calculados aparte, solo con numpy."""
    d = a - b
    out = []
    for i in range(warm, len(c)):
        if np.isnan(d[i]) or np.isnan(d[i - 1]):
            continue
        if d[i] > 0 and d[i - 1] <= 0:
            out.append((i, 1))
        elif d[i] < 0 and d[i - 1] >= 0:
            out.append((i, -1))
    return out


def test_cruce_de_sma_contra_calculo_manual():
    df = _df()
    c = df["Close"].to_numpy(float)
    cfg = eng.Config(media_tipo="sma", ema_corta=20, ema_larga=50)
    P = eng.preparar(df, cfg)
    esperado = _cruces_manual(c, ind.sma(c, 20), ind.sma(c, 50), 51)
    assert [(i, l) for i, l, _ in P.cruces] == esperado and len(esperado) > 20
    assert np.allclose(P.ema_c[50:], ind.sma(c, 20)[50:]) and np.allclose(P.ema_l[50:], ind.sma(c, 50)[50:])


def test_modo_precio_cruza_una_sola_media():
    df = _df()
    c = df["Close"].to_numpy(float)
    for tipo, fn in (("sma", ind.sma), ("ema", ind.ema)):
        cfg = eng.Config(media_tipo=tipo, modo_senal="precio", media_unica=40)
        P = eng.preparar(df, cfg)
        m = fn(c, 40)
        assert [(i, l) for i, l, _ in P.cruces] == _cruces_manual(c, c, m, 41), tipo
        assert P.ema_c is P.ema_l                      # el pullback usa la misma media como referencia
    # el cierre de la vela del cruce queda del lado correcto de la media
    P = eng.preparar(df, eng.Config(media_tipo="sma", modo_senal="precio", media_unica=40))
    m = ind.sma(c, 40)
    assert all((c[i] - m[i]) * lado > 0 for i, lado, _ in P.cruces)


def test_modos_nuevos_no_cambian_el_comportamiento_por_defecto():
    df = _df()
    base = eng.Config(sma_activo=True, adx_activo=True)
    a = eng.ejecutar(eng.preparar(df, base), base).trades
    b_cfg = replace(base, media_tipo="ema", modo_senal="cruce", media_unica=99)      # media_unica no interviene en "cruce"
    b = eng.ejecutar(eng.preparar(df, b_cfg), b_cfg).trades
    pd.testing.assert_frame_equal(a, b)
    assert len(a) > 10


def test_modo_precio_con_pullback_filtros_y_sin_look_ahead():
    df = _df(5000)
    cfg = eng.Config(media_tipo="sma", modo_senal="precio", media_unica=30, sma_activo=True, sma_periodo=100,
                     adx_activo=True, pullback_activo=True, pullback_pct=40.0, pullback_velas=8)
    full = eng.preparar(df, cfg)
    r = eng.ejecutar(full, cfg)
    assert r.cruces == r.tomados + sum(r.descartes.values()) and r.cruces > 20
    assert r.pb["ordenes"] > 0 and r.pb["llenadas"] > 0
    for k in (1500, 3000):
        pref = eng.preparar(df.iloc[:k], cfg)
        assert pref.cruces == [x for x in full.cruces if x[0] < k], k


def test_validacion_de_media_y_modo():
    import pytest
    with pytest.raises(ValueError, match="SMA corta"):
        eng.Config(media_tipo="sma", ema_corta=50, ema_larga=20).validar()
    with pytest.raises(ValueError, match="EMA corta"):
        eng.Config(ema_corta=50, ema_larga=20).validar()
    eng.Config(modo_senal="precio", ema_corta=50, ema_larga=20).validar()       # en "precio" no importa corta < larga
    with pytest.raises(ValueError):
        eng.Config(modo_senal="precio", media_unica=1).validar()
    with pytest.raises(ValueError):
        eng.Config(media_tipo="wma").validar()
    with pytest.raises(ValueError):
        eng.Config(modo_senal="otro").validar()


# ---------------------------------------------------------------- salida por señal (sin TP)
def _P_senal(c, diff, sp=None, h=None, l=None, dist=2.0):
    n = len(c)
    c = np.asarray(c, float)
    h = c + 0.5 if h is None else np.asarray(h, float)
    l = c - 0.5 if l is None else np.asarray(l, float)
    return eng.Preparado(h, l, c, np.zeros(n) if sp is None else np.asarray(sp, float), np.full(n, 1.0), np.full(n, dist),
                         pd.date_range("2024-01-01", periods=n, freq="5min"), [], 0.0, diff=np.asarray(diff, float))


def test_salida_senal_largo_sale_al_cierre_del_otro_lado():
    P = _P_senal([100, 101, 103, 105, 104, 99], [1, 1, 1, 1, 1, -1])
    tr, _ = eng.simular(P, [(0, 1)], 2.0, 0.0, None, "senal")
    f = tr.iloc[0]
    assert f["motivo"] == "senal" and f["salida"] == 5 and f["res"] == "SL"
    assert abs(f["R"] - (99 - 100) / 2.0) < 1e-9 and np.isnan(f["tp"])


def test_salida_senal_ganadora_y_corto_con_spread():
    P = _P_senal([100, 99, 97, 95, 96, 101], [-1, -1, -1, -1, -1, 1], sp=[0.2] * 6)
    tr, _ = eng.simular(P, [(0, -1)], 2.0, 0.0, None, "senal")
    f = tr.iloc[0]
    assert f["res"] == "SL" and f["salida"] == 5      # sale a 101+0.2: pierde
    P2 = _P_senal([100, 99, 97, 95, 96], [-1, -1, -1, -1, 1], sp=[0.2] * 5, dist=10.0)
    f2 = eng.simular(P2, [(0, -1)], 2.0, 0.0, None, "senal")[0].iloc[0]
    assert f2["res"] == "TP" and abs(f2["R"] - (100 - 96.2) / 10.0) < 1e-9


def test_salida_senal_el_sl_tiene_prioridad_en_la_misma_vela():
    P = _P_senal([100, 101, 99], [1, 1, -1], l=[99.5, 100.5, 90.0], dist=2.0)
    f = eng.simular(P, [(0, 1)], 2.0, 0.0, None, "senal")[0].iloc[0]
    assert f["motivo"] == "sl" and f["R"] == -1.0 and f["salida"] == 2


def test_salida_senal_no_mira_la_vela_de_entrada_y_sigue_abierta():
    P = _P_senal([100, 101, 102, 103], [-1, 1, 1, 1])     # la vela 0 (entrada) ya estaba del otro lado: no cuenta
    f = eng.simular(P, [(0, 1)], 2.0, 0.0, None, "senal")[0].iloc[0]
    assert f["res"] == "ABIERTA"


def test_salida_senal_extremo_a_extremo_con_config_precio():
    idx = pd.date_range("2024-01-01", periods=600, freq="5min")
    rng = np.random.default_rng(5)
    c = 2000 + np.cumsum(rng.normal(0, 1.5, 600))
    df = pd.DataFrame({"Open": c, "High": c + 1, "Low": c - 1, "Close": c, "Volume": 1.0}, index=idx)
    cfg = eng.Config(media_tipo="sma", modo_senal="precio", media_unica=50, salida_modo="senal", sl_valor=3.0,
                     spread="ninguno")
    r = eng.ejecutar(eng.preparar(df, cfg), cfg)
    t = r.trades
    assert len(t) > 3 and set(t["motivo"]) <= {"senal", "sl", ""}
    assert (t.loc[t["motivo"] == "sl", "R"] == -1.0).all()
    s = t[t["motivo"] == "senal"]
    assert len(s) and (s["R"] > -1.0 - 1e-9).all()
    cfg2 = eng.Config(media_tipo="sma", modo_senal="precio", media_unica=50, salida_modo="rr", sl_valor=3.0, spread="ninguno")
    r2 = eng.ejecutar(eng.preparar(df, cfg2), cfg2)
    assert set(r2.trades["motivo"]) <= {"tp", "sl", ""}


def test_salida_senal_valida_y_resumen_usa_pago_observado():
    try:
        eng.Config(salida_modo="x").validar()
        assert False, "debia rechazar"
    except ValueError:
        pass
    eng.Config(salida_modo="senal", rr=0.5).validar()
    tr = pd.DataFrame({"res": ["TP", "TP", "SL"], "R": [3.0, 1.0, -1.0], "amb": [False] * 3, "motivo": ["senal"] * 3})
    assert abs(met.resumen(tr, 5.0)["%equilibrio"] - 100 / (1 + 2.0)) < 1e-9


# ---------------------------------------------------------------- reglas de cuenta
def _P_cuenta(n=40, dias=None, d_sl=10.0):
    c = np.full(n, 100.0)
    P = eng.Preparado(c + 0.5, c - 0.5, c, np.zeros(n), np.full(n, 1.0), np.full(n, d_sl),
                      pd.date_range("2024-01-02 00:00", periods=n, freq="5min"), [], 0.0,
                      dia=np.asarray(dias if dias is not None else [0] * n, dtype="int64"),
                      diff=np.ones(n))
    return P


def _cuenta(**k):
    base = dict(capital=10000.0, vu=10.0, comision=0.0, p_dia=0.0, modo_dia="trailing", p_tot=0.0, modo_tot="estatico",
                proteger=False, riesgo_pct=None, pausa_min=None)
    base.update(k)
    return base


def _pierde(P, idx):
    """Hace que una señal larga en idx pierda en la vela siguiente (el SL esta a 10 por debajo)."""
    P.l[idx + 1] = 89.0


def test_cuenta_limite_diario_bloquea_el_resto_del_dia_y_se_libera_al_siguiente():
    dias = [0] * 20 + [1] * 20
    P = _P_cuenta(dias=dias)
    for i in (0, 3, 6, 9, 22):
        _pierde(P, i)
    tr, _ = eng.simular(P, [(0, 1), (3, 1), (6, 1), (9, 1), (22, 1)], 2.0, 0.0, None, "rr", _cuenta(p_dia=3.0))
    cs = tr.attrs["cuenta"]
    assert len(tr) == 4 and list(tr["señal"]) == [0, 3, 6, 22]
    assert cs["saltadas_dia"] == 1 and cs["dias_bloqueados"] == 1 and not cs["quemada"]
    assert abs(cs["balance_final"] - (10000 - 400)) < 1e-6 and abs(cs["peor_dia_usd"] + 300) < 1e-6


def test_cuenta_limite_total_estatico_quema_la_cuenta_y_corta():
    P = _P_cuenta()
    for i in (0, 3, 6, 9):
        _pierde(P, i)
    tr, _ = eng.simular(P, [(0, 1), (3, 1), (6, 1), (9, 1)], 2.0, 0.0, None, "rr", _cuenta(p_tot=2.5))
    cs = tr.attrs["cuenta"]
    assert len(tr) == 3 and cs["quemada"] and cs["quemada_en"] == 7        # piso 9750: 3 perdidas de 100 lo cruzan


def test_ema_cruce_con_salida_por_cruce_contrario():
    # EMA de cruce con "TP = cruce contrario": se sale en la primera vela en que la corta queda del otro lado de la larga
    df = _df()
    cfg = eng.Config(media_tipo="ema", modo_senal="cruce", ema_corta=13, ema_larga=34, salida_modo="senal",
                     sl_modo="atr", sl_valor=1.5)
    P = eng.preparar(df, cfg)
    tr = eng.ejecutar(P, cfg).trades
    ss = tr[tr["motivo"] == "senal"]
    assert len(ss) > 10 and set(tr["motivo"]) <= {"sl", "senal"}
    ec, el = P.ema_c, P.ema_l
    for _, f in ss.iterrows():
        lado, i, j = int(f["lado"]), int(f["i"]), int(f["salida"])
        assert lado * (ec[j] - el[j]) < 0                                   # el cruce se invirtio en la vela de salida
        assert all(lado * (ec[k] - el[k]) >= 0 for k in range(i + 1, j))    # y no antes
    # sin elegir la salida por cruce contrario, la EMA de siempre no cambia: TP fijo, sin motivo "senal"
    base = eng.Config(media_tipo="ema", ema_corta=13, ema_larga=34)
    assert "senal" not in set(eng.ejecutar(eng.preparar(df, base), base).trades["motivo"])


@pytest.mark.parametrize("ref,pb", [("larga", False), ("corta", False), ("larga", True), ("corta", True), ("cruce", False), ("cruce", True)])
def test_sl_anclado_a_la_media_nivel_fijo_y_r_consistente(ref, pb):
    df = _df()
    cfg = eng.Config(ema_corta=13, ema_larga=34, sl_modo="ema", sl_valor=2.0, sl_ema_ref=ref, rr=2.0,
                     pullback_activo=pb, pullback_pct=40.0, pullback_velas=8)
    P = eng.preparar(df, cfg)
    tr = eng.ejecutar(P, cfg).trades
    assert len(tr) > 20
    lado = tr["lado"].to_numpy()
    base = (tr["i"] - 1 if pb else tr["señal"]).to_numpy()            # media conocida al entrar: la de la vela anterior al llenado
    media = (P.ema_c + P.ema_l) / 2.0 if ref == "cruce" else (P.ema_c if ref == "corta" else P.ema_l)
    assert np.allclose(tr["sl"].to_numpy(), media[base] - lado * 2.0)                      # nivel = media -/+ distancia
    assert (tr["dist"] > 0).all() and np.allclose(tr["dist"].to_numpy(), lado * (tr["entrada"].to_numpy() - tr["sl"].to_numpy()))
    tp = tr[tr["res"] == "TP"]
    assert len(tp) and np.allclose(tp["R"].to_numpy(), 2.0)                                # el RR se mide sobre esa distancia
    assert np.allclose(tp["tp"].to_numpy(), tp["entrada"].to_numpy() + tp["lado"].to_numpy() * 2.0 * tp["dist"].to_numpy())


def test_sl_anclado_a_la_media_del_lado_equivocado_no_se_opera():
    import pytest
    from dataclasses import replace
    df = _df()
    cfg = eng.Config(ema_corta=13, ema_larga=34, sl_modo="ema", sl_valor=1.0, direccion="largos", rr=2.0)
    P = eng.preparar(df, cfg)
    n_senales = sum(1 for _, _, m in P.cruces if m is None)
    arriba = replace(P, sl_ref=P.c + 50.0)                           # media 50 por encima del precio: el SL de un largo quedaria al reves
    r = eng.ejecutar(arriba, cfg)
    assert r.trades.empty and r.trades.attrs["sl_invalido"] == n_senales > 0
    normal = eng.ejecutar(P, cfg)
    assert normal.trades.attrs["sl_invalido"] <= n_senales and len(normal.trades) > 0
    # validaciones
    for k in (dict(sl_valor=-1.0), dict(sl_ema_ref="otra")):
        with pytest.raises(ValueError):
            eng.preparar(df.iloc[:500], eng.Config(sl_modo="ema", **{"sl_valor": 1.0, **k}))
    eng.preparar(df.iloc[:500], eng.Config(sl_modo="ema", sl_valor=0.0))       # distancia 0: el SL justo en la media


def test_sl_anclado_a_la_media_en_modo_precio_usa_la_unica_media_y_el_veredicto_lo_cuenta():
    df = _df()
    cfg = eng.Config(media_tipo="sma", modo_senal="precio", media_unica=50, sl_modo="ema", sl_valor=1.5, rr=2.0)
    P = eng.preparar(df, cfg)
    tr = eng.ejecutar(P, cfg).trades
    assert len(tr) > 10 and np.allclose(tr["sl"].to_numpy(), P.sl_ref[tr["señal"].to_numpy()] - tr["lado"].to_numpy() * 1.5)
    for sal, esperado in (("rr", "TP a 1:2"), ("senal", "sin TP fijo")):
        c2 = eng.Config(media_tipo="sma", modo_senal="precio", media_unica=50, sl_modo="ema", sl_valor=1.5, rr=2.0, salida_modo=sal)
        txt = vd.describir(c2, "XAUUSD", "M5", df.index[0], df.index[-1], 12.0, 0.1, 100.0, 80, 20, 60, 0.1, 500.0)
        assert "SL a 1,50 de precio de la SMA 50" in txt and esperado in txt, txt
    c3 = eng.Config(ema_corta=13, ema_larga=34, sl_modo="ema", sl_valor=2.0, sl_ema_ref="corta")
    assert "EMA corta (13)" in vd.describir(c3, "XAUUSD", "M5", df.index[0], df.index[-1], 12.0, 0.1, 100.0, 80, 20, 60, 0.1, 500.0)


def test_cuenta_registra_cuanto_llego_a_ganar_antes_de_quemarse():
    P = _P_cuenta()
    P.h[2] = 125.0                                   # la primera señal gana 200 (balance maximo 10200)
    for i in (3, 6, 9, 12):
        _pierde(P, i)                                # cuatro perdidas de 100: 10200 -> 9800
    tr, _ = eng.simular(P, [(0, 1), (3, 1), (6, 1), (9, 1), (12, 1)], 2.0, 0.0, None, "rr", _cuenta(p_tot=1.5))
    cs = tr.attrs["cuenta"]
    assert cs["quemada"] and abs(cs["balance_max"] - 10200.0) < 1e-6 and 9800.0 - 1e-6 <= cs["balance_final"] <= 9850.0 + 1e-6
    # sin ganancias previas, el maximo es el capital inicial
    P2 = _P_cuenta()
    for i in (0, 3, 6, 9):
        _pierde(P2, i)
    cs2 = eng.simular(P2, [(0, 1), (3, 1), (6, 1), (9, 1)], 2.0, 0.0, None, "rr", _cuenta(p_tot=2.5))[0].attrs["cuenta"]
    assert cs2["quemada"] and cs2["balance_max"] == 10000.0


def test_cuenta_limite_total_trailing_sube_con_el_maximo():
    P = _P_cuenta()
    P.h[2] = 125.0                                   # señal 0 gana: TP a 100+20=120 (RR 2)
    for i in (3, 6):
        _pierde(P, i)
    c_t = _cuenta(p_tot=2.5, modo_tot="trailing")
    tr, _ = eng.simular(P, [(0, 1), (3, 1), (6, 1)], 2.0, 0.0, None, "rr", c_t)
    cs = tr.attrs["cuenta"]
    # tras ganar 200: balance 10200, piso 10200*0.975 = 9945; dos perdidas dejan 10000 (> piso): sigue viva
    assert len(tr) == 3 and not cs["quemada"]
    c_e = _cuenta(p_tot=2.5, modo_tot="estatico")
    assert not eng.simular(P, [(0, 1), (3, 1), (6, 1)], 2.0, 0.0, None, "rr", c_e)[0].empty


def test_cuenta_proteccion_del_sl_y_cierre_forzado_por_limite():
    P = _P_cuenta()
    for i in (0, 3):
        _pierde(P, i)
    # piso diario 9850 (1,5 %): tras perder 100 quedan 9900; abrir arriesga otros 100 -> 9800 <= 9850
    prot = eng.simular(P, [(0, 1), (3, 1)], 2.0, 0.0, None, "rr", _cuenta(p_dia=1.5, proteger=True))
    assert len(prot[0]) == 1 and prot[0].attrs["cuenta"]["saltadas_proteccion"] == 1
    sin = eng.simular(P, [(0, 1), (3, 1)], 2.0, 0.0, None, "rr", _cuenta(p_dia=1.5, proteger=False))[0]
    f = sin.iloc[1]
    assert f["motivo"] == "limite" and abs(f["R"] + 0.5) < 1e-9          # margen US$50 = 5 de precio = 0,5 R
    assert abs(sin.attrs["cuenta"]["balance_final"] - 9850) < 1e-6 and sin.attrs["cuenta"]["forzadas"] == 1


def test_cuenta_riesgo_por_operacion_saltea_si_supera_el_porcentaje():
    P = _P_cuenta()
    _pierde(P, 0)
    solo = eng.simular(P, [(0, 1)], 2.0, 0.0, None, "rr", _cuenta(riesgo_pct=0.5))
    assert len(solo[0]) == 0 and solo[0].attrs["cuenta"]["saltadas_riesgo"] == 1
    assert len(eng.simular(P, [(0, 1)], 2.0, 0.0, None, "rr", _cuenta(riesgo_pct=1.0))[0]) == 1     # 100 / 10000 = 1 %


def test_cuenta_pausa_tras_perdida_descarta_las_señales_dentro_del_tiempo():
    P = _P_cuenta()
    _pierde(P, 0)
    tr, _ = eng.simular(P, [(0, 1), (3, 1), (9, 1)], 2.0, 0.0, None, "rr", _cuenta(pausa_min=30.0))
    assert list(tr["señal"]) == [0, 9] and tr.attrs["cuenta"]["saltadas_pausa"] == 1     # 10 min < 30 < 40 min
    P2 = _P_cuenta()
    P2.h[2] = 125.0                                                                       # una ganadora no activa la pausa
    tr2, _ = eng.simular(P2, [(0, 1), (3, 1)], 2.0, 0.0, None, "rr", _cuenta(pausa_min=30.0))
    assert len(tr2) == 2


def test_cuenta_balance_coincide_con_las_operaciones_y_comision():
    P = _P_cuenta()
    P.h[2] = 125.0
    _pierde(P, 3)
    tr, _ = eng.simular(P, [(0, 1), (3, 1)], 2.0, 0.0, None, "rr", _cuenta(comision=7.0, p_dia=50.0, p_tot=50.0))
    esperado = 10000 + float((tr["R"] * tr["dist"] * 10.0 - 7.0).sum())
    assert abs(tr.attrs["cuenta"]["balance_final"] - esperado) < 1e-6


def test_cuenta_con_limites_en_cero_y_sin_protecciones_no_cambia_nada():
    idx = pd.date_range("2024-01-01", periods=1500, freq="5min")
    rng = np.random.default_rng(9)
    c = 2000 + np.cumsum(rng.normal(0, 1.5, 1500))
    df = pd.DataFrame({"Open": c, "High": c + 1, "Low": c - 1, "Close": c, "Volume": 1.0}, index=idx)
    base = dict(ema_corta=9, ema_larga=21, sl_valor=3.0, spread="ninguno")
    a = eng.ejecutar(eng.preparar(df, eng.Config(**base)), eng.Config(**base)).trades
    cfg = eng.Config(**base, reglas_activas=True, capital=25000.0, usd_por_unidad=10.0, perd_dia_pct=0.0, perd_tot_pct=0.0,
                     proteger_sl=False)
    r = eng.ejecutar(eng.preparar(df, cfg), cfg)
    assert r.cuenta["dias_bloqueados"] == 0 and not r.cuenta["quemada"]
    pd.testing.assert_frame_equal(a.reset_index(drop=True), r.trades.reset_index(drop=True))


def test_cuenta_reglas_validan_y_limites_efectivos():
    cfg = eng.Config(perd_dia_pct=5.0, perd_tot_pct=10.0, colchon_pct=1.0)
    assert cfg.limites_efectivos() == (4.0, 9.0)
    assert eng.Config(perd_dia_pct=0.0, perd_tot_pct=10.0).limites_efectivos() == (0.0, 9.0)
    for kw in (dict(colchon_pct=5.0), dict(perd_dia_modo="x"), dict(colchon_pct=-1.0),
               dict(reglas_activas=True, capital=0.0, usd_por_unidad=1.0),
               dict(riesgo_op_activo=True, riesgo_op_pct=0.0)):
        try:
            eng.Config(**kw).validar()
            assert False, kw
        except ValueError:
            pass


def test_claves_dia_cortan_a_medianoche_de_europa_central():
    idx = pd.DatetimeIndex(["2026-11-03 00:30", "2026-11-03 01:00", "2026-11-03 23:30"])
    cfg = eng.Config(servidor_offset_horas=2.0, servidor_dst_eeuu=True)     # servidor UTC+2 en invierno; CET = UTC+1
    k = eng.claves_dia(idx, cfg)
    assert k[0] == k[1] - 1 and k[1] == k[2]                                # 00:30 servidor = 23:30 CET del dia anterior
    k2 = eng.claves_dia(idx, eng.Config())                                  # sin desfase: dia de los datos
    assert k2[0] == k2[1] == k2[2]


@pytest.mark.parametrize("ref,pb", [("cruce", False), ("cruce", True), ("larga", False)])
def test_sl_anclado_en_porcentaje_del_nivel(ref, pb):
    df = _df()
    cfg = eng.Config(ema_corta=13, ema_larga=34, sl_modo="ema", sl_valor=0.2, sl_ema_pct=True, sl_ema_ref=ref, rr=2.0,
                     pullback_activo=pb, pullback_pct=40.0, pullback_velas=8)
    P = eng.preparar(df, cfg)
    tr = eng.ejecutar(P, cfg).trades
    assert len(tr) > 20
    lado = tr["lado"].to_numpy()
    base = (tr["i"] - 1 if pb else tr["señal"]).to_numpy()
    media = (P.ema_c + P.ema_l) / 2.0 if ref == "cruce" else P.ema_l
    nivel = media[base] - lado * media[base] * 0.2 / 100.0                      # nivel -/+ 0,2 % del propio nivel
    assert np.allclose(tr["sl"].to_numpy(), nivel)
    assert (tr["dist"] > 0).all()
    tp = tr[tr["res"] == "TP"]
    assert len(tp) and np.allclose(tp["R"].to_numpy(), 2.0)


def test_sl_en_porcentaje_equivale_a_precio_cuando_coinciden():
    # con el mismo desplazamiento en unidades de precio, los dos modos dan el mismo SL
    df = _df()
    P_pct = eng.preparar(df, eng.Config(sl_modo="ema", sl_valor=0.1, sl_ema_pct=True, sl_ema_ref="cruce"))
    off = np.abs(P_pct.sl_ref) * 0.1 / 100.0
    assert isinstance(P_pct.sl_off, np.ndarray) and np.allclose(P_pct.sl_off, off, equal_nan=True)
    P_px = eng.preparar(df, eng.Config(sl_modo="ema", sl_valor=2.0, sl_ema_ref="cruce"))
    assert P_px.sl_off == 2.0


# ---------------------------------------------------------------- retiros dentro de la cuenta
def _gana(P, idx):
    P.h[idx + 1] = 200.0


def _corre(P, señales, **k):
    tr, _ = eng.simular(P, [(i, 1) for i in señales], 2.0, 0.0, None, "rr", _cuenta(**k))
    return tr, tr.attrs["cuenta"]


def test_retiro_saca_toda_la_ganancia_del_ciclo_y_no_cuenta_como_perdida_del_dia():
    P = _P_cuenta()
    for i in (0, 3, 6):
        _gana(P, i)
    tr, cs = _corre(P, (0, 3, 6), retiro_usd=300.0, p_dia=3.0)
    assert [x["monto"] for x in cs["retiros"]] == [400.0] and abs(cs["retirado"] - 400.0) < 1e-9
    assert cs["retiros"][0]["j"] == 4                       # sale en la vela de salida de la 2da ganadora
    assert abs(cs["balance_final"] - 10200.0) < 1e-6        # tras el retiro arranco otro ciclo con la 3ra ganadora
    assert cs["peor_dia_usd"] == 0.0 and cs["dias_bloqueados"] == 0 and not cs["quemada"]


def test_sin_retiro_la_cuenta_acumula_y_con_retiro_se_quema_por_perder_el_colchon():
    P = _P_cuenta()
    for i in (0, 3):
        _gana(P, i)
    for i in (6, 9, 12, 15, 18, 21):
        _pierde(P, i)
    señales = (0, 3, 6, 9, 12, 15, 18, 21)
    _, sin = _corre(P, señales, p_tot=5.0)                  # piso estatico 9500: 10400 - 600 = 9800, sobrevive
    assert not sin["quemada"] and abs(sin["balance_final"] - 9800.0) < 1e-6
    _, con = _corre(P, señales, p_tot=5.0, retiro_usd=300.0)    # retira 400 y queda en 10000: 6 perdidas lo llevan a 9400
    assert con["quemada"] and con["retirado"] == 400.0 and len(con["retiros"]) == 1


def test_piso_trailing_se_mantiene_despues_del_retiro():
    P = _P_cuenta()
    for i in (0, 3):
        _gana(P, i)
    for i in (6, 9, 12):
        _pierde(P, i)
    # pico 10400, piso 9880 (5 %): tras retirar el balance es 10000 y la 2da perdida (9800) ya lo toca
    tr, cs = _corre(P, (0, 3, 6, 9, 12), p_tot=5.0, modo_tot="trailing", retiro_usd=300.0)
    assert cs["quemada"] and len(tr) == 4 and cs["quemada_en"] == 10


def test_config_pasa_el_retiro_a_la_cuenta_y_lo_valida():
    cfg = eng.Config(reglas_activas=True, capital=10000.0, usd_por_unidad=10.0, retiro_activo=True, retiro_pct=3.0)
    P = _P_cuenta()
    assert abs(eng.cuenta_de(P, cfg)["retiro_usd"] - 300.0) < 1e-9
    assert eng.cuenta_de(P, eng.Config(reglas_activas=True, capital=10000.0, usd_por_unidad=10.0))["retiro_usd"] is None
    try:
        eng.Config(reglas_activas=True, capital=10000.0, usd_por_unidad=10.0, retiro_activo=True, retiro_pct=0.0).validar()
        assert False
    except ValueError:
        pass


def test_pausa_tras_ganancia_descarta_las_señales_dentro_del_tiempo():
    # velas de 5 min: la 1ra gana y sale en la vela 1; la señal en la vela 3 (10 min despues) cae dentro de 30 min y se descarta,
    # la de la vela 12 (55 min despues) ya no
    P = _P_cuenta(n=40)
    for i in (0, 3, 12):
        _gana(P, i)
    tr, cs = _corre(P, (0, 3, 12), pausa_gan_min=30.0)
    assert list(tr["señal"]) == [0, 12] and cs["saltadas_pausa_gan"] == 1 and cs["saltadas_pausa"] == 0
    tr0, cs0 = _corre(P, (0, 3, 12))
    assert len(tr0) == 3 and cs0["saltadas_pausa_gan"] == 0


def test_pausa_tras_ganancia_no_frena_despues_de_una_perdida_y_config_la_valida():
    P = _P_cuenta(n=40)
    _pierde(P, 0)
    _gana(P, 3)
    tr, cs = _corre(P, (0, 3), pausa_gan_min=30.0)
    assert len(tr) == 2 and cs["saltadas_pausa_gan"] == 0
    cfg = eng.Config(reglas_activas=True, capital=10000.0, usd_por_unidad=10.0, pausa_gan_activa=True, pausa_gan_min=45.0)
    assert eng.cuenta_de(_P_cuenta(), cfg)["pausa_gan_min"] == 45.0
    try:
        eng.Config(reglas_activas=True, capital=10000.0, usd_por_unidad=10.0, pausa_gan_activa=True, pausa_gan_min=-1.0).validar()
        assert False
    except ValueError:
        pass


# ---------------------------------------------------------------- sentido de las pausas tras ganancia / perdida
def _corre_lados(P, señales, **k):
    tr, _ = eng.simular(P, señales, 2.0, 0.0, None, "rr", _cuenta(**k))
    return tr, tr.attrs["cuenta"]


def test_pausa_ganancia_mismo_sentido_frena_solo_el_mismo_lado():
    P = _P_cuenta(n=60)
    _gana(P, 0)
    # compra ganadora en la 0; a los 10 min una compra (frenada) y una venta (pasa)
    tr, cs = _corre_lados(P, [(0, 1), (3, -1)], pausa_gan_min=30.0, pausa_gan_sentido="mismo")
    assert list(tr["lado"]) == [1, -1] and cs["saltadas_pausa_gan"] == 0
    tr, cs = _corre_lados(P, [(0, 1), (3, 1)], pausa_gan_min=30.0, pausa_gan_sentido="mismo")
    assert list(tr["lado"]) == [1] and cs["saltadas_pausa_gan"] == 1


def test_pausa_ganancia_sentido_contrario_frena_solo_el_lado_opuesto():
    P = _P_cuenta(n=60)
    _gana(P, 0)
    tr, cs = _corre_lados(P, [(0, 1), (3, 1)], pausa_gan_min=30.0, pausa_gan_sentido="contrario")
    assert list(tr["lado"]) == [1, 1] and cs["saltadas_pausa_gan"] == 0
    tr, cs = _corre_lados(P, [(0, 1), (3, -1)], pausa_gan_min=30.0, pausa_gan_sentido="contrario")
    assert list(tr["lado"]) == [1] and cs["saltadas_pausa_gan"] == 1


def test_pausa_perdida_sentido_contrario_y_ambos():
    P = _P_cuenta(n=60)
    _pierde(P, 0)
    # compra perdedora: con "contrario" frena una venta, deja pasar otra compra
    tr, cs = _corre_lados(P, [(0, 1), (3, -1)], pausa_min=30.0, pausa_sentido="contrario")
    assert len(tr) == 1 and cs["saltadas_pausa"] == 1
    tr, cs = _corre_lados(P, [(0, 1), (3, 1)], pausa_min=30.0, pausa_sentido="contrario")
    assert len(tr) == 2 and cs["saltadas_pausa"] == 0
    for lado2 in (1, -1):                                    # "ambos" frena las dos, como antes
        tr, cs = _corre_lados(P, [(0, 1), (3, lado2)], pausa_min=30.0)
        assert len(tr) == 1 and cs["saltadas_pausa"] == 1


def test_cada_operacion_arranca_su_propio_reloj_por_sentido():
    P = _P_cuenta(n=80)
    _gana(P, 0)                                              # compra ganadora (reloj de compras)
    # una venta que tambien gana: SL arriba (101+...), TP abajo; la armamos con un minimo bajo
    P.l[7] = 50.0
    tr, cs = _corre_lados(P, [(0, 1), (6, -1), (9, 1)], pausa_gan_min=60.0, pausa_gan_sentido="mismo")
    # la venta de la 6 pasa (no hay venta ganadora previa); la compra de la 9 sigue frenada por la compra ganadora de la 0
    assert list(tr["lado"]) == [1, -1] and cs["saltadas_pausa_gan"] == 1


def test_config_valida_el_sentido_de_la_pausa():
    base = dict(reglas_activas=True, capital=10000.0, usd_por_unidad=10.0)
    assert eng.cuenta_de(_P_cuenta(), eng.Config(**base, pausa_sentido="mismo", pausa_gan_sentido="contrario"))["pausa_sentido"] == "mismo"
    try:
        eng.Config(**base, pausa_sentido="otro").validar()
        assert False
    except ValueError:
        pass


def test_retroceso_tras_ganancia_exige_precio_y_vence():
    # compra ganadora: entrada ~100, el helper arma TP; la señal siguiente solo pasa si el precio bajo del nivel de retroceso
    base = dict(reglas_activas=True, capital=10000.0, usd_por_unidad=10.0)
    cfg = eng.Config(**base, pausa_gan_retroceso_activo=True, pausa_gan_retroceso_pct=50.0)
    ct = eng.cuenta_de(_P_cuenta(), cfg)
    assert ct["gan_retro_pct"] == 50.0 and ct["gan_vence"] == "nunca"
    assert eng.cuenta_de(_P_cuenta(), eng.Config(**base, pausa_gan_activa=True, pausa_gan_retroceso_pct=50.0))["gan_retro_pct"] is None   # retroceso apagado
    for kw in (dict(pausa_gan_retroceso_pct=-1.0), dict(pausa_gan_vence="x"), dict(pausa_gan_vence="horas", pausa_gan_vence_h=0.0)):
        try:
            eng.Config(**base, pausa_gan_retroceso_activo=True, **kw).validar(); assert False
        except ValueError:
            pass
    P = _P_cuenta(n=60)
    _gana(P, 0)
    _gana(P, 12)
    tr, cs = _corre(P, (0, 12), gan_retro_pct=50.0)                  # cierre 120, recorrido 20: nivel 110; el precio (100) ya retrocedio
    assert len(tr) == 2 and cs["saltadas_retroceso"] == 0
    P.c[12] = 118.0                                                  # ahora el precio sigue arriba del nivel
    tr, cs = _corre(P, (0, 12), gan_retro_pct=50.0)
    assert len(tr) == 1 and cs["saltadas_retroceso"] == 1
    tr, cs = _corre(P, (0, 12), gan_retro_pct=50.0, gan_vence="horas", gan_vence_h=0.5)
    assert len(tr) == 2 and cs["saltadas_retroceso"] == 0            # 60 min despues ya vencio
    tr, cs = _corre(P, (0, 12), gan_retro_pct=None)
    assert len(tr) == 2 and cs["saltadas_retroceso"] == 0            # 0 = sin condicion


def _m5_para_tendencia(n=4000, semilla=7):
    idx = pd.date_range("2024-03-04", periods=n, freq="5min")
    c = 2000 + np.cumsum(np.random.default_rng(semilla).normal(0, 0.8, n))
    return pd.DataFrame({"Open": c, "High": c + 0.5, "Low": c - 0.5, "Close": c, "Volume": 1, "Spread": 0}, index=idx)


def test_tendencia_mayor_usa_la_ultima_vela_cerrada_y_no_mira_el_futuro():
    df = _m5_para_tendencia()
    sube, baja, sin = eng.tendencia_mayor(df, "H1", 20)
    cl = df["Close"].resample("60min").last()
    sma = cl.rolling(20).mean()
    for i in (500, 1234, 3999):
        cierre = df.index[i] + pd.Timedelta(minutes=5)
        ok = [t for t in cl.index if t + pd.Timedelta(minutes=60) <= cierre]
        t = ok[-1]                                               # ultima vela H1 que ya cerro al cierre de la vela i
        assert sube[i] == bool(cl[t] > sma[t]) and baja[i] == bool(cl[t] < sma[t])
    assert sin[:100].all() and not sin[-1]                       # al arranque no hay SMA todavia
    # cambiar el futuro no altera lo ya calculado
    df2 = df.copy()
    df2.iloc[2000:, df2.columns.get_loc("Close")] += 500.0
    s2, b2, n2 = eng.tendencia_mayor(df2, "H1", 20)
    assert (s2[:1990] == sube[:1990]).all() and (b2[:1990] == baja[:1990]).all()


def test_tendencia_mayor_filtra_por_sentido_y_valida():
    df = _m5_para_tendencia(6000)
    cfg0 = eng.Config()
    P0 = eng.preparar(df, cfg0)
    P1 = eng.preparar(df, eng.Config(tm1_activo=True, tm1_tf="H1", tm1_periodo=20))
    sube, baja, _ = eng.tendencia_mayor(df, "H1", 20)
    assert len(P1.cruces) == len(P0.cruces)
    for i, lado, motivo in P1.cruces:
        permitido = sube[i] if lado == 1 else baja[i]
        assert (motivo is None) == bool(permitido) or motivo not in (None, "tm1")
    assert any(m == "tm1" for _, _, m in P1.cruces)
    P2 = eng.preparar(df, eng.Config(tm1_activo=True, tm1_tf="H1", tm1_periodo=20, tm2_activo=True, tm2_tf="H4", tm2_periodo=5))
    assert sum(m is None for *_, m in P2.cruces) <= sum(m is None for *_, m in P1.cruces)     # dos filtros nunca dejan pasar mas
    for cfg in (eng.Config(tm1_activo=True, tm1_tf="M5"), eng.Config(tm1_tf="W1"), eng.Config(tm2_periodo=1)):
        with pytest.raises(ValueError):
            eng.preparar(df, cfg)
    P3 = eng.preparar(df.iloc[:600], eng.Config(tm2_activo=True, tm2_tf="H4", tm2_periodo=200))     # historial corto: avisa y descarta
    assert P3.tm_aviso and all(m == "tm2" for *_, m in P3.cruces)


# ---------------------------------------------------------------- Volume Profile
def _m5_vp(dias=16, semilla=11):
    """M5 de lunes a viernes (24 h) mas un par de horas de domingo a la noche, con volumen y rangos variables."""
    rng = np.random.default_rng(semilla)
    partes = [pd.date_range("2024-03-03 22:00", periods=24, freq="5min")]                      # domingo: 2 h (dia casi vacio)
    for d in pd.bdate_range("2024-03-04", periods=dias):
        partes.append(pd.date_range(d, periods=288, freq="5min"))
    idx = partes[0].append(partes[1:]) if len(partes) > 1 else partes[0]
    n = len(idx)
    c = 2000 + np.cumsum(rng.normal(0, 1.2, n))
    h = c + rng.uniform(0.1, 2.5, n)
    l = c - rng.uniform(0.1, 2.5, n)
    return pd.DataFrame({"Open": c, "High": h, "Low": l, "Close": c, "Volume": rng.integers(1, 400, n).astype(float), "Spread": 0.0}, index=idx)


def _vp_referencia(df, esc, N):
    """Version lenta e independiente: reparte cada vela escalon por escalon y arma el area de valor mirando todo el perfil."""
    dia = eng.claves_dia(df.index, eng.Config())
    out = np.full((3, len(df)), np.nan)
    perfiles = {}
    orden = []
    for d in dict.fromkeys(dia):
        m = dia == d
        if m.sum() * 5 < eng.VP_MIN_MINUTOS:
            continue
        p = {}
        for hh, ll, vv in zip(df["High"].values[m], df["Low"].values[m], df["Volume"].values[m]):
            for k in range(int(np.floor(ll / esc)), int(np.floor(hh / esc)) + 1):
                a, b = max(ll, k * esc), min(hh, (k + 1) * esc)
                p[k] = p.get(k, 0.0) + (vv * (b - a) / (hh - ll) if hh > ll else 0.0)
        perfiles[d] = p
        orden.append(d)
    for d in dict.fromkeys(dia):
        previos = [x for x in orden if x < d][-N:]
        if len(previos) < N:
            continue
        tot = {}
        for x in previos:
            for k, vv in perfiles[x].items():
                tot[k] = tot.get(k, 0.0) + vv
        ks = list(range(min(tot), max(tot) + 1))
        vol = [tot.get(k, 0.0) for k in ks]
        poc = int(np.argmax(vol))
        lo = hi = poc
        acum = vol[poc]
        while acum < eng.VP_AREA * sum(vol) and (lo > 0 or hi < len(vol) - 1):
            ar = vol[hi + 1] if hi + 1 < len(vol) else -1
            ab = vol[lo - 1] if lo - 1 >= 0 else -1
            if ar >= ab:
                hi += 1; acum += vol[hi]
            else:
                lo -= 1; acum += vol[lo]
        m = dia == d
        out[0, m], out[1, m], out[2, m] = (ks[poc] + 0.5) * esc, (ks[hi] + 1) * esc, ks[lo] * esc
    return out


def test_vp_reparte_el_volumen_de_una_vela_y_arma_el_area_de_valor():
    k0, v = eng._perfil_dia(np.array([4002.6]), np.array([4000.3]), np.array([120.0]), 1.0)
    assert k0 == 4000 and np.allclose(v, [120 * 0.7 / 2.3, 120 / 2.3, 120 * 0.6 / 2.3]) and abs(v.sum() - 120) < 1e-9
    k0, v = eng._perfil_dia(np.array([4001.5]), np.array([4001.5]), np.array([50.0]), 1.0)      # vela sin rango: entera a su escalon
    assert k0 == 4001 and v[0] == pytest.approx(50.0)
    # perfil del ejemplo: POC = 3er escalon; area de valor = escalones 2 a 5
    assert eng._area_valor(np.array([80, 150, 260, 210, 170, 90, 40.0])) == (2, 1, 4)


@pytest.mark.parametrize("esc,N", [(1.0, 1), (2.0, 3), (0.5, 2)])
def test_vp_niveles_coinciden_con_la_referencia_lenta(esc, N):
    df = _m5_vp()
    (poc, vah, val), sin = eng.niveles_vp(df, eng.Config(vp_activo=True, vp_dias=N, vp_escalon=esc))
    ref = _vp_referencia(df, esc, N)
    assert not sin
    assert np.array_equal(np.isnan(poc), np.isnan(ref[0]))
    ok = ~np.isnan(poc)
    assert ok.sum() > 1000
    assert np.allclose(poc[ok], ref[0][ok]) and np.allclose(vah[ok], ref[1][ok]) and np.allclose(val[ok], ref[2][ok])
    assert (val[ok] < poc[ok]).all() and (poc[ok] < vah[ok]).all()


def test_vp_no_mira_el_futuro_y_el_domingo_no_cuenta_como_dia():
    df = _m5_vp()
    cfg = eng.Config(vp_activo=True, vp_dias=1)
    (poc, vah, val), _ = eng.niveles_vp(df, cfg)
    dia = eng.claves_dia(df.index, cfg)
    # el primer dia (domingo, 2 h) y el lunes no tienen perfil previo valido; el martes usa solo el lunes
    assert np.isnan(poc[dia == dia[0]]).all()
    lunes = dia == np.unique(dia)[1]
    assert np.isnan(poc[lunes]).all()
    # cambiar un dia y los siguientes no altera los niveles de ese dia ni de los anteriores
    d_corte = np.unique(dia)[8]
    df2 = df.copy()
    f = dia >= d_corte
    for k in ("High", "Low", "Close", "Open"):
        df2.loc[f, k] += 300.0
    df2.loc[f, "Volume"] *= 7
    (poc2, vah2, val2), _ = eng.niveles_vp(df2, cfg)
    antes = dia <= d_corte
    assert np.array_equal(poc[antes], poc2[antes], equal_nan=True) and np.array_equal(val[antes], val2[antes], equal_nan=True)
    assert not np.allclose(poc[~antes], poc2[~antes], equal_nan=True)


def test_vp_modos_filtran_por_posicion_y_validan():
    df = _m5_vp(40, semilla=5)
    P0 = eng.preparar(df, eng.Config())
    res = {}
    for modo in eng.VP_MODOS:
        cfg = eng.Config(vp_activo=True, vp_modo=modo, vp_dias=1, servidor_offset_horas=2.0)
        P = eng.preparar(df, cfg)
        assert len(P.cruces) == len(P0.cruces) and P.vp is not None
        poc, vah, val = P.vp
        for i, lado, m in P.cruces:
            if np.isnan(poc[i]):
                ok = False
            elif modo == "poc":
                ok = (P.c[i] - poc[i]) * lado > 0
            elif modo == "fuera":
                ok = P.c[i] > vah[i] if lado == 1 else P.c[i] < val[i]
            else:
                ok = val[i] <= P.c[i] <= vah[i]
            assert (m is None) == bool(ok) or m not in (None, "vp")
        assert any(m == "vp" for *_, m in P.cruces)
        res[modo] = sum(m is None for *_, m in P.cruces)
    assert res["fuera"] <= res["poc"]                       # fuera del area implica estar del lado correcto del POC
    for cfg in (eng.Config(vp_modo="x"), eng.Config(vp_dias=0), eng.Config(vp_escalon=0), eng.Config(vp_activo=True)):   # la ultima: sin desfase del servidor
        with pytest.raises(ValueError):
            eng.preparar(df, cfg)
    P3 = eng.preparar(df.iloc[:400], eng.Config(vp_activo=True, vp_dias=3, servidor_offset_horas=2.0))                    # historial corto: avisa y descarta
    assert P3.tm_aviso and all(m == "vp" for *_, m in P3.cruces)
    P4 = eng.preparar(df.drop(columns="Volume"), eng.Config(vp_activo=True, servidor_offset_horas=2.0))
    assert any("volumen" in a for a in P4.tm_aviso)
