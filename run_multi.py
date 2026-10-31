#!/usr/bin/env python3
"""Comparador multi-simbolo: los MISMOS parametros en cada simbolo, una fila por activo.

NO sirve para elegir el activo ganador: al probar varios, alguno sale bien por azar. Sirve para ver
si la idea se sostiene en la mayoria de los mercados o solo en uno.

Ejemplos:
  python run_multi.py --fuente mt5 --simbolos auto --tf H1 --desde 2020-01-01 --recortar-comun
  python run_multi.py --fuente mt5 --simbolos XAUUSD,XAGUSD,EURUSD,US30 --tf H1 --desde 2020-01-01
  python run_multi.py --fuente sintetico            # prueba de la herramienta
Acepta los mismos parametros de señal, gestion y filtros que run_backtest.py.
"""
import sys

import pandas as pd

import data as dt
import metrics as met
from run_backtest import armar_config, crear_parser

pd.set_option("display.width", 220)
pd.set_option("display.max_columns", 30)


def main():
    p = crear_parser()
    p.add_argument("--simbolos", default="auto", help="'auto' (oro, plata, BTC, mayores, indices) o lista con comas")
    p.add_argument("--recortar-comun", action="store_true", help="usar solo el periodo que todos comparten")
    a = p.parse_args()
    try:
        cfg = armar_config(a)
        cfg.validar()
        datos, faltan = {}, []
        if a.fuente == "sintetico":
            for k in range(4):
                datos[f"SINT{k + 1}"] = dt.sintetico(n=12000 + 2000 * k, tendencia=a.tendencia, seed=10 + k)
        elif a.fuente == "mt5":
            if a.simbolos == "auto":
                hall = dt.detectar_simbolos(dt.listar_simbolos_mt5())
                simbolos = [v for v in hall.values() if v]
                faltan = [k for k, v in hall.items() if not v]
            else:
                simbolos = [s.strip() for s in a.simbolos.split(",") if s.strip()]
            for s in simbolos:
                print(f"Descargando {s} {a.tf} ", end="", flush=True)
                try:
                    datos[s] = dt.cargar_mt5(s, a.tf, a.desde, a.hasta, progreso=lambda: print(".", end="", flush=True))[0]
                    print(f" {len(datos[s])} velas")
                except dt.ErrorDatos as e:
                    print(f" omitido ({e})")
        else:
            sys.exit("El modo multi-simbolo necesita --fuente mt5 (o sintetico para probar).")
    except (dt.ErrorDatos, ValueError, RuntimeError) as e:
        sys.exit(f"Error: {e}")
    if not datos:
        sys.exit("No hay datos para comparar.")
    if faltan:
        print(f"No disponibles en el servidor: {', '.join(faltan)}")

    contador = met.ContadorPruebas()
    tabla, notas = met.comparar_simbolos(datos, cfg, a.oos, a.azar_veces, a.semilla, contador, a.recortar_comun)
    print(f"\nEMA {cfg.ema_corta}/{cfg.ema_larga} | RR 1:{cfg.rr:g} | SL {cfg.sl_valor:g} "
          f"{'ATR' if cfg.sl_modo == 'atr' else '%'} | spread: {cfg.spread} | tf {a.tf}\n")
    print(tabla.round(2).to_string())
    pos = int(((tabla["exp_R"] > 0) & (tabla["exp_R_OOS"] > 0)).sum())
    print(f"\nLectura de robustez: expectativa positiva en TODO y en OUT-OF-SAMPLE en {pos} de {len(tabla)} simbolos.")
    print(f"Pruebas realizadas en esta sesion: {contador.n}. Al probar varios activos es ESPERABLE que alguno salga "
          "bien por azar;\nelegir el mejor de varios es una forma de sobreajuste. Comparar en R, no en dinero "
          "(el valor por tick difiere entre activos).")
    for n in dict.fromkeys(notas):
        print("  - " + n)
    print()


if __name__ == "__main__":
    main()
