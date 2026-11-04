"""Interfaz Streamlit del backtester de cruce de medias (EMA o SMA) con filtros opcionales.

La misma pantalla sirve para dos paginas: la de EMA (app_backtest.py) y la de SMA (app_backtest_sma.py, que define
TIPO_MEDIA = "sma" antes de ejecutar este archivo). La de SMA suma el modo "precio cruza una sola media".

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

import numpy as np
import pandas as pd
import streamlit as st

import data
import engine as eng
import generar_bot as gb
import metrics as met
import ui_estilo as vis
import veredicto as vd
import ui_helpers as ui

TIPO = globals().get("TIPO_MEDIA", "ema")       # "sma" lo define app_backtest_sma.py antes de ejecutar este archivo
ES_SMA = TIPO == "sma"
MEDIA = TIPO.upper()                            # "EMA" o "SMA", para los textos
_PFX = "" if TIPO == "ema" else TIPO + "_"


class _Estado:
    """Estado de ESTA página: las dos páginas de backtester no comparten resultados. El contador de pruebas sí es único."""
    def _k(self, k):
        return k if k == "contador" else _PFX + k

    def setdefault(self, k, v):
        return st.session_state.setdefault(self._k(k), v)

    def get(self, k, d=None):
        return st.session_state.get(self._k(k), d)

    def __getattr__(self, k):
        return st.session_state[self._k(k)]

    def __setattr__(self, k, v):
        st.session_state[self._k(k)] = v


estado = _Estado()

try:
    import MetaTrader5  # noqa: F401
    MT5_OK = True
except ImportError:
    MT5_OK = False

SPREADS = {"Spread de la vela": "vela", "Ceros → mediana": "mediana",
           "Valor fijo": "fijo", "Sin spread": "ninguno"}
DIRECCIONES = {"Largos y cortos": "ambas", "Solo largos": "largos", "Solo cortos": "cortos"}
ALTO_FILA = 400          # alto mínimo (px) de las tarjetas «Expectativa por año» y «Embudo», para que queden iguales
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


def _hoy() -> date:
    """El día en que se ejecuta (hora de Argentina: en Render el reloj del servidor va en UTC y se adelantaría un día)."""
    try:
        from datetime import datetime
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("America/Argentina/Buenos_Aires")).date()
    except Exception:                       # Windows sin tzdata: se usa el reloj de la PC
        return date.today()


@st.cache_data(show_spinner=False)
def _mt5(simbolo: str, tf: str, desde: str, hasta: str):
    return data.cargar_mt5(simbolo, tf, desde, hasta)


@st.cache_data(ttl=300, show_spinner=False)
def _simbolos_mt5() -> list:
    return data.listar_simbolos_mt5()


TITULO_PAGINA = "Backtester: SMA con filtros" if ES_SMA else "Backtester: cruce de EMAs con filtros"
estado.setdefault("contador", met.ContadorPruebas())
estado.setdefault("res", None)
estado.setdefault("comp", None)
estado.setdefault("abl", None)
estado.setdefault("vista", "bt")      # pantalla: bt = backtest, abl = ablación, comp = comparación

st.markdown(vis.css(), unsafe_allow_html=True)

# ------------------------------------------------------------------ datos
with st.sidebar:
    # La fuente es la base de todo: va fuera de los menús, como un título, debajo del modo oscuro.
    st.markdown('<div class="fte">Fuente de datos</div>', unsafe_allow_html=True)
    fuente = st.radio("Fuente de datos", [ETQ_MT5, ETQ_CSV, ETQ_SINT], index=0 if MT5_OK else 1,
                      label_visibility="collapsed")
    st.markdown('<div class="fte-fin"></div>', unsafe_allow_html=True)
    exp_instr = st.expander("1. Instrumento a operar", expanded=False)
    exp_datos = st.expander("2. Datos: período y temporalidad", expanded=False)
    datos, specs, avisos_datos = {}, {}, []
    simbolos, tf, desde, hasta = [], None, None, None
    with exp_instr:
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

    with exp_datos:
        try:
            if fuente == ETQ_MT5 and MT5_OK:
                tf = st.selectbox("Temporalidad", ["D1", "H4", "H1", "M30", "M15", "M5", "M1"], index=2)
                c1, c2 = st.columns(2)
                desde = c1.date_input("Desde", date(2020, 1, 1))
                hasta = c2.date_input("Hasta", _hoy())
                if desde >= hasta:
                    st.error("La fecha 'desde' debe ser anterior a 'hasta'.")
                elif not simbolos:
                    st.info("Elegí al menos un símbolo en «Instrumento a operar».")
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
                                    f"{d_.index[0]:%d/%m/%Y}. El servidor o el terminal no guardan más atrás. "
                                    "Para más historia usá una temporalidad mayor "
                                    "(H1 o D1) o subí 'Max bars in chart' en MT5 (Herramientas → Opciones → Gráficos).")
                        except data.ErrorDatos as e:
                            avisos_datos.append(f"{simbolo}: {e}")
                        barra.progress((k + 1) / len(simbolos))
                    barra.empty()
        except (data.ErrorDatos, ValueError, KeyError) as e:
            st.error(str(e))
            datos, specs = {}, {}

        if datos:
            regla = st.selectbox("Remuestrear a", ["No", "15min", "30min", "1h", "4h", "1D"])
            if regla != "No":
                datos = {s: data.resamplear(d_, regla) for s, d_ in datos.items()}
            primero = next(iter(datos.values()))
            if fuente != ETQ_MT5:       # con MT5 el período ya lo define "Desde / Hasta"
                rango = st.date_input("Recortar período", (primero.index[0].date(), primero.index[-1].date()))
                if isinstance(rango, tuple) and len(rango) == 2:
                    datos = {s: d_.loc[str(rango[0]):str(rango[1])] for s, d_ in datos.items()}
            datos = {s: d_ for s, d_ in datos.items() if len(d_)}
        elif fuente != ETQ_MT5 or not MT5_OK:
            st.caption("Cargá archivos o datos de demo en «Instrumento a operar».")

    with st.expander("3. Señal y gestión", expanded=False):
        modo_senal, media_unica = "cruce", 50
        if ES_SMA:
            modo_senal = {"Cruce de dos SMA": "cruce", "Precio cruza una SMA": "precio"}[st.radio(
                "Señal", ["Cruce de dos SMA", "Precio cruza una SMA"],
                help="Cruce de dos SMA: la corta cruza a la larga. Precio cruza una SMA: el cierre de la vela pasa de un lado "
                     "al otro de la media (alcista si pasa a estar encima). En los dos casos se entra al cierre de esa vela.")]
        if modo_senal == "precio":
            media_unica = st.number_input("Período de la SMA", 2, 1000, 50)
            ema_c, ema_l = 20, 50                   # no intervienen en este modo
        else:
            c1, c2 = st.columns(2)
            ema_c = c1.number_input(f"{MEDIA} corta", 2, 500, 20 if ES_SMA else 13)
            ema_l = c2.number_input(f"{MEDIA} larga", 3, 1000, 50 if ES_SMA else 34)
        direccion = DIRECCIONES[st.selectbox("Dirección", list(DIRECCIONES))]
        salida_txt = "Objetivo fijo (RR o US$)" if not ES_SMA else st.radio(      # solo en la página SMA: la de EMA no cambia
            "Salida (Take Profit)", ["Objetivo fijo (RR o US$)", "Cuando el precio cambia de lado de la media"],
            help="Objetivo fijo: TP a una distancia fija del SL, como siempre. Cambio de lado: no hay TP; se cierra al cierre "
                 "de la primera vela que queda del otro lado de la media (un largo sale cuando una vela cierra por debajo, un "
                 "corto cuando cierra por encima). El SL sigue activo y se revisa antes en cada vela.")
        salida_modo = "senal" if salida_txt.startswith("Cuando") else "rr"
        sl_modo = st.selectbox("SL en", [SL_ATR, SL_PCT, SL_USD])
        if salida_modo == "senal":
            st.caption("Sin TP fijo: la operación dura hasta que una vela cierra del otro lado de la media o toca el SL.")
            rr, tp_usd, tp_modo = 2.0, 0.0, TP_RR            # el RR no interviene
            if sl_modo == SL_USD:
                sl_usd = st.number_input("Stop Loss (US$ por operación)", 1.0, 10_000_000.0, 100.0, 10.0)
                sl_valor = sl_usd
            else:
                sl_usd = 0.0
                sl_valor = st.number_input("Valor del SL", 0.01, 100.0, 1.5 if sl_modo == SL_ATR else 0.5, 0.1)
        elif sl_modo == SL_USD:
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
        # El ATR solo interviene si el SL va en múltiplos de ATR o si algún filtro lo usa (los filtros se definen más abajo:
        # sus valores ya están en session_state al comienzo de cada ejecución).
        usa_atr = (sl_modo == SL_ATR or bool(st.session_state.get("f_atr"))
                   or (bool(st.session_state.get("f_sma")) and float(st.session_state.get("f_sma_dist", 0) or 0) > 0)
                   or (bool(st.session_state.get("f_vwap")) and float(st.session_state.get("f_vwap_dist", 0) or 0) > 0))
        atr_per = st.number_input("Período ATR", 2, 200, 14, disabled=not usa_atr,
                                  help="Se usa en el SL en múltiplos de ATR, en el filtro ATR y en la distancia mínima a la SMA o al VWAP.")
        if not usa_atr:
            st.caption("Desactivado: con SL en dólares o en % del precio y sin filtros que usen ATR, este valor no interviene.")
        pb_on = st.checkbox(f"Entrar en pullback a la {MEDIA} (opcional)",
                            help="Apagado: se entra al cierre de la vela del cruce, como siempre. Encendido: el cruce sigue "
                                 f"siendo la señal, pero la entrada se hace cuando el precio retrocede hacia la {MEDIA}.")
        pb_pct, pb_ema, pb_velas = 50, "corta", 10
        if pb_on:
            pb_pct = st.number_input(f"Retroceso hacia la {MEDIA} (%)", 0, 100, 50, 5,
                                     help="0 = entrar al cierre (igual que sin pullback). 100 = entrar recién cuando el precio "
                                          f"toca la {MEDIA}. Se mide sobre la distancia entre el extremo posterior al cruce y la {MEDIA}.")
            if modo_senal == "cruce":
                pb_ema = {"Corta": "corta", "Larga": "larga"}[st.radio(f"{MEDIA} de referencia", ["Corta", "Larga"], horizontal=True)]
            pb_velas = st.number_input("Caducidad (velas)", 1, 200, 10,
                                       help="Si en estas velas el precio no hizo el retroceso, la orden se cancela. También "
                                            "se cancela si aparece un cruce en sentido contrario.")
            st.caption("Con pullback, el filtro de sesión se evalúa cuando se ejecuta la entrada.")

    with st.expander("4. Lotaje y dinero", expanded=False):
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
        capital = st.number_input("Capital de la cuenta (US$)", 0.0, 100_000_000.0, 100_000.0, 1000.0)
        st.caption("Capital inicial: sobre él se calculan los límites de pérdida y se estima, en la conclusión final, "
                   "el riesgo de tocarlos.")
        st.markdown("**Reglas de la cuenta**")
        reglas_on = st.checkbox("Aplicar reglas de cuenta en el backtest", value=True,
                                help="Tildado: el backtest simula la cuenta en orden cronológico y respeta los límites y controles de "
                                     "abajo (las operaciones bloqueadas no cuentan). Destildado: funciona como hasta ahora, sin "
                                     "cuenta. Los valores quedan cargados y el bot de MT5 los usa igual.")
        MODOS_DIA = ["Trailing", "Estático"]
        MODOS_TOT = ["Estático", "Trailing"]
        perd_dia = st.number_input("Pérdida diaria máx. (%)", 0.0, 100.0, 5.0, 0.5)
        modo_dia = {MODOS_DIA[0]: "trailing", MODOS_DIA[1]: "estatico"}[st.radio(
            "Modo diario", MODOS_DIA, horizontal=True,
            help="Trailing: el límite es un % del balance con el que empezó el día y se recalcula cada día. "
                 "Estático: un monto fijo en dólares (el % del capital inicial) que se resta del balance de inicio del día.")]
        st.caption("0 = sin límite. Se vigila el equity (incluye lo flotante). En FTMO es el 5% del capital.")
        perd_tot = st.number_input("Pérdida total máx. (%)", 0.0, 100.0, 10.0, 0.5)
        modo_tot = {MODOS_TOT[0]: "estatico", MODOS_TOT[1]: "trailing"}[st.radio(
            "Modo total", MODOS_TOT, horizontal=True,
            help="Estático: el piso es fijo (capital inicial menos el %). Trailing: el piso sube con "
                 "el balance máximo alcanzado y nunca baja.")]
        st.caption("0 = sin límite. En FTMO es el 10% del capital inicial y el piso no sube.")
        colchon = st.number_input("Colchón antes del límite (%)", 0.0, 50.0, 1.0, 0.5)
        st.caption("Se resta a los dos límites: el bot y el backtest frenan ese margen antes del límite real, para cubrir "
                   "saltos de precio y slippage. Con 5% y colchón 1%, frena en 4%.")
        _ef_d = max(perd_dia - colchon, 0.0) if perd_dia > 0 else 0.0
        _ef_t = max(perd_tot - colchon, 0.0) if perd_tot > 0 else 0.0
        if (0 < perd_dia <= colchon) or (0 < perd_tot <= colchon):
            st.error("El colchón tiene que ser menor que los límites.")
        else:
            _txt_d = (f"diario {_ef_d:g} % (US$ {_ef_d / 100 * capital:,.0f})".replace(",", ".") if _ef_d else "diario: sin límite")
            _txt_t = (f"total {_ef_t:g} %" + (f" (piso US$ {capital * (1 - _ef_t / 100):,.0f})".replace(",", ".")
                                              if modo_tot == "estatico" else " (desde el máximo)") if _ef_t else "total: sin límite")
            st.info(f"**Límites efectivos** (los usan el backtest y el bot)\n\n- {_txt_d}\n- {_txt_t}")
        proteger = st.checkbox("No abrir si el SL, perdiendo al máximo, rompe un límite", value=True,
                               help="Evita que una sola operación lleve la cuenta por debajo del límite diario o total. "
                                    "Sin esto, una operación abierta se cierra cuando el equity toca el límite.")
        riesgo_on = st.checkbox("Riesgo máximo por operación (% del capital)",
                                help="Si el riesgo del SL de una operación supera este porcentaje, la operación se saltea. "
                                     "Los lotes siguen siendo fijos.")
        riesgo_pct = st.number_input("Máximo por operación (%)", 0.05, 100.0, 1.0, 0.25, disabled=not riesgo_on)
        pausa_on = st.checkbox("Tiempo mínimo tras una pérdida (minutos)",
                               help="Después de una operación que cierra en pérdida, las señales que caen dentro de este "
                                    "tiempo se descartan.")
        pausa_min = st.number_input("Minutos sin operar tras una pérdida", 0.0, 100_000.0, 60.0, 5.0, disabled=not pausa_on)
        offset_dia = st.number_input("Desfase del servidor en invierno (GMT+2 → 2)", -12.0, 14.0, 2.0, 1.0, key="offset_dia")
        st.caption("Sirve para cortar el día a medianoche de Europa Central (hora CE(S)T), como FTMO. Medilo con el "
                   "mercado abierto; es el mismo dato del filtro de sesión.")
        limite_pct = perd_tot

    with st.expander("5. Costos", expanded=False):
        spread = SPREADS[st.selectbox("Spread", list(SPREADS))]
        spread_fijo = st.number_input("Spread fijo (unid. de precio)", 0.0, value=0.3) if spread == "fijo" else 0.0
        costo_extra = st.number_input("Costo extra por operación (unid. de precio)", 0.0, value=0.0)

    with st.expander("6. Filtros (independientes)", expanded=False):
        sma_on = st.checkbox("Filtro SMA", key="f_sma")
        if sma_on:
            sma_per = st.number_input("Período SMA", 2, 1000, 200)
            sma_dist = st.number_input("Distancia mínima al cierre (múltiplos de ATR, 0 = sin)", 0.0, value=0.0, step=0.1, key="f_sma_dist")
            sma_pend = st.number_input("Pendiente a favor: N velas (0 = sin)", 0, 500, 0)
        else:
            sma_per, sma_dist, sma_pend = 200, 0.0, 0
        vwap_on = st.checkbox("Filtro VWAP (diario)", key="f_vwap")
        if vwap_on:
            vwap_dist = st.number_input("Distancia mínima al VWAP (múltiplos de ATR, 0 = sin)", 0.0, value=0.5, step=0.1, key="f_vwap_dist",
                                        help="Regla práctica habitual: exigir al menos 0,5 ATR de distancia para no operar en la zona de ruido pegada al VWAP.")
            vwap_min = st.number_input("Minutos mínimos desde el inicio del día", 0, 1440, 30, 5,
                                       help="No se filtra en los primeros minutos del día: al abrir el VWAP es casi igual al precio. "
                                            "Práctica habitual: ignorar la primera media hora.")
            st.caption("VWAP del día (precio típico × volumen de ticks), reiniciado en cada día del servidor. "
                       "Largos solo con el cierre sobre el VWAP; cortos solo debajo. Necesita velas menores a D1.")
        else:
            vwap_dist, vwap_min = 0.5, 30
        adx_on = st.checkbox("Filtro ADX")
        if adx_on:
            adx_per = st.number_input("Período ADX", 2, 100, 14)
            adx_min = st.number_input("ADX mínimo", 0.0, 100.0, 20.0)
            adx_max = st.number_input("ADX máximo (0 = sin)", 0.0, 100.0, 0.0)
            adx_cre = st.number_input("ADX creciente: N velas (0 = sin)", 0, 200, 0)
        else:
            adx_per, adx_min, adx_max, adx_cre = 14, 20.0, 0.0, 0
        rango_on = st.checkbox("Filtro de rango (ratio de eficiencia)", key="f_rango",
                               help="Mide cuánto avanzó el precio en las últimas N velas respecto de todo lo que se movió: 1 = tendencia "
                                    "limpia, 0 = va y viene sin avanzar (rango). Si el ratio es menor al mínimo, la señal no se opera.")
        if rango_on:
            rango_vent = st.number_input("Ventana (velas)", 2, 500, 20, key="rango_vent")
            rango_min = st.number_input("Ratio mínimo (0 a 1)", 0.0, 1.0, 0.30, 0.05, format="%.2f", key="rango_min")
            st.caption("Valor de partida: ventana 20, mínimo 0,30. Más alto = más exigente (opera menos). "
                       "Se parece al ADX: probá uno u otro con la ablación antes de usar los dos.")
        else:
            rango_vent, rango_min = 20, 0.30
        atr_on = st.checkbox("Filtro ATR", key="f_atr")
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
        ses_on = st.checkbox("Filtro de sesión",
                             help="Sin marcar, el bot opera 24/5: toma cruces a cualquier hora en que el mercado esté "
                                  "abierto, sin filtro de sesión y sin necesitar el desfase del servidor. Tokio + Londres + "
                                  "Nueva York juntas dejan afuera unas 2-3 horas por día (después del cierre de Nueva York "
                                  "y antes de Tokio).")
        if not ses_on:
            st.caption("Sin marcar: 24/5, todo el mercado.")
        if ses_on:
            sesiones = st.multiselect("Sesiones permitidas", SESIONES, SESIONES)
            offset = st.number_input("Desfase del servidor en invierno (GMT+2 → 2)", -12.0, 14.0, 2.0, 1.0)
            dst = st.checkbox("El servidor cambia de hora con EE.UU.", True)
            st.caption("Confirmá el desfase midiéndolo con el mercado abierto. Los horarios de "
                       "las sesiones se mueven con el horario de verano de cada plaza. En BTC el "
                       "filtro se desactiva solo (opera 24/7).")
        else:
            sesiones, offset, dst = list(SESIONES), None, True

    with st.expander("7. Control de sobreajuste", expanded=False):
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
        ema_corta=int(ema_c), ema_larga=int(ema_l), rr=float(rr), salida_modo=salida_modo,
        media_tipo=TIPO, modo_senal=modo_senal, media_unica=int(media_unica),
        sl_modo=modo, sl_valor=valor, atr_periodo=int(atr_per),
        pullback_activo=bool(pb_on), pullback_pct=float(pb_pct), pullback_ema=pb_ema, pullback_velas=int(pb_velas),
        direccion=direccion, spread=spread, spread_fijo=float(spread_fijo), costo_extra=float(costo_extra),
        vwap_activo=vwap_on, vwap_dist_min_atr=float(vwap_dist), vwap_min_minutos=float(vwap_min),
        sma_activo=sma_on, sma_periodo=int(sma_per), sma_dist_min_atr=float(sma_dist), sma_pendiente_n=int(sma_pend),
        adx_activo=adx_on, adx_periodo=int(adx_per), adx_min=float(adx_min),
        adx_max=float(adx_max) or None, adx_creciente_n=int(adx_cre),
        rango_activo=rango_on, rango_ventana=int(rango_vent), rango_min=float(rango_min),
        atr_activo=atr_on, atr_unidad="pct", atr_min=float(atr_min) or None, atr_max=float(atr_max) or None,
        atr_rel_n=int(rel_n), atr_rel_min=float(rel_min) or None, atr_rel_max=float(rel_max) or None,
        sesion_activo=ses_on, sesiones=tuple(sesiones),
        servidor_offset_horas=offset if ses_on else (offset_dia if reglas_on else None), servidor_dst_eeuu=dst,
        reglas_activas=bool(reglas_on), capital=float(capital),
        usd_por_unidad=float(met.valor_por_unidad(p["tick_size"], p["tick_value"], lotes)),
        comision_op_usd=float(comision) * float(lotes),
        perd_dia_pct=float(perd_dia), perd_dia_modo=modo_dia, perd_tot_pct=float(perd_tot), perd_tot_modo=modo_tot,
        colchon_pct=float(colchon), proteger_sl=bool(proteger),
        riesgo_op_activo=bool(riesgo_on), riesgo_op_pct=float(riesgo_pct),
        pausa_activa=bool(pausa_on), pausa_min=float(pausa_min))


# ------------------------------------------------------------------ cuerpo
def html(x: str) -> None:
    st.html(x)


def tarjeta_html(titulo: str, cuerpo: str, nota: str = "", derecha: str = "", min_alto: int = 0) -> None:
    html(vis.tarjeta(titulo, cuerpo, nota, derecha, min_alto))


if not datos:
    html(vis.barra_superior(TITULO_PAGINA,
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
    TITULO_PAGINA,
    "Medí si una idea tiene ventaja demostrable, no cuál combinación gana: con muchas pruebas, "
    "un buen resultado puede ser azar.",
    [("Símbolo", activo), ("Pruebas en la sesión", estado.contador.n)]))
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
            conv.append((s_, f"SL {vis.n(c_.sl_valor, 5 if c_.sl_valor < 1 else 2)}" + ("" if salida_modo == "senal" else
                        f" · TP {vis.n(c_.sl_valor * c_.rr, 5 if c_.sl_valor < 1 else 2)}")))
        st.write("")
        html(vis.tarjeta(f"SL de US${vis.n(sl_usd)}" + ("" if salida_modo == "senal" else f" y TP de US${vis.n(sl_usd * rr)}")
                         + f" con {vis.n(lotes)} lotes: en puntos de precio",
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
if correr:
    estado.vista = "bt"
abl = b2.button("Modo ablación (cruce solo + cada filtro)")
comp = b3.button("Comparar símbolos", disabled=len(datos) < 2)

if correr:
    try:
        cfg = construir_config()
        with ui.cargando("Calculando..."):
            estado.res = (met.evaluar(df, cfg, oos / 100, int(azar_n), 42,
                                                estado.contador), cfg, activo,
                                    {"lotes": float(lotes), "comision": float(comision), "capital": float(capital),
                                     "limite_pct": float(limite_pct), **params_dinero(activo)})
    except (ValueError, data.ErrorDatos) as e:
        st.error(str(e))

# ------------------------------------------------------------- generar bot (barra lateral, fuera de los menús)
_REGLA_TF = {"15min": "M15", "30min": "M30", "1h": "H1", "4h": "H4", "1D": "D1"}
with st.sidebar:
    st.markdown('<div class="fte">Bot para MT5</div>', unsafe_allow_html=True)
    try:
        _cfg_bot = construir_config()
        _tf_bot = _REGLA_TF.get(regla, "") if regla != "No" else (globals().get("tf") or "")
        _vd_bot = None
        _g = estado.get("veredicto_bot")      # (config, veredicto, símbolo, lotes, temporalidad)
        if _g and _g[0] == _cfg_bot and _g[2] == activo and _g[3] == float(lotes) and _g[4] == _tf_bot:
            _vd_bot = _g[1]
        _motivo = ("Con datos sintéticos no se genera bot." if fuente == ETQ_SINT
                   else gb.motivo_rechazo(_vd_bot, _tf_bot))
        if _motivo:
            st.button("⚙️ Generar bot (.mq5)", disabled=True, use_container_width=True)
            st.caption(_motivo)
        else:
            _mq5 = gb.generar_mq5(_cfg_bot, activo, _tf_bot, float(lotes),
                                  float(sl_usd) if sl_modo == SL_USD else None, _vd_bot,
                                  capital=float(capital), limite_pct=float(limite_pct))
            st.download_button("⚙️ Generar bot (.mq5)", _mq5.encode("utf-8"),
                               file_name=gb.nombre_archivo(activo, _tf_bot), mime="text/plain",
                               use_container_width=True)
            st.caption("Veredicto del backtest: " + _vd_bot["titulo"] + ". El bot opera solo y con parámetros fijos: "
                       "se niega a arrancar si el símbolo, la temporalidad, el lote o el horario del servidor no coinciden. "
                       "Compilalo en MetaEditor (F7) y probalo en demo.")
    except (ValueError, RuntimeError, OSError) as e:
        st.caption("No se puede generar el bot: " + str(e))

if comp:
    try:
        cfgs = {s: construir_config(s) for s in datos}
        with ui.cargando("Comparando símbolos..."):
            _tabla, _notas = met.comparar_simbolos(
                datos, cfgs, oos / 100, int(azar_n), 42, estado.contador, recortar)
            _gest = (f"SL US${vis.n(sl_usd, 0)}" if sl_modo == SL_USD
                     else f"SL {vis.n(sl_valor, 1)}{'×ATR' if sl_modo == SL_ATR else '%'}")
            _gest += " · salida por cambio de lado" if salida_modo == "senal" else (
                f" · TP US${vis.n(sl_usd * rr, 0)}" if sl_modo == SL_USD else f" · TP 1:{vis.n(rr, 1)}")
            _sen = (f"Precio vs SMA {int(media_unica)}" if modo_senal == "precio" else f"{MEDIA} {int(ema_c)}/{int(ema_l)}")
            estado.comp = (_tabla, _notas, f"{_sen} · {_gest}")
            estado.vista = "comp"
    except (ValueError, data.ErrorDatos) as e:
        st.error(str(e))

if abl:
    try:
        cfg = construir_config()
        with ui.cargando("Corriendo la ablación..."):
            tabla_abl, omitidos = met.ablacion(df, cfg, oos_pct=oos / 100,
                                               azar_veces=min(int(azar_n), 100),
                                               contador=estado.contador)
        estado.abl = (tabla_abl, omitidos, activo)
        estado.vista = "abl"
    except (ValueError, data.ErrorDatos) as e:
        st.error(str(e))

if estado.vista == "abl" and estado.abl is not None:
    tabla_abl, omitidos, act_abl = estado.abl
    st.write("")
    if st.button("← Volver al backtest", key="volver_abl"):
        estado.vista = "bt"
        st.rerun()
    html(vis.titulo_seccion("Modo ablación", "El cruce solo y el efecto de cada filtro, uno por uno"))
    filas = []
    for nombre, fila in tabla_abl.iterrows():
        filas += [(f"{nombre} · todo", fila["exp_R"]), (f"{nombre} · OOS", fila["exp_R_OOS"], vis.VIOLETA)]
    tarjeta_html(f"Ablación de {act_abl}: expectativa en R", vis.barras_divergentes(filas),
                 "Los filtros se miden con parámetros fijos (SMA 200, VWAP diario sin distancia, ADX mínimo 20, rango con ventana 20 y mínimo 0,30, ATR relativo de 100 "
                 "velas entre 0,8 y 2,0). El aporte es el de esos valores, no el del filtro en general.")
    with st.expander("Ver tabla de la ablación"):
        html(vis.tabla_df(tabla_abl, dec=3, nombre_indice="Configuración"))
    if omitidos:
        st.warning(f"Omitidos: {', '.join(omitidos)}. (Sesión necesita el desfase del servidor; VWAP necesita velas menores a D1.)")
    st.stop()

if estado.comp is not None and len(estado.comp) != 3:      # versión anterior: se descarta
    estado.comp = None
if estado.comp is not None and estado.vista == "comp":
    tabla_c, notas_c, estrategia_c = estado.comp
    if st.button("← Volver al backtest", key="volver_comp"):
        estado.vista = "bt"
        st.rerun()
    vc = vd.evaluar_comparabilidad(tabla_c)
    rb = vc["robustez"]
    N_c = len(tabla_c)
    ini_c, fin_c = tabla_c["desde"].max(), tabla_c["hasta"].min()
    st.write("")
    html(vis.titulo_seccion("Comparación de símbolos", "Mismos parámetros en todos, sin optimizar por activo"))
    html(vis.chips([("Símbolos", ", ".join(tabla_c.index)), ("Período común", f"{ini_c} → {fin_c}"), ("Estrategia", estrategia_c)]))
    st.write("")
    k1, k2, k3, k4 = st.columns(4)
    lo_, hi_ = vc["rango_exp"]
    with k1:
        html(vis.kpi("Símbolos comparados", str(N_c), "mismos parámetros en todos", vis.INDIGO))
    with k2:
        html(vis.kpi("Positivos en todo el período", f"{rb['pos_total']} de {N_c}", "expectativa mayor que 0", vis.VIOLETA))
    with k3:
        html(vis.kpi("Positivos en out-of-sample", f"{rb['pos_oos']} de {N_c}", "datos que el modelo no vio", vis.ROSA))
    with k4:
        html(vis.kpi("Rango de expectativa", vis.n(hi_ - lo_, 2) + " R",
                     f"de {vis.n(lo_, 2, True)} a {vis.n(hi_, 2, True)} (todo el período)", vis.AZUL))
    st.write("")
    filas = []
    for simbolo, fila in tabla_c.iterrows():
        filas += [(f"{simbolo} · todo", fila["exp_R"]), (f"{simbolo} · OOS", fila["exp_R_OOS"], vis.VIOLETA)]
    cc1, cc2 = st.columns([3, 2])
    with cc1:
        tarjeta_html("Expectativa por símbolo (R por operación)", vis.barras_divergentes(filas),
                     "Se compara en R, no en dinero: el valor por tick difiere entre activos.", min_alto=340)
    with cc2:
        html(vis.veredicto_caja(
            "Veredicto de comparabilidad", vc["titulo"],
            f"<div>{vc['texto']}</div><div style='margin-top:8px;opacity:.85;font-size:.8rem'>Criterios: "
            f"{vc['n_ok']} cumplen · {vc['n_warn']} con reservas · {vc['n_bad']} no cumplen</div>",
            {"ok": "ok", "reservas": "dudosa", "no": "pierde"}[vc["nivel"]]))
        st.write("")
        html(vis.veredicto_caja("Robustez de la estrategia", rb["titulo"], f"<div>{rb['texto']}</div>",
                                {"ok": "ok", "dudosa": "dudosa", "sin": "sin"}[rb["nivel"]]))
    st.write("")
    simbolos_c = list(tabla_c.index)
    for k0 in range(0, N_c, 4):
        cols_r = st.columns(min(4, N_c - k0))
        for col_, simbolo in zip(cols_r, simbolos_c[k0:k0 + 4]):
            f_ = tabla_c.loc[simbolo]
            with col_:
                html(vis.tarjeta("", vis.anillo(
                    f_["%TP"], simbolo, f"{int(f_['resueltas'])} operaciones · exp. {vis.n(f_['exp_R'], 2, True)} R · "
                    f"equilibrio {vis.n(f_['%equilibrio'], 1)}%", f_["%equilibrio"],
                    vis.INDIGO if f_["exp_R"] > 0 else vis.ROSA, uid=f"c{k0}{simbolo}"[:12])))
    st.write("")
    cols_f = ["Símbolo", "Tipo", "Operaciones", "en OOS", "% TP", "Exp. todo", "Exp. OOS", "Mejor que azar OOS",
              "Spread % SL", "SL en ATR", "Ops/mes", "Máx. DD (R)"]
    filas_f = [[s_, f_["tipo"], str(int(f_["resueltas"])), str(int(f_["resueltas_OOS"])), vis.n(f_["%TP"], 1) + "%",
                vis.n(f_["exp_R"], 2, True), vis.n(f_["exp_R_OOS"], 2, True),
                "–" if f_["mejor_que_%azar_OOS"] != f_["mejor_que_%azar_OOS"] else vis.n(f_["mejor_que_%azar_OOS"], 0) + "%",
                vis.n(f_["spread_%SL"], 0) + "%", vis.n(f_["sl_atr"], 1) + "×", vis.n(f_["ops_mes"], 1), vis.n(f_["maxDD_R"], 1)]
               for s_, f_ in tabla_c.iterrows()]
    est_c = {n_: e_ for e_, n_, _ in vc["checks"]}
    resalta = {9: est_c["Riesgo equivalente (SL en ATR)"] != vd.OK, 8: est_c["Costos comparables (spread / SL)"] != vd.OK,
               10: est_c["Frecuencia parecida"] != vd.OK, 3: est_c["Muestra suficiente en cada uno"] != vd.OK,
               1: est_c["Mismo tipo de activo"] != vd.OK}
    tarjeta_html("Ficha por símbolo", vis.tabla_html(cols_f, filas_f, resaltar=lambda i, j: resalta.get(j, False), izq=(1,)),
                 "Las columnas resaltadas son las que no cumplen su criterio de comparabilidad.")
    st.write("")
    filas_k = [[vd.SIMBOLO[e_], n_, d_] for e_, n_, d_ in vc["checks"]]
    tarjeta_html("Criterios de comparabilidad", vis.tabla_html(
        ["", "Criterio", "Resultado"], filas_k, izq=(1, 2),
        clase=lambda i, j: ("pos" if filas_k[i][0] == "✓" else "neg" if filas_k[i][0] == "✕" else None) if j == 0 else None),
        "Si todos se cumplen: «Comparables». Con alguno en «!»: «Comparables con reservas». Con alguno en «✕»: «No comparables».")
    if notas_c:
        html("<ul style='margin:4px 0 0 18px;padding:0;font-size:.82rem;line-height:1.5;color:" + vis.TEXTO + ";opacity:.8'>"
             + "".join(f"<li>{n_}</li>" for n_ in dict.fromkeys(notas_c)) + "</ul>")
    with st.expander("Ver tabla de la comparación"):
        html(vis.tabla_df(tabla_c, dec=3, nombre_indice="Símbolo"))
    st.stop()

if estado.res is None:
    st.stop()

# ------------------------------------------------------------------ resultado
if len(estado.res) != 4:      # resultado de una versión anterior: se descarta
    estado.res = None
    st.stop()
r, cfg_usada, act_res, pdin = estado.res
t = r["tabla"]
tt, ti, to = t.loc["Todo"], t.loc["In-sample"], t.loc["Out-of-sample"]
tr = r["trades"]
if cfg_usada.salida_modo == "senal":
    st.caption("Salida por cambio de lado: aquí «TP» son las operaciones que cerraron con ganancia y «SL» las que cerraron con "
               "pérdida (ya sea por el SL o por la señal de salida). La columna «motivo» de la tabla dice cómo cerró cada una; "
               "el R de cada operación es el real, no uno fijo.")
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

if cfg_usada.reglas_activas and r.get("cuenta"):
    _cu = r["cuenta"]
    _cap_u = float(cfg_usada.capital)
    _dias_tot = int(len(np.unique(r["P"].dia))) if r["P"].dia is not None else 0
    _salt = (_cu["saltadas_dia"] + _cu["saltadas_proteccion"] + _cu["saltadas_riesgo"] + _cu["saltadas_pausa"])
    if _cu["quemada"]:
        st.error(f"Con estas reglas la cuenta se habría quemado el {str(r['P'].indice[int(_cu['quemada_en'])])[:10]}: "
                 "el resultado termina ahí y el resto del período no se opera.")
    st.write("")
    html(vis.titulo_seccion("Reglas de la cuenta", "Qué hicieron los límites y controles en el período (tramo «Todo»)"))
    q1, q2, q3, q4 = st.columns(4)
    with q1:
        html(vis.kpi("Días bloqueados", vis.n(_cu["dias_bloqueados"], 0), f"por el límite diario, de {_dias_tot} días",
                     vis.ROSA if _cu["dias_bloqueados"] else vis.INDIGO, 140))
    with q2:
        html(vis.kpi("Señales salteadas", vis.n(_salt, 0),
                     f"{_cu['saltadas_dia']} día bloqueado · {_cu['saltadas_proteccion']} protección · "
                     f"{_cu['saltadas_riesgo']} riesgo · {_cu['saltadas_pausa']} pausa", vis.VIOLETA, 140))
    with q3:
        html(vis.kpi("Cuenta quemada", "Sí" if _cu["quemada"] else "No",
                     (f"{_cu['forzadas']} cierres forzados por límite" if _cu["forzadas"] else "límite total no alcanzado"),
                     vis.ROSA if _cu["quemada"] else vis.INDIGO, 140))
    with q4:
        html(vis.kpi("Peor día", vis.n(_cu["peor_dia_usd"], 0, True) + " US$",
                     f"{vis.n(100 * _cu['peor_dia_usd'] / _cap_u, 1, True)} % del capital · balance mínimo "
                     f"{vis.n(100 * (_cu['balance_min'] - _cap_u) / _cap_u, 1, True)} %", vis.tono(_cu["peor_dia_usd"]), 140))
    st.caption("Cada tramo (todo, in-sample, out-of-sample) y cada corrida al azar arranca con una cuenta nueva. "
               "Dentro de una vela no se conoce el máximo flotante, así que los límites del día se aplican de forma aproximada.")

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
                     "Un año con pocas operaciones pesa poco: mirá el número debajo de cada barra.", min_alto=ALTO_FILA)
    with h2:
        _pb = tt["pb"] if isinstance(tt["pb"], dict) else {}
        _pasos = [("Cruces detectados", tt["cruces"]), ("Pasan los filtros", tt["tomados"])]
        if _pb:
            _pasos += [("Órdenes dejadas (pullback)", _pb["ordenes"]), ("Entradas ejecutadas", _pb["llenadas"])]
        else:
            _pasos += [("Operaciones tomadas", tt["resueltas"] + tt["abiertas"])]
        cuerpo = vis.embudo(_pasos + [("Llegaron a TP", tt["TP"])])
        _nombres = {"sma": "SMA", "adx": "ADX", "rango": "Rango", "atr": "ATR", "sesion": "Sesión"}
        _txt = []
        if r["descartes"]:
            _txt.append("Descartadas por filtro: " + " · ".join(f"{_nombres.get(k, k)} {int(v_)}" for k, v_ in r["descartes"].items()) + ".")
        if _pb and _pb["ordenes"]:
            _txt.append(f"Sin ejecutar: caducaron {_pb['caducadas']}, cruce contrario {_pb['cruce_contrario']}.")
        _txt.append(f"{int(tt['ignoradas'])} señales ignoradas por haber ya una operación abierta.")
        tarjeta_html("Embudo de señales", cuerpo, " ".join(_txt), min_alto=ALTO_FILA)

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
            html(vis.kpi("Resultado neto", vis.n(dinero["neto"], 2, True), f"con {vis.n(lotes_u)} lotes, tras comisiones", vis.tono(dinero["neto"]), 140))
        with m2:
            html(vis.kpi("Ganancia media (TP)", vis.n(dinero["ganancia_media_TP"], 2, True), "por operación ganadora", vis.INDIGO, 140))
        with m3:
            html(vis.kpi("Pérdida media (SL)", vis.n(dinero["perdida_media_SL"], 2, True), "por operación perdedora", vis.ROSA, 140))
        with m4:
            html(vis.kpi("Máx. drawdown", vis.n(dinero["max_drawdown"], 2), f"riesgo medio por operación: {vis.n(dinero['riesgo_medio_por_operacion'], 2)}", vis.ROSA, 140))
        _ex = met.extremos_diarios(tr, r["P"].indice, tick_size, tick_value, lotes_u, comision_u)
        if _ex:
            d1, d2 = st.columns(2)
            with d1:
                html(vis.kpi("Máx. drawdown diario", vis.n(min(_ex["peor_usd"], 0), 2),
                             f"{_ex['peor_dia']:%d/%m/%Y} · {_ex['peor_ops']} op. · {vis.n(_ex['peor_R'], 1, True)} R "
                             "(peor día, operaciones cerradas)", vis.ROSA, 140))
            with d2:
                html(vis.kpi("Máx. ganancia diaria (TP)", vis.n(max(_ex["mejor_usd"], 0), 2, True),
                             f"{_ex['mejor_dia']:%d/%m/%Y} · {_ex['mejor_ops']} op. · {vis.n(_ex['mejor_R'], 1, True)} R "
                             "(mejor día)", vis.INDIGO, 140))
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
        html(vis.kpi("Por día", vis.n(_fr["por_dia"], 2), f"promedio por día con mercado ({_fr.get('dias_mercado', 0)} días)", vis.INDIGO, 165))
    with f2:
        html(vis.kpi("Por semana", vis.n(_fr["por_semana"], 1), "promedio por semana calendario", vis.VIOLETA, 165))
    with f3:
        html(vis.kpi("Por mes", vis.n(_fr["por_mes"], 1), "promedio por mes calendario", vis.ROSA, 165))
    with f4:
        html(vis.kpi("Máx. en un día", str(_fr["max_dia"]), f"operaba en {_fr['dias_con_op']} días del período", vis.AZUL, 165))
    with f5:
        _sub = (f"del {_fr['sin_op_desde']:%d/%m/%Y} al {_fr['sin_op_hasta']:%d/%m/%Y}"
                if _fr["sin_op_desde"] is not None else "sin lapsos")
        html(vis.kpi("Máx. sin operar", f"{_fr['max_sin_op']} d", _sub, vis.MAGENTA, 165))
    st.caption(f"Total: {_fr['n']} operaciones tomadas (incluye las que no llegaron a TP ni SL). "
               "Con pocas operaciones por mes, los porcentajes tardan más en volverse confiables.")

# ------------------------------------------------------------- tasa de acierto y duración
if len(res):
    st.write("")
    html(vis.titulo_seccion("Tasa de acierto y duración", "Cuántas operaciones ganan y cuánto dura cada una, en el período analizado"))
    _du = met.duraciones(tr, r["P"].indice)
    d1, d2, d3, d4 = st.columns(4)
    with d1:
        html(vis.kpi("Win rate", f"{vis.n(_du['win_rate'], 1)}%",
                     f"{_du['n_tp']} TP y {_du['n_sl']} SL · equilibrio {vis.n(float(tt['%equilibrio']), 1)}%", vis.VIOLETA, 165))
    with d2:
        html(vis.kpi("Duración media", met.fmt_duracion(_du["min_todas"]),
                     f"{vis.n(_du['velas_todas'], 1)} velas · mediana {met.fmt_duracion(_du['min_mediana_todas'])}", vis.INDIGO, 165))
    with d3:
        html(vis.kpi("Media en TP", met.fmt_duracion(_du["min_tp"]),
                     f"{vis.n(_du['velas_tp'], 1)} velas · mediana {met.fmt_duracion(_du['min_mediana_tp'])}", vis.AZUL, 165))
    with d4:
        html(vis.kpi("Media en SL", met.fmt_duracion(_du["min_sl"]),
                     f"{vis.n(_du['velas_sl'], 1)} velas · mediana {met.fmt_duracion(_du['min_mediana_sl'])}", vis.ROSA, 165))
    st.caption("El win rate es sobre las operaciones resueltas (TP o SL). La duración va desde la entrada hasta la vela en que se "
               "cerró, contada en velas (la vela de salida cuenta entera) y pasada a tiempo con la temporalidad; no incluye fines de semana.")

# ------------------------------------------------------------- objetivo y retiros
if len(res) and dinero:
    st.write("")
    html(vis.titulo_seccion("Objetivo y retiros", "Cuánto tarda en ganar un % del balance inicial y, si retiraras cada vez, en volver a ganarlo"))
    _cap = float(pdin.get("capital", 0.0))
    _c_obj, _c_eq = st.columns([1, 3])
    with _c_obj:
        _obj_pct = st.number_input("Objetivo por retiro (% del balance inicial)", 0.5, 100.0, 5.0, 0.5, key="obj_retiro")
    with _c_eq:
        if _cap > 0:
            html(f"<div style='padding-top:2.05rem;font-size:.8rem;color:{vis.SUAVE}'>= US$ {vis.n(_cap * _obj_pct / 100, 0)} "
                 f"sobre un balance inicial de US$ {vis.n(_cap, 0)}</div>")
    if _cap <= 0:
        st.info("Cargá el capital de la cuenta (sección 4 de la barra lateral) y volvé a correr para calcular el objetivo.")
    else:
        _ob = met.ciclos_objetivo(tr, r["P"].indice, tick_size, tick_value, lotes_u, comision_u, _cap, _obj_pct)
        _rs, _ec, _cs = _ob["resumen"], _ob["en_curso"], _ob["ciclos"]
        _meta = f"+{vis.n(_obj_pct, 1)}% (US$ {vis.n(_ob['objetivo_usd'], 0)})"
        o1, o2, o3, o4 = st.columns(4)
        with o1:
            if _cs:
                html(vis.kpi("Primer objetivo", met.fmt_duracion(_rs["primero"]),
                             f"{_meta} · del {_cs[0]['desde']:%d/%m/%Y} al {_cs[0]['hasta']:%d/%m/%Y}", vis.INDIGO, 165))
            else:
                html(vis.kpi("Primer objetivo", "No llegó",
                             f"{_meta} · al cierre del período iba en {vis.n(_ec['avance_pct'], 1, True)}%", vis.ROSA, 165))
        with o2:
            html(vis.kpi("Retiros logrados", str(_rs["n"]),
                         f"cada vez que suma {_meta} · retirado en total US$ {vis.n(_rs['retirado'], 0)}", vis.VIOLETA, 165))
        with o3:
            if _cs:
                html(vis.kpi("Tiempo medio entre retiros", met.fmt_duracion(_rs["medio"]),
                             f"mediana {met.fmt_duracion(_rs['mediana'])} · mín {met.fmt_duracion(_rs['minimo'])} · "
                             f"máx {met.fmt_duracion(_rs['maximo'])}", vis.AZUL, 165))
            else:
                html(vis.kpi("Tiempo medio entre retiros", "–", "todavía no hubo ningún retiro", vis.AZUL, 165))
        with o4:
            html(vis.kpi("Ciclo en curso", f"{vis.n(_ec['avance_pct'], 1, True)}%",
                         f"desde el {_ec['desde']:%d/%m/%Y} · {met.fmt_duracion(_ec['min'])} · {_ec['ops']} op. · "
                         f"faltan US$ {vis.n(max(_ec['falta_usd'], 0), 0)}", vis.tono(_ec["avance"]), 165))
        if _cs:
            with st.expander("Ver cada retiro"):
                _filas_o = [[str(c["n"]), c["desde"].strftime("%d/%m/%Y %H:%M"), c["hasta"].strftime("%d/%m/%Y %H:%M"),
                             met.fmt_duracion(c["min"]), str(c["ops"]),
                             f"{vis.n(c['ganado'], 0, True)} ({vis.n(100 * c['ganado'] / _cap, 1, True)}%)"] for c in _cs]
                html(vis.tabla_html(["#", "Desde", "Hasta", "Tiempo", "Operaciones", "Ganado (US$)"], _filas_o))
        st.caption("Cada ciclo arranca con el balance inicial. Cuando la ganancia de las operaciones cerradas llega al objetivo se "
                   "supone que retirás todo lo ganado (el balance vuelve al inicial) y empieza otro ciclo. Las caídas cuentan: "
                   "si el ciclo baja de cero, primero hay que recuperarlas. Es tiempo calendario (incluye fines de semana) hasta la "
                   "vela de salida de la operación que alcanzó el objetivo. Valores teóricos, sin contar la ganancia flotante. "
                   "Con pocos retiros el promedio no es confiable.")

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
    f"<br><br>Llevás <b>{estado.contador.n}</b> pruebas en esta sesión: cuantas más probás, "
    "más probable es que alguna salga bien solo por azar. Esto no demuestra una ventaja por sí solo."))

# ------------------------------------------------------------- conclusión final
st.write("")
meses_datos = max((r["P"].indice[-1] - r["P"].indice[0]).days / 30.44, 0.1)
usd_R = dinero["riesgo_medio_por_operacion"] if dinero else None
veredicto = vd.evaluar_veredicto(r, cfg_usada, meses_datos, usd_R, pdin.get("capital", 0.0),
                                 pdin.get("limite_pct", 10.0), estado.contador.n)
sl_usd_u = tp_usd_u = 0.0
if cfg_usada.sl_modo == "precio":
    sl_usd_u = cfg_usada.sl_valor * met.valor_por_unidad(pdin["tick_size"], pdin["tick_value"], pdin["lotes"])
    tp_usd_u = 0.0 if cfg_usada.salida_modo == "senal" else sl_usd_u * cfg_usada.rr
_tf = globals().get("tf")
tf_txt = regla if regla != "No" else (_tf or "")
_vd_clave = (cfg_usada, act_res, float(pdin["lotes"]), _REGLA_TF.get(regla, "") if regla != "No" else (_tf or ""),
             veredicto["nivel"], veredicto["titulo"])
if estado.get("veredicto_bot_clave") != _vd_clave:
    estado.veredicto_bot = (cfg_usada, veredicto, act_res, float(pdin["lotes"]), _vd_clave[3])
    estado.veredicto_bot_clave = _vd_clave
    st.rerun()          # la barra lateral ya se dibujó: se repite para que el botón del bot vea el veredicto nuevo
relato = vd.describir(cfg_usada, act_res, tf_txt, r["P"].indice[0], r["P"].indice[-1], meses_datos, pdin["lotes"],
                      dinero["neto"] if dinero else None, int(tt["resueltas"]), int(tt["TP"]), int(tt["SL"]),
                      float(tt["exp_R"]) if tt["exp_R"] == tt["exp_R"] else 0.0,
                      dinero["max_drawdown"] if dinero else None, sl_usd_u, tp_usd_u)
if cfg_usada.reglas_activas and r.get("cuenta"):
    _cu2 = r["cuenta"]
    _ed, _et = cfg_usada.limites_efectivos()
    relato += (f"<br><br>Con las reglas de cuenta aplicadas (límite diario {vis.n(_ed, 1)} %, total {vis.n(_et, 1)} %): "
               f"{_cu2['dias_bloqueados']} días bloqueados, {_cu2['saltadas_dia'] + _cu2['saltadas_proteccion'] + _cu2['saltadas_riesgo'] + _cu2['saltadas_pausa']} "
               f"señales salteadas y la cuenta " + ("<b>se habría quemado</b>." if _cu2["quemada"] else "no se quemó."))
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
        _trv = tr if cfg_usada.salida_modo == "senal" else tr.drop(columns=["motivo"], errors="ignore")
        html(vis.tabla_df(_trv.drop(columns=["i", "salida"]), decs={c: _d for c in ("entrada", "sl", "tp", "dist")},
                          nombre_indice="n.º"))
        st.download_button("Descargar operaciones (CSV)", _trv.to_csv(index=False).encode("utf-8"),
                           "operaciones.csv", "text/csv")

_entrada_txt = ("- Con pullback: tras el cruce se deja una orden límite en el nivel de retroceso elegido y la operación se "
                "abre cuando el precio lo toca (no al cierre del cruce ni de la vela que llega). Caduca a las N velas o si "
                "aparece el cruce contrario; fills exactos en SL/TP, sin slippage ni gaps.\n"
                if cfg_usada.pb_efectivo() else
                "- Entrada al cierre de la vela del cruce; fills exactos en SL/TP, sin slippage ni gaps.\n")
with st.expander("Supuestos y limitaciones"):
    st.markdown(
        _entrada_txt +
        "- Velas OHLC, no ticks: si una vela toca SL y TP, se cuenta SL y como ambigua.\n"
        "- El spread es el de cierre de cada vela; en velas viejas suele venir en 0.\n"
        "- Una cuenta demo puede diferir en spread y ejecución. El Strategy Tester de MT5 con "
        "ticks reales es la validación final.\n"
        "- En índices hay gaps de apertura y pausas diarias que el backtest no modela.\n"
        "- Resultados pasados no garantizan resultados futuros.")
