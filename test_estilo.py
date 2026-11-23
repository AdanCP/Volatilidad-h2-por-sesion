"""Pruebas de los componentes visuales (no necesitan Streamlit)."""
import os
import re
import sys
from html.parser import HTMLParser

import ui_estilo as ui


class Balance(HTMLParser):
    VACIOS = {"line", "circle", "rect", "path", "stop", "br", "polygon", "polyline", "meta", "img"}

    def __init__(self):
        super().__init__()
        self.pila = []

    def handle_starttag(self, tag, attrs):
        if tag not in self.VACIOS:
            self.pila.append(tag)

    def handle_startendtag(self, tag, attrs):
        pass

    def handle_endtag(self, tag):
        if tag in self.VACIOS:
            return
        assert self.pila and self.pila.pop() == tag, f"etiqueta desbalanceada: {tag}"


def svgs(h):
    """SVG que van dentro de <img src="data:...">, ya decodificados."""
    import base64
    return [base64.b64decode(m).decode("utf-8") for m in re.findall(r'data:image/svg\+xml;base64,([A-Za-z0-9+/=]+)', h)]


def balanceado(h):
    b = Balance()
    b.feed(h)
    b.close()
    assert not b.pila, f"sin cerrar: {b.pila}"


def todos():
    return [
        ui.barra_superior("T", "s", [("a", 1)]), ui.kpi("l", "1", "s"), ui.tarjeta("t", "<p>x</p>", "nota", "der"),
        ui.anillo(40, "t", "s", 33.3), ui.medidor(60, "t", "s"),
        ui.barras_divergentes([("a", 1.0), ("b", -0.5, ui.VIOLETA), ("c", float("nan"))]),
        ui.embudo([("a", 100), ("b", 50), ("c", 10)]), ui.curva_equity([0, 1, 2, 1, 3], "a", "b", 2),
        ui.barras_verticales([(2020, 0.3, "10 op."), (2021, -0.2, "5 op.")]), ui.insight("t", "<b>x</b>"),
        ui.chips([("a", 1)]), ui.equivalencia_precio("t", "US$1", "US$5", "1 lotes", [("X", "1", "5"), ("Y", "2", None)], "n"),
    ]


def test_equivalencia_precio():
    h = ui.equivalencia_precio("Equivalencia en precio", "US$175,00", "US$875,00", "0,17 lotes",
                               [("XAUUSD", "10,29", "51,47"), ("A<B", "1,00", None)], "nota")
    assert "XAUUSD" in h and "TP (precio)" in h and "A&lt;B" in h and h.count("<table") == h.count("</table>") == 1
    h2 = ui.equivalencia_precio("t", "US$1", "US$5", "1 lotes", [("X", "1", None)])
    assert "TP (precio)" not in h2 and "US$5" not in h2


def test_html_balanceado():
    for h in todos():
        balanceado(h)
        for s in svgs(h):
            balanceado(s)


def test_los_graficos_van_como_imagen_y_no_como_svg_en_linea():
    # st.html suele eliminar <svg> en línea: tiene que ir como <img> con data-URI
    for h in (ui.anillo(40, "t", "s"), ui.medidor(60, "t"), ui.curva_equity([0, 1, 2]), ui.barras_verticales([(1, 1.0, "x")])):
        assert "<svg" not in h and "<img" in h and svgs(h) and 'xmlns="http://www.w3.org/2000/svg"' in svgs(h)[0]


def test_formato_numeros():
    assert ui.n(1234.5, 2) == "1.234,50" and ui.n(0.4, 1, True) == "+0,4" and ui.n(None) == "–"
    assert ui.n(-3, 0, True) == "-3"


def test_escapa_html_de_nombres_de_simbolo():
    h = ui.barras_divergentes([("<img src=x onerror=alert(1)>", 1.0)]) + ui.kpi("<b>", "<i>", "<u>")
    assert "<img" not in h and "&lt;img" in h and "<i>" not in h


