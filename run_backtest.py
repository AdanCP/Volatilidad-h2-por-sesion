#!/usr/bin/env python3
"""Corre el backtester desde la terminal (la interfaz Streamlit es la etapa b).

Ejemplos:
  python run_backtest.py --fuente sintetico
  python run_backtest.py --fuente mt5 --simbolo XAUUSD --tf H1 --desde 2020-01-01
  python run_backtest.py --fuente mt5 --tf H1 --desde 2020-01-01 --sma 200 --adx-min 20
  python run_backtest.py --fuente mt5 --tf H1 --desde 2020-01-01 --ablacion --offset-servidor 2
  python run_backtest.py --fuente csv --archivo XAUUSD_H1.csv --point 0.01 --lotes 0.10
"""
import argparse
import sys

import pandas as pd

import data as dt
import engine as eng
import metrics as met

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 30)


def parse():
    p = argparse.ArgumentParser(description="Backtester de cruce de EMAs con filtros")
    p.add_argument("--fuente", choices=["mt5", "csv", "sintetico"], default="sintetico")
    p.add_argument("--simbolo", default="XAUUSD")
    p.add_argument("--tf", choices=list(dt.TF_MT5), default="H1")
    p.add_argument("--desde", default="2020-01-01")
    p.add_argument("--hasta", default=None)
    p.add_argument("--archivo")
    p.add_argument("--point", type=float, default=0.01, help="valor de 1 punto (CSV con columna spread)")
    p.add_argument("--tendencia", type=float, default=0.0, help="solo sintetico")
    g = p.add_argument_group("señal y gestion")
    g.add_argument("--ema-corta", type=int, default=13)
    g.add_argument("--ema-larga", type=int, default=34)
    g.add_argument("--rr", type=float, default=2.0)
    g.add_argument("--sl-modo", choices=["atr", "pct"], default="atr")
    g.add_argument("--sl-valor", type=float, default=1.5)
    g.add_argument("--atr-periodo", type=int, default=14)
    g.add_argument("--direccion", choices=["ambas", "largos", "cortos"], default="ambas")
    g.add_argument("--spread", choices=["vela", "mediana", "fijo", "ninguno"], default="vela")
    g.add_argument("--spread-fijo", type=float, default=0.0)
    g.add_argument("--costo-extra", type=float, default=0.0)
    f = p.add_argument_group("filtros (cada uno se activa solo si se indica)")
    f.add_argument("--sma", type=int, metavar="PERIODO", help="activa el filtro SMA")
    f.add_argument("--sma-dist", type=float, default=0.0, help="distancia minima al precio en ATR")
    f.add_argument("--sma-pend", type=int, default=0, help="exigir pendiente a favor, N velas")
    f.add_argument("--adx-min", type=float, help="activa el filtro ADX con este minimo")
    f.add_argument("--adx-periodo", type=int, default=14)
    f.add_argument("--adx-max", type=float)
    f.add_argument("--adx-creciente", type=int, default=0, help="ADX creciente, N velas")
    f.add_argument("--atr-min", type=float, help="activa el filtro ATR (minimo)")
    f.add_argument("--atr-max", type=float)
    f.add_argument("--atr-unidad", choices=["pct", "precio"], default="pct")
    f.add_argument("--atr-rel", type=int, default=0, help="modo relativo: promedio de N velas")
    f.add_argument("--atr-rel-min", type=float)
    f.add_argument("--atr-rel-max", type=float)
    f.add_argument("--sesiones", help='ej. "Londres,Nueva York" (activa el filtro de sesion)')
    f.add_argument("--offset-servidor", type=float, help="desfase del servidor en invierno (GMT+2 -> 2)")
    f.add_argument("--sin-dst-eeuu", action="store_true", help="el servidor NO cambia de hora con EEUU")
    d = p.add_argument_group("dinero")
    d.add_argument("--lotes", type=float)
    d.add_argument("--comision", type=float, default=0.0, help="por lote")
    d.add_argument("--tick-size", type=float, help="CSV/sintetico; con MT5 se lee del simbolo")
    d.add_argument("--tick-value", type=float)
    p.add_argument("--oos", type=float, default=0.3)
    p.add_argument("--azar-veces", type=int, default=200)
    p.add_argument("--semilla", type=int, default=42)
    p.add_argument("--ablacion", action="store_true", help="cruce solo + un filtro por vez")
    return p.parse_args()


def armar_config(a) -> eng.Config:
    c = eng.Config(ema_corta=a.ema_corta, ema_larga=a.ema_larga, rr=a.rr, sl_modo=a.sl_modo,
                   sl_valor=a.sl_valor, atr_periodo=a.atr_periodo, direccion=a.direccion,
                   spread=a.spread, spread_fijo=a.spread_fijo, costo_extra=a.costo_extra,
                   servidor_offset_horas=a.offset_servidor, servidor_dst_eeuu=not a.sin_dst_eeuu)
    if a.sma:
        c.sma_activo, c.sma_periodo, c.sma_dist_min_atr, c.sma_pendiente_n = True, a.sma, a.sma_dist, a.sma_pend
    if a.adx_min is not None:
        c.adx_activo, c.adx_min, c.adx_max = True, a.adx_min, a.adx_max
        c.adx_periodo, c.adx_creciente_n = a.adx_periodo, a.adx_creciente
    if a.atr_min is not None or a.atr_max is not None or a.atr_rel:
        c.atr_activo, c.atr_min, c.atr_max, c.atr_unidad = True, a.atr_min, a.atr_max, a.atr_unidad
        c.atr_rel_n, c.atr_rel_min, c.atr_rel_max = a.atr_rel, a.atr_rel_min, a.atr_rel_max
    if a.sesiones:
        c.sesion_activo, c.sesiones = True, tuple(s.strip() for s in a.sesiones.split(","))
    return c


