"""Sesiones de mercado. Las ventanas se definen en HORA LOCAL de cada ciudad (zoneinfo),
asi el horario de verano se ajusta solo. Las velas de MT5 vienen en hora del servidor:
hay que convertirlas a UTC con el desfase del servidor (que debe medirse con el
mercado abierto; diagnostico_mt5.py lo estima)."""
import numpy as np
import pandas as pd

# nombre: (zona horaria, hora local de inicio, hora local de fin). Editables.
SESIONES_LOCAL = {
    "Tokio": ("Asia/Tokyo", 9.0, 18.0),
    "Londres": ("Europe/London", 8.0, 17.0),
    "Nueva York": ("America/New_York", 8.0, 17.0),
}


def _domingo(anio: int, mes: int, n: int) -> pd.Timestamp:
    d = pd.Timestamp(anio, mes, 1)
    primero = d + pd.Timedelta(days=(6 - d.dayofweek) % 7)
    return primero + pd.Timedelta(weeks=n - 1)


def en_dst_eeuu(indice: pd.DatetimeIndex) -> np.ndarray:
    """True durante el horario de verano de EEUU (2.º domingo de marzo al 1.º de
    noviembre). Aproximado al dia: error de unas horas en 2 fechas por año."""
    out = np.zeros(len(indice), dtype=bool)
    for y in np.unique(indice.year):
        ini, fin = _domingo(int(y), 3, 2), _domingo(int(y), 11, 1)
        out |= (indice >= ini) & (indice < fin) & (indice.year == y)
    return out


def servidor_a_utc(indice: pd.DatetimeIndex, offset_horas: float, dst_eeuu: bool = True) -> pd.DatetimeIndex:
    """Hora del servidor (naive) -> UTC (naive). offset_horas es el desfase en INVIERNO
    (por ej. 2 para GMT+2); con dst_eeuu=True suma 1 hora durante el verano de EEUU, que es
    la convencion de muchos brokers (GMT+2/+3). Verificar con el servidor real."""
    off = np.full(len(indice), float(offset_horas))
    if dst_eeuu:
        off = off + en_dst_eeuu(indice)
    return indice - pd.to_timedelta(off, unit="h")


def mascara_sesiones(indice_utc: pd.DatetimeIndex, nombres, horarios=None) -> np.ndarray:
    """True si la vela cae en AL MENOS UNA de las sesiones elegidas (solapamientos
    validos). Ventana [inicio, fin) en hora local; admite ventanas que cruzan medianoche."""
    horarios = horarios or SESIONES_LOCAL
    ok = np.zeros(len(indice_utc), dtype=bool)
    base = indice_utc.tz_localize("UTC")
    for nombre in nombres:
        if nombre not in horarios:
            raise ValueError(f"Sesion desconocida: {nombre}")
        zona, ini, fin = horarios[nombre]
        try:
            loc = base.tz_convert(zona)
        except Exception as e:  # ZoneInfoNotFoundError en Windows sin tzdata
            raise RuntimeError(f"No se pudo cargar la zona horaria {zona} (pip install tzdata): {e}")
        h = loc.hour.to_numpy() + loc.minute.to_numpy() / 60.0
        ok |= (h >= ini) & (h < fin) if ini < fin else (h >= ini) | (h < fin)
    return ok