def test_casos_vacios_y_extremos():
    assert "Sin operaciones" in ui.curva_equity([])
    assert "Sin datos" in ui.barras_verticales([])
    assert ui.anillo(float("nan"), "t", "s") and ui.medidor(250, "t") and ui.embudo([])
    assert ui.curva_equity([1.0]) and ui.curva_equity([0.0, 0.0, 0.0])      # sin división por cero
    assert len(re.findall("<circle", svgs(ui.anillo(50, "t", "s"))[0])) == 2


def test_css_sin_lineas_en_blanco_y_con_interruptor():
    assert "\n\n" not in ui.css() and "stSidebar" in ui.css()
    ui.SIDEBAR_MORADO = False
    try:
        assert "stSidebar" not in ui.css()
    finally:
        ui.SIDEBAR_MORADO = True


def test_barras_verticales_deja_lugar_al_valor_negativo():
    h = svgs(ui.barras_verticales([("a", -1.0, "x"), ("b", 1.0, "y")]))[0]
    ys = [float(v) for v in re.findall(r'<text x="[\d.]+" y="([\d.]+)" text-anchor="middle" font-size="11"', h)]
    assert ys and max(ys) < 230 - 24            # el número de la barra negativa queda sobre el pie


def test_tabla_df_formato_signo_y_recorte():
    import pandas as pd
    df = pd.DataFrame({"exp_R": [0.5, -0.25, float("nan")], "n": [1500, 2, 3], "ok": [True, False, True],
                       "s": ["<b>x</b>", "a", "b"], "f": pd.to_datetime(["2020-01-02 03:04"] * 3)})
    h = ui.tabla_df(df, dec=2)
    assert 'class="pos"' in h and 'class="neg"' in h and "0,50" in h and "-0,25" in h
    assert ">1500<" in h and ">sí<" in h and ">no<" in h and "2020-01-02 03:04" in h and "–" in h
    assert "<b>x</b>" not in h and "&lt;b&gt;" in h
    grande = ui.tabla_df(pd.DataFrame({"a": range(1000)}), max_filas=50)
    assert grande.count("<tr>") == 51 and "primeras 50 de 1000" in grande
    balanceado(h)


def test_temas_claro_y_oscuro():
    import ui_estilo as v
    try:
        v.set_tema("oscuro"); o = v.css(); a = v.anillo(50, "x", "y")
        v.set_tema("claro"); c = v.css()
    finally:
        v.set_tema("claro")
    import re
    assert not re.findall(r"@[A-Z]+@", o) and not re.findall(r"@[A-Z]+@", c)
    assert "#0e1126" in o and "#0e1126" not in c and "#eef0fb" in c
    assert "\n\n" not in o and "\n\n" not in c
    assert 'class="sec"' in v.titulo_seccion("Hola", "sub")


if __name__ == "__main__":
    pruebas = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    for nombre, f in pruebas:
        f()
        print("OK ", nombre)
    print(f"\n{len(pruebas)} tests pasaron.")


def test_circulo_de_carga():
    import ui_estilo as v
    h = v.cargando("Calculando <b>")
    assert "anillo-carga" in h and "&lt;b&gt;" in h
    c = v.css()
    assert "giro-carga" in c and "@NEG@" not in c and "@VIO@" not in c


def test_campo_numerico_del_area_principal():
    import ui_estilo as ui
    for t in ("claro", "oscuro"):
        ui.set_tema(t)
        c = ui.css()
        assert '[data-testid="stMain"] [data-testid="stNumberInput"] :is([data-testid="stNumberInputStepUp"],[data-testid="stNumberInputStepDown"]){background:linear-gradient(135deg,' in c
        assert "@ACC@" not in c and "@VIO@" not in c and "\n\n" not in c
        assert ui.TEMAS[t]["VIOLETA"] in c        # el borde usa el violeta del tema
    ui.set_tema("claro")


