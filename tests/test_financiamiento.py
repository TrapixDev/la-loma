"""Financiamiento informativo: plan de meses sin intereses (Fase 6)."""

import os
import sys
from pathlib import Path

PROJECT_DIR = str(Path(__file__).resolve().parents[1])
sys.path.insert(0, PROJECT_DIR)
os.chdir(PROJECT_DIR)
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt6.QtWidgets import QApplication

from database.db_manager import DatabaseManager
from database.models import Product, Sale, SaleItem
from modules.categories.category_service import CategoryService
from modules.clients.client_service import ClientService
from modules.credit.credit_service import CreditService
from modules.credit.credit_widget import CreditSaleDialog
from modules.pos.cart_service import CartService
from modules.products.product_service import ProductService
from modules.promotions.promotion_service import PromotionService
from network.session import session

TEST_DB = os.path.join(PROJECT_DIR, "tests", ".tmp", "test_financiamiento.db")

app = QApplication.instance() or QApplication([])
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


def _services(db) -> dict:
    return {
        "db": db,
        "product": ProductService(db),
        "category": CategoryService(db),
        "client": ClientService(db),
        "cart": CartService(db),
        "credit": CreditService(db),
        "promotions": PromotionService(db),
    }


def _setup(db, price=120000.0):
    product_id = ProductService(db).create(Product(
        code="FIN-1", name="Mueble financiado", sale_price=price,
        tax_rate=0.0))
    product = ProductService(db).get_by_id(product_id)
    client_id = db.execute_insert(
        "INSERT INTO clients (id_type, id_number, name) VALUES (?, ?, ?)",
        ("01", "777777777", "Cliente Financiado"))
    client = ClientService(db).get_by_id(client_id)
    PromotionService(db).create(
        "3, 6 o 12 meses", "financing",
        {"min_total": 100000, "months": [3, 6, 12]})
    cart_item = {
        "product_id": product.id, "product_name": product.name,
        "quantity": 1, "unit_price": price, "tax_rate": 0.0,
        "discount": 0.0, "cabys_code": "", "total": price,
    }
    return product, client, client_id, cart_item


def test_financiamiento_persistido_en_cuenta():
    db = _db()
    product, client, client_id, cart_item = _setup(db)
    sale = Sale(client_id=client_id, subtotal=120000.0, tax_amount=0.0,
                total=120000.0, payment_method="credito", status="PENDIENTE",
                sale_reference="ref-fin-1")
    item = SaleItem(product_id=product.id, product_name=product.name,
                    quantity=1, unit_price=120000.0, total=120000.0)
    CartService(db).create_sale(
        sale, [item], credit_notes="Venta financiada",
        financing_months=6, financing_installment=20000.0)
    account = CreditService(db).get_by_client(client_id)[0]
    assert account.financing_months == 6
    assert account.financing_installment == 20000.0


def test_create_account_con_financiamiento():
    db = _db()
    _product, _client, client_id, _cart = _setup(db)
    sale_id = db.execute_insert(
        "INSERT INTO sales (invoice_number, client_id, total, payment_method, "
        "status) VALUES (?, ?, ?, ?, ?)",
        ("V-FIN1", client_id, 120000.0, "credito", "PENDIENTE"))
    account_id = CreditService(db).create_account(
        sale_id, client_id, "V-FIN1", 120000.0, financing_months=12,
        financing_installment=10000.0)
    account = CreditService(db).get_by_id(account_id)
    assert account.financing_months == 12
    assert account.financing_installment == 10000.0


def test_dialogo_muestra_opciones_de_plan():
    db = _db()
    _product, client, _client_id, cart_item = _setup(db)
    dialog = CreditSaleDialog(_services(db), cart=[cart_item], client=client)
    assert dialog.plan_row.isHidden() is False
    opciones = [dialog.plan_combo.itemData(i)
                for i in range(dialog.plan_combo.count())]
    assert opciones == [0, 3, 6, 12]
    assert "12 meses de" in dialog.plan_combo.itemText(3)


def test_dialogo_sin_plan_bajo_minimo():
    db = _db()
    _product, client, _client_id, cart_item = _setup(db, price=50000.0)
    dialog = CreditSaleDialog(_services(db), cart=[cart_item], client=client)
    assert dialog.plan_row.isHidden() is True


def test_encargo_no_muestra_plan():
    db = _db()
    _product, client, _client_id, cart_item = _setup(db)
    dialog = CreditSaleDialog(_services(db), cart=[cart_item], client=client,
                              mode="encargo")
    assert dialog.plan_row.isHidden() is True
