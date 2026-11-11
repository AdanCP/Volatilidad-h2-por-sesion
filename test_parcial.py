"""Tests del cierre parcial: simulacion vela por vela, redondeo de lotes y validaciones."""
import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import engine as eng
import metrics as met
from test_breakeven import P_manual, _be


def _par(nivel=1.0, f=0.5, sl=0.05, modo="r"):
    return {"modo": modo, "valor": nivel, "f": f, "sl_nivel": sl}


def run(h, l, lado=1, par=None, be=None, sp=None, rr=2.0, costo=0.0, salida="rr"):
    tr, _ = eng.simular(P_manual(h, l, sp), [(0, lado)], rr, costo, None, salida, None, be, par)
    return tr.iloc[0]


# entrada 100, SL 98 (1R = 2), TP 104 (rr 2). Parcial a 1R = 102, SL del resto en 100,1 (0,05 R)
def test_parcial_y_despues_tp():
    t = run([100, 102.5, 104.5], [100, 100.5, 101], par=_par())
    assert t["res"] == "TP" and t["parcial"] == 1 and t["salida"] == 2
    assert t["R_parcial"] == pytest.approx(0.5) and t["R_resto"] == pytest.approx(1.0) and t["R"] == pytest.approx(1.5)


def test_parcial_y_el_resto_sale_en_su_sl():
    t = run([100, 102.5, 101], [100, 100.5, 100.0], par=_par())
    assert t["res"] == "PARC_SL" and t["motivo"] == "parc_sl" and t["parcial"] == 1
    assert t["R"] == pytest.approx(0.5 + 0.5 * 0.05) and not t["amb"]


def test_misma_vela_parcial_y_sl_original_gana_el_sl():
    t = run([100, 102.5], [100, 97.5], par=_par())
    assert t["res"] == "SL" and t["R"] == -1.0 and t["parcial"] == 0 and t["R_parcial"] == 0.0


def test_misma_vela_parcial_y_vuelta_al_nivel_del_resto_es_peor_caso():
    t = run([100, 102.5], [100, 100.0], par=_par())
    assert t["res"] == "PARC_SL" and t["amb"] and t["R"] == pytest.approx(0.525)


def test_misma_vela_parcial_y_tp_se_ejecutan_los_dos():
    t = run([100, 104.5], [100, 101], par=_par())
    assert t["res"] == "TP" and t["parcial"] == 1 and t["R"] == pytest.approx(1.5)


def test_sin_mover_el_sl_el_resto_sigue_con_el_original():
    t = run([100, 102.5, 101], [100, 100.5, 97.5], par=_par(sl=None))
    assert t["res"] == "PARC_SL" and t["R"] == pytest.approx(0.5 - 0.5)


def test_convive_con_el_breakeven_gana_el_sl_mas_favorable():
    # parcial en 102 mueve el SL a 100,1; el breakeven (103, nivel 0,5 R = 101) lo sube a 101
    t = run([100, 102.5, 103.5, 102], [100, 100.5, 101.5, 100.8], par=_par(), be=_be(act=1.5, nivel=0.5))
    assert t["res"] == "PARC_SL" and t["be"] == 1 and t["R"] == pytest.approx(0.5 + 0.5 * 0.5)


def test_breakeven_mas_bajo_que_el_del_parcial_no_lo_empeora():
    t = run([100, 102.5, 103.5, 102], [100, 100.5, 101.5, 100.05], par=_par(sl=0.5), be=_be(act=1.5, nivel=0.0))
    assert t["res"] == "PARC_SL" and t["R"] == pytest.approx(0.5 + 0.5 * 0.5)   # el SL quedo en 101 (parcial), no en 100


def test_corto_es_simetrico():
    t = run([100, 99.5, 100.5], [100, 97.5, 99.0], lado=-1, par=_par())
    assert t["res"] == "PARC_SL" and t["parcial"] == 1 and t["R"] == pytest.approx(0.525)


def test_corto_usa_el_spread_igual_que_el_tp():
    # low 98,2 + spread 0,5 = 98,7: no llega a 98; con low 97,4 (+0,5 = 97,9) si
    t = run([100, 99.5], [100, 98.2], lado=-1, par=_par(), sp=[0, 0.5])
    assert t["parcial"] == 0 and t["res"] == "ABIERTA"
    t = run([100, 99.5], [100, 97.4], lado=-1, par=_par(), sp=[0, 0.5])
    assert t["parcial"] == 1


def test_apagado_es_identico():
    h, l = [100, 102.5, 101, 104.5], [100, 100.5, 100.2, 101]
    a, b = run(h, l), run(h, l, par=None)
    assert a["R"] == b["R"] and a["res"] == b["res"] and a["parcial"] == 0 and a["R_parcial"] == 0.0 and a["R_resto"] == a["R"]


def test_costo_extra_se_resta_una_sola_vez():
    t = run([100, 102.5, 104.5], [100, 100.5, 101], par=_par(), costo=0.2)
    assert t["R"] == pytest.approx(1.5 - 0.1) and t["R_parcial"] + t["R_resto"] == pytest.approx(t["R"])


def test_parcial_total_cierra_todo_en_el_nivel():
    t = run([100, 102.5, 104.5], [100, 100.5, 101], par=_par(f=1.0))
    assert t["res"] == "TP" and t["motivo"] == "parcial" and t["R"] == pytest.approx(1.0)


