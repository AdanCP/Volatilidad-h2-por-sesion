#!/usr/bin/env python3
"""Sincroniza el historial de MT5 (FTMO) a la carpeta datos_mt5 y, opcionalmente, lo sube a GitHub.

La app online (Render) lee esa carpeta, asi puede elegir simbolos como si leyera MT5.
Solo LEE datos de MT5. Corre en tu PC con Windows, con el terminal abierto y con sesion iniciada.

Ejemplos:
  python sincronizar_mt5.py                       # auto (oro, plata, BTC, mayores, indices), H1, desde 2020
  python sincronizar_mt5.py --push                # ademas hace commit y push de datos_mt5
  python sincronizar_mt5.py --tfs H1,H4 --simbolos XAUUSD,EURUSD,US30.cash
IMPORTANTE: el repo deberia ser PRIVADO (son datos de tu broker).
"""
import argparse
import os
import subprocess
import sys
from datetime import datetime

import data as dt


def _git(*args, check=True):
    r = subprocess.run(["git", *args], capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} fallo:\n{r.stdout}{r.stderr}")
    return r


def subir(carpeta: str) -> None:
    _git("add", carpeta)
    if _git("diff", "--cached", "--quiet", "--", carpeta, check=False).returncode == 0:
        print("Sin cambios en los datos: no hay nada que subir.")
        return
    _git("commit", "-m", f"Sincroniza datos MT5 ({datetime.now():%Y-%m-%d %H:%M})", "--", carpeta)
    # El bot de alertas tambien hace commits en el repo: se trae lo ultimo antes de subir.
    _git("pull", "--rebase", "--autostash")
    _git("push")
    print("Datos subidos a GitHub. Render los usa cuando termine el redeploy.")


def main():
    p = argparse.ArgumentParser(description="Sincroniza MT5 -> datos_mt5 (-> GitHub)")
    p.add_argument("--simbolos", default="auto", help="'auto' o lista separada por comas")
    p.add_argument("--tfs", default="H1", help="ej. H1 o H1,H4 (M5/M1 pesan mucho)")
    p.add_argument("--desde", default="2020-01-01")
    p.add_argument("--salida", default=dt.CARPETA_SYNC)
    p.add_argument("--push", action="store_true", help="commit + push de la carpeta de datos")
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

    manifest = dt.leer_manifest(a.salida) or {"simbolos": {}}
    manifest.setdefault("simbolos", {})
    nuevos = 0
    for s in simbolos:
        for tf in [t.strip().upper() for t in a.tfs.split(",") if t.strip()]:
            print(f"{s} {tf} ", end="", flush=True)
            try:
                df, spec, _ = dt.cargar_mt5(s, tf, a.desde, None, progreso=lambda: print(".", end="", flush=True))
            except dt.ErrorDatos as e:
                print(f" omitido ({e})")
                continue
            dt.guardar_sync(df, spec, a.salida, s, tf)
            ent = manifest["simbolos"].setdefault(s, {"spec": spec, "tfs": {}})
            ent["spec"] = spec
            ent["tfs"][tf] = {"velas": len(df), "desde": str(df.index[0]), "hasta": str(df.index[-1])}
            nuevos += 1
            print(f" {len(df)} velas ({df.index[0].date()} -> {df.index[-1].date()})")
    if not nuevos:
        sys.exit("No se pudo sincronizar nada.")
    manifest["sincronizado"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    dt.escribir_manifest(a.salida, manifest)
    print(f"\nListo: {nuevos} series en ./{a.salida}")
    if a.push:
        try:
            subir(a.salida)
        except RuntimeError as e:
            sys.exit(f"No se pudo subir a GitHub:\n{e}")
    else:
        print("Para subirlas: agrega --push, o haz git add/commit/push de la carpeta.")


if __name__ == "__main__":
    main()
