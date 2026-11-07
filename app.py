"""App unica: reune el calculador de sesiones (XAU/USD) y el backtester de cruce de EMAs.

Cada pagina vive en su propio archivo; este solo arma el menu lateral.
Local:  streamlit run app.py   (o doble clic en abrir_app.bat)
Render: streamlit run app.py ...
"""
import streamlit as st
import streamlit.components.v1 as components

import ui_estilo

st.set_page_config(page_title="ACPTester", page_icon="📈", layout="wide")

# Estilo (juego de colores) y modo noche: viven arriba de la barra lateral y se recuerdan en la URL
# (?estilo=pastel&tema=oscuro) al recargar.
if "estilo" not in st.session_state:
    _e = st.query_params.get("estilo")
    st.session_state["estilo"] = _e if _e in ui_estilo.ESTILOS else "moderno"
if "oscuro" not in st.session_state:
    st.session_state["oscuro"] = st.query_params.get("tema") == "oscuro"
# Los widgets viven en la barra lateral (o en la portada); el valor se lee de session_state, que ya trae lo elegido.
estilo = st.session_state["estilo"]
oscuro = st.session_state["oscuro"]
if estilo != "moderno":
    st.query_params["estilo"] = estilo
elif "estilo" in st.query_params:
    del st.query_params["estilo"]
if oscuro:
    st.query_params["tema"] = "oscuro"
elif "tema" in st.query_params:
    del st.query_params["tema"]
