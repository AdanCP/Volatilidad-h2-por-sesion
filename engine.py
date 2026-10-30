"""Motor del backtest de cruce de EMAs con filtros opcionales (sesion, SMA, ADX, ATR).

Reglas (ver prompt):
  - Entrada al CIERRE de la vela del cruce (alcista = largo, bajista = corto).
  - Filtros evaluados con datos de la vela de la señal, en este orden: sesion, SMA, ADX, ATR.
    Cada cruce descartado se atribuye al PRIMER filtro que falla.
  - SL = ATR * mult (o % del precio); TP = SL * RR. Una operacion a la vez.
  - Vela que toca SL y TP a la vez = SL ("ambigua"). Sin slippage ni gaps.
  - Spread: velas BID. Largo entra al ask (cierre + spread); el corto entra al bid y su
    SL/TP se activan con el ask (precio + spread).
"""
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

import indicators as ind
import sessions as ses


@dataclass
class Config:
    # señal y gestion
    ema_corta: int = 13
    ema_larga: int = 34
    rr: float = 2.0
    sl_modo: str = "atr"            # "atr" (multiplo) o "pct" (% del precio)
    sl_valor: float = 1.5
    atr_periodo: int = 14
    direccion: str = "ambas"        # "ambas" | "largos" | "cortos"
    # costos
    spread: str = "vela"            # "vela" | "mediana" (ceros -> mediana) | "fijo" | "ninguno"
    spread_fijo: float = 0.0        # unidades de precio, solo con spread="fijo"
    costo_extra: float = 0.0        # unidades de precio por operacion, restado al resultado
    # filtro SMA
    sma_activo: bool = False
    sma_periodo: int = 200
    sma_dist_min_atr: float = 0.0   # 0 = sin condicion
    sma_pendiente_n: int = 0        # 0 = sin condicion
    # filtro ADX
    adx_activo: bool = False
    adx_periodo: int = 14
    adx_min: float = 20.0
    adx_max: Optional[float] = None
    adx_creciente_n: int = 0        # 0 = sin condicion
    # filtro ATR
    atr_activo: bool = False
    atr_unidad: str = "pct"         # "pct" (% del precio) o "precio"
    atr_min: Optional[float] = None
    atr_max: Optional[float] = None
    atr_rel_n: int = 0              # >0: ATR / promedio de las ultimas N velas
    atr_rel_min: Optional[float] = None
    atr_rel_max: Optional[float] = None
    # filtro de sesion
    sesion_activo: bool = False
    sesiones: tuple = ("Londres", "Nueva York")
    horarios: Optional[dict] = None
    servidor_offset_horas: Optional[float] = None   # desfase del servidor en invierno (GMT+2 -> 2)
    servidor_dst_eeuu: bool = True

    def validar(self) -> None:
        if self.ema_corta >= self.ema_larga:
            raise ValueError("La EMA corta debe ser menor que la larga.")
        if not 1 <= self.rr <= 10:
            raise ValueError("El RR debe estar entre 1 y 10.")
        if self.sl_modo not in ("atr", "pct") or self.sl_valor <= 0:
            raise ValueError("SL invalido: modo 'atr' o 'pct' y valor mayor que 0.")
        if self.direccion not in ("ambas", "largos", "cortos"):
            raise ValueError("Direccion invalida.")
        if self.spread not in ("vela", "mediana", "fijo", "ninguno"):
            raise ValueError("Modo de spread invalido.")
        if self.sesion_activo and self.servidor_offset_horas is None:
            raise ValueError("El filtro de sesion necesita el desfase horario del servidor "
                             "(servidor_offset_horas). Medilo con el mercado abierto.")


FILTROS_APAGADOS = dict(sma_activo=False, adx_activo=False, atr_activo=False, sesion_activo=False)


@dataclass
class Preparado:
    """Arrays y cruces calculados una sola vez para una configuracion."""
    h: np.ndarray
    l: np.ndarray
    c: np.ndarray
    sp: np.ndarray
    atr: np.ndarray
    dist: np.ndarray
    indice: pd.DatetimeIndex
    cruces: list                    # (i, lado, motivo_descarte|None)
    spread_ceros_pct: float


def _spread(df: pd.DataFrame, cfg: Config) -> np.ndarray:
    sp = df["Spread"].to_numpy(float) if "Spread" in df else np.zeros(len(df))
    if cfg.spread == "ninguno":
        return np.zeros(len(df))
    if cfg.spread == "fijo":
        return np.full(len(df), float(cfg.spread_fijo))
    if cfg.spread == "mediana":
        pos = sp[sp > 0]
        return np.where(sp > 0, sp, float(np.median(pos)) if len(pos) else 0.0)
    return sp


