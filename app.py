from datetime import date

import numpy as np
import pandas as pd
import streamlit as st

import bot_control
from bot_alertas import (
    EMA_LENTA,
    EMA_RAPIDA,
    INTERVALO_MIN,
    SMA_FILTRO,
    TZ_MENSAJE,
    descargar_m15,
    detectar_cruces,
)
from bot_alertas import TICKER as TICKER_BOT
from xauusd_sesiones import (
    TICKER,
    calcular_tabla,
    descargar,
    estadisticas_objetivo,
    nombre_csv,
)

st.set_page_config(
    page_title="XAU/USD - Calculadora de Sesiones",
    page_icon="📈",
    layout="centered",
)

st.title("📈 XAU/USD - Movimiento de las Sesiones")
st.write(
    "Calcula el rango High-Low en **dólares ($)** durante las dos primeras"
    " horas de Tokio, Londres y Nueva York."
)
st.caption(
    f"Datos de {TICKER} (futuro de oro COMEX, no spot XAU/USD) vía Yahoo"
    " Finance. Aperturas: Tokio 09:00 JST, Londres 08:00 local, Nueva York"
    " 08:00 ET. El horario de verano se ajusta automáticamente."
)

st.sidebar.header("Parámetros de Búsqueda")
fecha_inicio = st.sidebar.date_input(
    "Fecha de inicio", value=date(2026, 9, 23), format="DD/MM/YYYY"
)
fecha_fin = st.sidebar.date_input(
    "Fecha de fin", value=date(2026, 10, 24), format="DD/MM/YYYY"
)


objetivo = st.sidebar.number_input(
    "Objetivo en dólares ($)",
    min_value=0.0,
    value=10.0,
    step=0.5,
    format="%.2f",
    help="Se cuenta cuántas veces el rango High-Low de las 2 primeras horas"
    " alcanzó o superó este valor.",
)


@st.cache_data(ttl=900, show_spinner=False)
def descargar_cacheado(inicio: date, fin: date):
    return descargar(inicio, fin)


# ------------------------------------------------------------------ Calculador
# El resultado se guarda en session_state para que no desaparezca cuando se
# interactúa con la sección del bot (cada botón vuelve a ejecutar la página).
if st.sidebar.button("Calcular Movimientos", type="primary"):
    if fecha_inicio > fecha_fin:
        st.session_state["calculo"] = {
            "aviso": ("error", "❌ La fecha de inicio no puede ser posterior a la de fin.")
        }
    else:
        with st.spinner("Descargando datos y procesando rangos..."):
            df = descargar_cacheado(fecha_inicio, fecha_fin)
        if df.empty:
            st.session_state["calculo"] = {
                "aviso": (
                    "warning",
                    "⚠️ No se encontraron datos para ese rango. Recordá que"
                    " Yahoo solo ofrece velas de 1h de los últimos ~730 días.",
                )
            }
        else:
            tabla = calcular_tabla(df, fecha_inicio, fecha_fin)
            if tabla.empty:
                st.session_state["calculo"] = {
                    "aviso": (
                        "warning",
                        "⚠️ No hay sesiones completas en ese rango de fechas.",
                    )
                }
            else:
                st.session_state["calculo"] = {
                    "tabla": tabla,
                    "inicio": fecha_inicio,
                    "fin": fecha_fin,
                }


def mostrar_calculo(calculo: dict) -> None:
    if "aviso" in calculo:
        tipo, texto = calculo["aviso"]
        getattr(st, tipo)(texto)
        return

    tabla = calculo["tabla"]
    st.success("¡Datos procesados con éxito!")

    st.subheader("Resumen")
    resumen = tabla.agg(["mean", "median", "max"]).round(2)
    resumen.index = ["Promedio", "Mediana", "Máximo"]
    st.dataframe(resumen)

    st.subheader(f"Objetivo de ${objetivo:,.2f}")
    st.caption(
        "Días en que el rango High-Low de las 2 primeras horas alcanzó o"
        " superó el objetivo."
    )
    stats = estadisticas_objetivo(tabla, objetivo)
    st.dataframe(stats.style.format({"% de veces": "{:.1f}%"}, na_rep="-"))

    st.subheader("Detalle diario")
    st.caption("En verde, los días en que se alcanzó el objetivo.")

    def resaltar(data: pd.DataFrame) -> pd.DataFrame:
        return pd.DataFrame(
            np.where(data >= objetivo, "background-color: #2e7d3255", ""),
            index=data.index,
            columns=data.columns,
        )

    st.dataframe(
        tabla.style.apply(resaltar, axis=None).format("{:.2f}", na_rep="-")
    )

    st.download_button(
        label="📥 Descargar resultados en CSV",
        data=tabla.to_csv().encode("utf-8"),
        file_name=nombre_csv(calculo["inicio"], calculo["fin"]),
        mime="text/csv",
    )


