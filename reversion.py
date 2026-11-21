"""Estrategia de reversion a la media (se combina con la de tendencia; no modifica nada de la EMA).

Variante A, extremos de un rango: una vela cierra fuera de la banda de Bollinger y la siguiente cierra de vuelta adentro, con ADX bajo.
Variante B, ruptura falsa del maximo / minimo de ayer: el precio supera el maximo (o minimo) del dia anterior y dentro de las K velas
siguientes vuelve a cerrar adentro. En las dos se opera en contra de la ruptura y se entra al cierre de la vela de confirmacion.

Reutiliza el motor (engine.simular) con TP y lote por señal: el riesgo es fijo en US$, asi que el lote cambia con la distancia del SL.
Los datos, el spread, las noticias, el fin de semana y las reglas de cuenta son los mismos del analisis (Config). El cierre por tiempo,
el breakeven y el horario de sesion son propios (ConfigRev).
"""
from dataclasses import dataclass, field, replace
from typing import Optional

import numpy as np
import pandas as pd

import engine as eng
import indicators as ind
import metrics as met
import sessions as ses

VARIANTES = ("A", "B")


@dataclass
class ConfigRev:
    activo: bool = False
    variante: str = "A"                 # "A" extremos de un rango (Bollinger + ADX bajo) | "B" ruptura falsa del maximo / minimo de ayer
    bb_n: int = 20                      # A: media de Bollinger (velas)
    bb_k: float = 2.0                   # A: desvios
    adx_periodo: int = 14
    adx_max: float = 20.0               # A: obligatorio (solo se opera con ADX menor a esto). B: solo si adx_activo_b
    adx_activo_b: bool = False
    b_velas: int = 6                    # B: velas (desde la que rompe, incluida) para volver a cerrar adentro
    sl_modo: str = "atr"                # "atr": mas alla del extremo + sl_atr_x ATR | "precio": distancia fija (unidades de precio)
    sl_atr_x: float = 0.5
    sl_precio: float = 3.0
    atr_periodo: int = 14
    tp_modo: str = "media"              # "media": A en la media de Bollinger, B en el punto medio del rango de ayer | "rr": RR fijo
    rr: float = 1.0
    riesgo_usd: float = 50.0            # riesgo fijo por operacion (US$): lote = riesgo / (distancia del SL x US$ por unidad por lote)
    # horario propio (igual que el filtro de sesion de la EMA)
    sesion_activo: bool = False
    sesiones: tuple = ("Tokio", "Londres", "Nueva York")
    horarios: Optional[dict] = None
    cortes: Optional[dict] = None
    sin_pausa: tuple = ()
    # gestion propia
    tstop_activo: bool = False
    tstop_velas: int = 12
    tstop_r: float = -0.25
    be_activo: bool = False
    be_act_modo: str = "r"
    be_act_valor: float = 0.8
    be_nivel_modo: str = "r"
    be_nivel_valor: float = 0.0
    # ajuste y verificacion por fechas (ISO "AAAA-MM-DD"); sin fechas el informe usa solo el tramo "Todo"
    val_activa: bool = False
    ajuste_desde: Optional[str] = None
    ajuste_hasta: Optional[str] = None
    verif_desde: Optional[str] = None
    verif_hasta: Optional[str] = None
    # cartera (fase 2)
    prioridad: str = "primero"          # "primero": gana el primero en abrir | "ema": la EMA manda
    magic: int = 2

    def validar(self, cfg: "eng.Config") -> None:
        if not self.activo:
            return
        if self.variante not in VARIANTES:
            raise ValueError("La variante de reversión tiene que ser A o B.")
        if self.bb_n < 2 or self.bb_k <= 0:
            raise ValueError("Bollinger: la media tiene que ser de 2 velas o más y los desvíos mayores a 0.")
        if self.adx_periodo < 2 or self.adx_max <= 0:
            raise ValueError("ADX: el período tiene que ser de 2 o más y el máximo mayor a 0.")
        if self.b_velas < 0:
            raise ValueError("Las velas para volver a cerrar adentro no pueden ser negativas.")
        if self.sl_modo not in ("atr", "precio"):
            raise ValueError("El SL de la reversión es «más allá del extremo + ATR» o una distancia fija.")
        if self.sl_modo == "atr" and (self.sl_atr_x < 0 or self.atr_periodo < 2):
            raise ValueError("SL de la reversión: el ATR tiene que ser de 2 velas o más y el múltiplo no puede ser negativo.")
        if self.sl_modo == "precio" and self.sl_precio <= 0:
            raise ValueError("SL de la reversión: la distancia fija tiene que ser mayor a 0.")
        if self.tp_modo not in ("media", "rr") or (self.tp_modo == "rr" and self.rr <= 0):
            raise ValueError("TP de la reversión: elegí la media (o el punto medio de ayer) o un RR fijo mayor a 0.")
        if self.riesgo_usd <= 0:
            raise ValueError("El riesgo por operación de la reversión tiene que ser mayor a 0.")
        if not (cfg.lotes > 0 and cfg.usd_por_unidad > 0):
            raise ValueError("La reversión calcula el lote con un riesgo fijo en US$: cargá el lote y el valor por unidad de precio en «Lotaje y dinero».")
        if self.sesion_activo and cfg.servidor_offset_horas is None:
            raise ValueError("El horario propio de la reversión necesita el desfase horario del servidor.")
        if self.tstop_activo and (self.tstop_velas < 1 or not -50 <= self.tstop_r <= 50):
            raise ValueError("Cierre por tiempo de la reversión: velas ≥ 1 y R entre -50 y 50.")
        if self.prioridad not in ("primero", "ema"):
            raise ValueError("La prioridad de la cartera es «el primero en abrir» o «la EMA manda».")
        if self.val_activa:
            for k in ("ajuste_desde", "ajuste_hasta", "verif_desde", "verif_hasta"):
                if not getattr(self, k):
                    raise ValueError("Ajuste y verificación: completá las cuatro fechas.")
            a0, a1, v0, v1 = (pd.Timestamp(getattr(self, k)) for k in ("ajuste_desde", "ajuste_hasta", "verif_desde", "verif_hasta"))
            if not (a0 < a1 and v0 < v1):
                raise ValueError("Ajuste y verificación: cada tramo tiene que terminar después de empezar.")
            if v0 <= a1:
                raise ValueError("Ajuste y verificación: la verificación tiene que empezar después de que termina el ajuste.")


