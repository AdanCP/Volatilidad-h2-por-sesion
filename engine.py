"""Motor del backtest de cruce de EMAs con filtros opcionales (sesion, SMA, ADX, ATR).

Reglas (ver prompt):
  - Entrada al CIERRE de la vela del cruce (alcista = largo, bajista = corto).
  - Filtros evaluados con datos de la vela de la señal, en este orden: sesion, SMA, VWAP, ADX, ATR.
    Cada cruce descartado se atribuye al PRIMER filtro que falla.
  - SL = ATR * mult (o % del precio); TP = SL * RR. Una operacion a la vez.
  - Vela que toca SL y TP a la vez = SL ("ambigua"). Sin slippage ni gaps.
  - Opcional: entrada en PULLBACK a la EMA (pullback_activo). El cruce sigue siendo la señal; en vez de entrar al
    cierre se deja una orden pendiente que se ejecuta cuando el precio devuelve pullback_pct % de la distancia entre
    el extremo posterior al cruce y la EMA elegida. Caduca tras pullback_velas velas o si aparece un cruce contrario.
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
    sl_modo: str = "atr"            # "atr" (multiplo), "pct" (% del precio) o "precio" (distancia fija en unidades de precio)
    sl_valor: float = 1.5
    atr_periodo: int = 14
    direccion: str = "ambas"        # "ambas" | "largos" | "cortos"
    # entrada en pullback (opcional: apagado = entrada al cierre del cruce, como siempre)
    pullback_activo: bool = False
    pullback_pct: float = 50.0      # 0-100: % de la distancia extremo->EMA que debe devolver el precio (100 = toca la EMA)
    pullback_ema: str = "corta"     # "corta" | "larga"
    pullback_velas: int = 10        # caducidad de la orden pendiente, en velas desde el cruce
    # costos
    spread: str = "vela"            # "vela" | "mediana" (ceros -> mediana) | "fijo" | "ninguno"
    spread_fijo: float = 0.0        # unidades de precio, solo con spread="fijo"
    costo_extra: float = 0.0        # unidades de precio por operacion, restado al resultado
    # filtro SMA
    sma_activo: bool = False
    sma_periodo: int = 200
    sma_dist_min_atr: float = 0.0   # 0 = sin condicion
    sma_pendiente_n: int = 0        # 0 = sin condicion
    # filtro VWAP (diario: se reinicia cada dia del servidor; volumen de ticks)
    vwap_activo: bool = False
    vwap_dist_min_atr: float = 0.5  # el precio debe estar al menos a 0,5 ATR del VWAP (0 = sin condicion); regla practica habitual
    vwap_min_minutos: float = 30.0  # no filtra en los primeros 30 min del dia: al abrir el VWAP es casi igual al precio
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
    sesiones: tuple = ("Tokio", "Londres", "Nueva York")
    horarios: Optional[dict] = None
    servidor_offset_horas: Optional[float] = None   # desfase del servidor en invierno (GMT+2 -> 2)
    servidor_dst_eeuu: bool = True

    def pb_efectivo(self) -> bool:
        """El pullback solo actua si esta activo y el porcentaje es mayor que 0 (0 % = entrada al cierre, como sin pullback)."""
        return bool(self.pullback_activo and self.pullback_pct > 0)

    def validar(self) -> None:
        if self.vwap_dist_min_atr < 0 or self.vwap_min_minutos < 0:
            raise ValueError("Los parametros del VWAP no pueden ser negativos.")
        if not 0 <= self.pullback_pct <= 100:
            raise ValueError("El porcentaje de pullback debe estar entre 0 y 100.")
        if self.pullback_ema not in ("corta", "larga"):
            raise ValueError("La EMA del pullback debe ser 'corta' o 'larga'.")
        if self.pullback_velas < 1:
            raise ValueError("La caducidad del pullback debe ser de al menos 1 vela.")
        if self.ema_corta >= self.ema_larga:
            raise ValueError("La EMA corta debe ser menor que la larga.")
        if self.sl_modo not in ("atr", "pct", "precio") or self.sl_valor <= 0:
            raise ValueError("SL invalido: modo 'atr', 'pct' o 'precio' y valor mayor que 0.")
        if self.sl_modo == "precio":        # SL y TP fijos (p. ej. en dolares): la relacion TP/SL es libre
            if not 0.05 <= self.rr <= 50:
                raise ValueError("La relacion TP/SL debe estar entre 0,05 y 50.")
        elif not 1 <= self.rr <= 10:
            raise ValueError("El RR debe estar entre 1 y 10.")
        if self.direccion not in ("ambas", "largos", "cortos"):
            raise ValueError("Direccion invalida.")
        if self.spread not in ("vela", "mediana", "fijo", "ninguno"):
            raise ValueError("Modo de spread invalido.")
        if self.sesion_activo and self.servidor_offset_horas is None:
            raise ValueError("El filtro de sesion necesita el desfase horario del servidor "
                             "(servidor_offset_horas). Medilo con el mercado abierto.")


FILTROS_APAGADOS = dict(sma_activo=False, vwap_activo=False, adx_activo=False, atr_activo=False, sesion_activo=False, pullback_activo=False)


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
    ema_c: Optional[np.ndarray] = None
    ema_l: Optional[np.ndarray] = None
    sube: Optional[np.ndarray] = None       # cruces alcistas/bajistas de TODA la serie (cancelan ordenes pendientes)
    baja: Optional[np.ndarray] = None
    ok_ses: Optional[np.ndarray] = None     # sesion al EJECUTAR la entrada (solo con pullback)


def es_intradia(df: pd.DataFrame) -> bool:
    """El VWAP diario solo tiene sentido con velas menores a un dia."""
    if len(df) < 3:
        return False
    return bool(pd.Series(df.index).diff().median() < pd.Timedelta(hours=20))


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
    if cfg.sl_modo == "atr":
        dist = atr * cfg.sl_valor
    elif cfg.sl_modo == "pct":
        dist = c * cfg.sl_valor / 100.0
    else:                                   # "precio": la misma distancia en todas las operaciones
        dist = np.full(n, float(cfg.sl_valor))

    warm = cfg.ema_larga + 1        # sin filtros: igual que cruce_minimo.py
    if cfg.sma_activo:
        warm = max(warm, cfg.sma_periodo + max(cfg.sma_pendiente_n, 0))
    if cfg.adx_activo:
        warm = max(warm, 2 * cfg.adx_periodo + max(cfg.adx_creciente_n, 0) + 1)
    if cfg.atr_activo and cfg.atr_rel_n:
        warm = max(warm, cfg.atr_rel_n + cfg.atr_periodo)

    ema_c, ema_l = ind.ema(c, cfg.ema_corta), ind.ema(c, cfg.ema_larga)
    vwap = vwap_min = None
    if cfg.vwap_activo:
        if not es_intradia(df):
            raise ValueError("El filtro VWAP diario necesita velas menores a un dia (H4 o menos).")
        vol = df["Volume"].to_numpy(float) if "Volume" in df else np.ones(n)
        vwap, _ = ind.vwap_diario(h, l, c, vol, df.index.normalize().to_numpy())
        paso = pd.Series(df.index).diff().median()                       # duracion de una vela
        # minutos transcurridos desde el inicio del dia hasta el CIERRE de cada vela
        vwap_min = ((df.index - df.index.normalize()) + paso) / pd.Timedelta(minutes=1)
        vwap_min = np.asarray(vwap_min, float)
    diff = ema_c - ema_l
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

    def ok_vwap(i, lado):
        if vwap_min[i] < cfg.vwap_min_minutos or np.isnan(vwap[i]) or (c[i] - vwap[i]) * lado <= 0:
            return False
        return not (cfg.vwap_dist_min_atr > 0 and abs(c[i] - vwap[i]) < cfg.vwap_dist_min_atr * atr[i])

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
        if cfg.sesion_activo and not cfg.pb_efectivo() and not ok_ses[i]:    # con pullback la sesion se mira al ejecutar
            motivo = "sesion"
        elif cfg.sma_activo and not ok_sma(i, lado):
            motivo = "sma"
        elif cfg.vwap_activo and not ok_vwap(i, lado):
            motivo = "vwap"
        elif cfg.adx_activo and not ok_adx(i):
            motivo = "adx"
        elif cfg.atr_activo and not ok_atr(i):
            motivo = "atr"
        cruces.append((i, lado, motivo))

    sp = _spread(df, cfg)
    raw = df["Spread"].to_numpy(float) if "Spread" in df else np.zeros(n)
    return Preparado(h, l, c, sp, atr, dist, df.index, cruces, 100 * float((raw == 0).mean()),
                     ema_c, ema_l, sube, baja, ok_ses if (cfg.pb_efectivo() and cfg.sesion_activo) else None)


def pb_de(cfg: Config):
    """Parametros del pullback para simular(), o None si no se usa."""
    if not cfg.pb_efectivo():
        return None
    return {"pct": float(cfg.pullback_pct), "ema": cfg.pullback_ema, "velas": int(cfg.pullback_velas)}


def simular(P: Preparado, señales, rr: float, costo_extra: float = 0.0, pb=None):
    """señales: lista de (indice, lado). Devuelve (DataFrame de operaciones, ignoradas).

    pb=None: entrada al cierre de la vela de la señal. pb={"pct","ema","velas"}: la señal deja una orden pendiente.
    El resultado trae en .attrs["pb"] cuantas ordenes se llenaron, caducaron o se cancelaron por cruce contrario.
    En la tabla, "i" es la vela de ENTRADA real y "señal" la vela del cruce (iguales sin pullback)."""
    h, l, c, sp, dist = P.h, P.l, P.c, P.sp, P.dist
    n = len(c)
    filas, libre, ignoradas = [], 0, 0
    st = {"ordenes": 0, "llenadas": 0, "caducadas": 0, "cruce_contrario": 0}

    def recorrer(desde, lado, sl, tp):
        for j in range(desde, n):
            if lado == 1:
                hit_sl, hit_tp = l[j] <= sl, h[j] >= tp
            else:
                hit_sl, hit_tp = h[j] + sp[j] >= sl, l[j] + sp[j] <= tp
            if hit_sl and hit_tp:
                return "SL", True, j
            if hit_sl:
                return "SL", False, j
            if hit_tp:
                return "TP", False, j
        return "ABIERTA", False, n - 1

    for i, lado in señales:
        if i < libre:                                   # operacion en curso (o orden pendiente): se ignora
            ignoradas += 1
            continue
        if pb is None:
            k = i                                       # vela de entrada
            d = dist[k]
            if not d > 0:
                continue
            entrada = c[i] + sp[i] if lado == 1 else c[i]
            sl, tp = entrada - lado * d, entrada + lado * d * rr
            res, amb, j_out = recorrer(i + 1, lado, sl, tp)
        else:
            st["ordenes"] += 1
            ema = P.ema_c if pb["ema"] == "corta" else P.ema_l
            frac = pb["pct"] / 100.0
            ext = h[i] if lado == 1 else l[i]           # extremo desde el cruce, hasta la vela anterior
            contra = P.baja if lado == 1 else P.sube
            fin = min(i + pb["velas"], n - 1)
            k, px, fin_esp, motivo = None, None, fin, "caducadas"
            for j in range(i + 1, fin + 1):
                e = ema[j - 1]                          # EMA conocida al dejar la orden
                if lado == 1:
                    nivel = ext - frac * max(ext - e, 0.0)
                    toca = l[j] <= nivel
                else:
                    nivel = ext + frac * max(e - ext, 0.0)
                    toca = h[j] >= nivel
                if toca and (P.ok_ses is None or P.ok_ses[j]):
                    k = j
                    px = min(nivel, h[j]) if lado == 1 else max(nivel, l[j])
                    break
                if contra is not None and contra[j]:   # cruce contrario: se descarta la orden
                    fin_esp, motivo = j - 1, "cruce_contrario"
                    break
                ext = max(ext, h[j]) if lado == 1 else min(ext, l[j])
            if k is None:
                st[motivo] += 1
                libre = fin_esp + 1
                continue
            d = dist[k]
            if not d > 0:
                continue
            st["llenadas"] += 1
            entrada = px + sp[k] if lado == 1 else px
            sl, tp = entrada - lado * d, entrada + lado * d * rr
            # en la vela de entrada no se sabe que paso primero: si toca el SL, cuenta como SL; el TP recien desde la siguiente
            toca_sl = l[k] <= sl if lado == 1 else h[k] + sp[k] >= sl
            if toca_sl:
                res, amb, j_out = "SL", True, k
            else:
                res, amb, j_out = recorrer(k + 1, lado, sl, tp)
        r = rr if res == "TP" else (-1.0 if res == "SL" else 0.0)
        if res != "ABIERTA" and costo_extra:
            r -= costo_extra / d
        filas.append({"i": k, "señal": i, "lado": lado, "entrada": entrada, "sl": sl, "tp": tp, "dist": d,
                      "res": res, "amb": amb, "salida": j_out, "R": r})
        if res == "ABIERTA":
            break
        libre = j_out + 1
    cols = ["i", "señal", "lado", "entrada", "sl", "tp", "dist", "res", "amb", "salida", "R"]
    out = pd.DataFrame(filas, columns=cols)
    out.attrs["pb"] = st
    return out, ignoradas


@dataclass
class Resultado:
    trades: pd.DataFrame
    descartes: dict = field(default_factory=dict)
    cruces: int = 0                 # cruces detectados en el tramo
    tomados: int = 0                # cruces que pasaron todos los filtros
    ignoradas: int = 0              # cruces que pasaron filtros pero habia operacion abierta
    pb: dict = field(default_factory=dict)   # ordenes / llenadas / caducadas / cruce_contrario (vacio sin pullback)


def ejecutar(P: Preparado, cfg: Config, lo: int = 0, hi: Optional[int] = None) -> Resultado:
    hi = len(P.c) if hi is None else hi
    en_rango = [x for x in P.cruces if lo <= x[0] < hi]
    descartes = {}
    for _, _, m in en_rango:
        if m:
            descartes[m] = descartes.get(m, 0) + 1
    señales = [(i, lado) for i, lado, m in en_rango if m is None]
    pb = pb_de(cfg)
    tr, ign = simular(P, señales, cfg.rr, cfg.costo_extra, pb)
    return Resultado(tr, descartes, len(en_rango), len(señales), ign, dict(tr.attrs.get("pb", {})) if pb else {})
