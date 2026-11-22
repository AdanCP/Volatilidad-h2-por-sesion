"""Capa de datos: MT5 directo (por tramos), CSV exportado de MT5 y datos sinteticos.
Todas las fuentes se normalizan a un DataFrame con indice de fecha (hora del servidor,
sin zona horaria) y columnas Open, High, Low, Close, Volume y Spread (en unidades de precio)."""
import sys
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

TF_MT5 = {"M1": "TIMEFRAME_M1", "M5": "TIMEFRAME_M5", "M15": "TIMEFRAME_M15",
          "M30": "TIMEFRAME_M30", "H1": "TIMEFRAME_H1", "H4": "TIMEFRAME_H4",
          "D1": "TIMEFRAME_D1", "W1": "TIMEgiFRAME_W1"}
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


MODOS_CALCULO_CFD = (0, 2, 3, 4, 5)      # forex, CFD, CFD indices, CFD con apalancamiento, forex sin apalancamiento (de ENUM_SYMBOL_CALC_MODE)


def corregir_tick_value(spec: dict) -> dict:
    """Algunos servidores informan mal el valor del tick (p. ej. 0,01 en vez de 1 en el oro). Para forex y CFD con beneficio en la
    moneda de la cuenta, el dinero por cada 1.00 de precio y por lote es el tamano del contrato (el que usa el servidor para calcular el
    resultado real): si el tick_value informado no cuadra (mas de 1 %), se reemplaza por contrato * tick_size y se deja anotado."""
    ts, tv, cs = float(spec.get("tick_size") or 0), float(spec.get("tick_value") or 0), float(spec.get("contrato") or 0)
    if (cs > 0 and ts > 0 and spec.get("modo_calculo") in MODOS_CALCULO_CFD and spec.get("moneda_beneficio")
            and spec.get("moneda_beneficio") == spec.get("moneda_cuenta")):
        esperado = cs * ts
        if not tv > 0 or abs(tv - esperado) > 0.01 * esperado:
            spec = dict(spec, tick_value_informado=tv, tick_value=esperado, tick_value_corregido=True)
    return spec


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
        cuenta = mt5.account_info()
        spec = {"simbolo": simbolo, "point": info.point, "digits": info.digits,
                "contrato": info.trade_contract_size, "tick_size": info.trade_tick_size,
                "tick_value": info.trade_tick_value, "vol_min": info.volume_min,
                "vol_max": info.volume_max, "vol_step": info.volume_step,
                "moneda_beneficio": info.currency_profit, "modo_calculo": info.trade_calc_mode,
                "moneda_cuenta": cuenta.currency if cuenta is not None else ""}
        spec = corregir_tick_value(spec)
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
    if "point" in df:                       # CSV de exportar_mt5.py: trae el point de cada simbolo
        point = df["point"].to_numpy(float)
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


def corregir_hora(df: pd.DataFrame, tramos) -> tuple:
    """Corrige un historial cuya hora esta corrida. `tramos` es una lista de (antes_de, horas): a cada vela con hora
    ANTERIOR a `antes_de` se le restan `horas` horas (varios tramos se acumulan). Las velas con la misma hora que quedan en
    el empalme se reducen a una: la del tramo ya correcto (la posterior). Devuelve (df nuevo, info). No toca el original."""
    tramos = [(pd.Timestamp(f), float(h)) for f, h in (tramos or []) if float(h) != 0.0]
    if not tramos or not len(df):
        return df, {"tramos": [], "velas_corridas": 0, "duplicadas_quitadas": 0}
    idx = pd.DatetimeIndex(df.index)
    horas = np.zeros(len(idx))
    for antes_de, h in tramos:
        horas += np.where(idx < antes_de, h, 0.0)
    out = df.copy()
    out.index = idx - pd.to_timedelta(horas, unit="h")
    out = out.sort_index(kind="stable")
    dup = out.index.duplicated(keep="last")
    return out[~dup], {"tramos": [(str(f.date()), h) for f, h in tramos], "velas_corridas": int((horas != 0).sum()),
                       "duplicadas_quitadas": int(dup.sum())}


