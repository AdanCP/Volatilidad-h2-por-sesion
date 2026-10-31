"""Conclusión final: descripción del resultado, veredicto con criterios explícitos y proyección estadística.

Todo es transparente y reproducible (semilla fija). No usa Streamlit.

Método de la proyección (a 1, 3, 6 y 12 meses):
  * Cada operación resuelta gana (+R del TP) o pierde (R del SL). Con w ganadas y l perdidas, la probabilidad
    real de ganar una operación es incierta: se la modela con una Beta(w+1, l+1) (inferencia bayesiana con
    prior plano). Con pocas operaciones la Beta es ancha, y la proyección lo refleja.
  * En cada simulación se sortea esa probabilidad y luego las operaciones del horizonte (frecuencia = las
    operaciones por mes observadas en el historial). Se miden el resultado final y si el acumulado llegó a
    tocar el límite de pérdida máxima de la cuenta.
  * Se hace con todo el historial y, aparte, solo con el tramo out-of-sample (más conservador: no lo "vio" el
    ajuste). Supuestos: el futuro se parece al pasado, las operaciones son independientes y los costos
    reales son los modelados. Es una estimación, no una garantía.
"""
from typing import Optional

import numpy as np
import pandas as pd

HORIZONTES = (1, 3, 6, 12)
OK, WARN, BAD = "ok", "warn", "bad"
SIMBOLO = {OK: "✓", WARN: "!", BAD: "✕"}


# ------------------------------------------------------------------ estadística
def _resueltas(tr: pd.DataFrame) -> pd.DataFrame:
    return tr[tr["res"].isin(["TP", "SL"])] if len(tr) else tr


def parametros_binomiales(tr: pd.DataFrame, rr: float = 2.0) -> Optional[dict]:
    """w ganadas, l perdidas, R medio de una ganadora y de una perdedora, y el % de acierto de equilibrio."""
    res = _resueltas(tr)
    if not len(res):
        return None
    tp, sl = res[res["res"] == "TP"]["R"], res[res["res"] == "SL"]["R"]
    gana = float(tp.mean()) if len(tp) else float(rr)
    pierde = float(sl.mean()) if len(sl) else -1.0
    if gana <= 0 or pierde >= 0:                      # costos tan altos que una ganadora no gana: sin ventaja posible
        p_be = 1.0 if gana <= 0 else 0.0
    else:
        p_be = -pierde / (gana - pierde)
    return {"w": len(tp), "l": len(sl), "gana_R": gana, "pierde_R": pierde, "p_equilibrio": p_be}


def prob_ventaja(par: Optional[dict], sims: int = 40000, semilla: int = 7) -> float:
    """Probabilidad (posterior) de que la tasa de acierto real supere a la de equilibrio, es decir, de que la
    expectativa verdadera sea positiva."""
    if not par:
        return float("nan")
    p = np.random.default_rng(semilla).beta(par["w"] + 1, par["l"] + 1, sims)
    return float((p > par["p_equilibrio"]).mean())


