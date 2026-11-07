"""Boton «Descargar resultados (PDF)»: imprime la zona de resultados tal como se ve en pantalla.

El navegador no puede bajar un PDF solo, asi que el boton (con el estilo de los de arriba) abre el cuadro de impresion con todo lo de arriba de los
resultados oculto (barra lateral, parametros, etc.) y la pagina lista para imprimir en horizontal. Ahi se elige
«Guardar como PDF». El nombre sugerido del archivo es el titulo que se le pasa.
Es solo del lado del navegador: no toca el calculo ni lo que se muestra en pantalla.
"""
import json

CLASE_MARCA = "res-inicio"

# CSS que rige SOLO al imprimir. Streamlit mide el alto de la pagina y scrollea por dentro: para que se imprima todo hay que soltarlo.
CSS_IMPRESION = """
@media print {
  @page { size: A4 landscape; margin: 8mm; }
  * { -webkit-print-color-adjust: exact !important; print-color-adjust: exact !important; }
  html, body, .stApp, [data-testid="stApp"], [data-testid="stAppViewContainer"], [data-testid="stMain"], section.main,
  [data-testid="stMainBlockContainer"], .block-container { height: auto !important; min-height: 0 !important; overflow: visible !important; }
  [data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"], [data-testid="stHeader"], [data-testid="stToolbar"],
  [data-testid="stBottom"], [data-testid="stStatusWidget"], footer { display: none !important; }
  [data-testid="stMain"], section.main { margin: 0 !important; padding: 0 !important; width: 100% !important; }
  [data-testid="stMainBlockContainer"], .block-container { max-width: 100% !important; padding: 0 4px !important; }
  [data-testid="stElementContainer"], [data-testid="stHorizontalBlock"], [data-testid="stExpander"] { break-inside: avoid; }
  .pdf-oculto { display: none !important; }
}
"""

_JS = """
(function () {
  var TITULO = %(titulo)s;
  var P = window.parent, D = P.document;
  function estilo() {
    if (D.getElementById("pdf-pantalla-css")) return;
    var s = D.createElement("style");
    s.id = "pdf-pantalla-css";
    s.textContent = %(css)s;
    D.head.appendChild(s);
  }
  function esBloquePrincipal(el) {
    var p = el.parentElement;
    return !!p && p.matches('[data-testid="stVerticalBlock"]') && !!p.parentElement &&
           p.parentElement.matches('[data-testid="stMainBlockContainer"], .block-container');
  }
  window.imprimirResultados = function () {
    estilo();
    var ocultos = [];
    var marca = D.querySelector(".%(marca)s");
    if (marca) {
      var top = marca;
      while (top && top.parentElement && !esBloquePrincipal(top)) top = top.parentElement;
      if (top && top.parentElement) {
        var h = top.previousElementSibling;
        while (h) { h.classList.add("pdf-oculto"); ocultos.push(h); h = h.previousElementSibling; }
      }
    }
    var marco = window.frameElement;               // este mismo boton no sale en el PDF
    if (marco) { marco.classList.add("pdf-oculto"); ocultos.push(marco); }
    var tituloAntes = D.title;
    D.title = TITULO;
    var limpiar = function () {
      ocultos.forEach(function (e) { e.classList.remove("pdf-oculto"); });
      D.title = tituloAntes;
      P.removeEventListener("afterprint", limpiar);
    };
    P.addEventListener("afterprint", limpiar);
    setTimeout(function () { P.print(); }, 150);
  };
})();
"""


def marca_html() -> str:
    """Marca invisible: lo que esta ARRIBA de ella no se imprime."""
    return f'<div class="{CLASE_MARCA}" style="height:0;margin:0;padding:0"></div>'


def css_fondo(bg: str) -> str:
    """Fija el color de fondo de la pagina al imprimir. Sin esto, algunos navegadores imprimen el fondo con el tema oscuro de Streamlit
    (casi negro) aunque en pantalla se vea el color de la app. Al ir en el fondo de la raiz (html), tambien tapa los margenes del papel."""
    return ("@media print { html, body, .stApp, [data-testid=\"stApp\"], [data-testid=\"stAppViewContainer\"], [data-testid=\"stMain\"], "
            "section.main, [data-testid=\"stMainBlockContainer\"], .block-container, [data-testid=\"stVerticalBlock\"] "
            "{ background: " + bg + " !important; } }\n")


def lanzar_html(titulo_pdf: str, fondo: str = "#ffffff") -> str:
    """Pagina invisible (alto 0) que abre el cuadro de impresion apenas se carga. Se muestra solo justo despues de apretar el boton
    «Descargar resultados (PDF)», que es un boton comun de Streamlit con el mismo estilo que los de arriba."""
    seguro = lambda x: json.dumps(x).replace("<", "\\u003c")          # nada que cierre el <script> desde el titulo
    js = _JS % {"titulo": seguro(titulo_pdf), "css": seguro(CSS_IMPRESION + css_fondo(fondo)), "marca": CLASE_MARCA}
    return f"<!doctype html><html><body><script>{js}\nsetTimeout(window.imprimirResultados, 600);</script></body></html>"
