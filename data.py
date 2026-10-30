"""Capa de datos: MT5 directo (por tramos), CSV exportado de MT5 y datos sinteticos.
Todas las fuentes se normalizan a un DataFrame con indice de fecha (hora del servidor,
sin zona horaria) y columnas Open, High, Low, Close, Volume y Spread (en unidades de precio)."""
import sys
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

TF_MT5 = {"M1": "TIMEFRAME_M1", "M5": "TIMEFRAME_M5", "M15": "TIMEFRAME_M15",
          "M30": "TIMEFRAME_M30", "H1": "TIMEFRAME_H1", "H4": "TIMEFRAME_H4",
          "D1": "TIMEFRAME_D1", "W1": "TIMEFRAME_W1"}
# Dias por tramo: un pedido unico de todo el rango falla con "Invalid params".
PASO_DIAS = {"W1": 3650, "D1": 3650, "H4": 1825, "H1": 730, "M30": 365, "M15": 365, "M5": 90, "M1": 30}
COLUMNAS = ["Open", "High", "Low", "Close", "Volume", "Spread"]


class ErrorDatos(Exception):
    """Falla de datos con mensaje listo para mostrar al usuario."""


def unir_tramos(partes) -> np.ndarray:
    """Une arrays estructurados de MT5 sin velas repetidas (los bordes de tramo se pisan)."""
    a = np.concatenate(partes)
    _, idx = np.unique(a["time"], return_index=True)
    return a[np.sort(idx)]


def descargar_por_tramos(fetch, desde: datetime, hasta: datetime, paso_dias: int, progreso=None):
    """fetch(ini, fin) -> array o None. Devuelve (array unido o None, tramos_sin_datos)."""
    partes, sin_datos, ini = [], 0, desde
    while ini < hasta:
        fin = min(ini + timedelta(days=paso_dias), hasta)
        r = fetch(ini, fin)
        if r is not None and len(r):
            partes.append(r)
        else:
            sin_datos += 1
        if progreso:
            progreso()
        ini = fin
    return (unir_tramos(partes) if partes else None), sin_datos


def rates_a_df(rates: np.ndarray, point: float) -> pd.DataFrame:
    idx = pd.DatetimeIndex(pd.to_datetime(rates["time"], unit="s"))
    return pd.DataFrame({"Open": rates["open"], "High": rates["high"], "Low": rates["low"],
                         "Close": rates["close"], "Volume": rates["tick_volume"],
                         "Spread": rates["spread"].astype(float) * point}, index=idx)


def _importar_mt5():
    try:
        import MetaTrader5 as mt5
        return mt5
    except ImportError:
        raise ErrorDatos("Falta la libreria: pip install MetaTrader5 (solo Windows).")


def cargar_mt5(simbolo: str, tf: str, desde, hasta=None, progreso=None):
    """Devuelve (df, spec_simbolo, tramos_sin_datos). Requiere MT5 abierto y con sesion iniciada."""
    mt5 = _importar_mt5()
    if not mt5.initialize():
        raise ErrorDatos(f"No se pudo conectar al terminal MT5: {mt5.last_error()}. Revisa que este "
                         "abierto, con sesion iniciada, y que Python y MT5 sean de 64 bits.")
    try:
        info = mt5.symbol_info(simbolo)
        if info is None:
            raise ErrorDatos(f"El simbolo {simbolo} no existe en este servidor.")
        mt5.symbol_select(simbolo, True)
        spec = {"simbolo": simbolo, "point": info.point, "digits": info.digits,
                "contrato": info.trade_contract_size, "tick_size": info.trade_tick_size,
                "tick_value": info.trade_tick_value, "vol_min": info.volume_min,
                "vol_max": info.volume_max, "vol_step": info.volume_step}
        tf_c = getattr(mt5, TF_MT5[tf])
        hasta_dt = pd.Timestamp(hasta).to_pydatetime() if hasta else datetime.now()
        rates, sin_datos = descargar_por_tramos(
            lambda i, f: mt5.copy_rates_range(simbolo, tf_c, i, f),
            pd.Timestamp(desde).to_pydatetime(), hasta_dt, PASO_DIAS[tf], progreso)
        if rates is None:
            raise ErrorDatos(f"MT5 no devolvio velas para {simbolo} {tf} ({mt5.last_error()}).")
    finally:
        mt5.shutdown()
    return rates_a_df(rates, info.point), spec, sin_datos


