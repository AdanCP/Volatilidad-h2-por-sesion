"""Convierte guia_campos.md en una pagina HTML autonoma (un solo archivo) para abrirla aparte, en el navegador.

Solo entiende la parte de Markdown que usa la guia: titulos (#, ##, ###), listas con guion o numeradas (con sangria de a 2
espacios), parrafos, **negrita**, *cursiva* y `codigo`. No necesita ninguna libreria externa."""
import html as _h
import re

_CSS = """
:root{--bg:#eef0fb;--card:#fff;--txt:#1f2340;--mut:#7a7f9d;--acc:#4c4fe0;--rosa:#ff4fa3;--vio:#7c5cf0;--line:#e3e6f6}
@media (prefers-color-scheme:dark){:root{--bg:#0e1126;--card:#181b3b;--txt:#e9ebff;--mut:#9aa0cc;--acc:#9aa0ff;--line:#2a2f5e}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--txt);font:16px/1.6 Inter,"Segoe UI",system-ui,sans-serif}
.cab{background:linear-gradient(185deg,#4b3fd1 0%,#6a4fe6 55%,#8a63f2 100%);color:#fff;padding:34px 24px}
.cab h1{max-width:852px;margin:0 auto;font-size:2.1rem;font-weight:800;letter-spacing:-.02em}
.cab p{max-width:852px;margin:6px auto 0;color:rgba(255,255,255,.85)}
main{max-width:900px;margin:0 auto;padding:22px 24px 70px}
nav{background:var(--card);border-radius:16px;padding:14px 22px;margin:0 0 26px;box-shadow:0 6px 22px rgba(60,64,140,.10)}
nav b{display:block;margin-bottom:6px}
nav a{display:block;padding:3px 0;color:var(--acc);text-decoration:none}nav a:hover{text-decoration:underline}
h2{font-size:1.45rem;margin:38px 0 10px;padding-bottom:6px;border-bottom:3px solid transparent;border-image:linear-gradient(90deg,var(--rosa),var(--vio)) 1;scroll-margin-top:12px}
h3{font-size:1.1rem;margin:24px 0 6px;color:var(--acc)}
p{margin:8px 0}ul,ol{margin:6px 0;padding-left:22px}li{margin:5px 0}
code{background:var(--line);border-radius:5px;padding:1px 6px;font-size:.92em}
"""


def _inline(t: str) -> str:
    t = _h.escape(t, quote=False)
    t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    return re.sub(r"(?<![\*\w])\*(?!\s)(.+?)(?<!\s)\*(?![\*\w])", r"<em>\1</em>", t)


def _cuerpo(md: str):
    out, indice, pila = [], [], []          # pila: etiquetas de listas abiertas ("ul"/"ol"), una por nivel
    for linea in md.splitlines():
        m = re.match(r"^(\s*)(?:([-*])|(\d+)\.)\s+(.*)$", linea)
        if m:
            nivel = len(m.group(1)) // 2
            tag = "ul" if m.group(2) else "ol"
            while len(pila) > nivel + 1:
                out.append(f"</li></{pila.pop()}>")
            if len(pila) == nivel + 1:
                out.append("</li>")
            while len(pila) < nivel + 1:
                pila.append(tag)
                out.append(f"<{tag}>")
            out.append("<li>" + _inline(m.group(4)))
            continue
        while pila:
            out.append(f"</li></{pila.pop()}>")
        if not linea.strip():
            continue
        t = re.match(r"^(#{1,3})\s+(.*)$", linea)
        if t:
            niv, txt = len(t.group(1)), t.group(2).strip()
            if niv == 2:
                ancla = f"s{len(indice) + 1}"
                indice.append((ancla, txt))
                out.append(f'<h2 id="{ancla}">{_inline(txt)}</h2>')
            else:
                out.append(f"<h3>{_inline(txt)}</h3>")
        else:
            out.append(f"<p>{_inline(linea.strip())}</p>")
    while pila:
        out.append(f"</li></{pila.pop()}>")
    return "\n".join(out), indice


def convertir(md: str, titulo: str = "Guía de cada campo", subtitulo: str = "") -> str:
    """Pagina HTML completa (sin recursos externos) con la guia y un indice de las secciones."""
    cuerpo, indice = _cuerpo(md)
    nav = ("<nav><b>Secciones</b>" + "".join(f'<a href="#{a}">{_inline(t)}</a>' for a, t in indice) + "</nav>") if indice else ""
    sub = f"<p>{_h.escape(subtitulo)}</p>" if subtitulo else ""
    return (f'<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f"<title>{_h.escape(titulo)}</title><style>{_CSS}</style></head><body>"
            f'<header class="cab"><h1>{_h.escape(titulo)}</h1>{sub}</header><main>{nav}{cuerpo}</main></body></html>')
