"""Estilo y componentes visuales del dashboard (sin dependencias: HTML + SVG).

Todo devuelve texto HTML que se muestra con `st.html(...)`. No importa Streamlit, así que se
puede probar fuera de la app. Paleta: rosa -> violeta -> azul. Positivo = azul/violeta,
negativo = rosa, siempre acompañado de signo o flecha (no depende solo del color).
"""
import re
from html import escape as _e

# Cada estilo tiene su version clara y su version noche. Claves: ROSA = color de lo negativo; INDIGO = color de lo positivo;
# VIOLETA/MAGENTA/AZUL/ORQ/PROF = resto del degradado; SIDE/SIDETXT = barra lateral y su texto; VEIL/VEILB = velo de los
# elementos de la barra lateral (fondo y bordes); BTNTXT = texto sobre botones y barras de color; GLOW = brillo de los botones.
ESTILOS = {
    "moderno": {
        "claro": dict(ROSA="#ff4fa3", MAGENTA="#e63e9c", VIOLETA="#7c5cf0", INDIGO="#4c4fe0", AZUL="#2f3fd8", ORQ="#a355e8", PROF="#1b2a9e",
                      TEXTO="#1f2340", SUAVE="#7a7f9d", PISTA="#e7e9f7", GRID="#eceefa", EJE="#b9bcd8",
                      BG="#eef0fb", CARD="#ffffff", LINE="#eef0fb", HEAD="#f4f5fd", ND="#b0b4cc",
                      SHADOW="rgba(60,64,140,.10)", SHADOW2="rgba(60,64,140,.08)", INBG="#ffffff", INBD="#d9dcf3",
                      SIDE="linear-gradient(185deg,#4b3fd1 0%,#6a4fe6 55%,#8a63f2 100%)", SIDETXT="#ffffff",
                      VEIL="rgba(255,255,255,.10)", VEILB="rgba(255,255,255,.25)", BTNTXT="#ffffff", GLOW="rgba(124,92,240,.35)"),
        "oscuro": dict(ROSA="#ff5fae", MAGENTA="#f05fb0", VIOLETA="#9b82ff", INDIGO="#8b8fff", AZUL="#6b86ff", ORQ="#b778f0", PROF="#3a4bd0",
                       TEXTO="#eceefc", SUAVE="#9aa0c8", PISTA="#2a2e5a", GRID="#252952", EJE="#4a4f80",
                       BG="#0e1126", CARD="#181b3b", LINE="#262a52", HEAD="#20244d", ND="#5a5f8a",
                       SHADOW="rgba(0,0,0,.40)", SHADOW2="rgba(0,0,0,.30)", INBG="#10132d", INBD="#363c72",
                       SIDE="linear-gradient(185deg,#1d1858 0%,#2b2280 55%,#3d2f98 100%)", SIDETXT="#ffffff",
                       VEIL="rgba(255,255,255,.10)", VEILB="rgba(255,255,255,.25)", BTNTXT="#ffffff", GLOW="rgba(155,130,255,.35)"),
    },
    "sobrio": {
        "claro": dict(ROSA="#c0504d", MAGENTA="#b0454a", VIOLETA="#5a6f8a", INDIGO="#2f5d8a", AZUL="#1f4468", ORQ="#7a8aa3", PROF="#16324d",
                      TEXTO="#1f2933", SUAVE="#6b7785", PISTA="#e3e7ec", GRID="#e9edf1", EJE="#b8c0ca",
                      BG="#f1f3f6", CARD="#ffffff", LINE="#e9edf1", HEAD="#f5f7f9", ND="#b0b8c2",
                      SHADOW="rgba(31,41,51,.09)", SHADOW2="rgba(31,41,51,.07)", INBG="#ffffff", INBD="#d3d9e0",
                      SIDE="linear-gradient(185deg,#2b3340 0%,#343d4c 60%,#3d4859 100%)", SIDETXT="#ffffff",
                      VEIL="rgba(255,255,255,.08)", VEILB="rgba(255,255,255,.22)", BTNTXT="#ffffff", GLOW="rgba(47,93,138,.30)"),
        "oscuro": dict(ROSA="#e0706c", MAGENTA="#d4747f", VIOLETA="#8497b3", INDIGO="#6fa0d1", AZUL="#4f86bf", ORQ="#9aa9c0", PROF="#2f5d8a",
                       TEXTO="#e6e9ee", SUAVE="#98a2b0", PISTA="#2a313b", GRID="#252b34", EJE="#4b5563",
                       BG="#12151a", CARD="#1b2027", LINE="#2a313b", HEAD="#222831", ND="#5f6b7a",
                       SHADOW="rgba(0,0,0,.45)", SHADOW2="rgba(0,0,0,.33)", INBG="#14181e", INBD="#364050",
                       SIDE="linear-gradient(185deg,#0f1216 0%,#171b21 60%,#1e242c 100%)", SIDETXT="#e6e9ee",
                       VEIL="rgba(255,255,255,.07)", VEILB="rgba(255,255,255,.18)", BTNTXT="#ffffff", GLOW="rgba(111,160,209,.30)"),
    },
    "pastel": {                       # menta y durazno: verdes suaves con coral claro para lo negativo
        "claro": dict(ROSA="#ee8466", MAGENTA="#e57457", VIOLETA="#7cc9ae", INDIGO="#3fa07e", AZUL="#5aa7c7", ORQ="#f2c46d", PROF="#2f7d62",
                      TEXTO="#3b4a44", SUAVE="#6f8279", PISTA="#e5f1ea", GRID="#ebf4ee", EJE="#c3d4ca",
                      BG="#f4faf6", CARD="#ffffff", LINE="#ebf4ee", HEAD="#f2f9f5", ND="#b9c9c0",
                      SHADOW="rgba(80,130,105,.13)", SHADOW2="rgba(80,130,105,.10)", INBG="#ffffff", INBD="#d6e6dc",
                      SIDE="linear-gradient(185deg,#d6eee2 0%,#e4f3e9 50%,#fde8d8 100%)", SIDETXT="#3b4a44",
                      VEIL="rgba(255,255,255,.65)", VEILB="rgba(59,74,68,.20)", BTNTXT="#2f3d37", GLOW="rgba(63,160,126,.30)"),
        "oscuro": dict(ROSA="#ff9d85", MAGENTA="#f48d73", VIOLETA="#a6e0c8", INDIGO="#7fd6b0", AZUL="#82c4e0", ORQ="#f5d27f", PROF="#4aa586",
                       TEXTO="#e8f3ed", SUAVE="#9ab3a7", PISTA="#2d3d36", GRID="#27352f", EJE="#4f685c",
                       BG="#16201c", CARD="#1f2b26", LINE="#2b3a33", HEAD="#25332d", ND="#68857a",
                       SHADOW="rgba(0,0,0,.40)", SHADOW2="rgba(0,0,0,.30)", INBG="#18231f", INBD="#3a5247",
                       SIDE="linear-gradient(185deg,#1b2a24 0%,#22352c 55%,#2f3a2c 100%)", SIDETXT="#e8f3ed",
                       VEIL="rgba(255,255,255,.08)", VEILB="rgba(255,255,255,.20)", BTNTXT="#16201c", GLOW="rgba(127,214,176,.28)"),
    },
    "oceano": {
        "claro": dict(ROSA="#ef6f6c", MAGENTA="#e5575f", VIOLETA="#2aa6a0", INDIGO="#0f7f9e", AZUL="#0b5d8a", ORQ="#4bb5c9", PROF="#073f63",
                      TEXTO="#12323f", SUAVE="#6a8794", PISTA="#dcecf0", GRID="#e6f1f4", EJE="#aac4cc",
                      BG="#eef6f8", CARD="#ffffff", LINE="#e6f1f4", HEAD="#f2f9fb", ND="#a5bcc4",
                      SHADOW="rgba(11,93,138,.11)", SHADOW2="rgba(11,93,138,.08)", INBG="#ffffff", INBD="#cfe2e8",
                      SIDE="linear-gradient(185deg,#0b4f6c 0%,#0e6f8a 55%,#12808f 100%)", SIDETXT="#ffffff",
                      VEIL="rgba(255,255,255,.10)", VEILB="rgba(255,255,255,.25)", BTNTXT="#ffffff", GLOW="rgba(15,127,158,.35)"),
        "oscuro": dict(ROSA="#ff7f7a", MAGENTA="#f0707c", VIOLETA="#43c9b8", INDIGO="#4fc3dc", AZUL="#3aa0d6", ORQ="#68d6e6", PROF="#1b6fa3",
                       TEXTO="#e3f2f6", SUAVE="#8fb0bb", PISTA="#1c3a46", GRID="#183440", EJE="#3d6372",
                       BG="#0a1a22", CARD="#10262f", LINE="#1c3a46", HEAD="#15303b", ND="#52798a",
                       SHADOW="rgba(0,0,0,.42)", SHADOW2="rgba(0,0,0,.32)", INBG="#0b1d25", INBD="#2a5365",
                       SIDE="linear-gradient(185deg,#06222d 0%,#08303e 55%,#0b4152 100%)", SIDETXT="#e3f2f6",
                       VEIL="rgba(255,255,255,.08)", VEILB="rgba(255,255,255,.20)", BTNTXT="#06222d", GLOW="rgba(79,195,220,.30)"),
    },
    "atardecer": {
        "claro": dict(ROSA="#c0264f", MAGENTA="#d44a6a", VIOLETA="#8a3f7a", INDIGO="#d9701a", AZUL="#b8530f", ORQ="#e8a13a", PROF="#8a3a08",
                      TEXTO="#3a2430", SUAVE="#94787f", PISTA="#f6e4da", GRID="#f9ece4", EJE="#d9bfb0",
                      BG="#fdf3ec", CARD="#ffffff", LINE="#f9ece4", HEAD="#fdf6f1", ND="#cdb5a8",
                      SHADOW="rgba(160,80,60,.12)", SHADOW2="rgba(160,80,60,.09)", INBG="#ffffff", INBD="#efd7c8",
                      SIDE="linear-gradient(185deg,#6b2340 0%,#a53a3a 55%,#c85a1f 100%)", SIDETXT="#ffffff",
                      VEIL="rgba(255,255,255,.10)", VEILB="rgba(255,255,255,.25)", BTNTXT="#ffffff", GLOW="rgba(217,98,43,.35)"),
        "oscuro": dict(ROSA="#ff6b8a", MAGENTA="#f0607f", VIOLETA="#d98ab8", INDIGO="#ffa04d", AZUL="#ff8a3d", ORQ="#ffc166", PROF="#c4551b",
                       TEXTO="#f6e8e2", SUAVE="#b79a98", PISTA="#432a2e", GRID="#392327", EJE="#6b4b4c",
                       BG="#1c1214", CARD="#2a1a1d", LINE="#3f282c", HEAD="#331f23", ND="#7d5e5e",
                       SHADOW="rgba(0,0,0,.45)", SHADOW2="rgba(0,0,0,.33)", INBG="#211416", INBD="#5a3a3d",
                       SIDE="linear-gradient(185deg,#2a0f1c 0%,#4a1a2a 55%,#6b2a22 100%)", SIDETXT="#f6e8e2",
                       VEIL="rgba(255,255,255,.08)", VEILB="rgba(255,255,255,.20)", BTNTXT="#2a1014", GLOW="rgba(255,160,77,.30)"),
    },
}
# degradado de los botones principales (por defecto, del color de lo negativo al violeta)
_BOTONES = {("pastel", "claro"): ("#f5a58a", "#7cc9ae"), ("pastel", "oscuro"): ("#ff9d85", "#7fd6b0"),
            ("sobrio", "claro"): ("#2f5d8a", "#5a6f8a"), ("sobrio", "oscuro"): ("#4f86bf", "#6f8aa8"),
            ("oceano", "claro"): ("#0f7f9e", "#2aa6a0"), ("oceano", "oscuro"): ("#4fc3dc", "#43c9b8"),
            ("atardecer", "claro"): ("#d9701a", "#c0264f"), ("atardecer", "oscuro"): ("#ffa04d", "#ff6b8a")}
