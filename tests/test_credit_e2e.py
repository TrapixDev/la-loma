"""Test end-to-end del flujo de crédito:

venta POS -> cuenta por cobrar -> abonos -> reportes (base caja).
"""

import os
import sys
from pathlib import Path

PROJECT_DIR = str(Path(__file__).resolve().parents[1])
sys.path.insert(0, PROJECT_DIR)
os.chdir(PROJECT_DIR)
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from database.db_manager import DatabaseManager
from database.models import Sale, SaleItem
from modules.credit.credit_service import CreditService
from modules.pos.cart_service import CartService
from modules.reports.reports_service import ReportsService
from network.session import session

TEST_DB = os.path.join(PROJECT_DIR, "tests", ".tmp", "test_credit_e2e.db")

session.set("test-token", 1, "Tester", "CAJA-1")

_last_db: DatabaseManager | None = None


def cleanup():
    global _last_db
    if _last_db is not None:
        _last_db.close()
        _last_db = None
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


def setup_function():
    cleanup()


def teardown_function():
    cleanup()


def _db() -> DatabaseManager:
    global _last_db
    db = DatabaseManager(TEST_DB)
    db.initialize()
    _last_db = db
    return db


def _client(db) -> int:
    return db.execute_insert(
        "INSERT INTO clients (id_type, id_number, name) VALUES (?, ?, ?)",
        ("01", "123456789", "Cliente E2E"),
    )


def _product(db, cost=40000.0, price=100000.0) -> int:
    return db.execute_insert(
        "INSERT INTO products (name, sale_price, cost_price) VALUES (?, ?, ?)",
        ("Mesa E2E", price, cost),
    )


def _range():
    return "2000-01-01", "2100-01-01"


def _create_credit_sale(db, client_id, product_id, price=100000.0, qty=1.0,
                        with_account=False):
    """Simula la venta a crédito del POS: venta + items, como en CreditSaleDialog."""
    cart = CartService(db)
    sale = Sale(
        client_id=client_id,
        subtotal=price * qty,
        discount=0.0,
        tax_amount=0.0,
        total=price * qty,
        payment_method="credito",
        status="completada",
        station="CAJA-1",
        user_id=1,
        user_name="Tester",
        items=[],
    )
    item = SaleItem(
        product_id=product_id,
        product_name="Mesa E2E",
        quantity=qty,
        unit_price=price,
        discount=0.0,
        tax_amount=0.0,
        total=price * qty,
    )
    sale_id = cart.create_sale(
        sale, [item],
        credit_notes="Cuenta E2E" if with_account else None)
    created = cart.get_sale(sale_id)
    return sale_id, created.invoice_number


def test_flujo_completo_credito():
    db = _db()
    client_id = _client(db)
    product_id = _product(db, cost=40000.0, price=100000.0)
    cart = CartService(db)
    credit = CreditService(db)
    report = ReportsService(db)

    sale_id, invoice = _create_credit_sale(db, client_id, product_id)
    assert invoice.startswith("V-")

    account_id = credit.create_account(
        sale_id, client_id, invoice, 100000.0, "Venta a crédito E2E")
    account = credit.get_by_id(account_id)
    assert account.balance == 100000.0
    assert account.status == "pendiente"
    assert credit.get_by_client(client_id)[0].invoice_number == invoice

    # El costo de fabricación se cuenta al vender, el ingreso aún no.
    summary = report.summary(*_range())
    assert summary["cost"] == 40000.0
    assert summary["ingresos"] == 0.0

    # Primer abono parcial: entra como ingreso en base a caja.
    credit.make_payment(account_id, 40000.0, "efectivo", notes="Abono 40%")
    account = credit.get_by_id(account_id)
    assert account.amount_paid == 40000.0
    assert account.balance == 60000.0
    summary = report.summary(*_range())
    assert summary["ingresos"] == 40000.0

    # Abono final: la cuenta queda pagada y el ingreso completo.
    credit.make_payment(account_id, 60000.0, "transferencia")
    account = credit.get_by_id(account_id)
    assert account.balance == 0.0
    assert account.status == "pagada"
    summary = report.summary(*_range())
    assert summary["ingresos"] == 100000.0
    assert summary["cost"] == 40000.0
    assert summary["gross_profit"] == 60000.0

    full = report.full_summary(*_range())
    assert full["egresos"] == 40000.0
    assert full["net_profit"] == 60000.0

    types = [m["tipo"] for m in report.list_movements(*_range())]
    assert "CRÉDITO" in types
    assert "ABONO" in types

    # Doble anulación no debe romper ni cambiar el resultado.
    assert cart.anular_venta(sale_id, "Prueba", excluir_reporte=True) is True
    assert cart.anular_venta(sale_id, "Prueba", excluir_reporte=True) is False
    summary = report.summary(*_range())
    assert summary["ingresos"] == 0.0
    assert summary["cost"] == 0.0


def test_venta_credito_anulada_no_aporta_ingresos():
    db = _db()
    client_id = _client(db)
    product_id = _product(db, cost=30000.0, price=80000.0)
    cart = CartService(db)
    credit = CreditService(db)
    report = ReportsService(db)

    sale_id, invoice = _create_credit_sale(db, client_id, product_id, price=80000.0)
    account_id = credit.create_account(sale_id, client_id, invoice, 80000.0)
    credit.make_payment(account_id, 80000.0, "efectivo")
    assert report.summary(*_range())["ingresos"] == 80000.0

    cart.anular_venta(sale_id, "Error de facturación", excluir_reporte=True)
    summary = report.summary(*_range())
    assert summary["ingresos"] == 0.0
    assert summary["cost"] == 0.0

    account = credit.get_by_id(account_id)
    assert account.status == "anulada"
    assert account.balance == 0.0

    by_day = {row["day"]: row for row in report.daily_breakdown(*_range())}
    for row in by_day.values():
        assert row["ingresos"] == 0.0
        assert row["cost"] == 0.0


def test_venta_credito_atomica_crea_cuenta():
    db = _db()
    client_id = _client(db)
    product_id = _product(db, cost=40000.0, price=100000.0)
    credit = CreditService(db)

    _sale_id, invoice = _create_credit_sale(
        db, client_id, product_id, with_account=True)
    accounts = credit.get_by_client(client_id)
    assert len(accounts) == 1
    assert accounts[0].invoice_number == invoice
    assert accounts[0].total == 100000.0
    assert accounts[0].balance == 100000.0
    assert accounts[0].status == "pendiente"
