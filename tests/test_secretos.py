"""Secretos en reposo: cifrado DPAPI y migración de hacienda_config."""

import os
import sys
from pathlib import Path

PROJECT_DIR = str(Path(__file__).resolve().parents[1])
sys.path.insert(0, PROJECT_DIR)
os.chdir(PROJECT_DIR)
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from database.db_manager import DatabaseManager
from utils import secretos

TEST_DB = os.path.join(PROJECT_DIR, "tests", ".tmp", "test_secretos.db")


def cleanup():
    for _ in range(5):
        try:
            if os.path.exists(TEST_DB):
                os.remove(TEST_DB)
            for ext in ("-wal", "-shm"):
                p = TEST_DB + ext
                if os.path.exists(p):
                    os.remove(p)
        except PermissionError:
            import time
            time.sleep(0.1)


def setup_function():
    cleanup()


def teardown_function():
    cleanup()


def _db() -> DatabaseManager:
    db = DatabaseManager(TEST_DB)
    db.initialize()
    return db


def test_cifrar_descifrar_roundtrip():
    cifrado = secretos.cifrar("clave-super-secreta-123")
    assert cifrado.startswith(secretos.PREFIX)
    assert "clave-super-secreta-123" not in cifrado
    assert secretos.descifrar(cifrado) == "clave-super-secreta-123"


def test_cifrado_idempotente_y_vacios():
    assert secretos.cifrar("") == ""
    assert secretos.descifrar("") == ""
    una_vez = secretos.cifrar("dato")
    assert secretos.cifrar(una_vez) == una_vez
    assert secretos.descifrar(una_vez) == "dato"


def test_texto_plano_pasa_igual():
    assert secretos.descifrar("valores viejos") == "valores viejos"
    assert not secretos.es_cifrado("valores viejos")
    assert secretos.descifrar_campos({"password": "plano"})["password"] == "plano"


def test_campos_secretos_cifrados():
    original = {"password": "abc123", "pin": "4321", "company_name": "Mueblería"}
    cifrado = secretos.cifrar_campos(original)
    assert cifrado["company_name"] == "Mueblería"
    assert secretos.es_cifrado(cifrado["password"])
    assert secretos.es_cifrado(cifrado["pin"])
    assert secretos.descifrar_campos(cifrado) == original


def test_migracion_fila_unica():
    db = _db()
    db.execute_insert(
        "INSERT OR REPLACE INTO hacienda_config (id, password, pin, company_name) "
        "VALUES (1, ?, ?, ?)", ("clave-plana", "1234", "Mueblería"))
    migrados = secretos.migrar_secretos_en_db(db)
    assert migrados >= 2
    fila = db.execute_query("SELECT * FROM hacienda_config WHERE id = 1")[0]
    assert secretos.es_cifrado(fila["password"])
    assert secretos.es_cifrado(fila["pin"])
    assert secretos.descifrar(fila["password"]) == "clave-plana"
    assert secretos.descifrar(fila["pin"]) == "1234"
    assert fila["company_name"] == "Mueblería"
    assert secretos.migrar_secretos_en_db(db) == 0
    db.close()


def test_migracion_tolera_valores_ausentes():
    db = _db()
    assert secretos.migrar_secretos_en_db(db) == 0
    db.execute_insert(
        "INSERT OR REPLACE INTO hacienda_config (id, company_name) "
        "VALUES (1, ?)", ("Mueblería",))
    assert secretos.migrar_secretos_en_db(db) == 0
    fila = db.execute_query("SELECT * FROM hacienda_config WHERE id = 1")[0]
    assert fila["password"] in (None, "")
    assert fila["company_name"] == "Mueblería"
    db.close()