def cfg_gestion(cfg: "eng.Config", rv: ConfigRev) -> "eng.Config":
    """Config con la gestion de la reversion (cierre por tiempo y breakeven propios; sin parcial, reentrada ni pullback) para be_de / tstop_de /
    cuenta_de. Lo compartido (cuenta, noticias, fin de semana, spread) queda como en cfg."""
    return replace(cfg, be_activo=rv.be_activo, be_act_modo=rv.be_act_modo, be_act_valor=rv.be_act_valor, be_nivel_modo=rv.be_nivel_modo,
                   be_nivel_valor=rv.be_nivel_valor, tstop_activo=rv.tstop_activo, tstop_velas=rv.tstop_velas, tstop_r=rv.tstop_r,
                   parcial_activo=False, reentrada_activa=False, pullback_activo=False, salida_modo="rr", rr=max(rv.rr, 0.01))


# ---------------------------------------------------------------- señales
def bollinger(c: np.ndarray, n: int, k: float):
    """(media, banda superior, banda inferior) con desvio poblacional."""
    s = pd.Series(c)
    ma = s.rolling(n).mean().to_numpy()
    sd = s.rolling(n).std(ddof=0).to_numpy()
    return ma, ma + k * sd, ma - k * sd


def senales_a(h, l, c, ma, up, lo):
    """[(vela de confirmacion j, lado, extremo de las dos velas, objetivo = media)]. Venta: la vela j-1 cierra sobre la banda superior y la j
    cierra de vuelta adentro (bajo la banda). Compra: al reves."""
    out = []
    with np.errstate(invalid="ignore"):
        sell = (c[:-1] > up[:-1]) & (c[1:] < up[1:])
        buy = (c[:-1] < lo[:-1]) & (c[1:] > lo[1:])
    for j in np.flatnonzero(sell | buy) + 1:
        if sell[j - 1]:
            out.append((int(j), -1, float(max(h[j - 1], h[j])), float(ma[j])))
        if buy[j - 1]:
            out.append((int(j), 1, float(min(l[j - 1], l[j])), float(ma[j])))
    return out


