"""Interfaz Streamlit del backtester de cruce de EMAs con filtros opcionales.

Usa solo los módulos existentes (data, engine, metrics). No toca app.py ni los bots.
Online (Render) funciona con CSV exportado de MT5 o datos sintéticos; la conexión
directa a MT5 solo aparece si la librería MetaTrader5 está instalada (Windows, local).
"""
import io
from datetime import date

import pandas as pd
import streamlit as st

import data
import engine as eng
import metrics as met

st.set_page_config(page_title="Backtester cruce de EMAs", layout="wide")

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


@st.cache_data(show_spinner=False)
def _csv(contenido: bytes, point: float) -> pd.DataFrame:
    return data.cargar_csv(io.BytesIO(contenido), point)


@st.cache_data(show_spinner=False)
def _sintetico(n: int, tendencia: float, semilla: int) -> pd.DataFrame:
    return data.sintetico(n=n, tendencia=tendencia, seed=semilla)


@st.cache_data(show_spinner="Descargando de MT5 (por tramos)...")
def _mt5(simbolo: str, tf: str, desde: str, hasta: str):
    return data.cargar_mt5(simbolo, tf, desde, hasta)


st.session_state.setdefault("contador", met.ContadorPruebas())
st.session_state.setdefault("res", None)

st.title("Backtester: cruce de EMAs con filtros")
st.info("Herramienta para medir si una idea tiene ventaja demostrable, **no** para elegir "
        "la combinación ganadora. Con muchas pruebas, un buen resultado puede ser azar.")

# ------------------------------------------------------------------ datos
with st.sidebar:
    st.header("1. Datos")
    fuentes = ["CSV exportado de MT5", "Datos sintéticos (demo)"] + (["MT5 directo"] if MT5_OK else [])
    fuente = st.radio("Fuente", fuentes)
    spec, df, aviso_datos = None, None, None
    try:
        if fuente == "CSV exportado de MT5":
            archivo = st.file_uploader("Archivo CSV", type=["csv", "txt"])
            point = st.number_input("Point del símbolo (spread en puntos → precio)",
                                    value=0.01, format="%.5f")
            if archivo is not None:
                df = _csv(archivo.getvalue(), point)
        elif fuente == "Datos sintéticos (demo)":
            tend = st.slider("Tendencia (0 = azar puro)", 0.0, 1.0, 0.0, 0.1)
            df = _sintetico(30000, tend, 1)
        else:
            simbolo = st.text_input("Símbolo", "XAUUSD")
            tf = st.selectbox("Temporalidad", ["D1", "H4", "H1", "M30", "M15", "M5", "M1"], index=2)
            c1, c2 = st.columns(2)
            desde = c1.date_input("Desde", date(2020, 1, 1))
            hasta = c2.date_input("Hasta", date.today())
            if desde >= hasta:
                st.error("La fecha 'desde' debe ser anterior a 'hasta'.")
            else:
                df, spec, sin_datos = _mt5(simbolo, tf, str(desde), str(hasta))
                if sin_datos:
                    aviso_datos = f"{sin_datos} tramos de descarga vinieron vacíos."
    except (data.ErrorDatos, ValueError, KeyError) as e:
        st.error(str(e))
        df = None

    if df is not None:
        regla = st.selectbox("Remuestrear a", ["No", "15min", "30min", "1h", "4h", "1D"])
        if regla != "No":
            df = data.resamplear(df, regla)
        rango = st.date_input("Recortar período", (df.index[0].date(), df.index[-1].date()))
        if isinstance(rango, tuple) and len(rango) == 2:
            df = df.loc[str(rango[0]):str(rango[1])]

    st.header("2. Señal y gestión")
    c1, c2 = st.columns(2)
    ema_c = c1.number_input("EMA corta", 2, 500, 13)
    ema_l = c2.number_input("EMA larga", 3, 1000, 34)
    direccion = DIRECCIONES[st.selectbox("Dirección", list(DIRECCIONES))]
    rr = st.number_input("RR (1:x)", 1.0, 10.0, 2.0, 0.5)
    sl_modo = st.radio("SL en", ["Múltiplo de ATR", "% del precio"], horizontal=True)
    sl_valor = st.number_input("Valor del SL", 0.01, 100.0, 1.5 if sl_modo == "Múltiplo de ATR" else 0.5, 0.1)
    atr_per = st.number_input("Período ATR", 2, 200, 14)

    st.header("3. Costos")
    spread = SPREADS[st.selectbox("Spread", list(SPREADS))]
    spread_fijo = st.number_input("Spread fijo (unid. de precio)", 0.0, value=0.3) if spread == "fijo" else 0.0
    costo_extra = st.number_input("Costo extra por operación (unid. de precio)", 0.0, value=0.0)

    st.header("4. Filtros (independientes)")
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
                   "las sesiones se mueven con el horario de verano de cada plaza.")
    else:
        sesiones, offset, dst = ["Londres", "Nueva York"], None, True

    st.header("5. Control de sobreajuste")
    oos = st.slider("Out-of-sample reservado (%)", 10, 50, 30)
    azar_n = st.number_input("Repeticiones del azar", 20, 500, 100, 20)