for _e_, _modos in ESTILOS.items():
    for _m_, _p_ in _modos.items():
        _c1, _c2 = _BOTONES.get((_e_, _m_), (_p_["ROSA"], _p_["VIOLETA"]))
        _p_["BTNG"] = f"linear-gradient(90deg,{_c1},{_c2})"
NOMBRES_ESTILO = {"moderno": "Moderno", "sobrio": "Sobrio", "pastel": "Pastel", "oceano": "Océano", "atardecer": "Atardecer"}
ESTILO = "moderno"
TEMAS = dict(ESTILOS["moderno"])           # paleta clara/oscura del estilo activo (set_tema la actualiza)
TEMA = "claro"
ROSA = MAGENTA = VIOLETA = INDIGO = AZUL = ORQ = TEXTO = SUAVE = PISTA = GRID = EJE = POS = NEG = ""


def set_tema(nombre: str = "claro", estilo: str = None) -> str:
    """Cambia la paleta de los componentes (colores de los gráficos y del CSS). `nombre` es el modo ("claro" o "oscuro",
    este último es el modo noche) y `estilo` el juego de colores (ver ESTILOS). Es global del proceso: se llama una vez
    por ejecución, al comienzo de app.py."""
    global ESTILO, TEMA, ROSA, MAGENTA, VIOLETA, INDIGO, AZUL, ORQ, TEXTO, SUAVE, PISTA, GRID, EJE, POS, NEG
    if estilo is not None:
        ESTILO = estilo if estilo in ESTILOS else "moderno"
        TEMAS.clear()
        TEMAS.update(ESTILOS[ESTILO])
    TEMA = nombre if nombre in TEMAS else "claro"
    p = TEMAS[TEMA]
    ROSA, MAGENTA, VIOLETA, INDIGO, AZUL, ORQ = p["ROSA"], p["MAGENTA"], p["VIOLETA"], p["INDIGO"], p["AZUL"], p["ORQ"]
    TEXTO, SUAVE, PISTA, GRID, EJE = p["TEXTO"], p["SUAVE"], p["PISTA"], p["GRID"], p["EJE"]
    POS, NEG = INDIGO, ROSA
    return TEMA


set_tema("claro", "moderno")

# Poné False si la barra lateral de color no se ve bien en tu versión de Streamlit.
SIDEBAR_MORADO = True


def n(x, dec=2, signo=False) -> str:
    """Número con formato español (1.234,56)."""
    try:
        s = f"{float(x):,.{dec}f}"
    except (TypeError, ValueError):
        return "–"
    s = s.replace(",", "§").replace(".", ",").replace("§", ".")
    return ("+" + s if signo and float(x) > 0 else s)


def tono(x) -> str:
    return POS if (x or 0) >= 0 else NEG


