"""Tests de la seed de demostración: idempotente y no borra datos existentes."""

import os
import sys
import time
from pathlib import Path

PROJECT_DIR = str(Path(__file__).resolve().parents[1])
sys.path.insert(0, PROJECT_DIR)
os.chdir(PROJECT_DIR)
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from database.db_manager import DatabaseManager
from database.seed import DEMO_CREDIT_SALES, seed_initial_data

TEST_DB = os.path.join(PROJECT_DIR, "tests", ".tmp", "test_seed_demo.db")
TEST_DOCS = os.path.join(PROJECT_DIR, "tests", ".tmp", "creditos")


def cleanup():
    for _ in range(5):
        try:
            if os.path.exists(TEST_DB):
                os.remove(TEST_DB)
            for ext in ("-wal", "-shm"):
                p = TEST_DB + ext
                if os.path.exists(p):
                    os.remove(p)
            if os.path.isdir(TEST_DOCS):
                for name in os.listdir(TEST_DOCS):
                    try:
                        os.remove(os.path.join(TEST_DOCS, name))
                    except OSError:
                        pass
            break
        except PermissionError:
            time.sleep(0.1)


def get_db():
    cleanup()
    db = DatabaseManager(TEST_DB)
    db.initialize()
    db.execute_insert(
        "INSERT INTO categories (name, color) VALUES ('Muebles de Sala', '')")
    cid = db.execute_query("SELECT id FROM categories LIMIT 1")[0]["id"]
    db.execute_insert(
        "INSERT INTO products (name, sale_price, category_id, tax_rate) VALUES (?, ?, ?, ?)",
        ("silla comedor europea", 75000, cid, 13.0),
    )
    return db


def _counts(db):
    return {
        "prod": db.execute_query("SELECT COUNT(*) AS t FROM products")[0]["t"],
        "sales": db.execute_query("SELECT COUNT(*) AS t FROM sales")[0]["t"],
        "clients": db.execute_query("SELECT COUNT(*) AS t FROM clients")[0]["t"],
        "exp": db.execute_query("SELECT COUNT(*) AS t FROM expenses")[0]["t"],
        "cacc": db.execute_query("SELECT COUNT(*) AS t FROM credit_accounts")[0]["t"],
        "cpay": db.execute_query("SELECT COUNT(*) AS t FROM credit_payments")[0]["t"],
        "cimg": db.execute_query("SELECT COUNT(*) AS t FROM credit_payment_images")[0]["t"],
    }


def _enable_demo():
    os.environ["POS_DEMO_DATA"] = "1"
    os.environ["POS_DEMO_DOCS_DIR"] = TEST_DOCS


def test_seed_demo_con_producto_existente():
    db = get_db()
    _enable_demo()
    seed_initial_data(db)
    counts = _counts(db)
    silla = db.execute_query(
        "SELECT COUNT(*) AS t FROM products WHERE name='silla comedor europea'")[0]["t"]
    ok = counts["prod"] > 1 and counts["sales"] > 0 and silla == 1
    print(f"[{'OK' if ok else 'FAIL'}] seed demo sobre BD con datos: {counts}, silla={silla}")
    db.close()
    cleanup()
    assert ok


def test_seed_demo_no_duplica():
    db = get_db()
    _enable_demo()
    seed_initial_data(db)
    first = _counts(db)
    seed_initial_data(db)
    second = _counts(db)
    ok = all(second[k] == first[k] for k in first)
    print(f"[{'OK' if ok else 'FAIL'}] seed demo idempotente: {first} -> {second}")
    db.close()
    cleanup()
    assert ok


def test_seed_demo_incluye_credito():
    db = get_db()
    _enable_demo()
    seed_initial_data(db)
    counts = _counts(db)
    ventas_credito = db.execute_query(
        "SELECT COUNT(*) AS t FROM sales WHERE payment_method = 'credito'")[0]["t"]
    pendientes = db.execute_query(
        "SELECT COUNT(*) AS t FROM credit_accounts WHERE status = 'pendiente'")[0]["t"]
    ok = (ventas_credito == len(DEMO_CREDIT_SALES)
          and counts["cacc"] == len(DEMO_CREDIT_SALES)
          and counts["cpay"] > 0 and counts["cimg"] > 0
          and pendientes > 0)
    print(f"[{'OK' if ok else 'FAIL'}] seed demo crédito: {counts}, "
          f"ventas_credito={ventas_credito}, pendientes={pendientes}")
    db.close()
    cleanup()
    assert ok


def test_seed_sin_demo_no_agrega_productos():
    db = get_db()
    os.environ.pop("POS_DEMO_DATA", None)
    os.environ["POS_DEMO_DATA"] = "0"
    seed_initial_data(db)
    counts = _counts(db)
    ok = counts["prod"] == 1 and counts["sales"] == 0
    print(f"[{'OK' if ok else 'FAIL'}] POS_DEMO_DATA=0 no siembra demo: {counts}")
    db.close()
    cleanup()
    assert ok


if __name__ == "__main__":
    tests = [
        test_seed_demo_con_producto_existente,
        test_seed_demo_no_duplica,
        test_seed_demo_incluye_credito,
        test_seed_sin_demo_no_agrega_productos,
    ]
    failed = 0
    for t in tests:
        try:
            t()
        except Exception as e:
            print(f"[FAIL] {t.__name__}: {e}")
            failed += 1
    print(f"\n{'SEED DEMO OK' if failed == 0 else f'SEED DEMO FAIL: {failed}'}")
