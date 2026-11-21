"""Estrategia de ruptura del rango de apertura de Nueva York.

Rango: maximo y minimo de las velas que abren entre `apertura_min` y `apertura_min + rango_min` (hora de NY; 9:30 a 9:45 por defecto).
Entrada: desde el fin del rango, una vela que CIERRA fuera del rango da la señal (compra sobre el maximo, venta bajo el minimo) y se entra a su cierre.
SL: mitad del rango, lado opuesto del rango o multiplo de ATR, medido desde el precio de entrada. TP: RR sobre esa distancia real.
Horario: la ultima entrada y el cierre forzado se miden en hora de NY (se corren solos con el horario de verano).
Entradas por dia: 1, o 2 (la segunda solo hacia el lado contrario y solo si la primera salio por su SL original).

Este modulo NO simula: genera las señales (como "cruces" del motor), la distancia del SL de cada una y las mascaras de horario. La simulacion es la
del motor (engine.simular) con dos parametros opcionales que solo usa esta estrategia: `hcierre` (cierre a mercado a la hora forzada) y `grupo`
(entradas por dia). Se activa con Config.ruptura = ConfigRup(...); con None, el motor es el de siempre.
"""
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

import noticias as noti_
import sessions as ses

SL_MODOS = ("mitad", "opuesto", "atr")
# motivos de descarte de las señales que son del dia (no de un filtro): se cuentan aparte en el embudo
MOT_DIA = ("historial", "tamano", "hora")
MOT_FILTROS_NO = ("hora", "historial", "tamano", "noticias")


def hhmm(minutos: int) -> str:
    return f"{int(minutos) // 60:02d}:{int(minutos) % 60:02d}"


@dataclass
class ConfigRup:
    apertura_min: int = 9 * 60 + 30          # inicio del rango, hora de NY (minutos desde la medianoche)
    rango_min: int = 15                      # duracion del rango (minutos)
    sl_modo: str = "mitad"                   # "mitad" | "opuesto" | "atr"
    sl_atr_x: float = 1.0                    # con sl_modo "atr": multiplo del ATR (periodo = Config.atr_periodo)
    entradas_dia: int = 1                    # 1 o 2
    ultima_min: int = 12 * 60                # ultima entrada (el CIERRE de la vela de la señal tiene que ser <= esta hora), hora de NY
    cierre_min: int = 12 * 60 + 30           # cierre forzado a mercado, hora de NY
    tam_activo: bool = False                 # filtro de tamaño del rango
    tam_min: float = 0.5                     # el rango tiene que medir entre tam_min y tam_max veces el promedio de los rangos de los ultimos tam_n dias validos
    tam_max: float = 1.5
    tam_n: int = 20

    def validar(self, cfg) -> None:
        if not 0 <= self.apertura_min < 24 * 60 or not 0 <= self.ultima_min < 24 * 60 or not 0 < self.cierre_min <= 24 * 60:
            raise ValueError("Ruptura: los horarios tienen que estar entre 00:00 y 23:59.")
        if self.rango_min < 1:
            raise ValueError("Ruptura: el rango de apertura tiene que durar al menos 1 minuto.")
        if self.sl_modo not in SL_MODOS:
            raise ValueError("Ruptura: el SL tiene que ser 'mitad', 'opuesto' o 'atr'.")
        if self.sl_modo == "atr" and not self.sl_atr_x > 0:
            raise ValueError("Ruptura: el multiplo de ATR del SL tiene que ser mayor que 0.")
        if self.entradas_dia not in (1, 2):
            raise ValueError("Ruptura: las entradas por dia son 1 o 2.")
        if not self.apertura_min + self.rango_min <= self.ultima_min:
            raise ValueError("Ruptura: la ultima entrada tiene que ser posterior al fin del rango de apertura.")
        if not self.ultima_min < self.cierre_min:
            raise ValueError("Ruptura: el cierre forzado tiene que ser posterior a la ultima entrada.")
        if self.tam_activo:
            if not (self.tam_min >= 0 and self.tam_max > self.tam_min):
                raise ValueError("Ruptura: el filtro de tamaño necesita un minimo (0 o mas) menor que el maximo.")
            if self.tam_n < 1:
                raise ValueError("Ruptura: el filtro de tamaño necesita al menos 1 dia de historia.")
        if cfg.servidor_offset_horas is None:
            raise ValueError("Ruptura: hace falta el desfase horario del servidor (servidor_offset_horas) para ubicar la apertura de Nueva York.")
        if cfg.pullback_activo or cfg.reentrada_activa or cfg.salida_modo != "rr" or cfg.sl_modo == "ema":
            raise ValueError("Ruptura: no se combina con pullback, reentrada, salida por cruce ni SL anclado a una media.")


def _dia_ny(ny) -> np.ndarray:
    return (ny.year.to_numpy() * 10000 + ny.month.to_numpy() * 100 + ny.day.to_numpy()).astype(np.int64)


