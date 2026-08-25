"""Tests de ventas: idempotencia (reintento no duplica) y numeración única.

El stock se ignoró por diseño (se fabrica a pedido), así que las ventas se
crean sin validar ni descontar existencias.
"""

import os
import sys
import time
from pathlib import Path

PROJECT_DIR = str(Path(__file__).resolve().parents[1])
sys.path.insert(0, PROJECT_DIR)
os.chdir(PROJECT_DIR)
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from database.db_manager import DatabaseManager
from database.models import Sale, SaleItem
from modules.pos.cart_service import CartService

TEST_DB = os.path.join(PROJECT_DIR, "tests", ".tmp", "test_ventas.db")


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
            time.sleep(0.1)


def get_db():
    cleanup()
    db = DatabaseManager(TEST_DB)
    db.initialize()
    db.execute_insert(
        "INSERT INTO products (name, sale_price, stock_quantity, tax_rate, tax_type) "
        "VALUES ('Mesa de roble', 75000, 0, 13.0, 'gravado')")
    return db


def make_sale(reference, product_id, cantidad=1):
    return Sale(
        invoice_number="",
        subtotal=75000.0 * cantidad,
        discount=0.0,
        tax_amount=0.0,
        total=75000.0 * cantidad,
        payment_method="efectivo",
        cash_received=75000.0 * cantidad,
        change_amount=0.0,
        invoice_type="simplificada",
        sale_reference=reference,
        currency="CRC",
        status="completada",
        station="CAJA1",
        user_id=1,
        user_name="Test",
        created_at=None,
        items=[SaleItem(product_id=product_id, product_name="Mesa de roble",
                        quantity=cantidad, unit_price=75000.0, total=75000.0 * cantidad)],
    )


def test_reintento_no_duplica():
    db = get_db()
    service = CartService(db)
    producto = db.execute_query("SELECT id FROM products WHERE name='Mesa de roble'")[0]
    pid = producto["id"]

    sale = make_sale("ref-unicA-123", pid)
    id1 = service.create_sale(sale, sale.items)
    id2 = service.create_sale(sale, sale.items)

    count = db.execute_query("SELECT COUNT(*) AS n FROM sales")[0]["n"]
    ok = id1 == id2 and count == 1
    print(f"[{'OK' if ok else 'FAIL'}] reintento no duplica (id {id1}/{id2}, ventas={count})")
    db.close()
    cleanup()
    assert ok


def test_vende_sin_stock():
    db = get_db()
    service = CartService(db)
    producto = db.execute_query("SELECT id FROM products WHERE name='Mesa de roble'")[0]
    pid = producto["id"]

    # Sin existencias (stock_quantity=0) la venta se crea igual.
    sale = make_sale("ref-sinstock", pid, cantidad=10)
    sale_id = service.create_sale(sale, sale.items)
    count = db.execute_query("SELECT COUNT(*) AS n FROM sales")[0]["n"]
    stock = db.execute_query(
        "SELECT stock_quantity FROM products WHERE id = ?", (pid,))[0]["stock_quantity"]
    ok = sale_id > 0 and count == 1 and stock == 0
    print(f"[{'OK' if ok else 'FAIL'}] venta sin stock se registra: id={sale_id}, ventas={count}, stock={stock}")
    db.close()
    cleanup()
    assert ok


def test_numeracion_sin_duplicados():
    db = get_db()
    service = CartService(db)
    producto = db.execute_query("SELECT id FROM products WHERE name='Mesa de roble'")[0]
    pid = producto["id"]
    ids = []
    for i in range(3):
        ids.append(service.create_sale(make_sale(f"ref-num-{i}", pid),
                                       make_sale(f"ref-num-{i}", pid).items))
    numeros = [r["invoice_number"] for r in
               db.execute_query("SELECT invoice_number FROM sales ORDER BY id")]
    ok = len(set(numeros)) == 3 and numeros == sorted(numeros)
    print(f"[{'OK' if ok else 'FAIL'}] numeracion unica y creciente: {numeros}")
    db.close()
    cleanup()
    assert ok


if __name__ == "__main__":
    tests = [
        test_reintento_no_duplica,
        test_vende_sin_stock,
        test_numeracion_sin_duplicados,
    ]
    failed = 0
    for t in tests:
        try:
            t()
        except Exception as e:
            print(f"[FAIL] {t.__name__}: {e}")
            failed += 1
    print(f"\n{'VENTAS OK' if failed == 0 else f'VENTAS FAIL: {failed}'}")
