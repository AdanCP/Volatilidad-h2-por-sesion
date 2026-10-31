"""Interfaz Streamlit del backtester de cruce de EMAs con filtros opcionales.

Usa solo los módulos del backtester (data, engine, metrics, ui_helpers). No toca app.py ni los bots.

Fuentes de datos:
  - MT5 directo (FTMO): solo corriendo la app EN TU PC con Windows, con el terminal abierto
    (pip install MetaTrader5 y streamlit run app_backtest.py). Elegís símbolos por familia.
  - CSV exportado de MT5: sirve online (Render). Generalos con exportar_mt5.py; podés subir
    varios archivos, uno por símbolo.
  - Datos sintéticos: solo para probar la interfaz.
"""
import io
import os
from datetime import date

import pandas as pd
import streamlit as st

import data
import engine as eng
import metrics as met
import ui_estilo as vis
import veredicto as vd
import ui_helpers as ui

try:
    import MetaTrader5  # noqa: F401
    MT5_OK = True
except ImportError:
    MT5_OK = False

SPREADS = {"Spread de la vela": "vela", "Ceros → mediana": "mediana",
           "Valor fijo": "fijo", "Sin spread": "ninguno"}
DIRECCIONES = {"Largos y cortos": "ambas", "Solo largos": "largos", "Solo cortos": "cortos"}
SESIONES = ["Tokio", "Londres", "Nueva York"]
COLS_TABLA = ["resueltas", "TP", "SL", "abiertas", "ambiguas", "%TP", "%equilibrio", "exp_R",
              "R_total", "maxDD_R", "racha_SL", "azar_exp_R", "mejor_que_%azar",
              "cruces", "tomados", "ignoradas"]
SL_ATR, SL_PCT, SL_USD = "Múltiplo de ATR", "% del precio", "Dólares fijos"
TP_RR, TP_USD = "Ratio R:R", "Dólares fijos"
ETQ_MT5 = "MT5 directo (FTMO)" if MT5_OK else "MT5 directo (solo en tu PC con Windows)"
ETQ_CSV = "CSV exportado de MT5"
ETQ_SINT = "Datos sintéticos (demo)"


@st.cache_data(show_spinner=False)
def _csv(contenido: bytes, point: float) -> pd.DataFrame:
    return data.cargar_csv(io.BytesIO(contenido), point)


@st.cache_data(show_spinner=False)
def _sintetico(n: int, tendencia: float, semilla: int) -> pd.DataFrame:
    return data.sintetico(n=n, tendencia=tendencia, seed=semilla)


@st.cache_data(show_spinner=False)
def _mt5(simbolo: str, tf: str, desde: str, hasta: str):
    return data.cargar_mt5(simbolo, tf, desde, hasta)


@st.cache_data(ttl=300, show_spinner=False)
def _simbolos_mt5() -> list:
    return data.listar_simbolos_mt5()


st.session_state.setdefault("contador", met.ContadorPruebas())
st.session_state.setdefault("res", None)
st.session_state.setdefault("comp", None)

st.markdown(vis.css(), unsafe_allow_html=True)

