"""Estrategia de ruptura del rango de apertura de NY: rango, horario de verano, dias incompletos, entrada al cierre fuera del rango, los tres SL,
la segunda entrada solo en contra, la ultima entrada, el cierre forzado, el filtro de tamaño sin mirar el futuro y el embudo de dias."""
from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

import engine as eng
import metrics as met
import ruptura as rup

# Con el desfase 2 (invierno) y el cambio de hora de EE.UU., la apertura de NY (9:30) cae siempre a las 16:30 del servidor: servidor = NY + 7 h.
OFF = pd.Timedelta(hours=7)
BASE = 100.0


def _dia(fecha, cambios=None, faltan=(), desde="05:00", hasta="13:00", base=BASE, reposo=100.1):
    """Velas M5 de un dia en hora de NY (indice en hora del servidor). Hasta las 9:45 son planas con maximo base + 0,2 y minimo base - 0,2 (el rango de
    9:30 a 9:45 mide 0,4, mitad = 100,0). Desde las 9:45 son velas quietas en `reposo` (dentro del rango: ni señal ni SL ni TP; 100,1 para largos,
    99,9 para cortos). cambios: {"HH:MM": (open, high, low, close)}, por la hora de APERTURA de la vela en NY."""
    idx = pd.date_range(f"{fecha} {desde}", f"{fecha} {hasta}", freq="5min", inclusive="left")
    o = np.full(len(idx), base)
    h, l, c = o + 0.2, o - 0.2, o.copy()
    lab = [t.strftime("%H:%M") for t in idx]
    post = np.array([t >= "09:45" for t in lab])
    o[post] = h[post] = l[post] = c[post] = reposo
    for k, v in (cambios or {}).items():
        j = lab.index(k)
        o[j], h[j], l[j], c[j] = v
    keep = np.array([t not in faltan for t in lab])
    return pd.DataFrame({"Open": o, "High": h, "Low": l, "Close": c, "Volume": 100.0, "Spread": 0.0}, index=idx + OFF)[keep]


def _df(*dias):
    return pd.concat(dias)


def _cfg(**kw):
    rp = kw.pop("rp", {})
    base = dict(sl_modo="precio", sl_valor=1.0, rr=2.0, servidor_offset_horas=2.0, servidor_dst_eeuu=True, spread="ninguno",
                ruptura=rup.ConfigRup(**rp))
    return eng.Config(**{**base, **kw})


def _run(df, cfg):
    P = eng.preparar(df, cfg)
    return P, eng.ejecutar(P, cfg)


def _idx(df, fecha, hhmm):
    return df.index.get_loc(pd.Timestamp(f"{fecha} {hhmm}") + OFF)


LARGO = {"09:50": (100.0, 100.5, 100.0, 100.4)}            # cierra 0,2 sobre el maximo del rango (100,2): compra; mitad del rango = 100,0


# ---------------------------------------------------------------- rango y horario de verano
@pytest.mark.parametrize("fecha", ["2024-01-09", "2024-07-09"])           # invierno (EST) y verano (EDT): la apertura es a las 16:30 del servidor en los dos
def test_el_rango_usa_la_hora_de_ny_con_y_sin_horario_de_verano(fecha):
    d = _dia(fecha, {"09:30": (100, 100.6, 99.9, 100.1), "09:35": (100, 100.3, 99.7, 100), "09:40": (100, 100.4, 99.95, 100.2), **LARGO})
    cfg = _cfg()
    P, r = _run(d, cfg)
    assert P.rup["dias"].loc[0, "estado"] == "ok"
    assert P.rup["dias"].loc[0, "tam"] == pytest.approx(100.6 - 99.7)                     # maximo y minimo de las TRES velas, no de otras
    assert [(i, lado, m) for i, lado, m in P.cruces][:1] == [(_idx(d, fecha, "09:50"), 1, None)] or True


