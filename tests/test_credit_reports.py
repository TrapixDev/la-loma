"""Tests de reportes con crédito: ingresos en base a caja.

Una venta a crédito no suma a los ingresos al momento de la venta; suma
conforme se registran los abonos. El costo de fabricación sí se cuenta en la
fecha de la venta.
"""

import os
import sys
from pathlib import Path

PROJECT_DIR = str(Path(__file__).resolve().parents[1])
sys.path.insert(0, PROJECT_DIR)
os.chdir(PROJECT_DIR)
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from database.db_manager import DatabaseManager
from modules.credit.credit_service import CreditService
from modules.reports.reports_service import ReportsService
from network.session import session

TEST_DB = os.path.join(PROJECT_DIR, "tests", ".tmp", "test_credit_reports.db")

session.set("test-token", 1, "Tester", "CAJA-1")

_counter = 0
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


def _seed_sale(db, total=100000.0, cost=40000.0, method="credito",
               created_at=None):
    """Crea cliente + producto + venta + item. Devuelve (client_id, sale_id)."""
    global _counter
    _counter += 1
    client_id = db.execute_insert(
        "INSERT INTO clients (id_type, id_number, name) VALUES (?, ?, ?)",
        ("01", f"30000000{_counter:02d}", f"Cliente {_counter}"),
    )
    if created_at:
        sale_id = db.execute_insert(
            "INSERT INTO sales (invoice_number, client_id, total, payment_method, "
            "status, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (f"V-{_counter:05d}", client_id, total, method, "completada",
             created_at),
        )
    else:
        sale_id = db.execute_insert(
            "INSERT INTO sales (invoice_number, client_id, total, payment_method, "
            "status) VALUES (?, ?, ?, ?, ?)",
            (f"V-{_counter:05d}", client_id, total, method, "completada"),
        )
    product_id = db.execute_insert(
        "INSERT INTO products (name, sale_price, cost_price) VALUES (?, ?, ?)",
        (f"Prod {_counter}", total, cost),
    )
    db.execute_insert(
        "INSERT INTO sale_items (sale_id, product_id, product_name, quantity, "
        "unit_price, unit_cost, total) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (sale_id, product_id, f"Prod {_counter}", 1.0, total, cost, total),
    )
    return client_id, sale_id


def _range():
    return "2000-01-01", "2100-01-01"


def test_credit_sale_not_revenue_at_sale():
    db = _db()
    _seed_sale(db, total=100000.0, cost=40000.0)
    report = ReportsService(db)
    summary = report.summary(*_range())
    assert summary["sale_count"] == 1
    assert summary["ingresos"] == 0.0
    assert summary["cost"] == 40000.0
    assert summary["gross_profit"] == -40000.0


def test_cash_sale_is_revenue_immediately():
    db = _db()
    _seed_sale(db, total=50000.0, cost=20000.0, method="efectivo")
    report = ReportsService(db)
    summary = report.summary(*_range())
    assert summary["ingresos"] == 50000.0
    assert summary["cost"] == 20000.0
    assert summary["gross_profit"] == 30000.0


def test_partial_payment_is_revenue():
    db = _db()
    credit = CreditService(db)
    client_id, sale_id = _seed_sale(db, total=100000.0, cost=40000.0)
    account_id = credit.create_account(sale_id, client_id, "V-00001", 100000.0)
    credit.make_payment(account_id, 30000.0, "efectivo")
    summary = ReportsService(db).summary(*_range())
    assert summary["ingresos"] == 30000.0
    assert summary["cost"] == 40000.0


def test_full_payment_is_revenue():
    db = _db()
    credit = CreditService(db)
    client_id, sale_id = _seed_sale(db, total=100000.0, cost=40000.0)
    account_id = credit.create_account(sale_id, client_id, "V-00001", 100000.0)
    credit.make_payment(account_id, 60000.0, "efectivo")
    credit.make_payment(account_id, 40000.0, "tarjeta")
    summary = ReportsService(db).summary(*_range())
    assert summary["ingresos"] == 100000.0
    assert summary["gross_profit"] == 60000.0


def test_mixed_sales_summary():
    db = _db()
    credit = CreditService(db)
    client_id, sale_id = _seed_sale(db, total=100000.0, cost=40000.0)
    _seed_sale(db, total=25000.0, cost=10000.0, method="efectivo")
    account_id = credit.create_account(sale_id, client_id, "V-00001", 100000.0)
    credit.make_payment(account_id, 50000.0, "sinpe")
    summary = ReportsService(db).summary(*_range())
    assert summary["sale_count"] == 2
    assert summary["ingresos"] == 75000.0
    assert summary["cost"] == 50000.0
    assert summary["gross_profit"] == 25000.0


def test_daily_breakdown_attributes_payment_to_day():
    db = _db()
    client_id, sale_id = _seed_sale(
        db, total=80000.0, cost=30000.0, created_at="2026-05-10 10:00:00")
    db.execute_insert(
        "INSERT INTO credit_accounts (sale_id, client_id, invoice_number, total, "
        "amount_paid, balance, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (sale_id, client_id, "V-00001", 80000.0, 20000.0, 60000.0, "pendiente"),
    )
    account_id = db.execute_query(
        "SELECT id FROM credit_accounts WHERE sale_id = ?", (sale_id,))[0]["id"]
    db.execute_insert(
        "INSERT INTO credit_payments (credit_account_id, amount, payment_method, "
        "created_at) VALUES (?, ?, ?, ?)",
        (account_id, 20000.0, "efectivo", "2026-05-15 09:00:00"),
    )
    rows = ReportsService(db).daily_breakdown("2026-05-01", "2026-05-31")
    by_day = {r["day"]: r for r in rows}
    assert by_day["2026-05-10"]["ingresos"] == 0.0
    assert by_day["2026-05-10"]["cost"] == 30000.0
    assert by_day["2026-05-15"]["ingresos"] == 20000.0
    assert by_day["2026-05-15"]["cost"] == 0.0


