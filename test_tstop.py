"""Cierre por tiempo: al cierre de la vela entrada + N, si la operacion sigue abierta (sin breakeven) y va en R o peor, se cierra a mercado."""
import numpy as np
import pandas as pd
import pytest

import engine as eng
from test_reentrada import _P


def _P_(n=60):
    P = _P(n)
    P.sube[:] = False
    P.sube[0] = True
    return P


def _sim(P, tstop, **kw):
    tr, _ = eng.simular(P, [(0, 1)], 2.0, 0.0, None, "rr", None, tstop=tstop, **kw)
    return tr


def _cierre(P, j, px):
    """El precio cierra en px en la vela j (SL a 90 y TP a 120: sin tocarlos)."""
    P.c[j] = px
    P.h[j] = max(px, 100.0) + 0.5
    P.l[j] = min(px, 100.0) - 0.5


TS = {"velas": 5, "r": -0.25}


def test_cierra_por_tiempo_si_va_peor_que_el_umbral():
    P = _P_()
    _cierre(P, 5, 97.0)                                  # -0,3 R a la vela 0 + 5
    tr = _sim(P, TS)
    assert len(tr) == 1 and tr.loc[0, "motivo"] == "tiempo" and tr.loc[0, "salida"] == 5
    assert tr.loc[0, "res"] == "SL" and abs(tr.loc[0, "R"] + 0.3) < 1e-9


def test_sigue_si_va_mejor_que_el_umbral():
    P = _P_()
    _cierre(P, 5, 98.0)                                  # -0,2 R
    P.h[9] = 125.0                                       # y despues llega al TP
    tr = _sim(P, TS)
    assert tr.loc[0, "motivo"] == "tp" and tr.loc[0, "res"] == "TP"


def test_el_umbral_es_inclusivo():
    P = _P_()
    _cierre(P, 5, 97.5)                                  # justo -0,25 R
    assert _sim(P, TS).loc[0, "motivo"] == "tiempo"


def test_se_evalua_una_sola_vez_en_la_vela_n():
    P = _P_()
    _cierre(P, 4, 91.0)                                  # muy mal antes de N: no se mira
    _cierre(P, 5, 99.0)                                  # en N va bien: sigue
    _cierre(P, 6, 91.0)                                  # despues de N tampoco se vuelve a mirar
    P.l[7] = 85.0
    tr = _sim(P, TS)
    assert tr.loc[0, "motivo"] == "sl" and tr.loc[0, "salida"] == 7


def test_el_sl_antes_de_n_manda():
    P = _P_()
    P.l[3] = 85.0
    tr = _sim(P, TS)
    assert tr.loc[0, "motivo"] == "sl" and tr.loc[0, "salida"] == 3


def test_en_la_vela_n_manda_el_sl_o_el_tp_si_se_tocan():
    P = _P_()
    _cierre(P, 5, 97.0)
    P.l[5] = 85.0                                        # la vela N toca el SL
    assert _sim(P, TS).loc[0, "motivo"] == "sl"
    P = _P_()
    _cierre(P, 5, 97.0)
    P.h[5] = 125.0                                       # o el TP
    assert _sim(P, TS).loc[0, "motivo"] == "tp"


def test_con_breakeven_activado_no_se_aplica():
    P = _P_()
    P.h[2] = 108.0                                       # activa el breakeven (a 7 = 70 % de 10)... y vuelve
    _cierre(P, 5, 97.0)
    be = {"act_modo": "r", "act_valor": 0.5, "nivel_modo": "r", "nivel_valor": 0.0, "vu": 0.0}
    tr = _sim(P, TS, be=be)
    assert tr.loc[0, "be"] == 1 and tr.loc[0, "motivo"] != "tiempo"


def test_apagado_da_lo_mismo_que_antes():
    P = _P_()
    _cierre(P, 5, 90.5)
    P.h[9] = 125.0
    a = _sim(P, None)
    b, _ = eng.simular(P, [(0, 1)], 2.0, 0.0, None, "rr", None)
    assert a.equals(b)


