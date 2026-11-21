"""Estrategia de reversion a la media: señales A / B con velas sinteticas, descartes, lote por riesgo fijo, cuenta, validacion por fechas."""
from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

import engine as eng
import reversion as rv_
from test_reentrada import _df


def _vela(n, inicio="2024-01-02 00:00"):
    idx = pd.date_range(inicio, periods=n, freq="5min")
    c = np.full(n, 100.0)
    return idx, c


def _df_de(idx, c, h=None, l=None, spread=0.0):
    h = c + 0.1 if h is None else h
    l = c - 0.1 if l is None else l
    return pd.DataFrame({"Open": c, "High": h, "Low": l, "Close": c, "Volume": 100.0, "Spread": spread}, index=idx)


CFG = dict(lotes=1.0, usd_por_unidad=100.0)          # US$ 100 por 1,00 de precio con 1 lote
RVA = dict(activo=True, variante="A", bb_n=5, bb_k=1.5, adx_periodo=2, adx_max=1e6, atr_periodo=2, sl_atr_x=0.0, tp_modo="media", riesgo_usd=50.0)
RVB = dict(activo=True, variante="B", b_velas=3, adx_periodo=2, atr_periodo=2, sl_atr_x=0.0, tp_modo="media", riesgo_usd=50.0)


def _zigzag(n, base=100.0, amp=0.05):
    c = base + amp * np.where(np.arange(n) % 2 == 0, 1.0, -1.0)
    return c


def _datos_a(salida="tp"):
    """Zigzag alrededor de 100; la vela 30 cierra fuera de la banda superior (101) y la 31 cierra de vuelta adentro (100,3, aun sobre la media): venta."""
    n = 80
    idx = pd.date_range("2024-01-02 00:00", periods=n, freq="5min")
    c = _zigzag(n)
    c[30] = 101.0
    c[31] = 100.3
    h, l = c + 0.1, c - 0.1
    h[30] = 101.1
    if salida == "tp":
        l[32:] = 99.0                         # baja hasta debajo de la media: TP
    else:
        h[32] = 102.0                         # sube sobre el extremo: SL
    return _df_de(idx, c, h, l)


def test_variante_a_señal_de_venta_sl_tp_y_lote():
    df = _datos_a("tp")
    cfg, rv = eng.Config(**CFG), rv_.ConfigRev(**RVA)
    PR = rv_.preparar_rev(df, cfg, rv)
    ven = [(j, lado, m) for j, lado, m in PR.P.cruces if j == 31]
    assert ven == [(31, -1, None)]
    c = df["Close"].to_numpy()
    h = df["High"].to_numpy()
    ma = c[27:32].mean()                                           # media de Bollinger de 5 velas en la vela 31
    d = max(h[30], h[31]) - c[31]                                  # SL en el extremo de las dos velas (x = 0)
    assert PR.P.dist[31] == pytest.approx(d)
    assert PR.tp_dist[31] == pytest.approx(c[31] - ma)
    assert PR.lotes[31] == pytest.approx(np.floor(50.0 / (d * 100.0) / 0.01 + 1e-9) * 0.01)
    assert PR.vu_sig[31] == pytest.approx(PR.lotes[31] * 100.0)
    res = rv_.ejecutar_rev(PR, cfg, rv)
    tr = res.trades
    assert len(tr) == 1 and tr.loc[0, "res"] == "TP" and tr.loc[0, "R"] == pytest.approx((c[31] - ma) / d)
    assert tr.loc[0, "lotes"] == pytest.approx(PR.lotes[31])


def test_variante_a_sl():
    df = _datos_a("sl")
    cfg, rv = eng.Config(**CFG), rv_.ConfigRev(**RVA)
    res = rv_.ejecutar_rev(rv_.preparar_rev(df, cfg, rv), cfg, rv)
    assert len(res.trades) == 1 and res.trades.loc[0, "res"] == "SL" and res.trades.loc[0, "R"] == pytest.approx(-1.0)


