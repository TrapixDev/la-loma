"""Factura imprimible: HTML -> PDF (Qt) y copia física a la impresora."""

from pathlib import Path

from PyQt6.QtCore import QMarginsF
from PyQt6.QtGui import QPageLayout, QPageSize, QTextDocument
from PyQt6.QtPrintSupport import QPrinter, QPrinterInfo

from utils.helpers import format_currency

_MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
          "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def _fecha_corta(value) -> str:
    text = str(value or "").strip()
    if len(text) >= 16:
        return text[8:10] + "/" + text[5:7] + "/" + text[:4] + " " + text[11:16]
    if len(text) >= 10:
        return text[8:10] + "/" + text[5:7] + "/" + text[:4]
    return text


def factura_html(sale, company: dict, cliente_nombre: str = "") -> str:
    """HTML de la factura/ticket a partir de la venta guardada."""
    items = sale.items or []
    is_simplified = getattr(sale, "invoice_type", "general") == "simplificada"
    if is_simplified:
        title = "FACTURA SIMPLIFICADA"
    elif getattr(sale, "electronic_invoice", False):
        title = "FACTURA ELECTRÓNICA"
    else:
        title = "FACTURA"
    rows = "\n".join(
        '<tr>'
        f'<td align="center">{_fnum(item.quantity)}</td>'
        f'<td>{_html_escape(item.product_name)}</td>'
        f'<td align="right">{format_currency(float(item.unit_price or 0))}</td>'
        f'<td align="right">{format_currency(float(item.discount or 0))}</td>'
        f'<td align="right">{format_currency(float(item.total or 0))}</td>'
        '</tr>'
        for item in items
    )

    discount_line = ""
    if float(getattr(sale, "discount", 0) or 0) > 0:
        discount_line = _row("Descuento", format_currency(float(sale.discount)))

    cash_lines = ""
    method = str(getattr(sale, "payment_method", "") or "").lower()
    details_raw = getattr(sale, "payment_details", "") or ""
    # El PDF va en colones, pero los montos de pago se guardan en la moneda en
    # que se cobró (si fue en USD hay que reconvertirlos a CRC para mostrarlos).
    currency = str(getattr(sale, "currency", "CRC") or "CRC")
    rate = float(getattr(sale, "exchange_rate", 0) or 0)
    factor = rate if currency == "USD" and rate > 0 else 1.0

    def _crc(value) -> str:
        return format_currency(float(value or 0) * factor)

    if method == "mixto" and details_raw.startswith("[") and details_raw != "[]":
        try:
            import json as _json
            det = _json.loads(details_raw)
            cash_lines = "".join(
                _row(str(d.get("method", "")), _crc(d.get("amount")))
                for d in det)
            if float(getattr(sale, "change_amount", 0) or 0) > 0:
                cash_lines += _row("Vuelto", _crc(sale.change_amount))
        except Exception:
            cash_lines = ""
    elif method == "efectivo" and float(getattr(sale, "cash_received", 0) or 0) > 0:
        cash_lines = _row("Efectivo recibido", _crc(sale.cash_received)) \
            + _row("Vuelto", _crc(sale.change_amount))
    elif method in ("tarjeta", "sinpe") and float(getattr(sale, "cash_received", 0) or 0) > 0:
        cash_lines = _row(f"Pago con {method.title()}", _crc(sale.cash_received))

    clave_html = ""
    if not is_simplified:
        clave = getattr(sale, "hacienda_key", "") or ""
        if clave:
            clave_html = f'<p class="mono">Clave Hacienda: {clave}</p>'

    nombre_cliente = cliente_nombre or (getattr(sale, "client_name", "") or "Consumidor Final")

    client_section = ""
    if not is_simplified:
        client_section = (
            '<table class="caja">'
            f'  <tr><td><b>Cliente:</b> {_html_escape(nombre_cliente)}</td></tr>'
            '</table>'
        )

    subtotal_val = float(getattr(sale, "subtotal", 0) or 0)
    tax_val = float(getattr(sale, "tax_amount", 0) or 0)
    if is_simplified:
        tax_val = 0.0

    tax_line = ""
    if is_simplified:
        tax_line = _row("Exento de IVA", "")
    else:
        tax_line = _row("Impuesto", format_currency(tax_val))

    return f"""<html>
<head><style>
  body {{ font-family: 'Segoe UI', Arial, sans-serif; font-size: 10pt; color: #111; }}
  .caja {{ border: 1px solid #4b5563; border-collapse: collapse; width: 100%; margin-bottom: 8px; }}
  .caja td {{ padding: 4px 8px; }}
  .titulo {{ background-color: #1f2937; color: #ffffff; font-size: 13pt; font-weight: bold;
             text-align: center; padding: 6px 8px; }}
  table.detalle {{ border-collapse: collapse; width: 100%; margin: 6px 0; }}
  table.detalle th {{ background-color: #e5e7eb; border: 1px solid #9ca3af;
                       padding: 4px 6px; text-align: center; }}
  table.detalle td {{ border: 1px solid #d1d5db; padding: 3px 6px; }}
  table.totales {{ width: 100%; border-collapse: collapse; }}
  table.totales td {{ padding: 2px 8px; }}
  .total {{ font-weight: bold; font-size: 12pt; }}
  .mono {{ font-family: Consolas, monospace; font-size: 8pt; word-break: break-all; }}
  .pie {{ font-size: 8pt; color: #6b7280; margin-top: 6px; }}
</style></head><body>

<table class="caja">
  <tr><td colspan="2" class="titulo">{title}</td></tr>
  <tr>
    <td style="width:60%">
      <b>{_html_escape(company.get("company_name", "POS La Loma"))}</b><br>
      {_html_escape(company.get("address", ""))}<br>
      {_html_escape(company.get("phone", ""))} · Cédula {_html_escape(company.get("company_id", ""))}
      <br>{_html_escape(company.get("activity_code", ""))}
    </td>
    <td style="text-align:right; vertical-align:top">
      Factura <b>{_html_escape(getattr(sale, 'invoice_number', '') or '')}</b><br>
      {_fecha_corta(getattr(sale, 'created_at', ''))}<br>
      Caja: {_html_escape(getattr(sale, 'station', '') or '')}<br>
      Cajero: {_html_escape(getattr(sale, 'user_name', '') or '')}
    </td>
  </tr>
</table>

{client_section}

<table class="detalle">
  <tr><th>Can.</th><th style="text-align:left">Descripción</th><th>P. Unit.</th><th>Desc.</th><th>Total</th></tr>
  {rows}
</table>

<table class="totales">
  {_row("Subtotal", format_currency(subtotal_val))}
  {discount_line}
  {tax_line}
  <tr><td class="total">TOTAL</td><td class="total" align="right">{format_currency(float(sale.total))}</td></tr>
  {_row("Método de pago", _html_escape(str(getattr(sale, "payment_method", "") or "")))}
  {cash_lines}
</table>

{clave_html}
<p class="pie">Documento de respaldo generado por POS La Loma — guarda copias físicas y digitales.
{"Régimen de Tributación Simplificada — no genera crédito fiscal de IVA" if is_simplified else "Hacienda: " + ("ACEPTADA" if (getattr(sale, 'hacienda_status', '') or '') == 'ACEPTADA' else "ENVIADA")}</p>

</body></html>"""


