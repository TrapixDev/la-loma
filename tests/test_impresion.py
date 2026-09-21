"""Impresión de tickets: elección de papel y funciones de vista previa."""

import os
import sys
from pathlib import Path

PROJECT_DIR = str(Path(__file__).resolve().parents[1])
sys.path.insert(0, PROJECT_DIR)
os.chdir(PROJECT_DIR)
os.environ["QT_QPA_PLATFORM"] = "offscreen"

import pytest

from PyQt6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])

from database.db_manager import DatabaseManager
from modules.documentos.ticket import (
    PAPER_LABEL,
    PAPER_ROLL,
    PAPER_WINDOWS,
    _preparar_impresora,
    elegir_papel,
    get_paper_mode,
    get_show_dialog,
    imprimir_ticket,
    save_paper_mode,
    save_show_dialog,
)

TEST_DB = os.path.join(PROJECT_DIR, "tests", ".tmp", "test_impresion.db")


def cleanup():
    for _ in range(5):
        try:
            if os.path.exists(TEST_DB):
                os.remove(TEST_DB)
            for ext in ("-wal", "-shm"):
                p = TEST_DB + ext
                if os.path.exists(p):
                    os.remove(p)
        except PermissionError:
            import time
            time.sleep(0.1)


def setup_function():
    cleanup()


def teardown_function():
    cleanup()


SOPORTADAS = [
    ("Roll paper 80 x 297mm", 80.0, 297.0),
    ("Label 80 x 40mm", 80.0, 40.0),
    ("Label 80 x 15mm", 80.1, 15.0),
    ("A4", 210.0, 297.0),
]


def test_elegir_papel_rollo_usa_el_mas_alto():
    elegida = elegir_papel(SOPORTADAS, PAPER_ROLL)
    assert elegida is not None and elegida[0] == "Roll paper 80 x 297mm"
    assert elegida[2] == 297.0


def test_elegir_papel_etiqueta_prefiere_ancho_exacto():
    elegida = elegir_papel(SOPORTADAS, PAPER_LABEL)
    assert elegida is not None
    assert elegida[0] == "Label 80 x 40mm"


def test_elegir_papel_etiqueta_empate_de_ancho_usa_la_corta():
    opciones = [("Label 80 x 40mm", 80.0, 40.0),
                ("Label 80 x 15mm", 80.0, 15.0)]
    elegida = elegir_papel(opciones, PAPER_LABEL)
    assert elegida is not None and elegida[2] == 15.0


def test_elegir_papel_windows_no_cambia_nada():
    assert elegir_papel(SOPORTADAS, PAPER_WINDOWS) is None
    assert elegir_papel([], PAPER_ROLL) is None


def test_elegir_papel_sin_ancho_80_usa_todas():
    elegida = elegir_papel([("A4", 210.0, 297.0)], PAPER_ROLL)
    assert elegida == ("A4", 210.0, 297.0)


def test_impresora_pdf_se_rechaza():
    assert _preparar_impresora("Microsoft Print to PDF") is None
    assert _preparar_impresora("Microsoft XPS Document Writer") is None


def test_imprimir_ticket_pdf_devuelve_false():
    assert imprimir_ticket("<html><body>x</body></html>",
                           "Microsoft Print to PDF") is False


def _db() -> DatabaseManager:
    db = DatabaseManager(TEST_DB)
    db.initialize()
    return db


def test_papel_y_dialogo_se_guardan():
    db = _db()
    assert get_paper_mode(db) == PAPER_WINDOWS
    assert get_show_dialog(db) is False
    save_paper_mode(db, PAPER_LABEL)
    save_show_dialog(db, True)
    assert get_paper_mode(db) == PAPER_LABEL
    assert get_show_dialog(db) is True
    save_paper_mode(db, "invalido")
    assert get_paper_mode(db) == PAPER_WINDOWS
    db.close()


def test_previsualizar_sin_impresora_valida():
    from modules.documentos.ticket import previsualizar_ticket

    assert previsualizar_ticket("<html><body>x</body></html>",
                                "Microsoft Print to PDF") is False


@pytest.mark.skipif(os.environ.get("POS_TEST_PREVIEW") != "1",
                    reason="Requiere impresora real (POS_TEST_PREVIEW=1)")
def test_previsualizar_con_impresora_real():
    from modules.documentos.ticket import previsualizar_ticket

    assert isinstance(previsualizar_ticket("<html><body>x</body></html>"), bool)


# ---------- formato del ticket ----------

