"""Reentrada: tras una operacion de la tendencia que cerro con R > 0, se vuelve a entrar en el retroceso a la media."""
import numpy as np
import pandas as pd

import engine as eng
from test_backtester import _cuenta

N = 60


def _P(n=N, ema=98.0, adx=30.0, pdi=30.0, mdi=10.0, ses=None):
    """Precio plano en 100 (SL a 10, TP a 20 con rr 2), media larga fija en `ema`, una señal alcista en la vela 0."""
    c = np.full(n, 100.0)
    sube = np.zeros(n, dtype=bool)
    sube[0] = True
    re = {"base": np.ones((2, n), dtype=bool), "ses": ses, "adx": np.full(n, adx), "pdi": np.full(n, pdi), "mdi": np.full(n, mdi)}
    P = eng.Preparado(c + 0.5, c - 0.5, c.copy(), np.zeros(n), np.full(n, 1.0), np.full(n, 10.0),
                      pd.date_range("2024-01-02 00:00", periods=n, freq="5min"), [], 0.0,
                      ema_c=np.full(n, ema), ema_l=np.full(n, ema), sube=sube, baja=np.zeros(n, dtype=bool),
                      dia=np.zeros(n, dtype="int64"), diff=np.ones(n), re=re)
    return P


def _gana(P, i):
    P.h[i] = 125.0              # la vela i llega al TP (entrada 100 + 20)


def _pierde(P, i):
    P.l[i] = 85.0


def _toca(P, j, nivel=97.0):
    P.l[j] = nivel               # el precio baja a la media y cierra a favor (cierre 100 > media 98)


def _reent(**k):
    base = dict(nivel="larga", modo="confirmacion", max=1, velas=60, adx_min=25.0, di=True, adx_cre=0, adx_per=1)
    base.update(k)
    return base


def _sim(P, reent, cuenta=None, **kw):
    tr, _ = eng.simular(P, [(0, 1)], 2.0, 0.0, None, "rr", cuenta, reent=reent, **kw)
    return tr


def _base():
    P = _P()
    _gana(P, 1)
    _toca(P, 5)
    _gana(P, 6)
    return P


def test_reentra_en_el_retroceso_despues_de_una_ganadora():
    tr = _sim(_base(), _reent())
    assert list(tr["reentrada"]) == [0, 1] and list(tr["res"]) == ["TP", "TP"]
    assert tr.loc[1, "i"] == 5 and tr.loc[1, "señal"] == 0 and tr.loc[1, "entrada"] == 100.0 and tr.loc[1, "salida"] == 6


def test_sin_reentrada_activa_no_cambia_nada():
    assert len(_sim(_base(), None)) == 1


def test_no_reentra_despues_de_una_perdedora():
    P = _P()
    _pierde(P, 1)
    _toca(P, 5)
    _gana(P, 6)
    assert list(_sim(P, _reent())["reentrada"]) == [0]


def test_no_reentra_despues_de_un_breakeven_no_positivo():
    P = _P()
    P.h[1] = 110.0                                   # llega a 1R y vuelve a la entrada: breakeven en 0
    P.l[2] = 99.0
    _toca(P, 5)
    _gana(P, 6)
    be = {"act_modo": "r", "act_valor": 1.0, "nivel_modo": "r", "nivel_valor": 0.0, "vu": 1.0}
    tr = _sim(P, _reent(), be=be)
    assert list(tr["res"]) == ["BE"] and len(tr) == 1


def test_maximo_de_reentradas_por_tendencia():
    P = _base()
    _toca(P, 10)
    _gana(P, 11)
    assert list(_sim(P, _reent(max=1))["reentrada"]) == [0, 1]
    assert list(_sim(P, _reent(max=2))["reentrada"]) == [0, 1, 2]


def test_la_segunda_reentrada_solo_si_la_primera_cerro_positiva():
    P = _P()
    _gana(P, 1)
    _toca(P, 5)
    _pierde(P, 6)
    _toca(P, 10)
    _gana(P, 11)
    assert list(_sim(P, _reent(max=2))["reentrada"]) == [0, 1]