# ------------------------------------------------------------------ datos
with st.sidebar:
    with st.expander("1. Datos", expanded=True):
        fuente = st.radio("Fuente", [ETQ_MT5, ETQ_CSV, ETQ_SINT], index=0 if MT5_OK else 1)
        datos, specs, avisos_datos = {}, {}, []
        try:
            if fuente == ETQ_MT5 and not MT5_OK:
                st.warning("MT5 directo solo funciona corriendo la app **en tu PC con Windows**, con el "
                           "terminal de FTMO abierto y con sesión iniciada:\n\n"
                           "1. `pip install MetaTrader5`\n2. `streamlit run app_backtest.py`\n\n"
                           "En Render (online) no existe terminal de MT5. Online usá **CSV exportado**: "
                           "generalo en tu PC con `exportar_mt5.py`.")
            elif fuente == ETQ_MT5:
                todos = sorted(_simbolos_mt5())
                grupos, faltan = ui.agrupar_hallados(data.detectar_simbolos(todos))
                st.caption(f"El terminal informa {len(todos)} símbolos.")
                elegidos = []
                for familia, items in grupos.items():
                    opciones = [nombre for _, nombre in items]
                    por_defecto = [nombre for etiqueta, nombre in items if etiqueta == "oro"]
                    elegidos += st.multiselect(familia, opciones, por_defecto)
                if faltan:
                    st.caption("No detectados automáticamente: " + ", ".join(faltan))
                # Cualquier símbolo del servidor (escribí para buscar: US30, GER40, EURUSD...)
                elegidos += st.multiselect("Cualquier otro símbolo del servidor (escribí para buscar)",
                                           [s for s in todos if s not in elegidos], [])
                otros = st.text_input("O escribilos a mano (separados por coma)", "")
                simbolos = ui.unir_simbolos(elegidos, otros)
                tf = st.selectbox("Temporalidad", ["D1", "H4", "H1", "M30", "M15", "M5", "M1"], index=2)
                c1, c2 = st.columns(2)
                desde = c1.date_input("Desde", date(2020, 1, 1))
                hasta = c2.date_input("Hasta", date.today())
                if desde >= hasta:
                    st.error("La fecha 'desde' debe ser anterior a 'hasta'.")
                elif not simbolos:
                    st.info("Elegí al menos un símbolo.")
                else:
                    barra = st.progress(0.0)
                    for k, simbolo in enumerate(simbolos):
                        try:
                            d_, sp_, vacios = _mt5(simbolo, tf, str(desde), str(hasta))
                            datos[simbolo], specs[simbolo] = d_, sp_
                            if vacios:
                                avisos_datos.append(f"{simbolo}: {vacios} tramos de descarga vinieron vacíos.")
                            if len(d_) and (d_.index[0].date() - desde).days > 30:
                                avisos_datos.append(
                                    f"{simbolo}: pediste desde {desde:%d/%m/%Y}, pero MT5 solo tiene historia {tf} desde "
                                    f"{d_.index[0]:%d/%m/%Y}. El servidor o el terminal no guardan más atrás: por eso "
                                    "'Recortar período' muestra otra fecha. Para más historia usá una temporalidad mayor "
                                    "(H1 o D1) o subí 'Max bars in chart' en MT5 (Herramientas → Opciones → Gráficos).")
                        except data.ErrorDatos as e:
                            avisos_datos.append(f"{simbolo}: {e}")
                        barra.progress((k + 1) / len(simbolos))
                    barra.empty()
            elif fuente == ETQ_CSV:
                archivos = st.file_uploader("Archivos CSV (uno por símbolo)", type=["csv", "txt"],
                                            accept_multiple_files=True)
                point = st.number_input("Point del símbolo (solo si el CSV no trae columna 'point')",
                                        value=0.01, format="%.5f")
                for archivo in archivos or []:
                    datos[ui.simbolo_desde_archivo(archivo.name)] = _csv(archivo.getvalue(), point)
            else:
                tend = st.slider("Tendencia (0 = azar puro)", 0.0, 1.0, 0.0, 0.1)
                n_series = st.slider("Cantidad de series de demo", 1, 4, 1)
                for k in range(n_series):
                    datos[f"SINT{k + 1}"] = _sintetico(30000, tend, k + 1)
        except (data.ErrorDatos, ValueError, KeyError) as e:
            st.error(str(e))
            datos, specs = {}, {}

        if datos:
            regla = st.selectbox("Remuestrear a", ["No", "15min", "30min", "1h", "4h", "1D"])
            if regla != "No":
                datos = {s: data.resamplear(d_, regla) for s, d_ in datos.items()}
            primero = next(iter(datos.values()))
            rango = st.date_input("Recortar período", (primero.index[0].date(), primero.index[-1].date()))
            if isinstance(rango, tuple) and len(rango) == 2:
                datos = {s: d_.loc[str(rango[0]):str(rango[1])] for s, d_ in datos.items()}
            datos = {s: d_ for s, d_ in datos.items() if len(d_)}

    with st.expander("2. Señal y gestión", expanded=True):
        c1, c2 = st.columns(2)
        ema_c = c1.number_input("EMA corta", 2, 500, 13)
        ema_l = c2.number_input("EMA larga", 3, 1000, 34)
        direccion = DIRECCIONES[st.selectbox("Dirección", list(DIRECCIONES))]
        sl_modo = st.selectbox("SL en", [SL_ATR, SL_PCT, SL_USD])
        if sl_modo == SL_USD:
            sl_usd = st.number_input("Stop Loss (US$ por operación)", 1.0, 10_000_000.0, 100.0, 10.0)
            tp_modo = st.radio("Take Profit en", [TP_RR, TP_USD], horizontal=True)
            if tp_modo == TP_USD:
                tp_usd = st.number_input("Take Profit (US$ por operación)", 1.0, 10_000_000.0, 200.0, 10.0)
                rr = tp_usd / sl_usd
                st.caption(f"Relación TP/SL: {rr:.2f}")
            else:
                rr = st.number_input("RR (1:x)", 1.0, 10.0, 2.0, 0.5)
            sl_valor = sl_usd
        else:
            sl_usd = tp_usd = 0.0
            tp_modo = TP_RR
            rr = st.number_input("RR (1:x)", 1.0, 10.0, 2.0, 0.5)
            sl_valor = st.number_input("Valor del SL", 0.01, 100.0, 1.5 if sl_modo == SL_ATR else 0.5, 0.1)
        atr_per = st.number_input("Período ATR", 2, 200, 14)

    with st.expander("3. Lotaje y dinero", expanded=False):
        lotes = st.number_input("Lotes", 0.01, 1000.0, 0.10, 0.01, format="%.2f")
        tick_size_man, tick_value_man = 0.01, 1.0
        if any(s not in specs for s in datos):
            tick_size_man = st.number_input("tick_size del símbolo", 0.00001, value=0.01, format="%.5f")
            tick_value_man = st.number_input("tick_value (US$ por tick con 1 lote)", 0.00001, value=1.0, format="%.5f")
            st.caption("Sin MT5 directo no se conocen estos datos: los valores por defecto son los del oro. "
                       "En MT5: clic derecho en el símbolo → Especificación.")
        else:
            st.caption("tick_size, tick_value y el paso de lote se leen de cada símbolo en MT5.")
        comision = st.number_input("Comisión por lote (US$)", 0.0, value=0.0)
        capital = st.number_input("Capital de la cuenta (US$)", 0.0, 100_000_000.0, 100_000.0, 1000.0,
                                  help="Se usa en la conclusión final para estimar el riesgo de tocar la pérdida máxima.")
        limite_pct = st.number_input("Pérdida máxima permitida (% del capital)", 0.0, 100.0, 10.0, 1.0,
                                     help="En FTMO la pérdida máxima total es del 10% del capital inicial.")

    with st.expander("4. Costos", expanded=False):
        spread = SPREADS[st.selectbox("Spread", list(SPREADS))]
        spread_fijo = st.number_input("Spread fijo (unid. de precio)", 0.0, value=0.3) if spread == "fijo" else 0.0
        costo_extra = st.number_input("Costo extra por operación (unid. de precio)", 0.0, value=0.0)

    with st.expander("5. Filtros (independientes)", expanded=False):
        sma_on = st.checkbox("Filtro SMA")
        if sma_on:
            sma_per = st.number_input("Período SMA", 2, 1000, 200)
            sma_dist = st.number_input("Distancia mínima al cierre (múltiplos de ATR, 0 = sin)", 0.0, value=0.0, step=0.1)
            sma_pend = st.number_input("Pendiente a favor: N velas (0 = sin)", 0, 500, 0)
        else:
            sma_per, sma_dist, sma_pend = 200, 0.0, 0
        adx_on = st.checkbox("Filtro ADX")
        if adx_on:
            adx_per = st.number_input("Período ADX", 2, 100, 14)
            adx_min = st.number_input("ADX mínimo", 0.0, 100.0, 20.0)
            adx_max = st.number_input("ADX máximo (0 = sin)", 0.0, 100.0, 0.0)
            adx_cre = st.number_input("ADX creciente: N velas (0 = sin)", 0, 200, 0)
        else:
            adx_per, adx_min, adx_max, adx_cre = 14, 20.0, 0.0, 0
        atr_on = st.checkbox("Filtro ATR")
        if atr_on:
            atr_min = st.number_input("ATR mínimo (% del precio, 0 = sin)", 0.0, value=0.0, step=0.01, format="%.3f")
            atr_max = st.number_input("ATR máximo (% del precio, 0 = sin)", 0.0, value=0.0, step=0.01, format="%.3f")
            rel_on = st.checkbox("Modo relativo (ATR / promedio de N velas)")
            if rel_on:
                rel_n = st.number_input("N velas", 5, 500, 100)
                rel_min = st.number_input("Relativo mínimo", 0.0, value=0.8, step=0.1)
                rel_max = st.number_input("Relativo máximo", 0.0, value=2.0, step=0.1)
            else:
                rel_n, rel_min, rel_max = 0, 0.0, 0.0
        else:
            atr_min = atr_max = rel_n = rel_min = rel_max = 0
        ses_on = st.checkbox("Filtro de sesión")
        if ses_on:
            sesiones = st.multiselect("Sesiones permitidas", SESIONES, ["Londres", "Nueva York"])
            offset = st.number_input("Desfase del servidor en invierno (GMT+2 → 2)", -12.0, 14.0, 2.0, 1.0)
            dst = st.checkbox("El servidor cambia de hora con EE.UU.", True)
            st.caption("Confirmá el desfase midiéndolo con el mercado abierto. Los horarios de "
                       "las sesiones se mueven con el horario de verano de cada plaza. En BTC el "
                       "filtro se desactiva solo (opera 24/7).")
        else:
            sesiones, offset, dst = ["Londres", "Nueva York"], None, True

    with st.expander("6. Control de sobreajuste", expanded=False):
        oos = st.slider("Out-of-sample reservado (%)", 10, 50, 30)
        azar_n = st.number_input("Repeticiones del azar", 20, 500, 100, 20)


