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
    # filtros de tendencia mayor (dos independientes): compra solo si el cierre de la ultima vela YA CERRADA de esa temporalidad esta
    # sobre su SMA, venta solo si esta debajo. Sin SMA todavia (arranque del historial) la señal se descarta.
    tm1_activo: bool = False
    tm1_tf: str = "H1"
    tm1_periodo: int = 200
    tm2_activo: bool = False
    tm2_tf: str = "H4"
    tm2_periodo: int = 200
    # filtro Volume Profile: perfil de volumen (volumen de ticks) de los ultimos N dias completos YA CERRADOS (dia CE(S)T), fijo durante todo el dia.
    # modo "poc": compra sobre el POC / venta bajo el POC | "fuera": compra sobre el VAH / venta bajo el VAL | "dentro": solo entre VAL y VAH.
    vp_activo: bool = False
    vp_modo: str = "poc"
    vp_dias: int = 1
    vp_escalon: float = 1.0         # tamaño del escalon de precio (unidades de precio)
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
    cortes: Optional[dict] = None   # {sesion: (desde, hasta)} en hora LOCAL de la plaza: horario que se le descuenta a esa sesion (solo entradas nuevas)
    sin_pausa: tuple = ()           # sesiones a las que se les excluye la pausa de mediodia (solo bloquea entradas nuevas)
    servidor_offset_horas: Optional[float] = None   # desfase del servidor en invierno (GMT+2 -> 2)
    servidor_dst_eeuu: bool = True
    # fin de semana: con finde_mantener=False toda operacion abierta se cierra en la ultima vela de la semana (la que viene seguida
    # de un hueco de mas de 30 h, ~cierre del viernes de Nueva York), las ordenes pendientes del pullback se cancelan y, si
    # finde_no_abrir_desde no es None, el viernes no se abren operaciones desde esa hora (HORA LOCAL DE NUEVA YORK, [desde, ...))
    finde_mantener: bool = True
    finde_no_abrir_desde: Optional[float] = None
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
    # breakeven (opcional): apenas el precio llega a la ACTIVACION (sin esperar al cierre de la vela) el SL se mueve a la entrada
    # mas un NIVEL (0 = justo en la entrada; nunca menor que 0). Activacion: "r" (multiplos de R), "usd" (US$ fijos) o "pct_tp"
    # (% del camino al TP). Nivel: "r" o "usd". Una salida por ese SL es un resultado propio ("BE"): neutro para la tasa de acierto,
    # las rachas y las pausas (salvo be_pausa_perdida), pero su resultado en R y en dinero entra al balance y a la expectativa.
    be_activo: bool = False
    be_act_modo: str = "r"
    be_act_valor: float = 1.0
    be_nivel_modo: str = "r"
    be_nivel_valor: float = 0.0
    be_pausa_perdida: bool = False          # True: una salida en breakeven tambien dispara la pausa tras una perdida
    # cierre parcial (opcional): una sola vez por operacion, cuando el precio a favor llega al NIVEL (modo "r": multiplos de R;
    # "pct_tp": % del camino al TP) se cierra el parcial_pct % de la posicion. Con parcial_mover_sl el SL del resto pasa a la
    # entrada + parcial_sl_nivel (en R). Convive con el breakeven (el SL efectivo es el mas favorable). El resto termina en TP/SL/BE
    # (o por señal) y, si ya se cobro el parcial y sale por SL o BE, el resultado es "PARC_SL". El resultado en R es la suma ponderada.
    # lotes > 0: la parte cerrada se redondea al paso de volumen (lote_paso); si lo que queda es menor que lote_min se cierra todo.
    parcial_activo: bool = False
    parcial_nivel_modo: str = "r"
    parcial_nivel_valor: float = 1.5
    parcial_pct: float = 50.0
    parcial_mover_sl: bool = True
    parcial_sl_nivel: float = 0.05
    lotes: float = 0.0
    lote_paso: float = 0.01
    lote_min: float = 0.01

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

    def _validar_be(self) -> None:
        if not self.be_activo:
            return
        if self.be_act_modo not in BE_ACT_MODOS or self.be_nivel_modo not in BE_NIVEL_MODOS:
            raise ValueError("Breakeven: la activacion debe ser 'r', 'usd' o 'pct_tp' y el nivel 'r' o 'usd'.")
        if not self.be_act_valor > 0:
            raise ValueError("Breakeven: la activacion debe ser mayor que 0.")
        if self.be_nivel_valor < 0:
            raise ValueError("Breakeven: el nivel no puede ser menor que 0 (lo mejor que se puede hacer es salir sin perdida).")
        if self.be_act_modo == "pct_tp":
            if self.salida_modo == "senal":
                raise ValueError("Breakeven: la activacion en % del camino al TP necesita un TP fijo; con salida por señal no hay TP. "
                                 "Elegi multiplos de R o US$ fijos.")
            if not self.be_act_valor < 100:
                raise ValueError("Breakeven: la activacion debe ser menor que 100 % del camino al TP.")
        if "usd" in (self.be_act_modo, self.be_nivel_modo) and not self.usd_por_unidad > 0:
            raise ValueError("Breakeven en US$ fijos: necesita los lotes y el valor por unidad de precio (cargalos en «Lotaje y dinero»).")
        # con la distancia del SL conocida de antemano (SL fijo en precio) se puede comprobar el orden aca; si no, se revisa en cada operacion
        d = self.sl_valor if self.sl_modo == "precio" else None
        act, niv = be_en_r(self.be_act_modo, self.be_act_valor, d, self.rr, self.usd_por_unidad), \
            be_en_r(self.be_nivel_modo, self.be_nivel_valor, d, self.rr, self.usd_por_unidad)
        if act is not None and niv is not None and not niv < act:
            raise ValueError("Breakeven: el nivel al que se mueve el SL tiene que ser menor que la activacion; si no, el SL quedaria "
                             "mas alla del precio y la operacion se cerraria al instante.")
        if act is not None and self.salida_modo == "rr" and not act < self.rr:
            raise ValueError("Breakeven: la activacion tiene que ser menor que el TP (si el TP llega antes, el breakeven nunca actua).")

    def _validar_parcial(self) -> None:
        if not self.parcial_activo:
            return
        if self.parcial_nivel_modo not in ("r", "pct_tp"):
            raise ValueError("Cierre parcial: el nivel debe ser 'r' (multiplos de R) o 'pct_tp' (% del camino al TP).")
        if not self.parcial_nivel_valor > 0:
            raise ValueError("Cierre parcial: el nivel debe ser mayor que 0.")
        if not 0 < self.parcial_pct < 100:
            raise ValueError("Cierre parcial: el porcentaje que se cierra debe ser mayor que 0 y menor que 100.")
        if self.parcial_mover_sl and self.parcial_sl_nivel < 0:
            raise ValueError("Cierre parcial: el nivel del SL del resto no puede ser menor que 0.")
        if self.parcial_nivel_modo == "pct_tp":
            if self.salida_modo == "senal":
                raise ValueError("Cierre parcial: el nivel en % del camino al TP necesita un TP fijo; con salida por señal elegi multiplos de R.")
            if not self.parcial_nivel_valor < 100:
                raise ValueError("Cierre parcial: el nivel debe ser menor que 100 % del camino al TP.")
        niv = self.parcial_nivel_valor if self.parcial_nivel_modo == "r" else self.parcial_nivel_valor / 100.0 * self.rr
        if self.salida_modo == "rr" and not niv < self.rr:
            raise ValueError("Cierre parcial: el nivel tiene que ser menor que el TP (si el TP llega antes, el parcial nunca actua).")
        if self.parcial_mover_sl and not self.parcial_sl_nivel < niv:
            raise ValueError("Cierre parcial: el SL del resto tiene que quedar por debajo del nivel del parcial.")

    def validar(self) -> None:
        self._validar_parcial()
        if self.vwap_dist_min_atr < 0 or self.vwap_min_minutos < 0:
            raise ValueError("Los parametros del VWAP no pueden ser negativos.")
        if not 0 <= self.pullback_pct <= 100:
            raise ValueError("El porcentaje de pullback debe estar entre 0 y 100.")
        if self.pullback_ema not in ("corta", "larga"):
            raise ValueError("La EMA del pullback debe ser 'corta' o 'larga'.")
        if self.pullback_velas < 1:
            raise ValueError("La caducidad del pullback debe ser de al menos 1 vela.")
        for k in ("tm1", "tm2"):
            if getattr(self, k + "_tf") not in TF_MINUTOS or int(getattr(self, k + "_periodo")) < 2:
                raise ValueError("La tendencia mayor necesita una temporalidad M15, M30, H1, H4 o D1 y una SMA de al menos 2 periodos.")
        if self.vp_modo not in VP_MODOS or int(self.vp_dias) < 1 or not self.vp_escalon > 0:
            raise ValueError("Volume Profile: el modo debe ser 'poc', 'fuera' o 'dentro', los dias de perfil al menos 1 y el escalon mayor que 0.")
        if self.vp_activo and self.servidor_offset_horas is None:
            raise ValueError("El filtro Volume Profile necesita el desfase horario del servidor (servidor_offset_horas) para cortar el dia a medianoche CE(S)T.")
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
        self._validar_be()
        if self.direccion not in ("ambas", "largos", "cortos"):
            raise ValueError("Direccion invalida.")
        if self.spread not in ("vela", "mediana", "fijo", "ninguno"):
            raise ValueError("Modo de spread invalido.")
        if self.sesion_activo and self.servidor_offset_horas is None:
            raise ValueError("El filtro de sesion necesita el desfase horario del servidor "
                             "(servidor_offset_horas). Medilo con el mercado abierto.")
        if not self.finde_mantener and self.finde_no_abrir_desde is not None:
            if self.servidor_offset_horas is None:
                raise ValueError("Para no abrir operaciones el viernes desde una hora hace falta el desfase horario del servidor "
                                 "(servidor_offset_horas). Medilo con el mercado abierto.")
            if not (0.0 <= float(self.finde_no_abrir_desde) < 24.0):
                raise ValueError("La hora desde la que no se abren operaciones el viernes tiene que estar entre 00:00 y 23:59.")