def test_variante_a_compra_es_el_espejo():
    df = _datos_a("tp")
    c = _zigzag(len(df))
    c[30], c[31] = 99.0, 99.7
    h, l = c + 0.1, c - 0.1
    l[30] = 98.9
    h[32:] = 101.0
    cfg, rv = eng.Config(**CFG), rv_.ConfigRev(**RVA)
    res = rv_.ejecutar_rev(rv_.preparar_rev(_df_de(df.index, c, h, l), cfg, rv), cfg, rv)
    assert len(res.trades) == 1 and res.trades.loc[0, "lado"] == 1 and res.trades.loc[0, "res"] == "TP"


def test_variante_a_sin_señal_en_mercado_sin_extremos():
    idx = pd.date_range("2024-01-02 00:00", periods=80, freq="5min")
    df = _df_de(idx, _zigzag(80))
    cfg, rv = eng.Config(**CFG), rv_.ConfigRev(**RVA)
    PR = rv_.preparar_rev(df, cfg, rv)
    assert PR.P.cruces == [] and len(rv_.ejecutar_rev(PR, cfg, rv).trades) == 0


def test_variante_a_adx_alto_descarta():
    df = _datos_a("tp")
    cfg = eng.Config(**CFG)
    PR = rv_.preparar_rev(df, cfg, rv_.ConfigRev(**{**RVA, "adx_max": 1e-9}))
    assert [m for j, _, m in PR.P.cruces if j == 31] == ["adx"]


def test_variante_a_rr_fijo_y_tp_invalido():
    df = _datos_a("tp")
    cfg = eng.Config(**CFG)
    PR = rv_.preparar_rev(df, cfg, rv_.ConfigRev(**{**RVA, "tp_modo": "rr", "rr": 1.5}))
    assert PR.tp_dist[31] == pytest.approx(1.5 * PR.P.dist[31])
    # SL fijo en distancia: 0,5 de precio
    PR2 = rv_.preparar_rev(df, cfg, rv_.ConfigRev(**{**RVA, "sl_modo": "precio", "sl_precio": 0.5}))
    assert PR2.P.dist[31] == 0.5 and PR2.lotes[31] == pytest.approx(1.0)


def test_lote_menor_al_minimo_se_salta():
    df = _datos_a("tp")
    cfg = eng.Config(**CFG)
    PR = rv_.preparar_rev(df, cfg, rv_.ConfigRev(**{**RVA, "riesgo_usd": 0.5}))
    assert [m for j, _, m in PR.P.cruces if j == 31] == ["lote"]


def _datos_b(vuelve=True):
    """Dia 1: rango 99-101 (punto medio 100). Dia 2: la vela 10 rompe 101 (maximo 101,5) y la 12 vuelve a cerrar adentro: venta."""
    n = 576
    idx = pd.date_range("2024-01-02 00:00", periods=n, freq="5min")
    c = np.full(n, 100.0)
    h, l = c + 0.1, c - 0.1
    h[50], l[60] = 101.0, 99.0
    k = 288 + 10
    h[k], c[k] = 101.5, 101.3
    if vuelve:
        c[k + 1], h[k + 1] = 101.2, 101.4
        c[k + 2], h[k + 2] = 100.8, 101.0
    else:
        c[k + 1:k + 6], h[k + 1:k + 6] = 101.2, 101.4
    return _df_de(idx, c, h, l), k


def test_variante_b_ruptura_falsa_del_maximo_de_ayer():
    df, k = _datos_b(True)
    cfg, rv = eng.Config(**CFG), rv_.ConfigRev(**RVB)
    PR = rv_.preparar_rev(df, cfg, rv)
    assert [(j, lado, m) for j, lado, m in PR.P.cruces] == [(k + 2, -1, None)]
    d = 101.5 - 100.8                                               # SL en el nuevo extremo
    assert PR.P.dist[k + 2] == pytest.approx(d)
    assert PR.tp_dist[k + 2] == pytest.approx(100.8 - 100.0)       # TP en el punto medio del rango de ayer
    assert PR.lotes[k + 2] == pytest.approx(np.floor(50.0 / (d * 100.0) / 0.01 + 1e-9) * 0.01)


