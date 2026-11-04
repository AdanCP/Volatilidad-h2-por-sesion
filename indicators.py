"""Indicadores sobre arrays de numpy. Todos son causales: el valor en la vela i
solo usa datos hasta la vela i (sin look-ahead)."""
import numpy as np
import pandas as pd


def ema(x, periodo: int) -> np.ndarray:
    """EMA (adjust=False), igual que la de cruce_minimo.py y la del bot."""
    return pd.Series(x).ewm(span=periodo, adjust=False).mean().to_numpy()


def sma(x, periodo: int) -> np.ndarray:
    """Media simple del cierre; NaN hasta tener 'periodo' velas."""
    return pd.Series(x).rolling(periodo).mean().to_numpy()


def rango_verdadero(h, l, c) -> np.ndarray:
    prev = np.r_[c[0], c[:-1]]
    return np.maximum.reduce([h - l, np.abs(h - prev), np.abs(l - prev)])


def atr_wilder(h, l, c, periodo: int) -> np.ndarray:
    """ATR con suavizado de Wilder: ewm con alpha = 1/periodo."""
    return pd.Series(rango_verdadero(h, l, c)).ewm(alpha=1 / periodo, adjust=False).mean().to_numpy()


def adx_wilder(h, l, c, periodo: int):
    """ADX con suavizado de Wilder. Devuelve (adx, +DI, -DI).

    Formula:  +DM = max(h[i]-h[i-1], 0) si supera a (l[i-1]-l[i]), si no 0 (y simetrico para -DM).
              +DI = 100 * suav(+DM) / suav(TR);  -DI = 100 * suav(-DM) / suav(TR)
              DX  = 100 * |+DI - -DI| / (+DI + -DI);  ADX = suav(DX)
    donde suav(x) = ewm(alpha=1/periodo, adjust=False) (recursion de Wilder).
    Ojo: la semilla de la recursion es el primer valor y no el promedio inicial de
    Wilder, asi que los primeros ~2*periodo valores difieren del iADX de MT5; despues
    convergen. Conviene comparar contra iADX antes de replicar en el EA.
    """
    arriba = np.r_[0.0, h[1:] - h[:-1]]
    abajo = np.r_[0.0, l[:-1] - l[1:]]
    mas = np.where((arriba > abajo) & (arriba > 0), arriba, 0.0)
    menos = np.where((abajo > arriba) & (abajo > 0), abajo, 0.0)
    a = 1 / periodo
    tr = pd.Series(rango_verdadero(h, l, c)).ewm(alpha=a, adjust=False).mean()
    pdi = 100 * pd.Series(mas).ewm(alpha=a, adjust=False).mean() / tr
    ndi = 100 * pd.Series(menos).ewm(alpha=a, adjust=False).mean() / tr
    dx = (100 * (pdi - ndi).abs() / (pdi + ndi)).fillna(0.0)
    adx = dx.ewm(alpha=a, adjust=False).mean()
    return adx.to_numpy(), pdi.fillna(0.0).to_numpy(), ndi.fillna(0.0).to_numpy()


def vwap_diario(h, l, c, vol, dia):
    """VWAP que se reinicia cada día. `dia`: una clave por vela (p. ej. la fecha). Precio típico (H+L+C)/3 ponderado por volumen.
    Las velas sin volumen pesan 1 (evita dividir por cero; con volumen de ticks el efecto es despreciable).
    Devuelve (vwap, numero_de_vela_del_dia) con la primera vela del día = 1."""
    tp = (np.asarray(h, float) + np.asarray(l, float) + np.asarray(c, float)) / 3.0
    w = np.asarray(vol, float).copy()
    w[~(w > 0)] = 1.0
    pv = pd.Series(tp * w).groupby(np.asarray(dia)).cumsum().to_numpy()
    v = pd.Series(w).groupby(np.asarray(dia)).cumsum().to_numpy()
    nro = pd.Series(np.ones(len(tp))).groupby(np.asarray(dia)).cumsum().to_numpy()
    return pv / v, nro


def eficiencia(c, ventana: int):
    """Ratio de eficiencia de Kaufman en cada vela: |cierre[i] - cierre[i-N]| / suma de |cierre[k] - cierre[k-1]| (k = i-N+1 .. i).
    Va de 0 (el precio va y viene sin avanzar: rango) a 1 (movimiento limpio en una sola direccion).
    Si el precio no se movio en toda la ventana (recorrido 0) vale 0. Las primeras N velas quedan en NaN."""
    c = np.asarray(c, float)
    n = len(c)
    out = np.full(n, np.nan)
    if n <= ventana:
        return out
    paso = np.abs(np.diff(c, prepend=np.nan))                   # paso[k] = |c[k] - c[k-1]|; paso[0] = NaN
    recorrido = pd.Series(paso).rolling(ventana).sum().to_numpy()
    neto = np.abs(c - np.r_[np.full(ventana, np.nan), c[:-ventana]])
    ok = ~np.isnan(recorrido) & ~np.isnan(neto)
    with np.errstate(divide="ignore", invalid="ignore"):
        out[ok] = np.where(recorrido[ok] > 0, neto[ok] / recorrido[ok], 0.0)
    return out
