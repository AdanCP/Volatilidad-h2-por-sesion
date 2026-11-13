"""Regresiones de la auditoria: mejor/peor dia con el dia de Europa Central y PARC_SL contado como operacion cerrada."""
import numpy as np
import pandas as pd

import metrics as met


def _tr(res, R, salida):
    return pd.DataFrame({"res": res, "R": R, "dist": [10.0] * len(res), "salida": salida})


def test_extremos_diarios_usa_las_claves_de_dia_y_no_la_medianoche_del_servidor():
    idx = pd.date_range("2024-01-02 22:00", periods=6, freq="h")       # cruza la medianoche del servidor en la vela 2
    claves = np.array([100, 100, 101, 101, 101, 101])                  # pero el dia de CE(S)T cambia en la vela 2 tambien: se prueba con otro corte
    claves = np.array([100, 100, 100, 101, 101, 101])
    tr = _tr(["TP", "SL", "TP"], [2.0, -1.0, 2.0], [1, 2, 3])
    ex = met.extremos_diarios(tr, idx, 0.01, 1.0, 1.0, 0.0, claves=claves)
    assert ex["mejor_R"] == 2.0 and ex["peor_R"] == 1.0 and ex["mejor_ops"] == 1
    sin = met.extremos_diarios(tr, idx, 0.01, 1.0, 1.0, 0.0)           # por fecha de los datos: 2 ops el dia 2, 1 el dia 3
    assert sin["mejor_ops"] in (1, 2)


def test_parc_sl_cuenta_como_operacion_cerrada_en_extremos():
    idx = pd.date_range("2024-01-02", periods=4, freq="h")
    tr = _tr(["PARC_SL"], [0.5], [2])
    assert met.extremos_diarios(tr, idx, 0.01, 1.0, 1.0)["mejor_R"] == 0.5
