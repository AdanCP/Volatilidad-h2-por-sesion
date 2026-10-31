"""App unica: reune el calculador de sesiones (XAU/USD) y el backtester de cruce de EMAs.

Cada pagina vive en su propio archivo; este solo arma el menu lateral.
Local:  streamlit run app.py   (o doble clic en abrir_app.bat)
Render: streamlit run app.py ...
"""
import streamlit as st

st.set_page_config(page_title="Trading: sesiones y backtester", page_icon="📈", layout="wide")

pagina = st.navigation([
    st.Page("pagina_sesiones.py", title="Sesiones XAU/USD", icon="📈", default=True),
    st.Page("app_backtest.py", title="Backtester EMA", icon="🧪"),
])
pagina.run()
