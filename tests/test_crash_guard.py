"""La app no debe abortar cuando un slot de la interfaz lanza una excepción."""

import os
import sys
import tempfile
import time
from pathlib import Path

PROJECT_DIR = str(Path(__file__).resolve().parents[1])
sys.path.insert(0, PROJECT_DIR)
os.chdir(PROJECT_DIR)
os.environ["QT_QPA_PLATFORM"] = "offscreen"

TMP = Path(tempfile.mkdtemp(prefix="pos_crash_"))
os.environ["POS_NO_ERROR_DIALOG"] = "1"


def setup_function():
    os.environ["POS_LOG_DIR"] = str(TMP / "logs")


from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication


def test_slot_con_excepcion_no_tumba_la_app():
    from main import SafeApplication, _instalar_hooks

    original = sys.excepthook
    _instalar_hooks()
    try:
        app = QApplication.instance()
        if app is None:
            app = SafeApplication([])
        elif not isinstance(app, SafeApplication):
            print("[SKIP] ya existe un QApplication en este proceso; "
                  "la prueba corre aislada en tests.run_all")
            return

        ejecutados = []

        def boom():
            raise ZeroDivisionError("boom")

        QTimer.singleShot(0, boom)
        QTimer.singleShot(50, lambda: ejecutados.append("siguiente"))
        limite = time.time() + 3
        while time.time() < limite and not ejecutados:
            app.processEvents()
            time.sleep(0.01)

        assert ejecutados == ["siguiente"], (
            "la app debió seguir procesando eventos tras la excepción")
        log = (TMP / "logs" / "app.log").read_text(
            encoding="utf-8", errors="replace")
        assert "ZeroDivisionError" in log, log[-500:]
        print("[OK] excepción en slot capturada; la app sigue viva")
    finally:
        sys.excepthook = original


def test_excepthook_registra_en_log():
    from main import _instalar_hooks

    original = sys.excepthook
    try:
        _instalar_hooks()
        sys.excepthook(ValueError, ValueError("fallo de prueba"), None)
    finally:
        sys.excepthook = original

    log = (TMP / "logs" / "app.log").read_text(
        encoding="utf-8", errors="replace")
    assert "Excepción no controlada" in log
    assert "fallo de prueba" in log
    print("[OK] excepthook escribe en el log")
