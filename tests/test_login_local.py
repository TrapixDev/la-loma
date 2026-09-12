"""Tests del bloqueo local por intentos fallidos de PIN (LocalAuth)."""

import os
import sys
from pathlib import Path

PROJECT_DIR = str(Path(__file__).resolve().parents[1])
sys.path.insert(0, PROJECT_DIR)
os.chdir(PROJECT_DIR)
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from database.db_manager import DatabaseManager
from ui.login_dialog import MAX_FAILED, LocalAuth

TEST_DB = os.path.join(PROJECT_DIR, "tests", ".tmp", "test_login_local.db")


def cleanup():
    for _ in range(5):
        try:
            if os.path.exists(TEST_DB):
                os.remove(TEST_DB)
            for ext in ("-wal", "-shm"):
                p = TEST_DB + ext
                if os.path.exists(p):
                    os.remove(p)
            break
        except PermissionError:
            import time
            time.sleep(0.1)


def test_lockout_local():
    cleanup()
    db = DatabaseManager(TEST_DB)
    db.initialize()
    try:
        auth = LocalAuth(db)
        auth.setup("Tester", "1234")

        # Intentos fallidos acumulan y avisan el progreso.
        resultado = auth.login("9999")
        assert "Intento 1 de" in resultado["error"], resultado

        # Al llegar al máximo queda bloqueado, incluso con el PIN correcto.
        for _ in range(MAX_FAILED - 1):
            resultado = auth.login("9999")
        assert "Bloqueado" in resultado["error"], resultado
        resultado = auth.login("1234")
        assert "Demasiados" in resultado["error"], resultado

        # Cumplido el tiempo (simulado), el PIN correcto vuelve a entrar.
        auth._locked_until = 0.0
        resultado = auth.login("1234")
        assert resultado.get("user_id"), resultado
        assert auth._failed_attempts == 0
    finally:
        db.close()
        cleanup()
