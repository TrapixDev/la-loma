"""Configuración global del POS La Loma.

MODO DE RED:
  - MODE = "server": la base de datos vive en la PC servidor. Ejecute allí
    `python server.py` (o el .exe con --server) y en cada estación configure
    SERVER_URL apuntando a esa PC (ej. http://192.168.1.10:8000). El primer
    arranque pide crear el PIN inicial.
  - MODE = "local": todo en una sola PC, sin servidor. Útil para pruebas.

RUTAS DE DATOS:
  - Modo fuente (python main.py):  ./data (junto al código).
  - Modo empaquetado (.exe):       %APPDATA%\\PosLaLoma\\data
    De esta forma los datos nunca dependen de la carpeta del programa y las
    actualizaciones no los tocan.

CONFIG.INI (opcional):
  %APPDATA%\\PosLaLoma\\config.ini  (o ./config.ini en modo fuente) permite
  cambiar SERVER_URL, STATION, DOCS_PATH y MODE sin tocar el código:

      [pos]
      server_url = http://192.168.1.10:8000
      station = CAJA1
      docs_path = \\\\SERVIDOR\\documentos
      mode = server

  DOCS_PATH es la carpeta compartida en red donde se archivan XML+PDF de las
  facturas (todas las cajas guardan ahí). Si está vacía o no es accesible, se
  usa Documentos\\PosLaLoma y, como último recurso, %APPDATA%\\PosLaLoma\\documentos.
"""

import os
import sys
from configparser import ConfigParser
from pathlib import Path


APP_VERSION = "1.0.0"
IS_FROZEN = bool(getattr(sys, "frozen", False))


def appdata_dir() -> Path:
    """Raíz de datos del usuario: %APPDATA%\\PosLaLoma."""
    base = Path(os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming")))
    return base / "PosLaLoma"


def _data_dir() -> Path:
    """Directorio donde viven pos.db, respaldos y fotos."""
    if IS_FROZEN:
        return appdata_dir() / "data"
    return Path(__file__).resolve().parent / "data"


def _updates_dir() -> Path:
    """Carpeta donde el servidor guarda los setup para actualizar por red."""
    if IS_FROZEN:
        return appdata_dir() / "updates"
    return Path(__file__).resolve().parent / "updates"


def _read_overrides() -> dict:
    """Lee config.ini (APPDATA primero, proyecto como respaldo) y devuelve
    los valores como strings; el primer archivo que defina una clave gana."""
    overrides: dict[str, str] = {}
    files = []
    if IS_FROZEN:
        files.append(appdata_dir() / "config.ini")
    else:
        files.append(Path(__file__).resolve().parent / "config.ini")
        files.append(appdata_dir() / "config.ini")
    for path in files:
        if not path.is_file():
            continue
        parser = ConfigParser()
        try:
            parser.read(path, encoding="utf-8")
        except Exception:
            continue
        if not parser.has_section("pos"):
            continue
        for key, value in parser.items("pos"):
            overrides.setdefault(key, value)
    return overrides


_OVERRIDES = _read_overrides()


def _opt(name: str) -> str:
    return _OVERRIDES.get(name, "")


class Config:
    APP_NAME = "POS - La Loma"
    APP_VERSION = APP_VERSION

    MODE = _opt("mode") or "server"
    DB_PATH = str(_data_dir() / "pos.db")
    BACKUP_DIR = str(_data_dir() / "backups")
    UPDATE_DIR = str(_updates_dir())

    # Fotos de productos: se guardan en el servidor y se cachean en cada estación.
    PRODUCT_IMAGES_DIR = str(_data_dir() / "product_images")
    IMAGE_CACHE_DIR = str(Path.home() / ".pos_la_loma" / "images")
    MAX_IMAGE_BYTES = 1_500_000
    IMAGE_MAX_SIDE = 400

    # Carpeta compartida en red para XML+PDF de facturas (p. ej. \\\\SERVIDOR\\documentos).
    # Vacía = Documentos\\PosLaLoma; si no es accesible, %APPDATA%\\PosLaLoma\\documentos.
    DOCS_PATH = _opt("docs_path")

    # En tickets cobrados en USD, mostrar también el equivalente en colones
    # bajo el total ("0" en config.ini para ocultarlo).
    MOSTRAR_EQUIVALENTE_CRC = _opt("mostrar_equivalente_crc") != "0"

    SERVER_HOST = "0.0.0.0"
    SERVER_PORT = 8000
    SERVER_URL = _opt("server_url") or "http://127.0.0.1:8000"

    STATION = _opt("station") or "CAJA1"

    SESSION_HOURS = 12
    MAX_LOGIN_ATTEMPTS = 5
    LOCKOUT_MINUTES = 15
    BACKUP_HOURS = 6
    KEEP_BACKUPS = 14

    HACIENDA_API_URL = "https://api.hacienda.go.cr"
    FE_PROVIDER_URL = ""
    DEFAULT_FE_PROVIDER_URL = "https://fe.almendro.cr"
    COMPANY = {
        "name": "Mueblería y Aserradero La Loma",
        "id": "",
        "phone": "",
        "address": "",
        "activity_code": "31021",
        "branch": "001",
        "terminal": "001",
    }
