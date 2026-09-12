"""Tests de las tablas de crédito: credit_accounts, credit_payments, credit_payment_images."""

import os
import sys
from pathlib import Path

PROJECT_DIR = str(Path(__file__).resolve().parents[1])
sys.path.insert(0, PROJECT_DIR)
os.chdir(PROJECT_DIR)
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from database.db_manager import DatabaseManager

TEST_DB = os.path.join(PROJECT_DIR, "tests", ".tmp", "test_credito.db")


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


def _db():
    db = DatabaseManager(TEST_DB)
    db.initialize()
    return db


def test_credit_accounts_table_exists():
    db = _db()
    tables = db.execute_query("SELECT name FROM sqlite_master WHERE type='table'")
    names = [t["name"] for t in tables]
    assert "credit_accounts" in names


def test_credit_payments_table_exists():
    db = _db()
    tables = db.execute_query("SELECT name FROM sqlite_master WHERE type='table'")
    names = [t["name"] for t in tables]
    assert "credit_payments" in names


def test_credit_payment_images_table_exists():
    db = _db()
    tables = db.execute_query("SELECT name FROM sqlite_master WHERE type='table'")
    names = [t["name"] for t in tables]
    assert "credit_payment_images" in names


def test_insert_credit_account():
    db = _db()
    # Primero crear cliente y venta necesarios
    db.execute_insert(
        "INSERT INTO clients (id_type, id_number, name) VALUES (?, ?, ?)",
        ("01", "111111111", "Cliente Test"),
    )
    sale_id = db.execute_insert(
        "INSERT INTO sales (invoice_number, client_id, total, payment_method, status) "
        "VALUES (?, ?, ?, ?, ?)",
        ("V-00001", 1, 100000.0, "credito", "completada"),
    )
    account_id = db.execute_insert(
        "INSERT INTO credit_accounts (sale_id, client_id, invoice_number, total, balance) "
        "VALUES (?, ?, ?, ?, ?)",
        (sale_id, 1, "V-00001", 100000.0, 100000.0),
    )
    assert account_id > 0
    rows = db.execute_query("SELECT * FROM credit_accounts WHERE id = ?", (account_id,))
    assert len(rows) == 1
    assert rows[0]["total"] == 100000.0
    assert rows[0]["balance"] == 100000.0
    assert rows[0]["status"] == "pendiente"


def test_insert_credit_payment():
    db = _db()
    db.execute_insert(
        "INSERT INTO clients (id_type, id_number, name) VALUES (?, ?, ?)",
        ("01", "222222222", "Cliente Abono"),
    )
    sale_id = db.execute_insert(
        "INSERT INTO sales (invoice_number, client_id, total, payment_method, status) "
        "VALUES (?, ?, ?, ?, ?)",
        ("V-00002", 1, 50000.0, "credito", "completada"),
    )
    account_id = db.execute_insert(
        "INSERT INTO credit_accounts (sale_id, client_id, invoice_number, total, balance) "
        "VALUES (?, ?, ?, ?, ?)",
        (sale_id, 1, "V-00002", 50000.0, 50000.0),
    )
    payment_id = db.execute_insert(
        "INSERT INTO credit_payments (credit_account_id, amount, payment_method) "
        "VALUES (?, ?, ?)",
        (account_id, 20000.0, "efectivo"),
    )
    assert payment_id > 0
    rows = db.execute_query("SELECT * FROM credit_payments WHERE id = ?", (payment_id,))
    assert len(rows) == 1
    assert rows[0]["amount"] == 20000.0


def test_insert_credit_payment_image():
    db = _db()
    db.execute_insert(
        "INSERT INTO clients (id_type, id_number, name) VALUES (?, ?, ?)",
        ("01", "333333333", "Cliente Comprobante"),
    )
    sale_id = db.execute_insert(
        "INSERT INTO sales (invoice_number, client_id, total, payment_method, status) "
        "VALUES (?, ?, ?, ?, ?)",
        ("V-00003", 1, 75000.0, "credito", "completada"),
    )
    account_id = db.execute_insert(
        "INSERT INTO credit_accounts (sale_id, client_id, invoice_number, total, balance) "
        "VALUES (?, ?, ?, ?, ?)",
        (sale_id, 1, "V-00003", 75000.0, 75000.0),
    )
    payment_id = db.execute_insert(
        "INSERT INTO credit_payments (credit_account_id, amount, payment_method) "
        "VALUES (?, ?, ?)",
        (account_id, 15000.0, "sinpe"),
    )
    image_id = db.execute_insert(
        "INSERT INTO credit_payment_images (payment_id, image_path, description) "
        "VALUES (?, ?, ?)",
        (payment_id, "comprobante_001.jpg", "Transferencia SINPE"),
    )
    assert image_id > 0
    rows = db.execute_query("SELECT * FROM credit_payment_images WHERE id = ?", (image_id,))
    assert len(rows) == 1
    assert rows[0]["image_path"] == "comprobante_001.jpg"


def test_delete_credit_account_after_payments():
    db = _db()
    db.execute_insert(
        "INSERT INTO clients (id_type, id_number, name) VALUES (?, ?, ?)",
        ("01", "444444444", "Cliente Delete"),
    )
    sale_id = db.execute_insert(
        "INSERT INTO sales (invoice_number, client_id, total, payment_method, status) "
        "VALUES (?, ?, ?, ?, ?)",
        ("V-00004", 1, 30000.0, "credito", "completada"),
    )
    account_id = db.execute_insert(
        "INSERT INTO credit_accounts (sale_id, client_id, invoice_number, total, balance) "
        "VALUES (?, ?, ?, ?, ?)",
        (sale_id, 1, "V-00004", 30000.0, 30000.0),
    )
    db.execute_insert(
        "INSERT INTO credit_payments (credit_account_id, amount, payment_method) "
        "VALUES (?, ?, ?)",
        (account_id, 10000.0, "efectivo"),
    )
    # Eliminar pagos primero, luego la cuenta
    db.execute_update("DELETE FROM credit_payments WHERE credit_account_id = ?", (account_id,))
    db.execute_update("DELETE FROM credit_accounts WHERE id = ?", (account_id,))
    accounts = db.execute_query("SELECT * FROM credit_accounts WHERE id = ?", (account_id,))
    assert len(accounts) == 0
