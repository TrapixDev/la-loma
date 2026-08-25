"""Tests del ticket térmico 80mm: HTML, desglose, moneda e impresión segura."""

import os
import sys
from pathlib import Path
import time

PROJECT_DIR = str(Path(__file__).resolve().parents[1])
sys.path.insert(0, PROJECT_DIR)
os.chdir(PROJECT_DIR)
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from database.db_manager import DatabaseManager
from database.models import Sale, SaleItem
from modules.documentos.ticket import (
    ticket_html,
    imprimir_ticket,
    imprimir_prueba,
    get_printer_name,
    save_printer_name,
    _desglose_pago,
)

TEST_DB = os.path.join(PROJECT_DIR, "tests", ".tmp", "test_ticket.db")

COMPANY = {
    "company_name": "Muebleria La Loma",
    "address": "San Jose, Costa Rica",
    "phone": "2222-0000",
    "company_id": "3-101-123456",
    "activity_code": "31021",
}


def cleanup():
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
            time.sleep(0.1)


def make_sale(currency="CRC", rate=520.0, method="efectivo",
              details='[{"method":"Efectivo","amount":150000}]',
              invoice_type="general", clave=""):
    return Sale(
        id=1,
        invoice_number="V-00001",
        subtotal=150000.0,
        discount=0.0,
        tax_amount=19500.0,
        total=169500.0,
        payment_method=method,
        cash_received=170000.0,
        change_amount=500.0,
        payment_details=details,
        invoice_type=invoice_type,
        currency=currency,
        exchange_rate=rate,
        status="completada",
        hacienda_key=clave,
        hacienda_status="ACEPTADA",
        station="CAJA1",
        user_name="Juan",
        created_at="2026-08-09 10:30:00",
        items=[SaleItem(product_id=1, product_name="Mesa de roble",
                        quantity=2, unit_price=75000.0, total=150000.0)],
    )


def test_ticket_contiene_datos():
    sale = make_sale()
    html = ticket_html(sale, COMPANY)
    ok = ("Muebleria La Loma" in html
          and "V-00001" in html
          and "Mesa de roble" in html
          and "150,000" in html
          and "GRACIAS POR SU COMPRA" in html)
    print(f"[{'OK' if ok else 'FAIL'}] ticket contiene empresa, factura, items y pie")
    assert ok


def test_ticket_total_usd():
    sale = make_sale(currency="USD", rate=453.0)
    html = ticket_html(sale, COMPANY)
    # total CRC 169500 / 453 = 374.17 USD
    ok = "$374.17" in html
    print(f"[{'OK' if ok else 'FAIL'}] ticket en USD convierte total (169500/453=374.17)")
    assert ok


def test_ticket_usd_equivalente_crc():
    from config import Config
    original = Config.MOSTRAR_EQUIVALENTE_CRC
    try:
        Config.MOSTRAR_EQUIVALENTE_CRC = True
        sale = make_sale(currency="USD", rate=520.0)
        html = ticket_html(sale, COMPANY)
        ok = "Equiv. CRC" in html and "₡169,500.00" in html
        print(f"[{'OK' if ok else 'FAIL'}] ticket USD muestra equivalente en colones")
        assert ok
    finally:
        Config.MOSTRAR_EQUIVALENTE_CRC = original


def test_ticket_simplificada_sin_cliente():
    sale = make_sale(invoice_type="simplificada")
    html = ticket_html(sale, COMPANY)
    ok = "FACTURA SIMPLIFICADA" in html and "Cliente:" not in html
    print(f"[{'OK' if ok else 'FAIL'}] ticket simplificada: titulo, sin cliente")
    assert ok


def test_ticket_clave_hacienda():
    sale = make_sale(clave="123456789012345678901234567890123456789012345678901")
    html = ticket_html(sale, COMPANY)
    ok = "Clave:" in html and "1234567890123" in html
    print(f"[{'OK' if ok else 'FAIL'}] ticket incluye clave de Hacienda")
    assert ok


def test_desglose_mixto():
    sale = make_sale(method="mixto",
                     details='[{"method":"Efectivo","amount":150000},'
                             '{"method":"Tarjeta","amount":19500}]')
    sale.cash_received = 150000.0
    sale.change_amount = 0.0
    lines = _desglose_pago(sale, "CRC")
    ok = any("Efectivo" in ln and "150,000" in ln for ln in lines) and \
         any("Tarjeta" in ln and "19,500" in ln for ln in lines)
    try:
        print(f"[{'OK' if ok else 'FAIL'}] desglose mixto: {lines}")
    except UnicodeEncodeError:
        print(f"[{'OK' if ok else 'FAIL'}] desglose mixto: {len(lines)} lineas")
    assert ok


def test_imprimir_sin_impresora():
    # Sin impresora configurada y sin default -> False, sin excepcion
    ok = isinstance(imprimir_ticket("<html><body>x</body></html>", ""), bool)
    print(f"[{'OK' if ok else 'FAIL'}] imprimir_ticket no lanza excepcion (bool={ok})")
    assert ok


def test_prueba_no_lanza():
    ok = isinstance(imprimir_prueba(""), bool)
    print(f"[{'OK' if ok else 'FAIL'}] imprimir_prueba no lanza excepcion (bool={ok})")
    assert ok


def test_printer_config_save_load():
    cleanup()
    db = DatabaseManager(TEST_DB)
    db.initialize()
    save_printer_name(db, "EPSON TM-T20")
    name = get_printer_name(db)
    ok = name == "EPSON TM-T20"
    print(f"[{'OK' if ok else 'FAIL'}] printer_name guardado/leido: {name}")
    db.close()
    cleanup()
    assert ok


if __name__ == "__main__":
    tests = [
        test_ticket_contiene_datos,
        test_ticket_total_usd,
        test_ticket_usd_equivalente_crc,
        test_ticket_simplificada_sin_cliente,
        test_ticket_clave_hacienda,
        test_desglose_mixto,
        test_imprimir_sin_impresora,
        test_prueba_no_lanza,
        test_printer_config_save_load,
    ]
    failed = 0
    for t in tests:
        try:
            t()
        except Exception as e:
            print(f"[FAIL] {t.__name__}: {e}")
            failed += 1
    print(f"\n{'TICKET OK' if failed == 0 else f'TICKET FAIL: {failed}'}")
