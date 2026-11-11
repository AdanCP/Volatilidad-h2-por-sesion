"""Cierre parcial en el bot: la plantilla lleva los parametros y las cuentas del bot coinciden con las del backtester."""
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
    base = dict(sl_modo="precio", sl_valor=2.0, rr=4.0, usd_por_unidad=10.0)
    base.update(k)
    return _cfg(**base)


def test_plantilla_sin_parcial_lo_deja_apagado():
    t = _gen(_c(), "XAUUSD", "M5", 0.1, sl_usd=20.0)
    assert re.search(r"InpParOn\s+= false;", t) and "Cierre parcial:" not in t.split("//---")[1]
    assert "@@" not in t and "ManageParcial();" in t


def test_plantilla_con_parcial_lleva_los_valores_y_la_cabecera():
    c = _c(parcial_activo=True, parcial_nivel_modo="pct_tp", parcial_nivel_valor=40.0, parcial_pct=60.0,
           parcial_mover_sl=True, parcial_sl_nivel=0.1)
    t = _gen(c, "XAUUSD", "M5", 0.1, sl_usd=20.0)
    assert re.search(r"InpParOn\s+= true;", t) and re.search(r"InpParMode\s+= 1;", t) and re.search(r"InpParVal\s+= 40\.0+;", t)
    assert re.search(r"InpParPct\s+= 60\.0+;", t) and re.search(r"InpParMoveSl\s+= true;", t) and re.search(r"InpParSlLvl\s+= 0\.1;", t)
    assert "Cierre parcial: al llegar a 40.0 % del camino al TP" in t and "cierre parcial" in t
    assert "@@" not in t and t.count("{") == t.count("}")


def test_el_bot_rechaza_un_parcial_invalido():
    with pytest.raises(ValueError):
        _gen(_c(parcial_activo=True, parcial_nivel_valor=4.0), "XAUUSD", "M5", 0.1, sl_usd=20.0)      # el nivel no queda por debajo del TP


def test_el_estado_del_parcial_se_guarda_y_se_restaura():
    t = _gen(_c(parcial_activo=True), "XAUUSD", "M5", 0.1, sl_usd=20.0)
    for clave in ("PARID", "PARD", "PARDONE", "PARSLDONE", "PARPROFIT"):
        assert f'g_gv + "{clave}"' in t
    assert 'Avisar("PARCIAL: "' in t


@pytest.mark.skipif(not HAY_GPP, reason="sin g++")
@pytest.mark.parametrize("modo,val", [("r", 1.5), ("pct_tp", 40.0)])
def test_niveles_y_lotes_del_bot_coinciden_con_python(modo, val):
    c = _c(parcial_activo=True, parcial_nivel_modo=modo, parcial_nivel_valor=val, parcial_pct=50.0, parcial_sl_nivel=0.05)
    t = _gen(c, "XAUUSD", "M5", 0.17, sl_usd=20.0)
    main = '''int main(){int q;std::cin>>q;
 while(q--){double d,vol,pct,step,vmin;std::cin>>d>>vol>>pct>>step>>vmin;
  double lvl=0,sd=0;bool ok=ParLevels(d,lvl,sd);
  printf("%d %.14g %.14g %.14g\\n",ok?1:0,lvl,sd,ParVolume(vol,pct,step,vmin));}}'''
    rng = np.random.default_rng(7)
    casos = [(float(rng.uniform(0.5, 6.0)), float(v), float(p), 0.01, 0.01)
             for v in (0.01, 0.02, 0.05, 0.1, 0.17, 0.33, 1.0) for p in (1.0, 25.0, 33.0, 50.0, 70.0, 99.0)]
    entrada = f"{len(casos)}\n" + "\n".join(" ".join(repr(x) for x in cs) for cs in casos)
    with tempfile.TemporaryDirectory() as d_:
        exe = _compilar(t, main, d_)
        out = subprocess.run([exe], input=entrada, capture_output=True, text=True).stdout.strip().split("\n")
    assert len(out) == len(casos)
    for (d, vol, pct, step, vmin), ln in zip(casos, out):
        ok, lvl, sd, volc = ln.split()
        assert int(ok) == 1
        assert abs(float(lvl) - eng.be_distancia(modo, val, d, c.rr, 1.0)) < 1e-9 and abs(float(sd) - 0.05 * d) < 1e-9
        f = eng.fraccion_parcial(eng.Config(parcial_activo=True, parcial_pct=pct, lotes=vol, lote_paso=step, lote_min=vmin))
        assert abs(float(volc) - f * vol) < 1e-9          # 0 = no se parte, vol = se cierra todo, si no la parte redondeada