if "calculo" in st.session_state:
    mostrar_calculo(st.session_state["calculo"])


# ------------------------------------------------------------------- Bot Mane
@st.cache_data(ttl=30, show_spinner=False)
def bot_esta_activo() -> bool:
    return bot_control.leer_activo()


@st.cache_data(ttl=60, show_spinner=False)
def ultima_vela() -> str | None:
    return bot_control.ultima_vela_revisada()


@st.cache_data(ttl=300, show_spinner=False)
def ultimos_cruces(n: int = 8) -> pd.DataFrame:
    df = descargar_m15()
    if df.empty:
        return pd.DataFrame()
    filas = [
        {
            "Vela (hora Argentina)": c.inicio_vela.tz_convert(TZ_MENSAJE).strftime(
                "%d/%m %H:%M"
            ),
            "Cruce": c.direccion,
            "Tipo": c.tipo,
            "Cierre": round(c.cierre, 1),
            f"SMA{SMA_FILTRO}": round(c.sma, 1),
        }
        for c in detectar_cruces(df)[-n:]
    ]
    return pd.DataFrame(filas[::-1])


@st.dialog("Confirmar cambio")
def confirmar_cambio(activar: bool) -> None:
    if activar:
        st.write("¿Seguro que querés **ACTIVAR** el Bot Mane?")
        st.caption(
            "Volverá a enviar alertas por WhatsApp desde la próxima revisión"
            " (se hace cada ~15 minutos)."
        )
    else:
        st.write("¿Seguro que querés **DESACTIVAR** el Bot Mane?")
        st.caption("Dejará de enviar alertas por WhatsApp hasta que lo vuelvas a activar.")

    col_si, col_no = st.columns(2)
    if col_si.button("Sí, confirmar", type="primary", use_container_width=True):
        try:
            bot_control.cambiar_activo(activar)
        except bot_control.ErrorControl as e:
            st.error(str(e))
            return
        bot_esta_activo.clear()
        st.session_state["aviso_bot"] = (
            "Bot Mane activado ✅" if activar else "Bot Mane desactivado ⏸️"
        )
        st.rerun()
    if col_no.button("Cancelar", use_container_width=True):
        st.rerun()


st.divider()
st.header("🤖 Bot Mane (cruce EMA13/34)")
st.write(
    f"Revisa {TICKER_BOT} en velas de {INTERVALO_MIN} minutos y avisa por"
    f" WhatsApp cuando la EMA{EMA_RAPIDA} cruza a la EMA{EMA_LENTA}. Según la"
    f" posición de la SMA{SMA_FILTRO} clasifica el cruce como **COMPRA**,"
    " **VENTA** o **ANALIZAR**."
)

if "aviso_bot" in st.session_state:
    st.toast(st.session_state.pop("aviso_bot"))

if not bot_control.configurado():
    st.info(
        "Para poder activar o desactivar el bot desde acá, cargá las variables"
        " de entorno `GITHUB_TOKEN` y `GITHUB_REPO` en Render."
    )
else:
    try:
        activo = bot_esta_activo()
    except bot_control.ErrorControl as e:
        activo = None
        st.error(f"No se pudo consultar el estado del bot. {e}")

    if activo is not None:
        if activo:
            st.success("🟢 Bot ACTIVO")
        else:
            st.warning("🔴 Bot DESACTIVADO")

        etiqueta = "⏸️ Desactivar bot" if activo else "▶️ Activar bot"
        if st.button(etiqueta):
            confirmar_cambio(not activo)

        ultima = ultima_vela()
        if ultima:
            hora = pd.Timestamp(ultima).tz_convert(TZ_MENSAJE)
            st.caption(
                f"Última vela procesada por el bot: {hora:%d/%m %H:%M}"
                " (hora Argentina)."
            )

if st.checkbox("Ver últimos cruces detectados"):
    with st.spinner("Calculando cruces..."):
        cruces = ultimos_cruces()
    if cruces.empty:
        st.warning("⚠️ Sin datos de velas M15 (mercado cerrado o Yahoo no respondió).")
    else:
        st.dataframe(cruces, hide_index=True)
        st.caption("Es un historial informativo; no envía ningún mensaje.")
