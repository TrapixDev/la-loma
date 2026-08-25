"""Orquestación de documentos: guardar XML+PDF y reimprimir facturas."""

from . import pdf_factura as _pdf
from . import pdf_nota_credito as _pdf_nc
from . import xml_factura as _xml
from . import xml_nota_credito as _xml_nc
from .paths import carpeta_factura


def _base_nombre(sale) -> str:
    """Nombre base de los archivos: V-00021-2026-08-02 .xml/.pdf."""
    numero = str(getattr(sale, "invoice_number", "") or "")
    fecha = str(getattr(sale, "created_at", "") or "")
    if len(fecha) >= 10:
        fecha = fecha[:10]
    base = numero or "factura"
    if fecha:
        return f"{base}_{fecha}"
    return base


def generar_documentos(sale, company: dict, payload: dict | None = None,
                       clave: str = "", medio_pago: str = "01") -> dict:
    """Genera y guarda el respaldo de una venta en Documentos.

    - XML FEAT v4.3 (solo si hay payload de factura electrónica).
    - PDF de la factura siempre.

    Archivos nombrados como {numero}_{AAAA-MM-DD}.{xml,pdf}

    Devuelve {"carpeta", "xml", "pdf", "html"} con rutas (o None).
    """
    nombre = _base_nombre(sale)
    carpeta = carpeta_factura(getattr(sale, "created_at", None))
    html = _pdf.factura_html(sale, company)
    pdf_path = _pdf.guardar_pdf(carpeta, nombre, html)

    xml_path = None
    if payload:
        xml_text = _xml.build_factura_xml(payload, clave, medio_pago)
        xml_path = carpeta / f"{nombre}.xml"
        xml_path.write_text(xml_text, encoding="utf-8")

    return {
        "carpeta": str(carpeta),
        "xml": str(xml_path) if xml_path and xml_path.exists() else None,
        "pdf": str(pdf_path) if pdf_path else None,
        "html": html,
    }


def reimprimir_factura(db, cart_service, sale_id: int, imprimir: bool = True) -> dict | None:
    """Reedita el PDF (y lo imprime) de una venta ya guardada.

    Imprime el ticket térmico en la impresora configurada; si no se puede,
    intenta la factura A4 en la impresora por defecto.

    Devuelve el dict de generar_documentos (sin XML) o None si la venta no existe.
    """
    try:
        sale = cart_service.get_sale(sale_id)
    except Exception:
        return None
    if sale is None:
        return None
    company = _xml.cargar_empresa(db)
    resultado = generar_documentos(sale, company, payload=None)
    if imprimir and resultado["pdf"]:
        try:
            from .ticket import imprimir_ticket_venta
            if not imprimir_ticket_venta(sale, company, db):
                _pdf.imprimir_factura(resultado["html"])
        except Exception:
            _pdf.imprimir_factura(resultado["html"])
    return resultado


def generar_nota_credito(sale, company: dict, nota: dict,
                         cliente=None, payload: dict | None = None,
                         clave: str = "", imprimir: bool = False) -> dict:
    """Genera y guarda XML+PDF de una nota de crédito para una venta.

    - XML <NotaCreditoElectronica> (si hay payload).
    - PDF de la nota de crédito siempre.
    - Imprime si `imprimir` es True.

    Archivos nombrados como {num_nota}_{AAAA-MM-DD}.{xml,pdf}
    Devuelve {"carpeta", "xml", "pdf", "html"} con rutas (o None).
    """
    nombre = _base_nombre(_NotaShim(nota))
    carpeta = carpeta_factura(nota.get("created_at"))
    html = _pdf_nc.nota_credito_html(sale, company, nota, cliente_nombre=cliente_nombre(sale))
    pdf_path = _pdf_nc.guardar_pdf(carpeta, nombre, html)

    xml_path = None
    if payload:
        xml_text = _xml_nc.build_nota_credito_xml(payload, clave)
        xml_path = carpeta / f"{nombre}.xml"
        xml_path.write_text(xml_text, encoding="utf-8")

    if imprimir and pdf_path:
        _pdf_nc.imprimir_nota_credito(html)

    return {
        "carpeta": str(carpeta),
        "xml": str(xml_path) if xml_path and xml_path.exists() else None,
        "pdf": str(pdf_path) if pdf_path else None,
        "html": html,
    }


class _NotaShim:
    """Adapta el dict de la nota de crédito a lo que espera _base_nombre."""

    def __init__(self, nota: dict):
        self.invoice_number = nota.get("invoice_number", "")
        self.created_at = nota.get("created_at", "")


def cliente_nombre(sale) -> str:
    return getattr(sale, "client_name", "") or "Consumidor Final"