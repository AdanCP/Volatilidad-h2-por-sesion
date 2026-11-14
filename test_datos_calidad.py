"""Hora del historial corrida, aviso de salto de huso y control de velas corruptas."""
import numpy as np
import pandas as pd
import pytest

import data


def _semanas(desde="2023-01-02", n_sem=60, apertura=1, cierre=23, paso="5min", seed=0):
    """Velas lunes a viernes (apertura el lunes a `apertura`:00, cierre el viernes a las `cierre`:55)."""
    rng = np.random.default_rng(seed)
    partes = []
    for s in range(n_sem):
        lun = pd.Timestamp(desde) + pd.Timedelta(weeks=s)
        partes.append(pd.date_range(lun + pd.Timedelta(hours=apertura), lun + pd.Timedelta(days=4, hours=cierre, minutes=55), freq=paso))
    idx = partes[0].append(partes[1:])
    n = len(idx)
    c = 2000 + np.cumsum(rng.normal(0, 0.5, n))
    return pd.DataFrame({"Open": c, "High": c + 0.3, "Low": c - 0.3, "Close": c, "Volume": rng.integers(80, 120, n).astype(float),
                         "Spread": np.full(n, 0.2)}, index=idx)


# ---------------- corregir_hora
def test_resta_horas_solo_antes_de_la_fecha():
    df = _semanas(n_sem=6, apertura=2)
    corte = "2023-01-23"
    out, info = data.corregir_hora(df, [(corte, 1)])
    antes, despues = df.index < pd.Timestamp(corte), df.index >= pd.Timestamp(corte)
    assert (out.index[: antes.sum()] == df.index[antes] - pd.Timedelta(hours=1)).all()
    assert (out.index[antes.sum():] == df.index[despues]).all()
    assert info["velas_corridas"] == int(antes.sum()) and info["duplicadas_quitadas"] == 0
    assert out.index.is_monotonic_increasing and not out.index.duplicated().any()


def test_sin_tramos_o_con_cero_horas_no_cambia_nada():
    df = _semanas(n_sem=3)
    assert data.corregir_hora(df, [])[0].equals(df) and data.corregir_hora(df, [("2023-01-10", 0)])[0].equals(df)


def test_no_modifica_el_original():
    df = _semanas(n_sem=3)
    copia = df.copy()
    data.corregir_hora(df, [("2023-01-17", 1)])
    assert df.equals(copia)


def test_duplicados_en_el_empalme_se_reducen_a_una_y_gana_la_vela_del_tramo_correcto():
    # corrigiendo hacia adelante (-1 = sumar 1 h) las ultimas velas del tramo viejo pisan a las primeras del nuevo
    viejo = pd.date_range("2024-03-01 20:00", periods=6, freq="h")                    # hasta 01:00 (antes del corte)
    nuevo = pd.date_range("2024-03-02 02:00", periods=4, freq="h")
    df = pd.DataFrame({"Open": 1.0, "High": 1.0, "Low": 1.0, "Close": np.r_[np.full(6, 10.0), np.full(4, 99.0)], "Volume": 1.0, "Spread": 0.0},
                      index=viejo.append(nuevo))
    out, info = data.corregir_hora(df, [("2024-03-02 02:00", -1)])
    assert out.index.is_monotonic_increasing and not out.index.duplicated().any()
    assert info["duplicadas_quitadas"] == 1 and len(out) == len(df) - 1
    assert out.loc["2024-03-02 02:00", "Close"] == 99.0                                # gana la vela del tramo ya correcto
    assert out.loc["2024-03-01 21:00", "Close"] == 10.0                                # las del tramo viejo quedaron una hora adelante


def test_restar_horas_nunca_genera_duplicados():
    df = _semanas(n_sem=10)
    assert data.corregir_hora(df, [("2023-02-13", 1)])[1]["duplicadas_quitadas"] == 0


def test_dos_tramos_se_acumulan():
    df = _semanas(n_sem=6, apertura=3)
    out, _ = data.corregir_hora(df, [("2023-01-23", 1), ("2023-01-09", 1)])
    primera = df.index[0]
    assert out.index[0] == primera - pd.Timedelta(hours=2)