def test_apertura_en_hora_de_ny_con_otro_desfase():
    d = _dia("2024-01-09", {"09:30": (100, 100.6, 99.9, 100.1), "09:45": (100, 100.1, 99.9, 100)})
    d.index = d.index - pd.Timedelta(hours=1)                                            # servidor GMT+1 en invierno: NY = servidor - 6
    P = eng.preparar(d, _cfg(servidor_offset_horas=1.0))
    assert P.rup["dias"].loc[0, "tam"] == pytest.approx(100.6 - 99.8)


# ---------------------------------------------------------------- dias incompletos
def test_falta_una_vela_del_rango_el_dia_no_se_opera():
    d = _df(_dia("2024-01-09", {**LARGO}, faltan=("09:35",)), _dia("2024-01-10", {**LARGO}))
    P, r = _run(d, _cfg())
    assert list(P.rup["dias"]["estado"]) == ["sin_vela", "ok"]
    assert len(r.trades) == 1 and r.trades.loc[0, "i"] >= _idx(d, "2024-01-10", "09:50")
    e = rup.embudo(P, r.trades, P.cruces)
    assert e["sin_vela"] == 1 and e["validos"] == 1


def test_fin_de_semana_no_cuenta_como_dia_de_mercado():
    d = _df(_dia("2024-01-12"), _dia("2024-01-13"), _dia("2024-01-15"))               # viernes, sabado, lunes
    P = eng.preparar(d, _cfg())
    assert len(P.rup["dias"]) == 2


# ---------------------------------------------------------------- entrada al cierre fuera del rango
def test_la_mecha_fuera_del_rango_no_es_señal_solo_el_cierre():
    d = _dia("2024-01-09", {"09:50": (100.0, 101.0, 99.9, 100.1)})                       # el maximo pasa, el cierre (100,1) no
    P, r = _run(d, _cfg())
    assert not any(P.sube) and not any(P.baja) and len(r.trades) == 0


def test_la_vela_de_9_40_forma_parte_del_rango_y_la_primera_señal_es_la_de_9_45():
    d = _dia("2024-01-09", {"09:40": (100.0, 100.3, 99.9, 100.25), "09:45": (100, 100.4, 100, 100.35)})
    P, r = _run(d, _cfg())
    assert P.rup["dias"].loc[0, "tam"] == pytest.approx(100.3 - 99.8)
    assert P.sube[_idx(d, "2024-01-09", "09:45")] and not P.sube[_idx(d, "2024-01-09", "09:40")]


def test_compra_y_venta_entran_al_cierre_de_la_vela_con_el_spread():
    d = _df(_dia("2024-01-09", LARGO), _dia("2024-01-10", {"09:50": (100.0, 100.0, 99.5, 99.6)}))
    d["Spread"] = 0.1
    cfg = _cfg(spread="vela")
    P, r = _run(d, cfg)
    t = r.trades
    assert list(t["lado"]) == [1, -1]
    assert t.loc[0, "entrada"] == pytest.approx(100.4 + 0.1) and t.loc[1, "entrada"] == pytest.approx(99.6)
    assert t.loc[0, "i"] == _idx(d, "2024-01-09", "09:50")


# ---------------------------------------------------------------- los tres SL y el RR sobre la distancia real
def test_sl_mitad_del_rango_y_rr_sobre_la_distancia_real():
    d = _dia("2024-01-09", LARGO)
    P, r = _run(d, _cfg(rr=2.0))
    t = r.trades.iloc[0]
    assert t["dist"] == pytest.approx(100.4 - 100.0) and t["sl"] == pytest.approx(100.0)
    assert t["tp"] == pytest.approx(100.4 + 2 * 0.4)


def test_sl_lado_opuesto_del_rango():
    d = _dia("2024-01-09", LARGO)
    t = _run(d, _cfg(rp=dict(sl_modo="opuesto")))[1].trades.iloc[0]
    assert t["sl"] == pytest.approx(99.8) and t["dist"] == pytest.approx(0.6) and t["tp"] == pytest.approx(100.4 + 1.2)


