from datetime import date

import numpy as np
import pandas as pd
import pytest

import config_io as cio
import engine as eng
import generar_bot as gb
import sessions as ses

INVIERNO, VERANO = date(2026, 11, 5), date(2026, 7, 15)


def test_ventanas_por_defecto_en_hora_argentina():
    r = lambda f: {n: tuple(round(x, 2) for x in ses.ventana_art(n, f)) for n in ses.SESIONES_LOCAL}
    assert r(INVIERNO) == {"Tokio": (21.0, 3.5), "Londres": (5.0, 13.5), "Nueva York": (11.5, 18.0)}
    assert r(VERANO) == {"Tokio": (21.0, 3.5), "Londres": (4.0, 12.5), "Nueva York": (10.5, 17.0)}   # Tokio no cambia


def test_conversion_ida_y_vuelta():
    for f in (INVIERNO, VERANO):
        for zona in ("Asia/Tokyo", "Europe/London", "America/New_York"):
            for h in (0.0, 5.0, 11.5, 21.25):
                assert ses.local_a_art(ses.art_a_local(h, zona, f), zona, f) == pytest.approx(h)


def test_rango_ny_en_hora_argentina_pasa_a_hora_local():
    h = ses.horarios_con_rangos({"Nueva York": (11.5, 13.5)}, INVIERNO)
    assert h["Nueva York"] == ("America/New_York", 9.5, 11.5)
    assert h["Tokio"] == ses.SESIONES_LOCAL["Tokio"] and h["Londres"] == ses.SESIONES_LOCAL["Londres"]
    with pytest.raises(ValueError):
        ses.horarios_con_rangos({"Tokio": (21.0, 21.0)}, INVIERNO)


def test_la_franja_sigue_al_horario_de_verano_en_el_historial():
    # rango de NY configurado en invierno: 9:30-11:30 de Nueva York. En julio (EDT) esa franja es 13:30-15:30 UTC.
    h = ses.horarios_con_rangos({"Nueva York": (11.5, 13.5)}, INVIERNO)
    utc = pd.DatetimeIndex(["2026-07-15 13:00", "2026-07-15 13:30", "2026-07-15 15:00", "2026-07-15 15:30",     # verano
                            "2026-12-10 14:00", "2026-12-10 14:30", "2026-12-10 16:00", "2026-12-10 16:30"])    # invierno
    ok = ses.mascara_sesiones(utc, ["Nueva York"], h)
    assert list(ok) == [False, True, True, False, False, True, True, False]


def test_rebasar_horas_al_cambiar_el_horario_de_verano():
    pares = [("ny_desde", "ny_hasta", "America/New_York"), ("tokio_desde", "tokio_hasta", "Asia/Tokyo")]
    guardado = {"ny_desde": "11:30", "ny_hasta": "13:30", "tokio_desde": "21:00", "tokio_hasta": "23:00",
                "otro": 5, "_ref_fecha": "2026-11-05"}
    en_verano = ses.rebasar_horas(guardado, pares, VERANO)
    assert en_verano["ny_desde"] == "10:30" and en_verano["ny_hasta"] == "12:30"       # misma franja de Nueva York
    assert en_verano["tokio_desde"] == "21:00" and en_verano["tokio_hasta"] == "23:00"  # Tokio no cambia
    assert en_verano["otro"] == 5 and "_ref_fecha" not in en_verano
    assert ses.rebasar_horas(guardado, pares, INVIERNO)["ny_desde"] == "11:30"          # mismo dia: sin cambios
    assert "ny_desde" not in ses.rebasar_horas({"otro": 1}, pares, VERANO)             # sin fecha de referencia: no toca nada


def test_time_input_se_guarda_y_se_carga():
    from datetime import time
    out, err = cio.leer(cio.a_bytes("ema", {"ny_desde": time(11, 30)}), "ema")
    assert err is None and out == {"ny_desde": "11:30"}
    a, k = cio.con_valor("time_input", (time(9, 0),), {}, "13:45")
    assert a[0] == time(13, 45)
    a, k = cio.con_valor("time_input", (time(9, 0),), {}, 99)
    assert a[0] == time(9, 0)


def _df(n=6000):
    rng = np.random.default_rng(5)
    c = 2000 + np.cumsum(rng.normal(0, 1.5, n))
    o = np.r_[c[0], c[:-1]]
    return pd.DataFrame({"Open": o, "High": np.maximum(o, c) + 0.5, "Low": np.minimum(o, c) - 0.5, "Close": c,
                         "Volume": 100, "Spread": 0.2}, index=pd.date_range("2024-01-02", periods=n, freq="15min"))