# ------------------------------------------------------------------------------- CSS
_CSS_NATIVOS = """/* widgets nativos: colores forzados para que no dependan del tema de Streamlit ni del navegador */
[data-testid="stMain"] :is(h1,h2,h3,h4,h5,h6){color:@TXT@ !important;}
[data-testid="stMain"] [data-testid="stMarkdownContainer"] :is(p,li,span,strong,em,code,h1,h2,h3,h4){color:@TXT@ !important;}
[data-testid="stMain"] [data-testid="stWidgetLabel"] p,[data-testid="stMain"] label p,[data-testid="stMain"] label span{color:@TXT@ !important;}
[data-testid="stMain"] [data-testid="stCaptionContainer"] p{color:@MUTED@ !important;}
[data-baseweb="input"]>div,[data-baseweb="base-input"],[data-baseweb="select"]>div,[data-baseweb="textarea"]{background:@INBG@ !important;border-color:@INBD@ !important;}
[data-baseweb="input"] input,[data-baseweb="base-input"] input,textarea{color:@TXT@ !important;-webkit-text-fill-color:@TXT@ !important;}
[data-baseweb="select"] div,[data-baseweb="select"] span{color:@TXT@ !important;}
[data-baseweb="popover"] ul,[data-baseweb="popover"] [role="listbox"],[data-baseweb="menu"]{background:@CARD@ !important;}
[data-baseweb="popover"] li,[data-baseweb="popover"] li *{color:@TXT@ !important;}
[data-testid="stNumberInput"] :is([data-testid="stNumberInputStepUp"],[data-testid="stNumberInputStepDown"]){background:@INBG@ !important;color:@TXT@ !important;}
[data-testid="stMain"] [data-testid="stNumberInput"] :is(input,[data-baseweb="input"],[data-baseweb="base-input"],[data-testid="stNumberInputContainer"]){background:@INBG@ !important;color:@ACC@ !important;-webkit-text-fill-color:@ACC@ !important;font-weight:800;}
[data-testid="stMain"] [data-testid="stNumberInput"] [data-baseweb="input"]{border:1.5px solid @VIO@ !important;border-radius:12px !important;overflow:hidden;box-shadow:0 2px 10px rgba(124,92,240,.16);}
[data-testid="stMain"] [data-testid="stNumberInput"] :is([data-testid="stNumberInputStepUp"],[data-testid="stNumberInputStepDown"]){background:linear-gradient(135deg,@ACC@,@VIO@) !important;color:@BTNTXT@ !important;border:0 !important;border-left:1px solid rgba(255,255,255,.35) !important;border-radius:0 !important;}
[data-testid="stMain"] [data-testid="stNumberInput"] :is([data-testid="stNumberInputStepUp"],[data-testid="stNumberInputStepDown"]) :is(svg,path){fill:@BTNTXT@ !important;color:@BTNTXT@ !important;}
[data-testid="stMain"] [data-testid="stNumberInput"] :is([data-testid="stNumberInputStepUp"],[data-testid="stNumberInputStepDown"]):hover{filter:brightness(1.12) saturate(1.1);}
[data-testid="stFileUploaderDropzone"]{background:@INBG@ !important;}
[data-testid="stFileUploaderDropzone"] :is(span,small,p,div){color:@TXT@ !important;}
[data-testid="stExpander"] summary :is(p,span){color:@TXT@ !important;}
[data-testid="stMain"] [data-testid="stExpander"] :is(details,summary){background:@CARD@ !important;}
[data-testid="stAlert"] :is(p,div,span){color:@TXT@ !important;}"""

_CSS_SIDEBAR = """
[data-testid="stSidebar"]{background:@SIDE@;}
[data-testid="stSidebar"] :is(h1,h2,h3),
[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p,
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] p,
[data-testid="stSidebar"] [data-testid="stRadio"] label p,
[data-testid="stSidebar"] [data-testid="stCheckbox"] label p,
[data-testid="stSidebar"] label :is(p,span),
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] > p{color:@SIDETXT@ !important;}
[data-testid="stSidebar"] h2{font-size:1.05rem;letter-spacing:.02em;text-transform:uppercase;
  border-bottom:1px solid @VEILB@;padding-bottom:.35rem;margin-top:.6rem;}
[data-testid="stSidebar"] [data-testid="stExpander"]{background:@VEIL@;box-shadow:none;
  border:1px solid @VEILB@;border-radius:14px;}
[data-testid="stSidebar"] [data-testid="stExpander"] summary{padding:.55rem .8rem;}
/* los menús se levantan un poco al pasar el mouse por el título (sin cambiar color ni líneas) */
[data-testid="stSidebar"] [data-testid="stExpander"]{transition:transform .15s;}
[data-testid="stSidebar"] [data-testid="stExpander"]:has(> details > summary:hover){transform:translateY(-2px);}
[data-testid="stSidebar"] [data-testid="stExpander"] summary :is(p,span){color:@SIDETXT@ !important;font-weight:700;}
[data-testid="stSidebar"] [data-testid="stExpander"] summary svg{fill:@SIDETXT@;color:@SIDETXT@;}
[data-testid="stSidebar"] .sep-filtro{border-top:1px solid rgba(255,255,255,.35);margin:-.15rem 0;}
.fte{font-size:1.05rem;font-weight:800;letter-spacing:.02em;text-transform:uppercase;color:@SIDETXT@ !important;
  border-top:1px solid @VEILB@;padding-top:.7rem;margin-top:.4rem;}
.fte-fin{border-bottom:1px solid @VEILB@;margin:.2rem 0 .7rem;}
[data-testid="stSidebar"] :is([data-testid="stDownloadButton"],[data-testid="stButton"]) button{
  background:@BTNG@ !important;border:0 !important;border-radius:12px;
  box-shadow:0 4px 14px @GLOW@;}
[data-testid="stSidebar"] :is([data-testid="stDownloadButton"],[data-testid="stButton"]) button :is(p,span,div){
  color:@BTNTXT@ !important;font-weight:700;}
[data-testid="stSidebar"] [data-testid="stButton"] button:disabled{opacity:.45;box-shadow:none;cursor:not-allowed;}
[data-testid="stSidebar"] :is([data-testid="stDownloadButton"],[data-testid="stButton"]) button:not(:disabled):hover{
  filter:brightness(1.2) saturate(1.12);transform:translateY(-2px);
  box-shadow:0 0 0 3px @SIDETXT@,0 0 22px 6px @GLOW@;}
/* «Guardar configuración» (iframe con el cuadro «Guardar como»): se compensa el aire para la sombra */
[data-testid="stSidebar"] .st-key-cfg_guardar iframe{display:block;width:calc(100% + 36px) !important;margin:-20px -18px -22px;color-scheme:normal !important;background:transparent !important;}
/* «Cargar configuración»: el contenedor del selector es el botón (alto fijo, igual al de guardar); el selector real
   queda encima, invisible, para recibir el clic y los archivos arrastrados */
[data-testid="stSidebar"] .st-key-cfg_cargar [data-testid="stFileUploader"]{
  position:relative;height:2.5rem !important;min-height:2.5rem !important;box-sizing:border-box;overflow:hidden;
  padding:0 !important;margin:0 !important;background:@BTNG@ !important;border:1px solid rgba(255,255,255,.55);border-radius:12px;box-shadow:0 4px 14px @GLOW@;
  display:flex;align-items:center;justify-content:center;cursor:pointer;
  transition:filter .15s,transform .15s,box-shadow .15s;}
[data-testid="stSidebar"] .st-key-cfg_cargar [data-testid="stFileUploader"]::before{
  content:"📂 Cargar configuración";color:@BTNTXT@;font-family:"Source Sans","Source Sans Pro",sans-serif;
  font-weight:700;font-size:.9rem;line-height:1.6;pointer-events:none;}
[data-testid="stSidebar"] .st-key-cfg_cargar [data-testid="stFileUploader"] [data-testid="stFileUploaderDropzone"]{
  position:absolute !important;inset:0;width:100%;height:100%;opacity:0;cursor:pointer;}
[data-testid="stSidebar"] .st-key-cfg_cargar [data-testid="stFileUploader"] :is(label,[data-testid="stWidgetLabel"],
  [data-testid="stFileUploaderFile"],[data-testid="stFileUploaderFileList"]){display:none !important;}
[data-testid="stSidebar"] .st-key-cfg_cargar [data-testid="stFileUploader"]:hover{
  filter:brightness(1.2) saturate(1.12);transform:translateY(-2px);box-shadow:0 0 0 2px @SIDETXT@,0 3px 8px @GLOW@;}
/* «Generar bot»: es la acción final, va más grande y con más peso */
[data-testid="stSidebar"] .st-key-bot_gen :is([data-testid="stDownloadButton"],[data-testid="stButton"]) button{
  min-height:3.8rem;border-radius:14px;border:1px solid rgba(255,255,255,.55) !important;box-shadow:0 8px 24px @GLOW@;}
[data-testid="stSidebar"] .st-key-bot_gen :is([data-testid="stDownloadButton"],[data-testid="stButton"]) button:not(:disabled):hover{
  box-shadow:0 0 0 2px @SIDETXT@,0 4px 14px @GLOW@;}
[data-testid="stSidebar"] .st-key-bot_gen button :is(p,span,div){font-size:1.2rem;font-weight:800;letter-spacing:.01em;}
/* «Guía de cada campo»: un acceso discreto (fila de texto con flecha), no un botón */
[data-testid="stSidebar"] .st-key-guia_dl [data-testid="stDownloadButton"] button{
  background:transparent !important;border:0 !important;box-shadow:none !important;min-height:0;height:auto;padding:.3rem .15rem;
  justify-content:flex-start;gap:.5rem;opacity:.7;}
[data-testid="stSidebar"] .st-key-guia_dl [data-testid="stDownloadButton"] button:not(:disabled):hover{
  filter:none;transform:none;box-shadow:none !important;opacity:1;background:@VEIL@ !important;}
[data-testid="stSidebar"] .st-key-guia_dl [data-testid="stDownloadButton"] button :is(p,span,div){
  font-size:.86rem !important;font-weight:500 !important;color:@SIDETXT@ !important;}
[data-testid="stSidebar"] .st-key-guia_dl [data-testid="stDownloadButton"] button::after{
  content:"↗";margin-left:auto;font-size:.86rem;opacity:.65;}
/* boton para volver a abrir la barra lateral cuando esta contraida: visible sobre el fondo claro, con el estilo de los circulos de arriba */
:is([data-testid="stExpandSidebarButton"],[data-testid="stSidebarCollapsedControl"] button,[data-testid="collapsedControl"] button){
  background:@CARD@ !important;border:1px solid @INBD@ !important;border-radius:50% !important;box-shadow:0 2px 8px @SHADOW@;}
:is([data-testid="stExpandSidebarButton"],[data-testid="stSidebarCollapsedControl"] button,[data-testid="collapsedControl"] button) :is(span,svg,p){
  color:@ACC@ !important;fill:@ACC@;opacity:1 !important;}
:is([data-testid="stExpandSidebarButton"],[data-testid="stSidebarCollapsedControl"] button,[data-testid="collapsedControl"] button):hover{border-color:@ACC@ !important;}
/* logo de ACPTester: ocupa el espacio libre de arriba de la barra lateral, fuera del flujo (no mueve nada) */
[data-testid="stSidebarContent"]{position:relative;}
[data-testid="stSidebar"] .st-key-logo_acp{position:absolute;top:1.4rem;left:1.7rem;width:auto;z-index:1;pointer-events:none;}
[data-testid="stSidebar"] .st-key-logo_acp *{color:#fff !important;}
.logo-acp{display:flex;align-items:center;gap:13px;}
.logo-acp .nom{font-size:27px;line-height:1;white-space:nowrap;}
.logo-acp .nom b{font-weight:800;letter-spacing:-.02em;}.logo-acp .nom span{font-weight:300;letter-spacing:-.01em;}
.logo-acp .lema{font-size:10.5px;margin-top:5px;letter-spacing:.04em;opacity:.85;white-space:nowrap;}
[data-testid="stSidebarNav"] a{border-radius:10px;}
[data-testid="stSidebarNav"] a span{color:@SIDETXT@ !important;}
[data-testid="stSidebarNav"] a[aria-current="page"]{background:@VEILB@;}
"""

