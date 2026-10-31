"""Estilo y componentes visuales del dashboard (sin dependencias: HTML + SVG).

Todo devuelve texto HTML que se muestra con `st.html(...)`. No importa Streamlit, así que se
puede probar fuera de la app. Paleta: rosa -> violeta -> azul. Positivo = azul/violeta,
negativo = rosa, siempre acompañado de signo o flecha (no depende solo del color).
"""
from html import escape as _e

TEMAS = {
    "claro": dict(ROSA="#ff4fa3", MAGENTA="#e63e9c", VIOLETA="#7c5cf0", INDIGO="#4c4fe0", AZUL="#2f3fd8",
                  TEXTO="#1f2340", SUAVE="#7a7f9d", PISTA="#e7e9f7", GRID="#eceefa", EJE="#b9bcd8",
                  BG="#eef0fb", CARD="#ffffff", LINE="#eef0fb", HEAD="#f4f5fd", ND="#b0b4cc",
                  SHADOW="rgba(60,64,140,.10)", SHADOW2="rgba(60,64,140,.08)", INBG="#ffffff", INBD="#d9dcf3",
                  SIDE="linear-gradient(185deg,#4b3fd1 0%,#6a4fe6 55%,#8a63f2 100%)"),
    "oscuro": dict(ROSA="#ff5fae", MAGENTA="#f05fb0", VIOLETA="#9b82ff", INDIGO="#8b8fff", AZUL="#6b86ff",
                   TEXTO="#eceefc", SUAVE="#9aa0c8", PISTA="#2a2e5a", GRID="#252952", EJE="#4a4f80",
                   BG="#0e1126", CARD="#181b3b", LINE="#262a52", HEAD="#20244d", ND="#5a5f8a",
                   SHADOW="rgba(0,0,0,.40)", SHADOW2="rgba(0,0,0,.30)", INBG="#10132d", INBD="#363c72",
                   SIDE="linear-gradient(185deg,#1d1858 0%,#2b2280 55%,#3d2f98 100%)"),
}
TEMA = "claro"
ROSA = MAGENTA = VIOLETA = INDIGO = AZUL = TEXTO = SUAVE = PISTA = GRID = EJE = POS = NEG = ""


def set_tema(nombre: str = "claro") -> str:
    """Cambia la paleta de los componentes (colores de los gráficos y del CSS). Es global del proceso:
    se llama una vez por ejecución, al comienzo de app.py."""
    global TEMA, ROSA, MAGENTA, VIOLETA, INDIGO, AZUL, TEXTO, SUAVE, PISTA, GRID, EJE, POS, NEG
    TEMA = nombre if nombre in TEMAS else "claro"
    p = TEMAS[TEMA]
    ROSA, MAGENTA, VIOLETA, INDIGO, AZUL = p["ROSA"], p["MAGENTA"], p["VIOLETA"], p["INDIGO"], p["AZUL"]
    TEXTO, SUAVE, PISTA, GRID, EJE = p["TEXTO"], p["SUAVE"], p["PISTA"], p["GRID"], p["EJE"]
    POS, NEG = INDIGO, ROSA
    return TEMA


set_tema("claro")

