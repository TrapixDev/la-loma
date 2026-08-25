"""Ticket térmico 80mm: HTML compacto y envío a la impresora térmica.

Usa el driver de Windows de la impresora (Epson, Star, etc.) vía QPrinter
con página de 80mm y alto calculado según el contenido, para no desperdiciar
papel y cortar justo después del ticket.
"""

import json as _json

from PyQt6.QtCore import QMarginsF, QSizeF
from PyQt6.QtGui import QPageLayout, QPageSize, QTextDocument
from PyQt6.QtPrintSupport import QPrinter, QPrinterInfo

from config import Config
from utils.helpers import format_currency

_TICKET_WIDTH_MM = 80
_MARGIN_MM = 3


# ---------- helpers ----------

def _html_escape(value) -> str:
    if value is None:
        return ""
    text = str(value)
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                 .replace('"', "&quot;"))


def _fnum(value) -> str:
    try:
        num = float(value or 0)
    except (TypeError, ValueError):
        return "0"
    if num == int(num):
        return str(int(num))
    return f"{num:.2f}".rstrip("0").rstrip(".")


def _fecha_corta(value) -> str:
    text = str(value or "").strip()
    if len(text) >= 16:
        return text[8:10] + "/" + text[5:7] + "/" + text[:4] + " " + text[11:16]
    if len(text) >= 10:
        return text[8:10] + "/" + text[5:7] + "/" + text[:4]
    return text


def _desglose_pago(sale, moneda) -> list[str]:
    """Lista de líneas del desglose de pago (métodos, montos, vuelto)."""
    lines: list[str] = []
    method = str(getattr(sale, "payment_method", "") or "").lower()
    details_raw = getattr(sale, "payment_details", "") or ""
    if method == "mixto" and details_raw.startswith("[") and details_raw != "[]":
        try:
            det = _json.loads(details_raw)
            for d in det:
                nombre = str(d.get("method", "")) or "Pago"
                lines.append(f"{nombre:<12} {format_currency(float(d.get('amount') or 0), moneda)}")
            if float(getattr(sale, "change_amount", 0) or 0) > 0:
                lines.append(
                    f"{'Vuelto':<12} {format_currency(float(sale.change_amount), moneda)}")
        except Exception:
            pass
    elif method == "efectivo" and float(getattr(sale, "cash_received", 0) or 0) > 0:
        lines.append(
            f"{'Efectivo':<12} {format_currency(float(sale.cash_received), moneda)}")
        if float(getattr(sale, "change_amount", 0) or 0) > 0:
            lines.append(
                f"{'Vuelto':<12} {format_currency(float(sale.change_amount), moneda)}")
    elif method in ("tarjeta", "sinpe") and float(getattr(sale, "cash_received", 0) or 0) > 0:
        lines.append(
            f"{'Pago ' + method.title():<12} {format_currency(float(sale.cash_received), moneda)}")
    return lines


# ---------- HTML del ticket ----------