TF_MINUTOS = {"M15": 15, "M30": 30, "H1": 60, "H4": 240, "D1": 1440}

BE_ACT_MODOS = ("r", "usd", "pct_tp")
BE_NIVEL_MODOS = ("r", "usd")


def be_en_r(modo: str, valor: float, d, rr: float, vu: float):
    """Distancia del breakeven medida en R (multiplos de la distancia del SL `d`), o None si no se puede saber sin conocer `d`."""
    if modo == "r":
        return float(valor)
    if modo == "pct_tp":
        return float(valor) / 100.0 * rr
    if d is None or not d > 0 or not vu > 0:
        return None
    return float(valor) / vu / d


def be_distancia(modo: str, valor: float, d: float, rr: float, vu: float) -> float:
    """Distancia de precio del breakeven para una operacion con SL a distancia d (precio)."""
    if modo == "r":
        return valor * d
    if modo == "pct_tp":
        return valor / 100.0 * rr * d
    return valor / vu

VP_MODOS = ("poc", "fuera", "dentro")
VP_AREA = 0.70                  # el area de valor reune el 70 % del volumen del perfil
VP_MIN_MINUTOS = 360            # un dia solo cuenta para el perfil si tiene al menos 6 horas de velas (descarta domingos y feriados casi vacios)

