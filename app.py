"""App unica: reune el calculador de sesiones (XAU/USD) y el backtester de cruce de EMAs.

Cada pagina vive en su propio archivo; este solo arma el menu lateral.
Local:  streamlit run app.py   (o doble clic en abrir_app.bat)
Render: streamlit run app.py ...
"""
import streamlit as st
import streamlit.components.v1 as components

import ui_estilo

st.set_page_config(page_title="Trading: sesiones y backtester", page_icon="📈", layout="wide")

# Modo oscuro: el botón vive en la barra lateral y se recuerda en la URL (?tema=oscuro) al recargar.
if "oscuro" not in st.session_state:
    st.session_state["oscuro"] = st.query_params.get("tema") == "oscuro"
with st.sidebar:
    oscuro = st.toggle("🌙 Modo oscuro", key="oscuro")
if oscuro:
    st.query_params["tema"] = "oscuro"
elif "tema" in st.query_params:
    del st.query_params["tema"]
ui_estilo.set_tema("oscuro" if oscuro else "claro")
st.markdown(ui_estilo.css(), unsafe_allow_html=True)   # estilo común a todas las páginas

# Chrome traduce solo los textos si cree que la página está en otro idioma (ej. "High-Low" -> "Alto-Bajo").
# Se marca la página como español y "no traducir". Esto corre en la página que contiene a la app.
components.html(
    """<script>
    const d = window.parent.document;
    d.documentElement.setAttribute("lang", "es");
    d.documentElement.setAttribute("translate", "no");
    d.documentElement.classList.add("notranslate");
    if (!d.querySelector('meta[name="google"]')) {
      const m = d.createElement("meta"); m.name = "google"; m.content = "notranslate"; d.head.appendChild(m);
    }
    </script>""",
    height=0,
)

pagina = st.navigation([
    st.Page("pagina_sesiones.py", title="Sesiones XAU/USD", icon="📈", default=True),
    st.Page("app_backtest.py", title="Backtester EMA", icon="🧪"),
])
pagina.run()