def detectar_salto_horario(df: pd.DataFrame, min_semanas: int = 8) -> list:
    """Busca cambios de huso horario en el historial. En un servidor que sigue el horario de EE.UU. la apertura semanal del
    mercado cae siempre a la misma hora; si esa hora cambia de golpe y se mantiene por `min_semanas` semanas o mas, el historial
    cambio de huso. Los cambios cortos (las semanas en que Europa y EE.UU. cambian de horario en fechas distintas) se ignoran.
    Devuelve una lista de {"fecha", "de", "a", "horas"} (vacia si no hay salto); no corrige nada."""
    if len(df) < 2:
        return []
    idx = pd.DatetimeIndex(df.index)
    inicios = np.flatnonzero(np.diff(idx.values).astype("timedelta64[s]").astype(float) > 30 * 3600) + 1
    if len(inicios) < 2 * min_semanas:
        return []
    horas = idx[inicios].hour.to_numpy()
    fechas = idx[inicios]
    corridas, ini = [], 0                                   # tramos de semanas seguidas con la misma hora de apertura
    for k in range(1, len(horas) + 1):
        if k == len(horas) or horas[k] != horas[ini]:
            corridas.append((int(horas[ini]), ini, k - ini))
            ini = k
    largas = [c for c in corridas if c[2] >= min_semanas]
    cambios = []
    for (h0, _, _), (h1, i1, _) in zip(largas, largas[1:]):
        if h1 != h0:
            cambios.append({"fecha": fechas[i1], "de": h0, "a": h1, "horas": h1 - h0})
    return cambios


def velas_sospechosas(df: pd.DataFrame, k_vol: float = 5.0, k_rango: float = 5.0) -> dict:
    """Velas corruptas por exportaciones mal armadas: una vela que resume una hora o un dia entero (volumen y rango muy por encima de lo
    normal para su hora del dia) y que se repite siempre en el mismo minuto. Un pico aislado por una noticia no se marca: tiene que haber
    un patron de minuto (al menos 20 velas extremas en el anio y el 60 % o mas en el mismo minuto). Como el patron ya filtra las noticias,
    el volumen exigido es de 5 veces la mediana de su hora (una vela que resume una hora trae ~12 velas de volumen, pero con ruido puede
    quedar en 10 veces o menos) y el rango de 5 veces. Devuelve el aviso y la mascara."""
    n = len(df)
    vacio = {"mascara": np.zeros(n, dtype=bool), "extremas": 0, "sospechosas": 0, "anios": [], "spread0_minutos": []}
    if n < 500 or "Volume" not in df:
        return vacio
    idx = pd.DatetimeIndex(df.index)
    rango = (df["High"] - df["Low"]).to_numpy(float)
    vol = df["Volume"].to_numpy(float)
    hora = idx.hour.to_numpy()
    med_r = pd.Series(rango).groupby(hora).transform("median").to_numpy()
    med_v = pd.Series(vol).groupby(hora).transform("median").to_numpy()
    extrema = (med_v > 0) & (med_r > 0) & (vol > k_vol * med_v) & (rango > k_rango * med_r)
    minuto, anio = idx.minute.to_numpy(), idx.year.to_numpy()
    mascara, anios = np.zeros(n, dtype=bool), []
    for y in np.unique(anio[extrema]):
        sel = extrema & (anio == y)
        if sel.sum() < 20:
            continue
        m_tip = int(pd.Series(minuto[sel]).mode().iloc[0])
        if (minuto[sel] == m_tip).mean() < 0.6:
            continue
        marca = sel & (minuto == m_tip)
        mascara |= marca
        anios.append({"anio": int(y), "velas": int(marca.sum()), "minuto": m_tip,
                      "pct_del_anio": round(100 * float(marca.sum()) / float((anio == y).sum()), 2)})
    spread0 = []
    if "Spread" in df and 0.02 < float((df["Spread"] == 0).mean()) < 0.9:
        z = (df["Spread"].to_numpy(float) == 0)
        for y in np.unique(anio):
            sy = anio == y
            if sy.sum() < 2000:
                continue
            por_min = pd.Series(z[sy]).groupby(minuto[sy]).mean()
            if len(por_min) < 3:
                continue
            for m, v in por_min.items():
                if v >= 0.5 and v - float(por_min.drop(m).median()) >= 0.3:
                    spread0.append({"anio": int(y), "minuto": int(m), "pct_spread_cero": round(100 * float(v), 0)})
    return {"mascara": mascara, "extremas": int(extrema.sum()), "sospechosas": int(mascara.sum()), "anios": anios,
            "spread0_minutos": spread0}


def excluir_velas(df: pd.DataFrame, mascara) -> pd.DataFrame:
    """Saca del historial las velas marcadas (el resto queda igual)."""
    return df[~np.asarray(mascara, dtype=bool)]


def calidad(df: pd.DataFrame) -> dict:
    """Resumen de calidad: huecos grandes, duplicadas, NaN y % de spreads en cero."""
    dif = np.diff(df.index.values).astype("timedelta64[s]").astype(float) if len(df) > 1 else np.array([0.0])
    return {"velas": len(df), "primera": str(df.index[0]), "ultima": str(df.index[-1]),
            "huecos_mas_de_4d": int((dif > 4 * 86400).sum()),
            "mayor_hueco_dias": round(float(dif.max()) / 86400, 1),
            "duplicadas": int(df.index.duplicated().sum()),
            "con_nan": int(df[["Open", "High", "Low", "Close"]].isna().any(axis=1).sum()),
            "spread_cero_pct": round(100 * float((df["Spread"] == 0).mean()), 1),
            "sospechosas": (lambda v: {"velas": v["sospechosas"], "anios": v["anios"], "spread0_minutos": v["spread0_minutos"]})(velas_sospechosas(df))}


