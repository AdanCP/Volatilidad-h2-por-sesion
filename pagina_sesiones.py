from datetime import date

import streamlit as st

import ui_estilo as vis

from xauusd_sesiones import (
    TICKER,
    calcular_tabla,
    descargar,
    estadisticas_objetivo,
    nombre_csv,
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


st.html(vis.barra_superior(
    "XAU/USD · Movimiento de las sesiones",
    "Rango High-Low en dólares durante las dos primeras horas de Tokio, Londres y Nueva York.",
    [("Desde", f"{fecha_inicio:%d/%m/%Y}"), ("Hasta", f"{fecha_fin:%d/%m/%Y}"), ("Objetivo", f"${objetivo:,.2f}")]))
st.html(
    f'<div class="note">Datos de {TICKER} (futuro de oro COMEX, no spot XAU/USD) vía Yahoo Finance. '
    "Aperturas: Tokio 09:00 JST, Londres 08:00 local, Nueva York 08:00 ET. "
    "El horario de verano se ajusta automáticamente.</div>")


@st.cache_data(ttl=900, show_spinner=False)
def descargar_cacheado(inicio: date, fin: date):
    return descargar(inicio, fin)


# ------------------------------------------------------------------ Calculador
# El resultado se guarda en session_state para que no desaparezca cuando la
# página se vuelve a ejecutar (por ejemplo al descargar el CSV).
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


def corto(columna: str) -> str:
    return columna.replace(" 2H ($)", "")


def mostrar_calculo(calculo: dict) -> None:
    if "aviso" in calculo:
        tipo, texto = calculo["aviso"]
        getattr(st, tipo)(texto)
        return

    tabla = calculo["tabla"]
    resumen = tabla.agg(["mean", "median", "max"])
    stats = estadisticas_objetivo(tabla, objetivo)

    # ---- anillos: % de sesiones que alcanzaron el objetivo
    cols = st.columns(len(tabla.columns))
    for k, columna in enumerate(tabla.columns):
        fila = stats.loc[columna]
        pct = fila["% de veces"]
        with cols[k]:
            st.html(vis.anillo(
                pct if pct is not None else 0, corto(columna),
                f"{int(fila['Veces que alcanzó'])} de {int(fila['Sesiones medidas'])} sesiones<br>"
                f"promedio ${vis.n(resumen.loc['mean', columna])} · máx ${vis.n(resumen.loc['max', columna])}",
                uid=f"s{k}"))

    st.write("")
    c1, c2 = st.columns([3, 2])
    with c1:
        filas = [[nombre] + [vis.n(resumen.loc[clave, c]) if resumen.loc[clave, c] == resumen.loc[clave, c] else "–"
                             for c in tabla.columns]
                 for nombre, clave in (("Promedio", "mean"), ("Mediana", "median"), ("Máximo", "max"))]
        st.html(vis.tarjeta("Resumen del rango (US$)", vis.tabla_html([""] + [corto(c) for c in tabla.columns], filas),
                            "Rango High-Low de las dos primeras horas de cada sesión."))
    with c2:
        st.html(vis.tarjeta("Rango promedio por sesión (US$)", vis.barras_verticales(
            [(corto(c), float(resumen.loc["mean", c]), f"máx {vis.n(resumen.loc['max', c], 1)}") for c in tabla.columns], signo=False)))

    st.write("")
    partes = []
    for columna in tabla.columns:
        fila = stats.loc[columna]
        if fila["Sesiones medidas"]:
            partes.append(f"<b>{corto(columna)}</b> lo alcanzó en {int(fila['Veces que alcanzó'])} de "
                          f"{int(fila['Sesiones medidas'])} sesiones ({vis.n(fila['% de veces'], 1)}%)")
    st.html(vis.insight(f"Objetivo de ${vis.n(objetivo)}",
                        "; ".join(partes) + ".<br><br>Describe el período elegido; no predice las sesiones futuras."))

    st.write("")
    nd = lambda v: vis.n(v, 2) if v == v else "–"
    filas = [[f"{idx:%d/%m/%Y}"] + [nd(v) for v in fila] for idx, fila in zip(tabla.index, tabla.to_numpy())]
    st.html(vis.tarjeta(
        "Detalle diario (US$)",
        vis.tabla_html(["Fecha"] + [corto(c) for c in tabla.columns], filas, max_alto=420,
                       resaltar=lambda i, j: tabla.iat[i, j - 1] >= objetivo),
        "En violeta, los días en que se alcanzó el objetivo.", f"{len(tabla)} días"))
    st.download_button(
        label="📥 Descargar resultados en CSV",
        data=tabla.to_csv().encode("utf-8"),
        file_name=nombre_csv(calculo["inicio"], calculo["fin"]),
        mime="text/csv",
    )


if "calculo" in st.session_state:
    mostrar_calculo(st.session_state["calculo"])