def proyectar(par: Optional[dict], tasa_mes: float, usd_por_R: Optional[float] = None,
              limite_usd: Optional[float] = None, horizontes=HORIZONTES, semilla: int = 11) -> list:
    """Simulación Monte Carlo por horizonte. Devuelve una fila por horizonte."""
    filas = []
    if not par or tasa_mes <= 0:
        return filas
    rng = np.random.default_rng(semilla)
    for meses in horizontes:
        n = max(1, int(round(tasa_mes * meses)))
        sims = int(min(4000, max(300, 8_000_000 // n))) if n <= 20000 else 300
        p = rng.beta(par["w"] + 1, par["l"] + 1, sims)
        if n <= 20000:
            gana = rng.random((sims, n)) < p[:, None]
            camino = np.cumsum(np.where(gana, par["gana_R"], par["pierde_R"]), axis=1)
            final, minimo = camino[:, -1], camino.min(axis=1)
        else:                                          # muchísimas operaciones: solo el resultado final
            k = rng.binomial(n, p)
            final, minimo = k * par["gana_R"] + (n - k) * par["pierde_R"], None
        fila = {"meses": meses, "n": n, "p_ganar": float((final > 0).mean()),
                "R_mediana": float(np.median(final)), "R_p5": float(np.percentile(final, 5)),
                "R_p95": float(np.percentile(final, 95)), "p_limite": None}
        if usd_por_R and limite_usd and minimo is not None:
            fila["p_limite"] = float((minimo * usd_por_R <= -limite_usd).mean())
        filas.append(fila)
    return filas


# ------------------------------------------------------------------ descripción
def describir(cfg, simbolo: str, tf: str, ini, fin, meses: float, lotes: float, neto: Optional[float],
              n_res: int, tp: int, sl: int, exp_R: float, dd_usd: Optional[float],
              sl_usd: float = 0.0, tp_usd: float = 0.0) -> str:
    """Texto: 'En el período... usando el cruce EMA... habrías ganado/perdido...' (HTML simple)."""
    def n(x, d=2):
        s = f"{x:,.{d}f}".replace(",", "§").replace(".", ",").replace("§", ".")
        return s

    dir_txt = {"ambas": "largos y cortos", "largos": "solo largos", "cortos": "solo cortos"}[cfg.direccion]
    if cfg.sl_modo == "precio" and sl_usd > 0:
        gestion = f"SL de US${n(sl_usd)} y TP de US${n(tp_usd if tp_usd else sl_usd * cfg.rr)}"
    elif cfg.sl_modo == "atr":
        gestion = f"SL de {n(cfg.sl_valor, 1)}×ATR({cfg.atr_periodo}) y TP a 1:{n(cfg.rr, 1)}"
    elif cfg.sl_modo == "pct":
        gestion = f"SL de {n(cfg.sl_valor, 2)}% del precio y TP a 1:{n(cfg.rr, 1)}"
    else:
        gestion = f"SL fijo de {n(cfg.sl_valor, 2)} de precio y TP a 1:{n(cfg.rr, 2)}"
    filtros = []
    if cfg.sma_activo:
        x = f"SMA {cfg.sma_periodo}"
        if cfg.sma_dist_min_atr > 0:
            x += f", a más de {n(cfg.sma_dist_min_atr, 1)}×ATR"
        if cfg.sma_pendiente_n > 0:
            x += f", pendiente a favor ({cfg.sma_pendiente_n} velas)"
        filtros.append(x)
    if cfg.adx_activo:
        x = f"ADX({cfg.adx_periodo}) ≥ {n(cfg.adx_min, 0)}"
        if cfg.adx_max:
            x += f" y ≤ {n(cfg.adx_max, 0)}"
        if cfg.adx_creciente_n > 0:
            x += f", creciente ({cfg.adx_creciente_n} velas)"
        filtros.append(x)
    if cfg.atr_activo:
        x = "ATR"
        if cfg.atr_min:
            x += f" ≥ {n(cfg.atr_min, 3)}%"
        if cfg.atr_max:
            x += f" ≤ {n(cfg.atr_max, 3)}%"
        if cfg.atr_rel_n:
            x += f", relativo a {cfg.atr_rel_n} velas entre {n(cfg.atr_rel_min or 0, 1)} y {n(cfg.atr_rel_max or 0, 1)}"
        filtros.append(x)
    if cfg.sesion_activo:
        filtros.append("sesión " + " + ".join(cfg.sesiones))
    filtros_txt = ("filtros: " + "; ".join(filtros)) if filtros else "sin filtros"
    costos = {"vela": "spread de cada vela", "mediana": "spread de cada vela (ceros reemplazados por la mediana)",
              "fijo": f"spread fijo de {n(cfg.spread_fijo, 2)}", "ninguno": "sin spread"}[cfg.spread]
    if cfg.costo_extra:
        costos += f" y costo extra de {n(cfg.costo_extra, 2)} por operación"
    base = (f"En el período <b>{pd.Timestamp(ini):%d/%m/%Y} → {pd.Timestamp(fin):%d/%m/%Y}</b> ({n(meses, 1)} meses) "
            f"sobre <b>{simbolo}</b>{f' en velas <b>{tf}</b>' if tf else ''}, usando el cruce de EMA <b>{cfg.ema_corta}/{cfg.ema_larga}</b> "
            f"({dir_txt}), con {gestion}, {filtros_txt}, {costos}")
    if neto is not None:
        verbo = "ganado" if neto >= 0 else "perdido"
        base += (f" y {n(lotes)} lotes, habrías <b>{verbo} US${n(abs(neto))}</b> en {n_res} operaciones "
                 f"({tp} ganadoras y {sl} perdedoras)")
        if dd_usd:
            base += f", con una caída máxima de US${n(dd_usd)}"
    else:
        base += f", habrías tenido {n_res} operaciones ({tp} ganadoras y {sl} perdedoras)"
    return base + f". La expectativa fue de <b>{n(exp_R, 2)} R</b> por operación."


# ------------------------------------------------------------------ veredicto
def _fmt_pct(x, d=0):
    return "–" if x is None or x != x else f"{100 * x:.{d}f}%".replace(".", ",")


def evaluar_veredicto(r: dict, cfg, meses_datos: float, usd_por_R: Optional[float] = None,
                      capital: float = 0.0, limite_pct: float = 10.0, pruebas: int = 1) -> dict:
    """Aplica los criterios y devuelve nivel, titulo, checks, proyecciones y notas."""
    t = r["tabla"]
    tt, ti, to = t.loc["Todo"], t.loc["In-sample"], t.loc["Out-of-sample"]
    tr = r["trades"]
    n, n_oos = int(tt["resueltas"]), int(to["resueltas"])
    checks, notas = [], []

    # tramos de operaciones
    corte = r["corte"]
    res = _resueltas(tr)
    tr_oos = res[res["i"] >= corte] if len(res) else res
    par_t, par_o = parametros_binomiales(tr, cfg.rr), (parametros_binomiales(tr_oos, cfg.rr) if len(tr_oos) else None)
    pv_t = prob_ventaja(par_t)
    pv_o = prob_ventaja(par_o) if (par_o and n_oos >= 15) else None
    tasa = n / meses_datos if meses_datos > 0 else 0.0
    limite_usd = capital * limite_pct / 100.0 if capital > 0 else None
    proy_t = proyectar(par_t, tasa, usd_por_R, limite_usd)
    proy_o = proyectar(par_o, tasa, usd_por_R, limite_usd) if (par_o and n_oos >= 30) else []

    # A) muestra
    if n >= 100 and n_oos >= 30:
        a = (OK, f"{n} operaciones ({n_oos} en out-of-sample).")
    elif n >= 50 and n_oos >= 15:
        a = (WARN, f"{n} operaciones ({n_oos} en out-of-sample): alcanza para una idea, no para confiar.")
    else:
        a = (BAD, f"Solo {n} operaciones ({n_oos} en out-of-sample): muy poco para concluir.")
    checks.append((a[0], "Muestra suficiente", a[1]))

    # B) expectativa
    e_t, e_o = float(tt["exp_R"]) if tt["exp_R"] == tt["exp_R"] else -9, float(to["exp_R"]) if to["exp_R"] == to["exp_R"] else -9
    sg = lambda x: f"{x:+.2f}".replace(".", ",") + " R"
    if e_t > 0 and e_o > 0:
        b = (OK, f"Positiva en todo el período ({sg(e_t)}) y en out-of-sample ({sg(e_o)}).")
    elif e_t > 0 or e_o > 0:
        b = (WARN, f"Solo positiva en {'todo el período' if e_t > 0 else 'out-of-sample'} "
                   f"(todo {sg(e_t)}, out-of-sample {sg(e_o)}).")
    else:
        b = (BAD, f"Negativa o nula (todo {sg(e_t)}, out-of-sample {sg(e_o)}).")
    checks.append((b[0], "Expectativa positiva", b[1]))

    # C) ventaja real (probabilidad posterior)
    exigido = 0.99 if pruebas > 10 else 0.95
    candidatas = [x for x in (pv_t, pv_o) if x is not None and x == x]
    pv = min(candidatas) if candidatas else float("nan")
    if pv != pv:
        c = (BAD, "No se pudo estimar.")
    elif pv >= exigido:
        c = (OK, f"{_fmt_pct(pv)} de probabilidad de que la ventaja sea real (se exige {_fmt_pct(exigido)}"
                 f"{' por las muchas pruebas' if pruebas > 10 else ''}).")
    elif pv >= 0.80:
        c = (WARN, f"{_fmt_pct(pv)} de probabilidad de que la ventaja sea real: hay indicios, no certeza.")
    else:
        c = (BAD, f"Solo {_fmt_pct(pv)} de probabilidad de que la ventaja sea real: no se distingue del azar.")
    checks.append((c[0], "Ventaja estadística", c[1]))

    # D) contra el azar (out-of-sample)
    az = to["mejor_que_%azar"]
    if az != az or n_oos < 15:
        d = (WARN, "El out-of-sample tiene muy pocas operaciones para compararlo con el azar.")
    elif az >= 90:
        d = (OK, f"Mejor que el {az:.0f}% de las entradas al azar en out-of-sample.")
    elif az >= 70:
        d = (WARN, f"Mejor que el {az:.0f}% de las entradas al azar en out-of-sample: moderado.")
    else:
        d = (BAD, f"Solo mejor que el {az:.0f}% de las entradas al azar en out-of-sample.")
    checks.append((d[0], "Mejor que el azar", d[1]))

    # E) consistencia por año
    pa = r["por_anio"]
    pa = pa[pa["resueltas"] >= 10] if len(pa) else pa
    if len(pa) < 2:
        e = (WARN, "Hay menos de 2 años con operaciones suficientes para evaluar la consistencia.")
    else:
        pos = int((pa["exp_R"] > 0).sum())
        fr = pos / len(pa)
        e = ((OK if fr >= 0.6 else WARN if fr >= 0.5 else BAD), f"Expectativa positiva en {pos} de {len(pa)} años.")
    checks.append((e[0], "Consistencia por año", e[1]))

    # F) costos
    P = r["P"]
    dist_m = float(np.mean(P.dist)) if len(P.dist) else 0.0
    sp_pct = 100 * float(np.mean(P.sp)) / dist_m if dist_m > 0 else float("nan")
    if sp_pct != sp_pct:
        f = (WARN, "No se pudo medir el peso del spread.")
    elif sp_pct <= 20:
        f = (OK, f"El spread es el {sp_pct:.0f}% del SL: costo razonable.")
    elif sp_pct <= 35:
        f = (WARN, f"El spread es el {sp_pct:.0f}% del SL: pesa bastante.")
    else:
        f = (BAD, f"El spread es el {sp_pct:.0f}% del SL: el costo domina el resultado.")
    if cfg.spread == "vela" and P.spread_ceros_pct > 5 and f[0] == OK:
        f = (WARN, f"{P.spread_ceros_pct:.0f}% de las velas tiene spread 0 en el historial: el costo puede estar subestimado.")
    checks.append((f[0], "Peso de los costos", f[1]))

    # G) riesgo para la cuenta (límite de pérdida máxima)
    p12 = None
    for proy in (proy_t, proy_o):
        for fila in proy:
            if fila["meses"] == 12 and fila["p_limite"] is not None:
                p12 = max(p12 or 0.0, fila["p_limite"])
    if p12 is not None:
        cap = f"{capital:,.0f}".replace(",", ".")
        g = ((OK if p12 <= 0.10 else WARN if p12 <= 0.25 else BAD),
             f"{_fmt_pct(p12)} de probabilidad de tocar la pérdida máxima ({limite_pct:g}% de US${cap}) en 12 meses.")
        checks.append((g[0], "Riesgo para la cuenta", g[1]))
    else:
        notas.append("No se evaluó el riesgo para la cuenta: cargá el capital en la barra lateral.")

    # veredicto
    puntos = sum({OK: 2, WARN: 1, BAD: 0}[x] for x, _, _ in checks[1:])
    tope = 2 * len(checks[1:])
    est = {nombre: estado for estado, nombre, _ in checks}
    if est["Muestra suficiente"] == BAD:
        nivel, titulo = "nc", "No concluyente: hay muy pocas operaciones para opinar"
        sig = "Ampliá el período, usá una temporalidad menor o aflojá los filtros hasta tener más operaciones."
    elif est["Expectativa positiva"] == BAD:
        nivel, titulo = "pierde", "No válida: pierde dinero"
        sig = ("La expectativa es negativa con estos parámetros. Descartala o cambiá la lógica de fondo, no solo los números: "
               "ajustar hasta que salga bien suele ser sobreajuste.")
    elif est["Ventaja estadística"] == BAD:
        nivel, titulo = "sin", "No válida: no hay ventaja demostrable"
        sig = ("El resultado es compatible con el azar. Probá otra idea o sumá más datos; no la automatices ni la ajustes "
               "hasta que dé bien.")
    elif (puntos == tope and est["Muestra suficiente"] == OK and n >= 200 and n_oos >= 50):
        nivel, titulo = "solida", "Válida, evidencia sólida"
        sig = ("Pasala a demo con el lote previsto y revisá cada mes que la frecuencia de operaciones, el spread y la "
               "ejecución reales se parezcan a lo modelado.")
    elif puntos >= tope - 1 and BAD not in est.values() and est["Muestra suficiente"] == OK:
        nivel, titulo = "ok", "Válida para intentar, empezando en demo"
        sig = "Pasala a demo 1 a 3 meses y comprobá que la frecuencia de operaciones, el spread y la ejecución reales se parezcan a lo modelado."
    elif puntos >= 0.6 * tope:
        nivel, titulo = "dudosa", "Dudosa: hay indicios, pero no alcanza para confiar"
        sig = "Revisá los puntos con ! o ✕. Antes de arriesgar una cuenta, validala con más datos o en otros símbolos."
    else:
        nivel, titulo = "sin", "No válida: los criterios no se cumplen en conjunto"
        sig = "No hay evidencia suficiente en conjunto. No la automatices: probá otra idea o más datos."
    if pruebas > 10:
        notas.append(f"Llevás {pruebas} pruebas: se exigió una confianza mayor (99%) porque con tantas combinaciones "
                     "algo sale bien por azar.")
    return {"nivel": nivel, "titulo": titulo, "siguiente_paso": sig, "checks": checks, "puntos": puntos, "tope": tope,
            "prob_ventaja_total": pv_t, "prob_ventaja_oos": pv_o, "proy_total": proy_t, "proy_oos": proy_o,
            "tasa_mes": tasa, "notas": notas}
