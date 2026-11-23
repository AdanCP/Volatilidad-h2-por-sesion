"""Cableado de la página «Backtester Ruptura» (comprobaciones de código: no se puede correr Streamlit en las pruebas)."""
import os

AQUI = os.path.dirname(os.path.abspath(__file__))


def _leer(n):
    return open(os.path.join(AQUI, n), encoding="utf-8").read()


def test_la_pagina_de_ruptura_ejecuta_la_pantalla_comun_con_su_tipo():
    s = _leer("app_backtest_ruptura.py")
    assert '"TIPO_MEDIA": "ruptura"' in s and "app_backtest.py" in s


def test_app_registra_la_pagina_y_la_portada_la_muestra_en_lugar_del_bot():
    assert 'st.Page("app_backtest_ruptura.py", title="Backtester Ruptura"' in _leer("app.py")
    p = _leer("pagina_portada.py")
    assert '("ruptura", "Backtester Ruptura"' in p and '("bot", "Generar bot (.mq5)"' not in p


def test_la_ruptura_no_preselecciona_simbolo_y_usa_media_ema_en_la_config():
    s = _leer("app_backtest.py")
    assert 'multiselect(familia, opciones, [])' in s and 'etiqueta == "oro"' not in s      # ninguna página preselecciona símbolo
    assert 'media_tipo=("ema" if ES_RUP else TIPO)' in s          # Config.validar solo acepta 'ema' o 'sma'
    assert "ruptura=(rup_mod.ConfigRup(" in s


def test_la_config_de_la_pantalla_valida_con_el_motor():
    import engine as eng
    import ruptura as rup
    cfg = eng.Config(media_tipo="ema", sl_modo="precio", sl_valor=1.0, salida_modo="rr", servidor_offset_horas=2.0, servidor_dst_eeuu=True,
                     ruptura=rup.ConfigRup())
    cfg.validar()