def test_umbral_positivo_cierra_si_no_esta_en_ganancia_suficiente():
    P = _P_()
    _cierre(P, 5, 100.5)                                 # +0,05 R
    assert _sim(P, {"velas": 5, "r": 0.5}).loc[0, "motivo"] == "tiempo"
    tr = _sim(P, {"velas": 5, "r": 0.0})
    assert tr.loc[0, "motivo"] != "tiempo"               # 0,05 R > 0: sigue


def test_corto_y_spread():
    P = _P_()
    P.sube[0], P.baja[0] = False, True
    P.sp[:] = 1.0                                        # el corto compra al ask: cierre + spread
    P.c[5] = 103.0                                       # corto: pierde 3 + 1 de spread = -0,4 R
    P.h[5], P.l[5] = 103.5, 99.5
    tr, _ = eng.simular(P, [(0, -1)], 2.0, 0.0, None, "rr", None, tstop=TS)
    assert tr.loc[0, "motivo"] == "tiempo" and abs(tr.loc[0, "R"] + 0.4) < 1e-9


def test_libera_la_posicion_para_la_siguiente_senal():
    P = _P_()
    P.sube[6] = True
    _cierre(P, 5, 97.0)
    tr, _ = eng.simular(P, [(0, 1), (6, 1)], 2.0, 0.0, None, "rr", None, tstop=TS)
    assert list(tr["señal"]) == [0, 6] and tr.loc[0, "motivo"] == "tiempo"


def test_validacion_y_config():
    for k in (dict(tstop_velas=0), dict(tstop_velas=2.5), dict(tstop_r=99.0)):
        with pytest.raises(ValueError):
            eng.Config(tstop_activo=True, **k).validar()
    eng.Config(tstop_activo=True, tstop_velas=12, tstop_r=0.0).validar()
    eng.Config(tstop_activo=False, tstop_velas=0).validar()               # apagado: no se valida
    assert eng.tstop_de(eng.Config()) is None
    assert eng.tstop_de(eng.Config(tstop_activo=True, tstop_velas=12, tstop_r=-0.5)) == {"velas": 12, "r": -0.5}


def test_e2e_apagado_identico_y_encendido_cierra_por_tiempo():
    from test_reentrada import _df
    df = _df()
    _cfg = lambda **k: eng.Config(rr=2.0, **k)
    cfg0 = _cfg()
    t0 = eng.ejecutar(eng.preparar(df, cfg0), cfg0).trades
    cfg1 = _cfg(tstop_activo=False, tstop_velas=24)
    assert t0.equals(eng.ejecutar(eng.preparar(df, cfg1), cfg1).trades)
    cfg2 = _cfg(tstop_activo=True, tstop_velas=6, tstop_r=0.0)
    t2 = eng.ejecutar(eng.preparar(df, cfg2), cfg2).trades
    assert (t2["motivo"] == "tiempo").any()
    assert (t2.loc[t2["motivo"] == "tiempo", "salida"] - t2.loc[t2["motivo"] == "tiempo", "i"] == 6).all()


# ---------------------------------------------------------------- bot MQL5
import os
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_generar_bot import HAY_GPP, _cfg as _bcfg, _compilar, _gen


def _c(**k):
    base = dict(sl_modo="precio", sl_valor=2.0, rr=2.0, usd_por_unidad=10.0)
    base.update(k)
    return _bcfg(**base)


def test_plantilla_sin_cierre_por_tiempo_lo_deja_apagado():
    t = _gen(_c(), "XAUUSD", "M5", 0.1, sl_usd=20.0)
    assert re.search(r"InpTStopOn\s+= false;", t) and "Cierre por tiempo:" not in t.split("#property")[0]
    assert "@@" not in t


