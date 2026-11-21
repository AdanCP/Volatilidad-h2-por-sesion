"""Trading de noticias: deteccion de noticias de alto impacto (en las velas o desde un CSV de calendario) y mascaras para el motor.

Dos reglas (ver engine.py):
  1. no se abre una operacion (ni reentrada ni se llena una orden limite) cuando la entrada cae a menos de N minutos de una noticia;
  2. antes de la noticia, la operacion abierta se cierra si va en R o peor (solo si el breakeven no esta activado).
Todo en UTC (epoch en segundos); las velas vienen en hora del servidor y se pasan a UTC con sessions.servidor_a_utc.
"""
import io

import numpy as np
import pandas as pd

import indicators as ind
import sessions as ses

# horarios (hora de Nueva York, minutos desde medianoche) de las noticias de EEUU que mueven el oro:
# 8:30 (empleo, IPC, PIB...), 10:00 (ISM, confianza), 14:00 (FOMC), 14:30 (conferencia de prensa)
HORAS_NY = (8 * 60 + 30, 10 * 60, 14 * 60, 14 * 60 + 30)
ATR_PER = 14                      # ATR fijo de la deteccion (independiente del ATR de la estrategia)
_ALTO = {"high", "alto", "alta", "3", "red", "rojo", "h"}


def _epoch(idx_utc) -> np.ndarray:
    return pd.DatetimeIndex(idx_utc).values.astype("datetime64[s]").astype(np.int64)


def periodo_seg(index) -> int:
    """Duracion de una vela en segundos (mediana de las diferencias del indice)."""
    if len(index) < 2:
        return 60
    d = np.diff(pd.DatetimeIndex(index).values.astype("datetime64[s]").astype(np.int64))
    return int(max(np.median(d), 1))


def eventos_en_velas(df, cfg):
    """Eventos detectados en las velas del DataFrame (hora del servidor). Devuelve (array de epochs UTC, {año: n}, avisos)."""
    avisos = []
    utc = ses.servidor_a_utc(df.index, cfg.servidor_offset_horas, cfg.servidor_dst_eeuu)
    per = periodo_seg(df.index)
    if per > 30 * 60:
        avisos.append("Trading de noticias: con velas de más de 30 minutos no se pueden detectar las noticias en las velas "
                      "(las de 8:30 / 14:30 no existen). Usá velas de 30 minutos o menos, o cargá un CSV de calendario.")
        return np.zeros(0, dtype=np.int64), {}, avisos
    h, l, c = (df[k].to_numpy(float) for k in ("High", "Low", "Close"))
    atr = ind.atr_wilder(h, l, c, ATR_PER)
    atr_prev = np.concatenate([[np.nan], atr[:-1]])                   # ATR de las velas ANTERIORES (la de la noticia no se mide a si misma)
    ny = pd.DatetimeIndex(utc).tz_localize("UTC").tz_convert("America/New_York")
    minutos = ny.hour.to_numpy() * 60 + ny.minute.to_numpy()
    cand = np.isin(minutos, HORAS_NY) & (ny.weekday.to_numpy() < 5)
    with np.errstate(invalid="ignore"):
        grande = ((h - l) >= cfg.noticias_rango_atr * atr_prev) & ((h - l) >= cfg.noticias_rango_min)
    sel = cand & grande
    ep = _epoch(utc)[sel]
    años = {}
    for y in ny[sel].year:
        años[int(y)] = años.get(int(y), 0) + 1
    return ep, años, avisos


def leer_csv(contenido):
    """Lee el calendario (columnas fecha_hora_utc, moneda, impacto). Se quedan solo las filas USD de impacto alto.
    Devuelve (tupla de epochs UTC ordenados, info). Levanta ValueError si el archivo no sirve."""
    if isinstance(contenido, (bytes, bytearray)):
        contenido = bytes(contenido).decode("utf-8-sig", errors="replace")
    try:
        t = pd.read_csv(io.StringIO(contenido), sep=None, engine="python")
    except Exception as e:
        raise ValueError(f"No pude leer el CSV del calendario: {e}") from None
    t.columns = [str(x).strip().lower() for x in t.columns]
    faltan = [k for k in ("fecha_hora_utc", "moneda", "impacto") if k not in t.columns]
    if faltan:
        raise ValueError("El CSV del calendario tiene que tener las columnas fecha_hora_utc, moneda e impacto (faltan: " + ", ".join(faltan) + ").")
    f = pd.to_datetime(t["fecha_hora_utc"], errors="coerce", utc=True)
    mon = t["moneda"].astype(str).str.strip().str.upper()
    imp = t["impacto"].astype(str).str.strip().str.lower()
    ok = f.notna() & (mon == "USD") & imp.isin(_ALTO)
    ep = np.unique(f[ok].dt.tz_localize(None).values.astype("datetime64[s]").astype(np.int64)) if ok.any() else np.zeros(0, dtype=np.int64)
    info = {"filas": int(len(t)), "usd_alto": int(len(ep)),
            "desde": None if not len(ep) else pd.Timestamp(int(ep[0]), unit="s"),
            "hasta": None if not len(ep) else pd.Timestamp(int(ep[-1]), unit="s")}
    if not len(ep):
        raise ValueError("El CSV no tiene ninguna noticia de USD con impacto alto (columna impacto: high / alto / 3).")
    return tuple(int(x) for x in ep), info


def armar(utc, eventos, minutos: float):
    """Mascaras por vela para el motor (utc: indice UTC naive de las velas; eventos: epochs UTC). Devuelve dict:
      ent: True si el cierre de la vela (donde se entra) cae dentro de [E - N, E + N] de alguna noticia
      ov: True si la vela (inicio..fin) se solapa con alguna ventana (llenados de ordenes limite)
      cierre: por vela, epoch de la noticia cuya ventana arranca justo despues del cierre de esa vela (0 si ninguna): ahi se evalua la regla 2
      eventos: epochs de las noticias."""
    E = np.asarray(sorted(set(int(x) for x in eventos)), dtype=np.int64)
    n = len(utc)
    per = periodo_seg(utc)
    w = int(round(float(minutos) * 60))
    ini = _epoch(utc)
    fin = ini + per
    ent = np.zeros(n, dtype=bool)
    ov = np.zeros(n, dtype=bool)
    cierre = np.zeros(n, dtype=np.int64)
    if len(E):
        a = np.searchsorted(E, fin - w, side="left")
        b = np.searchsorted(E, fin + w, side="right")
        ent = a < b
        a = np.searchsorted(E, ini - w, side="left")
        b = np.searchsorted(E, fin + w, side="right")
        ov = a < b
        for e in E:
            s = e - w                                        # inicio de la ventana
            k = int(np.searchsorted(fin, s, side="right")) - 1     # ultima vela que cierra a mas tardar al inicio de la ventana
            if k >= 0 and s - fin[k] < per and ini[k] <= s:
                cierre[k] = e
    return {"ent": ent, "ov": ov, "cierre": cierre, "eventos": E, "per": per, "w": w}
