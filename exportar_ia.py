"""Informe para analizar una corrida con una IA: un ZIP con el informe en Markdown y las operaciones en CSV.

No depende de Streamlit: recibe lo que la página ya calculó y lo vuelca como texto plano (números sin formato visual,
tablas en Markdown, definiciones al principio) para que cualquier modelo pueda leerlo sin ver la pantalla."""
import dataclasses
import io
import json
import re
import zipfile
from datetime import datetime

import numpy as np
import pandas as pd

import engine as eng
import metrics as met
import veredicto as vd

GUIA = """## Cómo leer este informe
- **R** es la unidad de riesgo: 1 R = lo que se pierde si la operación toca el SL. Una operación que llega al TP con RR 2 da +2 R.
- **exp_R** (expectativa) es el promedio de R por operación resuelta. Positiva = gana en promedio, antes de saber si es azar.
- **resueltas** son las operaciones que terminaron en TP o SL (o cerraron por la señal de salida). **abiertas** no llegaron a cerrar al final del historial y no cuentan.
- **%TP** es el porcentaje de operaciones ganadoras; **%equilibrio** es el mínimo de %TP para no perder con ese RR y esos costos.
- **In-sample** es el tramo con el que se eligieron los parámetros; **Out-of-sample (OOS)** es el tramo reservado que el modelo no vio. Lo importante es el OOS.
- **azar_exp_R** y **mejor_que_%azar**: expectativa de entrar al azar con las mismas reglas (repetido muchas veces) y percentil de la estrategia frente a eso. Cerca de 50 % = indistinguible del azar.
- **maxDD_R**: peor caída desde un máximo, en R. **racha_SL**: máxima cantidad de SL seguidos.
- Los resultados son teóricos: velas OHLC (no ticks), si una vela toca SL y TP cuenta SL, sin slippage ni gaps.
"""


def _txt(h) -> str:
    """HTML de la página -> texto plano."""
    s = re.sub(r"<br\s*/?>", "\n", str(h))
    s = re.sub(r"</(div|p|li|tr)>", "\n", s)
    s = re.sub(r"<[^>]+>", "", s)
    return re.sub(r"\n{3,}", "\n\n", s).replace("&nbsp;", " ").strip()


def _v(x, dec=4) -> str:
    """Valor -> texto: NaN vacío, números redondeados, dicts/listas en JSON."""
    if x is None:
        return ""
    if isinstance(x, (dict, list, tuple)):
        try:
            return json.dumps(x, ensure_ascii=False, default=str)
        except TypeError:
            return str(x)
    if isinstance(x, (bool, np.bool_)):
        return "sí" if x else "no"
    if isinstance(x, (int, np.integer)):
        return str(int(x))
    if isinstance(x, (float, np.floating)):
        return "" if x != x else (f"{x:.{dec}f}".rstrip("0").rstrip(".") if abs(x) < 1e15 else str(x))
    if isinstance(x, (pd.Timestamp, datetime)):
        return str(x)[:19]
    return str(x).replace("|", "/").replace("\n", " ")


def _tabla(df: pd.DataFrame, dec=4, indice: str = "") -> str:
    if df is None or not len(df):
        return "_Sin datos._"
    cols = [indice or (df.index.name or "")] + [str(c) for c in df.columns]
    filas = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for idx, fila in df.iterrows():
        filas.append("| " + " | ".join([_v(idx, dec)] + [_v(x, dec) for x in fila.tolist()]) + " |")
    return "\n".join(filas)


def _clave_valor(d: dict, dec=4) -> str:
    filas = ["| Campo | Valor |", "|---|---|"] + [f"| {k} | {_v(v, dec)} |" for k, v in d.items()]
    return "\n".join(filas)


def _intentar(f, *a, **k):
    try:
        return f(*a, **k)
    except Exception as e:      # una sección que falla no debe impedir descargar el resto
        return {"_error": f"{type(e).__name__}: {e}"}


