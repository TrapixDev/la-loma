"""Arranque: asegura la estructura de datos y migra la base desde un USB.

En modo empaquetado (.exe), si %APPDATA%\\PosLaLoma\\data está vacío y existe
data\\pos.db junto al ejecutable (por ejemplo, llevado en un USB), se copia la
base, los respaldos y las fotos de productos al lugar definitivo.
"""

import shutil
import sys
from pathlib import Path

from config import Config, IS_FROZEN, appdata_dir


def _junto_al_exe() -> Path:
    """Carpeta del ejecutable (o del código, en modo fuente)."""
    if IS_FROZEN:
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def asegurar_estructura() -> None:
    """Crea las carpetas de datos (respaldos, fotos, updates)."""
    for carpeta in (Path(Config.BACKUP_DIR), Path(Config.PRODUCT_IMAGES_DIR),
                    Path(Config.UPDATE_DIR), Path(Config.DB_PATH).parent):
        carpeta.mkdir(parents=True, exist_ok=True)


def migrar_datos_si_vacio() -> bool:
    """Copia data\\pos.db + respaldos + fotos desde junto al .exe a %APPDATA%.

    Solo actúa en modo empaquetado y únicamente si el destino no tiene base.
    Devuelve True si se copió algo.
    """
    if not IS_FROZEN:
        return False
    destino = Path(Config.DB_PATH)
    if destino.is_file():
        return False
    origen = _junto_al_exe() / "data"
    if not origen.is_dir():
        return False
    copiado = False
    db_origen = origen / "pos.db"
    if db_origen.is_file():
        try:
            destino.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(db_origen, destino)
            copiado = True
        except OSError:
            pass
    backups = origen / "backups"
    if backups.is_dir():
        try:
            for archivo in backups.iterdir():
                if archivo.is_file():
                    shutil.copy2(archivo, Path(Config.BACKUP_DIR) / archivo.name)
            copiado = True
        except OSError:
            pass
    fotos = origen / "product_images"
    if fotos.is_dir():
        try:
            for archivo in fotos.iterdir():
                if archivo.is_file():
                    shutil.copy2(archivo, Path(Config.PRODUCT_IMAGES_DIR) / archivo.name)
            copiado = True
        except OSError:
            pass
    return copiado


def ruta_config_ini() -> Path:
    """Ruta del config.ini que se debe editar en cada PC."""
    return appdata_dir() / "config.ini"
