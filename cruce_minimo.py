#!/usr/bin/env python3
"""
cruce_minimo.py - Backtest minimo de cruce de EMAs (pensado para XAUUSD en MT5)

Responde UNA pregunta: con este cruce, este SL (en ATR) y este RR, ¿se toca el
TP mas veces de lo que ocurriria con entradas al azar?

Ejemplos:
  python cruce_minimo.py --fuente sintetico
  python cruce_minimo.py --fuente mt5 --simbolo XAUUSD --tf H1 --desde 2020-01-01
  python cruce_minimo.py --fuente csv --archivo XAUUSD_H1.csv --point 0.01

Reglas:
  - Entrada al CIERRE de la vela del cruce (alcista = largo, bajista = corto).
  - SL = ATR * multiplicador; TP = SL * RR.
  - Una operacion a la vez: los cruces con una operacion abierta se ignoran.
  - Si una vela toca SL y TP a la vez se cuenta como SL (y como "ambigua").
  - Spread: las velas de MT5 son precio BID. Largo entra al ask (cierre + spread);
    corto entra al bid, y su SL/TP se activan con el ask (precio + spread).
  - Sin slippage, sin comision, sin gaps. Fills exactos en el nivel.
"""
import argparse
import sys

import numpy as np
import pandas as pd

TF_MT5 = {"M1": "TIMEFRAME_M1", "M5": "TIMEFRAME_M5", "M15": "TIMEFRAME_M15",
          "M30": "TIMEFRAME_M30", "H1": "TIMEFRAME_H1", "H4": "TIMEFRAME_H4",
          "D1": "TIMEFRAME_D1", "W1": "TIMEFRAME_W1"}


# ----------------------------------------------------------------- datos
def cargar_mt5(simbolo, tf, desde, hasta):
    try:
        import MetaTrader5 as mt5
    except ImportError:
        sys.exit("Falta la libreria: pip install MetaTrader5 (solo Windows).")
    if not mt5.initialize():
        sys.exit(f"No se pudo conectar al terminal MT5: {mt5.last_error()}")
    try:
        info = mt5.symbol_info(simbolo)
        if info is None:
            sys.exit(f"El simbolo {simbolo} no existe en este servidor.")
        mt5.symbol_select(simbolo, True)
        rates = mt5.copy_rates_range(simbolo, getattr(mt5, TF_MT5[tf]),
                                     pd.Timestamp(desde).to_pydatetime(),
                                     pd.Timestamp(hasta).to_pydatetime())
        if rates is None or len(rates) == 0:
            sys.exit(f"MT5 no devolvio velas ({mt5.last_error()}).")
        point = info.point
    finally:
        mt5.shutdown()
    df = pd.DataFrame(rates)
    df.index = pd.to_datetime(df["time"], unit="s")
    df = df.rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close"})
    df["Spread"] = df["spread"] * point          # puntos -> unidades de precio
    return df[["Open", "High", "Low", "Close", "Spread"]]


def cargar_csv(archivo, point):
    """CSV exportado de MT5 (<DATE> <TIME> <OPEN>...) o con columnas time/open/high/low/close."""
    df = pd.read_csv(archivo, sep=None, engine="python")
    df.columns = [c.strip("<> ").lower() for c in df.columns]
    if "date" in df and "time" in df:
        idx = pd.DatetimeIndex(pd.to_datetime(df["date"].astype(str) + " " + df["time"].astype(str)))
    else:
        col = next((c for c in ("time", "datetime", "date") if c in df), None)
        if col is None:
            sys.exit("El CSV necesita columnas de fecha/hora (date+time, time o datetime).")
        idx = pd.DatetimeIndex(pd.to_datetime(df[col]))
    faltan = [c for c in ("open", "high", "low", "close") if c not in df]
    if faltan:
        sys.exit(f"Faltan columnas en el CSV: {faltan}")
    out = pd.DataFrame({"Open": df["open"].to_numpy(), "High": df["high"].to_numpy(),
                        "Low": df["low"].to_numpy(), "Close": df["close"].to_numpy()}, index=idx)
    out["Spread"] = df["spread"].to_numpy() * point if "spread" in df else 0.0
    return out.sort_index()


def sintetico(n=30000, tendencia=0.0, seed=1, precio=2000.0, sigma=3.0, spread=0.3):
    """Serie de prueba. tendencia=0 -> paseo aleatorio puro (sin ventaja posible)."""
    rng = np.random.default_rng(seed)
    z = np.zeros(n)
    for i in range(1, n):
        z[i] = 0.98 * z[i - 1] + rng.normal()
    drift = tendencia * sigma * z / (z.std() + 1e-12)
    close = precio + np.cumsum(drift + rng.normal(0, sigma, n))
    open_ = np.r_[precio, close[:-1]]
    high = np.maximum(open_, close) + np.abs(rng.normal(0, sigma * 0.4, n))
    low = np.minimum(open_, close) - np.abs(rng.normal(0, sigma * 0.4, n))
    idx = pd.date_range("2018-01-01", periods=n, freq="h")
    return pd.DataFrame({"Open": open_, "High": high, "Low": low, "Close": close,
                         "Spread": spread}, index=idx)


