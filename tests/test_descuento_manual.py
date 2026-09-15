"""Descuento manual en el carrito del POS (porcentaje o monto)."""

import os
import sys
from pathlib import Path

PROJECT_DIR = str(Path(__file__).resolve().parents[1])
sys.path.insert(0, PROJECT_DIR)
os.chdir(PROJECT_DIR)
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt6.QtWidgets import QApplication

from database.db_manager import DatabaseManager
from database.models import Product
from modules.categories.category_service import CategoryService
from modules.pos.cart_service import CartService
from modules.pos.discount_dialog import ManualDiscountDialog
from modules.pos.pos_widget import POSWidget
from modules.products.product_service import ProductService
from modules.promotions.promotion_service import PromotionService
from network.session import session

TEST_DB = os.path.join(PROJECT_DIR, "tests", ".tmp", "test_descuento_manual.db")

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


def _pos(db, with_promotions=False) -> tuple[POSWidget, Product]:
    services = {"db": db, "product": ProductService(db),
                "category": CategoryService(db), "cart": CartService(db)}
    if with_promotions:
        services["promotions"] = PromotionService(db)
    product_id = ProductService(db).create(Product(
        code="DSC-1", name="Mueble descuento", sale_price=100000.0,
        tax_rate=0.0))
    product = ProductService(db).get_by_id(product_id)
    return POSWidget(services), product


def test_descuento_manual_porcentaje():
    global _last_db
    db = DatabaseManager(TEST_DB)
    db.initialize()
    _last_db = db
    pos, product = _pos(db)
    pos.add_to_cart(product)

    pos._manual_discount = {"mode": "percent", "value": 10,
                            "reason": "Cliente frecuente"}
    pos._update_totals()
    assert pos.cart[0]["discount"] == 10000.0
    assert "90,000" in pos.total_label.text()
    assert "10,000" in pos.discount_label.text()
    assert "Descuento manual" in pos.promo_label.text()
    assert "Editar descuento" in pos.manual_discount_button.text()


def test_descuento_manual_monto_y_tope():
    global _last_db
    db = DatabaseManager(TEST_DB)
    db.initialize()
    _last_db = db
    pos, product = _pos(db)
    pos.add_to_cart(product)

    pos._manual_discount = {"mode": "amount", "value": 15000.0, "reason": ""}
    pos._update_totals()
    assert "85,000" in pos.total_label.text()

    # No puede superar el total.
    pos._manual_discount = {"mode": "amount", "value": 999999.0, "reason": ""}
    pos._update_totals()
    assert "0.00" in pos.total_label.text()


def test_quitar_descuento_manual():
    global _last_db
    db = DatabaseManager(TEST_DB)
    db.initialize()
    _last_db = db
    pos, product = _pos(db)
    pos.add_to_cart(product)
    pos._manual_discount = {"mode": "percent", "value": 20, "reason": ""}
    pos._update_totals()
    assert "80,000" in pos.total_label.text()

    pos._manual_discount = None
    pos._update_totals()
    assert "100,000" in pos.total_label.text()
    assert "Descuento manual…" in pos.manual_discount_button.text()


def test_descuento_manual_con_promo_de_producto():
    global _last_db
    db = DatabaseManager(TEST_DB)
    db.initialize()
    _last_db = db
    pos, product = _pos(db, with_promotions=True)
    segunda_id = ProductService(db).create(Product(
        code="DSC-2", name="Mueble promo", sale_price=50000.0, tax_rate=0.0))
    segunda = ProductService(db).get_by_id(segunda_id)
    PromotionService(db).create(
        "Combo", "bundle",
        {"product_id": product.id, "discount_product_id": segunda.id,
         "percent": 15})

    pos.add_to_cart(product)
    pos.add_to_cart(segunda)
    # Base: 150000 - 7500 (combo) = 142500
    pos._manual_discount = {"mode": "percent", "value": 10, "reason": ""}
    pos._update_totals()
    # Manual: 10% de 142500 = 14250; total 150000 - 7500 - 14250 = 128250
    assert "128,250" in pos.total_label.text()
    assert "21,750" in pos.discount_label.text()  # 7500 + 14250


def test_dialogo_descuento_manual():
    dialog = ManualDiscountDialog()
    dialog.mode_combo.setCurrentIndex(1)  # monto
    dialog.value_input.setValue(5000.0)
    dialog.reason_input.setText("Ajuste")
    dialog._apply()
    assert dialog.resultado == {"mode": "amount", "value": 5000.0,
                                "reason": "Ajuste"}

    editar = ManualDiscountDialog(dialog.resultado)
    assert editar.value_input.value() == 5000.0
    editar._clear()
    assert editar.resultado is None