def construir_config() -> eng.Config:
    pct = sl_modo == "% del precio"
    return eng.Config(
        ema_corta=int(ema_c), ema_larga=int(ema_l), rr=float(rr),
        sl_modo="pct" if pct else "atr", sl_valor=float(sl_valor), atr_periodo=int(atr_per),
        direccion=direccion, spread=spread, spread_fijo=float(spread_fijo), costo_extra=float(costo_extra),
        sma_activo=sma_on, sma_periodo=int(sma_per), sma_dist_min_atr=float(sma_dist), sma_pendiente_n=int(sma_pend),
        adx_activo=adx_on, adx_periodo=int(adx_per), adx_min=float(adx_min),
        adx_max=float(adx_max) or None, adx_creciente_n=int(adx_cre),
        atr_activo=atr_on, atr_unidad="pct", atr_min=float(atr_min) or None, atr_max=float(atr_max) or None,
        atr_rel_n=int(rel_n), atr_rel_min=float(rel_min) or None, atr_rel_max=float(rel_max) or None,
        sesion_activo=ses_on, sesiones=tuple(sesiones),
        servidor_offset_horas=offset if ses_on else None, servidor_dst_eeuu=dst)


# ------------------------------------------------------------------ cuerpo
if df is None or not len(df):
    st.write("Cargá datos en la barra lateral para empezar. Para probar la interfaz sin "
             "datos reales, elegí **Datos sintéticos (demo)**.")
    st.stop()

cal = data.calidad(df)
a, b, c, d = st.columns(4)
a.metric("Velas analizadas", f"{cal['velas']:,}")
b.metric("Rango real", f"{cal['primera'][:10]} → {cal['ultima'][:10]}")
c.metric("Spread en 0", f"{cal['spread_cero_pct']}%")
d.metric("Pruebas en la sesión", st.session_state.contador.n)
if aviso_datos:
    st.warning(aviso_datos)
if cal["duplicadas"] or cal["con_nan"]:
    st.warning(f"Calidad de datos: {cal['duplicadas']} velas duplicadas y {cal['con_nan']} con NaN.")

b1, b2 = st.columns(2)
correr = b1.button("Correr backtest", type="primary")
abl = b2.button("Modo ablación (cruce solo + cada filtro)")

if correr:
    try:
        cfg = construir_config()
        with st.spinner("Calculando..."):
            st.session_state.res = (met.evaluar(df, cfg, oos / 100, int(azar_n), 42,
                                                st.session_state.contador), cfg)
    except (ValueError, data.ErrorDatos) as e:
        st.error(str(e))