FILTROS_APAGADOS = dict(vp_activo=False, tm1_activo=False, tm2_activo=False, sma_activo=False, vwap_activo=False, adx_activo=False, rango_activo=False, atr_activo=False, sesion_activo=False, pullback_activo=False, be_activo=False, parcial_activo=False)


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
    tm_aviso: tuple = ()                    # avisos de los filtros de tendencia mayor y de Volume Profile (p. ej. historial corto)
    vp: Optional[tuple] = None              # (POC, VAH, VAL) de cada vela (NaN si todavia no hay perfil), solo con el filtro Volume Profile
    fs: Optional[np.ndarray] = None         # ultima vela de la semana de cada vela (n si no hay otro fin de semana adelante); solo si no se mantiene el finde
    bloq_vie: Optional[np.ndarray] = None   # True en las velas del viernes desde la hora en que ya no se abren operaciones (solo con ese campo)


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


def tendencia_mayor(df: pd.DataFrame, tf: str, periodo: int):
    """Para cada vela de `df`: (sube, baja, sin_dato). Usa la ultima vela de la temporalidad `tf` que YA CERRO al cierre de esa vela
    (sin mirar el futuro): sube = su cierre esta sobre su SMA(periodo), baja = debajo. Sin SMA todavia -> ninguna de las dos."""
    base = pd.Series(df.index).diff().median()
    minutos = TF_MINUTOS[tf]
    if pd.isna(base) or pd.Timedelta(minutes=minutos) <= base:
        raise ValueError(f"La tendencia mayor ({tf}) tiene que ser de una temporalidad mayor a la de las velas.")
    cl = df["Close"].resample(f"{minutos}min").last().dropna()
    sma = ind.sma(cl.to_numpy(float), int(periodo))
    fin = (cl.index + pd.Timedelta(minutes=minutos)).to_numpy()
    pos = np.searchsorted(fin, (df.index + base).to_numpy(), side="right") - 1
    ok = pos >= 0
    pos = np.where(ok, pos, 0)
    cv, sv = cl.to_numpy(float)[pos], sma[pos]
    hay = ok & np.isfinite(sv)
    return hay & (cv > sv), hay & (cv < sv), ~hay


def _perfil_dia(h: np.ndarray, l: np.ndarray, v: np.ndarray, esc: float):
    """Perfil de volumen de un dia: (k0, volumen por escalon). El escalon k cubre [k*esc, (k+1)*esc). Cada vela reparte su volumen entre
    los escalones que toca, en proporcion a cuanto de su rango (minimo a maximo) cae en cada uno; una vela sin rango va entera a su escalon."""
    k0, k1 = int(np.floor(l.min() / esc)), int(np.floor(h.max() / esc))
    bordes = np.arange(k0, k1 + 2) * esc
    ancho = np.maximum(h - l, 1e-9)
    acum = (np.clip((bordes[None, :] - l[:, None]) / ancho[:, None], 0.0, 1.0) * v[:, None]).sum(axis=0)
    return k0, np.maximum(np.diff(acum), 0.0)


