"""Tests de «Mantener posición el fin de semana»: cierre en la última vela de la semana, cancelación de pendientes y
bloqueo de entradas del viernes."""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import engine as eng
import metrics as met


def _df(semanas=8, tf="15min", seed=3):
    """Velas de lunes 00:00 a viernes 23:45 (hora del servidor), un hueco de ~48 h cada fin de semana. Enero-febrero: invierno."""
    idx = pd.date_range("2024-01-01", periods=semanas * 7 * 96, freq=tf)       # el 1/1/2024 es lunes
    idx = idx[idx.weekday < 5]
    rng = np.random.default_rng(seed)
    c = 2000 + np.cumsum(rng.normal(0, 1.5, len(idx)))
    o = np.r_[c[0], c[:-1]]
    return pd.DataFrame({"Open": o, "High": np.maximum(o, c) + 0.6, "Low": np.minimum(o, c) - 0.6, "Close": c,
                         "Volume": 100, "Spread": 0.2}, index=idx)


def _cfg(**k):
    return eng.Config(servidor_offset_horas=2.0, **k)


def test_fs_es_la_ultima_vela_de_cada_semana():
    df = _df()
    P = eng.preparar(df, _cfg(finde_mantener=False))
    ult = np.flatnonzero(np.diff(df.index.values).astype("timedelta64[m]").astype(int) > 30 * 60)
    assert len(ult) >= 6 and P.fs is not None
    for i in range(len(df) - 1):
        esperado = ult[ult >= i][0] if (ult >= i).any() else len(df)
        assert P.fs[i] == esperado
    assert all(df.index[j].weekday() == 4 and df.index[j].hour == 23 and df.index[j].minute == 45 for j in ult)
    assert eng.preparar(df, _cfg()).fs is None                      # por defecto se mantiene: nada cambia


def _P_semana(h, l, c0=100.0, d=2.0, sp=0.0):
    n = len(h)
    P = eng.Preparado(np.asarray(h, float), np.asarray(l, float), np.full(n, c0), np.full(n, sp), np.full(n, d), np.full(n, d),
                      pd.date_range("2024-01-01", periods=n, freq="h"), [], 0.0)
    P.fs = np.array([3] * 4 + [n] * (n - 4))                         # la semana termina en la vela 3
    return P


def test_la_operacion_abierta_se_cierra_en_la_ultima_vela_de_la_semana():
    # entrada 100 (largo, d=2, SL 98, TP 104): hasta la vela 3 no toca nada; la 3 cierra en 101 (ganancia de 0,5R)
    P = _P_semana([100, 101, 101.5, 101.4, 110, 110], [100, 99.5, 100.5, 100.6, 99, 99])
    P.c[3] = 101.0
    tr, _ = eng.simular(P, [(0, 1)], 2.0, 0.0, None, "rr", None, None)
    t = tr.iloc[0]
    assert t["res"] == "TP" and t["motivo"] == "finde" and t["salida"] == 3 and abs(t["R"] - 0.5) < 1e-9
    # sin fin de semana el TP se alcanza despues (vela 4)
    P.fs = None
    t2 = eng.simular(P, [(0, 1)], 2.0, 0.0, None, "rr", None, None)[0].iloc[0]
    assert t2["res"] == "TP" and t2["motivo"] == "tp" and t2["salida"] == 4


def test_cierre_de_fin_de_semana_con_perdida_cuenta_como_sl_con_su_r_real_y_el_spread():
    # largo: entra al ask (100 + 0,2), cierra al bid (99,0): R = (99,0 - 100,2) / 2 = -0,6
    P = _P_semana([100, 100.5, 100.4, 100.3, 105], [100, 99.2, 99.1, 98.9, 99], sp=0.2)
    P.c[3] = 99.0
    t = eng.simular(P, [(0, 1)], 2.0, 0.0, None, "rr", None, None)[0].iloc[0]
    assert t["res"] == "SL" and t["motivo"] == "finde" and abs(t["R"] - (-0.6)) < 1e-9


def test_un_corto_cierra_al_ask():
    P = _P_semana([100, 100.8, 100.9, 100.7, 100], [100, 99.5, 99.4, 99.3, 90], sp=0.2)
    P.c[3] = 99.5
    t = eng.simular(P, [(0, -1)], 2.0, 0.0, None, "rr", None, None)[0].iloc[0]
    assert t["motivo"] == "finde" and abs(t["R"] - (100.0 - (99.5 + 0.2)) / 2.0) < 1e-9


def test_si_toca_sl_o_tp_antes_del_fin_de_semana_no_se_toca():
    P = _P_semana([100, 100.5, 104.5, 100, 100], [100, 99.5, 100, 99, 99])
    t = eng.simular(P, [(0, 1)], 2.0, 0.0, None, "rr", None, None)[0].iloc[0]
    assert t["res"] == "TP" and t["motivo"] == "tp" and t["salida"] == 2


