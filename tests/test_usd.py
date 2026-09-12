"""Tests de funcionalidad USD: moneda, tipo de cambio, cobro, venta y reportes."""

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
from modules.pos.cart_service import CartService
from utils.helpers import format_currency

TEST_DB = os.path.join(PROJECT_DIR, "tests", ".tmp", "test_usd.db")


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


def get_db():
    cleanup()
    db = DatabaseManager(TEST_DB)
    db.initialize()
    return db


def test_sales_columns_exist():
    db = get_db()
    rows = db.execute_query("PRAGMA table_info(sales)")
    names = {r["name"] for r in rows}
    ok = "currency" in names and "exchange_rate" in names
    print(f"[{'OK' if ok else 'FAIL'}] columnas currency y exchange_rate existen en sales")
    db.close()
    cleanup()
    assert ok


def test_app_config_exists():
    db = get_db()
    rows = db.execute_query("SELECT name FROM sqlite_master WHERE type='table' AND name='app_config'")
    ok = len(rows) > 0
    print(f"[{'OK' if ok else 'FAIL'}] tabla app_config existe")
    db.close()
    cleanup()
    assert ok


def test_default_exchange_rate():
    db = get_db()
    rows = db.execute_query("SELECT value FROM app_config WHERE key = 'exchange_rate'")
    ok = len(rows) > 0 and float(rows[0]["value"]) == 520.0
    print(f"[{'OK' if ok else 'FAIL'}] tipo de cambio por defecto es 520.0")
    db.close()
    cleanup()
    assert ok


def test_format_currency():
    crc = format_currency(150000, "CRC")
    usd = format_currency(288.46, "USD")
    ok1 = "150,000" in crc
    ok2 = "$" in usd and "288.46" in usd
    ok = ok1 and ok2
    try:
        print(f"[{'OK' if ok else 'FAIL'}] format_currency CRC={crc}, USD={usd}")
    except UnicodeEncodeError:
        print(f"[{'OK' if ok else 'FAIL'}] format_currency CRC=OK, USD={usd}")
    assert ok


def test_create_usd_sale():
    db = get_db()
    cs = CartService(db)
    db.execute_insert(
        "INSERT INTO products (code, name, sale_price, stock_quantity) VALUES (?, ?, ?, ?)",
        ("PROD001", "Mesa de roble", 15000.0, 10)
    )
    sale = Sale(
        subtotal=15000.0, discount=0.0, tax_amount=1950.0, total=15000.0,
        payment_method="efectivo", cash_received=30.0, change_amount=0.0,
        payment_details='[{"method":"Efectivo","amount":30.0}]',
        invoice_type="general", currency="USD", exchange_rate=520.0,
        status="completada", station="CAJA1",
    )
    item = SaleItem(product_id=1, product_name="Mesa de roble", quantity=1, unit_price=15000.0, total=15000.0)
    sale_id = cs.create_sale(sale, [item])
    sale_db = cs.get_sale(sale_id)
    ok = (sale_db is not None and sale_db.currency == "USD"
          and sale_db.exchange_rate == 520.0 and sale_db.invoice_number.startswith("D-"))
    print(f"[{'OK' if ok else 'FAIL'}] venta USD: invoice={sale_db.invoice_number if sale_db else 'N/A'}, "
          f"currency={sale_db.currency if sale_db else 'N/A'}, rate={sale_db.exchange_rate if sale_db else 'N/A'}")
    db.close()
    cleanup()
    assert ok


def test_create_crc_sale():
    db = get_db()
    cs = CartService(db)
    db.execute_insert(
        "INSERT INTO products (code, name, sale_price, stock_quantity) VALUES (?, ?, ?, ?)",
        ("PROD002", "Silla de cedro", 52000.0, 10)
    )
    sale = Sale(
        subtotal=150000.0, discount=0.0, tax_amount=19500.0, total=150000.0,
        payment_method="efectivo", cash_received=150000.0, change_amount=0.0,
        payment_details='[{"method":"Efectivo","amount":150000}]',
        invoice_type="general", currency="CRC", exchange_rate=520.0,
        status="completada", station="CAJA1",
    )
    item = SaleItem(product_id=1, product_name="Silla de cedro", quantity=1, unit_price=150000.0, total=150000.0)
    sale_id = cs.create_sale(sale, [item])
    sale_db = cs.get_sale(sale_id)
    ok = (sale_db is not None and sale_db.currency == "CRC" and sale_db.invoice_number.startswith("V-"))
    print(f"[{'OK' if ok else 'FAIL'}] venta CRC: invoice={sale_db.invoice_number if sale_db else 'N/A'}")
    db.close()
    cleanup()
    assert ok