def _area_valor(vol: np.ndarray):
    """(escalon del POC, escalon inferior, escalon superior del area de valor). POC = escalon de mayor volumen (el mas bajo si hay empate).
    El area parte del POC y suma de a UN escalon, siempre el vecino de mayor volumen (a igualdad, el de arriba), hasta reunir VP_AREA del total."""
    poc = int(np.argmax(vol))
    objetivo = VP_AREA * float(vol.sum())
    lo = hi = poc
    acum, n = float(vol[poc]), len(vol)
    while acum < objetivo:
        arriba = float(vol[hi + 1]) if hi + 1 < n else -1.0
        abajo = float(vol[lo - 1]) if lo - 1 >= 0 else -1.0
        if arriba < 0 and abajo < 0:
            break
        if arriba >= abajo:
            hi += 1
            acum += arriba
        else:
            lo -= 1
            acum += abajo
    return poc, lo, hi


def niveles_vp(df: pd.DataFrame, cfg: Config):
    """(POC, VAH, VAL) para cada vela: el perfil de volumen de los ultimos `vp_dias` dias completos anteriores al dia de la vela (dia CE(S)T).
    Los niveles son fijos todo el dia y solo usan dias ya cerrados (no mira el futuro). Un dia entra al perfil si tiene al menos
    VP_MIN_MINUTOS de velas; se cuentan dias con datos, asi que el fin de semana no cuenta. Sin N dias previos validos -> NaN.
    POC = centro de su escalon; VAL/VAH = borde inferior del escalon de abajo / borde superior del escalon de arriba del area de valor.
    Devuelve ademas True si no habia volumen de ticks y se uso la cantidad de velas."""
    n = len(df)
    h, l = df["High"].to_numpy(float), df["Low"].to_numpy(float)
    sin_vol = "Volume" not in df
    v = np.ones(n) if sin_vol else df["Volume"].to_numpy(float)
    esc, N = float(cfg.vp_escalon), int(cfg.vp_dias)
    base_min = pd.Series(df.index).diff().median() / pd.Timedelta(minutes=1)
    dia = claves_dia(df.index, cfg)
    cortes = np.flatnonzero(np.diff(dia)) + 1
    ini, fin = np.r_[0, cortes], np.r_[cortes, n]
    perfiles = []                                   # solo los dias validos, en orden
    poc, vah, val = (np.full(n, np.nan) for _ in range(3))
    for a, b in zip(ini, fin):
        previos = perfiles[-N:]
        if len(previos) >= N:
            k0 = min(p[0] for p in previos)
            k1 = max(p[0] + len(p[1]) for p in previos)
            vol = np.zeros(k1 - k0)
            for pk, pv in previos:
                vol[pk - k0: pk - k0 + len(pv)] += pv
            if vol.sum() > 0:
                kp, klo, khi = _area_valor(vol)
                poc[a:b] = (k0 + kp + 0.5) * esc
                val[a:b] = (k0 + klo) * esc
                vah[a:b] = (k0 + khi + 1) * esc
        if (b - a) * base_min >= VP_MIN_MINUTOS:
            perfiles.append(_perfil_dia(h[a:b], l[a:b], v[a:b], esc))
    return (poc, vah, val), sin_vol


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
    tm, tm_aviso = {}, []
    for k in ("tm1", "tm2"):
        if getattr(cfg, k + "_activo"):
            tf_, per_ = getattr(cfg, k + "_tf"), int(getattr(cfg, k + "_periodo"))
            sube_m, baja_m, sin_m = tendencia_mayor(df, tf_, per_)
            tm[k] = (sube_m, baja_m)
            if sin_m.mean() > 0.30:
                tm_aviso.append(f"Tendencia mayor {tf_}: la SMA {per_} no existe en el {100 * sin_m.mean():.0f}% de las velas (necesita {per_} velas de {tf_} "
                                "de historial). Esas señales se descartan: cargá un período más largo o usá una SMA más corta.")
    vp = None
    if cfg.vp_activo:
        vp, _sin_vol = niveles_vp(df, cfg)
        if _sin_vol:
            tm_aviso.append("Volume Profile: los datos no traen volumen de ticks; el perfil se armó con la cantidad de velas (tiempo en cada precio).")
        _sp = np.isnan(vp[0])
        if _sp.mean() > 0.30:
            tm_aviso.append(f"Volume Profile: el {100 * _sp.mean():.0f}% de las velas no tiene perfil todavía (necesita {int(cfg.vp_dias)} día(s) completo(s) "
                            "de historial previo). Esas señales se descartan: cargá un período más largo o usá menos días de perfil.")
    adx = ind.adx_wilder(h, l, c, cfg.adx_periodo)[0] if cfg.adx_activo else None
    er = ind.eficiencia(c, cfg.rango_ventana) if cfg.rango_activo else None
    atr_pct = atr / c * 100.0
    atr_med = pd.Series(atr).rolling(cfg.atr_rel_n).mean().to_numpy() if (cfg.atr_activo and cfg.atr_rel_n) else None
    ok_ses = None
    if cfg.sesion_activo:
        utc = ses.servidor_a_utc(df.index, cfg.servidor_offset_horas, cfg.servidor_dst_eeuu)
        ok_ses = ses.mascara_sesiones(utc, cfg.sesiones, cfg.horarios, cfg.sin_pausa, cfg.cortes)

    fs = bloq_vie = None
    if not cfg.finde_mantener:
        hueco = np.diff(df.index.values).astype("timedelta64[m]").astype(np.int64) > 30 * 60      # hueco de mas de 30 h = fin de semana / feriado largo
        pos = np.flatnonzero(hueco)                                                                # ultima vela antes de cada hueco
        k_ = np.searchsorted(pos, np.arange(n))
        fs = np.where(k_ < len(pos), pos[np.minimum(k_, max(len(pos) - 1, 0))] if len(pos) else n, n).astype(np.int64)
        if cfg.finde_no_abrir_desde is not None:
            utc_ = ses.servidor_a_utc(df.index, cfg.servidor_offset_horas, cfg.servidor_dst_eeuu)
            ny = pd.DatetimeIndex(utc_).tz_localize("UTC").tz_convert("America/New_York")
            hh = ny.hour.to_numpy() + ny.minute.to_numpy() / 60.0
            bloq_vie = (ny.weekday.to_numpy() == 4) & (hh >= float(cfg.finde_no_abrir_desde))

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

    def ok_vp(i, lado):
        pc, ah, al = vp[0][i], vp[1][i], vp[2][i]
        if np.isnan(pc):
            return False
        if cfg.vp_modo == "poc":
            return (c[i] - pc) * lado > 0
        if cfg.vp_modo == "fuera":
            return c[i] > ah if lado == 1 else c[i] < al
        return al <= c[i] <= ah

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
        if not cfg.pb_efectivo() and ((bloq_vie is not None and bloq_vie[i]) or (fs is not None and fs[i] == i)):
            motivo = "viernes"                                        # (con pullback se mira al ejecutar: se cancela la orden) / la ultima vela de la semana no abre
        elif cfg.sesion_activo and not cfg.pb_efectivo() and not ok_ses[i]:    # con pullback la sesion se mira al ejecutar
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
        elif "tm1" in tm and not (tm["tm1"][0][i] if lado == 1 else tm["tm1"][1][i]):
            motivo = "tm1"
        elif "tm2" in tm and not (tm["tm2"][0][i] if lado == 1 else tm["tm2"][1][i]):
            motivo = "tm2"
        elif cfg.vp_activo and not ok_vp(i, lado):
            motivo = "vp"
        cruces.append((i, lado, motivo))

    sp = _spread(df, cfg)
    raw = df["Spread"].to_numpy(float) if "Spread" in df else np.zeros(n)
    return Preparado(h, l, c, sp, atr, dist, df.index, cruces, 100 * float((raw == 0).mean()),
                     ema_c, ema_l, sube, baja, ok_ses if (cfg.pb_efectivo() and cfg.sesion_activo) else None,
                     claves_dia(df.index, cfg) if cfg.reglas_activas else None, diff,
                     sl_ref, sl_off, tuple(tm_aviso), vp, fs, bloq_vie)


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
            "be_pausa_perdida": bool(cfg.be_activo and cfg.be_pausa_perdida),
            "retiro_usd": float(cfg.capital) * float(cfg.retiro_pct) / 100.0 if (cfg.retiro_activo and cfg.retiro_pct > 0) else None}


