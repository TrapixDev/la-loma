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
    PAPER_MODES,
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


def test_modos_de_papel_sin_rollo():
    assert "rollo" not in PAPER_MODES
    assert set(PAPER_MODES) == {PAPER_WINDOWS, PAPER_LABEL}


def test_modo_rollo_guardado_migra_a_windows():
    db = DatabaseManager(TEST_DB)
    db.initialize()
    try:
        save_paper_mode(db, "rollo")
        assert get_paper_mode(db) == PAPER_WINDOWS
    finally:
        db.close()


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
    assert elegir_papel([], PAPER_LABEL) is None


def test_elegir_papel_etiqueta_sin_ancho_80_usa_todas():
    elegida = elegir_papel([("A4", 210.0, 297.0)], PAPER_LABEL)
    assert elegida == ("A4", 210.0, 297.0)


def test_impresora_pdf_se_rechaza():
    from PyQt6.QtPrintSupport import QPrinterInfo

    from modules.documentos.ticket import (
        _es_impresora_pdf,
        _preparar_impresora,
        resolver_impresora,
        ultima_salida_pdf,
    )

    assert _es_impresora_pdf("Microsoft Print to PDF") is True
    assert _es_impresora_pdf("Microsoft XPS Document Writer") is True

    nombres = [p.printerName() for p in QPrinterInfo.availablePrinters()]
    if "POS-Test" in nombres:
        # Con la impresora virtual instalada, la salida se redirige a un PDF
        # visible en vez de fallar.
        printer = _preparar_impresora("Microsoft Print to PDF")
        assert printer is not None
        assert ultima_salida_pdf()
    elif "Microsoft Print to PDF" in nombres:
        assert _preparar_impresora("Microsoft Print to PDF") is None
    # Un nombre inexistente no rompe: cae a la impresora predeterminada.
    assert resolver_impresora("Impresora inexistente 123")


def test_imprimir_ticket_pdf_devuelve_false():
    from PyQt6.QtPrintSupport import QPrinterInfo

    nombres = [p.printerName() for p in QPrinterInfo.availablePrinters()]
    if "POS-Test" in nombres:
        pytest.skip("POS-Test instalada: la impresión se redirige a PDF de prueba")
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
    from PyQt6.QtPrintSupport import QPrinterInfo

    from modules.documentos.ticket import previsualizar_ticket

    nombres = [p.printerName() for p in QPrinterInfo.availablePrinters()]
    if "POS-Test" in nombres:
        pytest.skip("POS-Test instalada: hay impresora virtual disponible")
    # No debe abrir el visor (es modal) cuando no hay impresora válida.
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
          and "SUBTOTAL" in html and "IMPUESTOS/IVA" in html
          and "MONTO TOTAL" in html and "SON:" in html
          and "DIECISÉIS MIL NOVECIENTOS CINCUENTA COLONES" in html
          and "PAGA CON SINPE" in html
          and "FACTURA CONTADO" in html)
    print(f"[{'OK' if ok else 'FAIL'}] ticket con formato de la referencia")
    assert ok
    # Cada artículo usa descripción + línea de precio/importe para evitar que
    # las cuatro columnas se peguen en el papel térmico de 80 mm.
    assert '<div class="section-title">DETALLE</div>' in html
    assert '<table class="item-header"' in html
    assert '<table class="lineas">' not in html
    assert 'class="rtot"' in html


def test_ticket_anchos_respetados_por_qt():
    """Qt ignora `width` en CSS: las columnas deben usar el atributo HTML.

    Sin esto, los valores numéricos se pegaban a las etiquetas
    (p. ej. «FacturaV-EJEMPLO» o «CANT. × PRECIOIMPORTE»).
    """
    from PyQt6.QtGui import QTextDocument, QTextLength, QTextTable

    from modules.documentos.ticket import ticket_html

    doc = QTextDocument()
    doc.setHtml(ticket_html(_venta(), dict(EMPRESA_BASE)))
    doc.setTextWidth(300.0)
    tablas = [f for f in doc.rootFrame().childFrames()
              if isinstance(f, QTextTable)]
    assert tablas, "el ticket no tiene tablas"
    for tabla in tablas:
        for constraint in tabla.format().columnWidthConstraints():
            assert constraint.type() == QTextLength.Type.PercentageLength, (
                "columna sin ancho porcentual (los valores se pegan)")
            assert constraint.rawValue() > 0


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


