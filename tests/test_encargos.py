"""Tests de encargos/apartados: prima, entrega y filtros (Fase 1)."""

import os
import sys
from pathlib import Path

PROJECT_DIR = str(Path(__file__).resolve().parents[1])
sys.path.insert(0, PROJECT_DIR)
os.chdir(PROJECT_DIR)
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from database.db_manager import DatabaseManager
from database.models import Sale, SaleItem
from modules.clients.client_service import ClientService
from modules.credit.credit_service import CreditService
from modules.pos.cart_service import CartService
from modules.products.product_service import ProductService
from modules.reports.reports_service import ReportsService
from network.session import session

TEST_DB = os.path.join(PROJECT_DIR, "tests", ".tmp", "test_encargos.db")

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


def _client(db, name="Cliente Encargo") -> int:
    return db.execute_insert(
        "INSERT INTO clients (id_type, id_number, name) VALUES (?, ?, ?)",
        ("01", "123456789", name),
    )


def _product(db) -> int:
    return db.execute_insert(
        "INSERT INTO products (name, sale_price, cost_price) VALUES (?, ?, ?)",
        ("Mesa Encargo", 100000.0, 40000.0),
    )


def _create_order(db, client_id, product_id, total=100000.0, prima=30000.0,
                  due_date="2026-10-15", reference="ref-encargo-1",
                  created_at=None):
    cart = CartService(db)
    sale = Sale(
        client_id=client_id,
        subtotal=total,
        discount=0.0,
        tax_amount=0.0,
        total=total,
        payment_method="credito",
        status="PENDIENTE",
        sale_reference=reference,
        user_id=1,
        user_name="Tester",
        created_at=created_at,
        items=[],
    )
    item = SaleItem(product_id=product_id, product_name="Mesa Encargo",
                    quantity=1, unit_price=total, total=total)
    sale_id = cart.create_sale(
        sale, [item], credit_notes="Encargo de prueba",
        account_type="encargo", due_date=due_date, prima=prima,
        prima_method="sinpe")
    return cart, sale_id


def test_crear_encargo_con_prima():
    db = _db()
    client_id = _client(db)
    product_id = _product(db)
    cart, sale_id = _create_order(db, client_id, product_id)
    credit = CreditService(db)
    accounts = credit.get_by_client(client_id)
    assert len(accounts) == 1
    account = accounts[0]
    assert account.account_type == "encargo"
    assert account.delivery_status == "pendiente"
    assert account.due_date == "2026-10-15"
    assert account.total == 100000.0
    assert account.amount_paid == 30000.0
    assert account.balance == 70000.0
    assert account.status == "pendiente"

    payments = credit.get_payments(account.id)
    assert len(payments) == 1
    assert payments[0].amount == 30000.0
    assert payments[0].payment_method == "sinpe"
    assert payments[0].payment_reference == "ref-encargo-1:prima"
    assert credit.get_summary()["encargos_pendientes"] == 1
    assert credit.get_summary()["total_encargos"] == 70000.0


def test_encargo_sin_prima():
    db = _db()
    client_id = _client(db)
    product_id = _product(db)
    cart, sale_id = _create_order(db, client_id, product_id, prima=0.0,
                                  reference="ref-encargo-2")
    account = CreditService(db).get_by_client(client_id)[0]
    assert account.amount_paid == 0.0
    assert account.balance == 100000.0
    assert CreditService(db).get_payments(account.id) == []


def test_entregar_encargo():
    db = _db()
    client_id = _client(db)
    product_id = _product(db)
    _create_order(db, client_id, product_id, reference="ref-encargo-3")
    credit = CreditService(db)
    account = credit.get_by_client(client_id)[0]
    assert credit.mark_delivered(account.id) is True
    account = credit.get_by_id(account.id)
    assert account.delivery_status == "entregado"
    assert account.delivered_at
    assert credit.get_summary()["encargos_pendientes"] == 0


def test_filtro_por_tipo():
    db = _db()
    client_id = _client(db)
    product_id = _product(db)
    _create_order(db, client_id, product_id, reference="ref-encargo-4")
    cart = CartService(db)
    credit = CreditService(db)
    sale = Sale(client_id=client_id, subtotal=50000.0, tax_amount=0.0,
                total=50000.0, payment_method="credito", status="PENDIENTE",
                sale_reference="ref-credito-1")
    item = SaleItem(product_id=product_id, product_name="Mesa Encargo",
                    quantity=1, unit_price=50000.0, total=50000.0)
    cart.create_sale(sale, [item], credit_notes="Crédito normal")

    assert len(credit.get_all(type_filter="encargo")) == 1
    assert len(credit.get_all(type_filter="credito")) == 1
    assert len(credit.get_all()) == 2


def test_prima_idempotente():
    db = _db()
    client_id = _client(db)
    product_id = _product(db)
    cart, first_id = _create_order(db, client_id, product_id,
                                   reference="ref-encargo-5")
    _, second_id = _create_order(db, client_id, product_id,
                                 reference="ref-encargo-5")
    assert first_id == second_id
    account = CreditService(db).get_by_client(client_id)[0]
    assert len(CreditService(db).get_payments(account.id)) == 1
    assert account.amount_paid == 30000.0


def test_prima_mayor_al_total_rechazada():
    db = _db()
    client_id = _client(db)
    product_id = _product(db)
    try:
        _create_order(db, client_id, product_id, total=100000.0, prima=150000.0,
                      reference="ref-encargo-6")
        raised = False
    except ValueError:
        raised = True
    assert raised
    assert db.execute_query("SELECT COUNT(*) AS t FROM sales")[0]["t"] == 0


