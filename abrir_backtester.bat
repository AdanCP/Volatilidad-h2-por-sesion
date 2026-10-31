@echo off
title Backtester EMA (MT5 FTMO)
cd /d "%~dp0"
echo Abri el terminal de MT5 de FTMO y deja la sesion iniciada.
echo Para cerrar el backtester, cerra esta ventana.
echo.
python -m streamlit run app_backtest.py
if errorlevel 1 (
  echo.
  echo Hubo un error. Si dice que falta streamlit o MetaTrader5, corre:
  echo   pip install streamlit pandas numpy tzdata MetaTrader5
  pause
)
