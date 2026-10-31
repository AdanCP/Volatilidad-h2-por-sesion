"""Metricas, comparacion contra el azar, ablacion de filtros y resultados en dinero."""
from dataclasses import replace

import numpy as np
import pandas as pd

import engine as eng


class ContadorPruebas:
    """Cuenta las configuraciones evaluadas en la sesion (control anti-sobreajuste)."""
    def __init__(self):
        self.n = 0

    def sumar(self) -> int:
        self.n += 1
        return self.n


def resumen(tr: pd.DataFrame, rr: float) -> dict:
    res = tr[tr["res"].isin(["TP", "SL"])] if len(tr) else tr
    tp = int((res["res"] == "TP").sum()) if len(res) else 0
    sl = int((res["res"] == "SL").sum()) if len(res) else 0
    n = tp + sl
    eq = res["R"].cumsum().to_numpy() if n else np.array([0.0])
    racha = mejor = 0
    for x in (res["res"] if n else []):
        racha = racha + 1 if x == "SL" else 0
        mejor = max(mejor, racha)
    return {"resueltas": n, "TP": tp, "SL": sl,
            "abiertas": int((tr["res"] == "ABIERTA").sum()) if len(tr) else 0,
            "ambiguas": int(tr["amb"].sum()) if len(tr) else 0,
            "%TP": 100 * tp / n if n else np.nan, "%equilibrio": 100 / (1 + rr),
            "exp_R": float(res["R"].mean()) if n else np.nan,
            "R_total": float(res["R"].sum()) if n else 0.0,
            "maxDD_R": float((np.maximum.accumulate(np.r_[0.0, eq]) - np.r_[0.0, eq]).max()),
            "racha_SL": mejor}


def azar(P, cfg, lo, hi, n_sig, veces, rng) -> np.ndarray:
    """Expectativa en R de entradas aleatorias con las mismas reglas de SL, TP y spread."""
    n_sig = min(n_sig, hi - lo - 1)
    if n_sig < 1 or veces < 1:
        return np.array([])
    lados = {"ambas": [1, -1], "largos": [1], "cortos": [-1]}[cfg.direccion]
    out = []
    for _ in range(veces):
        idx = np.sort(rng.choice(np.arange(lo, hi), size=n_sig, replace=False))
        sig = list(zip(idx, rng.choice(lados, size=n_sig)))
        tr, _ = eng.simular(P, sig, cfg.rr, cfg.costo_extra)
        out.append(resumen(tr, cfg.rr)["exp_R"])
    return np.array([x for x in out if not np.isnan(x)])


def evaluar(df, cfg, oos_pct=0.3, azar_veces=200, semilla=42, contador=None) -> dict:
    """Corre una configuracion: tramos Todo / In-sample / Out-of-sample, azar y desglose por año."""
    prueba = contador.sumar() if contador else None
    P = eng.preparar(df, cfg)
    n = len(P.c)
    corte = int(n * (1 - oos_pct))
    rng = np.random.default_rng(semilla)
    filas, res_todo = [], None
    for nombre, lo, hi in [("Todo", 0, n), ("In-sample", 0, corte), ("Out-of-sample", corte, n)]:
        r = eng.ejecutar(P, cfg, lo, hi)
        if nombre == "Todo":
            res_todo = r
        s = resumen(r.trades, cfg.rr)
        base = azar(P, cfg, lo, hi, r.tomados, azar_veces, rng)
        s["azar_exp_R"] = float(base.mean()) if len(base) else np.nan
        s["mejor_que_%azar"] = (100 * float((base < s["exp_R"]).mean())
                                 if len(base) and not np.isnan(s["exp_R"]) else np.nan)
        s["cruces"], s["tomados"], s["ignoradas"] = r.cruces, r.tomados, r.ignoradas
        s["descartes"] = r.descartes
        filas.append({"tramo": nombre, **s})
    tabla = pd.DataFrame(filas).set_index("tramo")

    tr = res_todo.trades.copy()
    por_anio = pd.DataFrame()
    if len(tr):
        tr["fecha_entrada"] = P.indice[tr["i"].to_numpy()]
        tr["fecha_salida"] = P.indice[tr["salida"].to_numpy()]
        tr["anio"] = tr["fecha_entrada"].dt.year
        por_anio = pd.DataFrame([{"año": y, **{k: v for k, v in resumen(g, cfg.rr).items()
                                                if k in ("resueltas", "TP", "SL", "exp_R")}}
                                 for y, g in tr.groupby("anio")]).set_index("año")
    avisos = []
    for nombre, f in tabla.iterrows():
        if f["resueltas"] < 100:
            avisos.append(f"{nombre}: solo {int(f['resueltas'])} operaciones resueltas; muestra debil.")
    if cfg.spread == "vela" and P.spread_ceros_pct > 5:
        avisos.append(f"{P.spread_ceros_pct:.1f}% de las velas tiene spread 0 (historial incompleto): "
                      "el costo esta subestimado en ese tramo. Probar spread='mediana'.")
    if prueba and prueba >= 20:
        avisos.append(f"Prueba n.º {prueba}: con tantas pruebas, un resultado bueno puede ser azar.")
    return {"tabla": tabla, "trades": tr, "por_anio": por_anio, "avisos": avisos,
            "prueba": prueba, "P": P, "descartes": res_todo.descartes, "corte": corte}