def params_dinero(simbolo: str) -> dict:
    """tick_size, tick_value y límites de lote del símbolo (de MT5 si hay conexión; si no, los cargados a mano)."""
    sp = specs.get(simbolo)
    if sp:
        return {"tick_size": float(sp["tick_size"]), "tick_value": float(sp["tick_value"]),
                "vol": (sp["vol_min"], sp["vol_max"], sp["vol_step"])}
    return {"tick_size": float(tick_size_man), "tick_value": float(tick_value_man), "vol": (0.01, 1000.0, 0.01)}


def construir_config(simbolo: str = None) -> eng.Config:
    simbolo = simbolo or activo
    p = params_dinero(simbolo)
    try:
        met.validar_lotaje(lotes, *p["vol"])
    except ValueError as e:
        raise ValueError(f"{simbolo}: {e}")
    if sl_modo == SL_USD:
        # dólares -> distancia de precio: US$ / (US$ por cada 1,00 de precio con este lote)
        vpu = met.valor_por_unidad(p["tick_size"], p["tick_value"], lotes)
        modo, valor = "precio", float(sl_usd) / vpu
    else:
        modo, valor = ("pct" if sl_modo == SL_PCT else "atr"), float(sl_valor)
    return eng.Config(
        ema_corta=int(ema_c), ema_larga=int(ema_l), rr=float(rr),
        sl_modo=modo, sl_valor=valor, atr_periodo=int(atr_per),
        direccion=direccion, spread=spread, spread_fijo=float(spread_fijo), costo_extra=float(costo_extra),
        sma_activo=sma_on, sma_periodo=int(sma_per), sma_dist_min_atr=float(sma_dist), sma_pendiente_n=int(sma_pend),
        adx_activo=adx_on, adx_periodo=int(adx_per), adx_min=float(adx_min),
        adx_max=float(adx_max) or None, adx_creciente_n=int(adx_cre),
        atr_activo=atr_on, atr_unidad="pct", atr_min=float(atr_min) or None, atr_max=float(atr_max) or None,
        atr_rel_n=int(rel_n), atr_rel_min=float(rel_min) or None, atr_rel_max=float(rel_max) or None,
        sesion_activo=ses_on, sesiones=tuple(sesiones),
        servidor_offset_horas=offset if ses_on else None, servidor_dst_eeuu=dst)