CSS = """<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
html,body,[class*="css"],.stApp{font-family:'Inter',system-ui,sans-serif;}
.stApp{background:@BG@;}
.block-container{padding-top:1.6rem;max-width:1280px;}
header[data-testid="stHeader"]{background:transparent;}
h1,h2,h3{color:@TXT@;letter-spacing:-.01em;}
/* tarjetas: los contenedores con borde pasan a ser tarjetas blancas */
[data-testid="stVerticalBlockBorderWrapper"]{background:@CARD@;border:0 !important;border-radius:18px;
  box-shadow:0 6px 22px @SHADOW@;padding:.35rem .35rem;}
/* botones */
button[kind="primary"],[data-testid="stBaseButton-primary"]{background:@BTNG@;
  border:0;color:@BTNTXT@;border-radius:12px;font-weight:600;box-shadow:0 6px 16px @GLOW@;}
button[kind="secondary"],[data-testid="stBaseButton-secondary"]{border-radius:12px;border:1px solid @INBD@;
  background:@CARD@;color:@ACC@;font-weight:600;}
.stButton>button{width:100%;padding:.55rem 1rem;}
.stButton>button,.stDownloadButton>button{transition:filter .15s,transform .15s,box-shadow .15s,background .15s,border-color .15s;}
button[kind="primary"]:hover,[data-testid="stBaseButton-primary"]:hover{filter:brightness(1.18) saturate(1.12);transform:translateY(-2px);
  box-shadow:0 0 0 3px @CARD@,0 0 0 6px @NEG@,0 12px 26px @GLOW@;}
button[kind="secondary"]:hover,[data-testid="stBaseButton-secondary"]:hover{background:@HEAD@;border-color:@ACC@;color:@ACC@;
  transform:translateY(-2px);box-shadow:0 0 0 3px @CARD@,0 0 0 5px @ACC@,0 10px 22px @SHADOW@;}
button:active{transform:translateY(0);filter:brightness(.97);}
/* fila de acciones del backtester: botones secundarios con borde degradé, a juego con «Correr backtest» */
.st-key-fila_bt button[kind="secondary"],.st-key-fila_bt [data-testid="stBaseButton-secondary"],
.st-key-fila_bt_pdf button[kind="secondary"],.st-key-fila_bt_pdf [data-testid="stBaseButton-secondary"]{
  border:1.5px solid transparent !important;border-radius:12px;
  background:linear-gradient(@CARD@,@CARD@) padding-box,@BTNG@ border-box !important;
  box-shadow:0 4px 14px @GLOW@;min-height:2.6rem;}
.st-key-fila_bt button[kind="secondary"] :is(p,span,div),.st-key-fila_bt_pdf button[kind="secondary"] :is(p,span,div){color:@ACC@ !important;font-weight:700;white-space:normal;line-height:1.2;}
.st-key-fila_bt button[kind="secondary"]:not(:disabled):hover,.st-key-fila_bt_pdf button[kind="secondary"]:not(:disabled):hover{
  background:@BTNG@ border-box !important;transform:translateY(-2px);filter:brightness(1.12) saturate(1.1);
  box-shadow:0 0 0 3px @CARD@,0 0 0 5px @ACC@,0 10px 22px @GLOW@;}
.st-key-fila_bt button[kind="secondary"]:not(:disabled):hover :is(p,span,div),.st-key-fila_bt_pdf button[kind="secondary"]:not(:disabled):hover :is(p,span,div){color:@BTNTXT@ !important;}
.st-key-fila_bt button[kind="secondary"]:disabled{opacity:.5;box-shadow:none;cursor:not-allowed;}
[data-testid="stDataFrame"]{border-radius:12px;overflow:hidden;}
[data-testid="stExpander"]{background:@CARD@;border-radius:14px;border:0;box-shadow:0 4px 16px @SHADOW2@;}
/* componentes propios */
.tb{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px;margin:0 0 14px;}
.tb h1{margin:0;font-size:1.7rem;font-weight:800;color:@TXT@;}
.tb .sub{color:@MUTED@;font-size:.9rem;margin-top:2px;}
.st-key-fila_bt_pdf{margin-bottom:14px;}
/* banda de titulo de la pantalla de inicio */
.hero{position:relative;overflow:hidden;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:14px;margin:-3.3rem 0 18px;
  padding:26px 30px;border-radius:22px;background:@SIDE@;box-shadow:@HEROSH@;}
.hero:after{content:"";position:absolute;right:-120px;top:-120px;width:430px;height:430px;border-radius:50%;background:rgba(255,255,255,.10);pointer-events:none;}
.hero>*{position:relative;z-index:1;}
[data-testid="stMain"] .hero.hero h1{margin:0;font-size:2.6rem;font-weight:800;letter-spacing:-.03em;line-height:1.08;color:#fff !important;}
[data-testid="stMain"] .hero.hero .sub{color:rgba(255,255,255,.84) !important;font-size:.95rem;margin-top:6px;max-width:760px;}
[data-testid="stMain"] .hero.hero .chip{background:rgba(255,255,255,.16);box-shadow:none;border:1px solid rgba(255,255,255,.28);color:#fff !important;}
[data-testid="stMain"] .hero.hero .chip b{color:#fff !important;}
.chips{display:flex;gap:8px;flex-wrap:wrap;}
.chip{background:@CARD@;border-radius:999px;padding:6px 14px;font-size:.78rem;font-weight:600;color:@ACC@;
  box-shadow:0 3px 10px @SHADOW@;white-space:nowrap;}
.chip b{color:@TXT@;}
.eqp .top{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;}
.eqp .top h4{margin:0;}
.eqp .pills{display:flex;gap:8px;flex-wrap:wrap;}
.eqp .pill{border-radius:999px;padding:5px 13px;font-size:.76rem;font-weight:600;color:@BTNTXT@;white-space:nowrap;}
.eqp table{width:100%;border-collapse:collapse;margin-top:14px;font-size:.84rem;}
.eqp th{text-align:right;font-weight:600;font-size:.72rem;color:@MUTED@;padding:6px 10px;border-bottom:1px solid @LINE@;}
.eqp td{text-align:right;padding:8px 10px;border-top:1px solid @LINE@;font-variant-numeric:tabular-nums;font-weight:600;}
.eqp tbody tr:first-child td{border-top:0;}
.eqp th:first-child,.eqp td:first-child{text-align:left;}
.eqp td:first-child{color:@ACC@;font-weight:700;}
.eqp td.sl{color:@NEG@;} .eqp td.tp{color:@ACC@;}
.card{background:@CARD@;border-radius:18px;box-shadow:0 6px 22px @SHADOW@;padding:16px 18px;height:100%;box-sizing:border-box;}
.card h4{margin:0 0 10px;font-size:.92rem;font-weight:700;color:@TXT@;display:flex;justify-content:space-between;align-items:center;}
.card h4 small{font-weight:500;color:@MUTED@;font-size:.74rem;}
/* dos tarjetas lado a lado (curva de equity y medidor): misma altura aunque el texto de una sea más largo */
.st-key-par_equity [data-testid="stHorizontalBlock"]{align-items:stretch;}
.st-key-par_equity [data-testid="stColumn"]{display:flex;flex-direction:column;}
.st-key-par_equity [data-testid="stColumn"]>div,.st-key-par_equity [data-testid="stColumn"] [data-testid="stVerticalBlock"],
.st-key-par_equity [data-testid="stColumn"] [data-testid="stElementContainer"],.st-key-par_equity [data-testid="stColumn"] [data-testid="stHtml"]{flex:1 1 auto;height:100%;}
.kpi{position:relative;overflow:hidden;}
.kpi .lab{color:@MUTED@;font-size:.74rem;font-weight:600;text-transform:uppercase;letter-spacing:.05em;}
.kpi .val{font-size:1.85rem;font-weight:800;line-height:1.15;margin:4px 0 2px;}
.kpi .sub{color:@MUTED@;font-size:.78rem;}
.kpi .bar{position:absolute;left:0;top:0;bottom:0;width:5px;}
.cargando{display:flex;align-items:center;gap:14px;padding:14px 6px;}
.cargando .txt{color:@TXT@;font-weight:600;font-size:.95rem;}
.anillo-carga{width:34px;height:34px;border-radius:50%;flex:none;
  background:conic-gradient(from 0deg,transparent,@NEG@ 40%,@VIO@ 85%,@ACC@);
  -webkit-mask:radial-gradient(farthest-side,transparent calc(100% - 5px),#000 calc(100% - 4px));
  mask:radial-gradient(farthest-side,transparent calc(100% - 5px),#000 calc(100% - 4px));
  animation:giro-carga 1.2s linear infinite;}
@keyframes giro-carga{to{transform:rotate(360deg);}}
.ring{display:flex;flex-direction:column;align-items:center;text-align:center;}
.ring .t{font-weight:700;font-size:.85rem;margin-top:4px;color:@TXT@;}
.ring .s{font-size:.74rem;color:@MUTED@;margin-top:2px;line-height:1.35;}
.rows .r{display:grid;grid-template-columns:170px 1fr 72px;gap:10px;align-items:center;margin:9px 0;font-size:.8rem;}
.rows .r .nm{font-weight:600;color:@TXT@;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
.rows .r .v{text-align:right;font-weight:700;font-variant-numeric:tabular-nums;}
.track{position:relative;height:11px;border-radius:99px;background:@TRACK@;}
.track .c{position:absolute;left:50%;top:-3px;bottom:-3px;width:1px;background:@EJE@;}
.track .f{position:absolute;top:0;bottom:0;border-radius:99px;}
.emb .e{box-sizing:border-box;margin:8px auto;border-radius:12px;color:@BTNTXT@;padding:9px 14px;display:flex;justify-content:space-between;
  font-weight:600;font-size:.82rem;box-shadow:0 4px 12px @GLOW@;}
.emb .e span:last-child{font-weight:800;}
.ra{margin-bottom:9px;}
.ra .rl{display:flex;justify-content:space-between;font-size:.86rem;font-weight:600;color:@TXT@;}
.ra .rv{font-weight:800;}
.ra .trk{background:@TRACK@;border-radius:8px;height:13px;margin-top:3px;overflow:hidden;}
.ra .trk div{height:100%;border-radius:8px;}
.ra .rp{font-size:.7rem;color:@MUTED@;margin-top:1px;}
.insight{background:linear-gradient(120deg,@ACC@,@AZ@);color:@BTNTXT@;border-radius:18px;padding:16px 20px;
  box-shadow:0 8px 24px @GLOW@;font-size:.9rem;line-height:1.55;}
.insight b{color:@BTNTXT@;}
.insight .tt{font-weight:800;letter-spacing:.04em;text-transform:uppercase;font-size:.72rem;opacity:.85;margin-bottom:4px;}
.note{color:@MUTED@;font-size:.78rem;line-height:1.5;margin-top:6px;}
.tbl{overflow:auto;border-radius:12px;}
.tbl table{border-collapse:collapse;width:100%;font-size:.84rem;font-variant-numeric:tabular-nums;}
.tbl th{position:sticky;top:0;background:@HEAD@;color:@MUTED@;font-weight:700;font-size:.72rem;text-transform:uppercase;letter-spacing:.05em;text-align:right;padding:9px 12px;}
.tbl th:first-child,.tbl td:first-child{text-align:left;font-weight:600;color:@TXT@;}
.tbl td{padding:8px 12px;text-align:right;color:@TXT@;border-top:1px solid @LINE@;}
.tbl td.hit{background:rgba(124,92,240,.14);color:@ACC@;font-weight:700;}
.tbl td.pos{color:@ACC@;font-weight:700;}
.tbl td.neg{color:@NEG@;font-weight:700;}
.tbl td.nd{color:@ND@;}
@NATIVOS@
.sec{margin:8px 0 10px;}
.sec h3{margin:0;font-size:1.3rem;font-weight:800;color:@TXT@;letter-spacing:-.01em;}
.sec .sub{color:@MUTED@;font-size:.86rem;margin-top:2px;}
svg text{font-family:'Inter',system-ui,sans-serif;}
</style>"""