def test_el_motor_filtra_con_el_rango():
    df = _df()
    base = dict(sesion_activo=True, sesiones=("Nueva York",), servidor_offset_horas=2.0)
    completa = eng.preparar(df, eng.Config(**base))
    limitada = eng.preparar(df, eng.Config(**base, horarios=ses.horarios_con_rangos({"Nueva York": (11.5, 13.5)}, INVIERNO)))
    n_ok = lambda P: sum(1 for _, _, m in P.cruces if m is None)
    assert 0 < n_ok(limitada) < n_ok(completa)


def test_bot_lleva_las_ventanas_locales():
    cfg = eng.Config(sesion_activo=True, sesiones=("Nueva York", "Tokio"), servidor_offset_horas=2.0,
                     horarios=ses.horarios_con_rangos({"Nueva York": (11.5, 13.5)}, INVIERNO))
    src = gb.generar_mq5(cfg, "XAUUSD", "M15", 0.1, veredicto={"nivel": "ok", "titulo": "x"})
    assert "InpNYIni          = 9.5" in src and "InpNYFin          = 11.5" in src
    assert "InpTokioIni       = 9.0" in src and "InpTokioFin       = 15.5" in src and "InpLondresIni     = 8.0" in src and "InpLondresFin     = 16.5" in src
    assert "EnVentana(h, InpNYIni, InpNYFin)" in src
    assert "Nueva York 09:30-11:30" in src
    # sin horarios propios: las ventanas de siempre
    src2 = gb.generar_mq5(eng.Config(sesion_activo=True, servidor_offset_horas=2.0), "XAUUSD", "M15", 0.1,
                          veredicto={"nivel": "ok", "titulo": "x"})
    assert "InpNYIni          = 9.5" in src2 and "InpNYFin          = 16.0" in src2


# ---------------------------------------------------------------- pausa de mediodia
def test_pausa_m5_tokio_excluye_de_1130_a_1225():
    # Tokio 11:30-12:30 locales = 02:30-03:30 UTC; velas M5
    idx = pd.date_range("2024-01-09 02:00", "2024-01-09 04:00", freq="5min")      # invierno, sin DST en Tokio
    m = ses.mascara_sesiones(idx, ("Tokio",), None, sin_pausa=("Tokio",))
    ok = lambda hhmm: bool(m[list(idx.strftime("%H:%M")).index(hhmm)])
    assert ok("02:25") and not ok("02:30") and not ok("03:25") and ok("03:30")
    sin = ses.mascara_sesiones(idx, ("Tokio",))
    assert sin.all() and m.sum() == len(idx) - 12


def test_pausa_en_hora_argentina_y_verano():
    assert tuple(round(x, 2) for x in ses.pausa_art("Nueva York", INVIERNO)) == (14.0, 16.0)
    assert tuple(round(x, 2) for x in ses.pausa_art("Londres", INVIERNO)) == (9.0, 10.0)
    assert tuple(round(x, 2) for x in ses.pausa_art("Tokio", INVIERNO)) == (23.5, 0.5)
    for n, esp in (("Nueva York", (13.0, 15.0)), ("Londres", (8.0, 9.0)), ("Tokio", (23.5, 0.5))):
        assert tuple(round(x, 2) for x in ses.pausa_art(n, date(2024, 7, 15))) == esp


def test_pausa_solo_de_su_sesion_y_con_rango():
    # NY 12:00-14:00 locales (invierno = 17:00-19:00 UTC). Con Londres+NY, a esa hora Londres ya cerro: se excluye igual
    idx = pd.date_range("2024-01-09 16:00", "2024-01-09 20:00", freq="30min")
    m = ses.mascara_sesiones(idx, ("Nueva York",), None, sin_pausa=("Nueva York",))
    assert list(m) == [True, True, False, False, False, False, True, True, True][:len(idx)]
    # pausa fuera del rango limitado: no cambia nada
    h = ses.horarios_con_rangos({"Nueva York": (11.5, 13.5)}, INVIERNO)      # 9:30-11:30 locales
    assert (ses.mascara_sesiones(idx, ("Nueva York",), h, ("Nueva York",)) == ses.mascara_sesiones(idx, ("Nueva York",), h)).all()