# ------------------------------------------------------------ indicadores
def atr_wilder(h, l, c, n):
    prev = np.r_[c[0], c[:-1]]
    tr = np.maximum.reduce([h - l, np.abs(h - prev), np.abs(l - prev)])
    return pd.Series(tr).ewm(alpha=1 / n, adjust=False).mean().to_numpy()


def senales(close, corta, larga, direccion="ambas"):
    """Lista de (indice, lado): +1 largo en cruce alcista, -1 corto en cruce bajista."""
    s = pd.Series(close)
    diff = (s.ewm(span=corta, adjust=False).mean() - s.ewm(span=larga, adjust=False).mean()).to_numpy()
    prev = np.r_[np.nan, diff[:-1]]
    up = (diff > 0) & (prev <= 0)
    dn = (diff < 0) & (prev >= 0)
    out = []
    for i in range(larga + 1, len(close)):          # descarta el warm-up
        if up[i] and direccion in ("ambas", "largos"):
            out.append((i, 1))
        elif dn[i] and direccion in ("ambas", "cortos"):
            out.append((i, -1))
    return out


# ---------------------------------------------------------------- motor
def simular(a, sig, rr, mult, spread=True):
    """a: dict con arrays h, l, c, sp, atr. sig: lista de (indice, lado). Devuelve DataFrame."""
    h, l, c, sp, atr = a["h"], a["l"], a["c"], a["sp"], a["atr"]
    n = len(c)
    trades, libre = [], 0
    for i, lado in sig:
        if i < libre:                                  # operacion en curso: se ignora
            continue
        dist = atr[i] * mult
        if not dist > 0:
            continue
        s_in = sp[i] if spread else 0.0
        entrada = c[i] + s_in if lado == 1 else c[i]
        sl = entrada - lado * dist
        tp = entrada + lado * dist * rr
        res, amb, j_out = "ABIERTA", False, n - 1
        for j in range(i + 1, n):
            s = sp[j] if spread else 0.0
            if lado == 1:
                hit_sl, hit_tp = l[j] <= sl, h[j] >= tp
            else:
                hit_sl, hit_tp = h[j] + s >= sl, l[j] + s <= tp
            if hit_sl and hit_tp:
                res, amb, j_out = "SL", True, j
                break
            if hit_sl:
                res, j_out = "SL", j
                break
            if hit_tp:
                res, j_out = "TP", j
                break
        trades.append({"i": i, "lado": lado, "res": res, "amb": amb, "salida": j_out})
        if res == "ABIERTA":
            break
        libre = j_out + 1
    return pd.DataFrame(trades, columns=["i", "lado", "res", "amb", "salida"])


def resumen(tr, rr):
    tp = int((tr["res"] == "TP").sum()) if len(tr) else 0
    sl = int((tr["res"] == "SL").sum()) if len(tr) else 0
    res = tp + sl
    return {"resueltas": res, "TP": tp, "SL": sl,
            "abiertas": int((tr["res"] == "ABIERTA").sum()) if len(tr) else 0,
            "ambiguas": int(tr["amb"].sum()) if len(tr) else 0,
            "%TP": 100 * tp / res if res else np.nan,
            "%equilibrio": 100 / (1 + rr),
            "exp_R": (tp * rr - sl) / res if res else np.nan}


def azar(a, n_sig, lo, hi, rr, mult, spread, veces, rng, direccion):
    """Expectativa en R de entradas aleatorias (misma regla de SL/TP/una-a-la-vez)."""
    n_sig = min(n_sig, hi - lo - 1)
    if n_sig < 1:
        return np.array([])
    lados = {"ambas": [1, -1], "largos": [1], "cortos": [-1]}[direccion]
    out = []
    for _ in range(veces):
        idx = np.sort(rng.choice(np.arange(lo, hi), size=n_sig, replace=False))
        sig = list(zip(idx, rng.choice(lados, size=n_sig)))
        out.append(resumen(simular(a, sig, rr, mult, spread), rr)["exp_R"])
    return np.array([x for x in out if not np.isnan(x)])


