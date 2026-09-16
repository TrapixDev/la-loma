"""Diagnóstico de instalación y utilidades de log del POS.

Reúne chequeos del entorno (Windows, permisos, disco, puerto, impresoras,
base de datos) para detectar problemas de instalación antes de que fallen.
También centraliza la configuración del archivo de log con rotación.
"""

import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

from config import Config, IS_FROZEN, appdata_dir

LOG_MAX_BYTES = 1_000_000

NIVEL_OK = "ok"
NIVEL_AVISO = "aviso"
NIVEL_ERROR = "error"


def log_dir() -> Path:
    """Carpeta de logs (override con POS_LOG_DIR para pruebas)."""
    override = os.environ.get("POS_LOG_DIR")
    if override:
        return Path(override)
    return appdata_dir() / "logs"


def log_path() -> Path:
    return log_dir() / "app.log"


def configurar_logs() -> Path:
    """Crea la carpeta de logs y rota app.log si supera el tamaño máximo."""
    carpeta = log_dir()
    try:
        carpeta.mkdir(parents=True, exist_ok=True)
        destino = log_path()
        if destino.is_file() and destino.stat().st_size > LOG_MAX_BYTES:
            respaldo = destino.with_suffix(".log.1")
            try:
                respaldo.unlink(missing_ok=True)
                destino.rename(respaldo)
            except OSError:
                try:
                    destino.write_text("", encoding="utf-8")
                except OSError:
                    pass
        return destino
    except OSError:
        return log_path()


def escribir_log(mensaje: str) -> None:
    """Escribe una línea con sello de tiempo en el log (best-effort)."""
    import time
    try:
        ruta = configurar_logs()
        with open(ruta, "a", encoding="utf-8", errors="replace") as handle:
            handle.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {mensaje}\n")
    except OSError:
        pass


def registrar_traceback(contexto: str) -> str:
    """Guarda el traceback actual en el log y devuelve el texto."""
    import traceback
    detalle = traceback.format_exc()
    escribir_log(f"{contexto}\n{detalle}")
    return detalle


def _check(nivel: str, titulo: str, detalle: str) -> dict:
    return {"nivel": nivel, "titulo": titulo, "detalle": detalle}


def _windows_check() -> dict:
    try:
        version = sys.getwindowsversion()
        if version.major >= 10:
            return _check(NIVEL_OK, "Windows",
                          f"Windows {version.major}.{version.minor} "
                          f"(build {version.build})")
        return _check(NIVEL_ERROR, "Windows",
                      f"Windows {version.major}.{version.minor} no es "
                      f"compatible; se requiere Windows 10 o superior.")
    except AttributeError:
        return _check(NIVEL_AVISO, "Windows",
                      "No se pudo determinar la versión de Windows.")


def _appdata_check(base: Path | None = None) -> dict:
    carpeta = base or appdata_dir()
    try:
        carpeta.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=carpeta, delete=False) as handle:
            prueba = Path(handle.name)
        prueba.unlink(missing_ok=True)
        return _check(NIVEL_OK, "Carpeta de datos",
                      f"Se puede escribir en {carpeta}")
    except OSError as exc:
        return _check(NIVEL_ERROR, "Carpeta de datos",
                      f"No se puede escribir en {carpeta}: {exc}")


def _disk_check(base: Path | None = None) -> dict:
    carpeta = base or appdata_dir()
    try:
        uso = shutil.disk_usage(carpeta)
        libres_mb = uso.free // (1024 * 1024)
        nivel = NIVEL_OK if libres_mb >= 200 else NIVEL_AVISO
        return _check(nivel, "Espacio en disco", f"{libres_mb} MB libres")
    except OSError as exc:
        return _check(NIVEL_AVISO, "Espacio en disco",
                      f"No se pudo verificar: {exc}")


def _port_check(port: int | None = None) -> dict:
    puerto = port or Config.SERVER_PORT
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.bind(("127.0.0.1", puerto))
        return _check(NIVEL_OK, "Puerto del servidor",
                      f"El puerto {puerto} está libre")
    except OSError:
        pass
    finally:
        probe.close()
    try:
        from network.remote_db import RemoteDatabase
        if RemoteDatabase(f"http://127.0.0.1:{puerto}").check_connection(timeout=2):
            return _check(NIVEL_OK, "Puerto del servidor",
                          f"El servidor del POS ya responde en el {puerto}")
    except Exception:
        pass
    return _check(NIVEL_AVISO, "Puerto del servidor",
                  f"El puerto {puerto} está ocupado por otro programa; "
                  f"se usará un puerto alterno automáticamente.")


