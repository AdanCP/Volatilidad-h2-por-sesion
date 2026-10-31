"""Pruebas de los componentes visuales (no necesitan Streamlit)."""
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
        ui.chips([("a", 1)]),
    ]


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