def test_motor_y_bot_con_pausa():
    df = _df()
    base = dict(sesion_activo=True, sesiones=("Nueva York",), servidor_offset_horas=2.0)
    n_ok = lambda P: sum(1 for _, _, m in P.cruces if m is None)
    a = n_ok(eng.preparar(df, eng.Config(**base)))
    b = n_ok(eng.preparar(df, eng.Config(**base, sin_pausa=("Nueva York",))))
    assert 0 < b < a
    src = gb.generar_mq5(eng.Config(**base, sin_pausa=("Nueva York",)), "XAUUSD", "M15", 0.1, veredicto={"nivel": "ok", "titulo": "x"})
    assert "InpNYSinPausa     = true" in src and "InpNYPIni         = 12.0" in src and "InpNYPFin         = 14.0" in src
    assert "InpTokioSinPausa  = false" in src
    assert "&& !(InpNYSinPausa && EnVentana(h, InpNYPIni, InpNYPFin))" in src
    assert "sin pausa 12:00-14:00" in src


# ---------------------------------------------------------------- recorte de un horario por sesion
def test_recorte_ny_17_a_18_argentina_y_pausa_conviven():
    # invierno: 17:00-18:00 ART = 15:00-16:00 locales de Nueva York; pausa 12:00-14:00 locales. Velas M30 de NY (invierno = UTC-5)
    c = ses.cortes_con_rangos({"Nueva York": (17.0, 18.0)}, INVIERNO)
    assert tuple(round(x, 2) for x in c["Nueva York"]) == (15.0, 16.0)
    idx = pd.date_range("2026-11-05 14:30", "2026-11-05 21:30", freq="30min")      # 09:30 a 16:30 locales
    m = ses.mascara_sesiones(idx, ("Nueva York",), None, ("Nueva York",), c)
    horas_loc = [(i - pd.Timedelta(hours=5)).strftime("%H:%M") for i in idx[m]]
    assert horas_loc == ["09:30", "10:00", "10:30", "11:00", "11:30", "14:00", "14:30"]       # sin 12-14 (pausa) ni 15-16 (recorte)


def test_recorte_en_verano_se_corre_en_utc():
    c = ses.cortes_con_rangos({"Nueva York": (17.0, 18.0)}, VERANO)      # 17-18 ART = 16-17 locales (UTC-4)
    assert tuple(round(x, 2) for x in c["Nueva York"]) == (16.0, 17.0)


def test_recorte_que_cruza_la_medianoche_en_tokio():
    # 23:00-01:00 ART = 11:00-13:00 locales de Tokio (UTC+9)
    c = ses.cortes_con_rangos({"Tokio": (23.0, 1.0)}, INVIERNO)
    assert tuple(round(x, 2) for x in c["Tokio"]) == (11.0, 13.0)
    # recorte que cruza medianoche en hora local (22:00 a 02:00 de Londres, solo para la mascara)
    idx = pd.date_range("2026-11-05 00:00", "2026-11-05 23:30", freq="30min")
    m = ses.mascara_sesiones(idx, ("Londres",), {"Londres": ("Europe/London", 20.0, 8.0)}, (), {"Londres": (22.0, 2.0)})
    horas = [i.strftime("%H:%M") for i in idx[m]]
    assert "23:00" not in horas and "01:30" not in horas and "02:00" in horas and "21:30" in horas


def test_recorte_sin_duracion_es_error_y_fuera_de_sesion_avisa():
    with pytest.raises(ValueError):
        ses.cortes_con_rangos({"Nueva York": (17.0, 17.0)}, INVIERNO)
    with pytest.raises(ValueError):
        ses.cortes_con_rangos({"Marte": (1.0, 2.0)}, INVIERNO)
    assert ses.corte_toca_sesion("Nueva York", (15.0, 16.0))
    assert not ses.corte_toca_sesion("Nueva York", (20.0, 21.0))
    # con el rango limitado a 9:30-11:30 locales el recorte de 15-16 ya no toca nada
    h = ses.horarios_con_rangos({"Nueva York": (11.5, 13.5)}, INVIERNO)
    assert not ses.corte_toca_sesion("Nueva York", (15.0, 16.0), h)