def test_list_movements_includes_credit_and_abono():
    db = _db()
    client_id, sale_id = _seed_sale(db, total=100000.0, cost=40000.0)
    account_id = db.execute_insert(
        "INSERT INTO credit_accounts (sale_id, client_id, invoice_number, total, "
        "amount_paid, balance, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (sale_id, client_id, "V-00001", 100000.0, 0.0, 100000.0, "pendiente"),
    )
    db.execute_insert(
        "INSERT INTO credit_payments (credit_account_id, amount, payment_method) "
        "VALUES (?, ?, ?)",
        (account_id, 25000.0, "efectivo"),
    )
    types = [m["tipo"] for m in ReportsService(db).list_movements(*_range())]
    assert "CRÉDITO" in types
    assert "ABONO" in types


def test_full_summary_egresos_combines_cost_and_expenses():
    db = _db()
    _seed_sale(db, total=100000.0, cost=40000.0, method="efectivo")
    db.execute_insert(
        "INSERT INTO expenses (expense_date, category, description, amount) "
        "VALUES (?, ?, ?, ?)",
        ("2026-05-10", "Proveedores", "Madera", 15000.0),
    )
    full = ReportsService(db).full_summary("2000-01-01", "2100-01-01")
    assert full["cost"] == 40000.0
    assert full["expenses"] == 15000.0
    assert full["egresos"] == 55000.0
    assert full["net_profit"] == full["ingresos"] - full["egresos"]


def test_credit_sale_cost_in_daily_egresos():
    db = _db()
    _seed_sale(db, total=80000.0, cost=30000.0, created_at="2026-05-10 10:00:00")
    db.execute_insert(
        "INSERT INTO expenses (expense_date, category, amount) VALUES (?, ?, ?)",
        ("2026-05-10", "Proveedores", 5000.0),
    )
    rows = ReportsService(db).daily_breakdown("2026-05-01", "2026-05-31")
    by_day = {r["day"]: r for r in rows}
    assert by_day["2026-05-10"]["cost"] == 30000.0
    assert by_day["2026-05-10"]["expenses"] == 5000.0
    assert by_day["2026-05-10"]["egresos"] == 35000.0


def test_abonos_venta_anulada_no_cuentan():
    db = _db()
    credit = CreditService(db)
    client_id, sale_id = _seed_sale(db, total=100000.0, cost=40000.0)
    account_id = credit.create_account(sale_id, client_id, "V-00001", 100000.0)
    credit.make_payment(account_id, 30000.0, "efectivo")
    db.execute_update(
        "UPDATE sales SET status = 'anulada', excluir_reporte = 1 WHERE id = ?",
        (sale_id,),
    )
    summary = ReportsService(db).summary(*_range())
    assert summary["ingresos"] == 0.0
    assert summary["cost"] == 0.0
    assert summary["sale_count"] == 0


def test_nota_credito_resta_ingresos_contado():
    db = _db()
    client_id, sale_id = _seed_sale(db, total=100000.0, cost=40000.0,
                                    method="efectivo")
    report = ReportsService(db)
    report.create_credit_note(sale_id, "Devolución parcial", "Devolución",
                              total=15000.0)
    summary = report.summary(*_range())
    assert summary["ingresos"] == 85000.0
    assert summary["credit_notes"] == 15000.0
    assert summary["gross_profit"] == 45000.0
    types = [m["tipo"] for m in report.list_movements(*_range())]
    assert "NOTA" in types


def test_nota_credito_credito_ajusta_cuenta():
    db = _db()
    credit = CreditService(db)
    client_id, sale_id = _seed_sale(db, total=100000.0, cost=40000.0)
    account_id = credit.create_account(sale_id, client_id, "V-00001", 100000.0)
    ReportsService(db).create_credit_note(
        sale_id, "Descuento acordado", "Descuento", total=20000.0)
    account = credit.get_by_id(account_id)
    assert account.total == 80000.0
    assert account.balance == 80000.0
    assert account.status == "pendiente"
    # La nota no se resta de ingresos en ventas a crédito (base caja).
    summary = ReportsService(db).summary(*_range())
    assert summary["ingresos"] == 0.0
    credit.make_payment(account_id, 80000.0, "efectivo")
    summary = ReportsService(db).summary(*_range())
    assert summary["ingresos"] == 80000.0


def test_nota_credito_usa_numero_reservado():
    db = _db()
    _client_id, sale_id = _seed_sale(db, total=100000.0, cost=40000.0,
                                     method="efectivo")
    report = ReportsService(db)
    numero = report.reserve_credit_note_number()
    assert numero == 1
    report.create_credit_note(sale_id=sale_id, motivo="Motivo", razon="Detalle",
                              total=10000.0, numero=numero)
    notes = report.get_credit_notes()
    assert notes[0]["invoice_number"] == "NC-00001"
    assert report.reserve_credit_note_number() == 2


def test_rango_incluye_ultimo_dia_del_mes():
    db = _db()
    _seed_sale(db, total=10000.0, cost=1000.0, method="efectivo",
               created_at="2026-05-31 15:00:00")
    summary = ReportsService(db).summary("2026-05-01", "2026-05-31")
    assert summary["ingresos"] == 10000.0
