"""Portada de ACPTester: panel de marca a la izquierda y los 4 módulos en tarjetas 2x2. Sin barra lateral.

Se dibuja como una sola pieza HTML de tamaño fijo (components.html) para que el panel y las tarjetas midan siempre lo mismo.
Al tocar una tarjeta se "hace clic" en el enlace de esa página dentro del menú oculto de Streamlit, así se navega sin recargar
y no se pierde lo que haya cargado en los backtesters. Los dibujos son miniaturas ilustrativas, no datos reales."""
import numpy as np
import streamlit as st
import streamlit.components.v1 as components

import ui_estilo as ui

ALTO = 520      # alto del panel y del bloque de tarjetas (px)
PANEL = 27      # ancho del panel violeta, en % del ancho total
MARCO = 16      # aire arriba y abajo dentro del iframe, para las sombras
_HORAS = [.12, .14, .2, .34, .3, .22, .16, .4, .7, .62, .5, .46, .52, .86, 1, .9, .74, .6, .42, .3, .2, .14, .1, .1]


def _logo(c1: str, c2: str, s: int = 64) -> str:
    return (f'<svg width="{s}" height="{s}" viewBox="0 0 28 28">'
            f'<rect x="3" y="9" width="6" height="12" rx="1.5" fill="{c1}"/><line x1="6" y1="4" x2="6" y2="25" stroke="{c1}" stroke-width="2"/>'
            f'<rect x="11" y="5" width="6" height="14" rx="1.5" fill="{c2}"/><line x1="14" y1="2" x2="14" y2="24" stroke="{c2}" stroke-width="2"/>'
            f'<rect x="19" y="11" width="6" height="11" rx="1.5" fill="{c1}"/><line x1="22" y1="6" x2="22" y2="26" stroke="{c1}" stroke-width="2"/></svg>')


def _horas(w: int, h: int, base: str, fuerte: str) -> str:
    bw = w / 24
    r = "".join(f'<rect x="{i * bw + 1:.1f}" y="{h - x * (h - 2):.1f}" width="{bw - 2:.1f}" height="{x * (h - 2):.1f}" rx="1.5" '
                f'fill="{fuerte if 13 <= i <= 16 else base}"/>' for i, x in enumerate(_HORAS))
    return f'<svg width="100%" viewBox="0 0 {w} {h}">{r}</svg>'


def _curva(seed: int, w: int, h: int, color: str, deriva: float = .9, vol: float = 2.2) -> str:
    y = np.cumsum(np.random.default_rng(seed).normal(deriva, vol, 80))
    lo, hi = y.min(), y.max()
    pts = " L".join(f"{i * w / 79:.1f},{h - 4 - (v - lo) / (hi - lo) * (h - 8):.1f}" for i, v in enumerate(y))
    return f'<svg width="100%" viewBox="0 0 {w} {h}"><path d="M{pts}" fill="none" stroke="{color}" stroke-width="2.2" stroke-linejoin="round"/></svg>'


def _codigo(w: int, h: int, color: str) -> str:
    lin = "".join(f'<rect y="{8 + i * 14}" width="{a}" height="6" rx="3" fill="{color}" opacity="{o}"/>'
                  for i, (a, o) in enumerate([(120, .95), (170, .45), (95, .45), (150, .45)]))
    return f'<svg width="100%" viewBox="0 0 {w} {h}">{lin}</svg>'


