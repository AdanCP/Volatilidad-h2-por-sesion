"""Regla de consistencia en los retiros: el mejor dia del ciclo no puede pesar mas que ese % de la ganancia retirada."""
import numpy as np
import pandas as pd
import pytest

import engine as eng
import retiros as ret
from test_backtester import _P_cuenta, _cuenta, _gana, _pierde

DIAS = [0] * 20 + [1] * 20 + [2] * 20 + [3] * 20          # 4 dias de 20 velas; cada ganadora vale US$ 200 (rr 2, SL 10, vu 10)


def _sim(señales, perdedoras=(), **k):
    P = _P_cuenta(n=80, dias=DIAS)
    for i in señales:
        _gana(P, i)
    for i in perdedoras:
        _pierde(P, i)
    ss = sorted(list(señales) + list(perdedoras))
    tr, _ = eng.simular(P, [(i, 1) for i in ss], 2.0, 0.0, None, "rr", _cuenta(**k))
    return tr.attrs["cuenta"]


def test_sin_consistencia_retira_al_llegar_al_objetivo():
    cu = _sim([0, 3, 22, 42], retiro_usd=400.0)
    assert [x["monto"] for x in cu["retiros"]] == [400.0, 400.0] and not any(x["estirado"] for x in cu["retiros"])


def test_con_consistencia_espera_a_que_el_mejor_dia_pese_lo_permitido():
    # dia 0: 400 (mejor dia). Con 50 % hay que juntar 800: recien en el dia 2 (200 + 200 + 400)
    cu = _sim([0, 3, 22, 42], retiro_usd=400.0, consist=0.5)
    r = cu["retiros"]
    assert len(r) == 1 and r[0]["monto"] == 800.0 and r[0]["estirado"] and r[0]["umbral"] == 800.0 and r[0]["mejor_dia"] == 400.0
    assert cu["balance_final"] == 10000.0


def test_el_dia_en_curso_cuenta_para_el_mejor_dia():
    # 3 ganadoras el mismo dia = 600: con 50 % hace falta 1200, aunque el objetivo sea 400
    cu = _sim([0, 3, 6], retiro_usd=400.0, consist=0.5)
    assert cu["retiros"] == [] and cu["balance_final"] == 10600.0


def test_sin_estirar_si_el_mejor_dia_ya_cumple():
    # una ganadora por dia (200) con 50 %: 400 >= 200/0.5 = 400 -> retira justo en el objetivo
    cu = _sim([0, 22], retiro_usd=400.0, consist=0.5)
    assert len(cu["retiros"]) == 1 and cu["retiros"][0]["monto"] == 400.0 and not cu["retiros"][0]["estirado"]


def test_tras_el_retiro_el_ciclo_arranca_de_cero():
    # ciclo 1: dias 0 (400) y 1 (200) y 2 (200) -> 800; ciclo 2: un dia de 200 y otro de 200 -> 400 sin estirar
    cu = _sim([0, 3, 22, 42, 62], perdedoras=(), retiro_usd=400.0, consist=0.5)
    assert len(cu["retiros"]) == 1 and cu["balance_final"] == 10200.0          # el 5.o dia (200) ya es del ciclo nuevo
    cu = _sim([0, 3, 22, 42, 62, 66], retiro_usd=400.0, consist=0.5)          # dia 3: 400 en un dia -> mejor dia 400, ganancia 400
    assert len(cu["retiros"]) == 1 and cu["balance_final"] == 10400.0          # necesita 800: todavia no


def test_la_perdida_resta_de_la_ganancia_pero_no_cuenta_como_mejor_dia():
    # dia 0: +200 - 100 (una perdedora vale 1 R = 100) = +100; dia 1: +200; dia 2: +200. Con 50 % hace falta 2 x 200 = 400 -> retira 500 en el dia 2
    cu = _sim([0, 22, 42], perdedoras=(6,), retiro_usd=200.0, consist=0.5)
    r = cu["retiros"]
    assert len(r) == 1 and r[0]["monto"] == 500.0 and r[0]["mejor_dia"] == 200.0 and r[0]["estirado"]


def test_no_hace_nada_sin_retiro():
    cu = _sim([0, 3, 22], consist=0.5)
    assert cu["retiros"] == [] and cu["balance_final"] == 10600.0