def test_tamanos_soportados_api_correcta():
    """QPrinter NO tiene supportedPageSizes en Qt6; la lista la da QPrinterInfo."""
    from PyQt6.QtPrintSupport import QPrinter, QPrinterInfo

    from modules.documentos.ticket import tamanos_soportados

    assert not hasattr(QPrinter, "supportedPageSizes"), \
        "si Qt agregara el método, revisar la implementación"

    impresoras = [p.printerName() for p in QPrinterInfo.availablePrinters()]
    if not impresoras:
        pytest.skip("No hay impresoras instaladas en esta PC")
    tamanos = tamanos_soportados(impresoras[0])
    assert isinstance(tamanos, list)
    if tamanos:
        nombre, ancho, alto = tamanos[0]
        assert isinstance(nombre, str) and ancho >= 0 and alto >= 0
    assert tamanos_soportados("Impresora que no existe 123") == []


def test_escala_para_caber():
    from modules.documentos.ticket import _escala_para_caber

    assert _escala_para_caber(100.0, 80.0) == 1.0
    assert _escala_para_caber(100.0, 0.0) == 1.0
    assert _escala_para_caber(0.0, 80.0) == 1.0
    assert abs(_escala_para_caber(100.0, 150.0) - (100.0 / 150.0)) < 0.001
    assert _escala_para_caber(100.0, 1000.0) == 0.6  # nunca menor al mínimo


def test_mejor_encaja_etiqueta():
    from modules.documentos.ticket import _tamano_que_mejor_encaja

    tamanos = [("Rollo 80x297", 80.0, 297.0), ("Etiqueta 80x40", 80.0, 40.0),
               ("Etiqueta 80x15", 80.0, 15.0)]
    # Ticket de 120mm: el más chico que alcanza es el rollo de 297.
    elegido = _tamano_que_mejor_encaja(tamanos, 120.0)
    assert elegido is not None and elegido[0] == "Rollo 80x297"
    # Ticket de 35mm: entra en la etiqueta de 40 (menos desperdicio).
    elegido = _tamano_que_mejor_encaja(tamanos, 35.0)
    assert elegido is not None and elegido[0] == "Etiqueta 80x40"
    # Ticket de 400mm: ninguno alcanza -> el mayor (y se reduce al imprimir).
    elegido = _tamano_que_mejor_encaja(tamanos, 400.0)
    assert elegido is not None and elegido[2] == 297.0


def test_no_se_inventan_tamanos_de_papel():
    """Regresión: el bug de las 13 páginas venía de un tamaño inventado."""
    import inspect

    from modules import documentos
    from modules.documentos import ticket

    fuente = inspect.getsource(ticket)
    assert "Ticket80" not in fuente, "no se deben inventar nombres de papel"
    assert ".print(printer)" not in fuente, \
        "QTextDocument.print pagina el ticket; se pinta con QPainter"
    assert "printer.supportedPageSizes" not in fuente, \
        "supportedPageSizes es de QPrinterInfo (Qt6)"
    assert hasattr(documentos, "imprimir_ticket")


def test_papel_permite_a4():
    from modules.documentos.pdf_factura import papel_permite_a4

    assert papel_permite_a4(80.0, 297.0) is False, "la térmica de 80mm no imprime A4"
    assert papel_permite_a4(80.1, 15.0) is False
    assert papel_permite_a4(210.0, 297.0) is True
    assert papel_permite_a4(216.0, 279.0) is True
    assert papel_permite_a4(0.0) is False
    assert papel_permite_a4(None) is False


def test_imprimir_factura_rechaza_pdf():
    from modules.documentos.pdf_factura import imprimir_factura

    assert imprimir_factura("<html><body>x</body></html>",
                            "Microsoft Print to PDF") is False
    assert imprimir_factura("<html><body>x</body></html>",
                            "Microsoft XPS Document Writer") is False