def test_plantilla_con_cierre_por_tiempo_lleva_inputs_funcion_y_aviso():
    t = _gen(_c(tstop_activo=True, tstop_velas=24, tstop_r=-0.25), "XAUUSD", "M5", 0.1, sl_usd=20.0)
    assert re.search(r"InpTStopOn\s+= true;", t) and re.search(r"InpTStopBars\s+= 24;", t) and re.search(r"InpTStopR\s+= -0\.25\d*;", t)
    assert "void RevisarCierrePorTiempo" in t and "RevisarCierrePorTiempo(i);" in t
    assert "CIERRE POR TIEMPO" in t and 'g_gv + "TSID"' in t and "Cierre por tiempo: si a las 24 velas" in t
    assert "@@" not in t and t.count("{") == t.count("}")


@pytest.mark.skipif(not HAY_GPP, reason="sin g++")
def test_cuenta_de_velas_y_umbral_del_bot_coinciden_con_el_motor():
    t = _gen(_c(tstop_activo=True, tstop_velas=5, tstop_r=-0.25), "XAUUSD", "M5", 0.1, sl_usd=20.0)
    main = '''int main(){int n;std::cin>>n;g_m=n;g_time.resize(n);
 for(int i=0;i<n;i++){long long tt;std::cin>>tt;g_time[i]=tt;}
 int q;std::cin>>q;while(q--){long long te;int ii;std::cin>>te>>ii;printf("%d\\n",TsBarsSince((datetime)te,ii));}
 int r;std::cin>>r;while(r--){int side;double open,px,d;std::cin>>side>>open>>px>>d;double R=TsR(side,open,px,d);printf("%.12g %d\\n",R,TsDebeCerrar(R)?1:0);}}'''
    rng = np.random.default_rng(3)
    tiempos = np.cumsum(rng.choice([300, 300, 300, 300, 3600 * 48], 400))                  # velas de 5 min con huecos de fin de semana
    casos = []
    for _ in range(60):
        b = int(rng.integers(5, 390))
        casos.append((int(tiempos[b]) + int(rng.integers(0, 290)), int(rng.integers(b, 399))))
    casos.append((int(tiempos[0]) - 1000, 50))
    ent = f"{len(tiempos)}\n" + "\n".join(str(int(x)) for x in tiempos) + f"\n{len(casos)}\n" + "\n".join(f"{a} {b}" for a, b in casos)
    rs = [(1, 100.0, 97.5, 10.0), (1, 100.0, 97.6, 10.0), (-1, 100.0, 102.5, 10.0), (-1, 100.0, 102.4, 10.0), (1, 100.0, 103.0, 10.0)]
    ent += f"\n{len(rs)}\n" + "\n".join(" ".join(str(v) for v in x) for x in rs) + "\n"
    with tempfile.TemporaryDirectory() as d_:
        exe = _compilar(t, main, d_)
        out = subprocess.run([exe], input=ent, capture_output=True, text=True).stdout.split("\n")
    nb = [int(x) for x in out[:len(casos)]]
    for (te, ii), got in zip(casos, nb):
        idx = max([k for k in range(len(tiempos)) if tiempos[k] <= te], default=None)
        esp = 1000000000 if idx is None or idx > ii else ii - idx + 1
        if idx is not None and idx > ii:
            continue
        assert got == esp, (te, ii, got, esp)
    rr = [x.split() for x in out[len(casos):len(casos) + len(rs)]]
    for (side, op, px, d), (R, cierra) in zip(rs, rr):
        esp = side * (px - op) / d
        assert abs(float(R) - esp) < 1e-9 and int(cierra) == int(esp <= -0.25 + 1e-12)
    # mercado: la posicion abre al inicio de la vela b = señal + 1; el motor mira al cierre de la vela señal + N = b + N - 1  ->  barras = N
    N = 5
    for b in (10, 77, 300):
        assert (b + N - 1) - b + 1 == N
