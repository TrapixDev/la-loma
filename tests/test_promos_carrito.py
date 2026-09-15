"""Promociones de producto aplicadas al carrito del POS y de crédito (Fase 4)."""

import json
import os
import sys
from pathlib import Path

PROJECT_DIR = str(Path(__file__).resolve().parents[1])
sys.path.insert(0, PROJECT_DIR)
os.chdir(PROJECT_DIR)
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt6.QtWidgets import QApplication

from database.db_manager import DatabaseManager
from database.models import Client, Product, Sale, SaleItem
from modules.categories.category_service import CategoryService
from modules.clients.client_service import ClientService
from modules.credit.credit_service import CreditService
from modules.credit.credit_widget import CreditSaleDialog
from modules.pos.cart_service import CartService
from modules.pos.pos_widget import POSWidget
from modules.products.product_service import ProductService
from modules.promotions.promotion_service import PromotionService
from network.session import session

TEST_DB = os.path.join(PROJECT_DIR, "tests", ".tmp", "test_promos_carrito.db")

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


def _product(db, code, name, price) -> Product:
    service = ProductService(db)
    product_id = service.create(Product(
        code=code, name=name, sale_price=price, tax_rate=0.0))
    return service.get_by_id(product_id)


def _combo_promo(db, required, target, percent=15) -> None:
    PromotionService(db).create(
        "Combo promo", "bundle",
        {"product_id": required.id, "discount_product_id": target.id,
         "percent": percent})


def test_pos_aplica_bundle():
    db = _db()
    mesa = _product(db, "PR-1", "Mesa promo", 100000)
    lampara = _product(db, "PR-2", "Lámpara promo", 50000)
    _combo_promo(db, mesa, lampara)

    pos = POSWidget(_services(db))
    pos.add_to_cart(mesa)
    pos.add_to_cart(lampara)
    assert pos.cart[0]["discount"] == 0.0
    assert pos.cart[1]["discount"] == 7500.0
    assert "142,500" in pos.total_label.text()
    assert "Combo promo" in pos.promo_label.text()


def test_pos_volumen_recalcula_al_agregar():
    db = _db()
    silla = _product(db, "PR-3", "Silla promo", 10000)
    PromotionService(db).create(
        "Sillas volumen", "volume",
        {"product_id": silla.id, "tiers": [[4, 10], [6, 20]]})

    pos = POSWidget(_services(db))
    for _ in range(5):
        pos.add_to_cart(silla)
    assert pos.cart[0]["discount"] == 5000.0
    pos.add_to_cart(silla)
    assert pos.cart[0]["quantity"] == 6
    assert pos.cart[0]["discount"] == 12000.0
    assert "48,000" in pos.total_label.text()


def test_pos_quitar_producto_quita_promo():
    db = _db()
    mesa = _product(db, "PR-4", "Mesa promo", 100000)
    lampara = _product(db, "PR-5", "Lámpara promo", 50000)
    _combo_promo(db, mesa, lampara)

    pos = POSWidget(_services(db))
    pos.add_to_cart(mesa)
    pos.add_to_cart(lampara)
    assert pos.cart[1]["discount"] == 7500.0
    pos.cart_table.setCurrentCell(0, 0)
    pos._remove_selected_item()
    assert len(pos.cart) == 1
    assert pos.cart[0]["discount"] == 0.0
    assert "50,000" in pos.total_label.text()


def test_credito_dialogo_aplica_bundle():
    db = _db()
    mesa = _product(db, "PR-6", "Mesa promo", 100000)
    lampara = _product(db, "PR-7", "Lámpara promo", 50000)
    _combo_promo(db, mesa, lampara)
    client_id = db.execute_insert(
        "INSERT INTO clients (id_type, id_number, name) VALUES (?, ?, ?)",
        ("01", "123456789", "Cliente Promos"))
    client = ClientService(db).get_by_id(client_id)
    cart = [
        {"product_id": mesa.id, "product_name": mesa.name, "quantity": 1,
         "unit_price": 100000.0, "tax_rate": 0.0, "discount": 0.0,
         "cabys_code": "", "total": 100000.0},
        {"product_id": lampara.id, "product_name": lampara.name, "quantity": 1,
         "unit_price": 50000.0, "tax_rate": 0.0, "discount": 0.0,
         "cabys_code": "", "total": 50000.0},
    ]

    dialog = CreditSaleDialog(_services(db), cart=cart, client=client)
    assert dialog.cart[1]["discount"] == 7500.0
    assert "7,500" in dialog.discount_label.text()
    assert "142,500" in dialog.total_label.text()
    assert "Combo promo" in dialog.promo_label.text()


def test_persistencia_promotions_applied():
    db = _db()
    product = _product(db, "PR-8", "Mesa promo", 100000)
    db.execute_insert(
        "INSERT INTO clients (id_type, id_number, name) VALUES (?, ?, ?)",
        ("01", "987654321", "Cliente Persistencia"))
    cart_service = CartService(db)
    applied = json.dumps([{"name": "Combo promo", "type": "bundle",
                           "amount": 7500.0}], ensure_ascii=False)
    sale = Sale(client_id=1, subtotal=100000.0, discount=7500.0,
                tax_amount=0.0, total=92500.0, payment_method="efectivo",
                promotions_applied=applied, sale_reference="ref-promo-1")
    item = SaleItem(product_id=product.id, product_name="Mesa promo",
                    quantity=1, unit_price=100000.0, discount=7500.0,
                    total=92500.0)
    sale_id = cart_service.create_sale(sale, [item])
    saved = cart_service.get_sale(sale_id)
    assert "Combo promo" in saved.promotions_applied
    assert saved.discount == 7500.0
    assert saved.total == 92500.0
