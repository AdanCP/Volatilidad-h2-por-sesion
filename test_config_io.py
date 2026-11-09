import json
import config_io as c


def test_slug():
    assert c.slug("EMA corta") == "ema_corta"
    assert c.slug("Pérdida diaria máx. (%)") == "perdida_diaria_max"
    assert c.slug("¿¿??") == "campo"


def test_number_input_posicional_y_tipos():
    # (min, max, value, step): el valor guardado se castea al tipo del original
    a, k = c.con_valor("number_input", (2, 500, 13), {"key": "x"}, 21.0)
    assert a == (2, 500, 21) and isinstance(a[2], int)
    a, k = c.con_valor("number_input", (0.0, 100.0, 5.0, 0.5), {}, 7)
    assert a[2] == 7.0 and isinstance(a[2], float)


def test_number_input_value_por_nombre_y_limites():
    a, k = c.con_valor("number_input", (0.0,), {"value": 0.3}, 0.9)
    assert k["value"] == 0.9
    a, k = c.con_valor("number_input", (2, 100, 14), {}, 5000)       # fuera de rango: se recorta
    assert a[2] == 100
    a, k = c.con_valor("number_input", (0.00001,), {"value": 0.01}, "no es numero")
    assert k["value"] == 0.01


def test_checkbox_radio_select_multiselect():
    a, k = c.con_valor("checkbox", (True,), {}, False)
    assert a[0] is False
    a, k = c.con_valor("checkbox", (), {}, True)
    assert k["value"] is True
    a, k = c.con_valor("radio", (["A", "B", "C"],), {"horizontal": True}, "C")
    assert k["index"] == 2
    a, k = c.con_valor("selectbox", (["A", "B"], 0), {}, "B")
    assert a[1] == 1
    a, k = c.con_valor("radio", (["A", "B"],), {}, "Z")               # opción que ya no existe: se ignora
    assert "index" not in k
    a, k = c.con_valor("multiselect", (["T", "L", "N"], ["T", "L", "N"]), {}, ["L", "X"])
    assert a[1] == ["L"]


def test_ida_y_vuelta():
    vals = {"ema_corta": 13, "rr": 2.5, "filtro_sma": True, "sesiones_permitidas": ["Tokio"]}
    b = c.a_bytes("ema", vals)
    out, err = c.leer(b, "ema")
    assert err is None and out == vals
    assert json.loads(b)["app"] == "ACPTester"


def test_rechazos():
    assert c.leer(b"no json", "ema")[1]
    assert c.leer(b'{"hola": 1}', "ema")[1]
    out, err = c.leer(c.a_bytes("ema", {"a": 1}), "sma")
    assert out is None and "EMA" in err


def test_fechas_y_texto():
    from datetime import date
    a, k = c.con_valor("date_input", (date(2020, 1, 1),), {}, "2023-05-02")
    assert a[0] == date(2023, 5, 2)
    a, k = c.con_valor("date_input", ((date(2020, 1, 1), date(2021, 1, 1)),), {}, ["2022-01-01", "2022-06-30"])
    assert a[0] == (date(2022, 1, 1), date(2022, 6, 30))
    a, k = c.con_valor("date_input", (date(2020, 1, 1),), {}, 5)              # tipo incorrecto: se ignora
    assert a[0] == date(2020, 1, 1)
    a, k = c.con_valor("text_input", ("",), {}, "US30, GER40")
    assert a[0] == "US30, GER40"


def test_fechas_ida_y_vuelta():
    from datetime import date
    b = c.a_bytes("ema", {"desde": date(2021, 3, 4), "periodo": (date(2022, 1, 1), date(2022, 2, 1))})
    out, err = c.leer(b, "ema")
    assert out == {"desde": "2021-03-04", "periodo": ["2022-01-01", "2022-02-01"]}


def test_nombre_archivo():
    assert c.nombre_archivo("", "auto") == "auto.json"
    assert c.nombre_archivo("  mi prueba ", "auto") == "mi prueba.json"
    assert c.nombre_archivo("x.json", "auto") == "x.json"
    assert c.nombre_archivo("a/b\\c:d?", "auto") == "a_b_c_d.json"
    assert c.nombre_archivo("../..", "auto") == "auto.json"