def css() -> str:
    """CSS completo con la paleta del tema actual. Sin líneas en blanco: Markdown corta el bloque HTML en la primera."""
    p = TEMAS[TEMA]
    out = CSS.replace("@NATIVOS@", _CSS_NATIVOS)
    if SIDEBAR_MORADO:
        out = out.replace("</style>", _CSS_SIDEBAR + "</style>")
    fichas = {"@BG@": p["BG"], "@CARD@": p["CARD"], "@TXT@": p["TEXTO"], "@MUTED@": p["SUAVE"], "@TRACK@": p["PISTA"],
              "@LINE@": p["LINE"], "@HEAD@": p["HEAD"], "@ND@": p["ND"], "@EJE@": p["EJE"], "@SHADOW@": p["SHADOW"],
              "@SHADOW2@": p["SHADOW2"], "@INBG@": p["INBG"], "@INBD@": p["INBD"], "@ACC@": p["INDIGO"],
              "@NEG@": p["ROSA"], "@VIO@": p["VIOLETA"], "@SIDE@": p["SIDE"], "@AZ@": p["AZUL"], "@SIDETXT@": p["SIDETXT"],
              "@VEIL@": p["VEIL"], "@VEILB@": p["VEILB"], "@BTNTXT@": p["BTNTXT"], "@BTNG@": p["BTNG"], "@GLOW@": p["GLOW"]}
    # brillo de la banda del título: igual que siempre en tema claro; en noche, mucho más difuso y con la mitad de intensidad
    if TEMA == "oscuro":
        suave = re.sub(r"(rgba\([^)]*,)\s*([0-9.]+)\)", lambda m: f"{m.group(1)}{float(m.group(2)) / 2:.2f})", p["GLOW"])
        fichas["@HEROSH@"] = f"0 22px 70px -6px {suave}"
    else:
        fichas["@HEROSH@"] = f"0 14px 34px {p['GLOW']}"
    for k, v in fichas.items():
        out = out.replace(k, v)
    return "\n".join(l for l in out.split("\n") if l.strip())


