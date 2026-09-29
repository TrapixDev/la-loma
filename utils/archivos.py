"""Rutas y contenidos de archivos controlados (imágenes y comprobantes).

Regla de oro: nunca leer, abrir ni borrar un archivo cuya ruta venga de la
base de datos o de un campo de texto. Este módulo resuelve la ruta canónica y
verifica que sea una imagen real dentro de las carpetas permitidas.
"""

import os
from pathlib import Path

EXTENSIONES_IMAGEN = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
MAX_LOGO_BYTES = 2_000_000

# Tipos de imagen aceptados por su contenido (no por la extensión).
_MAGIC = (
    (b"\x89PNG\r\n\x1a\n", ".png"),
    (b"\xff\xd8\xff", ".jpg"),
    (b"BM", ".bmp"),
)


def es_imagen(data: bytes) -> bool:
    """True si los bytes iniciales corresponden a una imagen conocida."""
    if not data or len(data) < 12:
        return False
    for firma, _ext in _MAGIC:
        if data.startswith(firma):
            return True
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return True
    return False


def _carpetas_permitidas(extra: list | None = None) -> list[Path]:
    """Carpetas donde el POS guarda imágenes legítimas."""
    from config import Config

    carpetas = [
        Path(Config.PRODUCT_IMAGES_DIR),
        Path(Config.IMAGE_CACHE_DIR),
        Path(os.environ.get("APPDATA", ""), "PosLaLoma", "documentos", "creditos"),
    ]
    for ruta in extra or []:
        carpetas.append(Path(ruta))
    return [c for c in carpetas if str(c).strip()]


def ruta_imagen_permitida(valor, extra: list | None = None) -> Path | None:
    """Ruta canónica de una imagen existente dentro de carpetas permitidas.

    Acepta un nombre suelto (se busca en las carpetas permitidas) o una ruta
    absoluta (debe quedar dentro de alguna). Rechaza rutas UNC, extensiones
    no reconocidas y archivos que no sean imágenes reales.
    """
    texto = str(valor or "").strip()
    if not texto or texto.startswith("\\\\"):
        return None
    candidato = Path(texto)
    if candidato.suffix.lower() not in EXTENSIONES_IMAGEN:
        return None
    bases = _carpetas_permitidas(extra)
    rutas = ([candidato] if candidato.is_absolute()
             else [base / candidato.name for base in bases])
    for ruta in rutas:
        try:
            resuelta = ruta.resolve()
        except OSError:
            continue
        if not resuelta.is_file():
            continue
        for base in bases:
            try:
                if resuelta.is_relative_to(base.resolve()):
                    break
            except OSError:
                continue
        else:
            continue
        try:
            if not es_imagen(resuelta.read_bytes()[:16]):
                continue
        except OSError:
            continue
        return resuelta
    return None


def ruta_logo_segura(ruta) -> Path | None:
    """Valida el logo del ticket: imagen local, tamaño acotado y sin UNC."""
    texto = str(ruta or "").strip()
    if not texto or texto.startswith("\\\\"):
        return None
    candidato = Path(texto)
    if candidato.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
        return None
    try:
        resuelto = candidato.resolve()
        if not resuelto.is_file() or resuelto.stat().st_size > MAX_LOGO_BYTES:
            return None
        with open(resuelto, "rb") as archivo:
            cabecera = archivo.read(16)
    except OSError:
        return None
    return resuelto if es_imagen(cabecera) else None
