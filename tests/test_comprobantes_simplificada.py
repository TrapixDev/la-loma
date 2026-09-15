"""Comprobantes posteriores con fecha, simplificada en crédito y default del POS."""

import os
import sys
import tempfile
from pathlib import Path

PROJECT_DIR = str(Path(__file__).resolve().parents[1])
sys.path.insert(0, PROJECT_DIR)
os.chdir(PROJECT_DIR)
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt6.QtWidgets import QApplication

from database.db_manager import DatabaseManager
from database.models import Product
from modules.categories.category_service import CategoryService
from modules.clients.client_service import ClientService
from modules.credit.credit_service import CreditService
from modules.credit.credit_widget import CreditDetailDialog, CreditSaleDialog
from modules.pos.cart_service import CartService
from modules.pos.pos_widget import POSWidget
from modules.products.product_service import ProductService
from modules.promotions.promotion_service import PromotionService
from network.session import session

TEST_DB = os.path.join(PROJECT_DIR, "tests", ".tmp", "test_comprobantes_extra.db")

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
        "credit": CreditService(db),
        "promotions": PromotionService(db),
    }


def _client(db, name="Cliente Comprobantes") -> int:
    return db.execute_insert(
        "INSERT INTO clients (id_type, id_number, name) VALUES (?, ?, ?)",
        ("01", "246813579", name))


def _sale_account_payment(db, total=100000.0):
    client_id = _client(db)
    sale_id = db.execute_insert(
        "INSERT INTO sales (invoice_number, client_id, total, payment_method, "
        "status) VALUES (?, ?, ?, ?, ?)",
        ("V-EXT1", client_id, total, "credito", "PENDIENTE"))
    credit = CreditService(db)
    account_id = credit.create_account(sale_id, client_id, "V-EXT1", total)
    payment_id = credit.make_payment(account_id, 40000.0, "efectivo")
    return client_id, account_id, payment_id


def test_adjuntar_comprobante_despues_con_fecha():
    db = _db()
    _client_id, account_id, payment_id = _sale_account_payment(db)
    credit = CreditService(db)
    assert credit.list_payment_images(payment_id) == []

    # Adjuntar después de creado el abono.
    tmp = Path(tempfile.mkdtemp(prefix="pos_comp_"))
    imagen = tmp / "comprobante.png"
    imagen.write_bytes(b"PNG")
    image_id = credit.add_payment_image(payment_id, str(imagen),
                                        "Adjuntado después")
    assert image_id > 0
    imagenes = credit.list_payment_images(payment_id)
    assert len(imagenes) == 1
    assert imagenes[0].created_at, "el comprobante debe tener fecha de subida"
    assert imagenes[0].description == "Adjuntado después"

    # El detalle habilita "Adjuntar comprobante" al seleccionar el abono.
    account = credit.get_by_id(account_id)
    dialog = CreditDetailDialog(account, _services(db))
    assert dialog.attach_button.isEnabled() is False
    dialog.payments_table.setCurrentCell(0, 0)
    app.processEvents()
    assert dialog.attach_button.isEnabled() is True


def test_credito_con_simplificada_sin_iva():
    db = _db()
    services = _services(db)
    product_id = ProductService(db).create(Product(
        code="SIM-1", name="Mueble simplificado", sale_price=100000.0,
        tax_rate=13.0))
    product = ProductService(db).get_by_id(product_id)
    client_id = _client(db)
    client = ClientService(db).get_by_id(client_id)
    cart = [{"product_id": product.id, "product_name": product.name,
             "quantity": 1, "unit_price": 100000.0, "tax_rate": 13.0,
             "discount": 0.0, "cabys_code": "", "total": 100000.0}]

    dialog = CreditSaleDialog(services, cart=cart, client=client)
    assert dialog.invoice_combo.currentData() == "general"
    assert "13,000" in dialog.tax_label.text()

    dialog.invoice_combo.setCurrentIndex(1)
    app.processEvents()
    assert dialog.invoice_combo.currentData() == "simplificada"
    assert "0.00" in dialog.tax_label.text()
    assert "100,000" in dialog.total_label.text()

    directo = CreditSaleDialog(services, cart=cart, client=client,
                               invoice_type="simplificada")
    assert directo.invoice_combo.currentData() == "simplificada"


def test_pos_por_defecto_simplificada():
    db = _db()
    services = _services(db)
    product_id = ProductService(db).create(Product(
        code="SIM-2", name="Mueble POS", sale_price=100000.0, tax_rate=13.0))
    product = ProductService(db).get_by_id(product_id)
    services["cart"] = CartService(db)

    pos = POSWidget(services)
    assert pos.invoice_type_combo.currentData() == "simplificada"
    pos.add_to_cart(product)
    assert "0.00" in pos.tax_label.text()
    assert "100,000" in pos.total_label.text()

    pos.invoice_type_combo.setCurrentIndex(0)
    app.processEvents()
    assert "13,000" in pos.tax_label.text()

    pos._clear_cart()
    assert pos.invoice_type_combo.currentData() == "simplificada"
