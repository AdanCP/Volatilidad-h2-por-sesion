"""Rango High-Low de las 2 primeras horas de cada sesión (Tokio, Londres, NY).

Se puede usar de dos formas:
  - Como módulo: lo importa app.py.
  - Por consola: python xauusd_sesiones.py
"""

from datetime import date, datetime, timedelta

import pandas as pd
import yfinance as yf

TICKER = "GC=F"  # Futuro de oro COMEX (no es spot XAU/USD)
HORAS_SESION = 2

# Sesión: (zona horaria, hora local de apertura).
# Se usa hora LOCAL para que el horario de verano se ajuste solo.
SESIONES = {
    "Tokio": ("Asia/Tokyo", 9),
    "Londres": ("Europe/London", 8),
    "Nueva York": ("America/New_York", 8),
}


def descargar(inicio: date, fin: date, ticker: str = TICKER) -> pd.DataFrame:
    """Descarga velas de 1h entre inicio y fin (ambos inclusive)."""
    # yfinance trata "end" como exclusivo, por eso se suma un día.
    fin_inclusivo = fin + timedelta(days=1)
    df = yf.download(
        ticker,
        start=inicio.isoformat(),
        end=fin_inclusivo.isoformat(),
        interval="1h",
        progress=False,
        auto_adjust=False,
    )
    if df.empty:
        return df
    # Algunas versiones de yfinance devuelven columnas multinivel
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    return df


def rango_sesion(df: pd.DataFrame, tz: str, hora_apertura: int) -> pd.Series:
    """Rango High-Low de las primeras HORAS_SESION horas, en hora local."""
    local = df.tz_convert(tz)
    hora = local.index.hour
    sesion = local[
        (hora >= hora_apertura) & (hora < hora_apertura + HORAS_SESION)
    ]
    grupos = sesion.groupby(sesion.index.date)
    rango = grupos["High"].max() - grupos["Low"].min()
    # Descartar sesiones incompletas (feriados, cierres anticipados)
    rango = rango.where(grupos["High"].count() >= HORAS_SESION)
    return rango.round(2)


def calcular_tabla(df: pd.DataFrame, inicio: date, fin: date) -> pd.DataFrame:
    """Tabla día por día con el rango de cada sesión."""
    tabla = pd.DataFrame(
        {
            f"{nombre} 2H ($)": rango_sesion(df, tz, hora)
            for nombre, (tz, hora) in SESIONES.items()
        }
    )
    tabla.index.name = "Fecha"
    tabla = tabla[(tabla.index >= inicio) & (tabla.index <= fin)]
    return tabla.dropna(how="all")


def estadisticas_objetivo(tabla: pd.DataFrame, objetivo: float) -> pd.DataFrame:
    """Por sesión: cuántas veces el rango alcanzó o superó el objetivo ($)."""
    filas = {}
    for columna in tabla.columns:
        medidas = tabla[columna].dropna()
        total = len(medidas)
        alcanzo = int((medidas >= objetivo).sum())
        filas[columna] = {
            "Sesiones medidas": total,
            "Veces que alcanzó": alcanzo,
            "% de veces": round(alcanzo / total * 100, 1) if total else None,
        }
    return pd.DataFrame.from_dict(filas, orient="index")


def nombre_csv(inicio: date, fin: date) -> str:
    return f"xauusd_{inicio:%d%m%Y}_a_{fin:%d%m%Y}.csv"


def _pedir_fecha(texto: str) -> date:
    while True:
        try:
            return datetime.strptime(input(texto), "%d/%m/%Y").date()
        except ValueError:
            print("[X] Formato inválido. Usá DD/MM/AAAA (ej. 23/09/2026).")


def _pedir_objetivo():
    while True:
        texto = (
            input("\nObjetivo en dólares (Enter para omitir): ")
            .strip()
            .replace(",", ".")
        )
        if not texto:
            return None
        try:
            valor = float(texto)
            if valor > 0:
                return valor
        except ValueError:
            pass
        print("[X] Ingresá un número mayor a 0 (ej. 12.5).")


def main() -> None:
    print("==========================================")
    print("   CALCULADORA DE SESIONES XAU/USD (ORO)    ")
    print("==========================================")

    inicio = _pedir_fecha("Fecha de INICIO (DD/MM/AAAA, ej. 23/09/2026): ")
    fin = _pedir_fecha("Fecha de FIN (DD/MM/AAAA, ej. 24/10/2026): ")
    if inicio > fin:
        print("\n[X] La fecha de inicio no puede ser posterior a la de fin.")
        return

    print(f"\n[+] Descargando {TICKER} desde {inicio:%d/%m/%Y} hasta {fin:%d/%m/%Y}...")
    df = descargar(inicio, fin)
    if df.empty:
        print(
            "\n[X] No se encontraron datos para ese rango. Recordá que Yahoo"
            " solo ofrece velas de 1h de los últimos ~730 días."
        )
        return

    tabla = calcular_tabla(df, inicio, fin)
    if tabla.empty:
        print("\n[X] No hay sesiones completas en ese rango de fechas.")
        return

    print("\n==========================================")
    print("        RESULTADOS DÍA POR DÍA ($)        ")
    print("==========================================")
    print(tabla.to_string())

    print("\n------------------------------------------")
    print("RESUMEN")
    print("------------------------------------------")
    print(tabla.agg(["mean", "median", "max"]).round(2).to_string())

    objetivo = _pedir_objetivo()
    if objetivo is not None:
        print(f"\nOBJETIVO DE ${objetivo:.2f} (rango >= objetivo)")
        print(estadisticas_objetivo(tabla, objetivo).to_string())

    archivo = nombre_csv(inicio, fin)
    tabla.to_csv(archivo)
    print(f"\n[Éxito] Tabla guardada como '{archivo}' en la carpeta actual.")


if __name__ == "__main__":
    main()
