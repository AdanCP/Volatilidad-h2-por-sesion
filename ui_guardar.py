"""Botón «Guardar configuración»: abre el cuadro «Guardar como» del navegador (elegís carpeta y nombre).
Funciona en Chrome y Edge (API de acceso a archivos). En otros navegadores, o si el cuadro no se puede abrir,
descarga el archivo directamente con el nombre sugerido."""
import json

ALTO = 82          # alto del bloque: el botón mide 40 px y deja lugar para que la sombra no se corte (igual que «Cargar»)
BOTON = 40


def _js_str(x: str) -> str:
    return json.dumps(x, ensure_ascii=False).replace("</", "<\\/")


def html(p: dict, nombre: str, texto: str, etiqueta: str = "💾 Guardar configuración") -> str:
    css = f"""
html,body{{margin:0;background:transparent;overflow:hidden;}}
body{{font-family:"Source Sans","Source Sans Pro","Source Sans 3","Segoe UI",system-ui,sans-serif;padding:20px 18px 22px;box-sizing:border-box;}}
button{{display:block;width:100%;height:{BOTON}px;border:1px solid rgba(255,255,255,.55);border-radius:12px;cursor:pointer;
  background:{p['BTNG']};color:{p['BTNTXT']};font:inherit;font-weight:700;font-size:.9rem;line-height:1.6;
  box-shadow:0 4px 14px {p['GLOW']};transition:filter .15s,transform .15s,box-shadow .15s;}}
button:hover{{filter:brightness(1.2) saturate(1.12);transform:translateY(-2px);
  box-shadow:0 0 0 2px {p['SIDETXT']},0 3px 8px {p['GLOW']};}}
button:active{{transform:translateY(0);filter:brightness(.97);}}
button:focus-visible{{outline:2px solid {p['SIDETXT']};outline-offset:2px;}}
"""
    js = """
(function(){
  var NOMBRE = %s, TEXTO = %s, ETQ = %s;
  var P = window.parent, D = null;
  try { D = P.document; } catch(e) {}
  if (D) {   // misma tipografía que el resto de la app
    try {
      var css = [];
      for (var i = 0; i < D.styleSheets.length; i++) {
        try { var rs = D.styleSheets[i].cssRules; for (var j = 0; j < rs.length; j++) { if (rs[j].type === 5) css.push(rs[j].cssText); } } catch(e) {}
      }
      var st = document.createElement("style"); st.textContent = css.join("\\n"); document.head.appendChild(st);
    } catch(e) {}
  }
  var b = document.getElementById("g");
  function aviso(t){ b.textContent = t; setTimeout(function(){ b.textContent = ETQ; }, 1800); }
  function descargar(blob){
    var a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = NOMBRE;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(function(){ URL.revokeObjectURL(a.href); }, 3000);
    aviso("✔ Descargado");
  }
  b.addEventListener("click", async function(){
    var blob = new Blob([TEXTO], {type: "application/json"});
    if (window.showSaveFilePicker) {
      try {
        var h = await window.showSaveFilePicker({suggestedName: NOMBRE,
          types: [{description: "Configuración de ACPTester", accept: {"application/json": [".json"]}}]});
        var w = await h.createWritable(); await w.write(blob); await w.close();
        aviso("✔ Guardado"); return;
      } catch (e) {
        if (e && e.name === "AbortError") return;      // el usuario cerró el cuadro: no se hace nada
      }                                                  // cualquier otro error: descarga directa
    }
    descargar(blob);
  });
})();
""" % (_js_str(nombre), _js_str(texto), _js_str(etiqueta))
    return (f'<!doctype html><html><head><meta charset="utf-8"><style>{css}</style></head><body>'
            f'<button id="g" type="button">{etiqueta}</button><script>{js}</script></body></html>')


def render(p: dict, nombre: str, contenido: bytes) -> None:
    import streamlit.components.v1 as components
    components.html(html(p, nombre, contenido.decode("utf-8")), height=ALTO)