def senales_b(index, h, l, c, k: int):
    """Ruptura falsa del maximo / minimo del dia anterior (dia = fecha del servidor; ayer = el ultimo dia con datos). La primera vela del dia
    que supera el maximo de ayer y, dentro de las k velas siguientes (la que rompe incluida), el primer cierre de vuelta adentro: venta. Igual
    con el minimo: compra. Una señal por lado por dia. Devuelve [(j, lado, nuevo extremo, punto medio del rango de ayer)]."""
    dias = index.normalize().to_numpy()
    cambia = np.flatnonzero(np.r_[True, dias[1:] != dias[:-1]])
    lim = np.r_[cambia, len(c)]
    out = []
    for d in range(1, len(cambia)):
        a0, a1 = lim[d - 1], lim[d]
        s, e = lim[d], lim[d + 1]
        pdh, pdl = float(h[a0:a1].max()), float(l[a0:a1].min())
        mid = (pdh + pdl) / 2.0
        hh, ll, cc = h[s:e], l[s:e], c[s:e]
        for lado, rompe, dentro, ext in ((-1, hh > pdh, cc <= pdh, np.maximum.accumulate(hh)),
                                         (1, ll < pdl, cc >= pdl, np.minimum.accumulate(ll))):
            b = np.flatnonzero(rompe)
            if not len(b):
                continue
            b = int(b[0])
            fin = min(b + k, e - s - 1)
            t = np.flatnonzero(dentro[b:fin + 1])
            if not len(t):
                continue
            t = b + int(t[0])
            ex = float(hh[b:t + 1].max()) if lado == -1 else float(ll[b:t + 1].min())
            out.append((s + t, lado, ex, mid))
    out.sort(key=lambda x: (x[0], -x[1]))
    return out


# ---------------------------------------------------------------- preparar / ejecutar
@dataclass
class PrepRev:
    P: "eng.Preparado"                   # arrays comunes (spread, noticias, dia, finde) con dist / cruces de la reversion
    tp_dist: np.ndarray                  # por vela de confirmacion: distancia del TP desde el precio de entrada
    vu_sig: np.ndarray                   # por vela: US$ por unidad de precio de esa operacion (lote x US$ por unidad por lote)
    lotes: np.ndarray                    # por vela: lote de esa operacion
    senales_crudas: int = 0
    avisos: list = field(default_factory=list)


def preparar_rev(df: pd.DataFrame, cfg: "eng.Config", rv: ConfigRev) -> PrepRev:
    rv.validar(cfg)
    n = len(df)
    neutro = replace(cfg, **{k: v for k, v in eng.FILTROS_APAGADOS.items() if k != "noticias_activo"}, sl_modo="precio", sl_valor=1.0,
                     salida_modo="rr", direccion="ambas")
    P0 = eng.preparar(df, neutro)
    h, l, c, sp = P0.h, P0.l, P0.c, P0.sp
    upl = float(cfg.usd_por_unidad) / float(cfg.lotes)               # US$ por 1,00 de precio con 1 lote (tamaño del contrato)
    atr = ind.atr_wilder(h, l, c, rv.atr_periodo)
    adx = ind.adx_wilder(h, l, c, rv.adx_periodo)[0]
    warm = max(rv.bb_n if rv.variante == "A" else 2, 2 * rv.adx_periodo + 1, rv.atr_periodo + 1) + 1
    if rv.variante == "A":
        ma, up, lo = bollinger(c, rv.bb_n, rv.bb_k)
        crudas = senales_a(h, l, c, ma, up, lo)
    else:
        crudas = senales_b(df.index, h, l, c, rv.b_velas)
    ok_ses = None
    if rv.sesion_activo:
        utc = ses.servidor_a_utc(df.index, cfg.servidor_offset_horas, cfg.servidor_dst_eeuu)
        ok_ses = ses.mascara_sesiones(utc, rv.sesiones, rv.horarios, rv.sin_pausa, rv.cortes)
    usa_adx = rv.variante == "A" or rv.adx_activo_b
    dist, tp_dist, vu_sig, lotes = np.zeros(n), np.zeros(n), np.zeros(n), np.zeros(n)
    cruces, usados = [], set()
    for j, lado, ext, objetivo in crudas:
        if j < warm or j in usados:
            continue
        motivo = None
        if P0.bloq_vie is not None and P0.bloq_vie[j]:
            motivo = "viernes"
        elif ok_ses is not None and not ok_ses[j]:
            motivo = "sesion"
        elif usa_adx and not (adx[j] < rv.adx_max):
            motivo = "adx"
        if motivo is None:
            entrada = c[j] + sp[j] if lado == 1 else c[j]
            if rv.sl_modo == "atr":
                d = lado * (entrada - (ext - lado * rv.sl_atr_x * atr[j]))
            else:
                d = rv.sl_precio
            if not d > 0:
                motivo = "sl"
            else:
                td = lado * (objetivo - entrada) if rv.tp_modo == "media" else rv.rr * d
                if not td > 0:
                    motivo = "tp"
                else:
                    lt = np.floor(rv.riesgo_usd / (d * upl) / cfg.lote_paso + 1e-9) * cfg.lote_paso
                    if lt < cfg.lote_min - 1e-12:
                        motivo = "lote"
                    elif P0.noti is not None and P0.noti["ent"][j]:
                        motivo = "noticias"                                 # va ultimo: solo cuenta lo que habria entrado
                    else:
                        dist[j], tp_dist[j], lotes[j], vu_sig[j] = d, td, lt, lt * upl
        usados.add(j)
        cruces.append((j, lado, motivo))
    P = replace(P0, dist=dist, cruces=cruces)
    avisos = list(P0.tm_aviso)
    if cfg.spread == "vela" and P0.spread_ceros_pct > 5:
        avisos.append(f"{P0.spread_ceros_pct:.1f}% de las velas tiene spread 0 (historial incompleto): el costo está subestimado. Probar spread «mediana».")
    return PrepRev(P, tp_dist, vu_sig, lotes, len(crudas), avisos)