def html(p: dict, ruta: dict, oscuro: bool) -> str:
    """Devuelve el HTML completo de la portada. `p` es la paleta (ui.TEMAS[...]); `ruta` mapea clave -> url_path."""
    W, H = 300, 64
    mods = [
        ("sesiones", "Sesiones XAU/USD", "Volatilidad del oro por sesión y por hora", _horas(W, H, p["PISTA"], p["INDIGO"])),
        ("ema", "Backtester EMA", "Cruce de dos medias exponenciales", _curva(21, W, H, p["INDIGO"])),
        ("sma", "Backtester SMA", "Precio contra una media simple o cruce de dos", _curva(8, W, H, p["ROSA"], .7, 2.6)),
        ("bot", "Generar bot (.mq5)", "Exporta los parámetros del backtest a MetaTrader 5", _codigo(W, H, p["INDIGO"])),
    ]
    tarjetas = ""
    for k, titulo, desc, img in mods:
        if k in ruta:
            tarjetas += (f'<a class="cd" href="#" data-ir="{ruta[k]}"><span class="b">{titulo}</span><span class="d">{desc}</span>'
                         f'<small>Abrir ›</small><div class="th">{img}</div></a>')
        else:
            tarjetas += (f'<div class="cd fijo"><span class="b">{titulo}</span><span class="d">{desc}</span>'
                         f'<small class="mut">Se genera desde un backtester</small><div class="th">{img}</div></div>')
    logo = _logo(p["SIDETXT"], p["VIOLETA"] if oscuro else p["ORQ"])
    sombra_panel = "" if oscuro else f"box-shadow:0 4px 14px {p['GLOW']};"   # sombra suave solo de día
    css = f"""*{{box-sizing:border-box;margin:0;padding:0}}
html,body{{background:transparent;}}
body{{font-family:"Source Sans","Source Sans Pro","Source Sans 3","Segoe UI",system-ui,sans-serif;color:{p['TEXTO']};padding:{MARCO}px 0;}}
.w{{display:grid;grid-template-columns:{PANEL}% 1fr;gap:28px;height:{ALTO}px;}}
.pn{{background:{p['SIDE']};border-radius:22px;color:{p['SIDETXT']};display:flex;flex-direction:column;justify-content:center;
  padding:0 6%;{sombra_panel}}}
.pn h1{{font-size:38px;font-weight:800;letter-spacing:-.03em;margin-top:14px;line-height:1.05;}}
.g{{display:grid;grid-template-columns:1fr 1fr;grid-template-rows:1fr 1fr;gap:28px;}}
.cd{{background:{p['CARD']};border-radius:18px;padding:26px 28px 22px;box-shadow:0 6px 22px {p['SHADOW']};display:flex;flex-direction:column;
  text-decoration:none;color:inherit;min-height:0;transition:transform .15s,box-shadow .15s;}}
a.cd{{cursor:pointer;}}a.cd:hover{{transform:translateY(-3px);box-shadow:0 12px 28px {p['SHADOW']};}}
.b{{font-size:21px;font-weight:700;letter-spacing:-.01em;display:block;}}
.d{{font-size:15px;color:{p['SUAVE']};display:block;margin-top:4px;line-height:1.35;}}
small{{display:block;font-size:15px;color:{p['INDIGO']};margin-top:12px;font-weight:700;}}small.mut{{color:{p['SUAVE']};font-weight:500;opacity:.85;}}
.th{{margin-top:auto;}}
@media (max-width:900px){{.w{{grid-template-columns:1fr;height:auto}}.pn{{height:160px}}.g{{grid-template-columns:1fr}}.cd{{min-height:240px}}}}"""
    js = """
(function(){
  var P = window.parent, D = null;
  try { D = P.document; } catch(e) {}
  if (D) {   // misma tipografía que el resto de la app: se copian las fuentes de la página
    try {
      var css = [];
      for (var i = 0; i < D.styleSheets.length; i++) {
        try { var rs = D.styleSheets[i].cssRules; for (var j = 0; j < rs.length; j++) { if (rs[j].type === 5) css.push(rs[j].cssText); } } catch(e) {}
      }
      var st = document.createElement("style"); st.textContent = css.join("\\n"); document.head.appendChild(st);
    } catch(e) {}
  }
  document.querySelectorAll("a[data-ir]").forEach(function(a){
    a.addEventListener("click", function(ev){
      ev.preventDefault();
      var ruta = a.getAttribute("data-ir");
      if (D) {
        var enl = Array.prototype.slice.call(D.querySelectorAll('[data-testid="stSidebarNav"] a, nav a')).filter(function(x){
          var h = (x.getAttribute("href") || "").replace(/\\/+$/, ""); return h.endsWith("/" + ruta) || h === ruta; })[0];
        if (enl) { enl.click(); return; }
        P.location.href = P.location.pathname.replace(/[^\\/]*$/, "") + ruta + P.location.search;
      }
    });
  });
})();"""
    return f'<!doctype html><html><head><meta charset="utf-8"><style>{css}</style></head><body><div class="w"><div class="pn">{logo}<h1>ACPTester</h1></div><div class="g">{tarjetas}</div></div><script>{js}</script></body></html>'


_CSS = """<style>
[data-testid="stSidebar"],[data-testid="stSidebarCollapsedControl"],[data-testid="collapsedControl"],[data-testid="stExpandSidebarButton"]{display:none !important;}
[data-testid="stMain"] :is(.block-container,[data-testid="stMainBlockContainer"]){max-width:1280px;padding-top:0 !important;padding-bottom:0 !important;margin-top:-3rem !important;}
</style>"""


def render(rutas: dict) -> None:
    p = ui.TEMAS[ui.TEMA]
    st.markdown(_CSS.replace("@ALTO@", str(ALTO + 2 * MARCO)), unsafe_allow_html=True)
    components.html(html(p, rutas, ui.TEMA == "oscuro"), height=ALTO + 2 * MARCO)