def _row(label: str, value: str) -> str:
    return f'<tr><td>{label}</td><td align="right">{value}</td></tr>'


def _fnum(value) -> str:
    try:
        num = float(value or 0)
    except (TypeError, ValueError):
        return "0"
    if num == int(num):
        return str(int(num))
    return f"{num:.2f}".rstrip("0").rstrip(".")


def _html_escape(value) -> str:
    if value is None:
        return ""
    text = str(value)
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                 .replace('"', "&quot;"))


def _documento(html: str) -> QTextDocument:
    doc = QTextDocument()
    doc.setHtml(html)
    return doc


def guardar_pdf(carpeta: Path, nombre: str, html: str) -> Path | None:
    """Genera el PDF de la factura dentro de la carpeta mensual."""
    destino = carpeta / f"{nombre}.pdf"
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(str(destino))
    printer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    printer.setPageMargins(QMarginsF(12, 12, 12, 12), QPageLayout.Unit.Millimeter)
    _documento(html).print(printer)
    return destino if destino.exists() else None


def imprimir_factura(html: str) -> bool:
    """Imprime la factura en la impresora por defecto. True si se imprimió.

    Si la impresora por defecto es un PDF (Microsoft Print to PDF), no abre
    diálogo y devuelve False para que el caller use el PDF ya guardado.
    """
    printer_name = QPrinterInfo.defaultPrinterName()
    if not printer_name:
        return False
    lower = printer_name.lower()
    if "pdf" in lower or "xps" in lower:
        return False
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setPrinterName(printer_name)
    _documento(html).print(printer)
    return True