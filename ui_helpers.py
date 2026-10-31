"""Funciones puras de la interfaz (sin Streamlit) para poder probarlas."""
import os
import re

# Familias que se muestran en la interfaz -> etiquetas de data.CANDIDATOS
FAMILIAS = {
    "Metales": ["oro", "plata"],
    "Cripto": ["btc"],
    "Forex mayores": ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD", "NZDUSD"],
    "Índices": ["Dow Jones", "Nasdaq 100", "S&P 500", "DAX", "FTSE 100", "Nikkei"],
}


def agrupar_hallados(hallados: dict):
    """hallados: etiqueta -> nombre real en el servidor (o None).
    Devuelve ({familia: [(etiqueta, nombre)]}, [etiquetas no encontradas])."""
    grupos, faltan = {}, []
    for familia, etiquetas in FAMILIAS.items():
        items = [(e, hallados[e]) for e in etiquetas if hallados.get(e)]
        faltan += [e for e in etiquetas if not hallados.get(e)]
        if items:
            grupos[familia] = items
    return grupos, faltan


def unir_simbolos(elegidos, otros_texto: str = "") -> list:
    """Junta los elegidos con los escritos a mano (separados por coma, punto y coma o espacio), sin repetir."""
    extra = [s.strip() for s in re.split(r"[,;\s]+", otros_texto or "") if s.strip()]
    salida = []
    for s in list(elegidos) + extra:
        if s not in salida:
            salida.append(s)
    return salida


def simbolo_desde_archivo(nombre: str) -> str:
    """'XAUUSD_H1.csv' -> 'XAUUSD_H1' (el nombre del archivo identifica al simbolo)."""
    return os.path.splitext(os.path.basename(nombre))[0].strip() or "SIMBOLO"