def test_validacion():
    with pytest.raises(ValueError):
        eng.Config(consistencia_pct=120.0).validar()
    with pytest.raises(ValueError):
        eng.Config(consistencia_pct=-1.0).validar()
    eng.Config(consistencia_pct=20.0).validar()


def test_resumen_cuenta_los_retiros_estirados():
    idx = pd.date_range("2024-01-02", periods=40, freq="5min")
    cu = {"retiros": [{"j": 4, "monto": 800.0, "estirado": True, "umbral": 800.0, "mejor_dia": 400.0},
                      {"j": 30, "monto": 400.0, "estirado": False, "umbral": 400.0, "mejor_dia": 200.0}], "quemada": False, "balance_final": 10000.0}
    r = ret.resumen(cu, idx, 10000.0)
    assert r["n_estirados"] == 1 and r["estirados"] == [True, False] and r["umbrales"] == [800.0, 400.0] and r["mejores_dias"] == [400.0, 200.0]


# ------------------------------------------------------------- sugerencia de lotaje y RR
def _P_sug():
    P = _P_cuenta(n=400, dias=[i // 20 for i in range(400)])
    P.cruces = []
    sen = list(range(0, 380, 6))
    for i in sen:
        _gana(P, i)
    return P, sen


def test_mejor_dia_en_r():
    P = _P_cuenta(n=80, dias=DIAS)
    tr = pd.DataFrame({"res": ["TP", "TP", "TP", "SL", "ABIERTA"], "R": [2.0, 2.0, 2.0, -1.0, 9.0], "salida": [1, 4, 22, 23, 79]})
    assert ret.mejor_dia_r(tr, P) == 4.0                       # dia 0: 2 + 2
    assert ret.mejor_dia_r(tr.iloc[0:0], P) == 0.0


def test_la_sugerencia_calcula_la_cota_y_prueba_lotajes():
    P, sen = _P_sug()
    cfg = eng.Config(reglas_activas=True, capital=10000.0, usd_por_unidad=10.0, rr=2.0, salida_modo="rr", retiro_activo=True,
                     retiro_pct=4.0, consistencia_pct=50.0, lotes=1.0, lote_paso=0.01, lote_min=0.01)
    P.cruces = [(i, 1, None) for i in sen]
    res_ = eng.ejecutar(P, cfg)
    s = ret.sugerir(P, cfg, res_.trades)
    assert s["W"] == 400.0 and s["tope_dia"] == 200.0
    assert s["riesgo_base"] == pytest.approx(100.0)                     # SL a 10 de precio x 10 US$/unidad
    assert s["mejor_dia_r"] > 0 and s["riesgo_max"] == pytest.approx(200.0 / s["mejor_dia_r"])
    assert s["lotes_max"] == pytest.approx(np.floor(100 * s["riesgo_max"] / 100.0) / 100)
    assert len(s["filas"]) >= 5 and s["mejor"] is not None
    for f in s["filas"]:
        assert f["riesgo"] == pytest.approx(100.0 * f["lotes"]) and f["tp_usd"] == pytest.approx(f["riesgo"] * f["rr"])
    # con el lotaje de la cota segura, ningun retiro se estira
    seg = [f for f in s["filas"] if abs(f["lotes"] - s["lotes_max"]) < 1e-9]
    assert seg and seg[0]["sin_estirar"] == seg[0]["n"]


def test_la_sugerencia_con_rr_prueba_varios_rr_y_salta_las_invalidas():
    P, sen = _P_sug()
    cfg = eng.Config(reglas_activas=True, capital=10000.0, usd_por_unidad=10.0, rr=2.0, salida_modo="rr", retiro_activo=True,
                     retiro_pct=4.0, consistencia_pct=50.0, lotes=0.5, lote_paso=0.01, lote_min=0.01,
                     parcial_activo=True, parcial_nivel_valor=1.5, parcial_sl_nivel=0.05)
    P.cruces = [(i, 1, None) for i in sen]
    tr = eng.ejecutar(P, cfg).trades
    s = ret.sugerir(P, cfg, tr, con_rr=True)
    assert {f["rr"] for f in s["filas"]} <= {1.5 + 0.0, 2.0, 3.0, 4.0, 5.0}    # rr 1,0 deja el parcial (1,5 R) por encima del TP: invalida
    assert 1.0 not in {f["rr"] for f in s["filas"]}
