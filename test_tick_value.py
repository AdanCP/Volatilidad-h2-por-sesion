"""Valor del tick mal informado por el servidor (Funding Pips: 0,01 en vez de 1 en el oro): app y bot usan el tamano del contrato."""
import os
import subprocess
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import data
from test_generar_bot import HAY_GPP, _cfg, _compilar, _gen

ORO = dict(tick_size=0.01, contrato=100.0, modo_calculo=2, moneda_beneficio="USD", moneda_cuenta="USD")


def test_app_corrige_el_tick_value_del_oro_mal_informado():
    sp = data.corregir_tick_value(dict(ORO, tick_value=0.01))
    assert sp["tick_value_corregido"] and abs(sp["tick_value"] - 1.0) < 1e-12 and sp["tick_value_informado"] == 0.01


def test_app_no_toca_un_tick_value_correcto():
    sp = data.corregir_tick_value(dict(ORO, tick_value=1.0))
    assert sp["tick_value"] == 1.0 and not sp.get("tick_value_corregido")


def test_app_no_corrige_si_el_beneficio_no_esta_en_la_moneda_de_la_cuenta():
    sp = data.corregir_tick_value(dict(ORO, tick_value=0.0065, moneda_beneficio="JPY"))
    assert sp["tick_value"] == 0.0065 and not sp.get("tick_value_corregido")


@pytest.mark.skipif(not HAY_GPP, reason="sin g++")
@pytest.mark.parametrize("ts,tv,cs,modo,mon,esperado", [
    (0.01, 1.0, 100.0, 2, "USD", 100.0),         # FTMO: tick value correcto
    (0.01, 0.01, 100.0, 2, "USD", 100.0),        # Funding Pips: tick value mal informado -> contrato
    (0.00001, 1.0, 100000.0, 0, "USD", 100000.0),  # EURUSD
    (0.001, 0.65, 100000.0, 0, "JPY", 650.0),    # beneficio en otra moneda: valor del tick / tamano del tick
    (0.01, 1.0, 0.0, 2, "USD", 100.0),           # sin contrato: valor del tick / tamano del tick
])
def test_bot_dinero_por_unidad(ts, tv, cs, modo, mon, esperado):
    t = _gen(_cfg(sl_modo="precio", sl_valor=2.0, rr=2.0), "XAUUSD", "M5", 0.17, sl_usd=175.0)
    main = f'''int main(){{stub_ts={ts};stub_tv={tv};stub_cs={cs};stub_modo={'SYMBOL_CALC_MODE_FOREX' if modo == 0 else 'SYMBOL_CALC_MODE_CFD'};
 stub_mon="{mon}";printf("%.10g %.10g %.10g\\n",UsdPerUnit(),SlDistance(0,1,0.0),RiskUsd(10.0));}}'''
    with tempfile.TemporaryDirectory() as d_:
        exe = _compilar(t, main, d_)
        u, sl, riesgo = (float(x) for x in subprocess.run([exe], capture_output=True, text=True).stdout.split())
    assert abs(u - esperado) < 1e-6 * esperado
    if esperado == 100.0:
        assert abs(sl - 175.0 / (100.0 * 0.17)) < 1e-6          # 17 US$ por dolar: SL de 10.29, no de 1029
        assert abs(riesgo - (10.0 * 100.0 * 0.17 + 0.0)) < 1e-6


@pytest.mark.skipif(not HAY_GPP, reason="sin g++")
def test_bot_valor_forzado_manda_sobre_todo():
    t = _gen(_cfg(sl_modo="precio", sl_valor=2.0, rr=2.0), "XAUUSD", "M5", 0.17, sl_usd=175.0, usd_por_unidad_forzado=50.0)
    assert "InpUsdUnitForce   = 50.0" in t
    main = '''int main(){stub_ts=0.01;stub_tv=0.01;stub_cs=100;stub_modo=SYMBOL_CALC_MODE_CFD;stub_mon="USD";printf("%.10g\\n",UsdPerUnit());}'''
    with tempfile.TemporaryDirectory() as d_:
        exe = _compilar(t, main, d_)
        assert abs(float(subprocess.run([exe], capture_output=True, text=True).stdout) - 50.0) < 1e-9


def test_bot_sin_forzar_lleva_cero():
    assert "InpUsdUnitForce   = 0.0" in _gen(_cfg(sl_modo="precio", sl_valor=2.0, rr=2.0), "XAUUSD", "M5", 0.17, sl_usd=175.0)
