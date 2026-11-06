# -*- coding: utf-8 -*-
"""Retiros de la cuenta: resumen de los retiros que hizo la simulacion y barrido del objetivo por retiro.

La simulacion de la cuenta (engine.simular) retira TODA la ganancia del ciclo cuando llega al objetivo; aca solo se lee el
resultado (cuenta["retiros"]) y se repite la simulacion con distintos objetivos para ver cual retira mas."""
from dataclasses import replace

import pandas as pd

import engine as eng

GRILLA = (1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0, 15.0, 20.0)      # objetivo por retiro, % del capital inicial


COLCHON_OPS = 3          # el margen que conviene dejar tras un retiro: lo que cuestan este numero de perdidas grandes seguidas


def resumen(cuenta: dict, indice, capital: float, riesgo_usd: float = None) -> dict:
    """Retiros hechos, tiempo entre ellos y, si la cuenta se quemo, cuanto duro. `riesgo_usd`: perdida de una operacion grande
    (p. ej. el percentil 90 del SL en US$); con eso se sugiere cuanto retirar para no quedar pegado al limite."""
    idx = pd.DatetimeIndex(indice)
    ini, fin = idx[0], idx[-1]
    ret = cuenta.get("retiros", []) or []
    fechas = [idx[int(x["j"])] for x in ret]
    montos = [float(x["monto"]) for x in ret]
    tiempos, prev = [], ini
    for f in fechas:
        tiempos.append((f - prev).total_seconds() / 60.0)
        prev = f
    colchon = COLCHON_OPS * float(riesgo_usd) if riesgo_usd else None
    sug, margen_tras, margen_sug = [], [], []
    for x, m in zip(ret, montos):
        piso = x.get("piso")
        if piso is None or colchon is None:                     # sin limite total (o sin dato de riesgo): no hay nada que cuidar
            sug.append(m); margen_tras.append(None); margen_sug.append(None)
            continue
        s_ = min(m, max(0.0, float(x["bal_antes"]) - float(piso) - colchon))
        sug.append(s_)
        margen_tras.append(float(capital) - float(piso))
        margen_sug.append(float(capital) + (m - s_) - float(piso))
    q = cuenta.get("quemada_en") if cuenta.get("quemada") else None
    quemada_ts = idx[int(q)] if q is not None else None
    ultimo = fechas[-1] if fechas else ini
    out = {"n": len(ret), "total": float(sum(montos)), "fechas": fechas, "montos": montos, "tiempos_min": tiempos,
           "quemada": quemada_ts is not None, "quemada_ts": quemada_ts, "inicio": ini, "fin": fin,
           "ciclo_avance": float(cuenta.get("balance_final", capital)) - float(capital),
           "colchon": colchon, "sugeridos": sug, "margen_tras": margen_tras, "margen_sug": margen_sug,
           "sin_margen_ts": None, "sin_margen_n": 0}
    pd_ = cuenta.get("prot_desde")
    if pd_ is not None and quemada_ts is None:                   # la cuenta no se quemo pero quedo sin margen para abrir operaciones
        out["sin_margen_ts"], out["sin_margen_n"] = idx[int(pd_)], int(cuenta.get("prot_n", 0))
    if tiempos:
        s = pd.Series(tiempos)
        out.update(medio=float(s.mean()), mediana=float(s.median()), minimo=float(s.min()), maximo=float(s.max()))
    if quemada_ts is not None:
        out["hasta_quemarse_min"] = (quemada_ts - ini).total_seconds() / 60.0
        out["desde_ultimo_min"] = (quemada_ts - ultimo).total_seconds() / 60.0
        out["dias_operados"] = int(idx[: int(q) + 1].normalize().nunique())
    return out


def barrido(P, cfg, grilla=GRILLA) -> dict:
    """Repite la simulacion completa con cada objetivo. El ideal es el que MAS retira en este historial (empate: el que no
    se quema, y despues el que retira mas veces)."""
    filas = []
    for x in grilla:
        c = replace(cfg, retiro_activo=True, retiro_pct=float(x))
        cu = eng.ejecutar(P, c).cuenta
        rs = resumen(cu, P.indice, cfg.capital)
        filas.append({"pct": float(x), "usd": float(cfg.capital) * float(x) / 100.0, "n": rs["n"], "total": rs["total"],
                      "quemada": rs["quemada"], "hasta_quemarse_min": rs.get("hasta_quemarse_min")})
    mejor = max(filas, key=lambda f: (round(f["total"], 6), not f["quemada"], f["n"]))
    return {"filas": filas, "ideal": mejor["pct"]}
