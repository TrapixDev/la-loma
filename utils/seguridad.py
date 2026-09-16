"""Endurecimiento de permisos locales (ACLs NTFS).

Los datos del POS (base, respaldos, fotos y configuración) viven en
``%APPDATA%\\PosLaLoma``. Por defecto esa carpeta es legible por el grupo
"Usuarios" de Windows; aquí se quita la herencia y se deja acceso solo al
usuario que ejecuta la aplicación, SYSTEM y los Administradores.

Se usa ``icacls`` (incluido en Windows) con SIDs en vez de nombres de grupo
para que funcione igual en Windows en español o inglés.
"""

import os
import subprocess
import sys
from pathlib import Path

# SYSTEM y Administradores (SIDs fijos, independientes del idioma).
_SIDS_BASE = ("*S-1-5-18", "*S-1-5-32-544")
# Accesos amplios que se retiran: Usuarios autenticados, Usuarios, Todos.
_SIDS_AMPLIOS = ("*S-1-5-11", "*S-1-5-32-545", "*S-1-1-0")
_TIMEOUT = 30


def disponible() -> bool:
    """True si se pueden aplicar ACLs (Windows con icacls)."""
    return sys.platform == "win32"


def es_ruta_de_red(ruta) -> bool:
    """True si la ruta es UNC (\\\\servidor\\recurso); ahí no se tocan ACLs."""
    return str(ruta).strip().startswith("\\\\")


def _usuario_actual() -> str:
    usuario = os.environ.get("USERNAME") or ""
    dominio = os.environ.get("USERDOMAIN") or ""
    if usuario and dominio:
        return f"{dominio}\\{usuario}"
    return usuario


def _ejecutar_icacls(args: list[str]) -> bool:
    try:
        result = subprocess.run(
            ["icacls", *args], capture_output=True, text=True,
            timeout=_TIMEOUT)
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def endurecer_carpeta(ruta) -> bool:
    """Deja la carpeta accesible solo al usuario actual, SYSTEM y Administradores.

    Es idempotente y no falla si la carpeta no existe o está en red.
    Devuelve True si icacls terminó sin errores.
    """
    if not disponible():
        return False
    path = Path(ruta)
    if es_ruta_de_red(path) or not path.exists():
        return False
    usuario = _usuario_actual()
    if not usuario:
        return False
    args = [str(path), "/inheritance:r",
            "/grant:r", f"{usuario}:(OI)(CI)F"]
    for sid in _SIDS_BASE:
        args += ["/grant:r", f"{sid}:(OI)(CI)F"]
    args += ["/remove:g", *_SIDS_AMPLIOS]
    ok = _ejecutar_icacls(args)
    if not ok:
        # Si falló el retiro de accesos amplios, al menos deja quitar la
        # herencia y otorgar permisos explícitos.
        args = [str(path), "/inheritance:r",
                "/grant:r", f"{usuario}:(OI)(CI)F"]
        for sid in _SIDS_BASE:
            args += ["/grant:r", f"{sid}:(OI)(CI)F"]
        ok = _ejecutar_icacls(args)
    return ok


def carpetas_de_datos() -> list[Path]:
    """Carpetas locales del POS que conviene endurecer."""
    from config import Config, appdata_dir

    raiz = appdata_dir()
    carpetas: list[Path] = [raiz]
    for candidato in (Config.DB_PATH, Config.BACKUP_DIR,
                      Config.PRODUCT_IMAGES_DIR, Config.UPDATE_DIR):
        path = Path(candidato)
        try:
            path.resolve().relative_to(raiz.resolve())
        except (ValueError, OSError):
            continue
        carpetas.append(path if path.suffix == "" else path.parent)
    return carpetas


def endurecer_datos() -> int:
    """Aplica el endurecimiento a las carpetas locales. Devuelve cuántas aplicó."""
    aplicadas = 0
    for carpeta in carpetas_de_datos():
        try:
            carpeta.mkdir(parents=True, exist_ok=True)
        except OSError:
            continue
        if endurecer_carpeta(carpeta):
            aplicadas += 1
    return aplicadas
