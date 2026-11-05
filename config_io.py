"""Guardar y cargar la configuración del backtester (archivo .json). Sin dependencias de Streamlit: se puede probar suelto."""
import json
import re
from datetime import date, time
import unicodedata
from datetime import datetime

APP = "ACPTester"
VERSION = 1
TIPOS = ("number_input", "slider", "checkbox", "radio", "selectbox", "multiselect", "date_input", "text_input", "time_input")


def slug(texto: str) -> str:
    """Nombre estable de un campo a partir de su título («EMA corta» -> «ema_corta»)."""
    t = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "_", t).strip("_")[:48] or "campo"


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def con_valor(tipo: str, a: tuple, k: dict, v):
    """Devuelve (args, kwargs) del widget con `v` como valor inicial. Si `v` no corresponde, devuelve los originales."""
    a, k = list(a), dict(k)
    try:
        if tipo in ("number_input", "slider"):
            if not _num(v):
                return tuple(a), k
            lo = a[0] if len(a) > 0 else k.get("min_value")
            hi = a[1] if len(a) > 1 else k.get("max_value")
            orig = a[2] if len(a) > 2 else k.get("value")
            if orig is None:
                orig = lo                     # sin valor inicial, Streamlit parte del mínimo
            if orig is None or isinstance(orig, bool):
                return tuple(a), k
            nv = float(v) if isinstance(orig, float) else int(round(v))
            if lo is not None and nv < lo:
                nv = type(nv)(lo)
            if hi is not None and nv > hi:
                nv = type(nv)(hi)
            if len(a) > 2:
                a[2] = nv
            else:
                k["value"] = nv
        elif tipo == "checkbox":
            if not isinstance(v, bool):
                return tuple(a), k
            if len(a) > 0:
                a[0] = v
            else:
                k["value"] = v
        elif tipo in ("radio", "selectbox"):
            opciones = list(a[0] if len(a) > 0 else k.get("options", []))
            if v not in opciones:
                return tuple(a), k
            if len(a) > 1:
                a[1] = opciones.index(v)
            else:
                k["index"] = opciones.index(v)
        elif tipo == "text_input":
            orig = a[0] if len(a) > 0 else k.get("value", "")
            if not isinstance(v, str):
                return tuple(a), k
            if len(a) > 0:
                a[0] = v
            else:
                k["value"] = v
        elif tipo == "time_input":
            if not isinstance(v, str) or len(v) < 5:
                return tuple(a), k
            nv = time(int(v[:2]), int(v[3:5]))
            if len(a) > 0:
                a[0] = nv
            else:
                k["value"] = nv
        elif tipo == "date_input":
            orig = a[0] if len(a) > 0 else k.get("value")
            if isinstance(orig, (tuple, list)):                      # período: (desde, hasta)
                if not isinstance(v, list) or not 1 <= len(v) <= 2:
                    return tuple(a), k
                nv = tuple(date.fromisoformat(str(x)[:10]) for x in v)
            else:
                if not isinstance(v, str):
                    return tuple(a), k
                nv = date.fromisoformat(v[:10])
            if len(a) > 0:
                a[0] = nv
            else:
                k["value"] = nv
        elif tipo == "multiselect":
            opciones = list(a[0] if len(a) > 0 else k.get("options", []))
            if not isinstance(v, list):
                return tuple(a), k
            sel = [x for x in v if x in opciones]
            if len(a) > 1:
                a[1] = sel
            else:
                k["default"] = sel
    except (TypeError, ValueError, IndexError):
        return tuple(a), dict(k)
    return tuple(a), k


def a_bytes(tipo: str, valores: dict, nota: str = "") -> bytes:
    def _json(o):
        if isinstance(o, time):
            return f"{o.hour:02d}:{o.minute:02d}"
        return o.item() if hasattr(o, "item") else str(o)
    paquete = {"app": APP, "tipo": tipo, "version": VERSION,
               "guardado": datetime.now().strftime("%Y-%m-%d %H:%M"), "nota": nota, "valores": valores}
    return json.dumps(paquete, ensure_ascii=False, indent=1, default=_json).encode("utf-8")


def leer(contenido: bytes, tipo: str):
    """(valores, None) si el archivo sirve; (None, mensaje) si no."""
    try:
        d = json.loads(contenido.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None, "El archivo no es una configuración válida (no se pudo leer)."
    if not isinstance(d, dict) or d.get("app") != APP or not isinstance(d.get("valores"), dict):
        return None, "El archivo no es una configuración guardada por ACPTester."
    if d.get("tipo") != tipo:
        return None, (f"Esta configuración es del backtester de {str(d.get('tipo')).upper()}; "
                      f"cargala en esa página (estás en la de {tipo.upper()}).")
    return d["valores"], None


def nombre_archivo(escrito: str, por_defecto: str) -> str:
    """Nombre de archivo seguro (sin rutas ni caracteres prohibidos) y con la extensión .json."""
    base = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', "_", str(escrito or "")).strip(" ._")
    if base.lower().endswith(".json"):
        base = base[:-5].rstrip(" ._")
    return (base or por_defecto)[:120] + ".json"