FILTROS_ABLACION = {
    "SMA": dict(sma_activo=True),
    "ADX": dict(adx_activo=True),
    "ATR relativo": dict(atr_activo=True, atr_rel_n=100, atr_rel_min=0.8, atr_rel_max=2.0),
    "Sesion": dict(sesion_activo=True),
}


def ablacion(df, cfg_base, filtros=None, oos_pct=0.3, azar_veces=100, semilla=42, contador=None):
    """Cruce solo y luego cada filtro de a uno (mas todos juntos). Devuelve un DataFrame."""
    filtros = FILTROS_ABLACION if filtros is None else filtros
    base = replace(cfg_base, **eng.FILTROS_APAGADOS)
    configs = [("Cruce solo", base)]
    omitidos = []
    for nombre, ov in filtros.items():
        c = replace(base, **ov)
        if c.sesion_activo and c.servidor_offset_horas is None:
            omitidos.append(nombre)
            continue
        configs.append((f"+ {nombre}", c))
    if len(configs) > 2:
        todos = {}
        for _, c in configs[1:]:
            todos.update({k: v for k, v in vars(c).items() if k.endswith("activo") and v})
            for k in ("atr_rel_n", "atr_rel_min", "atr_rel_max"):
                if c.atr_activo:
                    todos[k] = getattr(c, k)
        configs.append(("Todos juntos", replace(base, **todos)))
    filas = []
    for nombre, c in configs:
        r = evaluar(df, c, oos_pct, azar_veces, semilla, contador)
        t = r["tabla"]
        filas.append({"configuracion": nombre, "resueltas": t.loc["Todo", "resueltas"],
                      "%TP": t.loc["Todo", "%TP"], "exp_R": t.loc["Todo", "exp_R"],
                      "exp_R_OOS": t.loc["Out-of-sample", "exp_R"],
                      "resueltas_OOS": t.loc["Out-of-sample", "resueltas"],
                      "mejor_que_%azar_OOS": t.loc["Out-of-sample", "mejor_que_%azar"],
                      "descartadas": sum(r["descartes"].values())})
    return pd.DataFrame(filas).set_index("configuracion"), omitidos


# ------------------------------------------------------------------ dinero
def validar_lotaje(lotes, vol_min, vol_max, vol_step) -> None:
    if lotes < vol_min or lotes > vol_max:
        raise ValueError(f"Lotaje fuera de rango: {vol_min} a {vol_max}.")
    pasos = (lotes - vol_min) / vol_step
    if abs(pasos - round(pasos)) > 1e-6:
        raise ValueError(f"El lotaje debe ser multiplo de {vol_step} (desde {vol_min}).")


def valor_por_unidad(tick_size, tick_value, lotes) -> float:
    """Dinero por cada 1.00 de movimiento de precio: (1 / tick_size) * tick_value * lotes."""
    return tick_value / tick_size * lotes


