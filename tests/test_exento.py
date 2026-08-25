"""Pruebas: Factura Simplificada exenta de IVA (Régimen de Tributación Simplificada)."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt6.QtWidgets import QApplication

app = QApplication([])

from database.models import Sale, SaleItem
from utils.helpers import calculate_totals
from modules.documentos.pdf_factura import factura_html
from modules.documentos.ticket import ticket_html

COMPANY = {"company_name": "Muebleria La Loma", "address": "San Jose",
           "phone": "2222-0000", "company_id": "3-101-123456",
           "activity_code": "31021"}

CART = [
    {"product_id": 1, "product_name": "Mesa", "quantity": 2,
     "unit_price": 50000.0, "tax_rate": 13.0, "discount": 0.0},
]


def test_calculate_totals_normal():
    t = calculate_totals(CART)
    ok = (t["subtotal"] == 100000.0 and t["tax_amount"] == 13000.0
          and t["total"] == 113000.0)
    print(f"[{'OK' if ok else 'FAIL'}] totals normal: {t}")
    assert ok


def test_calculate_totals_exento():
    t = calculate_totals(CART, exento=True)
    ok = (t["subtotal"] == 100000.0 and t["tax_amount"] == 0.0
          and t["total"] == 100000.0)
    print(f"[{'OK' if ok else 'FAIL'}] totals exento: {t}")
    assert ok


def test_calculate_totals_exento_descuento():
    cart = [dict(CART[0], discount=10000.0)]
    t = calculate_totals(cart, exento=True)
    ok = t["discount"] == 10000.0 and t["tax_amount"] == 0.0 and t["total"] == 90000.0
    print(f"[{'OK' if ok else 'FAIL'}] exento con descuento: {t}")
    assert ok


def make_sale(invoice_type="simplificada", subtotal=100000.0, total=100000.0,
              tax=0.0, discount=0.0):
    return Sale(
        id=1, invoice_number="S-00001", client_id=None, client_name="",
        subtotal=subtotal, discount=discount, tax_amount=tax, total=total,
        payment_method="Efectivo", cash_received=total, change_amount=0.0,
        payment_details='[{"method":"Efectivo","amount":100000.0}]',
        invoice_type=invoice_type, currency="CRC", exchange_rate=0.0,
        status="completada", hacienda_key="", hacienda_status="",
        electronic_invoice=False, station="CAJA1", user_name="Cajero",
        created_at="2026-08-09 10:00:00",
        items=[SaleItem(product_id=1, product_name="Mesa", quantity=2,
                        unit_price=50000.0, total=100000.0)],
    )


def test_pdf_simplificada_exenta():
    html = factura_html(make_sale(), COMPANY)
    ok = ("Exento de IVA" in html
          and "Impuesto" not in html
          and "FACTURA SIMPLIFICADA" in html)
    print(f"[{'OK' if ok else 'FAIL'}] PDF simplificada muestra 'Exento de IVA'")
    assert ok


def test_pdf_simplificada_total_sin_iva():
    html = factura_html(make_sale(), COMPANY)
    # subtotal y total deben ser 100000 (sin IVA 13% de 113000)
    ok = "100,000.00" in html and "113,000.00" not in html
    print(f"[{'OK' if ok else 'FAIL'}] PDF simplificada: total exento sin IVA")
    assert ok


def test_pdf_general_mantiene_iva():
    html = factura_html(make_sale(invoice_type="general", subtotal=100000.0,
                                  total=113000.0, tax=13000.0), COMPANY)
    ok = "Impuesto" in html and "Exento de IVA" not in html and "113,000.00" in html
    print(f"[{'OK' if ok else 'FAIL'}] PDF general mantiene IVA")
    assert ok


def test_ticket_simplificada_exenta():
    html = ticket_html(make_sale(), COMPANY)
    ok = ("Exento de IVA" in html
          and "Impuesto" not in html
          and "FACTURA SIMPLIFICADA" in html)
    print(f"[{'OK' if ok else 'FAIL'}] ticket simplificada muestra 'Exento de IVA'")
    assert ok


def test_ticket_general_mantiene_iva():
    html = ticket_html(make_sale(invoice_type="general", subtotal=100000.0,
                                 total=113000.0, tax=13000.0), COMPANY)
    ok = "Impuesto" in html and "Exento de IVA" not in html
    print(f"[{'OK' if ok else 'FAIL'}] ticket general mantiene IVA")
    assert ok


if __name__ == "__main__":
    tests = [
        test_calculate_totals_normal,
        test_calculate_totals_exento,
        test_calculate_totals_exento_descuento,
        test_pdf_simplificada_exenta,
        test_pdf_simplificada_total_sin_iva,
        test_pdf_general_mantiene_iva,
        test_ticket_simplificada_exenta,
        test_ticket_general_mantiene_iva,
    ]
    failed = 0
    for t in tests:
        try:
            t()
        except Exception as e:
            print(f"[FAIL] {t.__name__}: {e}")
            failed += 1
    print(f"\n{'EXENTO OK' if failed == 0 else f'EXENTO FAIL: {failed}'}")
