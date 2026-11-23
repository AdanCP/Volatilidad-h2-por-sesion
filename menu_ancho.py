"""Menús anchos de la barra lateral: al abrir un menú, sus campos se despliegan en un panel ancho hacia la derecha,
encima de los resultados, en varias columnas (menos scroll). Vale para todos los menús de la barra lateral de todas las páginas.

Cómo funciona: un script en la página (JS) marca el menú abierto con data-ancho="1" y calcula dónde empieza el panel (el borde
derecho de la barra lateral); el CSS hace el resto. Sin el script (o con el interruptor «Menús anchos» apagado) no se marca nada y
los menús se ven como siempre. Se apoya en la estructura interna de Streamlit (<details>/<summary>), igual que el acordeón de app.py.
"""

# Se agrega al CSS de la barra lateral (ui_estilo.css). Sin líneas en blanco: Markdown corta el bloque HTML en la primera.
CSS = """
/* Menús anchos: el menú abierto (marcado por menu_ancho.JS) muestra sus campos en un panel a la derecha de la barra lateral */
.ancho-anc{transform:none !important;filter:none !important;backdrop-filter:none !important;perspective:none !important;contain:none !important;will-change:auto !important;}
[data-testid="stSidebar"] details[data-ancho="1"] > :not(summary){position:fixed;top:var(--ancho-y,0px);left:var(--ancho-x,0px);
  width:var(--ancho-w,720px);height:100vh;box-sizing:border-box;overflow-y:auto;overflow-x:hidden;padding:4.2rem 2rem 2.5rem 2rem;
  background:@PANEL@;border-left:1px solid @VEILB@;box-shadow:14px 0 34px rgba(10,14,30,.30);z-index:999995;}
.menu-ancho-abierto .st-key-ctl_portada{display:none !important;}
[data-testid="stSidebar"] details[data-ancho="1"] > :not(summary)::before{content:attr(data-titulo);position:absolute;top:1.15rem;left:7.2rem;right:2rem;
  font-size:1.25rem;font-weight:800;color:@SIDETXT@;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
/* Grilla real: columnas fijas (las calcula el script según el ancho), filas alineadas arriba; los campos sueltos de un menú con tarjetas ocupan una fila propia a todo el ancho */
[data-testid="stSidebar"] details[data-ancho="1"] > :not(summary) > [data-testid="stVerticalBlock"]{display:grid !important;grid-template-columns:repeat(var(--ancho-cols,4),minmax(0,1fr));
  gap:1rem 1.2rem;align-items:start;align-content:start;}
[data-testid="stSidebar"] details[data-ancho="1"] > :not(summary) > [data-testid="stVerticalBlock"] > *{width:100% !important;min-width:0;margin:0 !important;}
[data-testid="stSidebar"] details[data-ancho="1"] > :not(summary) > [data-testid="stVerticalBlock"][data-tj="1"] > [data-celda="suelta"]{grid-column:1 / -1;}
[data-testid="stSidebar"] details[data-ancho="1"] > :not(summary) > [data-testid="stVerticalBlock"] > [data-celda="vacia"]{display:none !important;}
/* Submenús (contenedores sub_N de app_backtest._sub): una tarjeta igual para cada uno; el título y el botón de parámetros comparten la fila de arriba */
[data-testid="stSidebar"] details[data-ancho="1"] .sep-filtro,
[data-testid="stSidebar"] details[data-ancho="1"] [data-testid="stElementContainer"]:has(> .sep-filtro),
[data-testid="stSidebar"] details[data-ancho="1"] [data-testid="stElementContainer"]:has(.sep-filtro){display:none !important;}
[data-testid="stSidebar"] details[data-ancho="1"] :is([class*=" st-key-sub_"],[class^="st-key-sub_"]){background:@VEIL@;border:1px solid @VEILB@;border-radius:14px;
  padding:.8rem 1rem 1rem;margin:0;min-height:8.5rem;box-sizing:border-box;display:flex !important;flex-direction:column;gap:.7rem;
  overflow-wrap:normal;word-break:normal;}
[data-testid="stSidebar"] details[data-ancho="1"] :is([class*=" st-key-sub_"],[class^="st-key-sub_"])[data-vacia="1"]{padding:0 !important;border:0 !important;margin:0 !important;min-height:0 !important;background:transparent !important;}
[data-testid="stSidebar"] details[data-ancho="1"] :is([class*=" st-key-sub_"],[class^="st-key-sub_"]) > *{width:100% !important;min-width:0;}
[data-testid="stSidebar"] details[data-ancho="1"] [class*="st-key-acc_btn_"] button{background:transparent !important;border:1px solid @VEILB@ !important;box-shadow:none !important;
  min-height:0;padding:.25rem .8rem;border-radius:999px;}
[data-testid="stSidebar"] details[data-ancho="1"] [class*="st-key-acc_btn_"] button{cursor:pointer;transition:background .15s,border-color .15s;}
[data-testid="stSidebar"] details[data-ancho="1"] [class*="st-key-acc_btn_"] button:hover{background:color-mix(in srgb,@SIDETXT@ 22%,transparent) !important;border-color:@SIDETXT@ !important;transform:none;box-shadow:none !important;}
[data-testid="stSidebar"] details[data-ancho="1"] [class*="st-key-acc_btn_"] button:is(:active,:focus-visible){background:color-mix(in srgb,@SIDETXT@ 34%,transparent) !important;border-color:@SIDETXT@ !important;box-shadow:none !important;}
/* las tarjetas reaccionan al pasar el mouse igual que los menús de la lista: fondo más claro, borde marcado y un leve levantado */
[data-testid="stSidebar"] details[data-ancho="1"] :is([class*=" st-key-sub_"],[class^="st-key-sub_"]){transition:background .15s,border-color .15s,transform .15s,box-shadow .15s;}
[data-testid="stSidebar"] details[data-ancho="1"] :is([class*=" st-key-sub_"],[class^="st-key-sub_"]):not([data-vacia="1"]):hover{background:color-mix(in srgb,@SIDETXT@ 20%,transparent);border-color:@SIDETXT@;box-shadow:0 4px 14px @GLOW@;transform:translateY(-2px);}
/* explicaciones (los textos chicos que no son un campo): letra más chica dentro del panel */
[data-testid="stSidebar"] details[data-ancho="1"] [data-testid="stCaptionContainer"],
[data-testid="stSidebar"] details[data-ancho="1"] [data-testid="stCaptionContainer"] :is(p,span,small){font-size:.74rem !important;line-height:1.3 !important;}
#velo-menu-ancho{position:fixed;top:0;bottom:0;right:0;left:var(--ancho-x,0px);background:rgba(10,14,30,.42);z-index:999990;display:none;cursor:pointer;}
#cerrar-menu-ancho{position:fixed;top:.9rem;left:calc(var(--ancho-x,0px) + 1.4rem);z-index:999996;display:none;padding:.4rem .85rem;border-radius:10px;
  border:1px solid @VEILB@;background:@CARD@;color:@TXT@;font:700 .85rem "Source Sans","Source Sans Pro",sans-serif;cursor:pointer;box-shadow:0 2px 8px @SHADOW@;}
#cerrar-menu-ancho:hover{border-color:@ACC@;}
.menu-ancho-abierto #velo-menu-ancho,.menu-ancho-abierto #cerrar-menu-ancho{display:block;}
"""