# ---------------- detectar_salto_horario
def test_detecta_el_salto_de_huso_y_la_fecha():
    a = _semanas("2023-01-02", n_sem=30, apertura=2)                                     # apertura semanal a las 02:00
    b = _semanas("2023-07-31", n_sem=30, apertura=1)                                     # luego a las 01:00
    df = pd.concat([a, b])
    cambios = data.detectar_salto_horario(df)
    assert len(cambios) == 1 and cambios[0]["de"] == 2 and cambios[0]["a"] == 1 and cambios[0]["horas"] == -1
    assert str(cambios[0]["fecha"].date()) == "2023-07-31"


def test_sin_salto_no_avisa_y_ignora_semanas_sueltas():
    df = _semanas(n_sem=60, apertura=1)
    assert data.detectar_salto_horario(df) == []
    suelta = pd.concat([_semanas("2023-01-02", n_sem=20, apertura=1), _semanas("2023-05-22", n_sem=2, apertura=0),
                        _semanas("2023-06-05", n_sem=20, apertura=1)])               # 2 semanas distintas (cambios de horario desalineados)
    assert data.detectar_salto_horario(suelta) == []


def test_despues_de_corregir_ya_no_se_detecta_el_salto():
    a = _semanas("2023-01-02", n_sem=30, apertura=2)
    b = _semanas("2023-07-31", n_sem=30, apertura=1)
    df = pd.concat([a, b])
    out, _ = data.corregir_hora(df, [("2023-07-31", 1)])
    assert data.detectar_salto_horario(out) == []


# ---------------- velas sospechosas
def _con_corruptas(anio_malo=2021):
    df = _semanas("2021-01-04", n_sem=40, apertura=1)
    df2 = _semanas("2022-01-03", n_sem=40, apertura=1, seed=3)
    df = pd.concat([df, df2])
    m = (df.index.minute == 0)
    sel = m & (df.index.year == anio_malo)
    df.loc[sel, "Volume"] *= 12
    df.loc[sel, "High"] += 6.0
    df.loc[sel, "Low"] -= 6.0
    df.loc[sel, "Spread"] = 0.0
    return df, int(sel.sum())


def test_marca_las_velas_horarias_corruptas_y_no_las_normales():
    df, n_mal = _con_corruptas()
    r = data.velas_sospechosas(df)
    assert r["sospechosas"] == n_mal and r["anios"][0]["anio"] == 2021 and r["anios"][0]["minuto"] == 0
    assert r["mascara"].sum() == n_mal
    assert data.calidad(df)["sospechosas"]["velas"] == n_mal


def test_un_pico_aislado_por_noticia_no_se_marca():
    df = _semanas("2021-01-04", n_sem=40)
    df.iloc[3000, df.columns.get_loc("Volume")] *= 30
    df.iloc[3000, df.columns.get_loc("High")] += 20
    assert data.velas_sospechosas(df)["sospechosas"] == 0


def test_datos_limpios_no_avisan():
    assert data.calidad(_semanas(n_sem=40))["sospechosas"] == {"velas": 0, "anios": [], "spread0_minutos": []}


def test_excluir_velas_saca_solo_las_marcadas():
    df, n_mal = _con_corruptas()
    r = data.velas_sospechosas(df)
    out = data.excluir_velas(df, r["mascara"])
    assert len(out) == len(df) - n_mal and not data.velas_sospechosas(out)["sospechosas"]


def test_detecta_spread_cero_agrupado_en_un_minuto():
    df = _semanas("2021-01-04", n_sem=60)
    df.loc[df.index.minute == 0, "Spread"] = 0.0
    df.loc[df.index.minute != 0, "Spread"] = 0.3
    df.loc[(df.index.minute != 0) & (np.arange(len(df)) % 5 == 0), "Spread"] = 0.0                # algo de ruido normal
    r = data.velas_sospechosas(df)
    assert r["spread0_minutos"] and all(x["minuto"] == 0 for x in r["spread0_minutos"])
