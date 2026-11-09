"""Sesiones de mercado. Las ventanas se definen en HORA LOCAL de cada ciudad (zoneinfo),
asi el horario de verano se ajusta solo. Las velas de MT5 vienen en hora del servidor:
hay que convertirlas a UTC con el desfase del servidor (que debe medirse con el
mercado abierto; diagnostico_mt5.py lo estima)."""
from datetime import date, datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

# nombre: (zona horaria, hora local de inicio, hora local de fin) = apertura y cierre de la bolsa. Editables.
SESIONES_LOCAL = {
    "Tokio": ("Asia/Tokyo", 9.0, 15.5),                # bolsa de Tokio: 9:00 a 15:30 (cierre extendido desde nov-2024)
    "Londres": ("Europe/London", 8.0, 16.5),           # bolsa de Londres: 8:00 a 16:30
    "Nueva York": ("America/New_York", 9.5, 16.0),     # NYSE: 9:30 a 16:00
}

# Pausa de mediodia de cada sesion (definicion del usuario), en HORA LOCAL de la plaza: asi el horario de verano de Londres y
# Nueva York la corre solo en hora Argentina. Valores fijos. Hoy en hora Argentina: Tokio 23:30-00:30, Londres 09:00-10:00,
# Nueva York 14:00-16:00.
PAUSAS_LOCAL = {
    "Tokio": ("Asia/Tokyo", 11.5, 12.5),
    "Londres": ("Europe/London", 12.0, 13.0),
    "Nueva York": ("America/New_York", 12.0, 14.0),
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


def mascara_sesiones(indice_utc: pd.DatetimeIndex, nombres, horarios=None, sin_pausa=(), cortes=None) -> np.ndarray:
    """True si la vela cae en AL MENOS UNA de las sesiones elegidas (solapamientos
    validos). Ventana [inicio, fin) en hora local; admite ventanas que cruzan medianoche.
    `sin_pausa`: sesiones a las que se les saca su pausa de mediodia (PAUSAS_LOCAL, tambien [inicio, fin) por hora de APERTURA
    de la vela); la pausa se saca solo de su propia sesion.
    `cortes`: {sesion: (desde_local, hasta_local)} un horario cualquiera que se le descuenta a esa sesion (hora LOCAL de la plaza,
    [desde, hasta) por hora de apertura de la vela; si desde > hasta cruza la medianoche). Convive con la pausa y con el rango."""
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
        en = (h >= ini) & (h < fin) if ini < fin else (h >= ini) | (h < fin)
        if nombre in (sin_pausa or ()):
            _z, p_ini, p_fin = PAUSAS_LOCAL[nombre]
            en &= ~((h >= p_ini) & (h < p_fin))
        if cortes and nombre in cortes:
            c_ini, c_fin = cortes[nombre]
            en &= ~(((h >= c_ini) & (h < c_fin)) if c_ini < c_fin else ((h >= c_ini) | (h < c_fin)))
        ok |= en
    return ok


# ---------------------------------------------------------------------------------------------------------------------
# Rangos horarios dentro de cada sesion, elegidos en HORA ARGENTINA.
# Lo que se guarda y se evalua es la hora LOCAL de cada plaza (Tokio, Londres, Nueva York): asi, cuando cambia el horario de
# verano de Londres o de Nueva York, el rango se corre solo en hora Argentina (que no cambia) y sigue siendo la misma franja
# de esa plaza. Tokio no tiene horario de verano.
ZONA_AR = "America/Argentina/Buenos_Aires"
# hora local en que arranca la bolsa de cada plaza (valor por defecto del inicio del rango)
ABRE_BOLSA = {"Tokio": 9.0, "Londres": 8.0, "Nueva York": 9.5}


def _a_dt(fecha: date, hora: float, zona: str) -> datetime:
    minutos = int(round(float(hora) * 60)) % (24 * 60)
    return datetime(fecha.year, fecha.month, fecha.day, minutos // 60, minutos % 60, tzinfo=ZoneInfo(zona))


def _hora(d: datetime) -> float:
    return d.hour + d.minute / 60.0


def art_a_local(hora_art: float, zona: str, fecha: date) -> float:
    """Hora de reloj en Argentina -> hora de reloj en `zona`, con las reglas de verano vigentes en `fecha`."""
    return _hora(_a_dt(fecha, hora_art, ZONA_AR).astimezone(ZoneInfo(zona)))


def local_a_art(hora_local: float, zona: str, fecha: date) -> float:
    """Hora de reloj en `zona` -> hora de reloj en Argentina, con las reglas de verano vigentes en `fecha`."""
    return _hora(_a_dt(fecha, hora_local, zona).astimezone(ZoneInfo(ZONA_AR)))


def ventana_art(nombre: str, fecha: date, horarios=None) -> tuple:
    """(inicio, fin) en hora Argentina, en `fecha`, de la ventana por defecto de una sesion: desde que arranca la bolsa hasta
    el fin de la sesion."""
    zona, _ini, fin = (horarios or SESIONES_LOCAL)[nombre]
    return local_a_art(ABRE_BOLSA[nombre], zona, fecha), local_a_art(fin, zona, fecha)


def horarios_con_rangos(rangos_art: dict, fecha: date) -> dict:
    """Ventanas de todas las sesiones, listas para `mascara_sesiones`. `rangos_art` = {sesion: (desde, hasta)} en hora Argentina
    para las sesiones limitadas; las demas quedan completas. Cada rango se pasa a la hora local de su plaza."""
    out = dict(SESIONES_LOCAL)
    for nombre, (desde, hasta) in (rangos_art or {}).items():
        if nombre not in SESIONES_LOCAL:
            raise ValueError(f"Sesion desconocida: {nombre}")
        if abs(float(desde) - float(hasta)) < 1e-9:
            raise ValueError(f"{nombre}: el rango horario tiene el mismo inicio y fin; elegi un rango con duracion.")
        zona = SESIONES_LOCAL[nombre][0]
        out[nombre] = (zona, art_a_local(desde, zona, fecha), art_a_local(hasta, zona, fecha))
    return out


def cortes_con_rangos(cortes_art: dict, fecha: date) -> dict:
    """Recortes de horario por sesion, de hora Argentina a la hora local de su plaza: {sesion: (desde_local, hasta_local)}.
    Con desde > hasta el recorte cruza la medianoche; con desde == hasta es un error (no tiene duracion)."""
    out = {}
    for nombre, (desde, hasta) in (cortes_art or {}).items():
        if nombre not in SESIONES_LOCAL:
            raise ValueError(f"Sesion desconocida: {nombre}")
        if abs(float(desde) - float(hasta)) < 1e-9:
            raise ValueError(f"{nombre}: el recorte tiene el mismo inicio y fin; elegi un tramo con duracion.")
        zona = SESIONES_LOCAL[nombre][0]
        out[nombre] = (art_a_local(desde, zona, fecha), art_a_local(hasta, zona, fecha))
    return out


def corte_toca_sesion(nombre: str, corte_local: tuple, horarios=None) -> bool:
    """True si el recorte (hora local) pisa algun minuto de la ventana de la sesion; si no, no cambia nada."""
    _z, ini, fin = (horarios or SESIONES_LOCAL)[nombre]
    c_ini, c_fin = corte_local
    for m in range(1440):
        h = m / 60.0
        en_ses = (ini <= h < fin) if ini < fin else (h >= ini or h < fin)
        en_cor = (c_ini <= h < c_fin) if c_ini < c_fin else (h >= c_ini or h < c_fin)
        if en_ses and en_cor:
            return True
    return False


def _domingo_n(anio: int, mes: int, n: int) -> date:
    """n-esimo domingo del mes (n=1 primero, 2 segundo...)."""
    d = date(anio, mes, 1)
    return date(anio, mes, 1 + (6 - d.weekday()) % 7 + 7 * (n - 1))


def _ultimo_domingo(anio: int, mes: int) -> date:
    d = date(anio, mes + 1, 1) if mes < 12 else date(anio + 1, 1, 1)
    d = d.fromordinal(d.toordinal() - 1)
    return d.fromordinal(d.toordinal() - (d.weekday() + 1) % 7)


def aviso_cambio_horario(hoy: date):
    """Aviso de la portada por los cambios de horario de Londres y Nueva York, todos los años:
    marzo completo -> Londres / NY; del 20 al 31 de octubre -> Londres; del 1 al 7 de noviembre -> NY.
    Devuelve (titulo, detalle) o None fuera de esas fechas. Las fechas de cambio: EE.UU. 2.o domingo de marzo y 1.er domingo de
    noviembre; Reino Unido, ultimo domingo de marzo y de octubre."""
    def seg(nombre, d):
        if d == hoy:
            return f"{nombre} cambia hoy"
        return f"{nombre} {'cambió' if d < hoy else 'cambia'} el domingo {d:%d/%m}"
    y = hoy.year
    if hoy.month == 3:
        return ("Verificar filtro de sesión por cambio de horario LONDRES / NY",
                f"{seg('EE.UU.', _domingo_n(y, 3, 2))} y {seg('Londres', _ultimo_domingo(y, 3))}. Revisá el menú 6 antes de seguir probando.")
    if hoy.month == 10 and hoy.day >= 20:
        return ("Verificar filtro de sesión por cambio de horario LONDRES",
                f"{seg('Londres', _ultimo_domingo(y, 10))}. Revisá el menú 6 antes de seguir probando.")
    if hoy.month == 11 and hoy.day <= 7:
        return ("Verificar filtro de sesión de NY",
                f"{seg('EE.UU.', _domingo_n(y, 11, 1))}. Revisá el menú 6 antes de seguir probando.")
    return None


def pausa_art(nombre: str, fecha: date) -> tuple:
    """(inicio, fin) de la pausa de mediodia de una sesion en hora Argentina, en `fecha`."""
    zona, ini, fin = PAUSAS_LOCAL[nombre]
    return local_a_art(ini, zona, fecha), local_a_art(fin, zona, fecha)


def rebasar_horas(valores: dict, pares: list, hoy: date) -> dict:
    """Al cargar una configuracion guardada otro dia: las horas Argentina guardadas valian para la fecha de guardado
    (`_ref_fecha`). Se pasan a la hora local de la plaza y de vuelta a hora Argentina de HOY, asi la franja de la plaza no
    cambia aunque haya cambiado el horario de verano. `pares` = [(clave_desde, clave_hasta, zona)]."""
    out = {k: v for k, v in valores.items() if k != "_ref_fecha"}
    ref = valores.get("_ref_fecha")
    try:
        f_ref = date.fromisoformat(str(ref)[:10])
    except (TypeError, ValueError):
        return out
    if f_ref == hoy:
        return out
    for cd, ch, zona in pares:
        for clave in (cd, ch):
            v = out.get(clave)
            try:
                hh, mm = int(str(v)[:2]), int(str(v)[3:5])
            except (TypeError, ValueError):
                continue
            nuevo = local_a_art(art_a_local(hh + mm / 60.0, zona, f_ref), zona, hoy)
            m = int(round(nuevo * 60)) % (24 * 60)
            out[clave] = f"{m // 60:02d}:{m % 60:02d}"
    return out