def be_de(cfg: Config):
    """Parametros del breakeven para simular(), o None si no se usa."""
    if not cfg.be_activo:
        return None
    return {"act_modo": cfg.be_act_modo, "act_valor": float(cfg.be_act_valor), "nivel_modo": cfg.be_nivel_modo,
            "nivel_valor": float(cfg.be_nivel_valor), "vu": float(cfg.usd_por_unidad)}


def fraccion_parcial(cfg: Config) -> float:
    """Fraccion REAL de la posicion que cierra el parcial. Con lotes conocidos se redondea al paso de volumen (al mas cercano);
    si no se llega a un lote minimo no hay parcial (0) y si lo que queda es menor que el minimo se cierra todo (1)."""
    f = cfg.parcial_pct / 100.0
    if not cfg.lotes > 0:
        return f
    paso = cfg.lote_paso if cfg.lote_paso > 0 else 0.01
    cerrado = int(np.floor(cfg.lotes * f / paso + 0.5 + 1e-9)) * paso
    if cerrado < max(cfg.lote_min, paso) - 1e-9:
        return 0.0
    if cfg.lotes - cerrado < cfg.lote_min - 1e-9:
        return 1.0
    return float(cerrado / cfg.lotes)


def parcial_de(cfg: Config):
    """Parametros del cierre parcial para simular(), o None si no se usa (o si el lote no alcanza para partirlo)."""
    if not cfg.parcial_activo:
        return None
    f = fraccion_parcial(cfg)
    if not f > 0:
        return None
    return {"modo": cfg.parcial_nivel_modo, "valor": float(cfg.parcial_nivel_valor), "f": float(f),
            "sl_nivel": float(cfg.parcial_sl_nivel) if cfg.parcial_mover_sl else None}


