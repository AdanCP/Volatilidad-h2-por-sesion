"""Corte del dia de las reglas de cuenta: Europa Central (por defecto, como siempre) o medianoche del servidor."""
import re

import numpy as np
import pandas as pd
import pytest

import engine as eng
from test_generar_bot import _cfg, _gen


def _idx():
    return pd.date_range("2024-01-15 20:00", "2024-01-16 03:00", freq="30min")        # invierno: servidor GMT+2


def test_por_defecto_corta_en_europa_central_y_no_cambia():
    cfg = eng.Config(servidor_offset_horas=2.0, servidor_dst_eeuu=True)
    assert cfg.corte_dia == "europa"
    k = eng.claves_dia(_idx(), cfg)
    # servidor GMT+2 = 22:00 UTC -> Berlin GMT+1: la medianoche de Berlin es la 01:00 del servidor
    cambia = _idx()[np.flatnonzero(np.diff(k)) + 1]
    assert [str(x.time()) for x in cambia] == ["01:00:00"]


def test_corte_servidor_cambia_a_medianoche_de_la_plataforma():
    cfg = eng.Config(servidor_offset_horas=2.0, servidor_dst_eeuu=True, corte_dia="servidor")
    k = eng.claves_dia(_idx(), cfg)
    cambia = _idx()[np.flatnonzero(np.diff(k)) + 1]
    assert [str(x.time()) for x in cambia] == ["00:00:00"]


def test_corte_servidor_no_necesita_el_desfase():
    k = eng.claves_dia(_idx(), eng.Config(corte_dia="servidor"))
    assert len(set(k)) == 2


def test_el_perfil_de_volumen_sigue_cortando_en_europa_central():
    cfg = eng.Config(servidor_offset_horas=2.0, servidor_dst_eeuu=True, corte_dia="servidor")
    a = eng.claves_dia(_idx(), cfg, cuenta=False)
    b = eng.claves_dia(_idx(), eng.Config(servidor_offset_horas=2.0, servidor_dst_eeuu=True))
    assert (a == b).all()


def test_valor_invalido():
    with pytest.raises(ValueError):
        eng.Config(corte_dia="otro").validar()


def test_el_bot_lleva_el_corte():
    assert re.search(r"InpDayCut\s+= 0;", _gen(_cfg(), "XAUUSD", "M5", 0.1, sl_usd=20.0))
    t = _gen(_cfg(corte_dia="servidor"), "XAUUSD", "M5", 0.1, sl_usd=20.0)
    assert re.search(r"InpDayCut\s+= 1;", t) and "DayKeyNow()" in t and "@@" not in t