ui_estilo.set_tema("oscuro" if oscuro else "claro", estilo)
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
    // Posicion izquierda del contenido principal (cambia con la barra lateral abierta o cerrada): la usa el boton de la portada.
    const w = window.parent;
    if (!w.__mainxListo) {
      w.__mainxListo = true;
      w.setInterval(() => {
        const c = d.querySelector('[data-testid="stMainBlockContainer"]') || d.querySelector(".block-container");
        if (!c) return;
        const x = Math.round(c.getBoundingClientRect().left + parseFloat(w.getComputedStyle(c).paddingLeft || 0));
        if (d.documentElement.style.getPropertyValue("--mainx") !== x + "px") d.documentElement.style.setProperty("--mainx", x + "px");
      }, 250);
    }
    </script>""",
    height=0,
)

# Acordeón: en la barra lateral solo puede haber un menú abierto a la vez (al abrir uno se cierran los demás).
# Se apoya en la estructura interna de Streamlit (<details>/<summary>); si algún día cambia, los menús vuelven a ser independientes.
components.html(
    """<script>
    const d = window.parent.document, w = window.parent;
    if (!w.__acordeonListo) {
      w.__acordeonListo = true;
      let propio = false;
      d.addEventListener("click", (ev) => {
        if (propio) return;
        const sum = ev.target.closest && ev.target.closest("summary");
        const det = sum && sum.closest("details");
        const lado = det && det.closest('[data-testid="stSidebar"]');
        if (!lado || det.open) return;              // solo cuando se está ABRIENDO un menú de la barra lateral
        propio = true;
        lado.querySelectorAll("details[open]").forEach((o) => { if (o !== det) o.querySelector("summary").click(); });
        propio = false;
      }, true);
    }
    </script>""",
    height=0,
)

def _cambiar_modo():
    st.session_state["oscuro"] = not st.session_state["oscuro"]


def _controles_superiores():
    """Estilo y modo noche: dos botones redondos arriba a la derecha, en todas las páginas."""
    p = ui_estilo.TEMAS[ui_estilo.TEMA]
    st.markdown("""<style>
    [data-testid="stSidebarNav"]{display:none !important;}
    .st-key-ctl_top{position:fixed;top:.75rem;right:9.5rem;z-index:1000002;display:flex;flex-direction:row;gap:.55rem;width:auto;}
    .st-key-ctl_top [data-testid="stElementContainer"]{width:auto;}
    .st-key-ctl_top :is([data-testid="stPopover"],[data-testid="stButton"],[data-testid="stElementContainer"],.st-key-ctl_estilo){width:30px !important;min-width:30px !important;flex:none !important;}
    .st-key-ctl_top button{width:30px !important;min-width:30px !important;max-width:30px !important;height:30px !important;min-height:30px !important;padding:0 !important;border-radius:50% !important;border:1px solid @INBD@ !important;
      background:@CARD@ !important;box-shadow:0 2px 8px @SHADOW@;display:flex;align-items:center;justify-content:center;}
    .st-key-ctl_top button:hover{border-color:@ACC@ !important;transform:none;box-shadow:0 2px 8px @SHADOW@;}
    .st-key-ctl_top button :is(p,span,svg){color:@TXT@ !important;fill:@TXT@;}
    .st-key-ctl_estilo button{background:linear-gradient(135deg,@ACC@ 50%,@ORQ@ 50%) !important;}
    .st-key-ctl_estilo button *{display:none !important;}
    [data-testid="stSidebar"] [data-testid="stPageLink"] :is(a,p,span){color:@SIDETXT@ !important;font-weight:600;}
    .st-key-ctl_portada{position:fixed;top:.75rem;left:var(--mainx,3rem);z-index:1000002;width:30px !important;}
    .st-key-ctl_portada :is([data-testid="stElementContainer"],[data-testid="stPageLink"]){width:30px !important;min-width:30px !important;}
    .st-key-ctl_portada [data-testid="stPageLink"] a{display:flex;align-items:center;justify-content:center;width:30px;height:30px;min-height:30px;padding:0;
      border-radius:50%;border:1px solid @INBD@;background:@CARD@;box-shadow:0 2px 8px @SHADOW@;text-decoration:none;}
    .st-key-ctl_portada [data-testid="stPageLink"] a:hover{border-color:@ACC@;}
    .st-key-ctl_portada [data-testid="stPageLink"] a p{display:none !important;}
    .st-key-ctl_portada [data-testid="stPageLink"] a :is(span,svg){color:@TXT@ !important;fill:@TXT@;margin:0;}
    </style>""".replace("@INBD@", p["INBD"]).replace("@CARD@", p["CARD"]).replace("@SHADOW@", p["SHADOW"]).replace("@ACC@", p["INDIGO"])
        .replace("@SIDETXT@", p["SIDETXT"]).replace("@TXT@", p["TEXTO"]).replace("@ORQ@", p["ORQ"]), unsafe_allow_html=True)
    with st.container(key="ctl_top"):
        with st.container(key="ctl_estilo"):
            with st.popover("Estilo", help="Estilo de colores"):
                st.radio("Estilo", list(ui_estilo.ESTILOS), format_func=lambda k: ui_estilo.NOMBRES_ESTILO[k], key="estilo",
                         label_visibility="collapsed")
        st.button("", icon=":material/light_mode:" if st.session_state["oscuro"] else ":material/dark_mode:", key="ctl_modo",
                  on_click=_cambiar_modo, help="Modo claro" if st.session_state["oscuro"] else "Modo noche")


PAG = {
    "sesiones": st.Page("pagina_sesiones.py", title="Sesiones XAU/USD", icon="📈", url_path="sesiones"),
    "ema": st.Page("app_backtest.py", title="Backtester EMA", icon="🧪", url_path="ema"),
    "sma": st.Page("app_backtest_sma.py", title="Backtester SMA", icon="📐", url_path="sma"),
}


def portada():
    import pagina_portada
    pagina_portada.render({k: v.url_path for k, v in PAG.items()})


PORTADA = st.Page(portada, title="Portada", icon="🏠", url_path="portada", default=True)
pagina = st.navigation([PORTADA, *PAG.values()])
_controles_superiores()
if pagina is not PORTADA:
    st.markdown("<style>[data-testid='stMainBlockContainer'],[data-testid='stAppViewBlockContainer'],.block-container{padding-top:1.6rem !important;}</style>",
                unsafe_allow_html=True)       # el contenido sube: queda justo debajo de la fila de controles
    with st.sidebar, st.container(key="logo_acp"):    # logo en el espacio libre de arriba de la barra lateral (no ocupa lugar)
        st.markdown(ui_estilo.logo_acp(), unsafe_allow_html=True)
    with st.container(key="ctl_portada"):     # el menú de páginas se oculta: se vuelve a la portada desde este círculo (arriba a la izquierda)
        st.page_link(PORTADA, label="Portada", icon=":material/arrow_back:", help="Volver a la portada")
pagina.run()
