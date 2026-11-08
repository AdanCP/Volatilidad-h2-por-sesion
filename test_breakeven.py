"""Tests del breakeven: simulacion vela por vela, validaciones, pausas y metricas."""
import os
import sys
from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import engine as eng
import metrics as met
import veredicto as vd


def P_manual(h, l, sp=None, c0=100.0, d=2.0):
    n = len(h)
    return eng.Preparado(np.asarray(h, float), np.asarray(l, float), np.full(n, c0),
                         np.zeros(n) if sp is None else np.asarray(sp, float),
                         np.full(n, d), np.full(n, d),
                         pd.date_range("2024-01-01", periods=n, freq="h"), [], 0.0)


def _be(act=1.0, nivel=0.0, am="r", nm="r", vu=10.0):
    return {"act_modo": am, "act_valor": act, "nivel_modo": nm, "nivel_valor": nivel, "vu": vu}


def run(h, l, lado=1, be=None, sp=None, salida="rr", rr=2.0):
    tr, _ = eng.simular(P_manual(h, l, sp), [(0, lado)], rr, 0.0, None, salida, None, be)
    return tr.iloc[0]


# ------------------------------------------------------------- simulacion
def test_largo_activa_y_sale_en_la_entrada():
    # entrada 100, SL 98, TP 104. Activacion a 1R = 102. La vela 1 activa sin volver; la 2 vuelve a la entrada.
    t = run([100, 102.5, 101], [100, 100.5, 99.9], be=_be())
    assert t["res"] == "BE" and t["motivo"] == "be" and t["be"] == 1 and t["salida"] == 2
    assert abs(t["R"]) < 1e-12 and not t["amb"]


def test_sin_breakeven_la_misma_operacion_sigue_abierta():
    t = run([100, 102.5, 101], [100, 100.5, 99.9])
    assert t["res"] == "ABIERTA" and t["be"] == 0


def test_vela_que_activa_y_vuelve_es_breakeven_ambiguo():
    t = run([100, 102.5], [100, 99.8], be=_be())
    assert t["res"] == "BE" and t["amb"] and t["salida"] == 1


def test_vela_que_activa_y_toca_el_sl_original_es_sl():
    t = run([100, 102.5], [100, 97.5], be=_be())
    assert t["res"] == "SL" and t["R"] == -1.0 and t["be"] == 0


def test_activado_sigue_hasta_el_tp():
    t = run([100, 102.5, 104.5], [100, 100.5, 101], be=_be())
    assert t["res"] == "TP" and t["be"] == 1 and t["R"] == 2.0


def test_misma_vela_con_breakeven_y_tp_gana_el_breakeven():
    t = run([100, 102.5, 105], [100, 100.5, 99.5], be=_be())
    assert t["res"] == "BE" and t["amb"]


def test_nivel_positivo_en_r_asegura_ganancia():
    # nivel 0,5 R = 1 de precio -> el SL pasa a 101
    t = run([100, 102.5, 101.5], [100, 101.5, 100.9], be=_be(nivel=0.5))
    assert t["res"] == "BE" and abs(t["R"] - 0.5) < 1e-12


def test_nivel_en_dinero_y_activacion_en_dinero():
    # vu = 10 US$ por unidad de precio: activar con 30 US$ = 3 de precio (103), SL a 10 US$ = 1 de precio sobre la entrada
    t = run([100, 103.2, 100.8], [100, 101.5, 100.5], be=_be(act=30.0, nivel=10.0, am="usd", nm="usd"))
    assert t["res"] == "BE" and abs(t["R"] - 0.5) < 1e-12        # 1 de precio / 2 de distancia del SL


def test_activacion_en_porcentaje_del_camino_al_tp():
    # TP a 4 de distancia: el 50 % es 2 de precio (102)
    t = run([100, 102.2, 100.0], [100, 101.0, 99.9], be=_be(act=50.0, am="pct_tp"))
    assert t["res"] == "BE" and t["be"] == 1


def test_no_activa_si_no_llega_y_sigue_el_sl_normal():
    t = run([100, 101.9, 101], [100, 99, 97.9], be=_be())
    assert t["res"] == "SL" and t["be"] == 0


def test_corto_simetrico():
    # corto: entrada 100 (bid), SL 102, TP 96. Activa en 98 (el ask = minimo + spread). Vuelve a 100 en la vela 2.
    t = run([100, 99.5, 100.2], [100, 97.5, 98.5], lado=-1, be=_be())
    assert t["res"] == "BE" and t["be"] == 1 and abs(t["R"]) < 1e-12