def test_a4_printer_config_roundtrip():
    from modules.documentos.pdf_factura import get_a4_printer, save_a4_printer

    db = _db()
    assert get_a4_printer(db) == ""
    save_a4_printer(db, "HP LaserJet 1020")
    assert get_a4_printer(db) == "HP LaserJet 1020"
    save_a4_printer(db, "")
    assert get_a4_printer(db) == ""
    db.close()


def test_fuente_y_margenes_editables():
    from modules.documentos.ticket import _medir_alto, ticket_html

    chico = ticket_html(_venta(), dict(EMPRESA_BASE), font_pt=9.0)
    grande = ticket_html(_venta(), dict(EMPRESA_BASE), font_pt=14.0)
    assert "font-size: 9.0pt" in chico
    assert "font-size: 14.0pt" in grande
    # Con márgenes distintos cambia el ancho útil y la estimación de alto.
    alto_80 = _medir_alto(grande, 80.0, 3.0)
    alto_58 = _medir_alto(grande, 58.0, 3.0)
    assert alto_58 > alto_80, "en papel más angosto el ticket es más alto"


def test_ticket_settings_roundtrip():
    from modules.documentos.ticket import (
        DEFAULT_FONT_PT,
        get_ticket_settings,
        save_ticket_settings,
    )

    db = _db()
    inicial = get_ticket_settings(db)
    assert inicial["font_pt"] == DEFAULT_FONT_PT
    assert inicial["margin_mm"] == 3.0
    assert inicial["scale_mode"] == "ajustar"
    assert inicial["offset_x_mm"] == 0.0
    assert inicial["offset_y_mm"] == 0.0
    save_ticket_settings(db, font_pt=14.0, margin_mm=5.0, width_mm=80.0,
                         line_spacing=1.5, scale_mode="real",
                         offset_x_mm=-3.0, offset_y_mm=1.5)
    ajustes = get_ticket_settings(db)
    assert ajustes["font_pt"] == 14.0
    assert ajustes["margin_mm"] == 5.0
    assert ajustes["line_spacing"] == 1.5
    assert ajustes["scale_mode"] == "real"
    assert ajustes["offset_x_mm"] == -3.0
    assert ajustes["offset_y_mm"] == 1.5
    # Valores fuera de rango se recortan.
    save_ticket_settings(db, font_pt=99.0, margin_mm=-4.0, width_mm=80.0,
                         line_spacing=9.9, scale_mode="invalido",
                         offset_x_mm=-99.0, offset_y_mm=99.0)
    ajustes = get_ticket_settings(db)
    assert ajustes["font_pt"] == 20.0
    assert ajustes["margin_mm"] == 0.0
    assert ajustes["line_spacing"] == 2.0
    assert ajustes["scale_mode"] == "ajustar"
    assert ajustes["offset_x_mm"] == -8.0
    assert ajustes["offset_y_mm"] == 8.0
    db.close()


def test_tamano_que_mejor_encaja_ignora_invalidos():
    from modules.documentos.ticket import _tamano_que_mejor_encaja

    tamanos = [("", -1.0, -1.0), ("82(80)mm x 3276mm", 80.1, 3275.9),
               ("80(72)mm x 297mm", 72.0, 297.0), ("sin medidas", 0.0, 0.0)]
    elegido = _tamano_que_mejor_encaja(tamanos, 120.0)
    assert elegido is not None and elegido[0] == "82(80)mm x 3276mm"


def test_resolver_impresora():
    from PyQt6.QtPrintSupport import QPrinterInfo

    from modules.documentos.ticket import resolver_impresora

    impresoras = [p.printerName() for p in QPrinterInfo.availablePrinters()]
    if not impresoras:
        pytest.skip("No hay impresoras instaladas en esta PC")
    primera = impresoras[0]
    assert resolver_impresora(primera) == primera
    assert resolver_impresora(primera.upper()) == primera
    assert resolver_impresora(primera[:6]) == primera
    assert resolver_impresora("Impresora inexistente 123") in impresoras