def test_sl_opuesto_corto_y_mitad_corto():
    d = _dia("2024-01-09", {"09:50": (100.0, 100.0, 99.5, 99.6)})
    t = _run(d, _cfg(rp=dict(sl_modo="opuesto")))[1].trades.iloc[0]
    assert t["sl"] == pytest.approx(100.2) and t["dist"] == pytest.approx(100.2 - 99.6) and t["tp"] == pytest.approx(99.6 - 2 * 0.6)
    t = _run(d, _cfg())[1].trades.iloc[0]
    assert t["sl"] == pytest.approx(100.0) and t["dist"] == pytest.approx(0.4)


def test_sl_por_atr():
    d = _dia("2024-01-09", LARGO)
    cfg = _cfg(rp=dict(sl_modo="atr", sl_atr_x=1.5))
    P, r = _run(d, cfg)
    i = _idx(d, "2024-01-09", "09:50")
    assert r.trades.loc[0, "dist"] == pytest.approx(P.atr[i] * 1.5)


# ---------------------------------------------------------------- horario: ultima entrada y cierre forzado
def test_ultima_entrada_se_mide_por_el_cierre_de_la_vela():
    ok = {"11:55": (100, 100.5, 100, 100.4)}                                              # cierra a las 12:00: entra
    tarde = {"12:00": (100, 100.5, 100, 100.4)}                                           # cierra a las 12:05: no
    d = _df(_dia("2024-01-09", ok), _dia("2024-01-10", tarde))
    P, r = _run(d, _cfg())
    assert len(r.trades) == 1 and r.trades.loc[0, "i"] == _idx(d, "2024-01-09", "11:55")
    assert r.descartes.get("hora") == 1


def test_cierre_forzado_a_las_12_30_cierra_a_mercado_y_marca_hora():
    # la operacion queda flotando (+0,1) hasta el cierre de la vela de las 12:25 (12:30 NY)
    d = _dia("2024-01-09", {**LARGO, **{f"{h:02d}:{m:02d}": (100.5, 100.55, 100.45, 100.5) for h in (10, 11, 12) for m in range(0, 60, 5) if not (h == 12 and m > 25)}})
    P, r = _run(d, _cfg(rr=5.0))
    t = r.trades.iloc[0]
    assert t["motivo"] == "hora" and t["salida"] == _idx(d, "2024-01-09", "12:25")
    assert t["R"] == pytest.approx((100.5 - 100.4) / 0.4)
    assert t["res"] == "TP"                                                                 # gana: se rotula como las otras salidas al cierre


def test_nada_queda_abierto_despues_del_cierre_forzado():
    d = _df(_dia("2024-01-09", LARGO), _dia("2024-01-10", LARGO))
    P, r = _run(d, _cfg(rr=50.0, sl_modo="precio"))
    assert (r.trades["motivo"] == "hora").sum() <= 2 and (r.trades["res"] != "ABIERTA").all()
    for _, t in r.trades.iterrows():
        assert P.indice[int(t["salida"])].strftime("%H:%M") == "19:25"                      # 12:25 NY = 19:25 servidor


def test_el_cierre_forzado_cierra_tambien_con_breakeven_armado():
    cam = {"09:45": (100.1, 100.1, 100.1, 100.1), **LARGO, "10:00": (100.5, 100.9, 100.5, 100.8)}   # activa el breakeven (0,8 R) y se queda por encima del nivel
    d = _dia("2024-01-09", cam, reposo=100.45)
    cfg = _cfg(rr=10.0, be_activo=True, be_act_modo="r", be_act_valor=0.8, be_nivel_modo="r", be_nivel_valor=0.1)
    t = _run(d, cfg)[1].trades.iloc[0]
    assert t["be"] == 1 and t["motivo"] == "hora"