def _printers_check() -> dict | None:
    """Impresoras instaladas (requiere QApplication activa)."""
    try:
        from PyQt6.QtPrintSupport import QPrinterInfo
        from PyQt6.QtWidgets import QApplication
        if QApplication.instance() is None:
            return None
        impresoras = QPrinterInfo.availablePrinters()
        if impresoras:
            nombres = ", ".join(p.printerName() for p in impresoras[:3])
            return _check(NIVEL_OK, "Impresoras",
                          f"{len(impresoras)} instalada(s): {nombres}")
        return _check(NIVEL_AVISO, "Impresoras",
                      "No hay impresoras instaladas en Windows.")
    except Exception:
        return None


def _database_check(db_path: str | None = None) -> dict:
    ruta = Path(db_path or Config.DB_PATH)
    if not ruta.is_file():
        return _check(NIVEL_OK, "Base de datos",
                      f"Aún no existe; se creará en {ruta}")
    try:
        connection = sqlite3.connect(str(ruta))
        try:
            resultado = connection.execute("PRAGMA quick_check").fetchone()
        finally:
            connection.close()
        estado = str(resultado[0]) if resultado else "desconocido"
        if estado.lower() == "ok":
            return _check(NIVEL_OK, "Base de datos",
                          f"Íntegra ({ruta.name})")
        return _check(NIVEL_ERROR, "Base de datos",
                      f"Problema de integridad: {estado}")
    except sqlite3.Error as exc:
        return _check(NIVEL_ERROR, "Base de datos",
                      f"No se pudo abrir {ruta.name}: {exc}")


def _version_check() -> dict:
    modo = "instalado" if IS_FROZEN else "código fuente"
    return _check(NIVEL_OK, "Versión",
                  f"POS La Loma {Config.APP_VERSION} ({modo})")


def _log_check() -> dict:
    return _check(NIVEL_OK, "Registro (log)",
                  f"Los errores se guardan en {log_path()}")


def _seguridad_check() -> dict:
    """Cifrado del tráfico (HTTPS) y permisos de las carpetas de datos."""
    from utils import seguridad

    acl = ("ACLs restringidas al usuario actual" if seguridad.disponible()
           else "ACLs no aplicables (fuera de Windows)")
    certificado = Path(Config.TLS_CERT) if Config.TLS_CERT else None
    if certificado and certificado.is_file():
        return _check(NIVEL_OK, "Seguridad",
                      f"HTTPS activo ({certificado.name}); {acl}")
    return _check(NIVEL_AVISO, "Seguridad",
                  "El servidor usa HTTP dentro de la red local (no lo exponga a "
                  "Internet). Para cifrar el tráfico: "
                  "python tools/generar_certificado.py")


def _firewall_check() -> dict | None:
    """Comprueba si existe la regla de firewall del POS (solo Windows)."""
    if sys.platform != "win32":
        return None
    try:
        result = subprocess.run(
            ["netsh", "advfirewall", "firewall", "show", "rule",
             "name=POS La Loma"],
            capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode == 0 and "POS La Loma" in result.stdout:
        return _check(NIVEL_OK, "Firewall",
                      "Regla 'POS La Loma' configurada para la red local")
    return _check(NIVEL_AVISO, "Firewall",
                  "Sin regla 'POS La Loma'. Ejecute build\\firewall_pos.ps1 "
                  "como administrador para permitir solo la red local")


def recolectar(base: Path | None = None, db_path: str | None = None,
               port: int | None = None) -> list[dict]:
    """Ejecuta los chequeos de instalación y devuelve la lista de resultados."""
    checks = [
        _version_check(),
        _windows_check(),
        _appdata_check(base),
        _disk_check(base),
        _port_check(port),
    ]
    impresoras = _printers_check()
    if impresoras is not None:
        checks.append(impresoras)
    checks.append(_database_check(db_path))
    checks.append(_log_check())
    checks.append(_seguridad_check())
    firewall = _firewall_check()
    if firewall is not None:
        checks.append(firewall)
    return checks


def hay_problemas(checks: list[dict]) -> bool:
    """True si algún chequeo no está en nivel OK."""
    return any(check.get("nivel") != NIVEL_OK for check in checks)


def texto_reporte(checks: list[dict]) -> str:
    """Reporte de texto plano (para copiar o imprimir en --selftest)."""
    simbolos = {NIVEL_OK: "[OK]", NIVEL_AVISO: "[AVISO]", NIVEL_ERROR: "[ERROR]"}
    lineas = ["Diagnóstico POS La Loma", "=" * 40]
    for check in checks:
        simbolo = simbolos.get(check.get("nivel"), "[?]")
        lineas.append(f"{simbolo} {check.get('titulo', '')}: "
                      f"{check.get('detalle', '')}")
    lineas.append("=" * 40)
    return "\n".join(lineas)