# ------------------------------------------------------------------ cuerpo
def html(x: str) -> None:
    st.html(x)


def tarjeta_html(titulo: str, cuerpo: str, nota: str = "", derecha: str = "") -> None:
    html(vis.tarjeta(titulo, cuerpo, nota, derecha))


if not datos:
    html(vis.barra_superior("Backtester: cruce de EMAs con filtros",
                            "Medí si una idea tiene ventaja demostrable, no cuál combinación gana.", []))
    html(vis.tarjeta("Para empezar", "<div class='note' style='font-size:.9rem'>Cargá datos en la barra lateral. "
                     "Para probar la interfaz sin datos reales, elegí <b>Datos sintéticos (demo)</b>.</div>"))
    st.stop()

for av in avisos_datos:
    st.warning(av)

if len(datos) > 1:
    activo = st.selectbox("Símbolo para el análisis detallado", list(datos))
    recortar = st.checkbox("Al comparar, recortar al período común", True)
else:
    activo, recortar = next(iter(datos)), True
df, spec = datos[activo], specs.get(activo)

cal = data.calidad(df)
html(vis.barra_superior(
    "Backtester: cruce de EMAs con filtros",
    "Medí si una idea tiene ventaja demostrable, no cuál combinación gana: con muchas pruebas, "
    "un buen resultado puede ser azar.",
    [("Símbolo", activo), ("Pruebas en la sesión", st.session_state.contador.n)]))
k1, k2, k3, k4 = st.columns(4)
with k1:
    html(vis.kpi("Velas analizadas", vis.n(cal["velas"], 0), "después de recortar y remuestrear", vis.VIOLETA))
with k2:
    html(vis.kpi("Rango real", cal["primera"][:10], "hasta " + cal["ultima"][:10], vis.INDIGO))
with k3:
    html(vis.kpi("Spread en 0", f"{vis.n(cal['spread_cero_pct'], 1)}%", "de las velas (spread no registrado)",
                 vis.ROSA if cal["spread_cero_pct"] > 20 else vis.INDIGO))
with k4:
    html(vis.kpi("Mayor hueco", f"{vis.n(cal['mayor_hueco_dias'], 1)} d", f"{cal['huecos_mas_de_4d']} huecos de más de 4 días",
                 vis.ROSA if cal["huecos_mas_de_4d"] else vis.INDIGO))
if cal["duplicadas"] or cal["con_nan"]:
    st.warning(f"Calidad de datos: {cal['duplicadas']} velas duplicadas y {cal['con_nan']} con NaN.")

if sl_modo == SL_USD:
    try:
        conv = []
        for s_ in list(datos)[:8]:
            c_ = construir_config(s_)
            conv.append((s_, f"SL {vis.n(c_.sl_valor, 5 if c_.sl_valor < 1 else 2)} · TP {vis.n(c_.sl_valor * c_.rr, 5 if c_.sl_valor < 1 else 2)}"))
        st.write("")
        html(vis.tarjeta(f"SL de US${vis.n(sl_usd)} y TP de US${vis.n(sl_usd * rr)} con {vis.n(lotes)} lotes: en puntos de precio",
                         vis.chips(conv), "Se recalcula por símbolo con su tick_size y tick_value. Con otro lote cambia la distancia, "
                         "y por lo tanto las operaciones."))
    except ValueError as e:
        st.error(str(e))

with st.expander("📖 Guía de cada campo"):
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "guia_campos.md"), encoding="utf-8") as f_:
            st.markdown(f_.read())
    except OSError:
        st.caption("No se encontró guia_campos.md junto a la app.")

st.write("")
b1, b2, b3 = st.columns(3)
correr = b1.button("Correr backtest", type="primary")
abl = b2.button("Modo ablación (cruce solo + cada filtro)")
comp = b3.button("Comparar símbolos", disabled=len(datos) < 2)

if correr:
    try:
        cfg = construir_config()
        with st.spinner("Calculando..."):
            st.session_state.res = (met.evaluar(df, cfg, oos / 100, int(azar_n), 42,
                                                st.session_state.contador), cfg, activo,
                                    {"lotes": float(lotes), "comision": float(comision), "capital": float(capital),
                                     "limite_pct": float(limite_pct), **params_dinero(activo)})
    except (ValueError, data.ErrorDatos) as e:
        st.error(str(e))

if comp:
    try:
        cfgs = {s: construir_config(s) for s in datos}
        with st.spinner("Comparando símbolos..."):
            st.session_state.comp = met.comparar_simbolos(
                datos, cfgs, oos / 100, int(azar_n), 42, st.session_state.contador, recortar)
    except (ValueError, data.ErrorDatos) as e:
        st.error(str(e))