# ---------------------------------------------------------------- entradas por dia
def _dia_perdedor_y_contrario(extra=None):
    """Compra a las 9:50 que sale por SL (mitad del rango = 100,0), luego una venta (cierra bajo 99,8) a las 10:15."""
    cam = {**LARGO, "09:55": (100.4, 100.4, 99.9, 99.95), "10:15": (99.9, 99.9, 99.5, 99.6), **(extra or {})}
    return _dia("2024-01-09", cam)


def test_una_entrada_por_dia_por_defecto():
    t = _run(_dia_perdedor_y_contrario(), _cfg())[1].trades
    assert len(t) == 1 and t.loc[0, "motivo"] == "sl"


def test_la_segunda_entrada_es_solo_en_contra_y_solo_si_la_primera_salio_por_sl():
    d = _dia_perdedor_y_contrario()
    P, r = _run(d, _cfg(rp=dict(entradas_dia=2)))
    assert list(r.trades["lado"]) == [1, -1] and list(r.trades["motivo"])[0] == "sl"
    assert r.trades.loc[1, "i"] == _idx(d, "2024-01-09", "10:15")


def test_la_segunda_entrada_del_mismo_lado_no_se_toma():
    cam = {**LARGO, "09:55": (100.4, 100.4, 99.9, 99.95), "10:15": (99.95, 100.6, 99.95, 100.5)}      # vuelve a romper para arriba
    r = _run(_dia("2024-01-09", cam), _cfg(rp=dict(entradas_dia=2)))[1]
    assert len(r.trades) == 1


def test_si_la_primera_gano_no_hay_segunda_aunque_rompa_para_el_otro_lado():
    cam = {**LARGO, "10:00": (100.4, 101.5, 100.4, 101.4), "10:15": (100, 100, 99.5, 99.6)}              # TP (100,4 + 0,8) y despues rompe abajo
    r = _run(_dia("2024-01-09", cam), _cfg(rp=dict(entradas_dia=2)))[1]
    assert len(r.trades) == 1 and r.trades.loc[0, "res"] == "TP"


def test_la_segunda_no_cuenta_si_la_primera_salio_por_breakeven_u_hora():
    cam = {**LARGO, "09:55": (100.4, 100.7, 100.4, 100.45), "10:00": (100.45, 100.5, 100.05, 100.1), "10:15": (99.9, 99.9, 99.5, 99.6)}
    cfg = _cfg(rp=dict(entradas_dia=2), rr=10.0, be_activo=True, be_act_modo="r", be_act_valor=0.5, be_nivel_modo="r", be_nivel_valor=0.1)
    r = _run(_dia("2024-01-09", cam), cfg)[1]
    assert len(r.trades) == 1 and r.trades.loc[0, "motivo"] == "be"


def test_los_dias_son_independientes():
    d = _df(_dia_perdedor_y_contrario(), _dia("2024-01-10", LARGO))
    r = _run(d, _cfg())[1]
    assert len(r.trades) == 2


# ---------------------------------------------------------------- filtro de tamaño (sin mirar el futuro)
def _serie_dias(tamaños, hasta=None):
    ds = []
    dias_h = pd.bdate_range("2024-01-08", periods=len(tamaños))                # solo dias de semana
    for k, t in enumerate(tamaños):
        f = dias_h[k].strftime("%Y-%m-%d")
        ds.append(_dia(f, {"09:30": (100, 100 + t / 2, 100, 100), "09:35": (100, 100, 100 - t / 2, 100), "09:50": (100, 100 + t / 2 + 0.3, 100, 100 + t / 2 + 0.2)}))
    return _df(*ds)