def _venta():
    from database.models import Sale, SaleItem

    return Sale(
        id=1, invoice_number="V-00081", subtotal=15000.0, discount=0.0,
        tax_amount=1950.0, total=16950.0, payment_method="sinpe",
        cash_received=16950.0, change_amount=0.0, payment_details="[]",
        invoice_type="general", currency="CRC", exchange_rate=520.0,
        status="completada",
        hacienda_key="5062109260031011234560010000101000000008119",
        hacienda_status="ACEPTADA", station="CAJA1", user_name="kuchu",
        created_at="2026-09-21 09:03:00",
        items=[SaleItem(product_id=1, product_name="Mueble de sala",
                        quantity=1, unit_price=15000.0, total=15000.0,
                        tax_amount=1950.0)],
    )


EMPRESA_BASE = {
    "company_name": "MB SOLUTIONS CR", "company_id": "3-101-123456",
    "phone": "6205-5092", "address": "Centro Comercial Karim del Golfo",
}


def test_ticket_formato_referencia():
    from modules.documentos.ticket import ticket_html

    html = ticket_html(_venta(), dict(EMPRESA_BASE))
    ok = ("CANT" in html and "DETALLE" in html and "PRECIO" in html
          and "SUBTOT" in html and "IVA" in html
          and "MONTO TOTAL" in html and "SON:" in html
          and "DIECISÉIS MIL NOVECIENTOS CINCUENTA COLONES" in html
          and "PAGA CON SINPE" in html
          and "FACTURA CONTADO" in html)
    print(f"[{'OK' if ok else 'FAIL'}] ticket con formato de la referencia")
    assert ok


def test_ticket_omite_campos_vacios_y_muestra_extras():
    from modules.documentos.ticket import ticket_html

    sin_extras = ticket_html(_venta(), dict(EMPRESA_BASE))
    assert "IBAN:" not in sin_extras and "SINPE MÓVIL:" not in sin_extras

    empresa = dict(EMPRESA_BASE, email="factura@mb.cr",
                   iban="CR880151148200100403501", sinpe="6205-5092")
    html = ticket_html(_venta(), empresa)
    ok = ("factura@mb.cr" in html and "IBAN: CR880151148200100403501" in html
          and "SINPE MÓVIL: 6205-5092" in html)
    print(f"[{'OK' if ok else 'FAIL'}] extras del ticket (correo/IBAN/SINPE)")
    assert ok


def test_ticket_marca_reimpresion():
    from modules.documentos.ticket import ticket_html

    normal = ticket_html(_venta(), dict(EMPRESA_BASE))
    reimpreso = ticket_html(_venta(), dict(EMPRESA_BASE), es_reimpresion=True)
    assert "REIMPRESIÓN" not in normal
    assert "REIMPRESIÓN" in reimpreso


def test_monto_en_letras():
    from utils.helpers import monto_en_letras as texto

    assert texto(0) == "CERO COLONES"
    assert texto(15.5).startswith("QUINCE COLONES CON 50/100")
    assert texto(15000) == "QUINCE MIL COLONES"
    assert texto(21000) == "VEINTIÚN MIL COLONES"
    assert texto(16950) == "DIECISÉIS MIL NOVECIENTOS CINCUENTA COLONES"
    assert texto(15000, "USD") == "QUINCE MIL DÓLARES"


def test_empresa_extras_roundtrip():
    from modules.documentos.xml_factura import cargar_empresa, guardar_empresa_extra

    db = _db()
    guardar_empresa_extra(db, email="a@b.cr", iban="CR123", sinpe="8888-8888",
                          logo="")
    datos = cargar_empresa(db)
    assert datos.get("email") == "a@b.cr"
    assert datos.get("iban") == "CR123"
    assert datos.get("sinpe") == "8888-8888"
    assert datos.get("logo"), "sin logo configurado usa el PNG de la raíz"
    assert "logo-colegio.png" in datos["logo"]
    db.close()


def test_visor_preview_renderiza_una_pagina():
    from ui.ticket_preview import TicketPreviewDialog, render_ticket
    from modules.documentos.ticket import ticket_html

    pixmap = render_ticket(ticket_html(_venta(), dict(EMPRESA_BASE)))
    assert pixmap.width() > 300 and pixmap.height() > 300

    dialog = TicketPreviewDialog(ticket_html(_venta(), dict(EMPRESA_BASE)))
    try:
        assert dialog.copias_spin.value() == 1
        assert dialog.papel_combo.count() == 3
        dialog.show()
        app.processEvents()
        assert dialog._pagina.height() > 300
    finally:
        dialog.close()