def senales(df, cfg, rp: ConfigRup, sp, atr) -> dict:
    """Arma las señales de ruptura y las mascaras de horario. Devuelve un dict:
      sube / baja: vela de señal (cierre fuera del rango, entre el fin del rango y el cierre forzado)
      dist: distancia del SL de esa señal (precio, desde el precio de entrada), nan en el resto
      pre: motivo de descarte del dia ('historial', 'tamano', 'hora') o None
      hcierre: True en la vela que cierra a la hora forzada (o la ultima anterior si falta)
      grupo: id del dia (-1 fuera de la ventana de entradas)
      dias: DataFrame por dia de mercado (fecha, i0, estado, tam, ratio, motivo, fin)"""
    rp.validar(cfg)
    n = len(df)
    h, l, c = (df[k].to_numpy(float) for k in ("High", "Low", "Close"))
    utc = ses.servidor_a_utc(df.index, cfg.servidor_offset_horas, cfg.servidor_dst_eeuu)
    ny = pd.DatetimeIndex(utc).tz_localize("UTC").tz_convert("America/New_York")
    m = (ny.hour.to_numpy() * 60 + ny.minute.to_numpy()).astype(np.int64)
    fecha = _dia_ny(ny)
    per_s = noti_.periodo_seg(df.index)
    if per_s % 60 or per_s < 60:
        raise ValueError("Ruptura: las velas tienen que ser de un numero entero de minutos.")
    per = per_s // 60
    if per > rp.rango_min or rp.rango_min % per:
        raise ValueError(f"Ruptura: con velas de {per} minutos el rango de {rp.rango_min} minutos no se puede armar "
                         f"(la duracion del rango tiene que ser multiplo de la vela y no menor).")
    esperadas = rp.rango_min // per
    a_ = rp.apertura_min
    fin_rango = a_ + rp.rango_min

    sube = np.zeros(n, dtype=bool)
    baja = np.zeros(n, dtype=bool)
    dist = np.full(n, np.nan)
    pre = np.full(n, None, dtype=object)
    hcierre = np.zeros(n, dtype=bool)
    grupo = np.full(n, -1, dtype=np.int64)
    fila_dias = []
    tamaños = []                                    # rangos de los dias validos anteriores (para el filtro de tamaño)
    wd = ny.weekday.to_numpy()
    inicios = np.r_[0, np.flatnonzero(np.diff(fecha) != 0) + 1, n]
    gid = 0
    for k in range(len(inicios) - 1):
        a, b = int(inicios[k]), int(inicios[k + 1])
        if wd[a] >= 5:                              # sabados y domingos no son dias de mercado
            continue
        mm = m[a:b]
        en_rango = (mm >= a_) & (mm < fin_rango)
        fila = {"fecha": int(fecha[a]), "i0": a, "estado": "ok", "tam": np.nan, "ratio": np.nan, "motivo": None, "fin": a, "gid": -1}
        if int(en_rango.sum()) != esperadas:
            fila["estado"] = "sin_vela"             # feriado, cierre anticipado o hueco en los datos: ese dia no se opera
            fila_dias.append(fila)
            continue
        idx = a + np.flatnonzero(en_rango)
        hi, lo = float(h[idx].max()), float(l[idx].min())
        tam = hi - lo
        fila["tam"], fila["fin"] = tam, int(idx[-1])
        prev = tamaños[-rp.tam_n:] if len(tamaños) >= rp.tam_n else None
        if prev is not None:
            fila["ratio"] = tam / float(np.mean(prev)) if np.mean(prev) > 0 else np.nan
        mot_dia = None
        if rp.tam_activo:
            if prev is None:
                mot_dia = "historial"
            elif not (fila["ratio"] >= rp.tam_min and fila["ratio"] <= rp.tam_max):
                mot_dia = "tamano"
        tamaños.append(tam)                          # solo dias anteriores: el de hoy se suma despues de evaluarlo
        fila["motivo"] = mot_dia
        fila_dias.append(fila)
        cierre = mm + per                            # minuto en que cierra cada vela
        ventana = (np.arange(a, b) > idx[-1]) & (cierre <= rp.cierre_min) & (mm >= fin_rango)
        vi = a + np.flatnonzero(ventana)
        if len(vi):
            grupo[vi] = gid
            fila["gid"] = gid
            sube[vi] = c[vi] > hi
            baja[vi] = c[vi] < lo
            for i in vi:
                if mot_dia is not None:
                    pre[i] = mot_dia
                elif cierre[i - a] > rp.ultima_min:
                    pre[i] = "hora"
            nivel_l = (hi + lo) / 2.0 if rp.sl_modo == "mitad" else lo           # SL del largo
            nivel_c = (hi + lo) / 2.0 if rp.sl_modo == "mitad" else hi           # SL del corto
            for i in vi:
                if sube[i]:
                    ent = c[i] + sp[i]                                              # el largo entra al ask
                    dist[i] = ent - nivel_l if rp.sl_modo != "atr" else atr[i] * rp.sl_atr_x
                elif baja[i]:
                    dist[i] = nivel_c - c[i] if rp.sl_modo != "atr" else atr[i] * rp.sl_atr_x
            gid += 1
        cand = np.flatnonzero(cierre <= rp.cierre_min)
        if len(cand):
            hcierre[a + int(cand[-1])] = True        # la vela que cierra a la hora forzada (o la ultima anterior si falta)
    dias = pd.DataFrame(fila_dias)
    ok = dias[dias["gid"] >= 0] if len(dias) else dias
    return {"sube": sube, "baja": baja, "dist": dist, "pre": pre, "hcierre": hcierre, "grupo": grupo, "dias": dias,
            "per": per, "n_grupos": gid, "grupo_de_dia": {int(a): int(g) for a, g in zip(ok["i0"], ok["gid"])},
            "tam_de_grupo": {int(g): float(t) for g, t in zip(ok["gid"], ok["tam"])},
            "ratio_de_grupo": {int(g): float(r) for g, r in zip(ok["gid"], ok["ratio"])}}


