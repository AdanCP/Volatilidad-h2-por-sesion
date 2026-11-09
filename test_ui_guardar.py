import ui_estilo as vis
import ui_guardar as ug


def test_html_incrusta_nombre_y_contenido():
    p = vis.TEMAS[vis.TEMA]
    h = ug.html(p, "ACPTester_config_EMA_13-34.json", '{"a": "</script>x", "b": 1}')
    assert "ACPTester_config_EMA_13-34.json" in h
    assert "showSaveFilePicker" in h
    assert "</script>x" not in h                      # no puede cortar el script del contenido
    assert p["BTNG"] in h
