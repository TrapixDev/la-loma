"""Pruebas: cobro con monto por método, Mixto (efectivo + método) y guardado."""

import json
import os
import sys
from pathlib import Path
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])

from database.db_manager import DatabaseManager
from database.models import Product, Sale, SaleItem
from modules.pos.cart_service import CartService
from modules.pos.cobro_dialog import CobroDialog


def test_pago_mixto():
    TMP = tempfile.mkdtemp(prefix="pos_pago_")
    DB = os.path.join(TMP, "pos.db")

    db = DatabaseManager(DB)
    db.initialize()

    # 1. La migración agrega payment_details a una BD recién creada
    cols = {row["name"] for row in db.execute_query("PRAGMA table_info(sales)")}
    assert "payment_details" in cols, cols
    print("[OK] columna payment_details existe en sales")

    sv = CartService(db)

    # Crear producto de prueba para evitar FK
    db.execute_insert(
        "INSERT INTO products (name, sale_price, stock_quantity, tax_rate) VALUES (?, ?, ?, ?)",
        ("Mesa de prueba", 210000, 10, 13.0),
    )

    # 2. Tarjeta con monto: faltan / cobra / vuelto, y payment_details
    dlg = CobroDialog(210000)
    dlg._select_method("Tarjeta")
    assert dlg.pages.currentIndex() == 0
    assert dlg.amount_label.text().startswith("Monto de Tarjeta")
    dlg.cash_input.setText("150000")
    assert not dlg.cobrar_btn.isEnabled(), "faltante debe deshabilitar COBRAR"
    assert "Faltan" in dlg.error_label.text() and "60,000" in dlg.error_label.text()
    print("[OK] Tarjeta con monto inferior muestra 'Faltan X'")

    dlg.cash_input.setText("210000")
    assert dlg.cobrar_btn.isEnabled()
    dlg._on_cobrar()
    res = dlg.result()
    assert res["method"] == "Tarjeta"
    assert res["payment_details"] == [{"method": "Tarjeta", "amount": 210000.0}]
    assert res["change"] == 0.0
    print("[OK] Tarjeta con monto exacto cobra y guarda payment_details")

    # --- Sinpe con vuelto (paga de mas) ---
    d2 = CobroDialog(210000)
    d2.method_buttons["Sinpe"].click()
    d2.cash_input.setText("250000")
    assert d2.cobrar_btn.isEnabled()
    assert "40,000" in d2.change_display.text(), d2.change_display.text()
    d2._on_cobrar()
    res2 = d2.result()
    assert res2["change"] == 40000.0
    assert res2["payment_details"] == [{"method": "Sinpe", "amount": 250000.0}]
    print("[OK] SinPE con monto mayor calcula vuelto")

    # --- Mixto: Efectivo 150000 + Sinpe 60000 ---
    d3 = CobroDialog(210000)
    d3.method_buttons["Mixto"].click()
    assert d3.pages.currentIndex() == 1
    d3.mix_amount_a.setText("150000")
    d3.mix_method_b.setCurrentText("Sinpe")
    d3.mix_amount_b.setText("30000")
    assert not d3.cobrar_btn.isEnabled(), "suma < total no cobra"
    assert "30,000" in d3.mix_status_label.text(), d3.mix_status_label.text()

    # Enter en campo efectivo no cierra ventana cuando falta plata
    d3.mix_amount_a.returnPressed.emit()
    assert d3.isVisible() or not d3.cobrar_btn.isEnabled(), "Enter no debe cerrar si falta"

    d3._fill_missing()
    assert d3._parse_amount(d3.mix_amount_b.text()) == 60000.0, "completar falta"
    assert d3.cobrar_btn.isEnabled()

    # Enter en campo B con todo cubierto cierra (cobra)
    d3.mix_amount_b.returnPressed.emit()
    res3 = d3.result()
    assert res3["method"] == "Mixto"
    assert res3["cash_received"] == 150000.0, "efectivo del mixto"
    total_in = sum(d["amount"] for d in res3["payment_details"])
    assert total_in == 210000.0, res3["payment_details"]
    assert res3["change"] == 0.0
    assert res3["payment_details"] == [
        {"method": "Efectivo", "amount": 150000.0},
        {"method": "Sinpe", "amount": 60000.0},
    ], res3["payment_details"]
    print("[OK] Mixto Efectivo 150000 + Sinpe 60000 -> total y cobra")

    # --- Mixto: Efectivo 210000 solo (sin método B, vuelto 0) ---
    d3b = CobroDialog(210000)
    d3b.method_buttons["Mixto"].click()
    d3b.mix_amount_a.setText("210000")
    assert d3b.cobrar_btn.isEnabled()
    d3b._on_cobrar()
    res3b = d3b.result()
    assert res3b["cash_received"] == 210000.0
    assert res3b["change"] == 0.0
    assert res3b["payment_details"][0]["method"] == "Efectivo"
    assert res3b["payment_details"][0]["amount"] == 210000.0
    print("[OK] Mixto Efectivo 210000 solo -> cobra sin método B")

    # --- Mixto insuficiente no permite cobrar ---
    d4 = CobroDialog(210000)
    d4.method_buttons["Mixto"].click()
    d4.mix_amount_a.setText("150000")
    assert not d4.cobrar_btn.isEnabled(), "efectivo solo < total no cobra"
    assert "60,000" in d4.mix_status_label.text(), d4.mix_status_label.text()
    print("[OK] Mixto insuficiente muestra falta y bloquea COBRAR")

    # --- Guardar venta con payment_details y recuperarlo ---
    pid = db.execute_query("SELECT id FROM products LIMIT 1")[0]["id"]
    sale = Sale(
        id=0, invoice_number="", client_id=None, client_name="Consumidor Final",
        subtotal=190000, discount=0, tax_amount=20000, total=210000,
        payment_method="Mixto", cash_received=150000, change_amount=0,
        payment_details=json.dumps([
            {"method": "Efectivo", "amount": 150000.0},
            {"method": "Sinpe", "amount": 60000.0},
        ], ensure_ascii=False),
        status="completada", hacienda_key="", hacienda_status="",
        electronic_invoice=False, station="CAJA-T",
        user_id=None, user_name="", created_at=None,
    )
    sale_id = sv.create_sale(sale, [
        SaleItem(product_id=pid, product_name="Mesa de prueba", quantity=1,
                 unit_price=210000, total=210000),
    ])
    saved = sv.get_sale(sale_id)
    assert saved.payment_method == "Mixto"
    assert saved.payment_details and "Sinpe" in saved.payment_details
    assert json.loads(saved.payment_details)[0]["method"] == "Efectivo"
    assert json.loads(saved.payment_details)[0]["amount"] == 150000.0
    assert json.loads(saved.payment_details)[1]["method"] == "Sinpe"
    assert json.loads(saved.payment_details)[1]["amount"] == 60000.0
    assert saved.cash_received == 150000.0
    print("[OK] create_sale/get_sale conservan payment_details y cash_received")

    db.close()
    print("PAGO MIXTO OK")