if abl:
    try:
        cfg = construir_config()
        with st.spinner("Corriendo la ablación..."):
            tabla_abl, omitidos = met.ablacion(df, cfg, oos_pct=oos / 100,
                                               azar_veces=min(int(azar_n), 100),
                                               contador=st.session_state.contador)
        st.subheader("Ablación")
        st.dataframe(tabla_abl.round(3), use_container_width=True)
        st.caption("Los filtros se miden con parámetros fijos (SMA 200, ADX mínimo 20, "
                   "ATR relativo de 100 velas entre 0,8 y 2,0). El aporte es el de esos valores, "
                   "no el del filtro en general.")
        if omitidos:
            st.warning(f"Omitidos por falta de desfase del servidor: {', '.join(omitidos)}.")
    except (ValueError, data.ErrorDatos) as e:
        st.error(str(e))

if st.session_state.res is None:
    st.stop()

r, cfg_usada = st.session_state.res
st.subheader(f"Resultado (prueba n.º {r['prueba']})")
for av in r["avisos"]:
    st.warning(av)
st.dataframe(r["tabla"][COLS_TABLA].round(3), use_container_width=True)
st.caption("In-sample y out-of-sample se muestran siempre aparte. Si ajustás parámetros "
           "mirando el out-of-sample, deja de ser out-of-sample. Un 'mejor que el azar' cercano "
           "a 50% significa que la señal no se distingue de entrar al azar.")
if r["descartes"]:
    st.write("Señales descartadas por filtro:", r["descartes"])

tr = r["trades"]
res = tr[tr["res"].isin(["TP", "SL"])] if len(tr) else tr
if len(res):
    st.subheader("Curva de equity (R)")
    st.line_chart(res.set_index("fecha_entrada")["R"].cumsum())
    st.subheader("Por año")
    st.dataframe(r["por_anio"].round(3), use_container_width=True)

    st.subheader("Resultados en dinero (teóricos)")
    c1, c2, c3, c4 = st.columns(4)
    lotes = c1.number_input("Lotes", 0.01, 100.0, 0.10, 0.01)
    tick_size = c2.number_input("tick_size", 0.00001, value=float(spec["tick_size"]) if spec else 0.01, format="%.5f")
    tick_value = c3.number_input("tick_value", 0.00001, value=float(spec["tick_value"]) if spec else 1.0, format="%.5f")
    comision = c4.number_input("Comisión por lote", 0.0, value=0.0)
    try:
        v = spec or {"vol_min": 0.01, "vol_max": 100.0, "vol_step": 0.01}
        met.validar_lotaje(lotes, v["vol_min"], v["vol_max"], v["vol_step"])
        dinero = met.resumen_dinero(tr, tick_size, tick_value, lotes, comision)
        st.caption(f"Fórmula: (diferencia de precio / {tick_size}) × {tick_value} × {lotes} lotes "
                   f"= {met.valor_por_unidad(tick_size, tick_value, lotes):.2f} por cada 1,00 de precio.")
        st.json({k: round(x, 2) if isinstance(x, float) else x for k, x in dinero.items()})
        st.caption("Valores teóricos: el slippage y los gaps pueden hacer que una pérdida real supere la calculada.")
    except ValueError as e:
        st.error(str(e))

    st.subheader("Operaciones")
    st.dataframe(tr, use_container_width=True)
    st.download_button("Descargar operaciones (CSV)", tr.to_csv(index=False).encode("utf-8"),
                       "operaciones.csv", "text/csv")

with st.expander("Supuestos y limitaciones"):
    st.markdown(
        "- Entrada al cierre de la vela del cruce; fills exactos en SL/TP, sin slippage ni gaps.\n"
        "- Velas OHLC, no ticks: si una vela toca SL y TP, se cuenta SL y como ambigua.\n"
        "- El spread es el de cierre de cada vela; en velas viejas suele venir en 0.\n"
        "- Una cuenta demo puede diferir en spread y ejecución. El Strategy Tester de MT5 con "
        "ticks reales es la validación final.\n"
        "- Resultados pasados no garantizan resultados futuros.")
