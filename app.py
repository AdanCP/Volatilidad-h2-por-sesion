import pandas as pd
import streamlit as st
import yfinance as yf

# Configuración de la página web
st.set_page_config(
    page_title="XAU/USD - Calculadora de Sesiones",
    page_icon="📈",
    layout="centered",
)

st.title("📈 XAU/USD - Movimiento de las Sesiones")
st.write(
    "Calcula el movimiento exacto en **dólares ($)** durante las dos primeras"
    " horas de Tokio, Londres y Nueva York."
)

# Barra lateral para los controles
st.sidebar.header("Parámetros de Búsqueda")
input_inicio = st.sidebar.text_input(
    "Fecha de Inicio (DD/MM/AAAA)", "23/09/2026"
)
input_fin = st.sidebar.text_input("Fecha de Fin (DD/MM/AAAA)", "24/10/2026")

ticker = "GC=F"

# Botón para ejecutar el cálculo
if st.sidebar.button("Calcular Movimientos", type="primary"):
  try:
    # Convertir de DD/MM/AAAA a formato ISO para Yahoo Finance
    start_date = pd.to_datetime(input_inicio, format="%d/%m/%Y").strftime(
        "%Y-%m-%d"
    )
    end_date = pd.to_datetime(input_fin, format="%d/%m/%Y").strftime("%Y-%m-%d")
  except ValueError:
    st.error(
        "❌ Formato de fecha inválido. Utiliza estrictamente el formato"
        " DD/MM/AAAA (ej. 23/09/2026)."
    )
    st.stop()

  with st.spinner("Descargando datos y procesando rangos..."):
    df = yf.download(
        ticker, start=start_date, end=end_date, interval="1h", progress=False
    )

    if df.empty:
      st.warning(
          "⚠️ No se encontraron datos para ese rango de fechas. Verifica que"
          " sean correctas."
      )
    else:
      # Limpieza de formato si la librería devuelve columnas multinivel
      if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

      # Asegurar zona horaria UTC
      if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
      else:
        df.index = df.index.tz_convert("UTC")


      # Función para calcular el rango High - Low por sesión
      def calcular_rango_sesion(data, hora_inicio, hora_fin):
        resultados = []
        for fecha, grupo in data.groupby(data.index.date):
          mask = (grupo.index.hour >= hora_inicio) & (
              grupo.index.hour < hora_fin
          )
          sesion_df = grupo[mask]
          if not sesion_df.empty:
            rango = float(sesion_df["High"].max() - sesion_df["Low"].min())
            resultados.append({"Fecha": fecha, "Rango_USD": round(rango, 2)})
          else:
            resultados.append({"Fecha": fecha, "Rango_USD": None})
        return pd.DataFrame(resultados).set_index("Fecha")


      # Franjas horarias UTC:
      # - Tokio: 00:00 a 02:00 UTC
      # - Londres: 07:00 a 09:00 UTC
      # - Nueva York: 13:00 a 15:00 UTC
      df_tokio = calcular_rango_sesion(df, 0, 2)
      df_londres = calcular_rango_sesion(df, 7, 9)
      df_ny = calcular_rango_sesion(df, 13, 15)

      tabla_final = pd.DataFrame(
          {
              "Tokio 2H ($)": df_tokio["Rango_USD"],
              "Londres 2H ($)": df_londres["Rango_USD"],
              "Nueva York 2H ($)": df_ny["Rango_USD"],
          }
      )

      st.success("¡Datos procesados con éxito!")

      # Mostrar tabla interactiva en la web
      st.dataframe(tabla_final, use_container_width=True)

      # Botón de descarga directa para CSV
      csv = tabla_final.to_csv().encode("utf-8")
      nombre_archivo = (
          f"xauusd_{input_inicio.replace('/', '')}_a_{input_fin.replace('/', '')}.csv"
      )
      st.download_button(
          label="📥 Descargar resultados en CSV",
          data=csv,
          file_name=nombre_archivo,
          mime="text/csv",
      )