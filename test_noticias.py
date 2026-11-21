"""Trading de noticias: regla 1 (no abrir cerca de la noticia) y regla 2 (cerrar antes si va en R o peor)."""
import numpy as np
import pandas as pd
import pytest

import engine as eng
import noticias as nt
from test_reentrada import _P

N5 = 300
E_VELA = 20                                              # la noticia sale al inicio de la vela 20 (00:100 min desde el inicio)


def _ep(P, vela):
    return int(pd.Timestamp(P.indice[vela]).value // 10**9)


def _P_(n=60, minutos=6.0, vela_noticia=E_VELA):
    P = _P(n)
    P.sube[:] = False
    P.sube[0] = True
    P.noti = nt.armar(P.indice, [_ep(P, vela_noticia)], minutos)
    P.noti["cerrar_r"] = -0.5
    return P


def _sim(P, r=-0.5, señales=((0, 1),), **kw):
    nr = None if r is None else {"r": r}
    tr, _ = eng.simular(P, list(señales), 2.0, 0.0, None, "rr", None, nrule=nr, **kw)
    return tr


def test_mascaras_ventana_de_6_minutos_con_velas_de_5():
    P = _P_()
    M = P.noti
    assert list(np.flatnonzero(M["ent"])) == [18, 19, 20]          # cierres a las 95, 100 y 105 min: dentro de [94, 106]
    assert list(np.flatnonzero(M["ov"])) == [18, 19, 20, 21]        # velas que tocan la ventana
    assert list(np.flatnonzero(M["cierre"])) == [17]                # ultima vela que cierra (90) antes del inicio de la ventana (94)
    assert M["cierre"][17] == _ep(P, E_VELA)


def test_ventana_justo_en_el_borde():
    P = _P_(minutos=5.0)                                 # ventana [95, 105]: el cierre a las 95 y a las 105 entran (inclusivo)
    assert list(np.flatnonzero(P.noti["ent"])) == [18, 19, 20]
    assert list(np.flatnonzero(P.noti["cierre"])) == [18]            # la vela que cierra a las 95 justo al inicio de la ventana


def test_regla2_cierra_si_va_peor():
    P = _P_()
    P.c[17] = 94.0                                       # -0,6 R al cierre de la vela 17, antes de la ventana
    tr = _sim(P)
    assert len(tr) == 1 and tr.loc[0, "motivo"] == "noticia" and tr.loc[0, "salida"] == 17
    assert tr.loc[0, "res"] == "SL" and abs(tr.loc[0, "R"] + 0.6) < 1e-9
    assert tr.loc[0, "noticia_ev"] == _ep(P, E_VELA)


def test_regla2_no_cierra_si_va_mejor_o_en_ganancia():
    for px in (96.0, 100.0, 108.0):
        P = _P_()
        P.c[17] = px
        P.l[17] = min(px, 100.0) - 0.5
        P.h[17] = max(px, 100.0) + 0.5
        tr = _sim(P)
        assert tr.loc[0, "motivo"] != "noticia"


def test_regla2_umbral_inclusivo():
    P = _P_()
    P.c[17] = 95.0                                       # justo -0,5 R
    assert _sim(P).loc[0, "motivo"] == "noticia"


def test_regla2_con_breakeven_activado_sigue():
    P = _P_()
    P.h[2] = 108.0
    P.c[17] = 94.0
    be = {"act_modo": "r", "act_valor": 0.5, "nivel_modo": "r", "nivel_valor": 0.0, "vu": 0.0}
    tr = _sim(P, be=be)
    assert tr.loc[0, "be"] == 1 and tr.loc[0, "motivo"] != "noticia"


def test_regla2_sin_r_no_cierra_nada():
    P = _P_()
    P.c[17] = 94.0
    P.l[17] = 93.5
    assert _sim(P, r=None).loc[0, "motivo"] != "noticia"


def test_regla2_el_sl_de_esa_vela_manda():
    P = _P_()
    P.c[17] = 94.0
    P.l[17] = 85.0                                       # esa vela toca el SL
    assert _sim(P).loc[0, "motivo"] == "sl"


def test_regla2_corto_y_spread():
    P = _P_()
    P.sube[0] = False
    P.baja[0] = True
    P.c[17] = 105.0
    P.h[17] = 105.5
    P.sp[17] = 0.5                                       # el corto compra al ask: 105,5 -> -0,55 R: cierra
    tr, _ = eng.simular(P, [(0, -1)], 2.0, 0.0, None, "rr", None, nrule={"r": -0.5})
    assert tr.loc[0, "motivo"] == "noticia" and abs(tr.loc[0, "R"] + 0.55) < 1e-9


def test_tiempo_gana_si_coinciden():
    P = _P_()
    P.c[17] = 94.0
    P.l[17] = 93.5
    tr = _sim(P, tstop={"velas": 17, "r": -0.25})
    assert tr.loc[0, "motivo"] == "tiempo"


def test_el_cierre_libera_la_posicion_para_la_siguiente_señal():
    P = _P_()
    P.c[17] = 94.0
    P.l[17] = 93.5
    P.sube[30] = True
    tr = _sim(P, señales=((0, 1), (30, 1)))
    assert list(tr["i"]) == [0, 30]


def test_apagado_identico():
    P = _P_()
    P.c[17] = 94.0
    P.l[17] = 93.5
    a = _sim(P, r=None)
    P2 = _P_()
    P2.noti = None
    P2.c[17] = 94.0
    P2.l[17] = 93.5
    tr, _ = eng.simular(P2, [(0, 1)], 2.0, 0.0, None, "rr", None)
    assert list(a["R"]) == list(tr["R"]) and list(a["motivo"]) == list(tr["motivo"])
    assert "noticia_ev" not in tr.columns


# ----------------------------------------------------------- reentradas y ordenes limite
def _reent(**k):
    from test_reentrada import _reent as r
    return r(**k)


def test_reentrada_por_confirmacion_no_entra_en_la_ventana():
    P = _P_()
    P.h[5] = 125.0                                       # la primera gana
    P.l[19] = 97.0                                       # y el retroceso a la media cae en la vela 19 (cierre dentro de la ventana)
    tr, _ = eng.simular(P, [(0, 1)], 2.0, 0.0, None, "rr", None, reent=_reent())
    assert len(tr) == 1 and tr.loc[0, "reentrada"] == 0
    P = _P_()
    P.h[5] = 125.0
    P.l[10] = 97.0                                       # lejos de la noticia: entra
    tr, _ = eng.simular(P, [(0, 1)], 2.0, 0.0, None, "rr", None, reent=_reent())
    assert len(tr) == 2 and tr.loc[1, "reentrada"] == 1


def test_orden_limite_pullback_se_cancela_al_empezar_la_ventana():
    P = _P_(vela_noticia=E_VELA)
    P.ema_c[:] = 98.0
    P.ema_l[:] = 98.0
    P.l[19] = 90.0                                       # tocaria el nivel del pullback dentro de la ventana
    pb = {"pct": 50.0, "ema": "corta", "velas": 40}
    tr, _ = eng.simular(P, [(0, 1)], 2.0, 0.0, pb, "rr", None)
    assert len(tr) == 0 and tr.attrs["pb"]["noticias"] == 1
    P.l[19] = 99.9
    P.l[10] = 90.0                                       # llena antes de la ventana
    tr, _ = eng.simular(P, [(0, 1)], 2.0, 0.0, pb, "rr", None)
    assert len(tr) == 1 and tr.attrs["pb"]["noticias"] == 0


# ----------------------------------------------------------- detectar / csv / config
def test_validar():
    base = dict(noticias_activo=True, servidor_offset_horas=2.0)
    eng.Config(**base).validar()
    for k in (dict(noticias_min=0), dict(noticias_min=500), dict(noticias_fuente="otra"), dict(noticias_fuente="csv"),
              dict(noticias_cerrar_r=99.0), dict(noticias_rango_atr=0)):
        with pytest.raises(ValueError):
            eng.Config(**{**base, **k}).validar()
    with pytest.raises(ValueError):
        eng.Config(noticias_activo=True).validar()       # sin desfase horario
    eng.Config(**{**base, "noticias_cerrar_r": None}).validar()
    eng.Config(noticias_activo=False, noticias_fuente="otra").validar()      # apagado: no se valida


def test_csv():
    txt = ("fecha_hora_utc,moneda,impacto\n2024-01-05 13:30:00,USD,high\n2024-01-05 13:30:00,USD,High\n2024-01-05 15:00:00,EUR,high\n"
           "2024-01-06 15:00:00,USD,low\n2024-01-10 19:00:00,USD,3\n")
    ev, info = nt.leer_csv(txt.encode())
    assert len(ev) == 2 and info["usd_alto"] == 2 and info["filas"] == 5
    assert pd.Timestamp(ev[0], unit="s") == pd.Timestamp("2024-01-05 13:30")
    with pytest.raises(ValueError):
        nt.leer_csv("a,b\n1,2\n")
    with pytest.raises(ValueError):
        nt.leer_csv("fecha_hora_utc,moneda,impacto\n2024-01-05 13:30:00,EUR,high\n")


def _df_gold(offset=2.0):
    """Dias habiles de velas de 5 min en hora del servidor (UTC+2, enero = sin DST) con una vela enorme el viernes 5/1/2024 a las 8:30 NY."""
    idx = pd.date_range("2024-01-02 00:00", "2024-01-06 00:00", freq="5min", inclusive="left")
    rng = np.random.default_rng(1)
    c = 2000 + np.cumsum(rng.normal(0, 0.3, len(idx)))
    df = pd.DataFrame({"Open": c, "High": c + 0.4, "Low": c - 0.4, "Close": c, "Spread": 0.2}, index=idx)
    k = df.index.get_loc(pd.Timestamp("2024-01-05 15:30"))           # 8:30 NY = 13:30 UTC = 15:30 servidor
    df.iloc[k, df.columns.get_loc("High")] += 12.0
    df.iloc[k, df.columns.get_loc("Low")] -= 3.0
    return df, k


def test_deteccion_en_velas():
    df, k = _df_gold()
    cfg = eng.Config(noticias_activo=True, servidor_offset_horas=2.0, servidor_dst_eeuu=False)
    ev, años, av = nt.eventos_en_velas(df, cfg)
    assert list(ev) == [int(pd.Timestamp("2024-01-05 13:30").value // 10**9)] and años == {2024: 1} and av == []
    cfg2 = eng.Config(noticias_activo=True, servidor_offset_horas=2.0, servidor_dst_eeuu=False, noticias_rango_min=50.0)
    assert len(nt.eventos_en_velas(df, cfg2)[0]) == 0


def test_deteccion_avisa_con_velas_largas():
    df, _ = _df_gold()
    h1 = df.resample("1h").agg({"Open": "first", "High": "max", "Low": "min", "Close": "last", "Spread": "mean"}).dropna()
    cfg = eng.Config(noticias_activo=True, servidor_offset_horas=2.0)
    ev, _, av = nt.eventos_en_velas(h1, cfg)
    assert len(ev) == 0 and av and "30 minutos" in av[0]


def test_e2e_apagado_identico_y_encendido_descarta_y_cierra():
    from test_reentrada import _df
    df = _df()
    cfg0 = eng.Config(rr=2.0)
    r0 = eng.ejecutar(eng.preparar(df, cfg0), cfg0)
    cfg1 = eng.Config(rr=2.0, noticias_activo=False, noticias_min=30)
    r1 = eng.ejecutar(eng.preparar(df, cfg1), cfg1)
    assert r0.trades.equals(r1.trades) and r0.descartes == r1.descartes
    # con un calendario que tiene una noticia cada ~3 h las señales cercanas se descartan
    idx = df.index
    evs = tuple(int(pd.Timestamp(idx[j]).value // 10**9) + 2 * 3600 * 0 for j in range(200, len(idx), 150))
    cfg2 = eng.Config(rr=2.0, noticias_activo=True, noticias_fuente="csv", noticias_eventos=evs, noticias_min=30, servidor_offset_horas=0.0,
                      servidor_dst_eeuu=False)
    P = eng.preparar(df, cfg2)
    r2 = eng.ejecutar(P, cfg2)
    assert r2.descartes.get("noticias", 0) > 0 and len(r2.trades) <= len(r0.trades) + 3
    for _, t in r2.trades.iterrows():                    # ninguna entrada cae en la ventana de una noticia
        fin = P.indice[int(t["señal"])]
        e = int(pd.Timestamp(fin).value // 10**9) + 300
        assert all(abs(e - x) > 30 * 60 for x in evs)


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


def test_plantilla_sin_noticias_las_deja_apagadas():
    t = _gen(_c(), "XAUUSD", "M5", 0.1, sl_usd=20.0)
    assert re.search(r"InpNewsOn\s+= false;", t) and "@@" not in t and t.count("{") == t.count("}")
    assert re.search(r"InpNewsCloseOn\s+= false;", t)


def test_plantilla_con_noticias():
    t = _gen(_c(noticias_activo=True, noticias_min=6.0, noticias_cerrar_r=-0.5, servidor_offset_horas=2.0), "XAUUSD", "M5", 0.1, sl_usd=20.0)
    assert re.search(r"InpNewsOn\s+= true;", t) and re.search(r"InpNewsMin\s+= 6(\.0+)?;", t)
    assert re.search(r"InpNewsCloseOn\s+= true;", t) and re.search(r"InpNewsCloseR\s+= -0\.5\d*;", t)
    for frag in ("CalendarValueHistory", "CALENDAR_IMPORTANCE_HIGH", "Senal descartada por noticia", "Cierre antes de noticia",
                 "NO SE PUDO CERRAR ANTES DE LA NOTICIA", "CIERRE ANTES DE LA NOTICIA", 'g_gv + "NEID"', "NewsBarra(i);", "NewsOnTick();",
                 "MQL_TESTER", "CALENDARIO DE NOTICIAS NO DISPONIBLE", "Pullback cancelado: noticia."):
        assert frag in t, frag
    assert "@@" not in t and t.count("{") == t.count("}")
    t2 = _gen(_c(noticias_activo=True, noticias_cerrar_r=None, servidor_offset_horas=2.0), "XAUUSD", "M5", 0.1, sl_usd=20.0)
    assert re.search(r"InpNewsCloseOn\s+= false;", t2)


@pytest.mark.skipif(not HAY_GPP, reason="sin g++")
def test_ventanas_y_cierre_del_bot_coinciden_con_el_motor():
    N = 6.0
    t = _gen(_c(noticias_activo=True, noticias_min=N, noticias_cerrar_r=-0.5, servidor_offset_horas=2.0), "XAUUSD", "M5", 0.1, sl_usd=20.0)
    main = '''int main(){g_psec=300;int n;std::cin>>n;g_m=n;g_time.resize(n);
 for(int i=0;i<n;i++){long long tt;std::cin>>tt;g_time[i]=tt;}
 int m;std::cin>>m;ArrayResize(g_newsT,m);ArrayResize(g_newsN,m);g_newsM=m;
 for(int k=0;k<m;k++){long long e;std::cin>>e;g_newsT[k]=e;g_newsN[k]="n"+std::to_string(k);}
 for(int i=0;i<n;i++){std::string nom;long long ini=g_time[i],fin=ini+300;
   int ent=NewsBloquea((datetime)fin,(datetime)fin,nom)?1:0; int ov=NewsBloquea((datetime)ini,(datetime)fin,nom)?1:0;
   printf("%d %d %lld\\n",ent,ov,(long long)NewsCierreDe(i));}
 int r;std::cin>>r;while(r--){double R;std::cin>>R;printf("%d\\n",NewsDebeCerrar(R)?1:0);}}'''
    rng = np.random.default_rng(7)
    base = pd.date_range("2024-01-02 00:00", periods=900, freq="5min")
    idx = base.append(pd.date_range(base[-1] + pd.Timedelta(hours=60), periods=300, freq="5min"))         # hueco de fin de semana
    ep = idx.values.astype("datetime64[s]").astype(np.int64)
    evs, cur = [], int(ep[0]) + 1800
    while cur < int(ep[-1]) - 600:
        evs.append(cur)                                                                         # separadas 10+ min: una por ventana
        cur += int(rng.integers(600, 9000))
    evs = sorted(set(evs + [int(ep[40]), int(ep[41]) + 150, int(ep[500]) + 290]))               # y algunas justo en los bordes
    evs = [e for i, e in enumerate(evs) if i == 0 or e - evs[i - 1] >= 600]
    rs = [-0.6, -0.5, -0.4999, 0.0, 0.3]
    ent = f"{len(ep)}\n" + "\n".join(str(int(x)) for x in ep) + f"\n{len(evs)}\n" + "\n".join(str(e) for e in evs)
    ent += f"\n{len(rs)}\n" + "\n".join(str(x) for x in rs) + "\n"
    with tempfile.TemporaryDirectory() as d_:
        exe = _compilar(t, main, d_)
        out = subprocess.run([exe], input=ent, capture_output=True, text=True).stdout.split("\n")
    M = nt.armar(idx, evs, N)
    for i in range(len(ep)):
        e_, o_, c_ = out[i].split()
        assert (int(e_) == 1) == bool(M["ent"][i]), i
        assert (int(o_) == 1) == bool(M["ov"][i]), i
        assert int(c_) == int(M["cierre"][i]), (i, c_, M["cierre"][i])
    assert M["ent"].any() and (M["cierre"] != 0).sum() >= len(evs) // 2
    got = [int(x) for x in out[len(ep):len(ep) + len(rs)]]
    assert got == [1, 1, 0, 0, 0]


def test_cuenta_de_noticias_del_motor_igual_que_umbral_del_bot():
    # el motor cierra con R <= umbral (+1e-12); el bot igual: NewsDebeCerrar
    P = _P_()
    for px, esp in ((95.0, "noticia"), (95.1, "sl_o_tp_o_abierta")):
        P2 = _P_()
        P2.c[17] = px
        P2.l[17] = min(px, 100.0) - 0.5
        P2.h[17] = 100.5
        m = _sim(P2).loc[0, "motivo"]
        assert (m == "noticia") == (esp == "noticia")
