import numpy as np
import pandas as pd

import engine as eng
import retiros as ret
from test_backtester import _P_cuenta, _gana, _pierde


def _cs(**k):
    base = {"retiros": [{"j": 4, "monto": 400.0}, {"j": 30, "monto": 350.0}], "quemada": False, "quemada_en": None,
            "balance_final": 10120.0}
    base.update(k)
    return base


def test_resumen_cuenta_retiros_total_y_tiempos():
    idx = pd.date_range("2024-01-02 00:00", periods=40, freq="5min")
    r = ret.resumen(_cs(), idx, 10000.0)
    assert r["n"] == 2 and r["total"] == 750.0 and not r["quemada"] and abs(r["ciclo_avance"] - 120.0) < 1e-9
    assert r["tiempos_min"] == [20.0, 130.0] and r["maximo"] == 130.0 and abs(r["medio"] - 75.0) < 1e-9


def test_resumen_si_se_quema_mide_cuanto_duro_y_desde_el_ultimo_retiro():
    idx = pd.date_range("2024-01-02 00:00", periods=40, freq="5min")
    r = ret.resumen(_cs(quemada=True, quemada_en=35), idx, 10000.0)
    assert r["quemada"] and r["hasta_quemarse_min"] == 175.0 and r["desde_ultimo_min"] == 25.0 and r["dias_operados"] == 1


def test_barrido_elige_el_que_mas_retira_y_marca_las_quemadas():
    P = _P_cuenta(n=80)
    for i in (0, 3, 6, 9, 12, 15):
        _gana(P, i)
    cfg = eng.Config(reglas_activas=True, capital=10000.0, usd_por_unidad=10.0, rr=2.0, salida_modo="rr")
    P.cruces = [(i, 1, None) for i in (0, 3, 6, 9, 12, 15)]
    b = ret.barrido(P, cfg, (1.0, 2.0, 4.0))
    por = {f["pct"]: f for f in b["filas"]}
    assert por[1.0]["n"] == 6 and por[2.0]["n"] == 6 and por[4.0]["n"] == 3        # 200 US$ por operacion ganadora
    assert por[1.0]["total"] == 1200.0 and por[4.0]["total"] == 1200.0 and not any(f["quemada"] for f in b["filas"])
    assert b["ideal"] == 1.0                                                      # empate en total y en quemada: mas retiros