def resumen_dinero(tr: pd.DataFrame, tick_size, tick_value, lotes, comision_por_lote=0.0) -> dict:
    """Resultados en moneda de la cuenta. Teoricos: slippage y gaps pueden empeorarlos."""
    res = tr[tr["res"].isin(["TP", "SL"])]
    if not len(res):
        return {"operaciones": 0}
    vu = valor_por_unidad(tick_size, tick_value, lotes)
    riesgo = res["dist"].to_numpy() * vu                       # perdida de un SL
    pnl = res["R"].to_numpy() * riesgo - comision_por_lote * lotes
    eq = np.cumsum(pnl)
    pico = np.maximum.accumulate(np.r_[0.0, eq])
    return {"operaciones": len(res), "riesgo_medio_por_operacion": float(riesgo.mean()),
            "ganancia_media_TP": float(pnl[res["res"].to_numpy() == "TP"].mean()) if (res["res"] == "TP").any() else 0.0,
            "perdida_media_SL": float(pnl[res["res"].to_numpy() == "SL"].mean()) if (res["res"] == "SL").any() else 0.0,
            "neto": float(pnl.sum()), "comisiones": float(comision_por_lote * lotes * len(res)),
            "max_drawdown": float((pico - np.r_[0.0, eq]).max())}


# ------------------------------------------------------------ multi-simbolo
def tipo_activo(simbolo: str) -> str:
    s = simbolo.upper()
    if s.startswith(("BTC", "ETH", "LTC", "XRP")):
        return "cripto"
    if s.startswith(("XAU", "XAG", "XPT", "XPD", "GOLD", "SILVER")):
        return "metal"
    if s.startswith(("US30", "US100", "US500", "USTEC", "NAS", "SPX", "SP500", "GER", "DE40", "DAX",
                     "UK100", "FTSE", "JP225", "JPN", "NIKKEI", "DJ30", "WS30", "FRA", "EU50", "AUS200")):
        return "indice"
    return "forex" if len(s) >= 6 and s[:6].isalpha() else "otro"


def comparar_simbolos(datos: dict, cfg, oos_pct=0.3, azar_veces=100, semilla=42,
                      contador=None, recortar_comun=False):
    """Mismos parametros en todos los simbolos (sin optimizar por activo). Devuelve (tabla, notas)."""
    notas = []
    if recortar_comun and len(datos) > 1:
        ini = max(df.index[0] for df in datos.values())
        fin = min(df.index[-1] for df in datos.values())
        datos = {s: df.loc[ini:fin] for s, df in datos.items()}
        notas.append(f"Periodo comun recortado: {ini} -> {fin}.")
    filas = []
    for simbolo, df in datos.items():
        tipo = tipo_activo(simbolo)
        c = cfg
        if tipo == "cripto" and cfg.sesion_activo:
            c = replace(cfg, sesion_activo=False)
            notas.append(f"{simbolo}: opera 24/7, el filtro de sesion se desactivo para este simbolo.")
        if tipo == "indice" and cfg.sesion_activo:
            notas.append(f"{simbolo}: el filtro Tokio/Londres/NY no equivale al horario propio del indice.")
        if tipo == "indice":
            notas.append(f"{simbolo}: los indices tienen gaps de apertura y pausas que el backtest no modela.")
        r = evaluar(df, c, oos_pct, azar_veces, semilla, contador)
        t, P = r["tabla"], r["P"]
        filas.append({"simbolo": simbolo, "tipo": tipo, "velas": len(df), "desde": str(df.index[0].date()),
                      "hasta": str(df.index[-1].date()),
                      "spread_%SL": 100 * float(P.sp.mean() / P.dist.mean()) if P.dist.mean() > 0 else np.nan,
                      "spread_cero_%": P.spread_ceros_pct,
                      "resueltas": t.loc["Todo", "resueltas"], "%TP": t.loc["Todo", "%TP"],
                      "%equilibrio": t.loc["Todo", "%equilibrio"], "exp_R": t.loc["Todo", "exp_R"],
                      "exp_R_IS": t.loc["In-sample", "exp_R"], "exp_R_OOS": t.loc["Out-of-sample", "exp_R"],
                      "mejor_que_%azar_OOS": t.loc["Out-of-sample", "mejor_que_%azar"],
                      "descartadas": sum(r["descartes"].values())})
    tabla = pd.DataFrame(filas).set_index("simbolo")
    if len(tabla) > 1 and len(tabla[["desde", "hasta"]].drop_duplicates()) > 1 and not recortar_comun:
        notas.append("Los simbolos tienen historiales de distinto largo: no son comparables tal cual "
                     "(usar --recortar-comun).")
    return tabla, notas