# ----------------------------------------------------------------- main
def main():
    p = argparse.ArgumentParser(description="Backtest minimo de cruce de EMAs")
    p.add_argument("--fuente", choices=["mt5", "csv", "sintetico"], default="sintetico")
    p.add_argument("--simbolo", default="XAUUSD")
    p.add_argument("--tf", choices=list(TF_MT5), default="H1")
    p.add_argument("--desde", default="2020-01-01")
    p.add_argument("--hasta", default=str(pd.Timestamp.today().date()))
    p.add_argument("--archivo")
    p.add_argument("--point", type=float, default=0.01, help="valor de 1 punto (CSV con columna spread)")
    p.add_argument("--ema-corta", type=int, default=13)
    p.add_argument("--ema-larga", type=int, default=34)
    p.add_argument("--rr", type=float, default=2.0)
    p.add_argument("--atr-mult", type=float, default=1.5)
    p.add_argument("--atr-periodo", type=int, default=14)
    p.add_argument("--direccion", choices=["ambas", "largos", "cortos"], default="ambas")
    p.add_argument("--sin-spread", action="store_true")
    p.add_argument("--oos", type=float, default=0.3, help="fraccion final reservada como out-of-sample")
    p.add_argument("--azar-veces", type=int, default=200)
    p.add_argument("--semilla", type=int, default=42)
    p.add_argument("--tendencia", type=float, default=0.0, help="solo sintetico: 0 = sin ventaja")
    a = p.parse_args()

    if a.ema_corta >= a.ema_larga:
        sys.exit("La EMA corta debe ser menor que la larga.")
    if not 1 <= a.rr <= 10:
        sys.exit("El RR debe estar entre 1 y 10.")

    if a.fuente == "mt5":
        df = cargar_mt5(a.simbolo, a.tf, a.desde, a.hasta)
    elif a.fuente == "csv":
        if not a.archivo:
            sys.exit("Con --fuente csv hay que indicar --archivo.")
        df = cargar_csv(a.archivo, a.point)
    else:
        df = sintetico(tendencia=a.tendencia, seed=a.semilla)
    df = df.dropna(subset=["Open", "High", "Low", "Close"])
    if len(df) < 200:
        sys.exit(f"Datos insuficientes: {len(df)} velas (se necesitan al menos 200).")

    arr = {"h": df["High"].to_numpy(float), "l": df["Low"].to_numpy(float),
           "c": df["Close"].to_numpy(float), "sp": df["Spread"].to_numpy(float)}
    arr["atr"] = atr_wilder(arr["h"], arr["l"], arr["c"], a.atr_periodo)
    n = len(df)
    corte = int(n * (1 - a.oos))
    usar_spread = not a.sin_spread
    sig = senales(arr["c"], a.ema_corta, a.ema_larga, a.direccion)
    rng = np.random.default_rng(a.semilla)

    print(f"\nDatos: {a.fuente} | {n} velas | {df.index[0]} -> {df.index[-1]}")
    print(f"EMA {a.ema_corta}/{a.ema_larga} | RR 1:{a.rr:g} | SL {a.atr_mult:g} ATR({a.atr_periodo})"
          f" | spread {'SI' if usar_spread else 'NO'} | direccion {a.direccion}")
    print(f"Spread medio: {df['Spread'].mean():.3f} | ATR medio: {arr['atr'].mean():.3f}"
          f" | spread/SL medio: {100 * df['Spread'].mean() / (arr['atr'].mean() * a.atr_mult):.1f}%\n")

    filas, trades_todo = [], None
    for nombre, lo, hi in [("Todo", 0, n), ("In-sample", 0, corte), ("Out-of-sample", corte, n)]:
        s = [x for x in sig if lo <= x[0] < hi]
        tr = simular(arr, s, a.rr, a.atr_mult, usar_spread)
        if nombre == "Todo":
            trades_todo = tr
        r = resumen(tr, a.rr)
        base = azar(arr, len(s), lo, hi, a.rr, a.atr_mult, usar_spread, a.azar_veces, rng, a.direccion)
        r["azar_exp_R"] = base.mean() if len(base) else np.nan
        r["mejor_que_%azar"] = 100 * (base < r["exp_R"]).mean() if len(base) and not np.isnan(r["exp_R"]) else np.nan
        filas.append({"tramo": nombre, **r})
    tabla = pd.DataFrame(filas).set_index("tramo")
    print(tabla.round(2).to_string())

    if trades_todo is not None and len(trades_todo):
        t = trades_todo.copy()
        t["anio"] = df.index[t["i"].to_numpy()].year
        print("\nPor año de entrada:")
        por = []
        for y, g in t.groupby("anio"):
            r = resumen(g, a.rr)
            por.append({"año": y, "resueltas": r["resueltas"], "TP": r["TP"], "SL": r["SL"], "exp_R": r["exp_R"]})
        print(pd.DataFrame(por).set_index("año").round(2).to_string())

    print("\nLectura:")
    for nombre, r in tabla.iterrows():
        if r["resueltas"] < 100:
            print(f"  - {nombre}: solo {int(r['resueltas'])} operaciones resueltas; muestra debil.")
    print("  - exp_R > 0 y %TP > %equilibrio indican ventaja SOLO si se repite en out-of-sample,")
    print("    en la mayoria de los años y en parametros vecinos. 'mejor_que_%azar' cercano a")
    print("    50 significa que la señal no se distingue de entrar al azar.")
    print("  - Velas OHLC, sin slippage ni comision: el Strategy Tester con ticks reales es la")
    print("    validacion final.\n")


if __name__ == "__main__":
    main()