def test_variante_b_sin_vuelta_dentro_de_k_no_hay_señal():
    df, _ = _datos_b(False)
    PR = rv_.preparar_rev(df, eng.Config(**CFG), rv_.ConfigRev(**RVB))
    assert PR.P.cruces == []


def test_variante_b_k_largo_alcanza():
    df, k = _datos_b(False)
    df2 = df.copy()
    df2.iloc[k + 6, df2.columns.get_loc("Close")] = 100.5          # recien a la 6.ª vela vuelve
    assert rv_.preparar_rev(df2, eng.Config(**CFG), rv_.ConfigRev(**RVB)).P.cruces == []
    PR = rv_.preparar_rev(df2, eng.Config(**CFG), rv_.ConfigRev(**{**RVB, "b_velas": 8}))
    assert [(j, l) for j, l, m in PR.P.cruces] == [(k + 6, -1)]


def test_variante_b_la_vela_que_rompe_puede_ser_la_señal():
    df, k = _datos_b(True)
    df = df.copy()
    df.iloc[k, df.columns.get_loc("Close")] = 100.9                # rompe con la mecha y ya cierra adentro
    PR = rv_.preparar_rev(df, eng.Config(**CFG), rv_.ConfigRev(**RVB))
    assert [(j, l) for j, l, m in PR.P.cruces] == [(k, -1)]


def test_variante_b_una_señal_por_lado_por_dia():
    df, k = _datos_b(True)
    df = df.copy()
    df.iloc[k + 20, df.columns.get_loc("High")] = 101.6            # segunda ruptura el mismo dia: no cuenta
    df.iloc[k + 21, df.columns.get_loc("Close")] = 100.0
    PR = rv_.preparar_rev(df, eng.Config(**CFG), rv_.ConfigRev(**RVB))
    assert len(PR.P.cruces) == 1


def test_variante_b_adx_opcional():
    df, k = _datos_b(True)
    cfg = eng.Config(**CFG)
    PR = rv_.preparar_rev(df, cfg, rv_.ConfigRev(**{**RVB, "adx_activo_b": True, "adx_max": 1e-9}))
    assert [m for j, _, m in PR.P.cruces] in (["adx"],)