def test_modo_pct_tp():
    # 50 % del camino al TP (rr 2 -> 1R); mismo resultado que nivel 1R
    a = run([100, 102.5, 104.5], [100, 100.5, 101], par=_par(nivel=50, modo="pct_tp"))
    assert a["R"] == pytest.approx(1.5)


def test_por_senal_pondera_con_la_salida_por_cierre():
    P = P_manual([100, 102.5, 103], [100, 100.5, 101])
    P.diff = np.array([1.0, 1.0, -1.0])
    P.c = np.array([100.0, 102.0, 102.8])
    tr, _ = eng.simular(P, [(0, 1)], 2.0, 0.0, None, "senal", None, None, _par())
    t = tr.iloc[0]
    assert t["res"] == "TP" and t["motivo"] == "senal" and t["R"] == pytest.approx(0.5 + 0.5 * 1.4)


# ------------------------------------------------------------- lotes
def test_fraccion_con_lotes():
    cfg = lambda **k: eng.Config(parcial_activo=True, parcial_pct=50.0, **k)
    assert eng.fraccion_parcial(cfg()) == 0.5
    assert eng.fraccion_parcial(cfg(lotes=0.17)) == pytest.approx(0.09 / 0.17)   # 0,085 -> 0,09
    assert eng.fraccion_parcial(cfg(lotes=0.02)) == pytest.approx(0.5)
    assert eng.fraccion_parcial(cfg(lotes=0.01)) == 1.0                          # no se puede partir: se cierra todo
    assert eng.fraccion_parcial(eng.Config(parcial_activo=True, parcial_pct=1.0, lotes=0.17)) == 0.0


def test_lote_que_no_se_puede_partir_desactiva_el_parcial():
    assert eng.parcial_de(eng.Config(parcial_activo=True, parcial_pct=1.0, lotes=0.17)) is None
    assert eng.parcial_de(eng.Config()) is None
    assert eng.parcial_de(eng.Config(parcial_activo=True, parcial_mover_sl=False))["sl_nivel"] is None


# ------------------------------------------------------------- validaciones
@pytest.mark.parametrize("kw", [
    dict(parcial_nivel_modo="usd"), dict(parcial_nivel_valor=0), dict(parcial_pct=0), dict(parcial_pct=100),
    dict(parcial_sl_nivel=-0.1), dict(parcial_nivel_valor=2.0, rr=2.0), dict(parcial_nivel_modo="pct_tp", parcial_nivel_valor=100),
    dict(parcial_nivel_modo="pct_tp", salida_modo="senal"), dict(parcial_nivel_valor=1.0, parcial_sl_nivel=1.0),
])
def test_validaciones(kw):
    with pytest.raises(ValueError):
        eng.Config(parcial_activo=True, **kw).validar()


def test_apagado_no_valida_nada():
    eng.Config(parcial_activo=False, parcial_pct=500, parcial_nivel_valor=-3).validar()


# ------------------------------------------------------------- metricas
def test_wr_por_resultado_y_clasico():
    tr = pd.DataFrame({"res": ["TP", "SL", "PARC_SL", "BE", "BE"], "R": [1.5, -1.0, 0.525, 0.05, -0.1], "amb": False,
                       "be": 0, "parcial": [1, 0, 1, 0, 0], "R_parcial": [0.5, 0, 0.5, 0, 0], "motivo": ""})
    r = met.resumen(tr, 2.0)
    assert r["%TP"] == 50.0 and r["TP"] == 1 and r["SL"] == 1                    # clasico: solo TP contra SL
    assert r["WR_resultado"] == pytest.approx(60.0) and r["be_positivas"] == 1 and r["parc_sl"] == 1 and r["parciales"] == 2
    assert r["R_total"] == pytest.approx(1.5 - 1.0 + 0.525 + 0.05 - 0.1)


# ------------------------------------------------------------- de punta a punta (datos sinteticos)
def _corrida(**kw):
    import data as dt
    from dataclasses import replace
    df = dt.sintetico(n=12000, tendencia=0.0, seed=5)
    base = eng.Config(ema_corta=9, ema_larga=21, sl_modo="precio", sl_valor=6.0, rr=4.0, usd_por_unidad=10.0, lotes=0.17)
    cfg = replace(base, **kw)
    P = eng.preparar(df, cfg)
    return eng.ejecutar(P, cfg).trades


def test_punta_a_punta_apagado_igual_y_encendido_consistente():
    off = _corrida()
    off2 = _corrida(parcial_activo=False, parcial_pct=70.0)            # parametros del parcial sin activarlo: nada cambia
    assert off["R"].tolist() == off2["R"].tolist() and (off["parcial"] == 0).all()
    on = _corrida(parcial_activo=True, parcial_nivel_valor=1.5, parcial_pct=50.0, parcial_mover_sl=True, parcial_sl_nivel=0.05)
    assert len(on) > 0 and on["parcial"].sum() > 0
    assert np.allclose(on["R"], on["R_parcial"] + on["R_resto"])
    assert set(on["res"]) <= {"TP", "SL", "BE", "PARC_SL", "ABIERTA"}
    cerr = on[on["res"] != "ABIERTA"]
    assert (cerr.loc[cerr["res"] == "PARC_SL", "R"] > 0).all()            # parcial cobrado con el resto en 0,05 R: siempre positiva
    f = eng.fraccion_parcial(eng.Config(parcial_activo=True, parcial_pct=50.0, lotes=0.17))
    assert np.allclose(cerr.loc[cerr["parcial"] == 1, "R_parcial"], f * 1.5)
