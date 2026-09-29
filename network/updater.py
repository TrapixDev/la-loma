"""Actualización del POS por red local (LAN/WLAN).

La estación consulta al servidor (SERVER_URL) qué setup hay disponible en la
carpeta de updates, lo descarga, verifica su SHA-256 y —si hay una clave
pública configurada— la firma Ed25519 del archivo. Sin firma, la descarga solo
se acepta por HTTPS validado; nunca por HTTP ni con un hash ausente.

El servidor central se actualiza a sí mismo dejando el setup (y su `.sig`) en
%APPDATA%\\PosLaLoma\\updates.
"""

import base64
import hashlib
import json
import re
import ssl
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

from config import Config
from network.tls import contexto_cliente

_UPDATE_TIMEOUT = 30
_MAX_SETUP_BYTES = 500_000_000
_NOMBRE_VALIDO = re.compile(r"^[A-Za-z0-9_.\-]{1,120}\.exe$")


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
        with urllib.request.urlopen(
                request, timeout=timeout,
                context=contexto_cliente(Config.SERVER_URL)) as response:
            return response.read()
    except ssl.SSLError as exc:
        raise UpdateError(f"TLS: {exc}") from exc
    except urllib.error.URLError as exc:
        raise UpdateError(
            f"No se pudo conectar con el servidor en {Config.SERVER_URL}: "
            f"{exc.reason}") from exc
    except OSError as exc:
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


def _verificar_firma(data: bytes, setup: dict) -> None:
    """Exige firma Ed25519 cuando hay clave pública configurada.

    Sin clave pública, la descarga solo se acepta por HTTPS (servidor
    autenticado por certificado): nunca por HTTP ni sin hash.
    """
    clave = (Config.UPDATE_PUBLIC_KEY or "").strip()
    firma = str(setup.get("signature") or "").strip()
    if not clave:
        if not str(Config.SERVER_URL).lower().startswith("https"):
            raise UpdateError(
                "La actualización no está firmada y el servidor no usa HTTPS. "
                "Configure update_public_key (tools/generar_claves_update.py) "
                "o use HTTPS con el certificado del servidor.")
        return
    if not firma:
        raise UpdateError(
            "El setup no tiene firma digital; no se instalará. Firme el "
            "archivo con tools/firmar_setup.py.")
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PublicKey,
        )
    except ImportError as exc:
        raise UpdateError(
            "Falta el paquete 'cryptography' para verificar la firma del "
            "setup.") from exc
    try:
        clave_bytes = base64.b64decode(clave, validate=True)
        firma_bytes = base64.b64decode(firma, validate=True)
        Ed25519PublicKey.from_public_bytes(clave_bytes).verify(
            firma_bytes, data)
    except (ValueError, InvalidSignature) as exc:
        raise UpdateError(
            "La firma del setup no es válida; el archivo se rechazó.") from exc


def descargar_setup(setup: dict, destino: Path) -> Path:
    """Descarga el setup, verifica tamaño, nombre, hash y firma.

    El archivo SIEMPRE queda dentro de `destino` (nombres con rutas se
    rechazan) y el SHA-256 es obligatorio.
    """
    filename = str(setup.get("filename") or "")
    if not _NOMBRE_VALIDO.fullmatch(filename):
        raise UpdateError("El nombre del setup no es válido.")
    sha256_esperado = str(setup.get("sha256") or "").lower()
    if not re.fullmatch(r"[0-9a-f]{64}", sha256_esperado):
        raise UpdateError(
            "El servidor no publicó el SHA-256 del setup; no se descargará.")
    destino = Path(destino)
    destino.mkdir(parents=True, exist_ok=True)
    ruta = (destino / filename).resolve()
    if not ruta.is_relative_to(destino.resolve()):
        raise UpdateError("El nombre del setup intenta salir de la carpeta.")
    url = f"{Config.SERVER_URL}/api/update/download/{filename}"
    data = _get(url, timeout=300)
    if len(data) > _MAX_SETUP_BYTES:
        raise UpdateError("El setup descargado es demasiado grande.")
    if hashlib.sha256(data).hexdigest() != sha256_esperado:
        raise UpdateError(
            "El archivo descargado no coincide con el SHA-256 esperado.")
    _verificar_firma(data, setup)
    ruta.write_bytes(data)
    return ruta


def instalar_setup(ruta: Path) -> None:
    """Ejecuta el setup en modo silencioso (Inno Setup)."""
    ruta = Path(ruta)
    if not ruta.is_file() or ruta.suffix.lower() != ".exe":
        raise UpdateError("El archivo de actualización no existe.")
    if ruta.stat().st_size > _MAX_SETUP_BYTES:
        raise UpdateError("El archivo de actualización es demasiado grande.")
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
