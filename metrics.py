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
    if n and "motivo" in res and (res["motivo"] == "senal").any():      # sin TP fijo: el equilibrio sale del pago medio observado
        g_, p_ = res.loc[res["res"] == "TP", "R"], res.loc[res["res"] == "SL", "R"]
        if len(g_) and len(p_) and g_.mean() > 0 and p_.mean() < 0:
            rr = float(g_.mean() / -p_.mean())
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
        tr, _ = eng.simular(P, sig, cfg.rr, cfg.costo_extra, eng.pb_de(cfg), cfg.salida_modo,
                              eng.cuenta_de(P, cfg))
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
        s["pb"] = r.pb
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
    avisos = list(P.tm_aviso)
    for nombre, f in tabla.iterrows():
        if f["resueltas"] < 100:
            avisos.append(f"{nombre}: solo {int(f['resueltas'])} operaciones resueltas; muestra debil.")
    if cfg.spread == "vela" and P.spread_ceros_pct > 5:
        avisos.append(f"{P.spread_ceros_pct:.1f}% de las velas tiene spread 0 (historial incompleto): "
                      "el costo esta subestimado en ese tramo. Probar spread='mediana'.")
    if prueba and prueba >= 20:
        avisos.append(f"Prueba n.º {prueba}: con tantas pruebas, un resultado bueno puede ser azar.")
    return {"tabla": tabla, "trades": tr, "por_anio": por_anio, "avisos": avisos,
            "prueba": prueba, "P": P, "descartes": res_todo.descartes, "corte": corte,
            "cuenta": res_todo.cuenta}


FILTROS_ABLACION = {
    "SMA": dict(sma_activo=True),
    "VWAP": dict(vwap_activo=True),
    "Volume Profile": dict(vp_activo=True),
    "ADX": dict(adx_activo=True),
    "Rango (ratio de eficiencia)": dict(rango_activo=True, rango_ventana=20, rango_min=0.30),
    "ATR relativo": dict(atr_activo=True, atr_rel_n=100, atr_rel_min=0.8, atr_rel_max=2.0),
    "Sesion": dict(sesion_activo=True),
}


def ablacion(df, cfg_base, filtros=None, oos_pct=0.3, azar_veces=100, semilla=42, contador=None):
    """Cruce solo y luego cada filtro de a uno (mas todos juntos). Devuelve un DataFrame."""
    filtros = FILTROS_ABLACION if filtros is None else filtros
    if filtros is FILTROS_ABLACION and cfg_base.pb_efectivo():     # el pullback elegido entra como un paso mas
        filtros = {**FILTROS_ABLACION, "Pullback": dict(pullback_activo=True)}
    if filtros is FILTROS_ABLACION:                                 # los de tendencia mayor entran con la temporalidad y SMA que elegiste
        extra = {f"Tendencia mayor {k[2]} ({getattr(cfg_base, k + '_tf')})": {k + "_activo": True} for k in ("tm1", "tm2") if getattr(cfg_base, k + "_activo")}
        filtros = {**filtros, **extra}
    base = replace(cfg_base, **eng.FILTROS_APAGADOS)
    configs = [("Cruce solo", base)]
    omitidos = []
    for nombre, ov in filtros.items():
        c = replace(base, **ov)
        if any(k.startswith("tm") and k.endswith("_activo") and getattr(c, k) for k in ov):
            try:
                eng.preparar(df.iloc[:2000], c)
            except ValueError:
                omitidos.append(nombre)
                continue
        if (c.sesion_activo and c.servidor_offset_horas is None) or (c.vp_activo and c.servidor_offset_horas is None) or (c.vwap_activo and not eng.es_intradia(df)):
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


def cfg_sesion_original(cfg, simbolo) -> bool:
    """True si el filtro de sesion estaba activo para ese simbolo en la configuracion recibida."""
    c = cfg[simbolo] if isinstance(cfg, dict) else cfg
    return bool(c.sesion_activo)


