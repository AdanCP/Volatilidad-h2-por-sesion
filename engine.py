"""Motor del backtest de cruce de medias moviles (EMA o SMA) con filtros opcionales (sesion, SMA, ADX, ATR).

Señal (config.media_tipo y config.modo_senal):
  - modo "cruce" (por defecto): la media corta cruza a la larga. media_tipo "ema" (por defecto) o "sma".
  - modo "precio": el CIERRE cruza una sola media (config.media_unica). Alcista = el cierre pasa de debajo a encima.

Reglas (ver prompt):
  - Entrada al CIERRE de la vela del cruce (alcista = largo, bajista = corto).
  - Filtros evaluados con datos de la vela de la señal, en este orden: sesion, SMA, VWAP, ADX, rango (ratio de eficiencia), ATR.
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


SENTIDOS_PAUSA = ("ambos", "mismo", "contrario")


@dataclass
class Config:
    # señal y gestion
    ema_corta: int = 13             # media corta del modo "cruce" (el nombre se mantiene aunque sea SMA)
    ema_larga: int = 34
    media_tipo: str = "ema"         # "ema" | "sma": tipo de media de la señal (el FILTRO SMA es aparte)
    modo_senal: str = "cruce"       # "cruce" (dos medias) | "precio" (el cierre cruza una sola media)
    media_unica: int = 50           # periodo de la media en el modo "precio"
    rr: float = 2.0
    salida_modo: str = "rr"         # "rr" (TP fijo a RR) | "senal" (sin TP: sale al cierre de la 1ª vela del otro lado de la media)
    sl_modo: str = "atr"            # "atr" (multiplo), "pct" (% del precio) o "precio" (distancia fija en unidades de precio) o "ema" (nivel fijo: media elegida a esa distancia, al entrar)
    sl_valor: float = 1.5           # con sl_modo "ema": distancia (en unidades de precio) entre la media y el SL
    sl_ema_pct: bool = False        # con sl_modo "ema": sl_valor es un % del nivel de referencia (y no unidades de precio)
    sl_ema_ref: str = "larga"       # con sl_modo "ema": "cruce" (punto medio de las dos medias: el nivel del cruce), "corta" o "larga" (en modo precio, la unica media)
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
    # filtro de rango (ratio de eficiencia de Kaufman): desplazamiento neto / recorrido total de las ultimas N velas
    rango_activo: bool = False
    rango_ventana: int = 20
    rango_min: float = 0.30         # por debajo no se opera: el precio va y viene sin avanzar
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
    sin_pausa: tuple = ()           # sesiones a las que se les excluye la pausa de mediodia (solo bloquea entradas nuevas)
    servidor_offset_horas: Optional[float] = None   # desfase del servidor en invierno (GMT+2 -> 2)
    servidor_dst_eeuu: bool = True
    # reglas de la cuenta (limites de perdida, protecciones y controles de operacion)
    reglas_activas: bool = False            # False: el backtest no simula la cuenta (como hasta ahora)
    capital: float = 0.0                    # capital inicial de la cuenta (US$)
    usd_por_unidad: float = 0.0             # US$ por cada 1,00 de precio con los lotes elegidos
    comision_op_usd: float = 0.0            # comision por operacion (US$) = comision por lote x lotes
    perd_dia_pct: float = 5.0               # perdida diaria maxima (% del capital; 0 = sin limite)
    perd_dia_modo: str = "trailing"         # "trailing": % del balance de inicio del dia | "estatico": % del capital inicial
    perd_tot_pct: float = 10.0              # perdida total maxima (% del capital; 0 = sin limite)
    perd_tot_modo: str = "estatico"         # "estatico": piso fijo desde el capital inicial | "trailing": desde el balance maximo
    colchon_pct: float = 1.0                # se resta a los dos limites: el bot frena ese margen antes
    proteger_sl: bool = True                # no abrir si el SL, perdiendo al maximo, rompe un limite
    riesgo_op_activo: bool = False
    riesgo_op_pct: float = 1.0              # riesgo maximo por operacion (% del capital); si lo supera, se saltea
    pausa_activa: bool = False
    pausa_min: float = 60.0                 # minutos sin operar tras una operacion perdedora; las señales dentro se descartan
    pausa_sentido: str = "ambos"            # a que señales frena la pausa tras una perdida: "ambos" | "mismo" | "contrario" (sentido de la operacion cerrada)
    pausa_gan_activa: bool = False
    pausa_gan_min: float = 60.0             # minutos sin operar tras una operacion ganadora; las señales dentro se descartan
    pausa_gan_sentido: str = "ambos"        # idem para la pausa tras una ganancia
    pausa_gan_retroceso_activo: bool = False  # condicion de precio independiente de la pausa por minutos (pueden ir juntas o por separado)
    pausa_gan_retroceso_pct: float = 50.0   # (solo si esta activo). >0: tras una ganancia, para volver a operar en el MISMO sentido el precio
                                            # tiene que retroceder este % del recorrido de esa operacion (entrada -> cierre), medido desde el cierre
    pausa_gan_vence: str = "nunca"          # hasta cuando rige la condicion de precio: "nunca" | "dia" (fin del dia CE(S)T) | "horas"
    pausa_gan_vence_h: float = 24.0
    retiro_activo: bool = False             # retirar toda la ganancia del ciclo al llegar al objetivo (solo con reglas de cuenta)
    retiro_pct: float = 5.0                 # objetivo por retiro (% del capital inicial)

    def pb_efectivo(self) -> bool:
        """El pullback solo actua si esta activo y el porcentaje es mayor que 0 (0 % = entrada al cierre, como sin pullback)."""
        return bool(self.pullback_activo and self.pullback_pct > 0)

    def limites_efectivos(self) -> tuple:
        """(diario, total) en % tras restar el colchon; 0 = sin limite."""
        def ef(p):
            return max(p - self.colchon_pct, 0.0) if p > 0 else 0.0
        return ef(self.perd_dia_pct), ef(self.perd_tot_pct)

    def _validar_reglas(self) -> None:
        if self.perd_dia_modo not in ("trailing", "estatico") or self.perd_tot_modo not in ("trailing", "estatico"):
            raise ValueError("El modo de los limites de perdida debe ser 'trailing' o 'estatico'.")
        if not (0 <= self.perd_dia_pct <= 100 and 0 <= self.perd_tot_pct <= 100):
            raise ValueError("Los limites de perdida deben estar entre 0 y 100 %.")
        if self.colchon_pct < 0:
            raise ValueError("El colchon no puede ser negativo.")
        if self.retiro_activo and not (0 < self.retiro_pct <= 100):
            raise ValueError("El objetivo por retiro debe ser mayor que 0 y no pasar de 100 %.")
        for nombre, p in (("diario", self.perd_dia_pct), ("total", self.perd_tot_pct)):
            if 0 < p <= self.colchon_pct:
                raise ValueError(f"El colchon ({self.colchon_pct:g} %) debe ser menor que el limite {nombre} ({p:g} %).")
        if self.riesgo_op_activo and not 0 < self.riesgo_op_pct <= 100:
            raise ValueError("El riesgo maximo por operacion debe estar entre 0 y 100 %.")
        if self.pausa_sentido not in SENTIDOS_PAUSA or self.pausa_gan_sentido not in SENTIDOS_PAUSA:
            raise ValueError("El sentido de la pausa debe ser 'ambos', 'mismo' o 'contrario'.")
        if self.pausa_gan_retroceso_pct < 0 or self.pausa_gan_vence not in ("nunca", "dia", "horas") or \
                (self.pausa_gan_vence == "horas" and self.pausa_gan_vence_h <= 0):
            raise ValueError("El retroceso debe ser >= 0 y el vencimiento 'nunca', 'dia' u 'horas' (con horas > 0).")
        if (self.pausa_activa and self.pausa_min < 0) or (self.pausa_gan_activa and self.pausa_gan_min < 0):
            raise ValueError("El tiempo minimo entre operaciones no puede ser negativo.")
        if self.reglas_activas and (self.capital <= 0 or self.usd_por_unidad <= 0):
            raise ValueError("Las reglas de cuenta necesitan el capital de la cuenta y el valor por unidad de precio "
                             "(cargá el capital en «Lotaje y dinero»).")

    def validar(self) -> None:
        if self.vwap_dist_min_atr < 0 or self.vwap_min_minutos < 0:
            raise ValueError("Los parametros del VWAP no pueden ser negativos.")
        if not 0 <= self.pullback_pct <= 100:
            raise ValueError("El porcentaje de pullback debe estar entre 0 y 100.")
        if self.pullback_ema not in ("corta", "larga"):
            raise ValueError("La EMA del pullback debe ser 'corta' o 'larga'.")
        if self.pullback_velas < 1:
            raise ValueError("La caducidad del pullback debe ser de al menos 1 vela.")
        if self.media_tipo not in ("ema", "sma"):
            raise ValueError("El tipo de media debe ser 'ema' o 'sma'.")
        if self.modo_senal not in ("cruce", "precio"):
            raise ValueError("El modo de señal debe ser 'cruce' o 'precio'.")
        if self.modo_senal == "cruce" and self.ema_corta >= self.ema_larga:
            raise ValueError(f"La {self.media_tipo.upper()} corta debe ser menor que la larga.")
        if self.modo_senal == "precio" and self.media_unica < 2:
            raise ValueError("El período de la media debe ser de al menos 2.")
        self._validar_reglas()
        if self.rango_activo and (self.rango_ventana < 2 or not 0 <= self.rango_min <= 1):
            raise ValueError("Filtro de rango: la ventana debe ser de al menos 2 velas y el ratio minimo estar entre 0 y 1.")
        if self.salida_modo not in ("rr", "senal"):
            raise ValueError("Modo de salida invalido: 'rr' o 'senal'.")
        if self.sl_modo not in ("atr", "pct", "precio", "ema") or self.sl_valor < 0 or (self.sl_modo != "ema" and self.sl_valor <= 0):
            raise ValueError("SL invalido: modo 'atr', 'pct', 'precio' o 'ema' y valor mayor que 0 (con 'ema' puede ser 0).")
        if self.sl_ema_ref not in ("corta", "larga", "cruce"):
            raise ValueError("La referencia del SL debe ser 'cruce', 'corta' o 'larga'.")
        if self.salida_modo == "senal":     # sin TP: el RR no interviene
            pass
        elif self.sl_modo in ("precio", "ema"):        # SL y TP fijos (p. ej. en dolares): la relacion TP/SL es libre
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


FILTROS_APAGADOS = dict(sma_activo=False, vwap_activo=False, adx_activo=False, rango_activo=False, atr_activo=False, sesion_activo=False, pullback_activo=False)


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
    dia: Optional[np.ndarray] = None        # clave de dia de cada vela (reglas de cuenta); corte a medianoche CE(S)T si se conoce el desfase
    diff: Optional[np.ndarray] = None       # lado de la media por vela: >0 arriba (alcista), <0 abajo; base de la salida por señal
    sl_ref: Optional[np.ndarray] = None     # media de referencia del SL (solo con sl_modo "ema"): el SL queda en sl_ref -/+ sl_off
    sl_off: object = 0.0                    # distancia entre la media y el SL, en unidades de precio (un numero, o una por vela si va en %)


def _off(P, i: int) -> float:
    """Distancia entre la referencia y el SL en la vela i (en unidades de precio)."""
    return float(P.sl_off[i]) if isinstance(P.sl_off, np.ndarray) else float(P.sl_off)


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
    elif cfg.sl_modo == "ema":              # el SL real se calcula al entrar; mas abajo se deja un valor tipico (solo informativo)
        dist = None
    else:                                   # "precio": la misma distancia en todas las operaciones
        dist = np.full(n, float(cfg.sl_valor))

    modo_precio = cfg.modo_senal == "precio"
    warm = (cfg.media_unica if modo_precio else cfg.ema_larga) + 1        # sin filtros: igual que cruce_minimo.py
    if cfg.sma_activo:
        warm = max(warm, cfg.sma_periodo + max(cfg.sma_pendiente_n, 0))
    if cfg.adx_activo:
        warm = max(warm, 2 * cfg.adx_periodo + max(cfg.adx_creciente_n, 0) + 1)
    if cfg.rango_activo:
        warm = max(warm, cfg.rango_ventana + 1)
    if cfg.atr_activo and cfg.atr_rel_n:
        warm = max(warm, cfg.atr_rel_n + cfg.atr_periodo)

    media = ind.sma if cfg.media_tipo == "sma" else ind.ema
    if modo_precio:                         # una sola media: el pullback la usa como referencia (corta = larga)
        ema_c = ema_l = media(c, cfg.media_unica)
    else:
        ema_c, ema_l = media(c, cfg.ema_corta), media(c, cfg.ema_larga)
    sl_ref, sl_off = None, 0.0
    if cfg.sl_modo == "ema":
        # SL anclado a una media: nivel = media (de la vela de la señal, o de la anterior al llenado con pullback) -/+ la distancia.
        # La distancia que se arriesga cambia en cada operacion, asi que "dist" aca es solo un valor tipico para avisos.
        if cfg.sl_ema_ref == "cruce":
            sl_ref = (ema_c + ema_l) / 2.0      # en la vela del cruce las dos medias valen casi lo mismo: el punto medio es el nivel del cruce
        else:
            sl_ref = ema_c if cfg.sl_ema_ref == "corta" else ema_l
        # distancia entre la referencia y el SL: fija (precio) o un % del nivel de referencia (cambia con el precio)
        sl_off = np.abs(sl_ref) * float(cfg.sl_valor) / 100.0 if cfg.sl_ema_pct else float(cfg.sl_valor)
        dist = np.nan_to_num(np.abs(c - sl_ref) + sl_off, nan=0.0 if cfg.sl_ema_pct else float(cfg.sl_valor))
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
    diff = (c - ema_c) if modo_precio else (ema_c - ema_l)
    prev = np.r_[np.nan, diff[:-1]]
    sube, baja = (diff > 0) & (prev <= 0), (diff < 0) & (prev >= 0)

    sma = ind.sma(c, cfg.sma_periodo) if cfg.sma_activo else None
    adx = ind.adx_wilder(h, l, c, cfg.adx_periodo)[0] if cfg.adx_activo else None
    er = ind.eficiencia(c, cfg.rango_ventana) if cfg.rango_activo else None
    atr_pct = atr / c * 100.0
    atr_med = pd.Series(atr).rolling(cfg.atr_rel_n).mean().to_numpy() if (cfg.atr_activo and cfg.atr_rel_n) else None
    ok_ses = None
    if cfg.sesion_activo:
        utc = ses.servidor_a_utc(df.index, cfg.servidor_offset_horas, cfg.servidor_dst_eeuu)
        ok_ses = ses.mascara_sesiones(utc, cfg.sesiones, cfg.horarios, cfg.sin_pausa)

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

    def ok_rango(i):
        return not np.isnan(er[i]) and er[i] >= cfg.rango_min

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
        elif cfg.rango_activo and not ok_rango(i):
            motivo = "rango"
        elif cfg.atr_activo and not ok_atr(i):
            motivo = "atr"
        cruces.append((i, lado, motivo))

    sp = _spread(df, cfg)
    raw = df["Spread"].to_numpy(float) if "Spread" in df else np.zeros(n)
    return Preparado(h, l, c, sp, atr, dist, df.index, cruces, 100 * float((raw == 0).mean()),
                     ema_c, ema_l, sube, baja, ok_ses if (cfg.pb_efectivo() and cfg.sesion_activo) else None,
                     claves_dia(df.index, cfg) if cfg.reglas_activas else None, diff,
                     sl_ref, sl_off)


def pb_de(cfg: Config):
    """Parametros del pullback para simular(), o None si no se usa."""
    if not cfg.pb_efectivo():
        return None
    return {"pct": float(cfg.pullback_pct), "ema": cfg.pullback_ema, "velas": int(cfg.pullback_velas)}


def claves_dia(indice: pd.DatetimeIndex, cfg: Config) -> np.ndarray:
    """Clave de dia (dias desde 1970) de cada vela para las reglas de cuenta. Con el desfase del servidor cargado, el dia
    se corta a medianoche de Europa Central (hora CE(S)T, la que usa FTMO); sin el, a medianoche de los datos."""
    if cfg.servidor_offset_horas is not None:
        utc = ses.servidor_a_utc(indice, cfg.servidor_offset_horas, cfg.servidor_dst_eeuu)
        local = pd.DatetimeIndex(utc).tz_localize("UTC").tz_convert("Europe/Berlin").tz_localize(None)
    else:
        local = pd.DatetimeIndex(indice)
    return local.normalize().to_numpy().astype("datetime64[D]").astype("int64")


def cuenta_de(P: Preparado, cfg: Config):
    """Parametros de la simulacion de cuenta para simular(), o None si las reglas no estan aplicadas."""
    if not cfg.reglas_activas:
        return None
    if P.dia is None:
        raise ValueError("Las reglas de cuenta necesitan preparar() con esta configuracion.")
    p_dia, p_tot = cfg.limites_efectivos()
    return {"capital": float(cfg.capital), "vu": float(cfg.usd_por_unidad), "comision": float(cfg.comision_op_usd),
            "p_dia": p_dia, "modo_dia": cfg.perd_dia_modo, "p_tot": p_tot, "modo_tot": cfg.perd_tot_modo,
            "proteger": bool(cfg.proteger_sl), "riesgo_pct": float(cfg.riesgo_op_pct) if cfg.riesgo_op_activo else None,
            "pausa_min": float(cfg.pausa_min) if cfg.pausa_activa else None, "dia": P.dia,
            "pausa_gan_min": float(cfg.pausa_gan_min) if cfg.pausa_gan_activa else None,
            "pausa_sentido": cfg.pausa_sentido, "pausa_gan_sentido": cfg.pausa_gan_sentido,
            "gan_retro_pct": float(cfg.pausa_gan_retroceso_pct) if (cfg.pausa_gan_retroceso_activo and cfg.pausa_gan_retroceso_pct > 0) else None,
            "gan_vence": cfg.pausa_gan_vence, "gan_vence_h": float(cfg.pausa_gan_vence_h),
            "retiro_usd": float(cfg.capital) * float(cfg.retiro_pct) / 100.0 if (cfg.retiro_activo and cfg.retiro_pct > 0) else None}


def simular(P: Preparado, señales, rr: float, costo_extra: float = 0.0, pb=None, salida: str = "rr", cuenta=None):
    """señales: lista de (indice, lado). Devuelve (DataFrame de operaciones, ignoradas).

    pb=None: entrada al cierre de la vela de la señal. pb={"pct","ema","velas"}: la señal deja una orden pendiente.
    El resultado trae en .attrs["pb"] cuantas ordenes se llenaron, caducaron o se cancelaron por cruce contrario.
    salida="senal": no hay TP. Se sale al CIERRE de la primera vela (posterior a la de entrada) que cierra del otro lado de
    la media (diff de signo contrario al del lado); el SL sigue vigente y se revisa antes en cada vela. La tabla trae
    "motivo" (tp / sl / senal / limite): una salida por señal se rotula TP si gana y SL si pierde, con su R real.
    cuenta (ver cuenta_de): simula la cuenta en orden cronologico con limites de perdida diaria y total, proteccion del SL,
    riesgo maximo por operacion y pausa tras una perdida; el resumen queda en .attrs["cuenta"]. Si el equity llega a un
    limite con una operacion abierta, se cierra en ese nivel (motivo "limite").
    En la tabla, "i" es la vela de ENTRADA real y "señal" la vela del cruce (iguales sin pullback)."""
    h, l, c, sp, dist = P.h, P.l, P.c, P.sp, P.dist
    n = len(c)
    filas, libre, ignoradas, sl_invalido = [], 0, 0, 0
    st = {"ordenes": 0, "llenadas": 0, "caducadas": 0, "cruce_contrario": 0}
    por_senal = salida == "senal"
    if por_senal and P.diff is None:
        raise ValueError("La salida por señal necesita el lado de la media (preparar() con esta version).")

    # ---- estado de la cuenta (solo con reglas)
    ct = cuenta
    if ct:
        cap, vu, comm = ct["capital"], ct["vu"], ct["comision"]
        dia = ct["dia"] if ct.get("dia") is not None else P.dia
        ts_min = P.indice.to_numpy().astype("datetime64[s]").astype("int64") / 60.0
        cs = {"saltadas_dia": 0, "saltadas_pausa": 0, "saltadas_pausa_gan": 0, "saltadas_retroceso": 0, "saltadas_riesgo": 0, "saltadas_proteccion": 0, "forzadas": 0,
              "dias_bloqueados": 0, "quemada": False, "quemada_en": None, "peor_dia_usd": 0.0,
              "balance_final": cap, "balance_min": cap, "balance_max": cap, "retiros": [], "retirado": 0.0}
        S = {"bal": cap, "pico": cap, "dia": None, "bal_dia": cap, "bloq": None, "perd_j": {1: None, -1: None}, "gan_j": {1: None, -1: None}, "gan_ref": {1: None, -1: None}}

    def frena(minutos, ultimos, sentido, lado, i):
        """True si la señal `lado` de la vela i cae dentro del tiempo minimo. `ultimos` = ultima operacion cerrada de ese tipo
        (perdedora o ganadora) por sentido; sentido: ambos = la mas reciente de las dos, mismo = la del mismo lado de la señal,
        contrario = la del lado opuesto."""
        if minutos is None:
            return False
        if sentido == "mismo":
            j = ultimos[lado]
        elif sentido == "contrario":
            j = ultimos[-lado]
        else:
            vistos = [x for x in ultimos.values() if x is not None]
            j = max(vistos) if vistos else None
        return j is not None and ts_min[i] - ts_min[j] < minutos

    def sin_retroceso(lado, i):
        """True si la señal `lado` de la vela i NO cumple el retroceso exigido tras la ultima ganadora del MISMO sentido."""
        pct = ct.get("gan_retro_pct")
        if pct is None or S["gan_j"][lado] is None:
            return False
        j = S["gan_j"][lado]
        venc = ct.get("gan_vence", "nunca")
        if venc == "horas" and ts_min[i] - ts_min[j] >= ct.get("gan_vence_h", 24.0) * 60.0:
            return False
        if venc == "dia" and dia[i] != dia[j]:
            return False
        ref, recorrido = S["gan_ref"][lado]
        px = c[i] + sp[i] if lado == 1 else c[i]                 # precio al que entraria la señal
        nivel = ref - lado * pct / 100.0 * recorrido             # compra: por debajo del cierre; venta: por encima
        return px > nivel if lado == 1 else px < nivel

    def rodar_dia(k):
        if S["dia"] != dia[k]:
            S["dia"], S["bal_dia"] = dia[k], S["bal"]

    def pisos():
        pd_, pt_ = -np.inf, -np.inf
        if ct["p_dia"] > 0:
            pd_ = (S["bal_dia"] * (1 - ct["p_dia"] / 100.0) if ct["modo_dia"] == "trailing"
                   else S["bal_dia"] - ct["p_dia"] / 100.0 * cap)
        if ct["p_tot"] > 0:
            pt_ = (S["pico"] if ct["modo_tot"] == "trailing" else cap) * (1 - ct["p_tot"] / 100.0)
        return pd_, pt_

    def puerta(d):
        """None si se puede abrir una operacion con SL a distancia d; si no, el motivo por el que se saltea.
        Si se abre, devuelve ("ok", distancia de precio a la que el equity toca un limite o None)."""
        riesgo = d * vu + comm
        if ct["riesgo_pct"] is not None and riesgo / cap * 100.0 > ct["riesgo_pct"] + 1e-12:
            return "saltadas_riesgo", None
        pd_, pt_ = pisos()
        if ct["proteger"] and (S["bal"] - riesgo <= pd_ or S["bal"] - riesgo <= pt_):
            return "saltadas_proteccion", None
        margen = min(S["bal"] - pd_, S["bal"] - pt_) - comm       # US$ que puede perder antes de tocar un limite
        lim = max(margen, 0.0) / vu
        return "ok", (lim if lim < d else None)

    def cerrar(r, d, j_out, lado, entrada):
        """Aplica el resultado de la operacion a la cuenta y revisa los limites."""
        pnl = r * d * vu - comm
        rodar_dia(j_out)                 # si cruzo la medianoche, el dia nuevo parte del balance previo a este cierre
        S["bal"] += pnl
        S["pico"] = max(S["pico"], S["bal"])
        cs["peor_dia_usd"] = min(cs["peor_dia_usd"], S["bal"] - S["bal_dia"])
        cs["balance_min"] = min(cs["balance_min"], S["bal"])
        cs["balance_max"] = S["pico"]                    # si se quema, es lo maximo que llego a ganar antes de quemarse
        if pnl < 0:
            S["perd_j"][lado] = j_out
        elif pnl > 0:
            S["gan_j"][lado] = j_out
            S["gan_ref"][lado] = (entrada + lado * r * d, abs(r) * d)       # (precio de cierre, recorrido entrada -> cierre)
        pd_, pt_ = pisos()
        if S["bal"] <= pt_ + 1e-9:
            cs["quemada"], cs["quemada_en"] = True, j_out
        elif S["bal"] <= pd_ + 1e-9 and S["bloq"] != dia[j_out]:
            S["bloq"] = dia[j_out]
            cs["dias_bloqueados"] += 1
        if not cs["quemada"] and ct.get("retiro_usd") and S["bal"] - cap >= ct["retiro_usd"] - 1e-9:
            # retiro: se saca TODA la ganancia del ciclo y el balance vuelve al capital inicial. El piso trailing se mantiene
            # (S["pico"] no baja) y el retiro no cuenta como perdida del dia: se resta tambien del balance de inicio del dia.
            w = S["bal"] - cap
            S["bal"] = cap
            S["bal_dia"] -= w
            cs["retiros"].append({"j": int(j_out), "monto": float(w)})
            cs["retirado"] += float(w)

    def recorrer(desde, lado, sl, tp, entrada=None, lim=None):
        for j in range(desde, n):
            if lim is not None:                          # el equity toca un limite de cuenta antes que el SL
                adverso = (entrada - l[j]) if lado == 1 else (h[j] + sp[j] - entrada)
                if adverso >= lim:
                    return "LIM", False, j
            if por_senal:
                if (l[j] <= sl) if lado == 1 else (h[j] + sp[j] >= sl):
                    return "SL", False, j
                if (P.diff[j] < 0) if lado == 1 else (P.diff[j] > 0):
                    return "SEN", False, j
                continue
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
        if ct:
            if cs["quemada"]:
                break
            rodar_dia(i)
            if S["bloq"] == dia[i]:                     # dia bloqueado por el limite diario
                cs["saltadas_dia"] += 1
                continue
            if frena(ct["pausa_min"], S["perd_j"], ct.get("pausa_sentido", "ambos"), lado, i):
                cs["saltadas_pausa"] += 1
                continue
            if frena(ct.get("pausa_gan_min"), S["gan_j"], ct.get("pausa_gan_sentido", "ambos"), lado, i):
                cs["saltadas_pausa_gan"] += 1
                continue
            if sin_retroceso(lado, i):
                cs["saltadas_retroceso"] += 1
                continue
        lim = None
        if pb is None:
            k = i                                       # vela de entrada
            entrada = c[i] + sp[i] if lado == 1 else c[i]
            if P.sl_ref is not None:                    # SL anclado a una media: nivel fijo, la distancia sale de ahi
                d = lado * (entrada - (P.sl_ref[i] - lado * _off(P, i)))
                if not d > 0:
                    sl_invalido += 1                    # la media quedo del lado equivocado del precio: no se opera
                    continue
            else:
                d = dist[k]
            if not d > 0:
                continue
            if ct:
                motivo_p, lim = puerta(d)
                if motivo_p != "ok":
                    cs[motivo_p] += 1
                    continue
            sl, tp = entrada - lado * d, (np.nan if por_senal else entrada + lado * d * rr)
            res, amb, j_out = recorrer(i + 1, lado, sl, tp, entrada, lim)
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
            entrada = px + sp[k] if lado == 1 else px
            if P.sl_ref is not None:                    # el nivel se fija con la media conocida al dejar la orden (vela anterior al llenado)
                d = lado * (entrada - (P.sl_ref[k - 1] - lado * _off(P, k - 1)))
                if not d > 0:
                    sl_invalido += 1
                    libre = k + 1
                    continue
            else:
                d = dist[k]
            if not d > 0:
                continue
            if ct:
                motivo_p, lim = puerta(d)
                if motivo_p != "ok":
                    cs[motivo_p] += 1
                    libre = k + 1
                    continue
            st["llenadas"] += 1
            sl, tp = entrada - lado * d, (np.nan if por_senal else entrada + lado * d * rr)
            # en la vela de entrada no se sabe que paso primero: si toca el SL, cuenta como SL; el TP recien desde la siguiente
            toca_sl = l[k] <= sl if lado == 1 else h[k] + sp[k] >= sl
            if lim is not None and ((entrada - l[k]) if lado == 1 else (h[k] + sp[k] - entrada)) >= lim:
                res, amb, j_out = "LIM", True, k
            elif toca_sl:
                res, amb, j_out = "SL", True, k
            else:
                res, amb, j_out = recorrer(k + 1, lado, sl, tp, entrada, lim)
        motivo_sal = {"TP": "tp", "SL": "sl", "SEN": "senal", "LIM": "limite"}.get(res, "")
        if res == "SEN":                                # sale al cierre: el largo vende al bid, el corto compra al ask
            salida_px = c[j_out] if lado == 1 else c[j_out] + sp[j_out]
            r = lado * (salida_px - entrada) / d
            res = "TP" if r > 0 else "SL"
        elif res == "LIM":                              # el bot cierra todo cuando el equity toca el limite
            r = -lim / d
            res = "SL"
            cs["forzadas"] += 1
        else:
            r = rr if res == "TP" else (-1.0 if res == "SL" else 0.0)
        if res != "ABIERTA" and costo_extra:
            r -= costo_extra / d
        filas.append({"i": k, "señal": i, "lado": lado, "entrada": entrada, "sl": sl, "tp": tp, "dist": d,
                      "res": res, "amb": amb, "salida": j_out, "R": r, "motivo": motivo_sal})
        if res == "ABIERTA":
            break
        libre = j_out + 1
        if ct:
            cerrar(r, d, j_out, lado, entrada)
    cols = ["i", "señal", "lado", "entrada", "sl", "tp", "dist", "res", "amb", "salida", "R", "motivo"]
    out = pd.DataFrame(filas, columns=cols)
    out.attrs["pb"] = st
    out.attrs["sl_invalido"] = sl_invalido            # señales sin operar porque el SL anclado a la media quedaba al reves
    if ct:
        cs["balance_final"] = S["bal"]
        out.attrs["cuenta"] = cs
    return out, ignoradas


@dataclass
class Resultado:
    trades: pd.DataFrame
    descartes: dict = field(default_factory=dict)
    cruces: int = 0                 # cruces detectados en el tramo
    tomados: int = 0                # cruces que pasaron todos los filtros
    ignoradas: int = 0              # cruces que pasaron filtros pero habia operacion abierta
    pb: dict = field(default_factory=dict)   # ordenes / llenadas / caducadas / cruce_contrario (vacio sin pullback)
    cuenta: dict = field(default_factory=dict)   # resumen de las reglas de cuenta (vacio si no se aplican)


def ejecutar(P: Preparado, cfg: Config, lo: int = 0, hi: Optional[int] = None) -> Resultado:
    hi = len(P.c) if hi is None else hi
    en_rango = [x for x in P.cruces if lo <= x[0] < hi]
    descartes = {}
    for _, _, m in en_rango:
        if m:
            descartes[m] = descartes.get(m, 0) + 1
    señales = [(i, lado) for i, lado, m in en_rango if m is None]
    pb = pb_de(cfg)
    tr, ign = simular(P, señales, cfg.rr, cfg.costo_extra, pb, cfg.salida_modo, cuenta_de(P, cfg))
    return Resultado(tr, descartes, len(en_rango), len(señales), ign, dict(tr.attrs.get("pb", {})) if pb else {},
                     dict(tr.attrs.get("cuenta", {})))