def _como_img(svg: str, estilo: str = "width:100%;height:auto") -> str:
    """Devuelve el SVG como <img> con data-URI. st.html limpia el HTML y suele eliminar <svg> en línea;
    una imagen con data-URI sí se conserva y se ve igual."""
    import base64
    if "xmlns=" not in svg:
        svg = svg.replace("<svg ", '<svg xmlns="http://www.w3.org/2000/svg" font-family="Inter,Segoe UI,Arial,sans-serif" ', 1)
    b64 = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f'<img alt="" style="display:block;{estilo}" src="data:image/svg+xml;base64,{b64}">'


# ------------------------------------------------------------------------ componentes
def barra_superior(titulo: str, subtitulo: str, chips: list) -> str:
    cs = "".join(f'<span class="chip">{_e(k)}: <b>{_e(str(v))}</b></span>' for k, v in chips)
    return (f'<div class="tb"><div><h1>{_e(titulo)}</h1><div class="sub">{_e(subtitulo)}</div></div>'
            f'<div class="chips">{cs}</div></div>')


def banda_titulo(titulo: str, subtitulo: str, chips: list) -> str:
    """Titulo de la pantalla de inicio: banda de color (la de la barra lateral) con el titulo grande, el subtitulo y los chips."""
    cs = "".join(f'<span class="chip">{_e(k)}: <b>{_e(str(v))}</b></span>' for k, v in chips)
    return (f'<div class="hero"><div><h1>{_e(titulo)}</h1><div class="sub">{_e(subtitulo)}</div></div>'
            f'<div class="chips">{cs}</div></div>')


def logo_acp() -> str:
    """Logo de ACPTester (tres velas que suben dentro de una ficha) con el nombre y una linea de apoyo. Es un SVG en linea:
    se ve nitido a cualquier tamaño y no depende de archivos aparte. Pensado para el fondo violeta de la barra lateral."""
    return ('<div class="logo-acp"><svg width="58" height="58" viewBox="0 0 58 58" aria-hidden="true">'
            '<rect x="1" y="1" width="56" height="56" rx="16" fill="rgba(255,255,255,.14)" stroke="rgba(255,255,255,.55)"/>'
            '<g stroke-linecap="round"><path d="M17 17V42" stroke="#fff" stroke-width="2"/><rect x="13" y="25" width="8" height="12" rx="2" fill="#fff"/>'
            '<path d="M29 12V40" stroke="#ff8cc4" stroke-width="2"/><rect x="25" y="19" width="8" height="15" rx="2" fill="#ff8cc4"/>'
            '<path d="M41 10V34" stroke="#fff" stroke-width="2"/><rect x="37" y="14" width="8" height="14" rx="2" fill="#fff"/></g></svg>'
            '<div><div class="nom"><b>ACP</b><span>Tester</span></div><div class="lema">backtest y bots para MT5</div></div></div>')


def cargando(texto: str) -> str:
    """Circulo de carga (anillo degradado) con un texto al lado."""
    return f'<div class="cargando"><div class="anillo-carga"></div><div class="txt">{_e(texto)}</div></div>'


def kpi(etiqueta: str, valor: str, sub: str = "", color: str = None, min_alto: int = 0) -> str:
    """min_alto (px): para que las tarjetas de una misma fila queden del mismo alto aunque el texto cambie de largo."""
    color = color or INDIGO
    est = f' style="min-height:{int(min_alto)}px"' if min_alto else ""
    return (f'<div class="card kpi"{est}><div class="bar" style="background:{color}"></div>'
            f'<div class="lab">{_e(etiqueta)}</div><div class="val" style="color:{color}">{_e(valor)}</div>'
            f'<div class="sub">{_e(sub)}</div></div>')


def tarjeta(titulo: str, cuerpo_html: str, nota: str = "", derecha: str = "", min_alto: int = 0) -> str:
    """min_alto (px) sirve para que dos tarjetas lado a lado queden del mismo tamaño."""
    h = f"<h4><span>{_e(titulo)}</span><small>{_e(derecha)}</small></h4>" if titulo else ""
    nt = f'<div class="note">{_e(nota)}</div>' if nota else ""
    est = f' style="min-height:{int(min_alto)}px;box-sizing:border-box"' if min_alto else ""
    return f'<div class="card"{est}>{h}{cuerpo_html}{nt}</div>'


def anillo(pct, titulo: str, sub: str, equilibrio=None, color: str = None, uid: str = "a", min_alto: int = 0) -> str:
    """Anillo de progreso (0-100). `equilibrio` marca con una rayita el %TP mínimo para no perder."""
    import math
    color = color or VIOLETA
    p = max(0.0, min(100.0, float(pct if pct == pct else 0)))
    r, c = 46, 2 * math.pi * 46
    marca = ""
    if equilibrio is not None and equilibrio == equilibrio:
        ang = math.radians(-90 + 3.6 * float(equilibrio))
        x1, y1 = 60 + (r - 9) * math.cos(ang), 60 + (r - 9) * math.sin(ang)
        x2, y2 = 60 + (r + 9) * math.cos(ang), 60 + (r + 9) * math.sin(ang)
        marca = f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{TEXTO}" stroke-width="2.4" stroke-linecap="round"/>'
    svg = (f'<svg viewBox="0 0 120 120"><defs><linearGradient id="g{uid}" x1="0" y1="0" x2="1" y2="1">'
           f'<stop offset="0" stop-color="{ROSA}"/><stop offset="1" stop-color="{color}"/></linearGradient></defs>'
           f'<circle cx="60" cy="60" r="{r}" fill="none" stroke="{PISTA}" stroke-width="10"/>'
           f'<circle cx="60" cy="60" r="{r}" fill="none" stroke="url(#g{uid})" stroke-width="10" stroke-linecap="round" '
           f'stroke-dasharray="{c * p / 100:.1f} {c:.1f}" transform="rotate(-90 60 60)"/>{marca}'
           f'<text x="60" y="66" text-anchor="middle" font-size="21" font-weight="800" fill="{TEXTO}">{n(p, 1)}%</text></svg>')
    est = f' style="min-height:{int(min_alto)}px"' if min_alto else ""
    return (f'<div class="card"{est}><div class="ring">{_como_img(svg, "width:118px;height:118px")}'
            f'<div class="t">{_e(titulo)}</div><div class="s">{sub}</div></div></div>')


def medidor(pct, titulo: str, sub: str = "", uid: str = "m") -> str:
    """Medidor semicircular 0-100 (como el de eficiencia del ejemplo)."""
    import math
    p = max(0.0, min(100.0, float(pct if pct == pct else 0)))
    r = 78
    largo = math.pi * r
    ang = math.radians(180 - 1.8 * p)
    nx, ny = 100 + (r - 14) * math.cos(ang), 100 - (r - 14) * math.sin(ang)
    arco = f"M {100 - r} 100 A {r} {r} 0 0 1 {100 + r} 100"
    svg = (f'<svg viewBox="0 0 200 132"><defs><linearGradient id="g{uid}" x1="0" x2="1">'
           f'<stop offset="0" stop-color="{ROSA}"/><stop offset=".5" stop-color="{VIOLETA}"/><stop offset="1" stop-color="{AZUL}"/>'
           f'</linearGradient></defs><path d="{arco}" fill="none" stroke="{PISTA}" stroke-width="16" stroke-linecap="round"/>'
           f'<path d="{arco}" fill="none" stroke="url(#g{uid})" stroke-width="16" stroke-linecap="round" '
           f'stroke-dasharray="{largo * p / 100:.1f} {largo:.1f}"/>'
           f'<line x1="100" y1="100" x2="{nx:.1f}" y2="{ny:.1f}" stroke="{TEXTO}" stroke-width="3" stroke-linecap="round"/>'
           f'<circle cx="100" cy="100" r="6" fill="{TEXTO}"/>'
           f'<text x="100" y="128" text-anchor="middle" font-size="19" font-weight="800" fill="{TEXTO}">{n(p, 0)}%</text></svg>')
    return (f'<div class="ring">{_como_img(svg, "width:100%;max-width:260px;height:auto")}'
            f'<div class="t">{_e(titulo)}</div><div class="s">{sub}</div></div>')