def ejecutar_rev(PR: PrepRev, cfg: "eng.Config", rv: ConfigRev, lo: int = 0, hi: Optional[int] = None) -> "eng.Resultado":
    P = PR.P
    hi = len(P.c) if hi is None else hi
    en_rango = [x for x in P.cruces if lo <= x[0] < hi]
    descartes = {}
    for _, _, m in en_rango:
        if m:
            descartes[m] = descartes.get(m, 0) + 1
    señales = [(i, lado) for i, lado, m in en_rango if m is None]
    cg = cfg_gestion(cfg, rv)
    tr, ign = eng.simular(P, señales, cg.rr, cfg.costo_extra, None, "rr", eng.cuenta_de(P, cg), eng.be_de(cg), None, None, eng.tstop_de(cg),
                          eng.noti_de(cfg), tp_dist=PR.tp_dist, vu_sig=PR.vu_sig)
    if len(tr):
        tr["lotes"] = PR.lotes[tr["i"].to_numpy()]
    else:
        tr["lotes"] = pd.Series(dtype=float)
    return eng.Resultado(tr, descartes, len(en_rango), len(señales), ign, {}, dict(tr.attrs.get("cuenta", {})))


def rr_equilibrio(tr: pd.DataFrame) -> float:
    """R:R medio observado (ganancia media / perdida media) para el WR de equilibrio, ya que el TP cambia con cada señal."""
    if not len(tr):
        return 1.0
    g, p = tr.loc[tr["res"] == "TP", "R"], tr.loc[tr["res"] == "SL", "R"]
    if len(g) and len(p) and g.mean() > 0 and p.mean() < 0:
        return float(g.mean() / -p.mean())
    return 1.0


def resumen_rev(tr: pd.DataFrame) -> dict:
    return met.resumen(tr, rr_equilibrio(tr))


def tramos(P: "eng.Preparado", rv: ConfigRev, oos_pct: float = 0.3):
    """[(nombre, lo, hi)]: Todo, y Ajuste / Verificacion por fechas (o 70 / 30 si no se pidieron fechas)."""
    n = len(P.c)
    if rv.val_activa:
        ix = P.indice
        f = lambda t: int(ix.searchsorted(pd.Timestamp(t)))
        return [("Todo", 0, n), ("Ajuste", f(rv.ajuste_desde), f(pd.Timestamp(rv.ajuste_hasta) + pd.Timedelta(days=1))),
                ("Verificación", f(rv.verif_desde), min(f(pd.Timestamp(rv.verif_hasta) + pd.Timedelta(days=1)), n))]
    corte = int(n * (1 - oos_pct))
    return [("Todo", 0, n), ("Ajuste", 0, corte), ("Verificación", corte, n)]


