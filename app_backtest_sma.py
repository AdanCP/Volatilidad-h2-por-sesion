"""Página «Backtester SMA»: la misma pantalla que el backtester de EMA, con SMA y el modo «precio cruza una SMA».

No duplica código: define el tipo de media y ejecuta app_backtest.py, que se adapta a TIPO_MEDIA.
"""
import os
import runpy

runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "app_backtest.py"),
               init_globals={"TIPO_MEDIA": "sma"}, run_name="__main__")