def ticket_html(sale, company: dict) -> str:
    """HTML compacto del ticket térmico (80mm) para una venta guardada."""
    items = sale.items or []
    currency = str(getattr(sale, "currency", "CRC") or "CRC")
    rate = float(getattr(sale, "exchange_rate", 0) or 0)
    # Los montos de la venta se guardan en CRC; el ticket los muestra en la
    # moneda en que se cobró (los detalles de pago ya vienen en esa moneda).
    factor = (1.0 / rate) if currency == "USD" and rate > 0 else 1.0

    def moneda(valor: float) -> str:
        return format_currency(float(valor or 0) * factor, currency)

    is_simplified = getattr(sale, "invoice_type", "general") == "simplificada"
    if is_simplified:
        title = "FACTURA SIMPLIFICADA"
    elif getattr(sale, "electronic_invoice", False):
        title = "FACTURA ELECTRONICA"
    else:
        title = "FACTURA"

    rows = "\n".join(
        f'<tr>'
        f'<td class="q">{_fnum(item.quantity)}</td>'
        f'<td>{_html_escape(item.product_name)}</td>'
        f'<td class="r">{moneda(float(item.unit_price or 0))}</td>'
        f'<td class="r">{moneda(float(item.total or 0))}</td>'
        f'</tr>'
        for item in items
    )

    discount_line = ""
    if float(getattr(sale, "discount", 0) or 0) > 0:
        discount_line = f'<tr><td>Descuento</td><td></td><td></td><td class="r">{moneda(sale.discount)}</td></tr>'

    subtotal_val = float(getattr(sale, "subtotal", 0) or 0)
    tax_val = float(getattr(sale, "tax_amount", 0) or 0)
    if is_simplified:
        tax_val = 0.0

    equiv_line = ""
    if currency == "USD" and rate > 0 and Config.MOSTRAR_EQUIVALENTE_CRC:
        equiv_line = (f'<tr><td>Equiv. CRC</td><td></td><td></td>'
                      f'<td class="r">{format_currency(float(sale.total), "CRC")}</td></tr>')

    tax_line = ""
    if is_simplified:
        tax_line = '<tr><td>Exento de IVA</td><td></td><td></td><td></td></tr>'
    else:
        tax_line = f'<tr><td>Impuesto</td><td></td><td></td><td class="r">{moneda(tax_val)}</td></tr>'

    pago_lines = _desglose_pago(sale, currency)
    pago_html = "".join(
        f'<tr><td colspan="4">{_html_escape(ln)}</td></tr>' for ln in pago_lines)

    clave_html = ""
    if not is_simplified:
        clave = getattr(sale, "hacienda_key", "") or ""
        if clave:
            clave_html = f'<div class="clave">Clave: {_html_escape(clave)}</div>'

    nombre_cliente = getattr(sale, "client_name", "") or "Consumidor Final"
    cliente_html = ""
    if not is_simplified:
        cliente_html = f'<div class="cliente">Cliente: {_html_escape(nombre_cliente)}</div>'

    return f"""<html><head><style>
body {{ font-family: 'Courier New', monospace; font-size: 9pt; color: #000; margin: 0; }}
.centro {{ text-align: center; }}
.nombre {{ font-weight: bold; font-size: 10pt; }}
.mini {{ font-size: 8pt; }}
.linea {{ border-top: 1px dashed #000; margin: 3px 0; }}
table {{ width: 100%; border-collapse: collapse; }}
td {{ padding: 0; vertical-align: top; }}
.q {{ width: 8%; text-align: right; }}
.r {{ width: 26%; text-align: right; white-space: nowrap; }}
.total {{ font-weight: bold; font-size: 11pt; }}
.clave {{ font-size: 7.5pt; word-break: break-all; margin-top: 4px; }}
.cliente {{ margin: 3px 0; }}
.pie {{ text-align: center; font-weight: bold; margin-top: 6px; }}
</style></head><body>
<div class="centro nombre">{_html_escape(company.get("company_name", "POS La Loma"))}</div>
<div class="centro mini">{_html_escape(company.get("address", ""))}</div>
<div class="centro mini">{_html_escape(company.get("phone", ""))} · Céd. {_html_escape(company.get("company_id", ""))}</div>
<div class="linea"></div>
<div class="centro"><b>{title}</b></div>
<div class="centro mini">Factura: {_html_escape(getattr(sale, 'invoice_number', '') or '')}</div>
<div class="centro mini">{_fecha_corta(getattr(sale, 'created_at', ''))}</div>
<div class="centro mini">Caja: {_html_escape(getattr(sale, 'station', '') or '')} · Cajero: {_html_escape(getattr(sale, 'user_name', '') or '')}</div>
<div class="linea"></div>
{cliente_html}
<table>
<tr><td class="q">Cant</td><td>Descripcion</td><td class="r">P.U.</td><td class="r">Total</td></tr>
{rows}
</table>
<div class="linea"></div>
<table>
<tr><td>Subtotal</td><td></td><td></td><td class="r">{moneda(subtotal_val)}</td></tr>
{discount_line}
{tax_line}
<tr class="total"><td>TOTAL</td><td></td><td></td><td class="r">{moneda(float(sale.total))}</td></tr>
{equiv_line}
</table>
<div class="linea"></div>
<table>
<tr><td colspan="4">Metodo: {_html_escape(str(getattr(sale, 'payment_method', '') or '').title())}</td></tr>
{pago_html}
</table>
{clave_html}
<div class="pie">GRACIAS POR SU COMPRA</div>
<div class="centro mini">{'Regimen de Tributacion Simplificada' if is_simplified else 'Hacienda: ' + (str(getattr(sale, 'hacienda_status', '') or '').upper() or 'ENVIADA')}</div>
</body></html>"""


