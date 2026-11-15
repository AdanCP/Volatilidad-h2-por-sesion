"""Reentrada con SL / TP / lotaje propios: el riesgo en US$ se mantiene (el lote se recalcula) y el tope de lotaje la descarta."""
import pytest

import engine as eng
from test_backtester import _cuenta
from test_reentrada import _base, _reent, _sim


def test_por_defecto_igual_que_la_entrada():
    a = _sim(_base(), _reent())
    b = _sim(_base(), _reent(sl_modo="igual", sl_valor=0.0, rr=None, lote_max=None, lotes=1.0, lote_paso=0.01, lote_min=0.01))
    assert a.equals(b)


def test_tp_propio():
    tr = _sim(_base(), _reent(rr=1.0))
    assert tr.loc[1, "tp"] == 110.0 and tr.loc[1, "sl"] == 90.0 and tr.loc[1, "R"] == 1.0 and tr.loc[0, "tp"] == 120.0


def test_sl_propio_en_precio_y_tp_propio():
    tr = _sim(_base(), _reent(sl_modo="precio", sl_valor=5.0, rr=1.0, lotes=0.0))
    assert tr.loc[1, "sl"] == 95.0 and tr.loc[1, "tp"] == 105.0 and tr.loc[1, "dist"] == 5.0 and list(tr["res"]) == ["TP", "TP"]


def test_sl_propio_en_atr():
    tr = _sim(_base(), _reent(sl_modo="atr", sl_valor=3.0, lotes=0.0))          # ATR = 1 -> SL a 3
    assert tr.loc[1, "dist"] == 3.0 and tr.loc[1, "sl"] == 97.0


def test_lote_recalculado_mantiene_el_riesgo_en_dolares():
    cu = _cuenta(capital=10000.0, vu=10.0)
    tr = _sim(_base(), _reent(sl_modo="precio", sl_valor=5.0, rr=1.0, lotes=1.0, lote_paso=0.01, lote_min=0.01), cuenta=cu)
    # entrada: 2R x 10 x 10 = 200. Reentrada: SL a la mitad -> doble de lote (vu 20): 1R x 5 x 20 = 100 (= el riesgo de la entrada)
    assert abs(tr.attrs["cuenta"]["balance_final"] - 10300.0) < 1e-6


def test_el_valor_por_unidad_se_restituye_despues_de_la_reentrada():
    P = _base()
    P.l[10], P.h[11] = 97.0, 125.0
    cu = _cuenta(capital=10000.0, vu=10.0)
    tr = _sim(P, _reent(max=2, sl_modo="precio", sl_valor=5.0, rr=1.0, lotes=1.0), cuenta=cu)
    esperado = 10000.0 + 200.0 + 100.0 + 100.0          # la segunda reentrada vuelve a arriesgar lo mismo que la entrada
    assert len(tr) == 3 and abs(tr.attrs["cuenta"]["balance_final"] - esperado) < 1e-6


def test_el_tope_de_lotaje_descarta_la_reentrada():
    cu = _cuenta(capital=10000.0, vu=10.0)
    tr = _sim(_base(), _reent(sl_modo="precio", sl_valor=5.0, lotes=1.0, lote_max=1.5), cuenta=cu)
    assert list(tr["reentrada"]) == [0] and tr.attrs["reent_saltadas_lote"]["lote_max"] == 1
    tr = _sim(_base(), _reent(sl_modo="precio", sl_valor=5.0, lotes=1.0, lote_max=2.0), cuenta=cu)
    assert list(tr["reentrada"]) == [0, 1]


def test_lote_menor_que_el_minimo_descarta_la_reentrada():
    tr = _sim(_base(), _reent(sl_modo="precio", sl_valor=1000.0, lotes=0.05, lote_min=0.01), cuenta=_cuenta())
    assert list(tr["reentrada"]) == [0] and tr.attrs["reent_saltadas_lote"]["lote_min"] == 1


def test_validacion():
    for k in (dict(re_sl_modo="x"), dict(re_sl_modo="atr", re_sl_valor=0.0), dict(re_rr=0.0), dict(re_lote_max=0.0)):
        with pytest.raises(ValueError):
            eng.Config(reentrada_activa=True, **k).validar()
    eng.Config(reentrada_activa=True, re_sl_modo="precio", re_sl_valor=2.0, re_rr=1.0, re_lote_max=1.0).validar()
    r = eng.reent_de(eng.Config(reentrada_activa=True, re_sl_modo="atr", re_sl_valor=1.5, re_rr=1.0, lotes=0.17))
    assert r["sl_modo"] == "atr" and r["rr"] == 1.0 and r["lotes"] == 0.17


# ---------------------------------------------------------------- extremo a extremo (indicadores reales)
def test_e2e_gestion_propia_con_las_otras_funciones():
    import numpy as np
    from test_reentrada import _df, _cfg
    df = _df()
    for k in (dict(re_sl_modo="atr", re_sl_valor=0.5, re_rr=1.0, lotes=1.0, usd_por_unidad=100.0),
              dict(re_sl_modo="precio", re_sl_valor=1.0, re_rr=1.5, lotes=0.17, usd_por_unidad=17.0, re_lote_max=0.5),
              dict(re_sl_modo="atr", re_sl_valor=0.8, be_activo=True, parcial_activo=True, lotes=1.0, usd_por_unidad=100.0)):
        cfg = _cfg(**k)
        t = eng.ejecutar(eng.preparar(df, cfg), cfg).trades
        re_ = t[t["reentrada"] > 0]
        assert len(re_) > 0, k
        assert (t["i"].values[1:] > t["salida"].values[:-1]).all(), k               # una posicion a la vez
        if cfg.re_sl_modo == "precio":
            assert np.allclose(re_["dist"], cfg.re_sl_valor)
        if cfg.re_rr is not None and cfg.salida_modo == "rr" and not cfg.be_activo:
            assert set(np.round(re_.loc[re_["res"] == "TP", "R"], 6)) <= {round(cfg.re_rr, 6)}