def test_visor_actualiza_al_cambiar_letra():
    from modules.documentos.ticket import (
        get_ticket_settings,
        ticket_html,
    )
    from ui.ticket_preview import TicketPreviewDialog

    db = _db()

    def fabrica(font_pt, line_spacing):
        return ticket_html(_venta(), dict(EMPRESA_BASE), font_pt=font_pt,
                           line_spacing=line_spacing)

    ajustes = get_ticket_settings(db)
    dialog = TicketPreviewDialog(fabrica(ajustes["font_pt"],
                                         ajustes["line_spacing"]),
                                 db=db, html_factory=fabrica, ajustes=ajustes)
    try:
        chico = dialog._pagina.height()
        dialog.font_spin.setValue(16.0)
        app.processEvents()
        grande = dialog._pagina.height()
        assert grande > chico, "el visor debe re-renderizar con letra más grande"
        dialog.margin_spin.setValue(6.0)
        app.processEvents()
        assert dialog._pagina.width() == dialog._pagina.width()
        dialog._guardar_predeterminados()
        guardado = get_ticket_settings(db)
        assert guardado["font_pt"] == 16.0
        assert guardado["margin_mm"] == 6.0
    finally:
        dialog.close()
        db.close()


def test_impresion_pdf_una_pagina():
    """Modo de prueba: imprime a Microsoft Print to PDF y verifica 1 página."""
    import re

    from PyQt6.QtPrintSupport import QPrinterInfo

    from config import Config
    from modules.documentos.ticket import imprimir_ticket, ticket_html

    nombres = [p.printerName() for p in QPrinterInfo.availablePrinters()]
    if "Microsoft Print to PDF" not in nombres:
        pytest.skip("No está instalada la impresora virtual PDF")

    destino = os.path.join(PROJECT_DIR, "tests", ".tmp", "ticket_prueba.pdf")
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    if os.path.exists(destino):
        os.remove(destino)

    original_modo = Config.PRINT_TEST_MODE
    original_pdf = Config.PRINT_TEST_PDF
    Config.PRINT_TEST_MODE = True
    Config.PRINT_TEST_PDF = destino
    try:
        html = ticket_html(_venta(), dict(EMPRESA_BASE), font_pt=12.0)
        ok = imprimir_ticket(html, "Microsoft Print to PDF", "")
        assert ok is True, "debía imprimir a la impresora virtual"
        assert os.path.isfile(destino), "no se generó el PDF de prueba"
        with open(destino, "rb") as handle:
            datos = handle.read()
        paginas = len(re.findall(rb"/Type\s*/Page[^s]", datos))
        assert paginas == 1, f"el ticket debe salir en 1 página (salieron {paginas})"
        assert re.search(rb"/MediaBox", datos), "el PDF no tiene MediaBox"
    finally:
        Config.PRINT_TEST_MODE = original_modo
        Config.PRINT_TEST_PDF = original_pdf
        if os.path.exists(destino):
            os.remove(destino)


def test_impresion_a_impresora_virtual_visible():
    """La impresora virtual POS-Test debe dejar un PDF visible de 1 página."""
    import re
    import tempfile

    from PyQt6.QtPrintSupport import QPrinterInfo

    from config import Config
    from modules.documentos.ticket import (
        imprimir_ticket,
        ticket_html,
        ultima_salida_pdf,
    )

    nombres = [p.printerName() for p in QPrinterInfo.availablePrinters()]
    if "POS-Test" not in nombres:
        pytest.skip("No está creada la impresora virtual POS-Test")

    carpeta = Path(tempfile.mkdtemp(prefix="pos_pruebas_"))
    original_dir = Config.PRINT_TEST_DIR
    original_pdf = Config.PRINT_TEST_PDF
    Config.PRINT_TEST_DIR = str(carpeta)
    Config.PRINT_TEST_PDF = ""
    try:
        html = ticket_html(_venta(), dict(EMPRESA_BASE), font_pt=12.0)
        ok = imprimir_ticket(html, "POS-Test", "")
        assert ok is True
        salida = ultima_salida_pdf()
        assert salida and salida.startswith(str(carpeta)), salida
        assert os.path.isfile(salida), "no se generó el PDF de prueba"
        with open(salida, "rb") as handle:
            datos = handle.read()
        assert datos.startswith(b"%PDF")
        paginas = len(re.findall(rb"/Type\s*/Page[^s]", datos))
        assert paginas == 1, f"debe ser 1 página (salieron {paginas})"
    finally:
        Config.PRINT_TEST_DIR = original_dir
        Config.PRINT_TEST_PDF = original_pdf
        import shutil
        shutil.rmtree(carpeta, ignore_errors=True)


