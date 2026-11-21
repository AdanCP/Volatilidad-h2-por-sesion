"""Golden test de la SMA (cruce de dos SMA y precio contra una SMA): las operaciones de varias configuraciones sobre datos sinteticos tienen
que ser EXACTAMENTE las mismas que cuando se guardaron (antes de agregar la estrategia de ruptura al motor). Si falla, cambio la SMA."""
import json
import os

import data as dt
import engine as eng
from test_golden_ema import _hash, _NOTI

AQUI = os.path.dirname(os.path.abspath(__file__))
ARCHIVO = os.path.join(AQUI, "golden_sma.json")

CONFIGS = {
    "cruce": dict(media_tipo="sma", ema_corta=10, ema_larga=30),
    "cruce_filtros": dict(media_tipo="sma", ema_corta=10, ema_larga=30, adx_activo=True, atr_activo=True, atr_min=0.01, atr_max=9.0,
                          sesion_activo=True, servidor_offset_horas=2.0),
    "precio": dict(media_tipo="sma", modo_senal="precio", media_unica=40),
    "precio_rr": dict(media_tipo="sma", modo_senal="precio", media_unica=25, rr=1.5, sl_modo="pct", sl_valor=0.4),
    "precio_pullback": dict(media_tipo="sma", modo_senal="precio", media_unica=40, pullback_activo=True, pullback_pct=50.0, pullback_velas=8),
    "precio_gestion": dict(media_tipo="sma", modo_senal="precio", media_unica=40, be_activo=True, parcial_activo=True, tstop_activo=True,
                           tstop_velas=12, tstop_r=-0.2),
    "precio_cuenta_noticias": dict(media_tipo="sma", modo_senal="precio", media_unica=40, reglas_activas=True, capital=10000.0,
                                   usd_por_unidad=10.0, perd_dia_pct=3.0, perd_tot_pct=12.0, noticias_activo=True, noticias_fuente="csv",
                                   noticias_eventos=_NOTI, noticias_min=10.0, noticias_cerrar_r=-0.3, servidor_offset_horas=0.0,
                                   servidor_dst_eeuu=False),
    "cruce_reentrada_finde": dict(media_tipo="sma", ema_corta=10, ema_larga=30, reentrada_activa=True, finde_mantener=False,
                                  finde_no_abrir_desde=14.0, servidor_offset_horas=2.0),
}
DATOS = [dict(n=9000, tendencia=0.1, seed=5), dict(n=9000, tendencia=-0.05, seed=13)]


def calcular() -> dict:
    out = {}
    for k, d in enumerate(DATOS):
        df = dt.sintetico(**d)
        for nombre, kw in CONFIGS.items():
            cfg = eng.Config(**kw)
            r = eng.ejecutar(eng.preparar(df, cfg), cfg)
            out[f"{k}:{nombre}"] = _hash(r.trades) + ":" + json.dumps(sorted(r.descartes.items()))
    return out


def test_la_sma_da_lo_mismo_que_antes():
    esperado = json.load(open(ARCHIVO))
    got = calcular()
    assert got.keys() == esperado.keys()
    malos = [k for k in esperado if got[k] != esperado[k]]
    assert not malos, f"cambiaron los resultados de: {malos}"


if __name__ == "__main__":
    json.dump(calcular(), open(ARCHIVO, "w"), indent=1)
    print("golden guardado")
