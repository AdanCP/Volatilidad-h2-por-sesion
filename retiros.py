# -*- coding: utf-8 -*-
"""Retiros de la cuenta: resumen de los retiros que hizo la simulacion y barrido del objetivo por retiro.

La simulacion de la cuenta (engine.simular) retira TODA la ganancia del ciclo cuando llega al objetivo; aca solo se lee el
resultado (cuenta["retiros"]) y se repite la simulacion con distintos objetivos para ver cual retira mas."""
from dataclasses import replace

import pandas as pd

import engine as eng

GRILLA = (1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0, 15.0, 20.0)      # objetivo por retiro, % del capital inicial


def resumen(cuenta: dict, indice, capital: float) -> dict:
    """Retiros hechos, tiempo entre ellos y, si la cuenta se quemo, cuanto duro."""
    idx = pd.DatetimeIndex(indice)
    ini, fin = idx[0], idx[-1]
    ret = cuenta.get("retiros", []) or []
    fechas = [idx[int(x["j"])] for x in ret]
    montos = [float(x["monto"]) for x in ret]
    tiempos, prev = [], ini
    for f in fechas:
        tiempos.append((f - prev).total_seconds() / 60.0)
        prev = f
    q = cuenta.get("quemada_en") if cuenta.get("quemada") else None
    quemada_ts = idx[int(q)] if q is not None else None
    ultimo = fechas[-1] if fechas else ini
    out = {"n": len(ret), "total": float(sum(montos)), "fechas": fechas, "montos": montos, "tiempos_min": tiempos,
           "quemada": quemada_ts is not None, "quemada_ts": quemada_ts, "inicio": ini, "fin": fin,
           "ciclo_avance": float(cuenta.get("balance_final", capital)) - float(capital)}
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
