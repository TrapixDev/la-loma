"""Nota de crédito imprimible: HTML -> PDF (Qt) y copia física."""

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


def nota_credito_html(sale, company: dict, nota: dict | None = None,
                      cliente_nombre: str = "") -> str:
    """HTML de la nota de crédito a partir de la venta original y la nota."""
    items = sale.items or []
    nota = nota or {}
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

    clave_html = ""
    ref_clave = nota.get("referencia_clave") or getattr(sale, "hacienda_key", "") or ""
    if ref_clave:
        clave_html = f'<p class="mono">Clave factura original: {ref_clave}</p>'

    nota_clave = nota.get("hacienda_key") or ""
    nota_num = nota.get("invoice_number") or ""
    razon = nota.get("razon") or nota.get("motivo") or ""
    nombre_cliente = cliente_nombre or (getattr(sale, "client_name", "") or "Consumidor Final")

    return f"""<html>
<head><style>
  body {{ font-family: 'Segoe UI', Arial, sans-serif; font-size: 10pt; color: #111; }}
  .caja {{ border: 1px solid #4b5563; border-collapse: collapse; width: 100%; margin-bottom: 8px; }}
  .caja td {{ padding: 4px 8px; }}
  .titulo {{ background-color: #7f1d1d; color: #ffffff; font-size: 13pt; font-weight: bold;
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
  .razon {{ background-color: #fef2f2; border: 1px solid #fecaca; padding: 6px 8px;
            font-size: 10pt; margin-bottom: 8px; }}
</style></head><body>

<table class="caja">
  <tr><td colspan="2" class="titulo">NOTA DE CRÉDITO ELECTRÓNICA</td></tr>
  <tr>
    <td style="width:60%">
      <b>{_html_escape(company.get("company_name", "POS La Loma"))}</b><br>
      {_html_escape(company.get("address", ""))}<br>
      {_html_escape(company.get("phone", ""))} · Cédula {_html_escape(company.get("company_id", ""))}
      <br>{_html_escape(company.get("activity_code", ""))}
    </td>
    <td style="text-align:right; vertical-align:top">
      Nota de crédito <b>{_html_escape(nota_num)}</b><br>
      {_fecha_corta(nota.get("created_at") or getattr(sale, 'created_at', ''))}<br>
      Factura original: <b>{_html_escape(getattr(sale, 'invoice_number', '') or '')}</b><br>
      Caja: {_html_escape(getattr(sale, 'station', '') or '')}
    </td>
  </tr>
</table>

<table class="caja">
  <tr><td><b>Cliente:</b> {_html_escape(nombre_cliente)}</td></tr>
</table>

<div class="razon">
  <b>Motivo:</b> {_html_escape(razon)}
</div>

<table class="detalle">
  <tr><th>Can.</th><th style="text-align:left">Descripción</th><th>P. Unit.</th><th>Desc.</th><th>Total</th></tr>
  {rows}
</table>

<table class="totales">
  {_row("Subtotal", format_currency(float(getattr(sale, "subtotal", 0) or 0)))}
  {discount_line}
  {_row("Impuesto", format_currency(float(getattr(sale, "tax_amount", 0) or 0)))}
  <tr><td class="total">TOTAL ACREDITAR</td><td class="total" align="right">{format_currency(float(nota.get("total") or getattr(sale, "total", 0) or 0))}</td></tr>
</table>

{clave_html}
<p class="pie">Nota de crédito electrónica generada por POS La Loma.
Referencia: {_html_escape(getattr(sale, 'invoice_number', '') or '')}. {_html_escape(str(getattr(sale, 'hacienda_status', '') or ''))}</p>

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
    """Genera el PDF de la nota de crédito dentro de la carpeta mensual."""
    destino = carpeta / f"{nombre}.pdf"
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(str(destino))
    printer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    printer.setPageMargins(QMarginsF(12, 12, 12, 12), QPageLayout.Unit.Millimeter)
    _documento(html).print(printer)
    return destino if destino.exists() else None


def imprimir_nota_credito(html: str) -> bool:
    """Imprime en la impresora por defecto. True si se imprimió (no PDF)."""
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