def comparar_simbolos(datos: dict, cfg, oos_pct=0.3, azar_veces=100, semilla=42,
                      contador=None, recortar_comun=False):
    """Mismos parametros en todos los simbolos (sin optimizar por activo). Devuelve (tabla, notas).
    `cfg` puede ser una Config (igual para todos) o un dict {simbolo: Config}, util cuando el SL
    se fija en dolares y la distancia de precio depende del valor por tick de cada simbolo."""
    notas = []
    if recortar_comun and len(datos) > 1:
        ini = max(df.index[0] for df in datos.values())
        fin = min(df.index[-1] for df in datos.values())
        datos = {s: df.loc[ini:fin] for s, df in datos.items()}
        notas.append(f"Período común recortado: {ini:%Y-%m-%d} → {fin:%Y-%m-%d}.")
    filas = []
    for simbolo, df in datos.items():
        tipo = tipo_activo(simbolo)
        c = cfg[simbolo] if isinstance(cfg, dict) else cfg
        if tipo == "cripto" and c.sesion_activo:
            c = replace(c, sesion_activo=False)
            notas.append(f"{simbolo}: opera 24/7, el filtro de sesion se desactivo para este simbolo.")
        if tipo == "indice" and c.sesion_activo:
            notas.append(f"{simbolo}: el filtro Tokio/Londres/NY no equivale al horario propio del indice.")
        if tipo == "indice":
            notas.append(f"{simbolo}: los indices tienen gaps de apertura y pausas que el backtest no modela.")
        sesion_no_aplica = bool((tipo == "indice" or tipo == "cripto") and cfg_sesion_original(cfg, simbolo))
        r = evaluar(df, c, oos_pct, azar_veces, semilla, contador)
        t, P = r["tabla"], r["P"]
        ok_atr = np.isfinite(P.atr) & (P.atr > 0) & np.isfinite(P.dist)
        meses = max((df.index[-1] - df.index[0]).days / 30.44, 0.1)
        filas.append({"simbolo": simbolo, "tipo": tipo, "velas": len(df), "desde": str(df.index[0].date()),
                      "hasta": str(df.index[-1].date()),
                      "sl_atr": float((P.dist[ok_atr] / P.atr[ok_atr]).mean()) if ok_atr.any() else np.nan,
                      "ops_mes": float(t.loc["Todo", "resueltas"]) / meses,
                      "maxDD_R": t.loc["Todo", "maxDD_R"], "resueltas_OOS": t.loc["Out-of-sample", "resueltas"],
                      "sesion_no_aplica": sesion_no_aplica,
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


def rachas(tr: pd.DataFrame, indice, top: int = 5) -> dict:
    """Las `top` rachas más largas de TP seguidos y de SL seguidos (solo operaciones resueltas, en orden).
    Cada racha: {"largo", "desde", "hasta", "R"} con fechas de entrada de la primera y salida de la última."""
    out = {"TP": [], "SL": []}
    res = tr[tr["res"].isin(["TP", "SL"])] if len(tr) else tr
    if not len(res):
        return out
    actual = None
    for _, f in res.iterrows():
        if actual and actual["res"] == f["res"]:
            actual["largo"] += 1
            actual["hasta"] = indice[int(f["salida"])]
            actual["R"] += float(f["R"])
        else:
            if actual:
                out[actual["res"]].append(actual)
            actual = {"res": f["res"], "largo": 1, "desde": indice[int(f["i"])],
                      "hasta": indice[int(f["salida"])], "R": float(f["R"])}
    out[actual["res"]].append(actual)
    for k in out:   # más largas primero; a igual largo, la más reciente
        out[k] = sorted(out[k], key=lambda x: (-x["largo"], -x["desde"].value))[:top]
    return out


def frecuencia(tr: pd.DataFrame, indice) -> dict:
    """Operaciones tomadas por día, semana y mes (promedios sobre el período con datos).
    Día = días con velas (fines de semana sin mercado no cuentan); semana y mes = tiempo calendario."""
    n = int(len(tr))
    if n == 0 or len(indice) < 2:
        return {"n": n, "por_dia": 0.0, "por_semana": 0.0, "por_mes": 0.0, "max_dia": 0, "dias_con_op": 0,
                "max_sin_op": 0, "sin_op_desde": None, "sin_op_hasta": None, "dias_mercado": 0,
                "max_mes": 0, "mes_max": None}
    dias_mercado = max(len(pd.DatetimeIndex(indice).normalize().unique()), 1)
    dias_cal = max((indice[-1] - indice[0]).days, 1)
    entradas = pd.DatetimeIndex([indice[int(i)] for i in tr["i"]]).normalize()
    por_dia = pd.Series(1, index=entradas).groupby(level=0).sum()
    # mayor lapso sin operar: entre el inicio del período, cada entrada y el final (días calendario sin ninguna entrada)
    marcas = [pd.Timestamp(indice[0]).normalize()] + sorted(set(entradas)) + [pd.Timestamp(indice[-1]).normalize()]
    mejor, ini, fin = 0, None, None
    for a, b in zip(marcas[:-1], marcas[1:]):
        libres = (b - a).days - 1 if a != marcas[0] and b != marcas[-1] else (b - a).days
        if libres > mejor:
            mejor, ini, fin = libres, a, b
    por_mes = pd.Series(1, index=entradas.to_period("M")).groupby(level=0).sum()
    mes_max = por_mes.idxmax()
    return {"n": n, "por_dia": n / dias_mercado, "por_semana": n / (dias_cal / 7),
            "por_mes": n / (dias_cal / 30.44), "max_dia": int(por_dia.max()), "dias_con_op": int(len(por_dia)),
            "dias_mercado": dias_mercado, "max_sin_op": int(mejor), "sin_op_desde": ini, "sin_op_hasta": fin,
            "max_mes": int(por_mes.max()), "mes_max": (int(mes_max.year), int(mes_max.month))}


def fmt_duracion(minutos: float) -> str:
    """Duracion legible: minutos, horas o dias segun el tamano."""
    if minutos != minutos:
        return "–"
    if minutos < 90:
        return f"{minutos:.0f} min"
    if minutos < 60 * 48:
        h = minutos / 60
        return f"{h:.1f} h".replace(".", ",")
    return f"{minutos / 1440:.1f} d".replace(".", ",")


def duraciones(tr: pd.DataFrame, indice) -> dict:
    """Tasa de acierto y duracion de las operaciones resueltas (TP y SL), en el periodo analizado.
    La duracion se cuenta en velas desde la entrada hasta la vela de salida (la propia vela de salida cuenta
    entera) y se pasa a tiempo con el paso de la temporalidad: no incluye los fines de semana sin mercado."""
    res = tr[tr["res"].isin(["TP", "SL"])]
    n_tp, n_sl = int((res["res"] == "TP").sum()), int((res["res"] == "SL").sum())
    out = {"n": n_tp + n_sl, "n_tp": n_tp, "n_sl": n_sl, "win_rate": (100.0 * n_tp / (n_tp + n_sl)) if n_tp + n_sl else float("nan")}
    idx = pd.DatetimeIndex(indice)
    paso_min = float(idx.to_series().diff().dt.total_seconds().median() / 60.0) if len(idx) > 1 else float("nan")
    velas = (res["salida"].to_numpy() - res["i"].to_numpy()).clip(min=1) if len(res) else res["i"].to_numpy()
    for nombre, mascara in (("todas", slice(None)), ("tp", (res["res"] == "TP").to_numpy()), ("sl", (res["res"] == "SL").to_numpy())):
        v = velas[mascara] if len(res) else velas
        out[f"velas_{nombre}"] = float(v.mean()) if len(v) else float("nan")
        out[f"mediana_{nombre}"] = float(pd.Series(v).median()) if len(v) else float("nan")
        out[f"min_{nombre}"] = out[f"velas_{nombre}"] * paso_min
        out[f"min_mediana_{nombre}"] = out[f"mediana_{nombre}"] * paso_min
    out["paso_min"] = paso_min
    return out


def ciclos_objetivo(tr: pd.DataFrame, indice, tick_size, tick_value, lotes, comision_por_lote, capital,
                    objetivo_pct: float = 5.0) -> dict:
    """Cuanto tarda la estrategia en ganar el objetivo (% del balance inicial) y, si se retirara cada vez, en volver a ganarlo.

    El primer ciclo arranca al inicio del periodo con el balance inicial. Cuando la ganancia acumulada de las
    operaciones cerradas del ciclo llega al objetivo, se supone que se retira todo lo ganado (el balance vuelve al
    inicial) y arranca otro ciclo en ese momento. Las caidas cuentan: si el ciclo baja de cero hay que recuperarlas.
    El tiempo es calendario (incluye fines de semana) y llega hasta la vela de salida de la operacion que cruzo el
    objetivo. El ultimo tramo, si no llego al objetivo, se devuelve como 'en_curso'.
    Devuelve {"objetivo_usd", "objetivo_pct", "ciclos": [{"n","desde","hasta","min","ops","ganado"}], "en_curso": {...} o None}."""
    objetivo = float(capital) * float(objetivo_pct) / 100.0
    out = {"objetivo_usd": objetivo, "objetivo_pct": float(objetivo_pct), "ciclos": [], "en_curso": None}
    res = tr[tr["res"].isin(["TP", "SL"])] if len(tr) else tr
    if objetivo <= 0 or len(indice) < 2:
        return out
    inicio, fin = pd.Timestamp(indice[0]), pd.Timestamp(indice[-1])
    vu = valor_por_unidad(tick_size, tick_value, lotes)
    pnl = res["R"].to_numpy() * res["dist"].to_numpy() * vu - comision_por_lote * lotes if len(res) else np.array([])
    salidas = [pd.Timestamp(indice[int(s)]) for s in res["salida"]] if len(res) else []
    ini, acum, ops = inicio, 0.0, 0
    for p, t in zip(pnl, salidas):
        acum += float(p)
        ops += 1
        if acum >= objetivo - 1e-9:
            out["ciclos"].append({"n": len(out["ciclos"]) + 1, "desde": ini, "hasta": t,
                                  "min": (t - ini).total_seconds() / 60.0, "ops": ops, "ganado": acum})
            ini, acum, ops = t, 0.0, 0
    out["en_curso"] = {"desde": ini, "hasta": fin, "min": max((fin - ini).total_seconds() / 60.0, 0.0), "ops": ops,
                       "avance": acum, "avance_pct": 100.0 * acum / float(capital), "falta_usd": objetivo - acum}
    mins = [c["min"] for c in out["ciclos"]]
    out["resumen"] = {"n": len(mins), "primero": mins[0] if mins else float("nan"),
                      "medio": float(np.mean(mins)) if mins else float("nan"),
                      "mediana": float(np.median(mins)) if mins else float("nan"),
                      "minimo": float(min(mins)) if mins else float("nan"),
                      "maximo": float(max(mins)) if mins else float("nan"),
                      "retirado": float(sum(c["ganado"] for c in out["ciclos"]))}
    return out


def extremos_diarios(tr: pd.DataFrame, indice, tick_size, tick_value, lotes, comision_por_lote=0.0) -> dict:
    """Peor y mejor día en dinero y en R. Cada operación cuenta en el día en que se cerró (salida).
    Es sobre operaciones cerradas: no ve el flotante intradía."""
    res = tr[tr["res"].isin(["TP", "SL"])]
    if not len(res):
        return {}
    vu = valor_por_unidad(tick_size, tick_value, lotes)
    pnl = res["R"].to_numpy() * res["dist"].to_numpy() * vu - comision_por_lote * lotes
    dias = pd.DatetimeIndex([indice[int(j)] for j in res["salida"]]).normalize()
    usd = pd.Series(pnl, index=dias).groupby(level=0).sum()
    r_ = pd.Series(res["R"].to_numpy(), index=dias).groupby(level=0).sum()
    n_ = pd.Series(1, index=dias).groupby(level=0).sum()
    peor, mejor = usd.idxmin(), usd.idxmax()
    return {"peor_dia": peor, "peor_usd": float(usd[peor]), "peor_R": float(r_[peor]), "peor_ops": int(n_[peor]),
            "mejor_dia": mejor, "mejor_usd": float(usd[mejor]), "mejor_R": float(r_[mejor]), "mejor_ops": int(n_[mejor])}