def _lum(hexa):
    h = hexa.lstrip("#")
    c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def _contraste(a, b):
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def test_cinco_estilos_con_modo_noche_completos_y_legibles():
    import ui_estilo as v
    assert list(v.ESTILOS) == ["moderno", "sobrio", "pastel", "oceano", "atardecer"]
    claves = set(v.ESTILOS["moderno"]["claro"])
    try:
        for e, modos in v.ESTILOS.items():
            assert set(modos) == {"claro", "oscuro"} and e in v.NOMBRES_ESTILO
            for m, p in modos.items():
                assert set(p) == claves, (e, m)
                v.set_tema(m, e)
                c = v.css()
                assert not re.findall(r"@[A-Z]+@", c) and "\n\n" not in c, (e, m)
                assert p["BG"] in c and p["SIDE"] in c and p["BTNG"] in c
                # texto principal y secundario legibles sobre el fondo y las tarjetas
                assert _contraste(p["TEXTO"], p["BG"]) >= 7 and _contraste(p["TEXTO"], p["CARD"]) >= 7, (e, m)
                assert _contraste(p["SUAVE"], p["CARD"]) >= 3.5, (e, m)
                # texto de la barra lateral sobre sus colores extremos del degradado
                for col in re.findall(r"#[0-9a-fA-F]{6}", p["SIDE"]):
                    assert _contraste(p["SIDETXT"], col) >= 3.5, (e, m, col)
                # texto de botones sobre sus colores
                for col in re.findall(r"#[0-9a-fA-F]{6}", p["BTNG"]):
                    assert _contraste(p["BTNTXT"], col) >= 2.7, (e, m, col)
                # lo positivo y lo negativo se distinguen entre si y se leen sobre la tarjeta
                assert p["INDIGO"] != p["ROSA"] and _contraste(p["INDIGO"], p["CARD"]) >= 2.2 and _contraste(p["ROSA"], p["CARD"]) >= 2.2, (e, m)
                # el veredicto y los componentes se arman en cada estilo
                assert "insight" in v.veredicto_caja("a", "b", "<i>c</i>", "ok") and "<svg" not in v.anillo(10, "x", "y")
    finally:
        v.set_tema("claro", "moderno")


def test_set_tema_cambia_colores_de_componentes_y_vuelve_al_moderno():
    import ui_estilo as v
    try:
        v.set_tema("claro", "oceano")
        assert v.INDIGO == v.ESTILOS["oceano"]["claro"]["INDIGO"] and v.ESTILO == "oceano"
        assert v.TEMAS["oscuro"]["BG"] == v.ESTILOS["oceano"]["oscuro"]["BG"]
        v.set_tema("oscuro", "estilo_inexistente")
        assert v.ESTILO == "moderno" and v.TEMA == "oscuro"
    finally:
        v.set_tema("claro", "moderno")
    assert v.ROSA == "#ff4fa3" and v.TEMAS["claro"]["BG"] == "#eef0fb"


def test_anillo_acepta_alto_minimo():
    import ui_estilo as v
    assert "min-height:284px" in v.anillo(20, "t", "s", 16.7, min_alto=284)
    assert "min-height" not in v.anillo(20, "t", "s", 16.7)



def test_boton_pdf_de_resultados():
    import pdf_pantalla as pp
    h = pp.lanzar_html('Resultados "XAU" <1>')
    assert "imprimirResultados" in h and pp.CLASE_MARCA in h and "P.print()" in h and "setTimeout(window.imprimirResultados" in h
    assert "<1>" not in h.split("<script>")[1] and "\\u003c1>" in h                # el titulo va escapado dentro del script
    assert "@media print" in pp.CSS_IMPRESION and "stSidebar" in pp.CSS_IMPRESION and "landscape" in pp.CSS_IMPRESION
    assert pp.CLASE_MARCA in pp.marca_html()
    f = pp.lanzar_html("x", "#eef0fb")
    assert "background: #eef0fb !important" in f and "stAppViewContainer" in f          # el fondo se fija al color de la app
    import ui_estilo as v
    assert ".st-key-fila_bt_pdf{margin-bottom:14px;}" in v.css()                          # alineado con los chips de la barra
    assert ".st-key-fila_bt_pdf button[kind=\"secondary\"]" in v.css()                # mismo estilo que los botones de arriba