def test_cruce_contrario_termina_la_tendencia():
    P = _base()
    P.baja[4] = True
    assert len(_sim(P, _reent())) == 1


def test_cruce_contrario_en_la_vela_del_limite_no_la_anula_si_se_lleno_adentro():
    P = _base()
    P.baja[5] = True                                  # la vela 5 cierra con cruce contrario, pero el limite se lleno adentro (antes de saberlo)
    assert len(_sim(P, _reent(modo="limite"))) == 2 and len(_sim(P, _reent(modo="confirmacion"))) == 1


def test_caducidad_en_velas_desde_el_cruce():
    assert len(_sim(_base(), _reent(velas=4))) == 1 and len(_sim(_base(), _reent(velas=5))) == 2


def test_adx_minimo_y_di_a_favor():
    P = _base()
    P.re["adx"][:] = 20.0
    assert len(_sim(P, _reent())) == 1                          # ADX 20 < 25
    assert len(_sim(P, _reent(adx_min=None))) == 2
    P2 = _base()
    P2.re["pdi"][:], P2.re["mdi"][:] = 10.0, 30.0
    assert len(_sim(P2, _reent())) == 1                         # DI en contra
    assert len(_sim(P2, _reent(di=False))) == 2


def test_adx_creciente():
    P = _base()
    assert len(_sim(P, _reent(adx_cre=2))) == 1                 # ADX plano: no crece
    P.re["adx"][:] = np.linspace(26, 60, N)
    assert len(_sim(P, _reent(adx_cre=2))) == 2


def test_filtros_comunes_se_miran_en_la_vela_de_decision():
    P = _base()
    P.re["base"][0, 5] = False
    assert len(_sim(P, _reent())) == 1


def test_filtro_de_sesion_se_mira_en_la_vela_de_entrada():
    ses = np.ones(N, dtype=bool)
    ses[5] = False
    assert len(_sim(_with_ses(ses), _reent())) == 1


def _with_ses(ses):
    P = _P(ses=ses)
    _gana(P, 1)
    _toca(P, 5)
    _gana(P, 6)
    return P


def test_modo_limite_entra_en_la_media_conocida_en_la_vela_anterior():
    P = _base()
    tr = _sim(P, _reent(modo="limite"))
    assert tr.loc[1, "i"] == 5 and tr.loc[1, "entrada"] == 98.0       # fill en el nivel (98), no al cierre
    assert abs(tr.loc[1, "sl"] - 88.0) < 1e-9


def test_modo_limite_no_mira_la_media_de_la_vela_de_llenado():
    P = _base()
    ref = _sim(P, _reent(modo="limite")).loc[1, "entrada"]
    P2 = _base()
    P2.ema_l[5] = 50.0                                                # la media "de esa vela" no se conoce al dejar la orden
    assert _sim(P2, _reent(modo="limite")).loc[1, "entrada"] == ref


def test_modo_confirmacion_exige_cerrar_a_favor():
    P = _base()
    P.c[5] = 97.5                                                     # toca pero cierra por debajo de la media (98): sin confirmacion
    assert len(_sim(P, _reent())) == 1


def test_nivel_ema_corta():
    P = _base()
    P.ema_c[:] = 90.0                                                 # la corta queda lejos: no la toca
    assert len(_sim(P, _reent(nivel="corta"))) == 1 and len(_sim(P, _reent(nivel="larga"))) == 2


def test_la_cuenta_cuadra_con_las_reentradas():
    P = _base()
    _toca(P, 10)
    _gana(P, 11)
    cu = _cuenta(capital=10000.0, vu=10.0)
    tr = _sim(P, _reent(max=2), cuenta=cu)
    esperado = 10000.0 + float((tr["R"] * tr["dist"]).sum() * 10.0)
    assert len(tr) == 3 and abs(tr.attrs["cuenta"]["balance_final"] - esperado) < 1e-6


def test_las_reglas_de_cuenta_tambien_frenan_la_reentrada():
    cu = _cuenta(capital=10000.0, vu=10.0, pausa_gan_min=1000.0)          # pausa tras una ganancia: la reentrada llega despues de una
    tr = _sim(_base(), _reent(), cuenta=cu)
    assert len(tr) == 1 and tr.attrs["cuenta"]["saltadas_pausa_gan"] == 1
    cu2 = _cuenta(capital=10000.0, vu=10.0, riesgo_pct=0.5)                # 10 de SL x 10 US$ = 100 = 1 % > 0,5 %: se saltea
    assert len(_sim(_base(), _reent(), cuenta=cu2)) == 0