if abl:
    try:
        cfg = construir_config()
        with st.spinner("Corriendo la ablación..."):
            tabla_abl, omitidos = met.ablacion(df, cfg, oos_pct=oos / 100,
                                               azar_veces=min(int(azar_n), 100),
                                               contador=st.session_state.contador)
        st.write("")
        filas = []
        for nombre, fila in tabla_abl.iterrows():
            filas += [(f"{nombre} · todo", fila["exp_R"]), (f"{nombre} · OOS", fila["exp_R_OOS"], vis.VIOLETA)]
        tarjeta_html(f"Ablación de {activo}: expectativa en R", vis.barras_divergentes(filas),
                     "Los filtros se miden con parámetros fijos (SMA 200, ADX mínimo 20, ATR relativo de 100 "
                     "velas entre 0,8 y 2,0). El aporte es el de esos valores, no el del filtro en general.")
        with st.expander("Ver tabla de la ablación"):
            html(vis.tabla_df(tabla_abl, dec=3, nombre_indice="Configuración"))
        if omitidos:
            st.warning(f"Omitidos por falta de desfase del servidor: {', '.join(omitidos)}.")
    except (ValueError, data.ErrorDatos) as e:
        st.error(str(e))

if st.session_state.comp is not None:
    tabla_c, notas_c = st.session_state.comp
    pos = int(((tabla_c["exp_R"] > 0) & (tabla_c["exp_R_OOS"] > 0)).sum())
    filas = []
    for simbolo, fila in tabla_c.iterrows():
        filas += [(f"{simbolo} · todo", fila["exp_R"]), (f"{simbolo} · OOS", fila["exp_R_OOS"], vis.VIOLETA)]
    st.write("")
    cc1, cc2 = st.columns([3, 2])
    with cc1:
        tarjeta_html("Comparación de símbolos (mismos parámetros en todos)", vis.barras_divergentes(filas),
                     "Expectativa en R por operación. Se compara en R, no en dinero: el valor por tick difiere entre activos.")
    with cc2:
        html(vis.insight(
            "Lectura de robustez",
            f"Expectativa positiva en el total y en out-of-sample en <b>{pos} de {len(tabla_c)}</b> símbolos.<br><br>"
            "Sirve para ver si la idea se sostiene en varios mercados, no para elegir el ganador: al probar varios "
            "activos es esperable que alguno salga bien por azar."))
    for n_ in dict.fromkeys(notas_c):
        st.caption("• " + n_)
    with st.expander("Ver tabla de la comparación"):
        html(vis.tabla_df(tabla_c, dec=3, nombre_indice="Símbolo"))

if st.session_state.res is None:
    st.stop()

# ------------------------------------------------------------------ resultado
if len(st.session_state.res) != 4:      # resultado de una versión anterior: se descarta
    st.session_state.res = None
    st.stop()
r, cfg_usada, act_res, pdin = st.session_state.res
t = r["tabla"]
tt, ti, to = t.loc["Todo"], t.loc["In-sample"], t.loc["Out-of-sample"]
tr = r["trades"]
res = tr[tr["res"].isin(["TP", "SL"])] if len(tr) else tr
dinero = None

st.write("")
html(vis.barra_superior(f"Resultado de {act_res}", f"Prueba n.º {r['prueba']} de esta sesión",
                        [("In-sample", f"{int(ti['resueltas'])} op."), ("Out-of-sample", f"{int(to['resueltas'])} op.")]))
if act_res != activo:
    st.warning(f"Este resultado es de {act_res}; el símbolo seleccionado ahora es {activo}. "
               "Volvé a correr el backtest para actualizarlo.")
for av in r["avisos"]:
    st.warning(av)
_dist_med = float(r["P"].dist.mean())
if _dist_med > 0 and float(r["P"].sp.mean()) / _dist_med > 0.2:
    st.warning(f"El spread promedio equivale al {vis.n(100 * float(r['P'].sp.mean()) / _dist_med, 0)}% del SL: "
               "con un stop tan corto el costo pesa mucho en el resultado.")

c1, c2, c3, c4 = st.columns(4)
with c1:
    html(vis.kpi("Expectativa", vis.n(tt["exp_R"], 2, True) + " R", "por operación resuelta", vis.tono(tt["exp_R"])))
with c2:
    html(vis.kpi("Operaciones resueltas", vis.n(tt["resueltas"], 0),
                 f"{int(tt['TP'])} TP · {int(tt['SL'])} SL · {int(tt['abiertas'])} abiertas", vis.VIOLETA))
with c3:
    html(vis.kpi("R total", vis.n(tt["R_total"], 1, True), "suma de resultados", vis.tono(tt["R_total"])))
with c4:
    html(vis.kpi("Máx. drawdown", vis.n(tt["maxDD_R"], 1) + " R", f"racha máxima de SL: {int(tt['racha_SL'])}", vis.ROSA))