# Script de la página (corre dentro del iframe de components.html y trabaja sobre la página que lo contiene).
JS = """<script>
const w = window.parent, d = w.document;
if (!w.__menuAnchoListo) {
  w.__menuAnchoListo = true;
  const raiz = d.documentElement;
  const mk = (id, tag) => { let e = d.getElementById(id); if (!e) { e = d.createElement(tag); e.id = id; d.body.appendChild(e); } return e; };
  const abierto = () => {
    const s = d.querySelector('[data-testid="stSidebar"]');
    return s ? Array.prototype.slice.call(s.querySelectorAll("details[open]")).filter((x) => x.querySelector(":scope > summary"))[0] : null;
  };
  const cerrarMenu = () => { const a = abierto(); if (a) a.querySelector(":scope > summary").click(); };
  const limpiar = () => {
    d.querySelectorAll("details[data-ancho]").forEach((x) => x.removeAttribute("data-ancho"));
    d.querySelectorAll(".ancho-anc").forEach((x) => x.classList.remove("ancho-anc"));
    raiz.classList.remove("menu-ancho-abierto");
  };
  const aplicar = () => {
    const s = d.querySelector('[data-testid="stSidebar"]');
    const det = (w.__menuAncho !== false) && s ? abierto() : null;
    if (!det) { limpiar(); return; }
    const cuerpo = det.querySelector(":scope > :not(summary)");
    if (!cuerpo) { limpiar(); return; }
    d.querySelectorAll("details[data-ancho]").forEach((x) => { if (x !== det) x.removeAttribute("data-ancho"); });
    const x0 = Math.round(s.getBoundingClientRect().right);
    const ancho = Math.max(420, w.innerWidth - x0);              // el panel tapa todo el fondo a la derecha de la barra lateral
    const st = raiz.style;
    st.setProperty("--ancho-cols", String(Math.max(1, Math.min(4, Math.floor((ancho - 64) / 240)))));   // columnas de la grilla: hasta 4, menos si el panel es angosto
    st.setProperty("--ancho-x", x0 + "px");
    st.setProperty("--ancho-w", ancho + "px");
    const sum = det.querySelector(":scope > summary");
    const tp = sum.querySelector("p");
    cuerpo.setAttribute("data-titulo", ((tp ? tp.textContent : (sum.innerText || sum.textContent || "")) || "").replace(/^\\s*keyboard_arrow_\\w+\\s*/, "").trim());
    for (let e = det.parentElement; e && e !== s.parentElement; e = e.parentElement) e.classList.add("ancho-anc");
    det.setAttribute("data-ancho", "1");
    det.querySelectorAll('[class*="st-key-sub_"]').forEach((c) => {
      const hay = Array.prototype.some.call(c.children, (h) => h.getBoundingClientRect().height > 6);
      if (hay) c.removeAttribute("data-vacia"); else c.setAttribute("data-vacia", "1");
    });
    const bloque = cuerpo.querySelector(':scope > [data-testid="stVerticalBlock"]');
    if (bloque) {
      let hayTj = false;
      Array.prototype.forEach.call(bloque.children, (h) => {
        const tj = h.matches('[class*="st-key-sub_"]') ? h : h.querySelector('[class*="st-key-sub_"]');
        if (!tj) { h.setAttribute("data-celda", "suelta"); return; }
        if (tj.getAttribute("data-vacia") === "1") { h.setAttribute("data-celda", "vacia"); return; }
        h.setAttribute("data-celda", "tarjeta"); hayTj = true;
      });
      if (hayTj) bloque.setAttribute("data-tj", "1"); else bloque.removeAttribute("data-tj");
      // Tarjetas de una misma fila: todas del alto de la más alta de las cerradas; la que tiene su acordeón abierto crece sola.
      const fila = {};
      Array.prototype.forEach.call(bloque.children, (h) => {
        if (h.getAttribute("data-celda") !== "tarjeta") return;
        const tj = h.matches('[class*="st-key-sub_"]') ? h : h.querySelector('[class*="st-key-sub_"]');
        tj.style.minHeight = "";
        const ac = tj.querySelector('[class*="st-key-acc_"]:not([class*="st-key-acc_btn_"])');
        const abierta = !!ac && ac.offsetHeight > 0;
        const k = h.offsetTop;                      // no cambia con el levantado del hover
        (fila[k] = fila[k] || []).push({ tj: tj, alto: tj.offsetHeight, abierta: abierta });
      });
      Object.keys(fila).forEach((k) => {
        const cerr = fila[k].filter((x) => !x.abierta);
        const m = cerr.reduce((a, x) => Math.max(a, x.alto), 0);
        if (m > 0) cerr.forEach((x) => { x.tj.style.minHeight = m + "px"; });
      });
    }
    raiz.classList.add("menu-ancho-abierto");
    // Si un contenedor con transform/filter desplaza el panel (la posición fija pasa a ser relativa a él), se corrige con lo medido.
    const r = cuerpo.getBoundingClientRect(), y0 = parseFloat(st.getPropertyValue("--ancho-y")) || 0;
    if (Math.abs(x0 - r.left) > 1) st.setProperty("--ancho-x", (x0 + (x0 - r.left)) + "px");
    if (Math.abs(r.top) > 1) st.setProperty("--ancho-y", (y0 - r.top) + "px");
  };
  const velo = mk("velo-menu-ancho", "div"), cerrar = mk("cerrar-menu-ancho", "button");
  cerrar.type = "button"; cerrar.textContent = "✕ Cerrar";
  velo.addEventListener("click", cerrarMenu); cerrar.addEventListener("click", cerrarMenu);
  d.addEventListener("keydown", (ev) => { if (ev.key === "Escape" && raiz.classList.contains("menu-ancho-abierto")) cerrarMenu(); });
  let pend = false;
  const pedir = () => { if (pend) return; pend = true; w.requestAnimationFrame(() => { pend = false; try { aplicar(); } catch (e) { limpiar(); } }); };
  new w.MutationObserver(pedir).observe(d.body, { subtree: true, childList: true, attributes: true, attributeFilter: ["open"] });
  w.addEventListener("resize", pedir);
  w.setInterval(pedir, 500);
  pedir();
}
</script>"""


def js_flag(activo: bool) -> str:
    """Script mínimo que le dice a la página si los menús anchos están encendidos (interruptor en el botón de Estilo)."""
    return "<script>window.parent.__menuAncho = " + ("true" if activo else "false") + ";</script>"