def test_ticket_empresa_logo_y_correo():
    from modules.documentos.ticket import ticket_html

    empresa = dict(EMPRESA_BASE, email="factura@mb.cr",
                   logo="logo-colegio.png",
                   iban="CR880151148200100403501", sinpe="6205-5092")
    html = ticket_html(_venta(), empresa, font_pt=12.0)
    ok = ("MB SOLUTIONS CR" in html and "3-101-123456" in html
          and "Centro Comercial Karim" in html and "6205-5092" in html
          and "factura@mb.cr" in html
          and "data:image/png;base64," in html)
    print(f"[{'OK' if ok else 'FAIL'}] ticket con empresa, correo y logo")
    assert ok


def test_factura_a4_logo_y_correo():
    from modules.documentos.pdf_factura import factura_html

    company = {"company_name": "MB SOLUTIONS CR", "company_id": "3-101-123456",
               "phone": "6205-5092", "address": "Centro Comercial Karim",
               "email": "factura@mb.cr", "logo": "logo-colegio.png"}
    html = factura_html(_venta(), company)
    ok = ("MB SOLUTIONS CR" in html and "factura@mb.cr" in html
          and "data:image/png;base64," in html)
    print(f"[{'OK' if ok else 'FAIL'}] factura A4 con logo y correo")
    assert ok


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
        from utils.helpers import NoWheelComboBox, NoWheelIntSpinBox

        assert dialog.copias_spin.value() == 1
        assert dialog.papel_combo.count() == 2
        assert isinstance(dialog.papel_combo, NoWheelComboBox)
        assert isinstance(dialog.copias_spin, NoWheelIntSpinBox)
        dialog.show()
        app.processEvents()
        assert dialog._pagina.height() > 300
    finally:
        dialog.close()


# ---------- geometría compartida entre el visor y la impresión ----------

class _ImpresoraFalsa:
    """QPrinter mínimo para probar la geometría sin abrir la impresora."""

    def __init__(self, ancho_mm: float, alto_mm: float, res: int):
        self._ancho_px = max(1, int(round(ancho_mm * res / 25.4)))
        self._alto_px = max(1, int(round(alto_mm * res / 25.4)))
        self._res = res

    def resolution(self):
        return self._res

    def width(self):
        return self._ancho_px

    def height(self):
        return self._alto_px


def _tinta_bbox(imagen, dpi: float):
    """(x0, x1, y0) de la tinta de una imagen, en milímetros."""
    from PyQt6.QtGui import QImage

    imagen = imagen.convertToFormat(QImage.Format.Format_Grayscale8)
    ancho, alto = imagen.width(), imagen.height()
    stride = imagen.bytesPerLine()
    buffer = bytes(imagen.constBits().asarray(alto * stride))
    tabla = bytes(1 if i < 250 else 0 for i in range(256))
    min_x, max_x, min_y = ancho, -1, alto
    for y in range(alto):
        fila = buffer[y * stride:y * stride + ancho].translate(tabla)
        pos = fila.find(b"\x01")
        if pos >= 0:
            min_x = min(min_x, pos)
            max_x = max(max_x, fila.rfind(b"\x01"))
            min_y = min(min_y, y)
    mm = 25.4 / dpi
    return min_x * mm, (max_x + 1) * mm, min_y * mm