st.write("")
if len(res):
    g1, g2 = st.columns([2, 1])
    acumulado = res["R"].cumsum().tolist()
    pos_oos = int((res["i"] < r["corte"]).sum())
    with g1:
        tarjeta_html("Curva de equity (R)",
                     vis.curva_equity(acumulado, str(res["fecha_entrada"].iloc[0])[:10],
                                      str(res["fecha_entrada"].iloc[-1])[:10], pos_oos),
                     "La zona rosada es el out-of-sample: lo que el modelo no vio al ajustarse.", "acumulado")
    with g2:
        html(vis.tarjeta("Mejor que el azar (out-of-sample)",
                         vis.medidor(to["mejor_que_%azar"], "percentil frente a entradas al azar",
                                     "cerca de 50% = la señal no se distingue de entrar al azar"),
                         "Compara la expectativa con la de entradas aleatorias bajo las mismas reglas."))

st.write("")
anillos = [("Todo", "Todo el período", tt), ("In-sample", "In-sample", ti), ("Out-of-sample", "Out-of-sample", to)]
cols = st.columns(4)
for k, (clave, titulo, fila) in enumerate(anillos):
    with cols[k]:
        html(vis.anillo(fila["%TP"], titulo,
                        f"{int(fila['resueltas'])} operaciones<br>expectativa {vis.n(fila['exp_R'], 2, True)} R<br>"
                        f"equilibrio {vis.n(fila['%equilibrio'], 1)}%", fila["%equilibrio"], uid=f"r{k}"))
with cols[3]:
    html(vis.tarjeta("Cómo leer los anillos", "<div class='note' style='font-size:.8rem'>"
                     "El anillo es el <b>% de operaciones que llegan al TP</b>. La rayita negra marca el "
                     "<b>% de equilibrio</b> (el mínimo para no perder con ese RR y costos): si el anillo pasa la "
                     "rayita, la expectativa es positiva.</div>"))

st.write("")
if len(res):
    h1, h2 = st.columns([3, 2])
    with h1:
        anio = r["por_anio"]
        tarjeta_html("Expectativa por año (R)",
                     vis.barras_verticales([(int(a), f_["exp_R"], f"{int(f_['resueltas'])} op.") for a, f_ in anio.iterrows()]),
                     "Un año con pocas operaciones pesa poco: mirá el número debajo de cada barra.")
    with h2:
        cuerpo = vis.embudo([("Cruces detectados", tt["cruces"]), ("Tomados", tt["tomados"]),
                             ("Resueltas", tt["resueltas"]), ("Llegaron a TP", tt["TP"])])
        if r["descartes"]:
            cuerpo += "<div class='note'>Descartadas por filtro:</div>" + vis.chips(list(r["descartes"].items()))
        tarjeta_html("Embudo de señales", cuerpo,
                     f"{int(tt['ignoradas'])} señales ignoradas por haber ya una operación abierta.")

    # ------------------------------------------------------------- dinero
    st.write("")
    lotes_u, tick_size, tick_value, comision_u = pdin["lotes"], pdin["tick_size"], pdin["tick_value"], pdin["comision"]
    if abs(lotes - lotes_u) > 1e-9:
        st.info(f"Estos valores en dinero son de la corrida con {lotes_u} lotes. Cambiaste el lote en la barra "
                "lateral: volvé a correr para actualizar.")
    try:
        met.validar_lotaje(lotes_u, *pdin["vol"])
        dinero = met.resumen_dinero(tr, tick_size, tick_value, lotes_u, comision_u)
        m1, m2, m3, m4 = st.columns(4)
        with m1:
            html(vis.kpi("Resultado neto", vis.n(dinero["neto"], 2, True), f"con {vis.n(lotes_u)} lotes, después de comisiones", vis.tono(dinero["neto"])))
        with m2:
            html(vis.kpi("Ganancia media (TP)", vis.n(dinero["ganancia_media_TP"], 2, True), "por operación ganadora", vis.INDIGO))
        with m3:
            html(vis.kpi("Pérdida media (SL)", vis.n(dinero["perdida_media_SL"], 2, True), "por operación perdedora", vis.ROSA))
        with m4:
            html(vis.kpi("Máx. drawdown", vis.n(dinero["max_drawdown"], 2), f"riesgo medio por operación: {vis.n(dinero['riesgo_medio_por_operacion'], 2)}", vis.ROSA))
        _ex = met.extremos_diarios(tr, r["P"].indice, tick_size, tick_value, lotes_u, comision_u)
        if _ex:
            d1, d2 = st.columns(2)
            with d1:
                html(vis.kpi("Máx. drawdown diario", vis.n(min(_ex["peor_usd"], 0), 2),
                             f"{_ex['peor_dia']:%d/%m/%Y} · {_ex['peor_ops']} op. · {vis.n(_ex['peor_R'], 1, True)} R "
                             "(peor día, operaciones cerradas)", vis.ROSA))
            with d2:
                html(vis.kpi("Máx. ganancia diaria (TP)", vis.n(max(_ex["mejor_usd"], 0), 2, True),
                             f"{_ex['mejor_dia']:%d/%m/%Y} · {_ex['mejor_ops']} op. · {vis.n(_ex['mejor_R'], 1, True)} R "
                             "(mejor día)", vis.INDIGO))
        st.caption(f"Fórmula: (diferencia de precio / {tick_size}) × {tick_value} × {lotes_u} lotes "
                   f"= {met.valor_por_unidad(tick_size, tick_value, lotes_u):.2f} por cada 1,00 de precio. "
                   "Valores teóricos: el slippage y los gaps pueden hacer que una pérdida real supere la calculada.")
    except ValueError as e:
        st.error(str(e))

