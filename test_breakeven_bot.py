"""Breakeven en el bot: la plantilla lleva los parametros y las cuentas del bot coinciden con las del backtester."""
import os
import re
import subprocess
import sys
import tempfile

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import engine as eng
from test_generar_bot import HAY_GPP, _cfg, _compilar, _gen


def _c(**k):
    base = dict(sl_modo="precio", sl_valor=2.0, rr=2.0, usd_por_unidad=10.0)
    base.update(k)
    return _cfg(**base)


def test_plantilla_sin_breakeven_lo_deja_apagado():
    t = _gen(_c(), "XAUUSD", "M5", 0.1, sl_usd=20.0)
    assert re.search(r"InpBeOn\s+= false;", t) and re.search(r"InpBePauseLoss\s+= false;", t)
    assert "Breakeven:" not in t.split("//---")[1] if "//---" in t else True


def test_plantilla_con_breakeven_lleva_los_valores_y_la_cabecera():
    c = _c(be_activo=True, be_act_modo="pct_tp", be_act_valor=50.0, be_nivel_modo="usd", be_nivel_valor=15.0,
           pausa_activa=True, be_pausa_perdida=True)
    t = _gen(c, "XAUUSD", "M5", 0.1, sl_usd=20.0)
    assert re.search(r"InpBeOn\s+= true;", t) and re.search(r"InpBeActMode\s+= 2;", t) and re.search(r"InpBeActVal\s+= 50\.0+;", t)
    assert re.search(r"InpBeLvlMode\s+= 1;", t) and re.search(r"InpBeLvlVal\s+= 15\.0+;", t) and re.search(r"InpBePauseLoss\s+= true;", t)
    assert "// Breakeven: al llegar a 50,0 % del camino al TP" in t.replace(".", ",") or "Breakeven: al llegar a" in t
    assert "por TICK" in t and "ManageBreakeven();" in t
    assert "@@" not in t


def test_la_casilla_de_pausa_solo_vale_con_la_pausa_encendida():
    c = _c(be_activo=True, be_pausa_perdida=True, pausa_activa=False)
    assert re.search(r"InpBePauseLoss\s+= false;", _gen(c, "XAUUSD", "M5", 0.1, sl_usd=20.0))


def test_el_bot_rechaza_un_breakeven_invalido():
    with pytest.raises(ValueError):
        _gen(_c(be_activo=True, be_act_valor=1.0, be_nivel_valor=1.0), "XAUUSD", "M5", 0.1, sl_usd=20.0)


@pytest.mark.skipif(not HAY_GPP, reason="sin g++")
@pytest.mark.parametrize("am,nm", [("r", "r"), ("usd", "usd"), ("pct_tp", "r"), ("r", "usd"), ("pct_tp", "usd")])
def test_niveles_y_disparo_del_bot_coinciden_con_python(am, nm):
    lotes = 0.1
    c = _c(be_activo=True, be_act_modo=am, be_act_valor={"r": 1.0, "usd": 30.0, "pct_tp": 50.0}[am],
           be_nivel_modo=nm, be_nivel_valor={"r": 0.3, "usd": 4.0}[nm], rr=2.0)
    t = _gen(c, "XAUUSD", "M5", lotes, sl_usd=20.0)
    main = '''int main(){int q;std::cin>>q;
 while(q--){int side;double open,d,bid,ask;std::cin>>side>>open>>d>>bid>>ask;
  double act=0,sl=0;bool ok=BeLevels(side,open,d,act,sl);
  printf("%d %.14g %.14g %d\\n",ok?1:0,act,sl,BeTriggered(side,open,act,bid,ask)?1:0);}}'''
    rng = np.random.default_rng(5)
    casos = []
    for _ in range(40):
        side = int(rng.choice([1, -1]))
        d = float(rng.uniform(0.5, 6.0))
        open_ = float(rng.uniform(1900, 2100))
        act_est = d * 1.0
        bid = open_ + side * float(rng.uniform(-2, 2) * d)
        casos.append((side, open_, d, bid, bid + 0.3))
    entrada = f"{len(casos)}\n" + "\n".join(" ".join(repr(x) for x in cs) for cs in casos)
    with tempfile.TemporaryDirectory() as d_:
        exe = _compilar(t, main, d_)
        out = subprocess.run([exe], input=entrada, capture_output=True, text=True).stdout.strip().split("\n")
    vu = lotes * 1.0                                   # el stub devuelve tick_value = tick_size = 1
    for (side, open_, d, bid, ask), ln in zip(casos, out):
        ok, act, sl, trig = ln.split()
        a = eng.be_distancia(c.be_act_modo, c.be_act_valor, d, c.rr, vu)
        b = eng.be_distancia(c.be_nivel_modo, c.be_nivel_valor, d, c.rr, vu)
        valido = a > 0 and 0 <= b < a
        assert int(ok) == int(valido)
        if valido:
            assert abs(float(act) - a) < 1e-7 and abs(float(sl) - (open_ + side * b)) < 1e-9
            esperado = (bid >= open_ + a) if side == 1 else (ask <= open_ - a)
            assert int(trig) == int(esperado)