def test_entrada_en_la_ultima_vela_se_cierra_en_el_acto_y_paga_el_spread():
    P = _P_semana([100, 100, 100, 100, 100], [100, 100, 100, 100, 100], sp=0.2)
    t = eng.simular(P, [(3, 1)], 2.0, 0.0, None, "rr", None, None)[0].iloc[0]
    assert t["motivo"] == "finde" and t["salida"] == 3 and abs(t["R"] - (-0.1)) < 1e-9


def test_el_breakeven_armado_que_cierra_el_viernes_cuenta_por_su_resultado():
    P = _P_semana([100, 102.5, 102.0, 102.1, 110], [100, 100.5, 100.5, 100.6, 99])
    P.c[3] = 101.0
    be = {"act_modo": "r", "act_valor": 1.0, "nivel_modo": "r", "nivel_valor": 0.0, "vu": 10.0}
    t = eng.simular(P, [(0, 1)], 5.0, 0.0, None, "rr", None, be)[0].iloc[0]
    assert t["motivo"] == "finde" and t["res"] == "TP" and t["be"] == 1 and abs(t["R"] - 0.5) < 1e-9


def test_ninguna_operacion_cruza_el_fin_de_semana_sin_mantener():
    df = _df(10)
    for kw in ({}, dict(pullback_activo=True, pullback_pct=50.0, pullback_velas=200)):
        for mant in (True, False):
            cfg = _cfg(finde_mantener=mant, rr=6.0, **kw)
            P = eng.preparar(df, cfg)
            tr = eng.ejecutar(P, cfg).trades
            ab = tr[tr["res"] != "ABIERTA"]
            semana = lambda j: (df.index[j] - pd.Timedelta(days=df.index[j].weekday())).normalize()
            cruza = [(semana(r["i"]) != semana(r["salida"])) for _, r in ab.iterrows()]
            if mant:
                assert any(cruza) or len(ab) == 0       # con RR alto y velas de 15 min alguna cruza (control del test)
            else:
                assert len(ab) > 0 and not any(cruza)
                assert (ab["motivo"] == "finde").any()


def test_pendiente_del_pullback_se_cancela_al_cierre_de_la_semana():
    df = _df(10, seed=9)
    base = dict(pullback_activo=True, pullback_pct=100.0, pullback_velas=2000, rr=6.0)      # esperaria casi sin limite de tiempo
    a = eng.ejecutar(eng.preparar(df, _cfg(finde_mantener=True, **base)), _cfg(finde_mantener=True, **base))
    b = eng.ejecutar(eng.preparar(df, _cfg(finde_mantener=False, **base)), _cfg(finde_mantener=False, **base))
    assert b.pb["caducadas"] >= a.pb["caducadas"]
    tr = b.trades
    semana = lambda j: (df.index[j] - pd.Timedelta(days=df.index[j].weekday())).normalize()
    assert all(semana(r["señal"]) == semana(r["i"]) for _, r in tr.iterrows())        # se llena en la misma semana de la orden


def test_viernes_solo_se_abre_hasta_la_hora_elegida_en_hora_de_ny():
    df = _df(6)
    # invierno: servidor GMT+2 -> NY = servidor - 7 h. 12:00 de NY = 19:00 del servidor
    cfg = _cfg(finde_mantener=False, finde_no_abrir_desde=12.0)
    P = eng.preparar(df, cfg)
    quien = pd.Series(P.bloq_vie, index=df.index)
    assert quien[(df.index.weekday == 4) & (df.index.hour >= 19)].all()
    assert not quien[(df.index.weekday == 4) & (df.index.hour < 19)].any() and not quien[df.index.weekday < 4].any()
    bloqueadas = [(i, m) for i, _, m in P.cruces if m == "viernes"]
    assert bloqueadas and all(df.index[i].weekday() == 4 and df.index[i].hour >= 19 for i, _ in bloqueadas)
    tomadas = eng.ejecutar(P, cfg).trades
    assert not ((df.index[tomadas["señal"].to_numpy()].weekday == 4) & (df.index[tomadas["señal"].to_numpy()].hour >= 19)).any()
    # en verano (EE.UU. cambia el 10/3) el mismo corte en hora de NY cae una hora antes en el servidor... y es el servidor +/- DST
    # (el servidor sigue a EE.UU.: la diferencia con NY se mantiene en 7 h), asi que es el mismo 19:00 del servidor
    assert P.bloq_vie is not None


def test_sin_hora_de_viernes_no_bloquea_nada_y_por_defecto_todo_igual():
    df = _df(6)
    a = eng.preparar(df, _cfg(finde_mantener=False))
    assert a.bloq_vie is None and all(m != "viernes" for _, _, m in a.cruces)
    base = eng.preparar(df, _cfg())
    assert base.fs is None and base.bloq_vie is None
    assert [x for x in eng.ejecutar(base, _cfg()).trades["R"]] == [x for x in eng.ejecutar(eng.preparar(df, _cfg(finde_mantener=True)), _cfg(finde_mantener=True)).trades["R"]]