def test_guia_html_autonoma_con_indice_y_listas_balanceadas():
    import guia_html as g
    md = "### Intro\nTexto con **negrita**, *cursiva* y `cod`.\n\n## 1. Uno\n- a\n  - b\n  1. c\n- d\n\n## 2. Dos <x>\nFin"
    h = g.convertir(md, "T")
    assert h.startswith("<!doctype html>") and h.count("<h2") == 2 and 'href="#s2"' in h
    assert "<strong>negrita</strong>" in h and "<em>cursiva</em>" in h and "<code>cod</code>" in h and "&lt;x&gt;" in h
    for t in ("ul", "ol", "li"):
        assert h.count(f"<{t}>") == h.count(f"</{t}>")
    real = g.convertir(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "guia_campos.md"), encoding="utf-8").read())
    assert real.count("<li>") == real.count("</li>") and "**" not in real and real.count("<h2") >= 8


def test_menus_anchos_css_js_e_interruptor():
    import menu_ancho
    css = ui.css()
    assert 'details[data-ancho="1"]' in css and "#velo-menu-ancho" in css and "\n\n" not in css and not re.search(r"@[A-Z0-9]+@", css)
    ui.SIDEBAR_MORADO = False
    try:
        assert "data-ancho" not in ui.css()                       # sin barra lateral de estilo no hay panel
    finally:
        ui.SIDEBAR_MORADO = True
    assert menu_ancho.js_flag(True).count("true") == 1 and menu_ancho.js_flag(False).count("false") == 1
    assert menu_ancho.JS.count("{") == menu_ancho.JS.count("}") and "data-ancho" in menu_ancho.JS and "Escape" in menu_ancho.JS
    src = open("app.py", encoding="utf-8").read()
    assert 'key="menus_anchos"' in src and "menu_ancho.JS" in src and "menu_ancho.js_flag" in src


def test_submenus_como_tarjetas_en_el_panel_ancho():
    css = ui.css()
    assert 'st-key-sub_' in css and ".sep-filtro" in css and "\n\n" not in css
    src = open("app_backtest.py", encoding="utf-8").read()
    assert 'def _sub(grupo=""):' in src and src.count("with _sub():") >= 30
    ast_ok = __import__("ast").parse(src)
    assert ast_ok


def test_grilla_real_en_el_panel_ancho_y_hover_de_menus_cerrados():
    import menu_ancho
    css = ui.css()
    assert "grid-template-columns:repeat(var(--ancho-cols,4)" in css and 'data-tj="1"' in css and "column-width" not in css
    assert "--ancho-cols" in menu_ancho.JS and "data-celda" in menu_ancho.JS and menu_ancho.JS.count("{") == menu_ancho.JS.count("}")
    assert "summary:hover" in css and "details:not([open])" in css and "\n\n" not in css and not re.search(r"@[A-Z0-9]+@", css)


def test_instrumento_vacio_y_tarjetas_de_los_menus_de_datos():
    src = open("app_backtest.py", encoding="utf-8").read()
    assert "multiselect(familia, opciones, [])" in src and 'etiqueta == "oro"' not in src      # el instrumento arranca vacío
    assert src.count('with _sub("d"):') >= 8                                                   # menús 1 y 2 en tarjetas
    assert 'key="acc_senal"' in src and 'key="acc_atr"' in src                                 # EMA/dirección y ATR dentro de «Parámetros»
    assert src.index('_acc_cab_opc("atr"') < src.index('_acc_css(_acc_lista, _acc_activos, "sg", ("pb", "rtam"))')