def cargar(a):
    if a.fuente == "mt5":
        print("Descargando de MT5 por tramos", end="", flush=True)
        df, spec, vacios = dt.cargar_mt5(a.simbolo, a.tf, a.desde, a.hasta, progreso=lambda: print(".", end="", flush=True))
        print(f" listo ({vacios} tramos sin datos).")
        return df, spec
    if a.fuente == "csv":
        if not a.archivo:
            sys.exit("Con --fuente csv hay que indicar --archivo.")
        return dt.cargar_csv(a.archivo, a.point), {}
    return dt.sintetico(tendencia=a.tendencia, seed=a.semilla), {}


def main():
    a = parse()
    try:
        df, spec = cargar(a)
        cfg = armar_config(a)
        cfg.validar()
    except (dt.ErrorDatos, ValueError, RuntimeError) as e:
        sys.exit(f"Error: {e}")
    if len(df) < 200:
        sys.exit(f"Datos insuficientes: {len(df)} velas (se necesitan al menos 200).")
    q = dt.calidad(df)
    print(f"\nDatos: {a.fuente} | {q['velas']} velas | {q['primera']} -> {q['ultima']}")
    print(f"Calidad: huecos>4d {q['huecos_mas_de_4d']} (mayor {q['mayor_hueco_dias']} d) | "
          f"duplicadas {q['duplicadas']} | NaN {q['con_nan']} | spread 0 en {q['spread_cero_pct']}% de las velas")
    print(f"EMA {cfg.ema_corta}/{cfg.ema_larga} | RR 1:{cfg.rr:g} | SL {cfg.sl_valor:g} "
          f"{'ATR' if cfg.sl_modo == 'atr' else '%'}({cfg.atr_periodo}) | spread: {cfg.spread} | {cfg.direccion}")
    activos = [n for n, on in (("SMA", cfg.sma_activo), ("ADX", cfg.adx_activo),
                               ("ATR", cfg.atr_activo), ("Sesion", cfg.sesion_activo)) if on]
    print("Filtros activos: " + (", ".join(activos) if activos else "ninguno (cruce solo)") + "\n")

    contador = met.ContadorPruebas()
    if a.ablacion:
        tabla, omit = met.ablacion(df, cfg, oos_pct=a.oos, azar_veces=a.azar_veces, semilla=a.semilla, contador=contador)
        print("ABLACION (cada filtro con sus valores por defecto; editar met.FILTROS_ABLACION):")
        print(tabla.round(2).to_string())
        if omit:
            print(f"\nOmitidos: {', '.join(omit)} (falta --offset-servidor, el desfase horario del servidor).")
        print(f"\nPruebas realizadas en esta sesion: {contador.n}. Un filtro solo cuenta si mejora el "
              "out-of-sample y no solo el total.\n")
        return

    r = met.evaluar(df, cfg, a.oos, a.azar_veces, a.semilla, contador)
    cols = ["resueltas", "TP", "SL", "abiertas", "ambiguas", "%TP", "%equilibrio", "exp_R",
            "azar_exp_R", "mejor_que_%azar", "R_total", "maxDD_R", "racha_SL"]
    print(r["tabla"][cols].round(2).to_string())
    print(f"\nCruces: {r['tabla'].loc['Todo', 'cruces']} | tomados: {r['tabla'].loc['Todo', 'tomados']} | "
          f"ignorados por operacion abierta: {r['tabla'].loc['Todo', 'ignoradas']}")
    if r["descartes"]:
        print("Descartados por filtro: " + ", ".join(f"{k} {v}" for k, v in r["descartes"].items()))
    if len(r["por_anio"]):
        print("\nPor año de entrada:")
        print(r["por_anio"].round(2).to_string())
    if a.lotes:
        ts, tv = (spec.get("tick_size"), spec.get("tick_value")) if spec else (a.tick_size, a.tick_value)
        ts, tv = ts or a.tick_size or 0.01, tv or a.tick_value or 1.0
        if spec:
            met.validar_lotaje(a.lotes, spec["vol_min"], spec["vol_max"], spec["vol_step"])
        m = met.resumen_dinero(r["trades"], ts, tv, a.lotes, a.comision)
        print(f"\nDINERO (teorico; {a.lotes} lotes, tick_size {ts}, tick_value {tv}, comision {a.comision}/lote):")
        for k, v in m.items():
            print(f"  {k}: {v:,.2f}" if isinstance(v, float) else f"  {k}: {v}")
    if r["avisos"]:
        print("\nAvisos:")
        for x in r["avisos"]:
            print("  - " + x)
    print(f"\nPrueba n.º {r['prueba']} de esta sesion. Lectura: exp_R > 0 cuenta como ventaja SOLO si se repite en\n"
          "out-of-sample, en la mayoria de los años y en parametros vecinos. 'mejor_que_%azar' cerca de 50 =\n"
          "la señal no se distingue de entrar al azar. Velas OHLC, sin slippage: el Strategy Tester con\n"
          "ticks reales es la validacion final.\n")


if __name__ == "__main__":
    main()
