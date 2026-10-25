"""Control del Bot Mane desde la app.

El bot corre en GitHub Actions (alertas.yml). El interruptor es la variable de
repositorio BOT_ACTIVO ("true" / "false"): la app la lee y la cambia usando la
API de GitHub, y el workflow no se ejecuta cuando vale "false".

Variables de entorno (en Render):
  GITHUB_TOKEN  token fine-grained con permisos Variables (RW) y Contents (R)
  GITHUB_REPO   "usuario/repositorio"
"""

import json
import os
from typing import Optional

import requests

VARIABLE = "BOT_ACTIVO"
ARCHIVO_ESTADO = "estado_alertas.json"
API = "https://api.github.com"


class ErrorControl(Exception):
    """Falla al hablar con GitHub (mensaje listo para mostrar al usuario)."""


def configurado() -> bool:
    return bool(os.environ.get("GITHUB_TOKEN") and os.environ.get("GITHUB_REPO"))


def _headers(raw: bool = False) -> dict:
    return {
        "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
        "Accept": "application/vnd.github.raw+json"
        if raw
        else "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _url(ruta: str) -> str:
    return f"{API}/repos/{os.environ['GITHUB_REPO']}{ruta}"


def _validar(r: requests.Response) -> None:
    if r.ok:
        return
    pistas = {
        401: "el token es inválido o venció",
        403: "el token no tiene permiso de 'Variables' (lectura y escritura)",
        404: "no se encontró el repositorio (revisá GITHUB_REPO y el acceso del token)",
    }
    pista = pistas.get(r.status_code, "error inesperado")
    raise ErrorControl(f"GitHub respondió {r.status_code}: {pista}.")


def _pedir(metodo: str, ruta: str, **kw) -> requests.Response:
    try:
        return requests.request(metodo, _url(ruta), timeout=15, **kw)
    except requests.RequestException as e:
        raise ErrorControl(f"No se pudo conectar con GitHub: {e}") from e


def leer_activo() -> bool:
    """True si el bot está activo. Sin variable creada, se considera activo."""
    r = _pedir("GET", f"/actions/variables/{VARIABLE}", headers=_headers())
    if r.status_code == 404:
        # 404 puede ser "no existe la variable" o "no tengo acceso al repo"
        _validar(_pedir("GET", "", headers=_headers()))
        return True
    _validar(r)
    return str(r.json().get("value", "")).strip().lower() != "false"


def cambiar_activo(activo: bool) -> None:
    cuerpo = {"name": VARIABLE, "value": "true" if activo else "false"}
    r = _pedir(
        "PATCH", f"/actions/variables/{VARIABLE}", headers=_headers(), json=cuerpo
    )
    if r.status_code == 404:  # primera vez: la variable todavía no existe
        r = _pedir("POST", "/actions/variables", headers=_headers(), json=cuerpo)
    _validar(r)


def ultima_vela_revisada() -> Optional[str]:
    """ISO de la última vela que procesó el bot (None si no se puede saber)."""
    try:
        r = _pedir(
            "GET", f"/contents/{ARCHIVO_ESTADO}", headers=_headers(raw=True)
        )
        if not r.ok:
            return None
        return json.loads(r.text).get("ultima_barra")
    except (ErrorControl, ValueError):
        return None