def test_spread_hace_que_el_largo_salga_en_la_entrada_al_ask():
    # entrada al ask = 100,5; activa en 102,5; el SL en 100,5 se toca con el bid (minimo)
    t = run([100, 102.7, 101], [100, 101, 100.4], sp=[0.5] * 3, be=_be())
    assert abs(t["entrada"] - 100.5) < 1e-12 and t["res"] == "BE" and abs(t["R"]) < 1e-12


def test_salida_por_senal_con_breakeven():
    n = 4
    P = P_manual([100, 102.5, 101, 101], [100, 100.5, 99.9, 99.9])
    P.diff = np.ones(n)
    tr, _ = eng.simular(P, [(0, 1)], 2.0, 0.0, None, "senal", None, _be())
    assert tr.iloc[0]["res"] == "BE"


def test_nivel_que_no_queda_por_debajo_de_la_activacion_se_ignora_en_esa_operacion():
    tr, _ = eng.simular(P_manual([100, 102.5, 101], [100, 100.5, 99.9]), [(0, 1)], 2.0, 0.0, None, "rr", None, _be(act=1.0, nivel=1.5))
    assert tr.iloc[0]["res"] == "ABIERTA" and tr.attrs["be_invalidas"] == 1


def test_sin_breakeven_el_resultado_es_el_de_siempre():
    a, _ = eng.simular(P_manual([100, 101, 104.5], [100, 99, 100]), [(0, 1)], 2.0)
    b, _ = eng.simular(P_manual([100, 101, 104.5], [100, 99, 100]), [(0, 1)], 2.0, 0.0, None, "rr", None, None)
    assert a.iloc[0]["res"] == "TP" and a.equals(b) and a.iloc[0]["be"] == 0


# ------------------------------------------------------------- configuracion
def test_validaciones_del_breakeven():
    base = dict(be_activo=True, sl_modo="precio", sl_valor=2.0, usd_por_unidad=10.0)
    eng.Config(**base).validar()                                                 # 1 R / nivel 0 es valido
    for k in (dict(be_nivel_valor=-0.1), dict(be_nivel_valor=1.0), dict(be_act_valor=0.0), dict(be_act_valor=2.0),
              dict(be_act_modo="pct_tp", be_act_valor=100.0), dict(be_act_modo="x"),
              dict(be_act_modo="pct_tp", be_act_valor=50.0, salida_modo="senal"),
              dict(be_act_modo="usd", be_act_valor=10.0, usd_por_unidad=0.0)):
        with pytest.raises(ValueError):
            eng.Config(**{**base, **k}).validar()
    eng.Config(be_activo=False, be_nivel_valor=-5).validar()                     # apagado: no se valida


# ------------------------------------------------------------- cuenta y pausas
def _P_pausa():
    n = 40
    c = np.full(n, 100.0)
    P = eng.Preparado(c + 0.5, c - 0.5, c, np.zeros(n), np.full(n, 1.0), np.full(n, 10.0),
                      pd.date_range("2024-01-02 00:00", periods=n, freq="5min"), [], 0.0,
                      dia=np.zeros(n, dtype="int64"), diff=np.ones(n))
    P.h[1], P.l[1] = 111.0, 100.5          # activa (110) sin volver
    return P                               # la vela 2 vuelve a 100 (minimo 99,5) y cierra en breakeven


def _ct(**k):
    base = dict(capital=10000.0, vu=10.0, comision=7.0, p_dia=0.0, modo_dia="trailing", p_tot=0.0, modo_tot="estatico",
                proteger=False, riesgo_pct=None, pausa_min=30.0, pausa_gan_min=30.0)
    base.update(k)
    return base


def test_breakeven_no_dispara_pausas_y_su_dinero_entra_al_balance():
    tr, _ = eng.simular(_P_pausa(), [(0, 1), (3, 1)], 2.0, 0.0, None, "rr", _ct(), _be())
    assert tr.iloc[0]["res"] == "BE" and len(tr) == 2                          # la segunda señal no se frena
    cs = tr.attrs["cuenta"]
    assert cs["saltadas_pausa"] == 0 and cs["saltadas_pausa_gan"] == 0
    assert abs(cs["balance_final"] - (10000 - 7.0)) < 1e-6                     # 0 R brutos: solo la comision de la operacion cerrada


def test_casilla_que_hace_que_el_breakeven_dispare_la_pausa_tras_perdida():
    tr, _ = eng.simular(_P_pausa(), [(0, 1), (3, 1)], 2.0, 0.0, None, "rr", _ct(be_pausa_perdida=True), _be())
    assert len(tr) == 1 and tr.attrs["cuenta"]["saltadas_pausa"] == 1