def test_noticias_descartan_la_entrada_dentro_de_la_ventana():
    df, k = _datos_b(True)
    ev = int(df.index[k + 2].value // 10**9) + 120
    cfg = eng.Config(**CFG, noticias_activo=True, noticias_fuente="csv", noticias_eventos=(ev,), noticias_min=10.0, servidor_offset_horas=0.0,
                     servidor_dst_eeuu=False)
    PR = rv_.preparar_rev(df, cfg, rv_.ConfigRev(**RVB))
    assert [m for _, _, m in PR.P.cruces] == ["noticias"]
    assert rv_.ejecutar_rev(PR, cfg, rv_.ConfigRev(**RVB)).descartes == {"noticias": 1}


def test_sesion_propia_descarta_fuera_de_horario():
    df, k = _datos_b(True)                                          # la señal es a las 00:50 + 288 velas = 01:00 del dia 2 (servidor)
    cfg = eng.Config(**CFG, servidor_offset_horas=0.0, servidor_dst_eeuu=False)
    rv = rv_.ConfigRev(**{**RVB, "sesion_activo": True, "sesiones": ("Tokio",), "horarios": {"Tokio": ("UTC", 12.0, 13.0)}})
    assert [m for _, _, m in rv_.preparar_rev(df, cfg, rv).P.cruces] == ["sesion"]
    rv2 = replace(rv, horarios={"Tokio": ("UTC", 0.0, 3.0)})
    assert [m for _, _, m in rv_.preparar_rev(df, cfg, rv2).P.cruces] == [None]


def test_cuenta_el_resultado_en_dinero_es_r_por_riesgo_de_cada_operacion():
    df = _df(6000)
    df["Spread"] = 0.2
    cfg = eng.Config(lotes=0.5, usd_por_unidad=50.0, reglas_activas=True, capital=100000.0, perd_dia_pct=0, perd_tot_pct=0, proteger_sl=False)
    rv = rv_.ConfigRev(activo=True, variante="A", adx_max=40.0, riesgo_usd=60.0)
    r = rv_.evaluar_rev(df, cfg, rv)
    tr = r["trades"]
    assert len(tr) > 20
    pnl = float((tr["R"] * tr["lotes"] * 0 + tr["R"] * (tr["lotes"] * 100.0 * 0 + 1)).sum())      # R total
    esperado = sum(R * riesgo for R, riesgo in zip(tr["R"], [60.0] * len(tr)))
    # el riesgo real de cada operacion es lotes x distancia x US$ por unidad por lote (redondeado hacia abajo): <= 60
    riesgo_real = tr["lotes"] * (tr["R"] * 0 + 1) * 0
    bal = r["cuenta"]["balance_final"] - 100000.0
    assert bal == pytest.approx(sum(R * lt * d * 100.0 for R, lt, d in zip(tr["R"], tr["lotes"], r["P"].dist[tr["i"].to_numpy()])), rel=1e-9, abs=1e-6)
    assert all(lt * d * 100.0 <= 60.0 + 1e-9 for lt, d in zip(tr["lotes"], r["P"].dist[tr["i"].to_numpy()]))
    assert pnl == pytest.approx(float(tr["R"].sum())) and esperado == pytest.approx(60.0 * float(tr["R"].sum())) and riesgo_real.sum() == 0


def test_validar():
    cfg = eng.Config(**CFG)
    rv_.ConfigRev(**RVA).validar(cfg)
    rv_.ConfigRev(activo=False, variante="Z").validar(cfg)             # apagado: no se valida
    malos = [dict(variante="C"), dict(bb_n=1), dict(bb_k=0), dict(adx_max=0), dict(sl_modo="x"), dict(sl_modo="precio", sl_precio=0),
             dict(tp_modo="rr", rr=0), dict(riesgo_usd=0), dict(prioridad="otra"), dict(val_activa=True),
             dict(val_activa=True, ajuste_desde="2020-01-01", ajuste_hasta="2023-12-31", verif_desde="2023-06-01", verif_hasta="2024-12-31")]
    for k in malos:
        with pytest.raises(ValueError):
            rv_.ConfigRev(**{**RVA, **k}).validar(cfg)
    with pytest.raises(ValueError):
        rv_.ConfigRev(**RVA).validar(eng.Config())                       # sin lote ni valor por unidad
    with pytest.raises(ValueError):
        rv_.ConfigRev(**{**RVA, "sesion_activo": True}).validar(cfg)     # sin desfase horario
    rv_.ConfigRev(**{**RVA, "val_activa": True, "ajuste_desde": "2020-01-01", "ajuste_hasta": "2023-12-31", "verif_desde": "2024-01-01",
                     "verif_hasta": "2026-11-13"}).validar(cfg)


def test_tramos_por_fechas():
    df = _df(30000)
    df["Spread"] = 0.2
    cfg = eng.Config(**CFG)
    rv = rv_.ConfigRev(**{**RVA, "adx_max": 40.0, "val_activa": True, "ajuste_desde": "2024-01-01", "ajuste_hasta": "2024-02-29",
                          "verif_desde": "2024-03-01", "verif_hasta": "2024-04-15"})
    r = rv_.evaluar_rev(df, cfg, rv)
    P = r["P"]
    tr = rv_.tramos(P, rv)
    assert [t[0] for t in tr] == ["Todo", "Ajuste", "Verificación"]
    assert P.indice[tr[1][1]] >= pd.Timestamp("2024-01-01") and P.indice[tr[1][2] - 1] < pd.Timestamp("2024-03-01")
    assert P.indice[tr[2][1]] >= pd.Timestamp("2024-03-01") and P.indice[tr[2][2] - 1] < pd.Timestamp("2024-04-16")
    t = r["tabla"]
    assert t.loc["Ajuste", "resueltas"] + t.loc["Verificación", "resueltas"] <= t.loc["Todo", "resueltas"] + 3


def test_ablacion_primera_fila_es_la_señal_sola():
    df = _df(20000)
    df["Spread"] = 0.2
    cfg = eng.Config(**CFG)
    rv = rv_.ConfigRev(**{**RVA, "adx_max": 30.0, "tstop_activo": True, "be_activo": True})
    ab = rv_.ablacion_rev(df, cfg, rv)
    assert list(ab.index) == ["Señal sola (sin ADX)", "+ ADX máximo", "+ Cierre por tiempo", "+ Breakeven"]
    solo = rv_.ejecutar_rev(rv_.preparar_rev(df, cfg, replace(rv, adx_max=1e9, tstop_activo=False, be_activo=False)), cfg,
                            replace(rv, adx_max=1e9, tstop_activo=False, be_activo=False))
    assert ab.iloc[0]["operaciones"] == len(solo.trades)
    full = rv_.ejecutar_rev(rv_.preparar_rev(df, cfg, rv), cfg, rv)
    assert ab.iloc[-1]["operaciones"] == len(full.trades) and ab.iloc[-1]["R_total"] == pytest.approx(rv_.resumen_rev(full.trades)["R_total"])


def test_gestion_propia_cierre_por_tiempo_y_breakeven():
    df = _datos_a("tp")
    df = df.copy()
    c = df["Close"].to_numpy().copy()
    h, l = df["High"].to_numpy().copy(), df["Low"].to_numpy().copy()
    l[32:] = c[31] - 0.02                                           # la operacion no arranca: queda cerca de la entrada
    h[32:] = c[31] + 0.1
    df = _df_de(df.index, c, h, l)
    cfg = eng.Config(**CFG)
    rv = rv_.ConfigRev(**{**RVA, "tstop_activo": True, "tstop_velas": 3, "tstop_r": 0.5})
    tr = rv_.ejecutar_rev(rv_.preparar_rev(df, cfg, rv), cfg, rv).trades
    assert len(tr) == 1 and tr.loc[0, "motivo"] == "tiempo"


# ---------------------------------------------------------------- el motor con tp_dist / vu_sig no cambia nada si se piden los mismos valores
def test_simular_con_tp_y_vu_por_señal_iguales_a_los_escalares_da_lo_mismo():
    df = _df(12000)
    df["Spread"] = 0.15
    cfg = eng.Config(rr=1.7, reglas_activas=True, capital=50000.0, usd_por_unidad=20.0, comision_op_usd=0.4, perd_dia_pct=3.0, perd_tot_pct=8.0,
                     be_activo=True, be_act_valor=0.7, tstop_activo=True, tstop_velas=10, tstop_r=-0.2)
    P = eng.preparar(df, cfg)
    señales = [(i, lado) for i, lado, m in P.cruces if m is None]
    assert len(señales) > 30
    args = (cfg.rr, cfg.costo_extra, None, "rr", eng.cuenta_de(P, cfg), eng.be_de(cfg), None, None, eng.tstop_de(cfg), eng.noti_de(cfg))
    a, _ = eng.simular(P, señales, *args)
    tp = P.dist * cfg.rr
    vu = np.full(len(P.c), 20.0)
    b, _ = eng.simular(P, señales, *args, tp_dist=tp, vu_sig=vu)
    pd.testing.assert_frame_equal(a, b)
    assert a.attrs["cuenta"] == b.attrs["cuenta"]


def test_simular_con_tp_por_señal_no_acepta_pullback():
    df = _df(3000)
    cfg = eng.Config()
    P = eng.preparar(df, cfg)
    with pytest.raises(ValueError):
        eng.simular(P, [], 2.0, 0.0, {"pct": 50.0, "ema": "corta", "velas": 5}, "rr", None, tp_dist=np.ones(len(P.c)))