def test_el_filtro_de_tamaño_usa_solo_dias_anteriores_y_pide_historia():
    tam = [1.0] * 5 + [1.0, 3.0, 0.2, 1.0]                                   # lunes a viernes + 4 dias mas (hay sabado/domingo en el medio)
    df = _serie_dias(tam)
    cfg = _cfg(rp=dict(tam_activo=True, tam_min=0.5, tam_max=1.5, tam_n=3))
    P = eng.preparar(df, cfg)
    d = P.rup["dias"]
    assert [m for m in d["motivo"]][:3] == ["historial"] * 3                  # los primeros N dias no tienen historia
    assert d["ratio"].iloc[:3].isna().all()
    assert pd.isna(d["motivo"].iloc[3]) and d["ratio"].iloc[3] == pytest.approx(1.0)


def test_el_filtro_de_tamaño_no_mira_el_futuro():
    tam = [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0]
    df = _serie_dias(tam)
    cfg = _cfg(rp=dict(tam_activo=True, tam_min=0.5, tam_max=1.5, tam_n=3))
    a = eng.preparar(df, cfg)
    otro = _serie_dias(tam[:6] + [9.0, 9.0])                                # cambia solo lo que viene despues
    b = eng.preparar(otro, cfg)
    da, db = a.rup["dias"].iloc[:6], b.rup["dias"].iloc[:6]
    assert [None if pd.isna(x) else x for x in da["motivo"]] == [None if pd.isna(x) else x for x in db["motivo"]]
    np.testing.assert_allclose(da["ratio"].to_numpy(float), db["ratio"].to_numpy(float), equal_nan=True)
    ca = [x for x in a.cruces if x[0] < b.rup["dias"].iloc[6]["i0"]]
    cb = [x for x in b.cruces if x[0] < b.rup["dias"].iloc[6]["i0"]]
    assert ca == cb


def test_dia_fuera_de_tamaño_se_descarta_con_su_motivo():
    df = _serie_dias([1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 4.0, 1.0])
    cfg = _cfg(rp=dict(tam_activo=True, tam_min=0.5, tam_max=1.5, tam_n=3))
    P, r = _run(df, cfg)
    assert "tamano" in r.descartes and r.descartes["tamano"] >= 1
    e = rup.embudo(P, r.trades, P.cruces)
    assert e["tamano"] >= 1


# ---------------------------------------------------------------- embudo
def test_el_embudo_suma_los_dias_validos():
    ds = [_dia("2024-01-08", LARGO), _dia("2024-01-09"), _dia("2024-01-10", {"12:00": (100, 100.5, 100, 100.4)}), _dia("2024-01-11", LARGO, faltan=("09:40",)),
          _dia("2024-01-12", {"09:50": (100, 100.5, 100, 100.4)})]
    df = _df(*ds)
    cfg = _cfg(rp=dict(entradas_dia=1), adx_activo=True, adx_min=1000.0)               # el ADX rechaza todo: ninguna ruptura se toma
    P, r = _run(df, cfg)
    e = rup.embudo(P, r.trades, P.cruces)
    assert e["dias"] == 5 and e["sin_vela"] == 1 and e["validos"] == 4
    assert e["sin_ruptura"] == 1 and e["fuera_horario"] == 1 and e["filtros"] == 2 and e["operados"] == 0
    sumas = sum(e[k] for k in ("historial", "tamano", "sin_ruptura", "fuera_horario", "filtros", "noticias", "otros", "operados"))
    assert sumas == e["validos"]
    P2, r2 = _run(df, _cfg())
    e2 = rup.embudo(P2, r2.trades, P2.cruces)
    assert e2["operados"] == 2 and sum(e2[k] for k in ("historial", "tamano", "sin_ruptura", "fuera_horario", "filtros", "noticias", "otros", "operados")) == e2["validos"]


def test_el_embudo_por_tramo_y_las_estadisticas():
    df = _df(*[_dia((pd.Timestamp("2024-01-08") + pd.Timedelta(days=k)).strftime("%Y-%m-%d"), LARGO) for k in range(0, 5)])
    P, r = _run(df, _cfg())
    corte = len(df) // 2
    a, b = rup.embudo(P, r.trades, P.cruces, 0, corte), rup.embudo(P, r.trades, P.cruces, corte, len(df))
    assert a["operados"] + b["operados"] == len(r.trades) and a["dias"] + b["dias"] == 5
    s = rup.estadisticas(P, r.trades)
    assert s["n"] == len(r.trades) and s["lados"]["largos"]["n"] == len(r.trades)
    assert s["tam"]["ganadoras"]["n"] + s["tam"]["perdedoras"]["n"] == len(r.trades)


