"""Tests del ticket térmico 80mm: HTML, desglose, moneda e impresión segura."""

import os
import sys
import tempfile
from pathlib import Path
import time

PROJECT_DIR = str(Path(__file__).resolve().parents[1])
sys.path.insert(0, PROJECT_DIR)
os.chdir(PROJECT_DIR)
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])

from config import Config
from database.db_manager import DatabaseManager
from database.models import Sale, SaleItem
from modules.documentos.ticket import (
    TICKET_FORMAT_DEFAULTS,
    ticket_html,
    imprimir_ticket,
    imprimir_ticket_venta,
    imprimir_prueba,
    get_printer_name,
    save_printer_name,
    get_ticket_format,
    save_ticket_format,
    save_show_dialog,
    _desglose_pago,
)

# Las pruebas de impresión escriben en una carpeta temporal (nunca en
# Documentos ni en la impresora real).
_CARPETA_PRUEBAS = tempfile.mkdtemp(prefix="pos_ticket_test_")
Config.PRINT_TEST_DIR = _CARPETA_PRUEBAS

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
          and "Actividad económica: 31021" in html
          and "150,000" in html
          and "GRACIAS POR SU PREFERENCIA" in html
          and "CANT" in html and "DETALLE" in html and "TOTAL" in html
          and "SON:" in html)
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
        ok = "Equivalente CRC" in html and "₡169,500.00" in html
        print(f"[{'OK' if ok else 'FAIL'}] ticket USD muestra equivalente en colones")
        assert ok
    finally:
        Config.MOSTRAR_EQUIVALENTE_CRC = original


def test_ticket_simplificada_sin_cliente():
    sale = make_sale(invoice_type="simplificada")
    html = ticket_html(sale, COMPANY)
    ok = ("TIQUETE ELECTRÓNICO" in html and "Cliente General" in html
          and "CLAVE:" not in html)
    print(f"[{'OK' if ok else 'FAIL'}] ticket simplificada: titulo, sin cliente")
    assert ok


def test_ticket_clave_hacienda():
    sale = make_sale(clave="123456789012345678901234567890123456789012345678901")
    html = ticket_html(sale, COMPANY)
    ok = "CLAVE:" in html and "1234567890123" in html
    print(f"[{'OK' if ok else 'FAIL'}] ticket incluye clave de Hacienda")
    assert ok


def test_ticket_detalle_legible_en_lineas_separadas():
    html = ticket_html(make_sale(), COMPANY)

    assert '<div class="item-name">Mesa de roble</div>' in html
    assert '<table class="item-meta"' in html
    assert 'width="64%"' in html and 'width="36%"' in html
    assert "2 × ₡75,000.00" in html
    assert "₡150,000.00" in html
    assert '<table class="lineas">' not in html


def test_ticket_formato_personaliza_bloques_y_textos():
    formato = {
        **TICKET_FORMAT_DEFAULTS,
        "show_company_name": False,
        "show_email": False,
        "show_customer": False,
        "show_hacienda_key": False,
        "show_transfer_details": False,
        "show_payments": False,
        "show_amount_words": False,
        "show_status": False,
        "show_thank_you": False,
        "footer_text": "Gracias <de parte de La Loma> & vuelva pronto",
    }
    empresa = dict(COMPANY, email="factura@laloma.cr",
                   iban="CR880151148200100403501", sinpe="8888-8888")
    html = ticket_html(make_sale(clave="CLAVE-DE-PRUEBA"), empresa,
                       formato=formato)

    assert "Muebleria La Loma" not in html
    assert "factura@laloma.cr" not in html
    assert "CLIENTE:" not in html
    assert "CLAVE:" not in html
    assert "IBAN:" not in html and "SINPE MÓVIL:" not in html
    assert "PAGA CON EFECTIVO" not in html
    assert "SON:" not in html
    assert "GRACIAS POR SU PREFERENCIA" not in html
    assert "Comprobante electrónico:" not in html
    assert "Gracias &lt;de parte de La Loma&gt; &amp; vuelva pronto" in html


