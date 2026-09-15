"""Tests del diagnóstico de instalación y del log con rotación."""

import os
import socket
import sys
import tempfile
from pathlib import Path

PROJECT_DIR = str(Path(__file__).resolve().parents[1])
sys.path.insert(0, PROJECT_DIR)
os.chdir(PROJECT_DIR)
os.environ["QT_QPA_PLATFORM"] = "offscreen"

TMP = Path(tempfile.mkdtemp(prefix="pos_diag_"))


def setup_function():
    os.environ["POS_LOG_DIR"] = str(TMP / "logs")


from utils.diagnostico import (
    LOG_MAX_BYTES,
    configurar_logs,
    hay_problemas,
    recolectar,
    texto_reporte,
)


def test_configurar_logs_crea_y_rota():
    ruta = configurar_logs()
    ruta.write_text("x" * (LOG_MAX_BYTES + 10), encoding="utf-8")
    configurar_logs()
    assert (ruta.parent / "app.log.1").is_file()
    assert not ruta.exists() or ruta.stat().st_size <= LOG_MAX_BYTES
    print("[OK] log creado y rotado")


def test_recolectar_checks_esperados():
    checks = recolectar(base=TMP, db_path=str(TMP / "no_existe.db"))
    titulos = {c["titulo"] for c in checks}
    for esperado in ("Versión", "Windows", "Carpeta de datos", "Espacio en disco",
                     "Puerto del servidor", "Base de datos", "Registro (log)"):
        assert esperado in titulos, esperado
    assert isinstance(hay_problemas(checks), bool)
    print("[OK] diagnóstico reúne los chequeos")


def test_reporte_texto():
    checks = recolectar(base=TMP, db_path=str(TMP / "no_existe.db"))
    reporte = texto_reporte(checks)
    assert "Diagnóstico POS La Loma" in reporte
    assert "[OK]" in reporte or "[AVISO]" in reporte
    print("[OK] reporte de texto generado")


def test_appdata_no_escribible():
    archivo = TMP / "bloqueo.txt"
    archivo.write_text("x", encoding="utf-8")
    checks = recolectar(base=archivo / "sub" / "carpeta",
                        db_path=str(TMP / "no_existe.db"))
    carpeta = next(c for c in checks if c["titulo"] == "Carpeta de datos")
    assert carpeta["nivel"] == "error", carpeta
    assert hay_problemas(checks) is True
    print("[OK] detecta carpeta de datos no escribible")


def test_puerto_ocupado_por_ajeno():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    puerto = server.getsockname()[1]
    try:
        checks = recolectar(base=TMP, db_path=str(TMP / "no_existe.db"),
                            port=puerto)
        puerto_check = next(c for c in checks
                            if c["titulo"] == "Puerto del servidor")
        assert puerto_check["nivel"] == "aviso", puerto_check
    finally:
        server.close()
    print("[OK] detecta puerto ocupado por otro programa")