def simular(P: Preparado, señales, rr: float, costo_extra: float = 0.0, pb=None, salida: str = "rr", cuenta=None, be=None, parcial=None):
    """señales: lista de (indice, lado). Devuelve (DataFrame de operaciones, ignoradas).

    pb=None: entrada al cierre de la vela de la señal. pb={"pct","ema","velas"}: la señal deja una orden pendiente.
    El resultado trae en .attrs["pb"] cuantas ordenes se llenaron, caducaron o se cancelaron por cruce contrario.
    salida="senal": no hay TP. Se sale al CIERRE de la primera vela (posterior a la de entrada) que cierra del otro lado de
    la media (diff de signo contrario al del lado); el SL sigue vigente y se revisa antes en cada vela. La tabla trae
    "motivo" (tp / sl / senal / limite): una salida por señal se rotula TP si gana y SL si pierde, con su R real.
    cuenta (ver cuenta_de): simula la cuenta en orden cronologico con limites de perdida diaria y total, proteccion del SL,
    riesgo maximo por operacion y pausa tras una perdida; el resumen queda en .attrs["cuenta"]. Si el equity llega a un
    limite con una operacion abierta, se cierra en ese nivel (motivo "limite").
    be (ver be_de): breakeven. Apenas el precio llega a la activacion (dentro de la vela: no se espera al cierre) el SL pasa a la
    entrada mas el nivel. Si en esa misma vela toca el SL original, cuenta SL; si toca la activacion y vuelve al nivel nuevo
    (o el nivel nuevo y el TP en una misma vela), cuenta breakeven (peor caso, vela ambigua). Una salida por ese SL es res "BE";
    la columna "be" marca las operaciones que llegaron a activarlo.
    parcial (ver parcial_de): cierre parcial. Una sola vez por operacion, cuando el precio a favor llega al nivel (mismo criterio de
    spread que el TP). Si en esa misma vela toca el SL, primero el SL (peor caso); si toca el nivel y el TP, se ejecutan los dos. Si
    mueve el SL del resto y en esa vela el precio vuelve a ese nivel, el resto sale ahi (peor caso). Columnas: parcial (0/1),
    R_parcial y R_resto (R = R_parcial + R_resto); res "PARC_SL" = parcial cobrado y el resto salio por SL o breakeven.
    En la tabla, "i" es la vela de ENTRADA real y "señal" la vela del cruce (iguales sin pullback)."""
    h, l, c, sp, dist = P.h, P.l, P.c, P.sp, P.dist
    n = len(c)
    filas, libre, ignoradas, sl_invalido, be_invalidas = [], 0, 0, 0, 0
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
              "balance_final": cap, "balance_min": cap, "balance_max": cap, "retiros": [], "retirado": 0.0, "prot_desde": None, "prot_n": 0}
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

    def cerrar(r, d, j_out, lado, entrada, es_be=False):
        """Aplica el resultado de la operacion a la cuenta y revisa los limites."""
        pnl = r * d * vu - comm
        rodar_dia(j_out)                 # si cruzo la medianoche, el dia nuevo parte del balance previo a este cierre
        S["bal"] += pnl
        S["pico"] = max(S["pico"], S["bal"])
        cs["peor_dia_usd"] = min(cs["peor_dia_usd"], S["bal"] - S["bal_dia"])
        cs["balance_min"] = min(cs["balance_min"], S["bal"])
        cs["balance_max"] = S["pico"]                    # si se quema, es lo maximo que llego a ganar antes de quemarse
        if es_be:                        # breakeven: ni perdida ni ganancia para las pausas (salvo que se pida lo contrario)
            if ct.get("be_pausa_perdida"):
                S["perd_j"][lado] = j_out
        elif pnl < 0:
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
            bal_antes = float(S["bal"])
            S["bal"] = cap
            S["bal_dia"] -= w
            cs["retiros"].append({"j": int(j_out), "monto": float(w), "bal_antes": bal_antes,
                                  "piso": float(pt_) if np.isfinite(pt_) else None})
            cs["retirado"] += float(w)

    ex = {"parc": False, "sl_sal": None}               # datos extra de la ultima corrida de recorrer(): parcial cobrado y precio del SL de salida

    def recorrer(desde, lado, sl, tp, entrada=None, lim=None, bepar=None, tope=None, parpar=None):
        """Devuelve (resultado, ambigua, vela de salida, breakeven activado). bepar = (distancia de activacion, distancia del nivel).
        parpar = (distancia del parcial, fraccion que se cierra, distancia del SL del resto o None). Resultado "PARC_SL": parcial cobrado
        y el resto salio por SL o breakeven; "PARC_TOT": el parcial cerro toda la posicion. ex["parc"] dice si se cobro el parcial y
        ex["sl_sal"] a que precio salio el SL.
        tope: ultima vela de la semana (sin mantener el fin de semana): si hasta ahi no salio, se cierra ahi (resultado "FIN")."""
        armada, sl_cur, parc = False, sl, False
        ex["parc"], ex["sl_sal"] = False, sl
        if bepar is not None:
            act_px, be_px = entrada + lado * bepar[0], entrada + lado * bepar[1]
        ps_px = None
        if parpar is not None:
            par_px = entrada + lado * parpar[0]
            if parpar[2] is not None:
                ps_px = entrada + lado * parpar[2]
        for j in range(desde, (n if tope is None else tope + 1)):
            if lim is not None and not (armada or (parc and ps_px is not None)):   # el equity toca un limite de cuenta antes que el SL
                adverso = (entrada - l[j]) if lado == 1 else (h[j] + sp[j] - entrada)
                if adverso >= lim:
                    return "LIM", False, j, False
            if lado == 1:
                hit_sl = l[j] <= sl_cur
                hit_tp = (not por_senal) and h[j] >= tp
                trig = bepar is not None and not armada and h[j] >= act_px
                trigp = parpar is not None and not parc and h[j] >= par_px
            else:
                hit_sl = h[j] + sp[j] >= sl_cur
                hit_tp = (not por_senal) and l[j] + sp[j] <= tp
                trig = bepar is not None and not armada and l[j] + sp[j] <= act_px
                trigp = parpar is not None and not parc and l[j] + sp[j] <= par_px
            if hit_sl:                                   # SL vigente (si en la misma vela toca la activacion o el parcial, se asume el peor caso)
                ex["sl_sal"] = sl_cur
                if parc:
                    return "PARC_SL", bool(hit_tp), j, armada
                return ("BE" if armada else "SL"), bool(hit_tp), j, armada
            nuevo = sl_cur
            if trig:                                     # activacion dentro de la vela: no se espera al cierre
                armada = True
                nuevo = be_px
            if trigp:                                    # parcial dentro de la vela
                parc, ex["parc"] = True, True
                if parpar[1] >= 1.0:
                    return "PARC_TOT", False, j, armada
                if ps_px is not None:                    # el SL efectivo es el mas favorable de los dos
                    nuevo = max(nuevo, ps_px) if lado == 1 else min(nuevo, ps_px)
            if nuevo != sl_cur:
                sl_cur = nuevo
                vuelve = (l[j] <= sl_cur) if lado == 1 else (h[j] + sp[j] >= sl_cur)
                if vuelve:                               # no se sabe el orden dentro de la vela: peor caso
                    ex["sl_sal"] = sl_cur
                    return ("PARC_SL" if parc else "BE"), True, j, armada
            if hit_tp:
                return "TP", False, j, armada
            if por_senal and ((P.diff[j] < 0) if lado == 1 else (P.diff[j] > 0)):
                return "SEN", False, j, armada
        if tope is not None:
            return "FIN", False, tope, armada
        return "ABIERTA", False, n - 1, armada

    def tope_de(k):
        """Ultima vela de la semana de la vela k, o None si se mantienen las posiciones el fin de semana (o no hay otro fin de semana)."""
        if P.fs is None or P.fs[k] >= n:
            return None
        return int(P.fs[k])

    def bepar_de(d):
        """(distancia de activacion, distancia del nivel) en precio para una operacion con SL a distancia d, o None sin breakeven."""
        nonlocal be_invalidas
        if be is None:
            return None
        a = be_distancia(be["act_modo"], be["act_valor"], d, rr, be["vu"])
        b = be_distancia(be["nivel_modo"], be["nivel_valor"], d, rr, be["vu"])
        if not (a > 0 and 0 <= b < a):
            be_invalidas += 1
            return None
        return (a, b)

    def parpar_de(d):
        """(distancia del parcial, fraccion cerrada, distancia del SL del resto o None) para un SL a distancia d, o None sin parcial."""
        if parcial is None:
            return None
        a = be_distancia(parcial["modo"], parcial["valor"], d, rr, 1.0)
        b = None if parcial["sl_nivel"] is None else parcial["sl_nivel"] * d
        if not a > 0 or (b is not None and not b < a):
            return None
        return (a, parcial["f"], b)

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
                    if motivo_p == "saltadas_proteccion":       # sin margen: desde cuando, y cuantas señales desde la ultima operacion abierta
                        cs["prot_n"] += 1
                        if cs["prot_desde"] is None:
                            cs["prot_desde"] = i
                    continue
            sl, tp = entrada - lado * d, (np.nan if por_senal else entrada + lado * d * rr)
            bepar = bepar_de(d)
            parpar = parpar_de(d)
            res, amb, j_out, armada = recorrer(i + 1, lado, sl, tp, entrada, lim, bepar, tope_de(i), parpar)
        else:
            st["ordenes"] += 1
            ema = P.ema_c if pb["ema"] == "corta" else P.ema_l
            frac = pb["pct"] / 100.0
            ext = h[i] if lado == 1 else l[i]           # extremo desde el cruce, hasta la vela anterior
            contra = P.baja if lado == 1 else P.sube
            fin = min(i + pb["velas"], n - 1)
            if P.fs is not None and P.fs[i] < n:        # sin mantener el fin de semana: la orden se cancela al cierre de la semana
                fin = min(fin, int(P.fs[i]) - 1)            # y no se llena en la ultima vela de la semana (ahi ya no se abre)
            k, px, fin_esp, motivo = None, None, fin, "caducadas"
            for j in range(i + 1, fin + 1):
                if P.bloq_vie is not None and P.bloq_vie[j]:     # viernes desde la hora limite: ya no se abren operaciones, se cancela la orden
                    fin_esp = j - 1
                    break
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
                    if motivo_p == "saltadas_proteccion":       # sin margen: desde cuando, y cuantas señales desde la ultima operacion abierta
                        cs["prot_n"] += 1
                        if cs["prot_desde"] is None:
                            cs["prot_desde"] = i
                    libre = k + 1
                    continue
            st["llenadas"] += 1
            sl, tp = entrada - lado * d, (np.nan if por_senal else entrada + lado * d * rr)
            # en la vela de entrada no se sabe que paso primero: si toca el SL, cuenta como SL; el TP recien desde la siguiente
            toca_sl = l[k] <= sl if lado == 1 else h[k] + sp[k] >= sl
            bepar = bepar_de(d)
            parpar = parpar_de(d)
            armada = False
            ex["parc"] = False
            if lim is not None and ((entrada - l[k]) if lado == 1 else (h[k] + sp[k] - entrada)) >= lim:
                res, amb, j_out = "LIM", True, k
            elif toca_sl:
                res, amb, j_out = "SL", True, k
            else:
                res, amb, j_out, armada = recorrer(k + 1, lado, sl, tp, entrada, lim, bepar, tope_de(k), parpar)
        parc = parpar is not None and ex["parc"]
        motivo_sal = {"TP": "tp", "SL": "sl", "SEN": "senal", "LIM": "limite", "BE": "be", "FIN": "finde",
                      "PARC_SL": "parc_sl", "PARC_TOT": "parcial"}.get(res, "")
        if res in ("SEN", "FIN"):                       # sale al cierre: el largo vende al bid, el corto compra al ask
            salida_px = c[j_out] if lado == 1 else c[j_out] + sp[j_out]
            r = lado * (salida_px - entrada) / d
            res = "TP" if r > 0 else "SL"
        elif res == "LIM":                              # el bot cierra todo cuando el equity toca el limite
            r = -lim / d
            res = "SL"
            cs["forzadas"] += 1
        elif res == "BE":                               # sale en el nivel de breakeven: gana (o pierde, con costo extra) ese nivel
            r = bepar[1] / d
        elif res == "PARC_SL":                          # el resto sale en su SL (el de la entrada + nivel, o el original)
            r = lado * (ex["sl_sal"] - entrada) / d
        elif res == "PARC_TOT":                         # el parcial cerro toda la posicion
            r, res = 0.0, "TP"
        else:
            r = rr if res == "TP" else (-1.0 if res == "SL" else 0.0)
        r_par = 0.0
        if parc:                                        # suma ponderada: parte cerrada en el nivel + resto
            f = parpar[1]
            r_par = f * parpar[0] / d
            r_res = (1.0 - f) * r if f < 1.0 else 0.0
            r = r_par + r_res
        else:
            r_res = r
        if res != "ABIERTA" and costo_extra:
            r -= costo_extra / d
            r_res -= costo_extra / d
        if ct:
            cs["prot_desde"], cs["prot_n"] = None, 0          # se abrio una operacion: la cuenta tiene margen
        filas.append({"i": k, "señal": i, "lado": lado, "entrada": entrada, "sl": sl, "tp": tp, "dist": d,
                      "res": res, "amb": amb, "salida": j_out, "R": r, "motivo": motivo_sal, "be": int(armada),
                      "parcial": int(parc), "R_parcial": r_par, "R_resto": r_res})
        if res == "ABIERTA":
            break
        libre = j_out + 1
        if ct:
            cerrar(r, d, j_out, lado, entrada, res == "BE")
    cols = ["i", "señal", "lado", "entrada", "sl", "tp", "dist", "res", "amb", "salida", "R", "motivo", "be",
            "parcial", "R_parcial", "R_resto"]
    out = pd.DataFrame(filas, columns=cols)
    out.attrs["pb"] = st
    out.attrs["sl_invalido"] = sl_invalido            # señales sin operar porque el SL anclado a la media quedaba al reves
    out.attrs["be_invalidas"] = be_invalidas          # operaciones donde el nivel del breakeven no quedaba por debajo de la activacion
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
    tr, ign = simular(P, señales, cfg.rr, cfg.costo_extra, pb, cfg.salida_modo, cuenta_de(P, cfg), be_de(cfg), parcial_de(cfg))
    return Resultado(tr, descartes, len(en_rango), len(señales), ign, dict(tr.attrs.get("pb", {})) if pb else {},
                     dict(tr.attrs.get("cuenta", {})))