def test_breakeven_positivo_no_dispara_pausa_tras_ganancia_ni_retroceso():
    P = _P_pausa()
    tr, _ = eng.simular(P, [(0, 1), (3, 1)], 2.0, 0.0, None, "rr",
                        _ct(gan_retro_pct=50.0, gan_vence="nunca", pausa_min=None), _be(nivel=0.5))
    assert tr.iloc[0]["res"] == "BE" and tr.iloc[0]["R"] == 0.5 and len(tr) == 2
    assert tr.attrs["cuenta"]["saltadas_pausa_gan"] == 0 and tr.attrs["cuenta"]["saltadas_retroceso"] == 0


# ------------------------------------------------------------- metricas
def _tr_mixta():
    return pd.DataFrame({"i": [0, 10, 20, 30], "salida": [5, 15, 25, 35], "res": ["TP", "BE", "TP", "SL"],
                         "R": [2.0, 0.5, 2.0, -1.0], "dist": [2.0] * 4, "amb": [False] * 4, "be": [0, 1, 0, 0],
                         "motivo": ["tp", "be", "tp", "sl"]})


def test_resumen_breakeven_neutro_para_acierto_y_expectativa_incluye_su_dinero():
    r = met.resumen(_tr_mixta(), 2.0)
    assert r["TP"] == 2 and r["SL"] == 1 and r["resueltas"] == 3 and abs(r["%TP"] - 100 * 2 / 3) < 1e-9
    assert r["BE"] == 1 and r["be_activadas"] == 1 and abs(r["be_R"] - 0.5) < 1e-12
    assert abs(r["R_total"] - 3.5) < 1e-12 and abs(r["exp_R"] - 3.5 / 4) < 1e-12


def test_rachas_no_se_cortan_por_el_breakeven():
    idx = pd.date_range("2024-01-01", periods=60, freq="h")
    tr = _tr_mixta()
    tr["res"] = ["TP", "BE", "TP", "SL"]
    out = met.rachas(tr, idx, 5)
    assert [x["largo"] for x in out["TP"]] == [2] and [x["largo"] for x in out["SL"]] == [1]


def test_dinero_y_extremos_incluyen_el_breakeven():
    tr = _tr_mixta()
    idx = pd.date_range("2024-01-01", periods=60, freq="h")
    d = met.resumen_dinero(tr, 0.01, 1.0, 1.0)
    assert d["operaciones"] == 4 and d["breakeven"] == 1
    assert abs(d["neto"] - (3.5 * 2.0 * 100)) < 1e-6                          # R * distancia * 100 US$ por unidad
    assert met.extremos_diarios(tr, idx, 0.01, 1.0, 1.0)


def test_duraciones_y_win_rate_ignoran_el_breakeven():
    idx = pd.date_range("2024-01-01", periods=60, freq="h")
    du = met.duraciones(_tr_mixta(), idx)
    assert du["n"] == 3 and du["n_tp"] == 2 and du["n_sl"] == 1


def test_ablacion_agrega_el_paso_de_breakeven_solo_si_esta_activo():
    import data as dt
    df = dt.sintetico(n=4000, tendencia=0.0, seed=3)
    cfg = eng.Config(sl_modo="precio", sl_valor=10.0, rr=2.0, be_activo=True, usd_por_unidad=10.0)
    tabla, _ = met.ablacion(df, cfg, azar_veces=5)
    assert "+ Breakeven" in tabla.index
    tabla2, _ = met.ablacion(df, replace(cfg, be_activo=False), azar_veces=5)
    assert "+ Breakeven" not in tabla2.index


def test_describir_menciona_el_breakeven():
    cfg = eng.Config(sl_modo="precio", sl_valor=10.0, rr=2.0, be_activo=True, be_act_valor=1.0, be_nivel_valor=0.0)
    txt = vd.describir(cfg, "XAUUSD", "M5", "2024-01-01", "2024-06-01", 5.0, 0.1, None, 10, 5, 5, 0.1, None)
    assert "breakeven" in txt and "1,00 R" in txt


def test_ablacion_con_pullback_tambien_incluye_la_tendencia_mayor():
    import data as dt
    df = dt.sintetico(n=6000, tendencia=0.0, seed=3)
    cfg = eng.Config(sl_modo="precio", sl_valor=10.0, rr=2.0, pullback_activo=True, pullback_pct=50.0,
                     tm1_activo=True, tm1_tf="H1", tm1_periodo=20)
    tabla, omitidos = met.ablacion(df, cfg, azar_veces=5)
    assert "+ Pullback" in tabla.index
    assert any(i.startswith("+ Tendencia mayor 1") for i in tabla.index) or any(o.startswith("Tendencia mayor 1") for o in omitidos)
