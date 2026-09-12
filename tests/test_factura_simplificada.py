"""Pruebas: Factura Simplificada (Régimen de Tributación Simplificada)."""

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
from modules.documentos.pdf_factura import factura_html


def test_factura_simplificada():
    TMP = tempfile.mkdtemp(prefix="pos_simplif_")
    DB = os.path.join(TMP, "pos.db")

    db = DatabaseManager(DB)
    db.initialize()

    # 1. Migración agrega invoice_type
    cols = {row["name"] for row in db.execute_query("PRAGMA table_info(sales)")}
    assert "invoice_type" in cols, cols
    print("[OK] columna invoice_type existe en sales")

    sv = CartService(db)

    # Crear producto de prueba
    db.execute_insert(
        "INSERT INTO products (name, sale_price, stock_quantity, tax_rate) VALUES (?, ?, ?, ?)",
        ("Mueble simplificado", 50000, 5, 13.0),
    )
    pid = db.execute_query("SELECT id FROM products LIMIT 1")[0]["id"]

    # 2. Guardar venta simplificada
    sale = Sale(
        id=0, invoice_number="S-00001", client_id=None, client_name="",
        subtotal=50000, discount=0, tax_amount=0, total=50000,
        payment_method="Efectivo", cash_received=50000, change_amount=0,
        payment_details=json.dumps([{"method": "Efectivo", "amount": 50000.0}]),
        invoice_type="simplificada",
        status="completada", hacienda_key="", hacienda_status="",
        electronic_invoice=False, station="CAJA-T",
        user_id=None, user_name="Cajero", created_at=None,
    )
    sale_id = sv.create_sale(sale, [
        SaleItem(product_id=pid, product_name="Mueble simplificado", quantity=1,
                 unit_price=50000, total=50000),
    ])
    saved = sv.get_sale(sale_id)
    assert saved.invoice_type == "simplificada", saved.invoice_type
    assert not saved.electronic_invoice
    assert saved.payment_method == "Efectivo"
    print("[OK] create_sale/get_sale con invoice_type=simplificada")

    # 3. PDF: título "FACTURA SIMPLIFICADA", sin cliente, sin IVA
    company = {"company_name": "POS La Loma", "address": "San José", "phone": "2222-3333",
               "company_id": "3-123-456789", "activity_code": "Actividad 12345"}
    html = factura_html(saved, company)
    assert "FACTURA SIMPLIFICADA" in html, html[:200]
    assert "Cliente:" not in html, "simplificada no debe mostrar cliente"
    assert "Impuesto" not in html, "simplificada no debe mostrar IVA"
    assert "Mueble simplificado" in html
    assert "₡50,000.00" in html
    assert "Régimen de Tributación Simplificada" in html
    print("[OK] factura_html simplificada: título, sin cliente, sin IVA")

    # 4. PDF normal (general) sí muestra cliente e IVA
    sale2 = Sale(
        id=0, invoice_number="V-00001", client_id=None, client_name="Juan Pérez",
        subtotal=100000, discount=0, tax_amount=13000, total=113000,
        payment_method="Efectivo", cash_received=113000, change_amount=0,
        payment_details="[]",
        invoice_type="general",
        status="completada", hacienda_key="", hacienda_status="PENDIENTE",
        electronic_invoice=False, station="CAJA-T",
        user_id=None, user_name="Cajero", created_at=None,
    )
    sale2_id = sv.create_sale(sale2, [
        SaleItem(product_id=pid, product_name="Mueble simplificado", quantity=2,
                 unit_price=50000, total=100000),
    ])
    saved2 = sv.get_sale(sale2_id)
    html2 = factura_html(saved2, company)
    assert "FACTURA" in html2 and "SIMPLIFICADA" not in html2
    assert "Cliente:" in html2
    assert "Impuesto" in html2
    print("[OK] factura_html general: sin 'Simplificada', con cliente, con IVA")

    db.close()
    print("FACTURA SIMPLIFICADA OK")
