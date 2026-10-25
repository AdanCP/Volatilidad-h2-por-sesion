from datetime import date

import numpy as np
import pandas as pd
import streamlit as st

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


if st.sidebar.button("Calcular Movimientos", type="primary"):
    if fecha_inicio > fecha_fin:
        st.error("❌ La fecha de inicio no puede ser posterior a la de fin.")
        st.stop()

    with st.spinner("Descargando datos y procesando rangos..."):
        df = descargar_cacheado(fecha_inicio, fecha_fin)

    if df.empty:
        st.warning(
            "⚠️ No se encontraron datos para ese rango. Recordá que Yahoo"
            " solo ofrece velas de 1h de los últimos ~730 días."
        )
        st.stop()

    tabla = calcular_tabla(df, fecha_inicio, fecha_fin)
    if tabla.empty:
        st.warning("⚠️ No hay sesiones completas en ese rango de fechas.")
        st.stop()

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
        file_name=nombre_csv(fecha_inicio, fecha_fin),
        mime="text/csv",
    )