# ------------------------------------------------------------- frecuencia
if len(res):
    st.write("")
    html(vis.titulo_seccion("Frecuencia de operaciones", "Promedio de operaciones tomadas en el período analizado"))
    _fr = met.frecuencia(tr, r["P"].indice)
    f1, f2, f3, f4, f5 = st.columns(5)
    with f1:
        html(vis.kpi("Por día", vis.n(_fr["por_dia"], 2), f"promedio por día con mercado ({_fr.get('dias_mercado', 0)} días)", vis.INDIGO))
    with f2:
        html(vis.kpi("Por semana", vis.n(_fr["por_semana"], 1), "promedio por semana calendario", vis.VIOLETA))
    with f3:
        html(vis.kpi("Por mes", vis.n(_fr["por_mes"], 1), "promedio por mes calendario", vis.ROSA))
    with f4:
        html(vis.kpi("Máx. en un día", str(_fr["max_dia"]), f"operaba en {_fr['dias_con_op']} días del período", vis.AZUL))
    with f5:
        _sub = (f"entre el {_fr['sin_op_desde']:%d/%m/%Y} y el {_fr['sin_op_hasta']:%d/%m/%Y}"
                if _fr["sin_op_desde"] is not None else "sin lapsos")
        html(vis.kpi("Mayor lapso sin operar", f"{_fr['max_sin_op']} d", _sub, vis.MAGENTA))
    st.caption(f"Total: {_fr['n']} operaciones tomadas (incluye las que no llegaron a TP ni SL). "
               "Con pocas operaciones por mes, los porcentajes tardan más en volverse confiables.")

# ------------------------------------------------------------- rachas
if len(res):
    st.write("")
    html(vis.titulo_seccion("Rachas máximas", "Las 5 series más largas de TP seguidos y de SL seguidos en el período"))
    _rach = met.rachas(tr, r["P"].indice, 5)
    _usd = dinero["riesgo_medio_por_operacion"] if dinero else None
    cr1, cr2 = st.columns(2)
    for _col, _k, _tit, _nota in ((cr1, "TP", "Ganadoras seguidas (TP)", "Mejor racha positiva."),
                                  (cr2, "SL", "Perdedoras seguidas (SL)", "Sirve para dimensionar el peor tramo que habrías tenido que aguantar.")):
        with _col:
            _filas = [[f"{i}°", str(x["largo"]), x["desde"].strftime("%d/%m/%Y"), x["hasta"].strftime("%d/%m/%Y"),
                       vis.n(x["R"], 1, True) + " R" + (f" (≈ {vis.n(x['R'] * _usd, 0, True)} US$)" if _usd else "")]
                      for i, x in enumerate(_rach[_k], 1)]
            tarjeta_html(_tit, vis.tabla_html(["#", "Operaciones", "Desde", "Hasta", "Resultado"], _filas) if _filas
                         else "<div class='note'>Sin operaciones de este tipo.</div>", _nota)

# ------------------------------------------------------------- lectura
st.write("")
lineas = []
for nombre, fila in (("in-sample", ti), ("out-of-sample", to)):
    lineas.append(f"expectativa {'positiva' if fila['exp_R'] > 0 else 'negativa o nula'} en {nombre} "
                  f"({vis.n(fila['exp_R'], 2, True)} R, {int(fila['resueltas'])} operaciones)")
aviso_muestra = ("<br><br>La muestra out-of-sample es chica: tomá el resultado con cautela."
                 if to["resueltas"] < 100 else "")
html(vis.insight(
    "Lectura del resultado",
    "Hay " + " y ".join(lineas) + f". Frente al azar, el out-of-sample quedó en el percentil "
    f"<b>{vis.n(to['mejor_que_%azar'], 0)}</b>." + aviso_muestra +
    f"<br><br>Llevás <b>{st.session_state.contador.n}</b> pruebas en esta sesión: cuantas más probás, "
    "más probable es que alguna salga bien solo por azar. Esto no demuestra una ventaja por sí solo."))

# ------------------------------------------------------------- conclusión final
st.write("")
meses_datos = max((r["P"].indice[-1] - r["P"].indice[0]).days / 30.44, 0.1)
usd_R = dinero["riesgo_medio_por_operacion"] if dinero else None
veredicto = vd.evaluar_veredicto(r, cfg_usada, meses_datos, usd_R, pdin.get("capital", 0.0),
                                 pdin.get("limite_pct", 10.0), st.session_state.contador.n)
sl_usd_u = tp_usd_u = 0.0
if cfg_usada.sl_modo == "precio":
    sl_usd_u = cfg_usada.sl_valor * met.valor_por_unidad(pdin["tick_size"], pdin["tick_value"], pdin["lotes"])
    tp_usd_u = sl_usd_u * cfg_usada.rr
_tf = globals().get("tf")
tf_txt = regla if regla != "No" else (_tf or "")
relato = vd.describir(cfg_usada, act_res, tf_txt, r["P"].indice[0], r["P"].indice[-1], meses_datos, pdin["lotes"],
                      dinero["neto"] if dinero else None, int(tt["resueltas"]), int(tt["TP"]), int(tt["SL"]),
                      float(tt["exp_R"]) if tt["exp_R"] == tt["exp_R"] else 0.0,
                      dinero["max_drawdown"] if dinero else None, sl_usd_u, tp_usd_u)