# Poné False si la barra lateral morada no se ve bien en tu versión de Streamlit.
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
[data-testid="stNumberInput"] button{background:@INBG@ !important;color:@TXT@ !important;}
[data-testid="stFileUploaderDropzone"]{background:@INBG@ !important;}
[data-testid="stFileUploaderDropzone"] :is(span,small,p,div){color:@TXT@ !important;}
[data-testid="stExpander"] summary :is(p,span){color:@TXT@ !important;}
[data-testid="stAlert"] :is(p,div,span){color:@TXT@ !important;}"""

_CSS_SIDEBAR = """
[data-testid="stSidebar"]{background:@SIDE@;}
[data-testid="stSidebar"] :is(h1,h2,h3),
[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p,
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] p,
[data-testid="stSidebar"] [data-testid="stRadio"] label p,
[data-testid="stSidebar"] [data-testid="stCheckbox"] label p,
[data-testid="stSidebar"] label :is(p,span),
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] > p{color:#fff !important;}
[data-testid="stSidebar"] h2{font-size:1.05rem;letter-spacing:.02em;text-transform:uppercase;
  border-bottom:1px solid rgba(255,255,255,.25);padding-bottom:.35rem;margin-top:.6rem;}
[data-testid="stSidebar"] [data-testid="stExpander"]{background:rgba(255,255,255,.10);box-shadow:none;
  border:1px solid rgba(255,255,255,.22);border-radius:14px;}
[data-testid="stSidebar"] [data-testid="stExpander"] summary{padding:.55rem .8rem;}
[data-testid="stSidebar"] [data-testid="stExpander"] summary :is(p,span){color:#fff !important;font-weight:700;}
[data-testid="stSidebar"] [data-testid="stExpander"] summary svg{fill:#fff;color:#fff;}
[data-testid="stSidebarNav"] a{border-radius:10px;}
[data-testid="stSidebarNav"] a span{color:#fff !important;}
[data-testid="stSidebarNav"] a[aria-current="page"]{background:rgba(255,255,255,.18);}
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
button[kind="primary"],[data-testid="stBaseButton-primary"]{background:linear-gradient(90deg,#ff4fa3,#7c5cf0);
  border:0;color:#fff;border-radius:12px;font-weight:600;box-shadow:0 6px 16px rgba(124,92,240,.35);}
button[kind="secondary"],[data-testid="stBaseButton-secondary"]{border-radius:12px;border:1px solid @INBD@;
  background:@CARD@;color:@ACC@;font-weight:600;}
.stButton>button{width:100%;padding:.55rem 1rem;}
[data-testid="stDataFrame"]{border-radius:12px;overflow:hidden;}
[data-testid="stExpander"]{background:@CARD@;border-radius:14px;border:0;box-shadow:0 4px 16px @SHADOW2@;}
/* componentes propios */
.tb{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px;margin:0 0 14px;}
.tb h1{margin:0;font-size:1.7rem;font-weight:800;color:@TXT@;}
.tb .sub{color:@MUTED@;font-size:.9rem;margin-top:2px;}
.chips{display:flex;gap:8px;flex-wrap:wrap;}
.chip{background:@CARD@;border-radius:999px;padding:6px 14px;font-size:.78rem;font-weight:600;color:@ACC@;
  box-shadow:0 3px 10px @SHADOW@;white-space:nowrap;}
.chip b{color:@TXT@;}
.card{background:@CARD@;border-radius:18px;box-shadow:0 6px 22px @SHADOW@;padding:16px 18px;height:100%;box-sizing:border-box;}
.card h4{margin:0 0 10px;font-size:.92rem;font-weight:700;color:@TXT@;display:flex;justify-content:space-between;align-items:center;}
.card h4 small{font-weight:500;color:@MUTED@;font-size:.74rem;}
.kpi{position:relative;overflow:hidden;}
.kpi .lab{color:@MUTED@;font-size:.74rem;font-weight:600;text-transform:uppercase;letter-spacing:.05em;}
.kpi .val{font-size:1.85rem;font-weight:800;line-height:1.15;margin:4px 0 2px;}
.kpi .sub{color:@MUTED@;font-size:.78rem;}
.kpi .bar{position:absolute;left:0;top:0;bottom:0;width:5px;}
.ring{display:flex;flex-direction:column;align-items:center;text-align:center;}
.ring .t{font-weight:700;font-size:.85rem;margin-top:4px;color:@TXT@;}
.ring .s{font-size:.74rem;color:@MUTED@;margin-top:2px;line-height:1.35;}
.rows .r{display:grid;grid-template-columns:170px 1fr 72px;gap:10px;align-items:center;margin:9px 0;font-size:.8rem;}
.rows .r .nm{font-weight:600;color:@TXT@;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
.rows .r .v{text-align:right;font-weight:700;font-variant-numeric:tabular-nums;}
.track{position:relative;height:11px;border-radius:99px;background:@TRACK@;}
.track .c{position:absolute;left:50%;top:-3px;bottom:-3px;width:1px;background:@EJE@;}
.track .f{position:absolute;top:0;bottom:0;border-radius:99px;}
.emb .e{box-sizing:border-box;margin:8px auto;border-radius:12px;color:#fff;padding:9px 14px;display:flex;justify-content:space-between;
  font-weight:600;font-size:.82rem;box-shadow:0 4px 12px rgba(124,92,240,.25);}
.emb .e span:last-child{font-weight:800;}
.insight{background:linear-gradient(120deg,#4c4fe0,#2f3fd8);color:#fff;border-radius:18px;padding:16px 20px;
  box-shadow:0 8px 24px rgba(47,63,216,.30);font-size:.9rem;line-height:1.55;}
.insight b{color:#fff;}
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
              "@NEG@": p["ROSA"], "@SIDE@": p["SIDE"]}
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


def kpi(etiqueta: str, valor: str, sub: str = "", color: str = None) -> str:
    color = color or INDIGO
    return (f'<div class="card kpi"><div class="bar" style="background:{color}"></div>'
            f'<div class="lab">{_e(etiqueta)}</div><div class="val" style="color:{color}">{_e(valor)}</div>'
            f'<div class="sub">{_e(sub)}</div></div>')


def tarjeta(titulo: str, cuerpo_html: str, nota: str = "", derecha: str = "") -> str:
    h = f"<h4><span>{_e(titulo)}</span><small>{_e(derecha)}</small></h4>" if titulo else ""
    nt = f'<div class="note">{_e(nota)}</div>' if nota else ""
    return f'<div class="card">{h}{cuerpo_html}{nt}</div>'


def anillo(pct, titulo: str, sub: str, equilibrio=None, color: str = None, uid: str = "a") -> str:
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
    return (f'<div class="card"><div class="ring">{_como_img(svg, "width:118px;height:118px")}'
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
    """etapas: [(nombre, cantidad)] de mayor a menor. Ancho proporcional con un mínimo legible."""
    top = max((c for _, c in etapas), default=0) or 1
    cols = [ROSA, MAGENTA, "#a355e8", VIOLETA, INDIGO, AZUL]
    out, previo = [], None
    for k, (nombre, c) in enumerate(etapas):
        w = max(38.0, 100.0 * c / top)
        pct = "" if previo in (None, 0) else f" · {n(100 * c / previo, 0)}%"
        out.append(f'<div class="e" style="width:{w:.0f}%;background:{cols[k % len(cols)]}">'
                   f'<span>{_e(nombre)}<small style="opacity:.85;font-weight:500">{pct}</small></span><span>{n(c, 0)}</span></div>')
        previo = c
    return f'<div class="emb">{"".join(out)}</div>'


def _muestrear(vals, maximo=320):
    if len(vals) <= maximo:
        return list(range(len(vals))), list(vals)
    paso = (len(vals) - 1) / (maximo - 1)
    idx = sorted({round(k * paso) for k in range(maximo)})
    return idx, [vals[i] for i in idx]


def curva_equity(valores: list, etiqueta_ini: str = "", etiqueta_fin: str = "", pos_oos=None, uid: str = "e") -> str:
    """Área de la equity acumulada (en R). `pos_oos`: posición (0..len) donde empieza el out-of-sample."""
    if not valores:
        return '<div class="note">Sin operaciones resueltas.</div>'
    W, H, pl, pr, pt, pb = 640, 230, 46, 14, 14, 30
    idx, v = _muestrear(valores)
    total = len(valores) - 1 or 1
    lo, hi = min(0.0, min(v)), max(0.0, max(v))
    if hi == lo:
        hi = lo + 1
    X = lambda i: pl + (W - pl - pr) * i / total
    Y = lambda y: pt + (H - pt - pb) * (1 - (y - lo) / (hi - lo))
    pts = " ".join(f"{X(i):.1f},{Y(y):.1f}" for i, y in zip(idx, v))
    area = f"{X(idx[0]):.1f},{Y(0):.1f} {pts} {X(idx[-1]):.1f},{Y(0):.1f}"
    grid = ""
    for g in (lo, (lo + hi) / 2, hi):
        grid += (f'<line x1="{pl}" x2="{W - pr}" y1="{Y(g):.1f}" y2="{Y(g):.1f}" stroke="{GRID}"/>'
                 f'<text x="{pl - 6}" y="{Y(g) + 4:.1f}" text-anchor="end" font-size="10.5" fill="{SUAVE}">{n(g, 0)}</text>')
    cero = f'<line x1="{pl}" x2="{W - pr}" y1="{Y(0):.1f}" y2="{Y(0):.1f}" stroke="{EJE}" stroke-dasharray="4 4"/>'
    oos = ""
    if pos_oos is not None and 0 < pos_oos < len(valores):
        x = X(pos_oos)
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


_FONDOS = {"ok": "linear-gradient(120deg,#4c4fe0,#2f3fd8)", "dudosa": "linear-gradient(120deg,#7c5cf0,#a355e8)",
           "no": "linear-gradient(120deg,#ff4fa3,#e63e9c)", "nc": "linear-gradient(120deg,#7a7f9d,#555a82)"}


def veredicto_caja(etiqueta: str, titulo: str, texto_html: str, nivel: str) -> str:
    """Recuadro de color según el nivel: ok / dudosa / no / nc."""
    return (f'<div class="insight" style="background:{_FONDOS.get(nivel, _FONDOS["nc"])}">'
            f'<div class="tt">{_e(etiqueta)}</div><div style="font-size:1.25rem;font-weight:800;margin:2px 0 8px">{_e(titulo)}</div>'
            f'{texto_html}</div>')


def titulo_seccion(titulo: str, sub: str = "") -> str:
    """Título de sección con el mismo formato del resto (no depende del tema de Streamlit)."""
    s_ = f'<div class="sub">{_e(sub)}</div>' if sub else ""
    return f'<div class="sec"><h3>{_e(titulo)}</h3>{s_}</div>'