def barras_divergentes(filas: list, maximo=None, dec=2) -> str:
    """filas: [(nombre, valor, color_opcional)]. Barras hacia la derecha (positivo) o izquierda (negativo)."""
    vals = [abs(v) for _, v, *_ in filas if v == v]
    m = maximo or (max(vals) if vals else 1) or 1
    out = []
    for fila in filas:
        nombre, v = fila[0], fila[1]
        col = fila[2] if len(fila) > 2 and fila[2] else tono(v)
        if v != v:
            out.append(f'<div class="r"><div class="nm">{_e(nombre)}</div><div class="track"></div><div class="v">–</div></div>')
            continue
        w = min(50.0, abs(v) / m * 50)
        pos = f"left:50%;width:{w:.1f}%" if v >= 0 else f"right:50%;width:{w:.1f}%"
        flecha = "▲" if v >= 0 else "▼"
        out.append(f'<div class="r"><div class="nm" title="{_e(nombre)}">{_e(nombre)}</div>'
                   f'<div class="track"><div class="c"></div><div class="f" style="{pos};background:{col}"></div></div>'
                   f'<div class="v" style="color:{col}">{flecha} {n(v, dec, True)}</div></div>')
    return f'<div class="rows">{"".join(out)}</div>'


def embudo(etapas: list) -> str:
    """etapas: [(nombre, cantidad)]. Una barra por etapa; el largo es el % de la etapa ANTERIOR (la primera = 100 %),
    así cada paso se lee bien aunque la cantidad inicial sea mucho mayor que las siguientes."""
    cols = [ROSA, MAGENTA, ORQ, VIOLETA, INDIGO, AZUL]
    out, previo = [], None
    for k, (nombre, c) in enumerate(etapas):
        f = 100.0 if previo is None else (100.0 * c / previo if previo else 0.0)
        ancho = max(min(f, 100.0), 3.0)
        pie = "&nbsp;" if previo is None else f"{n(f, 0)}% del paso anterior"
        out.append(f'<div class="ra"><div class="rl"><span>{_e(nombre)}</span><span class="rv">{n(c, 0)}</span></div>'
                   f'<div class="trk"><div style="width:{ancho:.0f}%;background:linear-gradient(90deg,{cols[k % len(cols)]},{VIOLETA})"></div></div>'
                   f'<div class="rp">{pie}</div></div>')
        previo = c
    return f'<div class="emb">{"".join(out)}</div>'


def _muestrear(vals, maximo=320):
    if len(vals) <= maximo:
        return list(range(len(vals))), list(vals)
    paso = (len(vals) - 1) / (maximo - 1)
    idx = sorted({round(k * paso) for k in range(maximo)})
    return idx, [vals[i] for i in idx]


def curva_equity(valores: list, etiqueta_ini: str = "", etiqueta_fin: str = "", pos_oos=None, uid: str = "e",
                 xs=None, x_oos=None) -> str:
    """Área de la equity acumulada (en R). `pos_oos`: posición (0..len) donde empieza el out-of-sample.
    Con `xs` (fracción 0..1 del tiempo de cada punto) y `x_oos` (fracción donde empieza el out-of-sample) el eje es el tiempo:
    si la cuenta dejó de operar, la curva termina antes y el out-of-sample se marca igual."""
    if not valores:
        return '<div class="note">Sin operaciones resueltas.</div>'
    W, H, pl, pr, pt, pb = 640, 230, 46, 14, 14, 30
    idx, v = _muestrear(valores)
    total = len(valores) - 1 or 1
    lo, hi = min(0.0, min(v)), max(0.0, max(v))
    if hi == lo:
        hi = lo + 1
    X = (lambda i: pl + (W - pl - pr) * xs[i]) if xs is not None else (lambda i: pl + (W - pl - pr) * i / total)
    Y = lambda y: pt + (H - pt - pb) * (1 - (y - lo) / (hi - lo))
    pts = " ".join(f"{X(i):.1f},{Y(y):.1f}" for i, y in zip(idx, v))
    area = f"{X(idx[0]):.1f},{Y(0):.1f} {pts} {X(idx[-1]):.1f},{Y(0):.1f}"
    grid = ""
    for g in (lo, (lo + hi) / 2, hi):
        grid += (f'<line x1="{pl}" x2="{W - pr}" y1="{Y(g):.1f}" y2="{Y(g):.1f}" stroke="{GRID}"/>'
                 f'<text x="{pl - 6}" y="{Y(g) + 4:.1f}" text-anchor="end" font-size="10.5" fill="{SUAVE}">{n(g, 0)}</text>')
    cero = f'<line x1="{pl}" x2="{W - pr}" y1="{Y(0):.1f}" y2="{Y(0):.1f}" stroke="{EJE}" stroke-dasharray="4 4"/>'
    oos = ""
    if xs is not None and x_oos is not None and 0 < x_oos < 1:
        x = pl + (W - pl - pr) * x_oos
    elif xs is None and pos_oos is not None and 0 < pos_oos < len(valores):
        x = X(pos_oos)
    else:
        x = None
    if x is not None:
        oos = (f'<rect x="{x:.1f}" y="{pt}" width="{W - pr - x:.1f}" height="{H - pt - pb}" fill="{ROSA}" opacity=".07"/>'
               f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{pt}" y2="{H - pb}" stroke="{ROSA}" stroke-dasharray="3 3"/>'
               f'<text x="{x + 6:.1f}" y="{pt + 12}" font-size="10.5" font-weight="700" fill="{MAGENTA}">Out-of-sample</text>')
    return _como_img(f'<svg viewBox="0 0 {W} {H}"><defs><linearGradient id="g{uid}" x1="0" y1="0" x2="0" y2="1">'
            f'<stop offset="0" stop-color="{VIOLETA}" stop-opacity=".45"/><stop offset="1" stop-color="{VIOLETA}" stop-opacity=".02"/>'
            f'</linearGradient></defs>{grid}{oos}{cero}<polygon points="{area}" fill="url(#g{uid})"/>'
            f'<polyline points="{pts}" fill="none" stroke="{INDIGO}" stroke-width="2.4" stroke-linejoin="round" stroke-linecap="round"/>'
            f'<text x="{pl}" y="{H - 8}" font-size="10.5" fill="{SUAVE}">{_e(etiqueta_ini)}</text>'
            f'<text x="{W - pr}" y="{H - 8}" text-anchor="end" font-size="10.5" fill="{SUAVE}">{_e(etiqueta_fin)}</text></svg>')


def barras_verticales(items: list, dec=2, signo=True) -> str:
    """items: [(etiqueta, valor, texto_pie)]. Barras desde el cero: azul si es positiva, rosa si es negativa."""
    if not items:
        return '<div class="note">Sin datos.</div>'
    W, H, pl, pr, pt, pb = 640, 230, 14, 14, 22, 44
    vals = [v for _, v, _ in items if v == v]
    lo, hi = min(0.0, min(vals, default=0)), max(0.0, max(vals, default=0))
    if hi == lo:
        hi = lo + 1
    pad = (hi - lo) * 0.16            # lugar para el valor escrito fuera de cada barra
    lo, hi = (lo - pad if lo < 0 else lo), (hi + pad if hi > 0 else hi)
    k = len(items)
    paso = (W - pl - pr) / k
    ancho = min(54.0, paso * 0.62)
    Y = lambda y: pt + (H - pt - pb) * (1 - (y - lo) / (hi - lo))
    cuerpo = f'<line x1="{pl}" x2="{W - pr}" y1="{Y(0):.1f}" y2="{Y(0):.1f}" stroke="{EJE}"/>'
    for j, (et, v, pie) in enumerate(items):
        cx = pl + paso * (j + 0.5)
        if v == v:
            y0, y1 = Y(0), Y(v)
            top, h = min(y0, y1), max(abs(y1 - y0), 1.5)
            cuerpo += (f'<rect x="{cx - ancho / 2:.1f}" y="{top:.1f}" width="{ancho:.1f}" height="{h:.1f}" rx="6" fill="{tono(v)}"/>'
                       f'<text x="{cx:.1f}" y="{(top - 5) if v >= 0 else (top + h + 13):.1f}" text-anchor="middle" '
                       f'font-size="11" font-weight="700" fill="{tono(v)}">{n(v, dec, signo)}</text>')
        cuerpo += (f'<text x="{cx:.1f}" y="{H - 24}" text-anchor="middle" font-size="11.5" font-weight="600" fill="{TEXTO}">{_e(str(et))}</text>'
                   f'<text x="{cx:.1f}" y="{H - 10}" text-anchor="middle" font-size="10" fill="{SUAVE}">{_e(pie)}</text>')
    return _como_img(f'<svg viewBox="0 0 {W} {H}">{cuerpo}</svg>')


