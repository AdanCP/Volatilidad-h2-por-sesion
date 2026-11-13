# -*- coding: utf-8 -*-
"""Retiros de la cuenta: resumen de los retiros que hizo la simulacion y barrido del objetivo por retiro.

La simulacion de la cuenta (engine.simular) retira TODA la ganancia del ciclo cuando llega al objetivo; aca solo se lee el
resultado (cuenta["retiros"]) y se repite la simulacion con distintos objetivos para ver cual retira mas."""
from dataclasses import replace

import numpy as np
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
    estirados = [bool(x.get("estirado")) for x in ret]
    q = cuenta.get("quemada_en") if cuenta.get("quemada") else None
    quemada_ts = idx[int(q)] if q is not None else None
    ultimo = fechas[-1] if fechas else ini
    out = {"n": len(ret), "total": float(sum(montos)), "fechas": fechas, "montos": montos, "tiempos_min": tiempos,
           "quemada": quemada_ts is not None, "quemada_ts": quemada_ts, "inicio": ini, "fin": fin,
           "ciclo_avance": float(cuenta.get("balance_final", capital)) - float(capital),
           "colchon": colchon, "sugeridos": sug, "margen_tras": margen_tras, "margen_sug": margen_sug,
           "sin_margen_ts": None, "sin_margen_n": 0,
           "estirados": estirados, "n_estirados": int(sum(estirados)),
           "umbrales": [float(x.get("umbral", m)) for x, m in zip(ret, montos)],
           "mejores_dias": [float(x.get("mejor_dia", 0.0)) for x in ret]}
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


# ---------------------------------------------------------------- sugerencia de lotaje y RR para la consistencia
FACTORES_LOTE = (0.1, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5, 0.6, 0.75, 1.0)      # fracciones del lotaje actual que se prueban
GRILLA_RR = (1.0, 1.5, 2.0, 3.0, 4.0, 5.0)
SIN_ESTIRAR_MIN = 0.9      # la sugerencia pide que al menos el 90 % de los retiros se hagan justo en el minimo


def mejor_dia_r(tr, P) -> float:
    """Mejor dia del historial medido en R (suma de los R de las operaciones cerradas ese dia; dia = el de la vela de salida)."""
    if tr is None or not len(tr):
        return 0.0
    t = tr[tr["res"] != "ABIERTA"]
    if not len(t):
        return 0.0
    dias = np.asarray(P.dia)[t["salida"].to_numpy(dtype=int)]
    return float(max(pd.Series(t["R"].to_numpy(dtype=float)).groupby(dias).sum().max(), 0.0))


def _escalar(cfg, k: float, lotes: float, rr: float):
    """Misma estrategia con otro lotaje: solo escalan los dolares (el SL en precio queda igual)."""
    kw = dict(usd_por_unidad=cfg.usd_por_unidad * k, comision_op_usd=cfg.comision_op_usd * k, lotes=lotes, rr=rr)
    if cfg.be_act_modo == "usd":
        kw["be_act_valor"] = cfg.be_act_valor * k
    if cfg.be_nivel_modo == "usd":
        kw["be_nivel_valor"] = cfg.be_nivel_valor * k
    return replace(cfg, **kw)


def sugerir(P, cfg, tr, con_rr: bool = False) -> dict:
    """Con la consistencia y el objetivo de retiro de `cfg`, prueba varios lotajes (y, si se pide, varios RR) para ver con cuales
    se retira justo en el minimo. Devuelve la cota rapida (riesgo maximo para que NINGUN dia del historial pase el tope) y la tabla."""
    W = float(cfg.capital) * float(cfg.retiro_pct) / 100.0
    tope = W * float(cfg.consistencia_pct) / 100.0
    L = float(cfg.lotes)
    paso = float(cfg.lote_paso) if cfg.lote_paso > 0 else 0.01
    vmin = max(float(cfg.lote_min), paso)
    riesgo_base = float(tr.loc[tr["res"] != "ABIERTA", "dist"].median() * cfg.usd_por_unidad) if len(tr) else 0.0
    mdr = mejor_dia_r(tr, P)
    out = {"W": W, "tope_dia": tope, "mejor_dia_r": mdr, "riesgo_base": riesgo_base, "riesgo_max": None, "lotes_max": None, "filas": [], "mejor": None}
    if mdr > 0 and riesgo_base > 0:
        out["riesgo_max"] = tope / mdr
        if L > 0:
            out["lotes_max"] = float(np.floor(L * out["riesgo_max"] / riesgo_base / paso + 1e-9) * paso)
    if not (L > 0 and riesgo_base > 0):
        return out
    cand = {round(np.floor(L * f / paso + 0.5) * paso, 8) for f in FACTORES_LOTE}
    if out["lotes_max"]:
        cand.add(round(out["lotes_max"], 8))
    cand = sorted(x for x in cand if vmin - 1e-9 <= x <= L + 1e-9)
    rrs = list(GRILLA_RR) if con_rr else [float(cfg.rr)]
    if con_rr and float(cfg.rr) not in rrs:
        rrs = sorted(rrs + [float(cfg.rr)])
    for rr in rrs:
        for lots in cand:
            k = lots / L
            try:
                c2 = _escalar(cfg, k, lots, rr)
                c2.validar()
                cu = eng.ejecutar(P, c2).cuenta
            except ValueError:
                continue                                  # combinacion invalida (p. ej. un parcial por encima del TP nuevo)
            rs = resumen(cu, P.indice, cfg.capital)
            n = rs["n"]
            out["filas"].append({"rr": float(rr), "lotes": float(lots), "riesgo": riesgo_base * k, "tp_usd": riesgo_base * k * rr,
                                 "n": n, "sin_estirar": n - rs["n_estirados"], "total": rs["total"], "quemada": rs["quemada"],
                                 "medio_min": rs.get("medio")})
    ok = [i for i, f in enumerate(out["filas"]) if not f["quemada"] and f["n"] > 0 and f["sin_estirar"] / f["n"] >= SIN_ESTIRAR_MIN]
    if ok:
        # el sugerido es el que retira el minimo en MENOS tiempo (menor tiempo medio entre retiros); a igual tiempo, el que mas retira
        out["mejor"] = min(ok, key=lambda i: (out["filas"][i]["medio_min"] if out["filas"][i]["medio_min"] is not None else float("inf"),
                                              -round(out["filas"][i]["total"], 6)))
        out["cumple"] = True
    elif out["filas"]:
        out["mejor"] = max(range(len(out["filas"])), key=lambda i: (not out["filas"][i]["quemada"],
                           (out["filas"][i]["sin_estirar"] / out["filas"][i]["n"]) if out["filas"][i]["n"] else 0.0, out["filas"][i]["total"]))
        out["cumple"] = False
    return out