html(vis.titulo_seccion("Conclusión final", "Qué habría pasado, si vale la pena intentarla y con qué probabilidad"))
html(vis.tarjeta("Qué habría pasado", f'<div style="font-size:.95rem;line-height:1.6;color:{vis.TEXTO}">{relato}</div>',
                 "Resultado teórico sobre datos pasados: no incluye slippage ni gaps."))
st.write("")
html(vis.veredicto_caja("Veredicto", veredicto["titulo"],
                        f"<div>{veredicto['siguiente_paso']}</div>"
                        f"<div style='margin-top:8px;opacity:.85;font-size:.8rem'>Puntaje: {veredicto['puntos']} de "
                        f"{veredicto['tope']} (los criterios de abajo, sin contar la muestra).</div>", veredicto["nivel"]))
st.write("")
v1, v2 = st.columns([1, 1])
with v1:
    filas_c = [[vd.SIMBOLO[e_], nombre, det] for e_, nombre, det in veredicto["checks"]]
    html(vis.tarjeta("Criterios del veredicto", vis.tabla_html(
        ["", "Criterio", "Resultado"], filas_c, izq=(1, 2),
        clase=lambda i, j: ("pos" if filas_c[i][0] == "✓" else "neg" if filas_c[i][0] == "✕" else None) if j == 0 else None),
        "✓ cumple · ! con reservas · ✕ no cumple."))
with v2:
    por_h = {f["meses"]: f for f in veredicto["proy_total"]}
    por_o = {f["meses"]: f for f in veredicto["proy_oos"]}
    nombres_h = {1: "1 mes", 3: "3 meses", 6: "6 meses", 12: "1 año"}
    mon = lambda x: (vis.n(x * usd_R, 0, True) if usd_R else vis.n(x, 1, True) + " R")
    filas_p = []
    for h_ in vd.HORIZONTES:
        if h_ not in por_h:
            continue
        ft, fo = por_h[h_], por_o.get(h_)
        cons = fo or ft                                 # el escenario conservador manda si existe
        filas_p.append([nombres_h[h_], f"~{ft['n']}", f"{vis.n(100 * ft['p_ganar'], 0)}%",
                        f"{vis.n(100 * fo['p_ganar'], 0)}%" if fo else "–",
                        f"{mon(cons['R_mediana'])} ({mon(cons['R_p5'])} a {mon(cons['R_p95'])})",
                        f"{vis.n(100 * cons['p_limite'], 0)}%" if cons["p_limite"] is not None else "–"])
    def _cls(i, j):
        if j in (2, 3) and filas_p[i][j] != "–":
            x = float(filas_p[i][j].rstrip("%").replace(",", "."))
            return "pos" if x >= 70 else "neg" if x <= 50 else None
        return None
    html(vis.tarjeta("Probabilidad de terminar en ganancia", vis.tabla_html(
        ["Horizonte", "Operaciones", "Con todo el historial", "Solo out-of-sample", "Resultado típico (rango 90%)",
         "Toca la pérdida máx."], filas_p, clase=_cls),
        f"Frecuencia observada: ~{vis.n(veredicto['tasa_mes'], 1)} operaciones por mes. El resultado típico y el riesgo usan el "
        "escenario más conservador disponible (out-of-sample si tiene operaciones suficientes)."))
for n_ in veredicto["notas"]:
    st.caption("• " + n_)
st.caption("Estimación estadística (simulación Monte Carlo con una probabilidad de acierto incierta, según las operaciones "
           "observadas). Supone que el futuro se parece al pasado y que las operaciones son independientes. No es una "
           "garantía: empezá siempre en demo.")

st.write("")
with st.expander("Ver tabla completa de resultados"):
    html(vis.tabla_df(t[COLS_TABLA], dec=2, nombre_indice="Tramo"))
    st.caption("In-sample y out-of-sample se muestran siempre aparte. Si ajustás parámetros mirando el "
               "out-of-sample, deja de ser out-of-sample.")
if len(res):
    with st.expander("Ver operaciones"):
        _d = 5 if float(tr["entrada"].abs().median()) < 10 else 2      # forex: 5 decimales; oro e índices: 2
        html(vis.tabla_df(tr.drop(columns=["i", "salida"]), decs={c: _d for c in ("entrada", "sl", "tp", "dist")},
                          nombre_indice="n.º"))
        st.download_button("Descargar operaciones (CSV)", tr.to_csv(index=False).encode("utf-8"),
                           "operaciones.csv", "text/csv")

with st.expander("Supuestos y limitaciones"):
    st.markdown(
        "- Entrada al cierre de la vela del cruce; fills exactos en SL/TP, sin slippage ni gaps.\n"
        "- Velas OHLC, no ticks: si una vela toca SL y TP, se cuenta SL y como ambigua.\n"
        "- El spread es el de cierre de cada vela; en velas viejas suele venir en 0.\n"
        "- Una cuenta demo puede diferir en spread y ejecución. El Strategy Tester de MT5 con "
        "ticks reales es la validación final.\n"
        "- En índices hay gaps de apertura y pausas diarias que el backtest no modela.\n"
        "- Resultados pasados no garantizan resultados futuros.")
