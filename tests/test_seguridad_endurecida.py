"""Endurecimientos de la auditoría: rutas, firmas, HTML y CSV seguros."""

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

import config as config_module
from database.models import Sale, SaleItem
from server import _es_loopback, _image_dimensions
from modules.documentos.factura_service import _base_nombre, _destino_seguro
from modules.documentos.ticket import _logo_data_uri
from utils.archivos import ruta_imagen_permitida, ruta_logo_segura


def _venta(**extra) -> Sale:
    datos = dict(
        id=1, invoice_number="V-00021", subtotal=1000.0, tax_amount=130.0,
        total=1130.0, payment_method="tarjeta", cash_received=1130.0,
        invoice_type="general", currency="CRC", exchange_rate=520.0,
        status="completada", station="CAJA1", user_name="Cajero",
        created_at="2026-09-28 10:00:00",
        items=[SaleItem(product_id=1, product_name="Mesa",
                        quantity=1, unit_price=1000.0, total=1000.0)],
    )
    datos.update(extra)
    return Sale(**datos)


# ---------- números de factura y rutas de documentos ----------

@pytest.mark.parametrize("numero", [
    "..\\..\\Users\\Public\\evil",
    "\\\\attacker\\share\\factura",
    "C:\\Windows\\Temp\\x",
    "V-00021",
])
def test_base_nombre_sanea_el_numero(numero):
    nombre = _base_nombre(_venta(invoice_number=numero))
    assert ".." not in nombre
    assert "\\" not in nombre
    assert "/" not in nombre
    assert ":" not in nombre
    if numero == "V-00021":
        assert nombre.startswith("V-00021_")


def test_destino_seguro_no_sale_de_la_carpeta(tmp_path):
    destino = _destino_seguro(tmp_path, "V-00021_2026-09-28", ".xml")
    assert destino.parent == tmp_path.resolve()
    with pytest.raises(ValueError):
        _destino_seguro(tmp_path, "..\\fuera", ".xml")


# ---------- imágenes y logo ----------

def test_ruta_imagen_permitida_dentro_y_fuera(tmp_path, monkeypatch):
    monkeypatch.setattr(config_module.Config, "PRODUCT_IMAGES_DIR",
                        str(tmp_path))
    monkeypatch.setattr(config_module.Config, "IMAGE_CACHE_DIR",
                        str(tmp_path / "cache"))
    png = tmp_path / "foto.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 32)
    ajeno = tmp_path / "afuera"
    ajeno.mkdir()
    (ajeno / "otra.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 32)
    texto = tmp_path / "notas.png"
    texto.write_text("no soy imagen", encoding="utf-8")

    assert ruta_imagen_permitida(str(png)) == png.resolve()
    assert ruta_imagen_permitida("foto.png") == png.resolve()
    assert ruta_imagen_permitida(str(txt_path := (tmp_path / "secreto.txt"))) is None
    assert ruta_imagen_permitida(str(Path(tmp_path).parent / "otra.png")) is None
    assert ruta_imagen_permitida(str(texto)) is None
    assert ruta_imagen_permitida(r"\\servidor\recurso\foto.png") is None
    assert ruta_imagen_permitida("") is None


def test_logo_solo_imagenes_locales(tmp_path):
    png = tmp_path / "logo.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 32)
    txt = tmp_path / "notas.txt"
    txt.write_text("secreto", encoding="utf-8")
    falso = tmp_path / "falso.png"
    falso.write_text("no soy imagen", encoding="utf-8")

    assert ruta_logo_segura(str(png)) == png.resolve()
    assert ruta_logo_segura(str(txt)) is None
    assert ruta_logo_segura(str(falso)) is None
    assert ruta_logo_segura(r"\\servidor\logo.png") is None
    assert _logo_data_uri(str(txt)) == ""
    assert _logo_data_uri(str(png)).startswith("data:image/png;base64,")


# ---------- escapado en documentos ----------

def test_factura_escapa_clave_y_pago():
    from modules.documentos.pdf_factura import factura_html

    venta = _venta(
        hacienda_key='<img src="file:///C:/Windows/win.ini">',
        payment_method="mixto",
        payment_details='[{"method":"<b>x</b>","amount":10}]',
        electronic_invoice=True,
    )
    html = factura_html(venta, {"company_name": "Empresa"})
    assert "<img src=" not in html
    assert "&lt;img" in html
    assert "<b>x</b>" not in html

    from modules.documentos.pdf_nota_credito import nota_credito_html

    nota = {"referencia_clave": "<script>alert(1)</script>",
            "invoice_number": "NC-1", "total": 10.0}
    html_nc = nota_credito_html(venta, {"company_name": "Empresa"}, nota)
    assert "<script>" not in html_nc
    assert "&lt;script&gt;" in html_nc


def test_detalle_movimientos_en_texto_plano():
    from modules.reports.detail_dialogs import _esc

    assert _esc('<b>"x" & y</b>') == (
        "&lt;b&gt;&quot;x&quot; &amp; y&lt;/b&gt;")


# ---------- CSV seguro ----------

def test_csv_no_inyecta_formulas():
    from modules.reports.reports_widget import _csv_seguro

    assert _csv_seguro("=SUM(A1)") == "'=SUM(A1)"
    assert _csv_seguro("+1") == "'+1"
    assert _csv_seguro("-1") == "'-1"
    assert _csv_seguro("@x") == "'@x"
    assert _csv_seguro("Renta") == "Renta"
    assert _csv_seguro(1500) == 1500


# ---------- servidor ----------

def test_solo_loopback_crea_pin_inicial():
    assert _es_loopback("127.0.0.1") is True
    assert _es_loopback("::1") is True
    assert _es_loopback("::ffff:127.0.0.1") is True
    assert _es_loopback("192.168.1.25") is False
    assert _es_loopback("10.0.0.7") is False
    assert _es_loopback("8.8.8.8") is False
    assert _es_loopback("") is False


def test_dimensiones_de_imagen():
    import struct
    import zlib

    def _png(ancho: int, alto: int) -> bytes:
        def chunk(tipo: bytes, datos: bytes) -> bytes:
            return (struct.pack(">I", len(datos)) + tipo + datos
                    + struct.pack(">I", zlib.crc32(tipo + datos)))

        ihdr = struct.pack(">IIBBBBB", ancho, alto, 8, 2, 0, 0, 0)
        return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
                + chunk(b"IEND", b""))

    assert _image_dimensions(_png(640, 480)) == (640, 480)
    assert _image_dimensions(_png(9000, 10)) == (9000, 10)
    assert _image_dimensions(b"no es imagen") is None