def insight(titulo: str, texto_html: str) -> str:
    return f'<div class="insight"><div class="tt">{_e(titulo)}</div>{texto_html}</div>'


def chips(items: list) -> str:
    """items: [(texto, valor)] -> fila de pastillas."""
    if not items:
        return '<div class="note">Ninguna.</div>'
    return '<div class="chips">' + "".join(
        f'<span class="chip">{_e(str(k))}: <b>{_e(str(v))}</b></span>' for k, v in items) + "</div>"


def equivalencia_precio(titulo: str, sl_txt: str, tp_txt: str, lote_txt: str, filas: list, nota: str = "") -> str:
    """Tarjeta 'SL/TP en precio': pastillas de resumen (SL, TP opcional, lotes) y una tabla con una fila por simbolo.
    filas: [(simbolo, sl, tp_o_None)]. Si ninguna fila tiene TP (salida por señal) se omite esa columna."""
    con_tp = any(f[2] is not None for f in filas)
    pil = f'<span class="pill" style="background:{ROSA}">SL {_e(sl_txt)}</span>'
    if con_tp:
        pil += f'<span class="pill" style="background:{INDIGO}">TP {_e(tp_txt)}</span>'
    pil += f'<span class="pill" style="background:{VIOLETA}">{_e(lote_txt)}</span>'
    cab = "<th>Símbolo</th><th>SL (precio)</th>" + ("<th>TP (precio)</th>" if con_tp else "")
    cuerpo = "".join(f'<tr><td>{_e(s)}</td><td class="sl">{_e(a)}</td>' + (f'<td class="tp">{_e(b if b is not None else "-")}</td>' if con_tp else "") + "</tr>"
                     for s, a, b in filas)
    nt = f'<div class="note">{_e(nota)}</div>' if nota else ""
    return (f'<div class="card eqp"><div class="top"><h4>{_e(titulo)}</h4><div class="pills">{pil}</div></div>'
            f'<table><thead><tr>{cab}</tr></thead><tbody>{cuerpo}</tbody></table>{nt}</div>')


def tabla_html(columnas: list, filas: list, resaltar=None, max_alto: int = 0, clase=None, izq=()) -> str:
    """columnas: encabezados (el primero es el índice). filas: listas de textos.
    resaltar(fila_idx, col_idx) -> True pinta la celda. Es HTML propio: se ve igual en tema claro u oscuro."""
    est = lambda j: ' style="text-align:left"' if j in izq else ""
    cab = "".join(f"<th{est(j)}>{_e(str(c))}</th>" for j, c in enumerate(columnas))
    cuerpo = []
    for i, fila in enumerate(filas):
        celdas = []
        for j, v in enumerate(fila):
            c = "hit" if (resaltar and j > 0 and resaltar(i, j)) else ("nd" if v == "–" else (clase(i, j) if clase else None))
            cls = f' class="{c}"' if c else ""
            celdas.append(f"<td{cls}{est(j)}>{_e(str(v))}</td>")
        cuerpo.append("<tr>" + "".join(celdas) + "</tr>")
    alto = f' style="max-height:{max_alto}px"' if max_alto else ""
    return f'<div class="tbl"{alto}><table><thead><tr>{cab}</tr></thead><tbody>{"".join(cuerpo)}</tbody></table></div>'


COLS_CON_SIGNO = {"exp_R", "R_total", "R", "exp_R_IS", "exp_R_OOS", "azar_exp_R", "aporte"}


def tabla_df(df, decs: dict = None, dec: int = 2, signo_cols=COLS_CON_SIGNO, max_filas: int = 400, max_alto: int = 420,
             nombre_indice: str = "") -> str:
    """DataFrame de pandas -> tabla HTML con el estilo del dashboard (no depende del tema del navegador).
    Formatea números en español, pinta en azul/rosa las columnas de resultados en R y recorta a `max_filas`."""
    import pandas as pd
    decs = decs or {}
    recorte = len(df) > max_filas
    d = df.iloc[:max_filas]
    cols = [nombre_indice or (d.index.name or "")] + [str(c) for c in d.columns]

    def fmt(v, col):
        if v is None or (isinstance(v, float) and v != v) or v is pd.NaT:
            return "–"
        if isinstance(v, bool) or str(type(v)).endswith("bool_'>"):
            return "sí" if v else "no"
        if isinstance(v, pd.Timestamp):
            return v.strftime("%Y-%m-%d %H:%M")
        if isinstance(v, (int,)) or str(type(v)).find("int") >= 0:
            return str(int(v))
        if isinstance(v, float) or str(type(v)).find("float") >= 0:
            return n(v, decs.get(col, dec))
        return str(v)

    idx = d.index
    filas = [[fmt(i, "") if not isinstance(i, str) else i] + [fmt(v, c) for c, v in zip(d.columns, fila)]
             for i, fila in zip(idx, d.to_numpy(dtype=object))]
    nombres = list(d.columns)

    def clase(i, j):
        if nombres[j - 1] in signo_cols:
            try:
                x = float(d.iloc[i, j - 1])
            except (TypeError, ValueError):
                return None
            return None if x != x else ("pos" if x >= 0 else "neg")
        return None

    h = tabla_html(cols, filas, max_alto=max_alto, clase=clase)
    if recorte:
        h += f'<div class="note">Se muestran las primeras {max_filas} de {len(df)} filas. El CSV trae todas.</div>'
    return h


def _fondos() -> dict:
    """Fondos de los recuadros de veredicto, con los colores del estilo activo (lo malo siempre en rojo, lo no concluyente en gris)."""
    claro_txt = TEMAS[TEMA]["BTNTXT"] != "#ffffff"       # estilos con texto oscuro sobre los colores (pastel, noche suave)
    g = lambda a, b: f"linear-gradient(120deg,{a},{b})"
    p = TEMAS[TEMA]
    return {"solida": g(AZUL, p["PROF"]), "ok": g(INDIGO, AZUL), "dudosa": g(VIOLETA, ORQ), "sin": g(ORQ, MAGENTA),
            "pierde": g("#f28ba0", "#e2607f") if claro_txt else g("#e63e5c", "#b3123f"),
            "no": g("#f28ba0", "#e2607f") if claro_txt else g("#e63e5c", "#b3123f"),
            "nc": g("#c4c0d8", "#a9a4c4") if claro_txt else g("#7a7f9d", "#555a82")}


def veredicto_caja(etiqueta: str, titulo: str, texto_html: str, nivel: str) -> str:
    """Recuadro de color según el nivel: solida / ok / dudosa / sin / pierde / nc."""
    return (f'<div class="insight" style="background:{_fondos().get(nivel, _fondos()["nc"])}">'
            f'<div class="tt">{_e(etiqueta)}</div><div style="font-size:1.25rem;font-weight:800;margin:2px 0 8px">{_e(titulo)}</div>'
            f'{texto_html}</div>')


def titulo_seccion(titulo: str, sub: str = "") -> str:
    """Título de sección con el mismo formato del resto (no depende del tema de Streamlit)."""
    s_ = f'<div class="sub">{_e(sub)}</div>' if sub else ""
    return f'<div class="sec"><h3>{_e(titulo)}</h3>{s_}</div>'
