import pandas as pd
import yfinance as yf

print("==========================================")
print("   CALCULADORA DE SESIONES XAU/USD (ORO)    ")
print("==========================================")

# Solicitar fechas en formato latino / europeo (dd/mm/aaaa)
input_inicio = input(
    "Ingresa la fecha de INICIO (Formato DD/MM/AAAA, ej. 23/09/2026): "
)
input_fin = input(
    "Ingresa la fecha de FIN (Formato DD/MM/AAAA, ej. 24/10/2026): "
)

try:
  # Convertir el texto dd/mm/aaaa al formato que entiende la API (yyyy-mm-dd)
  start_date = pd.to_datetime(input_inicio, format="%d/%m/%Y").strftime(
      "%Y-%m-%d"
  )
  end_date = pd.to_datetime(input_fin, format="%d/%m/%Y").strftime("%Y-%m-%d")
except ValueError:
  print(
      "\n[X] Error: El formato de fecha ingresado no es válido. Asegúrate de"
      " usar DD/MM/AAAA (ej. 23/09/2026)."
  )
  exit()

ticker = "GC=F"

print(
    f"\n[+] Descargando datos históricos de {ticker} desde {input_inicio} hasta"
    f" {input_fin}..."
)

# Descargar datos en velas de 1 hora
df = yf.download(
    ticker, start=start_date, end=end_date, interval="1h", progress=False
)

if df.empty:
  print(
      "\n[X] No se encontraron datos para ese rango. Verifica que las fechas"
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
      mask = (grupo.index.hour >= hora_inicio) & (grupo.index.hour < hora_fin)
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

  print("\n==========================================")
  print("        RESULTADOS DÍA POR DÍA ($)        ")
  print("==========================================")
  print(tabla_final.to_string())

  # Exportar automáticamente a un CSV con nombre limpio (usando guiones bajos para el archivo)
  archivo_salida = (
      f"xauusd_{start_date.replace('-', '')}_a_{end_date.replace('-', '')}.csv"
  )
  tabla_final.to_csv(archivo_salida)
  print(
      f"\n[Éxito] ¡Tabla guardada automáticamente como '{archivo_salida}' en tu"
      " carpeta!"
  )