def cargar_csv(archivo: str, point: float = 0.01) -> pd.DataFrame:
    """CSV exportado de MT5 (<DATE> <TIME> <OPEN>...) o con columnas time/open/high/low/close."""
    df = pd.read_csv(archivo, sep=None, engine="python")
    df.columns = [c.strip("<> ").lower() for c in df.columns]
    if "date" in df and "time" in df:
        idx = pd.DatetimeIndex(pd.to_datetime(df["date"].astype(str) + " " + df["time"].astype(str)))
    else:
        col = next((c for c in ("time", "datetime", "date") if c in df), None)
        if col is None:
            raise ErrorDatos("El CSV necesita columnas de fecha/hora (date+time, time o datetime).")
        idx = pd.DatetimeIndex(pd.to_datetime(df[col]))
    faltan = [c for c in ("open", "high", "low", "close") if c not in df]
    if faltan:
        raise ErrorDatos(f"Faltan columnas en el CSV: {faltan}")
    vol = df["tickvol"] if "tickvol" in df else (df["tick_volume"] if "tick_volume" in df else 0)
    out = pd.DataFrame({"Open": df["open"].to_numpy(), "High": df["high"].to_numpy(),
                        "Low": df["low"].to_numpy(), "Close": df["close"].to_numpy(),
                        "Volume": np.asarray(vol) if np.ndim(vol) else 0,
                        "Spread": df["spread"].to_numpy() * point if "spread" in df else 0.0}, index=idx)
    return out.sort_index()


def sintetico(n=30000, tendencia=0.0, seed=1, precio=2000.0, sigma=3.0, spread=0.3) -> pd.DataFrame:
    """Serie de prueba. tendencia=0 -> paseo aleatorio puro (sin ventaja posible)."""
    rng = np.random.default_rng(seed)
    z = np.zeros(n)
    for i in range(1, n):
        z[i] = 0.98 * z[i - 1] + rng.normal()
    drift = tendencia * sigma * z / (z.std() + 1e-12)
    close = precio + np.cumsum(drift + rng.normal(0, sigma, n))
    open_ = np.r_[precio, close[:-1]]
    high = np.maximum(open_, close) + np.abs(rng.normal(0, sigma * 0.4, n))
    low = np.minimum(open_, close) - np.abs(rng.normal(0, sigma * 0.4, n))
    idx = pd.date_range("2018-01-01", periods=n, freq="h")
    return pd.DataFrame({"Open": open_, "High": high, "Low": low, "Close": close,
                         "Volume": 1, "Spread": spread}, index=idx)


def resamplear(df: pd.DataFrame, regla: str) -> pd.DataFrame:
    """Construye una temporalidad mayor (ej. '4h') con OHLC correcto."""
    agg = {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum", "Spread": "last"}
    return df.resample(regla).agg(agg).dropna(subset=["Open"])


def calidad(df: pd.DataFrame) -> dict:
    """Resumen de calidad: huecos grandes, duplicadas, NaN y % de spreads en cero."""
    dif = np.diff(df.index.values).astype("timedelta64[s]").astype(float) if len(df) > 1 else np.array([0.0])
    return {"velas": len(df), "primera": str(df.index[0]), "ultima": str(df.index[-1]),
            "huecos_mas_de_4d": int((dif > 4 * 86400).sum()),
            "mayor_hueco_dias": round(float(dif.max()) / 86400, 1),
            "duplicadas": int(df.index.duplicated().sum()),
            "con_nan": int(df[["Open", "High", "Low", "Close"]].isna().any(axis=1).sum()),
            "spread_cero_pct": round(100 * float((df["Spread"] == 0).mean()), 1)}