def test_ticket_formato_guardado_y_valores_invalidos_normalizados():
    cleanup()
    db = DatabaseManager(TEST_DB)
    db.initialize()
    try:
        assert get_ticket_format(db) == TICKET_FORMAT_DEFAULTS
        save_ticket_format(db, {
            "show_email": False,
            "logo_width_px": 9999,
            "thank_you_text": "  Gracias por comprar  ",
            "campo_desconocido": "ignorar",
        })
        formato = get_ticket_format(db)
        assert formato["show_email"] is False
        assert formato["logo_width_px"] == 240
        assert formato["thank_you_text"] == "Gracias por comprar"
        assert "campo_desconocido" not in formato

        db.execute_update(
            "INSERT OR REPLACE INTO app_config (key, value) VALUES (?, ?)",
            ("ticket_format", "{json roto"),
        )
        assert get_ticket_format(db) == TICKET_FORMAT_DEFAULTS
    finally:
        db.close()
        cleanup()


def test_venta_imprime_con_el_formato_guardado(monkeypatch):
    cleanup()
    db = DatabaseManager(TEST_DB)
    db.initialize()
    captured = {}

    def fake_print(html, *args, **kwargs):
        captured["html"] = html
        return True

    try:
        save_ticket_format(db, {
            **TICKET_FORMAT_DEFAULTS,
            "show_email": False,
            "thank_you_text": "FORMATO GUARDADO",
        })
        monkeypatch.setattr("modules.documentos.ticket.imprimir_ticket", fake_print)
        assert imprimir_ticket_venta(
            make_sale(), dict(COMPANY, email="factura@laloma.cr"), db)
        assert "factura@laloma.cr" not in captured["html"]
        assert "FORMATO GUARDADO" in captured["html"]
    finally:
        db.close()
        cleanup()


def test_impresora_virtual_omite_el_dialogo_de_windows(monkeypatch):
    """Con POS-Test no debe abrirse el menú de Windows: el PDF ya tiene
    destino fijo y el diálogo podría desviar la salida."""
    cleanup()
    db = DatabaseManager(TEST_DB)
    db.initialize()
    llamadas = {}

    def no_dialogo(*_args, **_kwargs):
        raise AssertionError("no debe abrirse el menú de impresión")

    def fake_print(html, *args, **kwargs):
        llamadas["html"] = html
        return True

    try:
        save_show_dialog(db, True)
        monkeypatch.setattr(
            "modules.documentos.ticket._sera_impresora_prueba",
            lambda *_args, **_kwargs: True)
        monkeypatch.setattr(
            "modules.documentos.ticket.imprimir_ticket_con_dialogo", no_dialogo)
        monkeypatch.setattr(
            "modules.documentos.ticket.imprimir_ticket", fake_print)
        assert imprimir_ticket_venta(make_sale(), COMPANY, db,
                                     printer_name="POS-Test")
        assert llamadas, "el ticket no se mandó a imprimir"
    finally:
        db.close()
        cleanup()


def test_sera_impresora_prueba_detecta_destinos_virtuales(monkeypatch):
    from modules.documentos import ticket as modulo

    monkeypatch.setattr(modulo, "resolver_impresora", lambda *_: "POS-Test")
    assert modulo._sera_impresora_prueba("POS-Test") is True

    monkeypatch.setattr(modulo, "resolver_impresora",
                        lambda *_: "Microsoft Print to PDF")
    monkeypatch.setattr(modulo, "_impresora_prueba_instalada", lambda: "POS-Test")
    assert modulo._sera_impresora_prueba("Microsoft Print to PDF") is True

    monkeypatch.setattr(modulo, "_impresora_prueba_instalada", lambda: "")
    monkeypatch.setattr(modulo.Config, "PRINT_TEST_MODE", False)
    assert modulo._sera_impresora_prueba("Microsoft Print to PDF") is False

    monkeypatch.setattr(modulo, "resolver_impresora", lambda *_: "")
    assert modulo._sera_impresora_prueba("") is False


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
