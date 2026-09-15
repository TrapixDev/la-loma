"""Descuento por método de pago: reparto por línea y diálogo de cobro (Fase 5)."""

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
from database.models import Product, Sale, SaleItem
from modules.categories.category_service import CategoryService
from modules.clients.client_service import ClientService
from modules.credit.credit_service import CreditService
from modules.pos.cart_service import CartService
from modules.pos.cobro_dialog import CobroDialog
from modules.pos.pos_widget import POSWidget
from modules.products.product_service import ProductService
from modules.promotions.promotion_service import (
    PromotionService,
    distribuir_descuento_pago,
)
from network.session import session
from utils.helpers import calculate_totals

TEST_DB = os.path.join(PROJECT_DIR, "tests", ".tmp", "test_pago_promos.db")

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


def _product(db, code, name, price, tax_rate=0.0) -> Product:
    service = ProductService(db)
    product_id = service.create(Product(
        code=code, name=name, sale_price=price, tax_rate=tax_rate))
    return service.get_by_id(product_id)


def _cart(items):
    return [
        {"product_id": pid, "product_name": f"P{pid}", "quantity": qty,
         "unit_price": price, "tax_rate": tax, "discount": 0.0,
         "cabys_code": "", "total": qty * price}
        for pid, qty, price, tax in items
    ]


def test_distribuir_proporcional_y_exacto():
    cart = _cart([(1, 1, 60000, 0), (2, 1, 40000, 0)])
    copia = distribuir_descuento_pago(cart, 10000.0)
    assert copia[0]["discount"] == 6000.0
    assert copia[1]["discount"] == 4000.0
    assert round(sum(i["discount"] for i in copia), 2) == 10000.0
    # El carrito original no se modifica.
    assert cart[0]["discount"] == 0.0


def test_distribuir_residuo_de_redondeo():
    cart = _cart([(1, 1, 33333, 0), (2, 1, 33333, 0), (3, 1, 33334, 0)])
    copia = distribuir_descuento_pago(cart, 100.0)
    assert round(sum(i["discount"] for i in copia), 2) == 100.0


def test_distribuir_vacio_o_cero():
    assert distribuir_descuento_pago([], 5000) == []
    cart = _cart([(1, 1, 10000, 0)])
    assert distribuir_descuento_pago(cart, 0) [0]["discount"] == 0.0


def test_descuento_pago_baja_iva():
    cart = _cart([(1, 1, 100000, 13.0)])
    copia = distribuir_descuento_pago(cart, 5000.0)
    totales = calculate_totals(copia)
    assert totales["discount"] == 5000.0
    assert totales["tax_amount"] == 12350.0  # 13% de 95.000
    assert totales["total"] == 107350.0


def test_cobro_dialog_aplica_descuento_por_metodo():
    descuentos = {"Efectivo": {"total": 95000.0, "discount": 5000.0}}
    dlg = CobroDialog(100000.0, exchange_rate=520.0, descuentos=descuentos)
    assert dlg.method == "Efectivo"
    assert dlg.total == 95000.0
    assert dlg.discount == 5000.0
    assert "5,000" in dlg.discount_display.text()

    dlg._select_method("Tarjeta")
    assert dlg.total == 100000.0
    assert dlg.discount == 0.0
    assert dlg.discount_display.text() == ""

    dlg._select_method("Efectivo")
    assert dlg.total == 95000.0
    assert dlg.discount == 5000.0

    dlg._select_method("Mixto")
    assert dlg.total == 100000.0
    assert dlg.discount == 0.0

    dlg._select_method("Efectivo")
    assert dlg.result()["discount"] == 5000.0


def test_pos_mapa_de_descuentos_por_metodo():
    db = _db()
    mesa = _product(db, "PP-1", "Mesa pago", 100000)
    PromotionService(db).create(
        "5% efectivo", "payment", {"methods": ["efectivo"], "percent": 5})

    pos = POSWidget(_services(db))
    pos.add_to_cart(mesa)
    mapa = pos._descuentos_por_metodo()
    assert "Efectivo" in mapa
    assert "Tarjeta" not in mapa
    assert mapa["Efectivo"]["discount"] == 5000.0
    assert mapa["Efectivo"]["total"] == 95000.0


def test_preview_y_persistencia_cuadran():
    db = _db()
    mesa = _product(db, "PP-2", "Mesa pago", 100000, tax_rate=13.0)
    PromotionService(db).create(
        "5% efectivo", "payment", {"methods": ["efectivo"], "percent": 5})

    pos = POSWidget(_services(db))
    pos.invoice_type_combo.setCurrentIndex(0)  # factura electrónica (con IVA)
    pos.add_to_cart(mesa)
    mapa = pos._descuentos_por_metodo()
    total_preview = mapa["Efectivo"]["total"]

    copia = distribuir_descuento_pago(pos.cart, mapa["Efectivo"]["discount"])
    total_real = calculate_totals(copia)["total"]
    assert total_preview == total_real == 107350.0

    # La venta persiste el descuento total y el detalle de promociones.
    info = PromotionService(db).evaluate(copia, payment_method="Efectivo")
    tipos = [a["type"] for a in info["applied"]]
    assert "payment" in tipos
    db.execute_insert(
        "INSERT INTO clients (id_type, id_number, name) VALUES (?, ?, ?)",
        ("01", "555555555", "Cliente Pago"))
    totales = calculate_totals(copia)
    sale = Sale(client_id=1, subtotal=totales["subtotal"],
                discount=totales["discount"], tax_amount=totales["tax_amount"],
                total=totales["total"], payment_method="Efectivo",
                promotions_applied=json.dumps(info["applied"]),
                sale_reference="ref-pago-promo")
    item = SaleItem(product_id=mesa.id, product_name=mesa.name, quantity=1,
                    unit_price=100000.0, discount=copia[0]["discount"],
                    total=100000.0)
    sale_id = CartService(db).create_sale(sale, [item])
    saved = CartService(db).get_sale(sale_id)
    assert saved.discount == 5000.0
    assert saved.total == 107350.0
    assert "payment" in saved.promotions_applied