def ticket_prueba_html() -> str:
    """Ticket de prueba para verificar la impresora."""
    return """<html><head><style>
body {{ font-family: 'Courier New', monospace; font-size: 9pt; color: #000; }}
.centro {{ text-align: center; }}
.linea {{ border-top: 1px dashed #000; margin: 3px 0; }}
</style></head><body>
<div class="centro"><b>PRUEBA DE IMPRESORA</b></div>
<div class="centro">POS La Loma</div>
<div class="linea"></div>
<div>Si puede leer este ticket, la impresora</div>
<div>esta configurada correctamente.</div>
<div class="linea"></div>
<div class="centro">Gracias</div>
</body></html>"""


# ---------- impresión ----------

def _documento(html: str) -> QTextDocument:
    doc = QTextDocument()
    doc.setHtml(html)
    return doc


def _medir_alto(html: str) -> float:
    """Estima el alto (mm) del ticket según su contenido."""
    try:
        mm_to_px = 96.0 / 25.4
        width_px = max(1.0, (_TICKET_WIDTH_MM - 2 * _MARGIN_MM) * mm_to_px)
        doc = _documento(html)
        doc.setPageSize(QSizeF(width_px, 100000.0))
        alto_mm = (doc.size().height() / mm_to_px) + 2 * _MARGIN_MM
        return min(max(alto_mm, 50.0), 500.0)
    except Exception:
        return 297.0


def imprimir_ticket(html: str, printer_name: str = "") -> bool:
    """Imprime el ticket en la impresora indicada (o la predeterminada).

    True si se envió a imprimir. False si no hay impresora válida o la
    seleccionada es un PDF/XPS.
    """
    name = printer_name or QPrinterInfo.defaultPrinterName()
    if not name:
        return False
    lower = name.lower()
    if "pdf" in lower or "xps" in lower:
        return False
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setPrinterName(name)
    alto = _medir_alto(html)
    printer.setPageSize(QPageSize(
        QSizeF(_TICKET_WIDTH_MM, alto), QPageSize.Unit.Millimeter,
        "Ticket80", QPageSize.SizeMatchPolicy.ExactMatch))
    printer.setPageMargins(QMarginsF(_MARGIN_MM, _MARGIN_MM, _MARGIN_MM, _MARGIN_MM),
                           QPageLayout.Unit.Millimeter)
    _documento(html).print(printer)
    return True


def imprimir_ticket_venta(sale, company: dict, db=None) -> bool:
    """Genera e imprime el ticket de una venta en la impresora configurada."""
    printer_name = get_printer_name(db) if db is not None else ""
    return imprimir_ticket(ticket_html(sale, company), printer_name)


def imprimir_prueba(printer_name: str = "") -> bool:
    """Imprime un ticket de prueba. True si se envió a imprimir."""
    return imprimir_ticket(ticket_prueba_html(), printer_name)


# ---------- configuración de impresora (app_config) ----------

def get_printer_name(db) -> str:
    """Nombre de la impresora de tickets guardada en app_config."""
    try:
        rows = db.execute_query(
            "SELECT value FROM app_config WHERE key = 'printer_name'")
        return str(rows[0]["value"]) if rows else ""
    except Exception:
        return ""


def save_printer_name(db, name: str) -> None:
    """Guarda el nombre de la impresora de tickets en app_config."""
    try:
        db.execute_update(
            "INSERT OR REPLACE INTO app_config (key, value) VALUES ('printer_name', ?)",
            (str(name),))
    except Exception:
        pass
