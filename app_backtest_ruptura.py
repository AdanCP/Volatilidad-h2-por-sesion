"""Página «Backtester Ruptura»: ruptura del rango de apertura de Nueva York.

No duplica código: define el tipo de estrategia y ejecuta app_backtest.py, que se adapta a TIPO_MEDIA (como la página de SMA).
"""
import os
import runpy

runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "app_backtest.py"),
               init_globals={"TIPO_MEDIA": "ruptura"}, run_name="__main__")