# ---- de punta a punta (preparar + ejecutar con datos sinteticos) ----
from dataclasses import replace

import pytest

import metrics as met


def _df(n=4000, semilla=5):
    rng = np.random.default_rng(semilla)
    c = 2000 + np.cumsum(rng.normal(0, 0.6, n) + np.sin(np.arange(n) / 300) * 0.15)
    o = np.r_[c[0], c[:-1]]
    h = np.maximum(o, c) + rng.uniform(0, 0.5, n)
    l = np.minimum(o, c) - rng.uniform(0, 0.5, n)
    return pd.DataFrame({"Open": o, "High": h, "Low": l, "Close": c, "Volume": 100.0, "Spread": 0.0},
                        index=pd.date_range("2024-01-01", periods=n, freq="5min"))


def _cfg(**k):
    return eng.Config(rr=2.0, reentrada_activa=True, reentrada_max=2, re_adx_min=20.0, **k)


@pytest.mark.parametrize("modo", ["confirmacion", "limite"])
@pytest.mark.parametrize("nivel", ["larga", "corta"])
def test_e2e_orden_ganadora_previa_y_sin_mirar_el_futuro(modo, nivel):
    df = _df()
    cfg = _cfg(reentrada_modo=modo, reentrada_nivel=nivel)
    t = eng.ejecutar(eng.preparar(df, cfg), cfg).trades
    assert (t["reentrada"] > 0).any()
    assert (t["i"].values[1:] > t["salida"].values[:-1]).all()                       # una posicion a la vez
    for ix in t.index[t["reentrada"] > 0]:
        assert t.loc[ix - 1, "R"] > 0 and t.loc[ix - 1, "lado"] == t.loc[ix, "lado"]  # solo tras una ganadora, mismo lado
    corte = 3000
    t2 = eng.ejecutar(eng.preparar(df.iloc[:corte], cfg), cfg).trades
    t2 = t2[t2.res != "ABIERTA"]
    a, b = t[t["salida"] < corte - 50].reset_index(drop=True), t2[t2["salida"] < corte - 50].reset_index(drop=True)
    assert len(a) == len(b) and np.allclose(a["R"], b["R"]) and (a["i"] == b["i"]).all()


def test_e2e_apagada_no_cambia_nada_y_la_columna_vale_cero():
    df = _df()
    base = eng.Config(rr=2.0)
    t = eng.ejecutar(eng.preparar(df, base), base).trades
    assert (t["reentrada"] == 0).all()
    t2 = eng.ejecutar(eng.preparar(df, replace(base, reentrada_activa=False, reentrada_max=2)), base).trades
    assert t.equals(t2)


def test_e2e_con_las_otras_funciones_no_se_solapa():
    df = _df()
    for k in (dict(pullback_activo=True, pullback_pct=50.0), dict(be_activo=True), dict(parcial_activo=True, lotes=1.0),
              dict(sl_modo="ema", sl_valor=1.0), dict(finde_mantener=False), dict(adx_activo=True, adx_min=15.0)):
        cfg = _cfg(**k)
        t = eng.ejecutar(eng.preparar(df, cfg), cfg).trades
        assert (t["i"].values[1:] > t["salida"].values[:-1]).all(), k


def test_e2e_evaluar_corre_con_reentrada():
    cfg = _cfg()
    r = met.evaluar(_df(), cfg, azar_veces=3)
    assert r is not None


def test_validacion_de_los_campos():
    for k in (dict(reentrada_max=3), dict(reentrada_nivel="x"), dict(reentrada_modo="x"), dict(reentrada_velas=0),
              dict(re_adx_creciente_n=-1)):
        with pytest.raises(ValueError):
            eng.Config(reentrada_activa=True, **k).validar()
    eng.Config(reentrada_activa=False, reentrada_max=3).validar()          # apagada: no se valida
