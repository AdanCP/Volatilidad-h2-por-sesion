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