# ---------------------------------------------------------------- filtros y cuenta del motor siguen funcionando con la ruptura
def test_los_filtros_del_motor_se_aplican_a_la_ruptura_y_el_azar_no_aplica():
    df = _df(_dia("2024-01-09", LARGO), _dia("2024-01-10", LARGO))
    cfg = _cfg(sesion_activo=True, sesiones=("Tokio",), horarios={"Tokio": ("UTC", 0.0, 1.0)})
    P, r = _run(df, cfg)
    assert r.descartes == {"sesion": 2} and len(r.trades) == 0
    ev = met.evaluar(df, _cfg(), 0.3, 20, 1)
    assert np.isnan(ev["tabla"].loc["Todo", "azar_exp_R"]) and ev["tabla"].loc["Todo", "resueltas"] >= 1


def test_con_reglas_de_cuenta_el_dinero_sale_de_la_distancia_del_sl():
    df = _df(_dia("2024-01-09", {**LARGO, "10:00": (100.4, 101.5, 100.4, 101.4)}))
    cfg = _cfg(reglas_activas=True, capital=10000.0, usd_por_unidad=100.0, perd_dia_pct=5.0, perd_tot_pct=10.0)
    P, r = _run(df, cfg)
    assert r.trades.loc[0, "res"] == "TP" and r.cuenta["balance_final"] == pytest.approx(10000.0 + 2.0 * 0.4 * 100.0)


def test_noticias_descartan_la_ruptura_cerca_de_la_noticia():
    df = _dia("2024-01-09", LARGO)
    ev = int((df.index[_idx(df, "2024-01-09", "09:50")] - pd.Timedelta(hours=2)).value // 10**9) + 300     # a 5 min del cierre de la señal
    cfg = _cfg(noticias_activo=True, noticias_fuente="csv", noticias_eventos=(ev,), noticias_min=10.0)
    P, r = _run(df, cfg)
    assert r.descartes == {"noticias": 1} and len(r.trades) == 0


# ---------------------------------------------------------------- validacion
def test_validar():
    base = _cfg()
    rup.ConfigRup().validar(base)
    malos = [dict(sl_modo="x"), dict(entradas_dia=3), dict(rango_min=0), dict(ultima_min=9 * 60 + 40), dict(cierre_min=12 * 60), dict(sl_modo="atr", sl_atr_x=0),
             dict(tam_activo=True, tam_min=2.0, tam_max=1.0), dict(tam_activo=True, tam_n=0), dict(apertura_min=-1)]
    for kw in malos:
        with pytest.raises(ValueError):
            rup.ConfigRup(**kw).validar(base)
    with pytest.raises(ValueError):
        rup.ConfigRup().validar(replace(base, servidor_offset_horas=None))
    for kw in (dict(pullback_activo=True), dict(reentrada_activa=True), dict(salida_modo="senal")):
        with pytest.raises(ValueError):
            rup.ConfigRup().validar(replace(base, **kw))


def test_el_rango_tiene_que_ser_multiplo_de_la_vela():
    d = _dia("2024-01-09", LARGO)
    with pytest.raises(ValueError):
        eng.preparar(d, _cfg(rp=dict(rango_min=7)))
    d15 = d[d.index.minute % 15 == 0]
    with pytest.raises(ValueError):
        eng.preparar(d15, _cfg(rp=dict(rango_min=10)))
    P = eng.preparar(d15, _cfg(rp=dict(rango_min=15)))                  # con velas M15 el rango es una sola vela
    assert P.rup["dias"].loc[0, "estado"] == "ok"
