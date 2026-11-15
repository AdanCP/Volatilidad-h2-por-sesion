"""Reentrada en el bot: la plantilla lleva los parametros, compila y el ADX / DI del bot coinciden con los del backtester."""
import os
import re
import subprocess
import sys
import tempfile

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import indicators as ind
from test_generar_bot import HAY_GPP, _cfg, _compilar, _gen


def _c(**k):
    base = dict(sl_modo="precio", sl_valor=2.0, rr=2.0, usd_por_unidad=10.0)
    base.update(k)
    return _cfg(**base)


def test_plantilla_sin_reentrada_la_deja_apagada():
    t = _gen(_c(), "XAUUSD", "M5", 0.1, sl_usd=20.0)
    assert re.search(r"InpReOn\s+= false;", t) and "Reentrada: con una tendencia" not in t.split("//---")[1]
    assert "@@" not in t and t.count("{") == t.count("}")


def test_plantilla_con_reentrada_lleva_los_valores_y_la_cabecera():
    c = _c(reentrada_activa=True, reentrada_nivel="corta", reentrada_modo="limite", reentrada_max=2, reentrada_velas=45,
           re_adx_min=27.0, re_di_favor=True, re_adx_creciente_n=4, re_adx_periodo=10)
    t = _gen(c, "XAUUSD", "M5", 0.1, sl_usd=20.0)
    for patron in (r"InpReOn\s+= true;", r"InpReLevel\s+= 1;", r"InpReMode\s+= 1;", r"InpReMax\s+= 2;", r"InpReBars\s+= 45;",
                   r"InpReAdxOn\s+= true;", r"InpReAdxMin\s+= 27\.0+;", r"InpReDi\s+= true;", r"InpReAdxRise\s+= 4;", r"InpReAdxPer\s+= 10;"):
        assert re.search(patron, t), patron
    assert "Reentrada: con una tendencia vigente" in t and "@@" not in t and t.count("{") == t.count("}")


def test_sin_adx_minimo_la_plantilla_lo_apaga():
    t = _gen(_c(reentrada_activa=True, re_adx_min=None), "XAUUSD", "M5", 0.1, sl_usd=20.0)
    assert re.search(r"InpReAdxOn\s+= false;", t)


def test_el_estado_de_la_reentrada_se_guarda_y_se_restaura():
    t = _gen(_c(reentrada_activa=True), "XAUUSD", "M5", 0.1, sl_usd=20.0)
    for clave in ("RESIDE", "RECROSS", "REN", "REELIG"):
        assert f'g_gv + "{clave}"' in t
    assert "ReAttempt(i)" in t and "ReTrack(i);" in t and "ReStart(i, cr);" in t


@pytest.mark.skipif(not HAY_GPP, reason="sin g++")
def test_adx_y_di_del_bot_coinciden_con_python():
    t = _gen(_c(reentrada_activa=True, re_adx_periodo=10), "XAUUSD", "M5", 0.1, sl_usd=20.0)
    main = '''int main(){int n;std::cin>>n;g_m=n;g_time.resize(n);g_h.resize(n);g_l.resize(n);g_c.resize(n);g_tv.resize(n);
 for(int i=0;i<n;i++){long long tt;std::cin>>tt>>g_h[i]>>g_l[i]>>g_c[i]>>g_tv[i];g_time[i]=tt;}
 CalcAdxDi(InpReAdxPer,g_rAdx,g_rPdi,g_rNdi);
 for(int i=0;i<n;i++)printf("%.12g %.12g %.12g\\n",g_rAdx[i],g_rPdi[i],g_rNdi[i]);}'''
    rng = np.random.default_rng(3)
    n = 800
    c = 2000 + np.cumsum(rng.normal(0, 2, n))
    h, l = c + rng.uniform(0, 1.5, n), c - rng.uniform(0, 1.5, n)
    entrada = f"{n}\n" + "\n".join(f"{i} {float(h[i])!r} {float(l[i])!r} {float(c[i])!r} 100" for i in range(n))
    with tempfile.TemporaryDirectory() as d_:
        exe = _compilar(t, main, d_)
        out = subprocess.run([exe], input=entrada, capture_output=True, text=True).stdout.strip().split("\n")
    a, p, m = ind.adx_wilder(h, l, c, 10)
    got = np.array([[float(x) for x in ln.split()] for ln in out])
    assert np.allclose(got[:, 0], a, atol=1e-6) and np.allclose(got[:, 1], p, atol=1e-6) and np.allclose(got[:, 2], m, atol=1e-6)