# ------------------------------------------------- simbolos candidatos por familia
CANDIDATOS = {
    "oro": ["XAUUSD", "GOLD"], "plata": ["XAGUSD", "SILVER"], "btc": ["BTCUSD"],
    "EURUSD": ["EURUSD"], "GBPUSD": ["GBPUSD"], "USDJPY": ["USDJPY"], "USDCHF": ["USDCHF"],
    "AUDUSD": ["AUDUSD"], "USDCAD": ["USDCAD"], "NZDUSD": ["NZDUSD"],
    "Dow Jones": ["US30", "DJ30", "WS30"], "Nasdaq 100": ["US100", "NAS100", "USTEC"],
    "S&P 500": ["US500", "SPX500", "SP500"], "DAX": ["GER40", "DE40", "DAX"],
    "FTSE 100": ["UK100", "FTSE100"], "Nikkei": ["JP225", "JPN225", "NIKKEI"],
}


def detectar_simbolos(nombres) -> dict:
    """Para cada candidato, el simbolo mas corto del servidor cuyo nombre empieza igual (o None)."""
    hallados = {}
    for etiqueta, bases in CANDIDATOS.items():
        hallados[etiqueta] = None
        for base in bases:
            m = sorted([n for n in nombres if n.upper().startswith(base)], key=len)
            if m:
                hallados[etiqueta] = m[0]
                break
    return hallados


def listar_simbolos_mt5() -> list:
    mt5 = _importar_mt5()
    if not mt5.initialize():
        raise ErrorDatos(f"No se pudo conectar al terminal MT5: {mt5.last_error()}")
    try:
        return [s.name for s in (mt5.symbols_get() or [])]
    finally:
        mt5.shutdown()


def exportar_df(df: pd.DataFrame, point: float) -> pd.DataFrame:
    """DataFrame normalizado -> tabla lista para guardar como CSV (la lee cargar_csv).
    El spread se guarda en PUNTOS y se agrega la columna 'point' para poder reconstruirlo."""
    return pd.DataFrame({
        "time": df.index.strftime("%Y-%m-%d %H:%M:%S"),
        "open": df["Open"].to_numpy(), "high": df["High"].to_numpy(),
        "low": df["Low"].to_numpy(), "close": df["Close"].to_numpy(),
        "tick_volume": df["Volume"].to_numpy(),
        "spread": np.rint(df["Spread"].to_numpy() / point).astype(int),
        "point": point})


# ------------------------------------------------- datos sincronizados (carpeta datos_mt5 del repo)
CARPETA_SYNC = "datos_mt5"


def ruta_sync(carpeta: str, simbolo: str, tf: str) -> str:
    import os
    return os.path.join(carpeta, f"{simbolo}_{tf}.csv.gz")


def guardar_sync(df: pd.DataFrame, spec: dict, carpeta: str, simbolo: str, tf: str) -> str:
    """Guarda un simbolo/temporalidad comprimido (bytes reproducibles: sin fecha en el gzip)."""
    import os
    os.makedirs(carpeta, exist_ok=True)
    ruta = ruta_sync(carpeta, simbolo, tf)
    exportar_df(df, spec["point"]).to_csv(ruta, index=False, compression={"method": "gzip", "mtime": 0})
    return ruta


def leer_manifest(carpeta: str) -> dict:
    """{'sincronizado': str, 'simbolos': {sim: {'spec': {...}, 'tfs': {tf: {velas, desde, hasta}}}}} o {} si no hay."""
    import json
    import os
    ruta = os.path.join(carpeta, "manifest.json")
    if not os.path.exists(ruta):
        return {}
    with open(ruta, encoding="utf-8") as f:
        return json.load(f)


def escribir_manifest(carpeta: str, manifest: dict) -> None:
    import json
    import os
    os.makedirs(carpeta, exist_ok=True)
    with open(os.path.join(carpeta, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=1, ensure_ascii=False, sort_keys=True)


def cargar_sync(carpeta: str, simbolo: str, tf: str) -> pd.DataFrame:
    import os
    ruta = ruta_sync(carpeta, simbolo, tf)
    if not os.path.exists(ruta):
        raise ErrorDatos(f"No hay datos sincronizados de {simbolo} {tf}.")
    return cargar_csv(ruta)