def _tinta_pdf_mm(pdf: str, dpi: int = 150):
    """(ancho de página, x0, x1, y0) de la tinta del PDF, en milímetros."""
    from PyQt6.QtCore import QSize
    from PyQt6.QtGui import QImage, QPainter
    from PyQt6.QtPdf import QPdfDocument

    doc = QPdfDocument(None)
    if doc.load(pdf) != QPdfDocument.Error.None_:
        raise AssertionError(f"no se pudo leer el PDF: {pdf}")
    pagina = doc.pagePointSize(0)
    ancho_mm = pagina.width() / 72 * 25.4
    imagen: QImage = doc.render(0, QSize(int(ancho_mm / 25.4 * dpi),
                                         int(pagina.height() / 72 * dpi)))
    if imagen.hasAlphaChannel():
        fondo = QImage(imagen.size(), QImage.Format.Format_RGB32)
        fondo.fill(0xFFFFFFFF)
        pintor = QPainter(fondo)
        pintor.drawImage(0, 0, imagen)
        pintor.end()
        imagen = fondo
    x0, x1, y0 = _tinta_bbox(imagen, dpi)
    return ancho_mm, x0, x1, y0


def test_geometria_ticket_respeta_driver_y_ancho_configurado():
    from modules.documentos.ticket import geometria_ticket

    # Área de dibujo angosta (form 58 mm): el contenido se limita al área.
    geo = geometria_ticket(_ImpresoraFalsa(52.0, 210.0, 203), 80.0, 3.0)
    assert geo.contenido_mm == pytest.approx(52.0, abs=0.2)
    assert geo.visor_mm == pytest.approx(58.0, abs=0.2)
    assert geo.visor_izq_mm == pytest.approx(3.0)

    # Papel ancho (A4): nunca se estira al ancho completo del papel.
    geo = geometria_ticket(_ImpresoraFalsa(204.0, 291.0, 600), 80.0, 3.0)
    assert geo.contenido_mm == pytest.approx(74.0, abs=0.2)
    assert geo.visor_mm == pytest.approx(80.0, abs=0.2)

    # Papel de 80 mm (térmica): el contenido ocupa el área imprimible.
    geo = geometria_ticket(_ImpresoraFalsa(74.0, 3269.9, 203), 80.0, 3.0)
    assert geo.contenido_mm == pytest.approx(74.0, abs=0.2)

    # Sin impresora: se usa el ancho configurado tal cual.
    geo = geometria_ticket(None, 80.0, 3.0)
    assert geo.contenido_mm == pytest.approx(74.0)
    assert geo.visor_mm == pytest.approx(80.0)

    # Desplazamientos: X negativo pega a la izquierda, Y positivo baja.
    geo = geometria_ticket(_ImpresoraFalsa(74.0, 3269.9, 203), 80.0, 3.0,
                           offset_x_mm=-3.0, offset_y_mm=2.0)
    assert geo.visor_izq_mm == pytest.approx(0.0)
    assert geo.visor_mm == pytest.approx(80.0, abs=0.2)
    assert geo.visor_arriba_mm == pytest.approx(5.0)
    assert geo.visor_abajo_mm == pytest.approx(1.0)

    # Desplazamiento X positivo: margen izquierdo mayor dentro de la tira.
    geo = geometria_ticket(None, 80.0, 3.0, offset_x_mm=2.0)
    assert geo.visor_izq_mm == pytest.approx(5.0)
    assert geo.visor_mm == pytest.approx(80.0)


def test_visor_renderiza_con_la_geometria_del_papel():
    from modules.documentos.ticket import GeometriaTicket, ticket_html
    from ui.ticket_preview import render_ticket

    geo = GeometriaTicket(73.95, 79.95, 3.0, 73.95, 3270.0)
    pixmap = render_ticket(ticket_html(_venta(), dict(EMPRESA_BASE)),
                           geometria=geo, dpi=203)
    assert pixmap.width() == round(geo.visor_mm * 203 / 25.4)
    x0, x1, _y0 = _tinta_bbox(pixmap.toImage(), 203)
    assert x0 == pytest.approx(3.0, abs=0.6), "margen izquierdo del visor"
    assert (x1 - x0) == pytest.approx(geo.contenido_mm, abs=1.5), \
        "el contenido debe ocupar el ancho útil del papel"