def test_anular_encargo():
    db = _db()
    client_id = _client(db)
    product_id = _product(db)
    cart, sale_id = _create_order(db, client_id, product_id,
                                  reference="ref-encargo-7")
    assert cart.anular_venta(sale_id, "Prueba", excluir_reporte=True) is True
    account = CreditService(db).get_by_client(client_id)[0]
    assert account.status == "anulada"
    assert account.balance == 0.0


def test_costo_encargo_pendiente_no_cuenta():
    db = _db()
    client_id = _client(db)
    product_id = _product(db)
    _create_order(db, client_id, product_id, reference="ref-costo-1",
                  created_at="2026-04-10 10:00:00")
    report = ReportsService(db)
    assert report.summary("2026-04-01", "2026-04-30")["cost"] == 0.0
    assert report.summary("2000-01-01", "2100-01-01")["cost"] == 0.0
    by_day = {row["day"]: row for row in
              report.daily_breakdown("2026-04-01", "2026-04-30")}
    assert by_day["2026-04-10"]["cost"] == 0.0


def test_costo_encargo_entregado_en_fecha_entrega():
    db = _db()
    client_id = _client(db)
    product_id = _product(db)
    _create_order(db, client_id, product_id, reference="ref-costo-2",
                  created_at="2026-04-10 10:00:00")
    account = CreditService(db).get_by_client(client_id)[0]
    db.execute_update(
        "UPDATE credit_accounts SET delivery_status = 'entregado', "
        "delivered_at = '2026-05-20 12:00:00' WHERE id = ?",
        (account.id,),
    )
    report = ReportsService(db)
    assert report.summary("2026-04-01", "2026-04-30")["cost"] == 0.0
    assert report.summary("2026-05-01", "2026-05-31")["cost"] == 40000.0
    by_day = {row["day"]: row for row in
              report.daily_breakdown("2026-05-01", "2026-05-31")}
    assert by_day["2026-05-20"]["cost"] == 40000.0
    months = {row["month"]: row for row in report.monthly_breakdown(2026)}
    assert months[4]["cost"] == 0.0
    assert months[5]["cost"] == 40000.0


def test_costo_credito_normal_sigue_en_fecha_venta():
    db = _db()
    client_id = _client(db)
    product_id = _product(db)
    cart = CartService(db)
    sale = Sale(client_id=client_id, subtotal=80000.0, tax_amount=0.0,
                total=80000.0, payment_method="credito", status="PENDIENTE",
                sale_reference="ref-costo-3", created_at="2026-04-15 09:00:00")
    item = SaleItem(product_id=product_id, product_name="Mesa Encargo",
                    quantity=1, unit_price=80000.0, total=80000.0)
    cart.create_sale(sale, [item], credit_notes="Crédito normal")
    report = ReportsService(db)
    assert report.summary("2026-04-01", "2026-04-30")["cost"] == 40000.0


def test_factura_del_encargo_se_genera():
    import tempfile
    from pathlib import Path

    from PyQt6.QtWidgets import QApplication

    from config import Config
    from modules.documentos.factura_service import generar_documentos
    from modules.documentos.xml_factura import cargar_empresa

    if QApplication.instance() is None:
        _app = QApplication([])

    db = _db()
    client_id = _client(db)
    product_id = _product(db)
    cart, sale_id = _create_order(db, client_id, product_id,
                                  reference="ref-fact-1")
    original = Config.DOCS_PATH
    Config.DOCS_PATH = tempfile.mkdtemp(prefix="pos_docs_")
    try:
        saved = cart.get_sale(sale_id)
        company = cargar_empresa(db)
        resultado = generar_documentos(saved, company)
        assert resultado["pdf"], resultado
        assert Path(resultado["pdf"]).is_file()
        assert saved.invoice_number in Path(resultado["pdf"]).name
    finally:
        Config.DOCS_PATH = original


def test_factura_xml_del_encargo_se_genera():
    import tempfile
    from pathlib import Path

    from PyQt6.QtWidgets import QApplication

    from config import Config
    from modules.credit.credit_widget import CreditDetailDialog
    from modules.documentos.factura_service import generar_documentos
    from modules.documentos.xml_factura import (
        build_factura_payload,
        cargar_empresa,
    )

    if QApplication.instance() is None:
        _app = QApplication([])

    db = _db()
    client_id = _client(db)
    product_id = _product(db)
    cart, sale_id = _create_order(db, client_id, product_id,
                                  reference="ref-fe-1")
    saved = cart.get_sale(sale_id)
    credit = CreditService(db)
    services = {
        "db": db,
        "cart": cart,
        "credit": credit,
        "product": ProductService(db),
        "client": ClientService(db),
    }
    account = credit.get_by_client(client_id)[0]
    dialog = CreditDetailDialog(account, services)
    items = dialog._items_para_factura(saved)
    assert len(items) == 1
    assert items[0]["product_name"] == "Mesa Encargo"
    assert "tax_rate" in items[0]
    assert "cabys_code" in items[0]

    company = cargar_empresa(db)
    client = ClientService(db).get_by_id(client_id)
    totals = {
        "subtotal": saved.subtotal,
        "discount": saved.discount,
        "tax_amount": saved.tax_amount,
        "total": saved.total,
    }
    payload = build_factura_payload(company, client, items, totals,
                                    "001-001-0000000001")
    assert payload

    original = Config.DOCS_PATH
    Config.DOCS_PATH = tempfile.mkdtemp(prefix="pos_docs_fe_")
    try:
        resultado = generar_documentos(saved, company, payload=payload,
                                       clave="", medio_pago="01")
        assert resultado["xml"], resultado
        assert Path(resultado["xml"]).is_file()
        assert Path(resultado["xml"]).read_text(encoding="utf-8").lstrip().startswith("<")
        assert resultado["pdf"]
    finally:
        Config.DOCS_PATH = original
