"""Actualización del POS por red local (LAN/WLAN).

La estación consulta al servidor (SERVER_URL) qué setup hay disponible en la
carpeta de updates, lo descarga, verifica su MD5 y lo ejecuta en modo
silencioso (Inno Setup). El servidor central se actualiza a sí mismo dejando
el setup en %APPDATA%\\PosLaLoma\\updates.
"""

import hashlib
import json
import re
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

from config import Config, appdata_dir

_UPDATE_TIMEOUT = 30


class UpdateError(Exception):
    """Falla al consultar, descargar o instalar una actualización."""


def version_key(version: str) -> tuple:
    """'1.2.3' -> (1, 2, 3) para comparar versiones."""
    parts = re.findall(r"\d+", str(version or "0"))
    return tuple(int(p) for p in parts[:3])


def _get(url: str, timeout: int = _UPDATE_TIMEOUT) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": f"POS-LaLoma/{Config.APP_VERSION}"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except (urllib.error.URLError, OSError) as exc:
        raise UpdateError(
            f"No se pudo conectar con el servidor en {Config.SERVER_URL}.") from exc


def consultar_actualizaciones() -> dict:
    """Consulta /api/update/info y devuelve el dict del servidor."""
    url = f"{Config.SERVER_URL}/api/update/info"
    try:
        data = json.loads(_get(url).decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise UpdateError("El servidor respondió un formato inesperado.") from exc
    if not isinstance(data, dict):
        raise UpdateError("El servidor respondió un formato inesperado.")
    return data


def setup_mas_nuevo(info: dict) -> dict | None:
    """Elige el setup más reciente por versión en el nombre (PosLaLoma_Setup_X.Y.Z.exe)."""
    setups = info.get("setups") or []
    mejores = []
    for setup in setups:
        match = re.search(r"(\d+)\.(\d+)\.(\d+)", str(setup.get("filename", "")))
        if not match:
            continue
        version = ".".join(match.groups())
        mejores.append((version_key(version), version, setup))
    if not mejores:
        return None
    mejores.sort(key=lambda item: item[0], reverse=True)
    return {**mejores[0][2], "version": mejores[0][1]}


def hay_actualizacion(info: dict) -> tuple[bool, str, dict | None]:
    """(hay_actualizacion, version_nueva, setup). El servidor manda la suya."""
    servidor = str(info.get("server_version", "") or "")
    setup = setup_mas_nuevo(info)
    if setup is None:
        return False, servidor, None
    nueva = setup["version"]
    if version_key(nueva) <= version_key(Config.APP_VERSION):
        return False, servidor, None
    return True, nueva, setup


def descargar_setup(setup: dict, destino: Path) -> Path:
    """Descarga el setup del servidor, verifica el MD5 y devuelve la ruta."""
    destino.mkdir(parents=True, exist_ok=True)
    ruta = destino / str(setup["filename"])
    url = f"{Config.SERVER_URL}/api/update/download/{setup['filename']}"
    data = _get(url, timeout=300)
    md5_esperado = str(setup.get("md5") or "").lower()
    if md5_esperado and hashlib.md5(data).hexdigest() != md5_esperado:
        raise UpdateError("El archivo descargado no coincide con el MD5 esperado.")
    ruta.write_bytes(data)
    return ruta


def instalar_setup(ruta: Path) -> None:
    """Ejecuta el setup en modo silencioso (Inno Setup)."""
    if not ruta.is_file():
        raise UpdateError("El archivo de actualización no existe.")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        subprocess.Popen(
            [str(ruta), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"],
            creationflags=flags,
            close_fds=True,
        )
    except OSError as exc:
        raise UpdateError(f"No se pudo ejecutar el instalador: {exc}") from exc


def carpeta_updates_local() -> Path:
    """Carpeta local donde se descargan los setups (misma que la del servidor)."""
    return Path(Config.UPDATE_DIR)