def evaluar_rev(df: pd.DataFrame, cfg: "eng.Config", rv: ConfigRev, oos_pct: float = 0.3, contador=None) -> dict:
    """Corre la reversion sola: tramos Todo / Ajuste / Verificacion, resultado por año y por mes, descartes."""
    prueba = contador.sumar() if contador else None
    PR = preparar_rev(df, cfg, rv)
    P = PR.P
    filas, res_todo = [], None
    for nombre, lo, hi in tramos(P, rv, oos_pct):
        r = ejecutar_rev(PR, cfg, rv, lo, hi)
        if nombre == "Todo":
            res_todo = r
        s = resumen_rev(r.trades)
        s["cruces"], s["tomados"], s["ignoradas"], s["descartes"] = r.cruces, r.tomados, r.ignoradas, r.descartes
        filas.append({"tramo": nombre, **s})
    tabla = pd.DataFrame(filas).set_index("tramo")
    tr = res_todo.trades.copy()
    por_anio = por_mes = pd.DataFrame()
    if len(tr):
        tr["fecha_entrada"] = P.indice[tr["i"].to_numpy()]
        tr["fecha_salida"] = P.indice[tr["salida"].to_numpy()]
        tr["anio"] = tr["fecha_entrada"].dt.year
        tr["mes"] = tr["fecha_entrada"].dt.to_period("M")
        por_anio = pd.DataFrame([{"año": y, "operaciones": len(g), "WR_resultado": float(100 * (g["R"] > 0).mean()), "R_total": float(g["R"].sum())}
                                 for y, g in tr.groupby("anio")]).set_index("año")
        por_mes = tr.groupby("mes")["R"].sum()
    avisos = list(PR.avisos)
    for nombre, f in tabla.iterrows():
        if f["resueltas"] < 100:
            avisos.append(f"{nombre}: solo {int(f['resueltas'])} operaciones resueltas; muestra débil.")
    if prueba and prueba >= 20:
        avisos.append(f"Prueba n.º {prueba}: con tantas pruebas, un resultado bueno puede ser azar.")
    return {"tabla": tabla, "trades": tr, "por_anio": por_anio, "por_mes": por_mes, "avisos": avisos, "prueba": prueba, "PR": PR, "P": P,
            "descartes": res_todo.descartes, "cuenta": res_todo.cuenta, "senales_crudas": PR.senales_crudas}


# ---------------------------------------------------------------- ablacion (acumulada, como la de la EMA)
def ablacion_rev(df: pd.DataFrame, cfg: "eng.Config", rv: ConfigRev) -> pd.DataFrame:
    """Parte de la señal sola y va sumando, de a uno, lo que esta activo: ADX (en B, si esta elegido), horario propio, noticias,
    cierre por tiempo y breakeven. Una fila por paso: operaciones, R total, expectativa, % de ganadoras y caida maxima."""
    base = replace(rv, adx_activo_b=False, sesion_activo=False, tstop_activo=False, be_activo=False)
    cfg0 = replace(cfg, noticias_activo=False)
    pasos = [("Señal sola" + (" (sin ADX)" if rv.variante == "A" else ""), cfg0, replace(base, adx_max=1e9) if rv.variante == "A" else base)]
    c_, r_ = cfg0, pasos[0][2]
    if rv.variante == "A":
        r_ = replace(r_, adx_max=rv.adx_max)
        pasos.append(("+ ADX máximo", c_, r_))
    elif rv.adx_activo_b:
        r_ = replace(r_, adx_activo_b=True)
        pasos.append(("+ ADX máximo", c_, r_))
    if rv.sesion_activo:
        r_ = replace(r_, sesion_activo=True)
        pasos.append(("+ Horario propio", c_, r_))
    if cfg.noticias_activo:
        c_ = cfg
        pasos.append(("+ Noticias", c_, r_))
    if rv.tstop_activo:
        r_ = replace(r_, tstop_activo=True)
        pasos.append(("+ Cierre por tiempo", c_, r_))
    if rv.be_activo:
        r_ = replace(r_, be_activo=True)
        pasos.append(("+ Breakeven", c_, r_))
    filas = []
    for nombre, c1, r1 in pasos:
        PR = preparar_rev(df, c1, r1)
        res = ejecutar_rev(PR, c1, r1)
        s = resumen_rev(res.trades)
        filas.append({"paso": nombre, "operaciones": int(len(res.trades)), "R_total": s["R_total"], "exp_R": s["exp_R"],
                      "WR_resultado": s["WR_resultado"], "maxDD_R": s["maxDD_R"]})
    return pd.DataFrame(filas).set_index("paso")