def embudo(P, trades: pd.DataFrame, cruces, lo: int = 0, hi: Optional[int] = None) -> dict:
    """Cuenta los DIAS por etapa en el tramo [lo, hi) (un dia cae en una sola fila). Devuelve un dict con las cantidades."""
    R = P.rup
    hi = len(P.c) if hi is None else hi
    dias = R["dias"]
    dias = dias[(dias["i0"] >= lo) & (dias["i0"] < hi)]
    grupo = R["grupo"]
    por_dia = {}
    for i, lado, mot in cruces:
        g = int(grupo[i])
        if g >= 0 and lo <= i < hi:
            por_dia.setdefault(g, []).append(mot)
    operados = set(int(grupo[i]) for i in trades["i"] if grupo[int(i)] >= 0) if len(trades) else set()
    # id de grupo de cada dia valido (los grupos se numeran en orden, solo para dias con rango valido y alguna vela de la ventana)
    out = {"dias": int(len(dias)), "sin_vela": 0, "validos": 0, "historial": 0, "tamano": 0, "sin_ruptura": 0, "fuera_horario": 0,
           "filtros": 0, "noticias": 0, "otros": 0, "operados": 0}
    g_de = R["grupo_de_dia"]
    for _, d in dias.iterrows():
        if d["estado"] == "sin_vela":
            out["sin_vela"] += 1
            continue
        out["validos"] += 1
        if d["motivo"] in ("historial", "tamano"):
            out[d["motivo"]] += 1
            continue
        g = g_de.get(int(d["i0"]), -1)
        if g in operados:
            out["operados"] += 1
            continue
        mots = por_dia.get(g, [])
        if not mots:
            out["sin_ruptura"] += 1
        elif all(x == "hora" for x in mots):
            out["fuera_horario"] += 1
        elif any(x is None for x in mots):
            out["otros"] += 1                      # paso todos los filtros pero no se tomo (cuenta, posicion abierta, entradas del dia)
        elif all(x in ("hora", "noticias") for x in mots):
            out["noticias"] += 1
        else:
            out["filtros"] += 1
    return out


def estadisticas(P, trades: pd.DataFrame, lo: int = 0, hi: Optional[int] = None) -> dict:
    """Salidas, largos / cortos y tamaño del rango en ganadoras y perdedoras, para las operaciones del tramo [lo, hi)."""
    hi = len(P.c) if hi is None else hi
    t = trades[(trades["i"] >= lo) & (trades["i"] < hi)] if len(trades) else trades
    out = {"n": int(len(t)), "salidas": {}, "lados": {}, "tam": {}}
    if not len(t):
        return out
    for mot, g in t.groupby("motivo"):
        out["salidas"][mot] = {"n": int(len(g)), "R_medio": float(g["R"].mean())}
    for lado, g in t.groupby("lado"):
        out["lados"]["largos" if lado == 1 else "cortos"] = {"n": int(len(g)), "ganadoras_%": float(100 * (g["R"] > 0).mean()), "R_total": float(g["R"].sum())}
    R = P.rup
    gdia = R["grupo"][t["i"].to_numpy()]
    tam_de = R["tam_de_grupo"]
    rat_de = R["ratio_de_grupo"]
    t = t.assign(_tam=[tam_de.get(int(g), np.nan) for g in gdia], _rat=[rat_de.get(int(g), np.nan) for g in gdia])
    for nombre, mask in (("ganadoras", t["R"] > 0), ("perdedoras", t["R"] <= 0)):
        g = t[mask]
        out["tam"][nombre] = {"n": int(len(g)), "rango_medio": float(g["_tam"].mean()) if len(g) else np.nan,
                              "ratio_medio": float(g["_rat"].mean()) if len(g) else np.nan}
    return out