def test_validaciones():
    import pytest
    with pytest.raises(ValueError):
        eng.Config(finde_mantener=False, finde_no_abrir_desde=12.0).validar()
    with pytest.raises(ValueError):
        _cfg(finde_mantener=False, finde_no_abrir_desde=25.0).validar()
    _cfg(finde_mantener=False, finde_no_abrir_desde=12.0).validar()
    eng.Config(finde_mantener=False).validar()          # sin hora de viernes no hace falta el desfase


def test_metricas_cuentan_el_cierre_de_fin_de_semana():
    P = _P_semana([100, 101, 101.5, 101.4, 110, 110], [100, 99.5, 100.5, 100.6, 99, 99])
    P.c[3] = 101.0
    tr, _ = eng.simular(P, [(0, 1)], 2.0, 0.0, None, "rr", None, None)
    r = met.resumen(tr, 2.0)
    assert r["resueltas"] == 1 and r["TP"] == 1 and abs(r["R_total"] - 0.5) < 1e-9


def test_la_ultima_vela_de_la_semana_no_abre_y_el_bot_lo_dice_igual():
    df = _df()
    P = eng.preparar(df, _cfg(finde_mantener=False))
    ult = {int(j) for j in np.unique(P.fs) if j < len(df)}
    blq = {i for i, _, m in P.cruces if m == "viernes"}
    assert blq <= ult
    for i, _, m in P.cruces:
        if i in ult:
            assert m == "viernes"


def test_el_bot_lleva_la_regla_de_fin_de_semana():
    import generar_bot as gb
    base = dict(servidor_offset_horas=2.0)
    a = gb.generar_mq5(eng.Config(**base), "XAUUSD", "M15", 0.1, veredicto={"nivel": "ok", "titulo": "x"})
    assert "InpFindeMantener  = true" in a and "InpFindeBloq      = false" in a and "@@" not in a
    cfg = eng.Config(**base, finde_mantener=False, finde_no_abrir_desde=12.0)
    b = gb.generar_mq5(cfg, "XAUUSD", "M15", 0.1, veredicto={"nivel": "ok", "titulo": "x"})
    assert "InpFindeMantener  = false" in b and "InpFindeBloq      = true" in b and "InpFindeBloqH     = 12.0" in b
    assert "ManageFinde();" in b and "if(FindeBloqueaEntrada(g_time[i])) return false;" in b
    assert "16:59 de Nueva York" in b and "desde las 12:00" in b
    # el magic no cambia si no se usa la regla, y cambia si se usa
    assert gb._magic(eng.Config(**base), "XAUUSD") == gb._magic(eng.Config(**base, finde_mantener=True), "XAUUSD")
    assert gb._magic(eng.Config(**base), "XAUUSD") != gb._magic(cfg, "XAUUSD")


def test_bot_compila_y_su_regla_del_viernes_coincide_con_la_del_motor():
    import shutil
    import tempfile
    import subprocess
    import generar_bot as gb
    import sessions as ses
    import test_generar_bot as tg
    if not shutil.which("g++"):
        import pytest
        pytest.skip("sin g++")
    cfg = eng.Config(servidor_offset_horas=2.0, finde_mantener=False, finde_no_abrir_desde=12.0)
    t = tg._gen(cfg, "XAUUSD", "H1", 0.1)
    main = r'int main(){long long t;while(std::cin>>t){printf("%d\n",FindeBloqueaEntrada((datetime)t)?1:0);}}'
    # velas H1 (hora del servidor) de una semana de enero (invierno) y una de julio (verano), de lunes a domingo
    idx = pd.DatetimeIndex(list(pd.date_range("2024-01-08", periods=24 * 7, freq="h")) + list(pd.date_range("2024-07-08", periods=24 * 7, freq="h"))
                           + list(pd.date_range("2024-03-04", periods=24 * 14, freq="h")))      # y dos semanas con el cambio de EE.UU. (10/3)
    utc = pd.DatetimeIndex(ses.servidor_a_utc(idx, 2.0, True)).tz_localize("UTC").tz_convert("America/New_York")
    h = utc.hour.to_numpy() + utc.minute.to_numpy() / 60.0
    esperado = ((utc.weekday.to_numpy() == 4) & ((h + 1.0 >= 17.0 - 1e-9) | (h >= 12.0))).astype(int)
    with tempfile.TemporaryDirectory() as d:
        exe = tg._compilar(t, main, d)
        entrada = "\n".join(str(int(x.timestamp())) for x in idx)
        out = subprocess.run([exe], input=entrada, capture_output=True, text=True).stdout.split()
    assert [int(x) for x in out] == list(esperado) and esperado.sum() > 20
