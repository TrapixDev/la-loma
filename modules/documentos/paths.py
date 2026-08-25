"""Ubicación de los respaldos de facturas.

Preferencia (primera que funcione):
  1. DOCS_PATH de config.ini / Config (carpeta compartida en red, p. ej.
     \\\\SERVIDOR\\documentos): todas las cajas archivan en el mismo lugar.
  2. Documentos/PosLaLoma (carpeta Documentos del usuario).
  3. %APPDATA%\\PosLaLoma\\documentos (red caída / sin permiso).

Estructura: <raíz>/Facturas/AAAA-MM/{invoice_number}_{AAAA-MM-DD}.xml (.pdf)
"""

from datetime import date, datetime
from pathlib import Path

from config import Config

try:
    from PyQt6.QtCore import QStandardPaths
except Exception:  # pragma: no cover - entorno sin Qt al hacer imports aislados
    QStandardPaths = None

_FALLBACK_LOCAL: Path | None = None


def _documents_root() -> Path:
    if QStandardPaths is not None:
        try:
            root = QStandardPaths.writableLocation(
                QStandardPaths.StandardLocation.DocumentsLocation)
            if root:
                return Path(root)
        except Exception:
            pass
    return Path.home() / "Documents"


def _fallback_root() -> Path:
    """Último recurso: %APPDATA%\\PosLaLoma\\documentos."""
    from config import appdata_dir
    return appdata_dir() / "documentos"


def _red_accesible(carpeta: Path) -> bool:
    """True si la carpeta (posiblemente UNC) se puede crear/escribir."""
    try:
        carpeta.mkdir(parents=True, exist_ok=True)
        prueba = carpeta / ".pos_laloma_write_test"
        prueba.write_text("ok", encoding="utf-8")
        prueba.unlink(missing_ok=True)
        return True
    except OSError:
        return False


def facturas_root() -> Path:
    """Raíz de respaldo: DOCS_PATH / Documentos\\PosLaLoma / APPDATA."""
    global _FALLBACK_LOCAL
    if _FALLBACK_LOCAL is not None:
        return _FALLBACK_LOCAL
    if Config.DOCS_PATH:
        compartida = Path(Config.DOCS_PATH)
        if _red_accesible(compartida):
            return compartida / "Facturas"
    local = _documents_root() / "PosLaLoma" / "Facturas"
    if _red_accesible(local):
        return local
    _FALLBACK_LOCAL = _fallback_root() / "Facturas"
    _FALLBACK_LOCAL.mkdir(parents=True, exist_ok=True)
    return _FALLBACK_LOCAL


def _year_month(value) -> tuple[int, int]:
    if isinstance(value, datetime):
        return value.year, value.month
    if isinstance(value, date):
        return value.year, value.month
    text = str(value)
    if len(text) >= 7 and text[:4].isdigit() and text[5:7].isdigit():
        return int(text[:4]), int(text[5:7])
    now = datetime.now()
    return now.year, now.month


def carpeta_factura(created_at=None) -> Path:
    """Carpeta del mes de la venta: .../Facturas/AAAA-MM/."""
    year, month = _year_month(created_at)
    folder = facturas_root() / f"{year}-{month:02d}"
    folder.mkdir(parents=True, exist_ok=True)
    return folder