def test_reports_convert_usd():
    db = get_db()
    cs = CartService(db)
    db.execute_insert(
        "INSERT INTO products (code, name, sale_price, stock_quantity) VALUES (?, ?, ?, ?)",
        ("PROD003", "Test USD", 100.0, 10)
    )
    db.execute_insert(
        "INSERT INTO products (code, name, sale_price, stock_quantity) VALUES (?, ?, ?, ?)",
        ("PROD004", "Test CRC", 52000.0, 10)
    )
    # POS guarda los montos en CRC aunque el cobro se muestre en USD; los
    # reportes no deben reconvertir (evita inflar la venta x520).
    sale = Sale(subtotal=52000.0, total=52000.0, currency="USD", exchange_rate=520.0, status="completada", station="CAJA1")
    item = SaleItem(product_id=1, product_name="Test USD", quantity=1, unit_price=52000.0, total=52000.0)
    cs.create_sale(sale, [item])
    sale2 = Sale(subtotal=52000.0, total=52000.0, currency="CRC", exchange_rate=520.0, status="completada", station="CAJA1")
    item2 = SaleItem(product_id=2, product_name="Test CRC", quantity=1, unit_price=52000.0, total=52000.0)
    cs.create_sale(sale2, [item2])
    from modules.reports.reports_service import ReportsService
    rs = ReportsService(db)
    summary = rs.summary()
    ok = abs(summary["ingresos"] - 104000.0) < 0.01
    print(f"[{'OK' if ok else 'FAIL'}] reports: ingresos={summary['ingresos']} (esperado 104000.0)")
    db.close()
    cleanup()
    assert ok


def test_exchange_rate_save_load():
    db = get_db()
    from network.exchange_rate import save_exchange_rate, get_exchange_rate_from_db
    save_exchange_rate(db, 535.75)
    rate, date_str = get_exchange_rate_from_db(db)
    ok = abs(rate - 535.75) < 0.01 and len(date_str) > 0
    print(f"[{'OK' if ok else 'FAIL'}] exchange_rate save/load: rate={rate}, date={date_str}")
    db.close()
    cleanup()
    assert ok


def test_toggle_currency_resta_montos():
    from PyQt6.QtWidgets import QApplication as _App
    if _App.instance() is None:
        _app = _App([])  # mantener referencia evitando GC del QApplication
    from modules.pos.cobro_dialog import CobroDialog
    dlg = CobroDialog(169500.0, exchange_rate=520.0)
    dlg.cash_input.setText("100000")  # 100000 CRC en efectivo
    dlg.usd_btn.click()
    campo = dlg._parse_amount(dlg.cash_input.text())
    ok1 = abs(campo - 192.31) < 0.01  # 100000 / 520
    pendiente = dlg._parse_amount(dlg.total_display.text())
    ok2 = abs(pendiente - 133.65) < 0.01  # 325.96 - 192.31
    ctx = dlg.context_label.text()
    ok3 = "325.96" in ctx and "192.31" in ctx
    ok = ok1 and ok2 and ok3
    print(f"[{'OK' if ok else 'FAIL'}] toggle CRC->USD: campo={campo}, pendiente={pendiente}, ctx={ctx!r}")
    assert ok


def test_toggle_currency_en_mixto_convierte_ambos():
    from PyQt6.QtWidgets import QApplication as _App
    if _App.instance() is None:
        _app = _App([])
    from modules.pos.cobro_dialog import CobroDialog
    dlg = CobroDialog(169500.0, exchange_rate=520.0)
    dlg.method_buttons["Mixto"].click()
    dlg.mix_amount_a.setText("100000")
    dlg.mix_amount_b.setText("69500")
    dlg.usd_btn.click()
    a = dlg._parse_amount(dlg.mix_amount_a.text())
    b = dlg._parse_amount(dlg.mix_amount_b.text())
    ok = abs(a - 192.31) < 0.01 and abs(b - 133.65) < 0.01 and dlg.cobrar_btn.isEnabled()
    print(f"[{'OK' if ok else 'FAIL'}] toggle CRC->USD en Mixto: a={a}, b={b}, cobrar={dlg.cobrar_btn.isEnabled()}")
    assert ok


def test_pdf_convierte_pago_usd_a_crc():
    from modules.documentos.pdf_factura import factura_html
    db = get_db()
    cs = CartService(db)
    db.execute_insert(
        "INSERT INTO products (code, name, sale_price) VALUES (?, ?, ?)",
        ("PROD005", "USD PDF", 52000.0),
    )
    sale = Sale(subtotal=52000.0, total=52000.0, currency="USD", exchange_rate=520.0,
                payment_method="efectivo", cash_received=100.0, change_amount=0.0,
                payment_details="[]", status="completada", station="CAJA1")
    item = SaleItem(product_id=1, product_name="USD PDF", quantity=1,
                    unit_price=52000.0, total=52000.0)
    sale_id = cs.create_sale(sale, [item])
    saved = cs.get_sale(sale_id)
    html = factura_html(saved, {"company_name": "POS", "address": "", "phone": "",
                                "company_id": "", "activity_code": ""})
    ok = "₡52,000.00" in html and "₡100.00" not in html
    print(f"[{'OK' if ok else 'FAIL'}] PDF convierte pago USD a CRC")
    db.close()
    cleanup()
    assert ok


if __name__ == "__main__":
    tests = [
        test_sales_columns_exist,
        test_app_config_exists,
        test_default_exchange_rate,
        test_format_currency,
        test_create_usd_sale,
        test_create_crc_sale,
        test_reports_convert_usd,
        test_exchange_rate_save_load,
        test_toggle_currency_resta_montos,
        test_toggle_currency_en_mixto_convierte_ambos,
        test_pdf_convierte_pago_usd_a_crc,
    ]
    failed = 0
    for t in tests:
        try:
            t()
        except Exception as e:
            print(f"[FAIL] {t.__name__}: {e}")
            failed += 1
    print(f"\n{'USD OK' if failed == 0 else f'USD FAIL: {failed}'}")
