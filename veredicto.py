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
def _senal_txt(cfg) -> str:
    """'el cruce de EMA 13/34' (igual que siempre), 'el cruce de SMA 20/50' o 'el cruce del precio con la SMA 50'."""
    tipo = getattr(cfg, "media_tipo", "ema").upper()
    if getattr(cfg, "modo_senal", "cruce") == "precio":
        return f"el cruce del precio con la {tipo} <b>{cfg.media_unica}</b>"
    return f"el cruce de {tipo} <b>{cfg.ema_corta}/{cfg.ema_larga}</b>"


def _ref_pullback(cfg) -> str:
    tipo = getattr(cfg, "media_tipo", "ema").upper()
    if getattr(cfg, "modo_senal", "cruce") == "precio":
        return f"la {tipo}"
    return f"la {tipo} {cfg.pullback_ema}"


def describir(cfg, simbolo: str, tf: str, ini, fin, meses: float, lotes: float, neto: Optional[float],
              n_res: int, tp: int, sl: int, exp_R: float, dd_usd: Optional[float],
              sl_usd: float = 0.0, tp_usd: float = 0.0) -> str:
    """Texto: 'En el período... usando el cruce EMA... habrías ganado/perdido...' (HTML simple)."""
    def n(x, d=2):
        s = f"{x:,.{d}f}".replace(",", "§").replace(".", ",").replace("§", ".")
        return s

    dir_txt = {"ambas": "largos y cortos", "largos": "solo largos", "cortos": "solo cortos"}[cfg.direccion]
    if cfg.sl_modo == "ema":
        _m = cfg.media_tipo.upper()
        _dist = f"{n(cfg.sl_valor, 2)} %" if cfg.sl_ema_pct else f"{n(cfg.sl_valor, 2)} de precio"
        if cfg.sl_ema_ref == "cruce" and cfg.modo_senal != "precio":
            _sl_txt = f"SL a {_dist} del cruce de las {_m} {cfg.ema_corta}/{cfg.ema_larga}"
        else:
            _ref = (f"{_m} {cfg.media_unica}" if cfg.modo_senal == "precio" else
                    f"{_m} {'corta' if cfg.sl_ema_ref == 'corta' else 'larga'} ({cfg.ema_corta if cfg.sl_ema_ref == 'corta' else cfg.ema_larga})")
            _sl_txt = f"SL a {_dist} de la {_ref}"
    else:
        _sl_txt = None
    if cfg.salida_modo == "senal":
        if cfg.modo_senal == "precio":
            sal = f"sin TP fijo: se sale al cierre de la primera vela que cierra del otro lado de la media {cfg.media_unica}"
        else:
            sal = "sin TP fijo: se sale al cierre de la primera vela en que el cruce se invierte"
        if _sl_txt:
            gestion = f"{_sl_txt} y {sal}"
        elif cfg.sl_modo == "precio" and sl_usd > 0:
            gestion = f"SL de US${n(sl_usd)} y {sal}"
        elif cfg.sl_modo == "atr":
            gestion = f"SL de {n(cfg.sl_valor, 1)}×ATR({cfg.atr_periodo}) y {sal}"
        elif cfg.sl_modo == "pct":
            gestion = f"SL de {n(cfg.sl_valor, 2)}% del precio y {sal}"
        else:
            gestion = f"SL fijo de {n(cfg.sl_valor, 2)} de precio y {sal}"
    elif _sl_txt:
        gestion = f"{_sl_txt} y TP a 1:{n(cfg.rr, 1)}"
    elif cfg.sl_modo == "precio" and sl_usd > 0:
        gestion = f"SL de US${n(sl_usd)} y TP de US${n(tp_usd if tp_usd else sl_usd * cfg.rr)}"
    elif cfg.sl_modo == "atr":
        gestion = f"SL de {n(cfg.sl_valor, 1)}×ATR({cfg.atr_periodo}) y TP a 1:{n(cfg.rr, 1)}"
    elif cfg.sl_modo == "pct":
        gestion = f"SL de {n(cfg.sl_valor, 2)}% del precio y TP a 1:{n(cfg.rr, 1)}"
    else:
        gestion = f"SL fijo de {n(cfg.sl_valor, 2)} de precio y TP a 1:{n(cfg.rr, 2)}"
    if getattr(cfg, "be_activo", False):
        _a = {"r": f"{n(cfg.be_act_valor, 2)} R de ganancia", "usd": f"US${n(cfg.be_act_valor)} de ganancia",
              "pct_tp": f"{n(cfg.be_act_valor, 0)} % del camino al TP"}[cfg.be_act_modo]
        _v = cfg.be_nivel_valor
        _b = ("la entrada" if _v == 0 else (f"{n(_v, 2)} R sobre la entrada" if cfg.be_nivel_modo == "r" else f"US${n(_v)} sobre la entrada"))
        gestion += f" (con breakeven: al llegar a {_a} el SL pasa a {_b})"
    if not getattr(cfg, "finde_mantener", True):
        gestion += " y sin posiciones el fin de semana (se cierra todo el viernes antes del cierre del mercado)"
    filtros = []
    if cfg.sma_activo:
        x = f"SMA {cfg.sma_periodo}"
        if cfg.sma_dist_min_atr > 0:
            x += f", a más de {n(cfg.sma_dist_min_atr, 1)}×ATR"
        if cfg.sma_pendiente_n > 0:
            x += f", pendiente a favor ({cfg.sma_pendiente_n} velas)"
        filtros.append(x)
    if cfg.vwap_activo:
        x = "VWAP diario"
        if cfg.vwap_dist_min_atr > 0:
            x += f", a más de {n(cfg.vwap_dist_min_atr, 1)}×ATR"
        filtros.append(x)
    if cfg.adx_activo:
        x = f"ADX({cfg.adx_periodo}) ≥ {n(cfg.adx_min, 0)}"
        if cfg.adx_max:
            x += f" y ≤ {n(cfg.adx_max, 0)}"
        if cfg.adx_creciente_n > 0:
            x += f", creciente ({cfg.adx_creciente_n} velas)"
        filtros.append(x)
    if cfg.rango_activo:
        filtros.append(f"rango: ratio de eficiencia({cfg.rango_ventana}) ≥ {n(cfg.rango_min, 2)}")
    if cfg.atr_activo:
        x = "ATR"
        if cfg.atr_min:
            x += f" ≥ {n(cfg.atr_min, 3)}%"
        if cfg.atr_max:
            x += f" ≤ {n(cfg.atr_max, 3)}%"
        if cfg.atr_rel_n:
            x += f", relativo a {cfg.atr_rel_n} velas entre {n(cfg.atr_rel_min or 0, 1)} y {n(cfg.atr_rel_max or 0, 1)}"
        filtros.append(x)
    for _k in ("tm1", "tm2"):
        if getattr(cfg, _k + "_activo"):
            filtros.append(f"tendencia mayor {getattr(cfg, _k + '_tf')} (cierre sobre/bajo su SMA {getattr(cfg, _k + '_periodo')})")
    if cfg.vp_activo:
        _r = {"poc": "compras sobre el POC y ventas bajo el POC", "fuera": "compras sobre el VAH y ventas bajo el VAL",
              "dentro": "solo entre el VAL y el VAH"}[cfg.vp_modo]
        filtros.append(f"Volume Profile de {cfg.vp_dias} día(s) (escalón de {n(cfg.vp_escalon, 2)}): {_r}")
    if cfg.sesion_activo:
        from sessions import SESIONES_LOCAL as _SL
        _hh = lambda x: f"{int(x):02d}:{int(round((x % 1) * 60)):02d}"
        _tx = [f"{n_} {_hh(cfg.horarios[n_][1])}-{_hh(cfg.horarios[n_][2])} hora local"
               if cfg.horarios and n_ in cfg.horarios and tuple(cfg.horarios[n_]) != tuple(_SL[n_]) else n_
               for n_ in cfg.sesiones]
        _tx = [t + " sin pausa de mediodía" if n_ in (cfg.sin_pausa or ()) else t for t, n_ in zip(_tx, cfg.sesiones)]
        _tx = [t + f" sin {_hh(cfg.cortes[n_][0])}-{_hh(cfg.cortes[n_][1])} hora local" if cfg.cortes and n_ in cfg.cortes else t
               for t, n_ in zip(_tx, cfg.sesiones)]
        filtros.append("sesión " + " + ".join(_tx))
    filtros_txt = ("filtros: " + "; ".join(filtros)) if filtros else "sin filtros"
    if cfg.pb_efectivo():
        filtros_txt += (f", entrando en pullback del {n(cfg.pullback_pct, 0)}% hacia {_ref_pullback(cfg)} "
                        f"(caduca a las {cfg.pullback_velas} velas)")
    costos = {"vela": "spread de cada vela", "mediana": "spread de cada vela (ceros reemplazados por la mediana)",
              "fijo": f"spread fijo de {n(cfg.spread_fijo, 2)}", "ninguno": "sin spread"}[cfg.spread]
    if cfg.costo_extra:
        costos += f" y costo extra de {n(cfg.costo_extra, 2)} por operación"
    base = (f"En el período <b>{pd.Timestamp(ini):%d/%m/%Y} → {pd.Timestamp(fin):%d/%m/%Y}</b> ({n(meses, 1)} meses) "
            f"sobre <b>{simbolo}</b>{f' en velas <b>{tf}</b>' if tf else ''}, usando {_senal_txt(cfg)} "
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


# ----------------------------------------------------------------------------- comparación de símbolos
def evaluar_comparabilidad(tabla: pd.DataFrame) -> dict:
    """Dos preguntas distintas sobre la tabla de comparar_simbolos:
      1) ¿son comparables los símbolos entre sí? (checks -> 'ok' / 'reservas' / 'no')
      2) ¿la estrategia se sostiene en todos? (robustez -> 'ok' / 'dudosa' / 'sin')
    Ser comparables no dice que la estrategia funcione: solo que la comparación es justa."""
    t = tabla
    N = len(t)
    f = lambda x: f"{x:.1f}".replace(".", ",")
    y_ = lambda xs: xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " y " + xs[-1]
    checks = []

    # 1) período común
    ini, fin = pd.to_datetime(t["desde"]), pd.to_datetime(t["hasta"])
    dif = max((ini.max() - ini.min()).days, (fin.max() - fin.min()).days)
    meses = (fin.min() - ini.max()).days / 30.44
    ctx = f"{ini.max():%Y-%m-%d} → {fin.min():%Y-%m-%d} ({f(max(meses, 0))} meses)"
    if dif <= 5:
        checks.append((OK, "Período común", f"{ctx} en todos los símbolos."))
    elif dif <= 60:
        checks.append((WARN, "Período común", f"Los períodos difieren hasta {dif} días. Período compartido: {ctx}."))
    else:
        checks.append((BAD, "Período común", f"Los períodos difieren hasta {dif} días: se comparan épocas distintas."))

    # 2) muestra
    chicos = [s for s, r in t.iterrows() if r["resueltas"] < 100 or r["resueltas_OOS"] < 30]
    muy_chicos = [s for s, r in t.iterrows() if r["resueltas"] < 50 or r["resueltas_OOS"] < 15]
    if not chicos:
        checks.append((OK, "Muestra suficiente en cada uno", "Todos tienen al menos 100 operaciones y 30 en out-of-sample."))
    else:
        det = "; ".join(f"{s}: {int(t.loc[s, 'resueltas'])} operaciones, {int(t.loc[s, 'resueltas_OOS'])} en out-of-sample" for s in chicos)
        checks.append((BAD if muy_chicos else WARN, "Muestra suficiente en cada uno", f"{det} (mínimo 100 y 30)."))

    # 3) tipo de activo
    tipos = list(dict.fromkeys(t["tipo"]))
    if len(tipos) == 1:
        checks.append((OK, "Mismo tipo de activo", f"Todos son de tipo «{tipos[0]}»."))
    else:
        checks.append((BAD, "Mismo tipo de activo", " vs ".join(f"{s} es {r['tipo']}" for s, r in t.iterrows())
                       + ": distinta dinámica, gaps y horarios."))

    # 4) riesgo equivalente (SL en múltiplos de ATR)
    sl = t["sl_atr"].astype(float)
    if sl.isna().any() or (sl <= 0).any():
        checks.append((WARN, "Riesgo equivalente (SL en ATR)", "No se pudo medir el SL en múltiplos de ATR."))
    else:
        ratio = sl.max() / sl.min()
        det = y_([f"{f(x)}×ATR en {s}" for s, x in sl.items()])
        txt = f"El SL equivale a {det}" + (f" ({f(ratio)} veces más ancho)." if ratio > 1.05 else ".")
        checks.append((OK if ratio <= 1.5 else WARN if ratio <= 2.5 else BAD, "Riesgo equivalente (SL en ATR)", txt))

    # 5) costos
    sp = t["spread_%SL"].astype(float)
    dsp = float(sp.max() - sp.min())
    det = y_([f"{sp[s]:.0f}%" for s in t.index])
    checks.append((OK if dsp <= 5 else WARN if dsp <= 15 else BAD, "Costos comparables (spread / SL)",
                   f"{det} del SL: " + ("los costos pesan parecido." if dsp <= 5 else "los costos pesan distinto en cada uno.")))

    # 6) frecuencia
    om = t["ops_mes"].astype(float)
    rat = om.max() / om.min() if om.min() > 0 else float("inf")
    det = y_([f(x) for x in om])
    checks.append((OK if rat <= 2 else WARN if rat <= 4 else BAD, "Frecuencia parecida", f"{det} operaciones por mes."))

    # 7) filtros aplicables
    if t["sesion_no_aplica"].astype(bool).any():
        quienes = ", ".join(s for s, r in t.iterrows() if r["sesion_no_aplica"])
        checks.append((WARN, "Filtros aplicables a todos",
                       f"El filtro Tokio/Londres/NY no equivale al horario propio de {quienes}."))
    else:
        checks.append((OK, "Filtros aplicables a todos", "Los filtros activos tienen sentido en todos los símbolos."))

    n_ok = sum(c[0] == OK for c in checks)
    n_w = sum(c[0] == WARN for c in checks)
    n_b = sum(c[0] == BAD for c in checks)
    malos = [c[1] for c in checks if c[0] == BAD]
    if n_b:
        nivel, titulo = "no", "No comparables entre sí"
        texto = (f"Hay {n_b} criterio{'s' if n_b > 1 else ''} que no se cumple{'n' if n_b > 1 else ''} "
                 f"({'; '.join(m_.lower() for m_ in malos)}). Leé cada símbolo por separado y no promedies ni compares "
                 "sus resultados como si fueran una misma prueba.")
    elif n_w:
        nivel, titulo = "reservas", "Comparables con reservas"
        texto = "Se pueden mirar lado a lado, pero revisá los criterios marcados con ! antes de sacar conclusiones."
    else:
        nivel, titulo = "ok", "Comparables"
        texto = "Los símbolos son equiparables: la comparación es justa. Eso no dice todavía que la estrategia funcione."

    # robustez: positiva en todo el período y en out-of-sample
    pos_t = int((t["exp_R"] > 0).sum())
    pos_o = int((t["exp_R_OOS"] > 0).sum())
    k = int(((t["exp_R"] > 0) & (t["exp_R_OOS"] > 0)).sum())
    if k == N:
        rn, rtit = "ok", "Se sostiene en todos los símbolos"
    elif k > N / 2:
        rn, rtit = "dudosa", "Se sostiene en la mayoría de los símbolos"
    else:
        rn, rtit = "sin", "No se sostiene en todos los símbolos"
    rtxt = f"Expectativa positiva en todo el período y en out-of-sample en {k} de {N}. "
    if nivel == "no":
        rtxt += "Con símbolos no comparables, esto es solo una pista: probar varios activos hace esperable que alguno salga bien por azar."
    else:
        rtxt += "Probar varios activos hace esperable que alguno salga bien por azar."
    return {"nivel": nivel, "titulo": titulo, "texto": texto, "checks": checks, "n_ok": n_ok, "n_warn": n_w, "n_bad": n_b,
            "robustez": {"nivel": rn, "titulo": rtit, "texto": rtxt, "k": k, "N": N, "pos_total": pos_t, "pos_oos": pos_o},
            "rango_exp": (float(t["exp_R"].min()), float(t["exp_R"].max()))}
