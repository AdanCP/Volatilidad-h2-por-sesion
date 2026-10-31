@echo off
title App de trading (sesiones + backtester)
cd /d "%~dp0"
echo Abri el terminal de MT5 de FTMO y deja la sesion iniciada (solo hace falta para el backtester).
echo Para cerrar la app, cerra esta ventana.
echo.
python -m streamlit run app.py
if errorlevel 1 (
  echo.
  echo Hubo un error. Si dice que falta streamlit o MetaTrader5, corre:
  echo   pip install streamlit pandas numpy tzdata yfinance MetaTrader5
  pause
)
