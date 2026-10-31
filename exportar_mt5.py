#!/usr/bin/env python3
"""Exporta el historial de MT5 (FTMO) a CSV, uno por simbolo y temporalidad.

Sirve para usar el backtester ONLINE (Render no puede conectarse a MT5): corres esto en tu PC con
Windows y el terminal abierto, y despues subis los CSV a la app. Solo LEE datos.

Ejemplos:
  python exportar_mt5.py --simbolos auto --tfs H1 --desde 2020-01-01
  python exportar_mt5.py --simbolos XAUUSD,EURUSD --tfs H1,H4 --desde 2015-01-01
Los CSV quedan en ./exportaciones_mt5 (tu .gitignore ya excluye *.csv, asi que no se suben a Git).
"""
import argparse
import os
import sys

import data as dt


def main():
    p = argparse.ArgumentParser(description="Exporta historial de MT5 a CSV")
    p.add_argument("--simbolos", default="auto", help="'auto' (oro, plata, BTC, mayores, indices) o lista con comas")
    p.add_argument("--tfs", default="H1", help="ej. H1,H4")
    p.add_argument("--desde", default="2020-01-01")
    p.add_argument("--hasta", default=None)
    p.add_argument("--salida", default="exportaciones_mt5")
    a = p.parse_args()
    try:
        if a.simbolos == "auto":
            hall = dt.detectar_simbolos(dt.listar_simbolos_mt5())
            simbolos = [v for v in hall.values() if v]
            faltan = [k for k, v in hall.items() if not v]
            if faltan:
                print(f"No disponibles en el servidor: {', '.join(faltan)}")
        else:
            simbolos = [s.strip() for s in a.simbolos.split(",") if s.strip()]
    except dt.ErrorDatos as e:
        sys.exit(f"Error: {e}")
    os.makedirs(a.salida, exist_ok=True)
    for s in simbolos:
        for tf in [t.strip().upper() for t in a.tfs.split(",") if t.strip()]:
            print(f"{s} {tf} ", end="", flush=True)
            try:
                df, spec, vacios = dt.cargar_mt5(s, tf, a.desde, a.hasta, progreso=lambda: print(".", end="", flush=True))
            except dt.ErrorDatos as e:
                print(f" omitido ({e})")
                continue
            ruta = os.path.join(a.salida, f"{s}_{tf}.csv")
            dt.exportar_df(df, spec["point"]).to_csv(ruta, index=False)
            print(f" {len(df)} velas ({df.index[0].date()} -> {df.index[-1].date()}) -> {ruta}")
    print("\nListo. Subi esos archivos a la app (fuente 'CSV exportado de MT5').")
    print("Ojo: el CSV no trae tick_size ni tick_value; para ver dinero en simbolos que no son oro, cargalos a mano.")


if __name__ == "__main__":
    main()