def test_recorte_solo_afecta_a_su_sesion_y_no_toca_sin_recorte():
    idx = pd.date_range("2026-11-05 00:00", "2026-11-05 23:30", freq="30min")
    base = ses.mascara_sesiones(idx, ("Tokio", "Nueva York"))
    assert (ses.mascara_sesiones(idx, ("Tokio", "Nueva York"), None, (), None) == base).all()
    con = ses.mascara_sesiones(idx, ("Tokio", "Nueva York"), None, (), {"Nueva York": (15.0, 16.0)})
    assert con.sum() == base.sum() - 2 and (con <= base).all()


def test_motor_bot_veredicto_y_magic_con_recorte():
    import veredicto as ver
    df = _df()
    base = dict(sesion_activo=True, sesiones=("Nueva York",), servidor_offset_horas=2.0)
    cort = {"Nueva York": (15.0, 16.0)}
    n_ok = lambda P: sum(1 for _, _, m in P.cruces if m is None)
    a = n_ok(eng.preparar(df, eng.Config(**base)))
    b = n_ok(eng.preparar(df, eng.Config(**base, cortes=cort)))
    assert 0 < b < a
    cfg = eng.Config(**base, sin_pausa=("Nueva York",), cortes=cort)
    src = gb.generar_mq5(cfg, "XAUUSD", "M15", 0.1, veredicto={"nivel": "ok", "titulo": "x"})
    assert "InpNYCorte        = true" in src and "InpNYCIni         = 15.0" in src and "InpNYCFin         = 16.0" in src
    assert "InpTokioCorte     = false" in src and "@@" not in src
    assert "&& !(InpNYCorte && EnVentana(h, InpNYCIni, InpNYCFin))" in src
    assert "sin 15:00-16:00" in src
    # sin recorte, el magic y el texto del bot no cambian
    assert gb._magic(eng.Config(**base), "XAUUSD") == gb._magic(eng.Config(**base, cortes=None), "XAUUSD")
    assert gb._magic(eng.Config(**base), "XAUUSD") != gb._magic(eng.Config(**base, cortes=cort), "XAUUSD")


def test_recorte_se_guarda_y_se_carga_y_se_rebasa():
    pares = [(cio.slug("Nueva York: recorte desde (hora Argentina)"), cio.slug("Nueva York: recorte hasta (hora Argentina)"), "America/New_York")]
    d, h = pares[0][0], pares[0][1]
    v = ses.rebasar_horas({d: "17:00", h: "18:00", "_ref_fecha": INVIERNO.isoformat()}, pares, VERANO)
    assert (v[d], v[h]) == ("16:00", "17:00")        # la misma franja de Nueva York (15-16 locales -> 16-17 ART en verano)


# ---------------------------------------------------------------- aviso por cambio de horario (portada)
def test_aviso_cambio_de_horario_todos_los_anios():
    f = ses.aviso_cambio_horario
    # marzo completo: Londres / NY
    for d in (date(2027, 3, 1), date(2027, 3, 15), date(2027, 3, 31), date(2030, 3, 10)):
        t, det = f(d)
        assert t == "Verificar filtro de sesión por cambio de horario LONDRES / NY"
    assert "EE.UU. cambia el domingo 14/03" in f(date(2027, 3, 1))[1] and "Londres cambia el domingo 28/03" in f(date(2027, 3, 1))[1]
    assert "EE.UU. cambió el domingo 14/03" in f(date(2027, 3, 20))[1] and "Londres cambia el domingo 28/03" in f(date(2027, 3, 20))[1]
    assert "Londres cambia hoy" in f(date(2027, 3, 28))[1]
    # octubre: del 20 al 31 inclusive, solo Londres
    assert f(date(2026, 10, 19)) is None
    for d in (date(2026, 10, 20), date(2026, 10, 31)):
        assert f(d)[0] == "Verificar filtro de sesión por cambio de horario LONDRES"
    assert "Londres cambia el domingo 25/10" in f(date(2026, 10, 20))[1]
    assert "Londres cambió el domingo 25/10" in f(date(2026, 10, 30))[1]
    # noviembre: del 1 al 7, solo NY
    for d in (date(2026, 11, 1), date(2026, 11, 7), date(2027, 11, 1)):
        assert f(d)[0] == "Verificar filtro de sesión de NY"
    assert "EE.UU. cambia hoy" in f(date(2026, 11, 1))[1] and "EE.UU. cambia el domingo 07/11" in f(date(2027, 11, 1))[1]
    assert f(date(2026, 11, 8)) is None
    # el resto del año no hay aviso
    assert all(f(date(2026, m, 15)) is None for m in (1, 2, 4, 5, 6, 7, 8, 9, 12))