def test_margenes_impresos_coinciden_con_el_visor():
    """Regresión: el ticket salía corrido a la derecha y estirado al ancho
    del área imprimible (con el lado derecho recortado)."""
    pytest.importorskip("PyQt6.QtPdf")
    from PyQt6.QtPrintSupport import QPrinterInfo

    nombres = [p.printerName() for p in QPrinterInfo.availablePrinters()]
    if "Microsoft Print to PDF" not in nombres:
        pytest.skip("No está instalada la impresora virtual PDF")

    from config import Config
    from modules.documentos.ticket import imprimir_ticket, ticket_html

    destino = os.path.join(PROJECT_DIR, "tests", ".tmp", "margenes.pdf")
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    if os.path.exists(destino):
        os.remove(destino)
    original_modo = Config.PRINT_TEST_MODE
    original_pdf = Config.PRINT_TEST_PDF
    Config.PRINT_TEST_MODE = True
    Config.PRINT_TEST_PDF = destino
    try:
        ok = imprimir_ticket(ticket_html(_venta(), dict(EMPRESA_BASE)),
                             "Microsoft Print to PDF", "", width_mm=80.0,
                             margin_mm=3.0)
        assert ok is True, "debía imprimir a la impresora virtual"
        assert os.path.isfile(destino), "no se generó el PDF"
        ancho_pagina, x0, x1, y0 = _tinta_pdf_mm(destino)
    finally:
        Config.PRINT_TEST_MODE = original_modo
        Config.PRINT_TEST_PDF = original_pdf
        if os.path.exists(destino):
            os.remove(destino)

    esperado = (ancho_pagina - 74.0) / 2.0
    assert (x1 - x0) == pytest.approx(74.0, abs=1.0), \
        "el contenido debe medir el ancho configurado, no el del papel"
    assert x0 == pytest.approx(esperado, abs=1.0), \
        "margen izquierdo distinto al del visor"
    assert (ancho_pagina - x1) == pytest.approx(esperado, abs=1.0), \
        "margen derecho distinto al del visor (contenido recortado)"
    assert y0 == pytest.approx(3.0, abs=1.0), "margen superior"


def test_desplazamiento_mueve_el_ticket_en_el_papel():
    """Con X negativo el ticket usa el espacio de la izquierda y deja más
    margen a la derecha; con Y positivo baja."""
    pytest.importorskip("PyQt6.QtPdf")
    from PyQt6.QtPrintSupport import QPrinterInfo

    nombres = [p.printerName() for p in QPrinterInfo.availablePrinters()]
    if "Microsoft Print to PDF" not in nombres:
        pytest.skip("No está instalada la impresora virtual PDF")

    from config import Config
    from modules.documentos.ticket import imprimir_ticket, ticket_html

    destino = os.path.join(PROJECT_DIR, "tests", ".tmp", "desplazado.pdf")
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    if os.path.exists(destino):
        os.remove(destino)
    original_modo = Config.PRINT_TEST_MODE
    original_pdf = Config.PRINT_TEST_PDF
    Config.PRINT_TEST_MODE = True
    Config.PRINT_TEST_PDF = destino
    try:
        ok = imprimir_ticket(ticket_html(_venta(), dict(EMPRESA_BASE)),
                             "Microsoft Print to PDF", "", width_mm=80.0,
                             margin_mm=3.0, offset_x_mm=-3.0, offset_y_mm=2.0)
        assert ok is True
        assert os.path.isfile(destino)
        ancho_pagina, x0, x1, y0 = _tinta_pdf_mm(destino)
    finally:
        Config.PRINT_TEST_MODE = original_modo
        Config.PRINT_TEST_PDF = original_pdf
        if os.path.exists(destino):
            os.remove(destino)

    assert x0 <= 1.0, "con X=-3 el contenido queda pegado a la izquierda"
    assert (x1 - x0) == pytest.approx(74.0, abs=1.0)
    assert (ancho_pagina - x1) >= 74.0, \
        "a la derecha debe quedar más margen que antes del desplazamiento"
    assert y0 == pytest.approx(5.0, abs=1.0), \
        "con Y=2 el contenido baja 2 mm (3 de margen + 2)"