def preparar(df: pd.DataFrame, cfg: Config) -> Preparado:
    cfg.validar()
    h, l, c = (df[k].to_numpy(float) for k in ("High", "Low", "Close"))
    n = len(c)
    atr = ind.atr_wilder(h, l, c, cfg.atr_periodo)
    dist = atr * cfg.sl_valor if cfg.sl_modo == "atr" else c * cfg.sl_valor / 100.0

    warm = cfg.ema_larga + 1        # sin filtros: igual que cruce_minimo.py
    if cfg.sma_activo:
        warm = max(warm, cfg.sma_periodo + max(cfg.sma_pendiente_n, 0))
    if cfg.adx_activo:
        warm = max(warm, 2 * cfg.adx_periodo + max(cfg.adx_creciente_n, 0) + 1)
    if cfg.atr_activo and cfg.atr_rel_n:
        warm = max(warm, cfg.atr_rel_n + cfg.atr_periodo)

    diff = ind.ema(c, cfg.ema_corta) - ind.ema(c, cfg.ema_larga)
    prev = np.r_[np.nan, diff[:-1]]
    sube, baja = (diff > 0) & (prev <= 0), (diff < 0) & (prev >= 0)

    sma = ind.sma(c, cfg.sma_periodo) if cfg.sma_activo else None
    adx = ind.adx_wilder(h, l, c, cfg.adx_periodo)[0] if cfg.adx_activo else None
    atr_pct = atr / c * 100.0
    atr_med = pd.Series(atr).rolling(cfg.atr_rel_n).mean().to_numpy() if (cfg.atr_activo and cfg.atr_rel_n) else None
    ok_ses = None
    if cfg.sesion_activo:
        utc = ses.servidor_a_utc(df.index, cfg.servidor_offset_horas, cfg.servidor_dst_eeuu)
        ok_ses = ses.mascara_sesiones(utc, cfg.sesiones, cfg.horarios)

    def entre(v, lo, hi):
        return not (np.isnan(v) or (lo is not None and v < lo) or (hi is not None and v > hi))

    def ok_sma(i, lado):
        s = sma[i]
        if np.isnan(s) or (c[i] - s) * lado <= 0:
            return False
        if cfg.sma_dist_min_atr > 0 and abs(c[i] - s) < cfg.sma_dist_min_atr * atr[i]:
            return False
        if cfg.sma_pendiente_n > 0:
            return (s - sma[i - cfg.sma_pendiente_n]) * lado > 0
        return True

    def ok_adx(i):
        if not entre(adx[i], cfg.adx_min, cfg.adx_max):
            return False
        return cfg.adx_creciente_n <= 0 or adx[i] > adx[i - cfg.adx_creciente_n]

    def ok_atr(i):
        v = atr[i] if cfg.atr_unidad == "precio" else atr_pct[i]
        if not entre(v, cfg.atr_min, cfg.atr_max):
            return False
        if atr_med is not None:
            return entre(atr[i] / atr_med[i], cfg.atr_rel_min, cfg.atr_rel_max)
        return True

    cruces = []
    for i in range(warm, n):
        if sube[i] and cfg.direccion in ("ambas", "largos"):
            lado = 1
        elif baja[i] and cfg.direccion in ("ambas", "cortos"):
            lado = -1
        else:
            continue
        motivo = None
        if cfg.sesion_activo and not ok_ses[i]:
            motivo = "sesion"
        elif cfg.sma_activo and not ok_sma(i, lado):
            motivo = "sma"
        elif cfg.adx_activo and not ok_adx(i):
            motivo = "adx"
        elif cfg.atr_activo and not ok_atr(i):
            motivo = "atr"
        cruces.append((i, lado, motivo))

    sp = _spread(df, cfg)
    raw = df["Spread"].to_numpy(float) if "Spread" in df else np.zeros(n)
    return Preparado(h, l, c, sp, atr, dist, df.index, cruces, 100 * float((raw == 0).mean()))


def simular(P: Preparado, señales, rr: float, costo_extra: float = 0.0):
    """señales: lista de (indice, lado). Devuelve (DataFrame de operaciones, ignoradas)."""
    h, l, c, sp, dist = P.h, P.l, P.c, P.sp, P.dist
    n = len(c)
    filas, libre, ignoradas = [], 0, 0
    for i, lado in señales:
        if i < libre:                                   # operacion en curso: se ignora
            ignoradas += 1
            continue
        d = dist[i]
        if not d > 0:
            continue
        entrada = c[i] + sp[i] if lado == 1 else c[i]
        sl, tp = entrada - lado * d, entrada + lado * d * rr
        res, amb, j_out = "ABIERTA", False, n - 1
        for j in range(i + 1, n):
            if lado == 1:
                hit_sl, hit_tp = l[j] <= sl, h[j] >= tp
            else:
                hit_sl, hit_tp = h[j] + sp[j] >= sl, l[j] + sp[j] <= tp
            if hit_sl and hit_tp:
                res, amb, j_out = "SL", True, j
                break
            if hit_sl:
                res, j_out = "SL", j
                break
            if hit_tp:
                res, j_out = "TP", j
                break
        r = rr if res == "TP" else (-1.0 if res == "SL" else 0.0)
        if res != "ABIERTA" and costo_extra:
            r -= costo_extra / d
        filas.append({"i": i, "lado": lado, "entrada": entrada, "sl": sl, "tp": tp, "dist": d,
                      "res": res, "amb": amb, "salida": j_out, "R": r})
        if res == "ABIERTA":
            break
        libre = j_out + 1
    cols = ["i", "lado", "entrada", "sl", "tp", "dist", "res", "amb", "salida", "R"]
    return pd.DataFrame(filas, columns=cols), ignoradas


@dataclass
class Resultado:
    trades: pd.DataFrame
    descartes: dict = field(default_factory=dict)
    cruces: int = 0                 # cruces detectados en el tramo
    tomados: int = 0                # cruces que pasaron todos los filtros
    ignoradas: int = 0              # cruces que pasaron filtros pero habia operacion abierta


def ejecutar(P: Preparado, cfg: Config, lo: int = 0, hi: Optional[int] = None) -> Resultado:
    hi = len(P.c) if hi is None else hi
    en_rango = [x for x in P.cruces if lo <= x[0] < hi]
    descartes = {}
    for _, _, m in en_rango:
        if m:
            descartes[m] = descartes.get(m, 0) + 1
    señales = [(i, lado) for i, lado, m in en_rango if m is None]
    tr, ign = simular(P, señales, cfg.rr, cfg.costo_extra)
    return Resultado(tr, descartes, len(en_rango), len(señales), ign)