@pytest.mark.skipif(not HAY_GPP, reason="sin g++")
@pytest.mark.parametrize("amin,di,cre", [(25.0, True, 0), (None, True, 3), (30.0, False, 2), (None, False, 0)])
def test_la_confirmacion_de_adx_del_bot_coincide_con_la_del_motor(amin, di, cre):
    per = 5
    t = _gen(_c(reentrada_activa=True, re_adx_min=amin, re_di_favor=di, re_adx_creciente_n=cre, re_adx_periodo=per), "XAUUSD", "M5", 0.1, sl_usd=20.0)
    main = '''int main(){int n;std::cin>>n;g_m=n;g_rAdx.resize(n);g_rPdi.resize(n);g_rNdi.resize(n);
 for(int i=0;i<n;i++)std::cin>>g_rAdx[i]>>g_rPdi[i]>>g_rNdi[i];
 for(int i=0;i<n;i++)printf("%d %d\\n",ReAdxOk(i,1)?1:0,ReAdxOk(i,-1)?1:0);}'''
    rng = np.random.default_rng(11)
    n = 300
    a, p, m = rng.uniform(5, 60, n), rng.uniform(5, 40, n), rng.uniform(5, 40, n)
    entrada = f"{n}\n" + "\n".join(f"{float(a[i])!r} {float(p[i])!r} {float(m[i])!r}" for i in range(n))
    with tempfile.TemporaryDirectory() as d_:
        exe = _compilar(t, main, d_)
        out = subprocess.run([exe], input=entrada, capture_output=True, text=True).stdout.strip().split("\n")

    def esperado(i, lado):                          # la misma regla que buscar_re() del motor
        if i < 2 * per + cre + 1:
            return False
        if amin is not None and not a[i] >= amin:
            return False
        if di and not ((p[i] > m[i]) if lado == 1 else (m[i] > p[i])):
            return False
        return not (cre > 0 and not a[i] > a[i - cre])
    for i, ln in enumerate(out):
        c_, v_ = (int(x) for x in ln.split())
        assert (bool(c_), bool(v_)) == (esperado(i, 1), esperado(i, -1)), i


# ----------------------------------------------------- SL / TP / lotaje propios de la reentrada
def test_plantilla_con_gestion_propia_lleva_los_valores():
    c = _c(reentrada_activa=True, re_sl_modo="atr", re_sl_valor=1.5, re_rr=1.0, re_lote_max=0.6)
    t = _gen(c, "XAUUSD", "M5", 0.17, sl_usd=20.0)
    for patron in (r"InpReSlMode\s+= 1;", r"InpReSlVal\s+= 1\.5;", r"InpReRrOn\s+= true;", r"InpReRr\s+= 1\.0+;", r"InpReLotMax\s+= 0\.6;"):
        assert re.search(patron, t), patron
    assert "gestion propia" in t and "@@" not in t and t.count("{") == t.count("}")
    t0 = _gen(_c(reentrada_activa=True), "XAUUSD", "M5", 0.17, sl_usd=20.0)
    assert re.search(r"InpReSlMode\s+= 0;", t0) and re.search(r"InpReRrOn\s+= false;", t0) and "gestion propia" not in t0


def test_el_lote_y_el_rr_de_la_posicion_se_guardan_y_se_restauran():
    t = _gen(_c(reentrada_activa=True, re_sl_modo="precio", re_sl_valor=1.0), "XAUUSD", "M5", 0.17, sl_usd=20.0)
    for clave in ("CURLOTS", "CURRR", "BASED"):
        assert f'g_gv + "{clave}"' in t
    assert "d * u * g_curLots" in t                                   # el riesgo usa el lote de la posicion


@pytest.mark.skipif(not HAY_GPP, reason="sin g++")
@pytest.mark.parametrize("d,lotmax", [(5.0, 0.0), (1.0, 0.0), (1.7, 0.0), (20.0, 0.0), (1.0, 1.0), (400.0, 0.0)])
def test_el_lote_recalculado_del_bot_coincide_con_el_del_motor(d, lotmax):
    lotes, base_d = 0.17, 10.0
    t = _gen(_c(reentrada_activa=True, re_sl_modo="precio", re_sl_valor=d, re_lote_max=lotmax or None), "XAUUSD", "M5", lotes, sl_usd=20.0)
    main = f'''int main(){{g_baseD={base_d!r};printf("%.6f\\n",ReLots({d!r}));}}'''
    with tempfile.TemporaryDirectory() as d_:
        exe = _compilar(t, main, d_)
        got = float(subprocess.run([exe], capture_output=True, text=True).stdout.strip().split("\n")[-1])
    # la misma regla que _abrir_re() del motor
    esp = float(np.floor(lotes * (base_d / d) / 0.01 + 1e-9)) * 0.01
    if esp < 0.01 - 1e-9 or (lotmax and esp > lotmax + 1e-9) or esp > 100:
        esp = 0.0
    assert abs(got - esp) < 1e-6, (got, esp)