def informe(r: dict, cfg, simbolo: str, pdin: dict, meta: dict, veredicto: dict = None, relato: str = "",
            obj_pct: float = 5.0, abl=None, comp=None, nombre_app: str = "ACPTester", rev=None):
    """Devuelve (markdown, csv_operaciones, csv_resultados) de la corrida `r` (salida de metrics.evaluar)."""
    P, t, tr, idx = r["P"], r["tabla"], r["trades"], r["P"].indice
    L = [f"# Informe de {nombre_app}: {simbolo}", "",
         f"Generado el {datetime.now():%d/%m/%Y %H:%M}. Backtester de {meta.get('media', 'EMA')} con filtros. "
         "Este archivo reúne la estrategia, los parámetros de la corrida y todos los resultados que muestra la página, "
         "para analizarlos con una IA. Las operaciones están una por una en `operaciones.csv`.", "", GUIA]

    # ---- estrategia
    L += ["## 1. Estrategia", ""]
    if relato:
        L += [_txt(relato), ""]
    L += ["### Parámetros de la estrategia (Config completa)", ""]
    L += [_clave_valor({f.name: getattr(cfg, f.name) for f in dataclasses.fields(cfg)}), ""]
    L += ["_Notas de unidades: con `sl_modo` = precio el `sl_valor` está en unidades de precio (ya convertido desde dólares); con "
          "`sl_modo` = ema es la distancia en unidades de precio entre la media y el SL (ya convertida desde pips si correspondía) o, con `sl_ema_pct` = True, un porcentaje del nivel de referencia; "
          "con atr es un múltiplo del ATR y con pct un porcentaje del precio._", ""]

    if getattr(cfg, "ruptura", None) is not None and getattr(P, "rup", None) is not None:
        import ruptura as _rup
        _n = len(P.c)
        _co = int(r.get("corte", int(_n * 0.7)))
        _ram = [("Todo", 0, _n), ("In-sample", 0, _co), ("Out-of-sample", _co, _n)]
        _e = {k: _intentar(_rup.embudo, P, tr, P.cruces, lo, hi) for k, lo, hi in _ram}
        _s = {k: _intentar(_rup.estadisticas, P, tr, lo, hi) for k, lo, hi in _ram}
        L += ["### Rango de apertura (ruptura)", "",
              f"Rango {_rup.hhmm(cfg.ruptura.apertura_min)}-{_rup.hhmm(cfg.ruptura.apertura_min + cfg.ruptura.rango_min)} de Nueva York; última entrada "
              f"{_rup.hhmm(cfg.ruptura.ultima_min)}; cierre forzado {_rup.hhmm(cfg.ruptura.cierre_min)} (hora de NY). Cada día cae en una sola fila del embudo.", "",
              "**Embudo de días**", "",
              _tabla(pd.DataFrame({k: v for k, v in _e.items()}), 0, "etapa"), "",
              "**Operaciones por tramo** (cantidad y R medio por tipo de salida)", ""]
        for k, v in _s.items():
            L += [f"- {k}: " + (v.get("_error") if "_error" in v else
                                 f"{v['n']} operaciones; " + "; ".join(f"{m}: {x['n']} (R medio {_v(x['R_medio'], 2)})" for m, x in v["salidas"].items()))]
        L += [""]
        L += ["_La comparación contra el azar no se calcula en la ruptura._", ""]

    # ---- datos y corrida
    L += ["## 2. Datos y corrida", ""]
    datos = {"Símbolo": simbolo, "Fuente de datos": meta.get("fuente"), "Temporalidad": meta.get("tf"),
             "Remuestreo": meta.get("regla"), "Hora del historial corregida": meta.get("hora_corregida") or "no",
             "Salto de huso detectado (sin corregir)": meta.get("salto_huso_detectado") or "no",
             "Velas sospechosas excluidas": meta.get("velas_excluidas") or "no",
             "Valor por 1,00 de precio forzado (US$ con 1 lote)": meta.get("valor_por_unidad_forzado") or "automático",
             "Primera vela": idx[0], "Última vela": idx[-1], "Velas": len(idx),
             "Meses de datos": round((idx[-1] - idx[0]).days / 30.44, 1), "Out-of-sample reservado (%)": meta.get("oos"),
             "Repeticiones del azar": meta.get("azar_n"), "Prueba n.º de esta sesión": r.get("prueba"),
             "Lotes": pdin.get("lotes"), "Comisión por lote (US$)": pdin.get("comision"), "Capital (US$)": pdin.get("capital"),
             "Límite de pérdida total (%)": pdin.get("limite_pct"), "tick_size": pdin.get("tick_size"),
             "tick_value": pdin.get("tick_value"), "Corte in-sample / out-of-sample (índice de vela)": r.get("corte"),
             "Fecha del corte": idx[min(int(r.get("corte", 0)), len(idx) - 1)]}
    L += [_clave_valor(datos), ""]
    if r.get("avisos"):
        L += ["### Avisos de la corrida", ""] + [f"- {a}" for a in r["avisos"]] + [""]

    # ---- resultados por tramo
    L += ["## 3. Resultados por tramo", "",
          "Columnas completas del backtest (ver la guía arriba). `pb` y `descartes` van como JSON.", "",
          _tabla(t, 4, "tramo"), ""]
    if len(r.get("por_anio", [])):
        L += ["### Por año (operaciones tomadas entre todo el historial)", "", _tabla(r["por_anio"], 4, "año"), ""]
    if r.get("descartes"):
        L += ["### Señales descartadas por filtro (tramo Todo)", "", _clave_valor(r["descartes"], 0), ""]
    si = int(getattr(tr, "attrs", {}).get("sl_invalido", 0) or 0)
    if si:
        L += [f"- {si} señales sin operar: la media de referencia quedó del lado equivocado del precio (SL a una media).", ""]

    if getattr(cfg, "tstop_activo", False) and len(tr) and "motivo" in tr:
        _ts = tr[tr["motivo"] == "tiempo"]
        L += ["### Cierre por tiempo (tramo Todo)", "",
              f"- Regla: a las {int(cfg.tstop_velas)} velas de la entrada, si sigue abierta (sin breakeven) y va en {cfg.tstop_r} R o peor, se cierra a mercado.",
              f"- Operaciones cerradas por tiempo: {len(_ts)} de {len(tr)}; R total {_v(float(_ts['R'].sum()), 2)}; "
              f"R promedio {_v(float(_ts['R'].mean()) if len(_ts) else 0.0, 2)}.", ""]

    if getattr(cfg, "noticias_activo", False):
        _P_n = r.get("P")
        _N_n = getattr(_P_n, "noti", None) or {}
        _nt = tr[tr["motivo"] == "noticia"] if len(tr) and "motivo" in tr else tr
        _dn = int((r.get("descartes") or {}).get("noticias", 0))
        _fuente = "calendario CSV" if cfg.noticias_fuente == "csv" else (
            f"detectadas en las velas (8:30/10:00/14:00/14:30 de Nueva York, rango >= {_v(cfg.noticias_rango_atr, 1)} x ATR(14) y >= {_v(cfg.noticias_rango_min, 1)} en precio)")
        L += ["### Trading de noticias (tramo Todo)", "",
              f"- Regla 1: sin abrir operaciones (ni reentradas ni órdenes límite) a ±{_v(cfg.noticias_min, 0)} min de una noticia de USD de alto impacto. "
              f"Fuente: {_fuente}. Noticias en el período: {len(_N_n.get('eventos', []))}" +
              (" (por año: " + ", ".join(f"{a}: {c}" for a, c in sorted((_N_n.get('años') or {}).items())) + ")" if _N_n.get("años") else "") + ".",
              f"- Señales descartadas por la ventana: {_dn}.",
              ("- Regla 2: apagada (no se cierra nada antes de la noticia)." if cfg.noticias_cerrar_r is None else
               f"- Regla 2: antes de la noticia, si la operación abierta va en {cfg.noticias_cerrar_r} R o peor (y sin breakeven activado) se cierra a mercado. "
               f"Cierres: {len(_nt)}; R total {_v(float(_nt['R'].sum()) if len(_nt) else 0.0, 2)}; R promedio {_v(float(_nt['R'].mean()) if len(_nt) else 0.0, 2)}."),
              "- Límites: las noticias detectadas en las velas se conocen a posteriori (sesgo optimista frente al calendario real); solo se cubren las "
              "operaciones abiertas cerca de la noticia (una abierta desde antes que sigue en ganancia la atraviesa).", ""]

    # ---- cuenta
    cu = r.get("cuenta")
    if getattr(cfg, "reglas_activas", False) and cu:
        L += ["## 4. Reglas de la cuenta (tramo Todo)", ""]
        lim_d, lim_t = cfg.limites_efectivos()
        cu2 = dict(cu)
        if cu2.get("quemada_en") is not None and cu2.get("quemada"):
            cu2["quemada_en_fecha"] = idx[int(cu2["quemada_en"])]
        if cu2.get("retiros"):
            cu2["retiros"] = [f"{idx[int(x['j'])]}: {x['monto']:.2f} US$" for x in cu2["retiros"]]
        if getattr(cfg, "retiro_activo", False):
            cu2["objetivo_por_retiro_%"] = cfg.retiro_pct
        cu2["limite_diario_efectivo_%"], cu2["limite_total_efectivo_%"] = lim_d, lim_t
        L += [_clave_valor(cu2), ""]

    # ---- dinero y métricas derivadas
    res = tr[tr["res"].isin(["TP", "SL", "BE", "PARC_SL"])] if len(tr) else tr
    L += ["## 5. Dinero, frecuencia y rachas", ""]
    if len(res):
        a = (pdin["tick_size"], pdin["tick_value"], pdin["lotes"], pdin["comision"])
        din = _intentar(met.resumen_dinero, tr, *a)
        L += ["### Resultado en dinero (con los lotes de la corrida)", "", _clave_valor(din), ""]
        if "max_drawdown" in din and pdin.get("capital"):
            L += [f"Máx. drawdown ≈ {_v(din['max_drawdown'], 2)} US$ = {_v(100 * din['max_drawdown'] / pdin['capital'], 2)} % del capital.", ""]
        ex = _intentar(lambda t_, i_, *aa: met.extremos_diarios(t_, i_, *aa, claves=eng.claves_dia(i_, cfg)), tr, idx, *a)     # mismo dia que usa la cuenta
        if ex:
            L += ["### Peor y mejor día", "", _clave_valor(ex), ""]
        L += ["### Frecuencia de operaciones", "", _clave_valor(_intentar(met.frecuencia, tr, idx)), ""]
        L += ["### Tasa de acierto y duración (minutos y velas)", "", _clave_valor(_intentar(met.duraciones, tr, idx)), ""]
        rach = _intentar(met.rachas, tr, idx, 5)
        for k, nom in (("TP", "Mayores rachas de TP seguidos"), ("SL", "Mayores rachas de SL seguidos")):
            if isinstance(rach, dict) and k in rach:
                L += [f"### {nom}", "", _tabla(pd.DataFrame(rach[k]), 3), ""]
        if pdin.get("capital"):
            ob = _intentar(met.ciclos_objetivo, tr, idx, *a[:3], a[3], pdin["capital"], obj_pct)
            if "resumen" in ob:
                L += [f"### Objetivo por retiro: {obj_pct} % del balance inicial", "",
                      _clave_valor({**ob["resumen"], "objetivo_usd": ob["objetivo_usd"]}), ""]
                if ob.get("ciclos"):
                    L += [_tabla(pd.DataFrame(ob["ciclos"]), 2), ""]
                L += ["Ciclo en curso: " + _v(ob["en_curso"]), ""]
    else:
        L += ["_Sin operaciones resueltas._", ""]

    # ---- veredicto
    if veredicto:
        L += ["## 6. Conclusión y veredicto", "", f"**{veredicto['titulo']}** (nivel: {veredicto['nivel']}; puntaje "
              f"{veredicto['puntos']} de {veredicto['tope']}).", "", _txt(veredicto["siguiente_paso"]), "",
              "### Criterios", "", "| | Criterio | Resultado |", "|---|---|---|"]
        L += [f"| {vd.SIMBOLO[e]} | {n} | {_txt(d).replace(chr(10), ' ')} |" for e, n, d in veredicto["checks"]]
        L += ["", "(✓ cumple · ! con reservas · ✕ no cumple)", ""]
        proy_o = {f["meses"]: f for f in veredicto.get("proy_oos", [])}
        filas = []
        for f in veredicto.get("proy_total", []):
            o = proy_o.get(f["meses"], {})
            filas.append({"meses": f["meses"], "operaciones": f.get("n"), "p_ganar_historial": f.get("p_ganar"),
                          "p_ganar_OOS": o.get("p_ganar"), "R_mediana": f.get("R_mediana"), "R_p5": f.get("R_p5"),
                          "R_p95": f.get("R_p95"), "p_toca_limite": f.get("p_limite")})
        if filas:
            L += ["### Probabilidad de terminar en ganancia (Monte Carlo)", "", _tabla(pd.DataFrame(filas).set_index("meses"), 3, "meses"), ""]
        L += [f"Frecuencia observada: {_v(veredicto.get('tasa_mes'), 2)} operaciones por mes.", ""]
        L += [f"- {_txt(n)}" for n in veredicto.get("notas", [])] + [""]

    # ---- ablación y comparación (si se corrieron en esta sesión)
    if abl is not None:
        tabla_abl, omitidos, act_abl = abl
        L += [f"## 7. Modo ablación ({act_abl})", "", "El cruce solo y el efecto de cada filtro, uno por uno (parámetros fijos de cada filtro).", "",
              _tabla(tabla_abl, 4, "configuración"), ""]
        if omitidos:
            L += ["Omitidos: " + ", ".join(omitidos), ""]
    if comp is not None and len(comp) == 3:
        tabla_c, notas_c, estrategia_c = comp
        L += ["## 8. Comparación de símbolos", "", f"Estrategia: {estrategia_c}", "", _tabla(tabla_c, 4, "símbolo"), ""]
        vc = _intentar(vd.evaluar_comparabilidad, tabla_c)
        if "checks" in vc:
            L += [f"**{vc['titulo']}** — {_txt(vc['texto'])}", "", "| | Criterio | Resultado |", "|---|---|---|"]
            L += [f"| {vd.SIMBOLO[e]} | {n} | {_txt(d)} |" for e, n, d in vc["checks"]]
            L += ["", f"Robustez: **{vc['robustez']['titulo']}** — {_txt(vc['robustez']['texto'])}", ""]
        L += [f"- {n}" for n in dict.fromkeys(notas_c or [])] + [""]

    # ---- reversion a la media (sola), solo si el menu 10 estaba activo en la corrida
    if rev is not None and rev[2].activo and rev[4] == simbolo:
        ev_, _cfg_r, rv_, ab_, _ = rev
        L += ["## Reversión a la media (sola)", "",
              f"- Variante {rv_.variante}" + (f": Bollinger de {rv_.bb_n} velas y {_v(rv_.bb_k, 1)} desvíos; ADX({rv_.adx_periodo}) menor a {_v(rv_.adx_max, 1)}."
                                          if rv_.variante == "A" else
                                          f": ruptura falsa del máximo / mínimo de ayer, vuelta a cerrar adentro en {rv_.b_velas} velas"
                                          + (f"; ADX({rv_.adx_periodo}) menor a {_v(rv_.adx_max, 1)}." if rv_.adx_activo_b else ".")),
              "- SL: " + (f"extremo de la señal + {_v(rv_.sl_atr_x, 2)} x ATR({rv_.atr_periodo})" if rv_.sl_modo == "atr" else f"distancia fija {_v(rv_.sl_precio, 2)}")
              + ". TP: " + ("la media de Bollinger (A) o el punto medio del rango de ayer (B)" if rv_.tp_modo == "media" else f"R:R fijo {_v(rv_.rr, 2)}") + ".",
              f"- Riesgo fijo de US${_v(rv_.riesgo_usd, 2)} por operación (lote = riesgo / (distancia del SL x US$ por unidad por lote), redondeado hacia abajo).",
              f"- Cierre por tiempo: {'sí, ' + str(rv_.tstop_velas) + ' velas, R ' + _v(rv_.tstop_r, 2) if rv_.tstop_activo else 'no'}. "
              f"Breakeven: {'sí, activa en ' + _v(rv_.be_act_valor, 2) + ' R, SL en ' + _v(rv_.be_nivel_valor, 2) + ' R' if rv_.be_activo else 'no'}. "
              f"Horario propio: {'sí (' + ', '.join(rv_.sesiones) + ')' if rv_.sesion_activo else 'no'}.",
              "- Esta sección es la reversión corrida SOLA (sin la EMA). La simulación conjunta de la cartera no está incluida.", "",
              "### Resultados por tramo", "", _tabla(ev_["tabla"].drop(columns=["descartes"], errors="ignore"), 4, "tramo"), "",
              "### Resultado por año", "", _tabla(ev_["por_anio"], 4, "año"), "",
              "### Señales descartadas", "", (_clave_valor(ev_["descartes"], 0) if ev_["descartes"] else "_Ninguna._"), "",
              "### Ablación (acumulada)", "", _tabla(ab_, 4, "paso"), ""]
        L += [f"- {a_}" for a_ in ev_["avisos"]] + [""]

    L += ["## Supuestos y limitaciones", "",
          "- Velas OHLC, no ticks: si una vela toca SL y TP, se cuenta SL (y se marca como ambigua).",
          "- Spread: el de cierre de cada vela (o el modo elegido); en velas viejas suele venir en 0.",
          "- Sin slippage ni gaps; en índices hay gaps de apertura y pausas diarias que no se modelan.",
          "- La estimación de probabilidades supone que el futuro se parece al pasado y que las operaciones son independientes.",
          "- Cuantas más pruebas se hacen sobre los mismos datos, más probable es que un resultado bueno sea azar.", ""]

    # ---- operaciones y tabla de resultados en CSV
    csv_ops = tr.to_csv(index=False) if len(tr) else "sin operaciones\n"
    return "\n".join(L), csv_ops, t.to_csv()


def zip_informe(md: str, csv_ops: str, csv_res: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("informe.md", md)
        z.writestr("operaciones.csv", csv_ops)
        z.writestr("resultados_por_tramo.csv", csv_res)
        z.writestr("LEEME.txt", "informe.md: estrategia, parámetros y resultados (leer primero).\n"
                                "operaciones.csv: todas las operaciones, una por fila.\n"
                                "resultados_por_tramo.csv: la tabla Todo / In-sample / Out-of-sample.\n")
    return buf.getvalue()