def test_tarjetas_de_los_menus_6_a_9_y_todo_cerrado_al_arrancar():
    src = open("app_backtest.py", encoding="utf-8").read()
    assert 'setdefault(_clave_abierto("sg"), None)' in src and 'setdefault(_clave_abierto("sg"), "sl")' not in src      # ninguna tarjeta abierta al arrancar
    assert 'key="acc_srv"' in src and 'key="acc_pp"' in src and 'key="acc_pg"' in src and 'key="acc_rt"' in src
    assert src.index('_acc_cab_opc("srv"') < src.index('"ses", tuple(cio.slug(n_) for n_ in SESIONES))')                # el CSS del acordeón va después de la tarjeta
    assert src.count('_sep_filtro()\n        with _sub():\n            perd_') >= 2 and "st.divider()" not in src.split('8. Reglas de la cuenta')[1].split('Trading de noticias')[0]
    nota = src.index('st.caption("No detectados automáticamente')
    assert nota < src.index('elegidos += _W(st).multiselect(familia, opciones, [])')       # la nota ya no va dentro de la tarjeta de Índices


def test_panel_ancho_explicaciones_chicas_y_tarjetas_de_la_fila_del_mismo_alto():
    import menu_ancho
    css = ui.css()
    assert "stCaptionContainer" in css and "font-size:.74rem" in css and "\n\n" not in css
    assert "minHeight" in menu_ancho.JS and "st-key-acc_" in menu_ancho.JS and menu_ancho.JS.count("{") == menu_ancho.JS.count("}")


def test_menu_abierto_no_se_sale_del_boton():
    css = ui.css()
    assert '[data-testid="stExpander"]{overflow:hidden;}' in css and "border-radius:inherit" in css and "\n\n" not in css


def test_hover_de_tarjetas_y_boton_parametros_y_costos_en_tarjetas():
    css = ui.css()
    assert ':not([data-vacia="1"]):hover{background:color-mix' in css and ":is(:active,:focus-visible)" in css and "\n\n" not in css
    assert not re.search(r"@[A-Z0-9]+@", css)
    src = open("app_backtest.py", encoding="utf-8").read()
    costos = src.split('. Costos", expanded=False)')[1].split("Control de sobreajuste")[0]
    assert costos.count("with _sub():") == 2


def test_ruptura_todas_las_tarjetas_con_parametros_para_que_midan_igual():
    src = open("app_backtest.py", encoding="utf-8").read()
    for c in ("rbol", "rent", "rsl", "rtp", "rhor", "rtam"):
        assert f'key="acc_{c}"' in src
    assert '"pb", "rtam"' in src                                  # el filtro de tamaño se abre solo al activarlo, como los otros
    horario = src.split("**Horario (hora de")[1].split("Filtro de tamaño del rango")[0]
    assert horario.index('st.error("La última entrada') > horario.index('key="acc_rhor"') and "                if not rup_ap + rup_dur <= rup_ult:" in horario   # las validaciones quedan a la vista


def test_fondo_del_panel_ancho_color_profundo_y_vuelta_atras():
    import re as _re
    assert "background:@PANEL@" in __import__("menu_ancho").CSS
    ant, ant_est, ant_tema = ui.PANEL_PROFUNDO, ui.ESTILO, ui.TEMA
    try:
        for est in ui.ESTILOS:
            for tema in ("claro", "oscuro"):
                ui.set_tema(tema, est)
                ui.PANEL_PROFUNDO = True
                css = ui.css()
                assert not _re.search(r"@[A-Z0-9]+@", css)
                p = ui.TEMAS[tema]
                esperado = p["PROF"] if ui._luminancia(p["SIDETXT"]) > 0.6 else p["SIDE"]
                assert f"background:{esperado};border-left" in css
        ui.set_tema("claro", "moderno")
        ui.PANEL_PROFUNDO = False
        assert f"background:{ui.TEMAS['claro']['SIDE']};border-left" in ui.css()          # apagado: igual que antes
    finally:
        ui.PANEL_PROFUNDO = ant
        ui.set_tema(ant_tema, ant_est)
