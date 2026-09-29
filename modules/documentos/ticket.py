"""Ticket térmico 80mm: HTML compacto y envío a la impresora térmica.

Usa el driver de Windows de la impresora (Epson, Star, etc.) vía QPrinter
con página de 80mm y alto calculado según el contenido, para no desperdiciar
papel y cortar justo después del ticket.
"""

import base64
import json as _json
from datetime import datetime
from pathlib import Path
from typing import NamedTuple

from PyQt6.QtCore import QMarginsF, QSizeF
from PyQt6.QtGui import QPageLayout, QPageSize, QPainter, QTextDocument
from PyQt6.QtPrintSupport import QPrinter, QPrinterInfo

from config import Config
from utils.helpers import format_currency, monto_en_letras

_TICKET_WIDTH_MM = 80.0
_MARGIN_MM = 3.0
# Ajustes de impresión editables desde el editor o el visor y guardados en BD.
# La letra base del ticket: 13 pt en la térmica de 203 dpi se lee bien y los
# textos pequeños ya no quedan diminutos.
DEFAULT_FONT_PT = 13.0
DEFAULT_LINE_SPACING = 1.35
SCALE_FIT = "ajustar"
SCALE_REAL = "real"
SCALE_MODES = {
    SCALE_FIT: "Ajustar al papel",
    SCALE_REAL: "Tamaño real (sin reducir)",
}

TICKET_FORMAT_DEFAULTS = {
    "show_logo": True,
    "show_company_name": True,
    "show_company_id": True,
    "show_address": True,
    "show_phone": True,
    "show_email": True,
    "show_activity": True,
    "show_customer": True,
    "show_hacienda_key": True,
    "show_transfer_details": True,
    "show_payments": True,
    "show_amount_words": True,
    "show_equivalent_crc": True,
    "show_status": True,
    "show_thank_you": True,
    "logo_width_px": 128,
    "thank_you_text": "GRACIAS POR SU PREFERENCIA",
    "footer_text": "",
}

_FORMAT_BOOLEAN_KEYS = tuple(
    key for key, value in TICKET_FORMAT_DEFAULTS.items()
    if isinstance(value, bool))


def normalizar_formato_ticket(formato: dict | None = None) -> dict:
    """Completa y valida las opciones guardadas para el diseño del tiquete."""
    valores = dict(TICKET_FORMAT_DEFAULTS)
    if not isinstance(formato, dict):
        return valores

    for key in _FORMAT_BOOLEAN_KEYS:
        if key not in formato:
            continue
        value = formato[key]
        if isinstance(value, bool):
            valores[key] = value
        elif isinstance(value, (int, float)):
            valores[key] = value != 0
        elif isinstance(value, str):
            text = value.strip().lower()
            if text in {"1", "true", "yes", "si", "sí", "on"}:
                valores[key] = True
            elif text in {"0", "false", "no", "off", ""}:
                valores[key] = False

    try:
        valores["logo_width_px"] = max(
            48, min(240, int(round(float(formato.get("logo_width_px", 128))))))
    except (TypeError, ValueError, OverflowError):
        pass

    for key, limite in (("thank_you_text", 100), ("footer_text", 160)):
        value = formato.get(key, valores[key])
        valores[key] = str(value or "").strip()[:limite]
    return valores


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

def _logo_data_uri(ruta: str) -> str:
    """Convierte el logo a data URI para incrustarlo en el HTML del ticket.

    Solo acepta imágenes locales, con un tamaño acotado y contenido real de
    imagen: la ruta viene de configuración y no debe permitir leer ni emitir
    cualquier archivo del equipo (ni rutas de red).
    """
    try:
        from utils.archivos import ruta_logo_segura

        path = ruta_logo_segura(ruta)
        if path is None:
            return ""
        datos = base64.b64encode(path.read_bytes()).decode("ascii")
        sufijo = path.suffix.lower().lstrip(".")
        tipo = "jpeg" if sufijo in ("jpg", "jpeg") else sufijo
        return f"data:image/{tipo};base64,{datos}"
    except Exception:
        return ""


def _pagos_ticket(sale, moneda) -> list[tuple[str, str]]:
    """Pares (etiqueta, monto) de las líneas de pago del ticket."""
    method = str(getattr(sale, "payment_method", "") or "").lower()
    total = float(getattr(sale, "total", 0) or 0)
    cambio = float(getattr(sale, "change_amount", 0) or 0)
    recibido = float(getattr(sale, "cash_received", 0) or 0)
    filas: list[tuple[str, str]] = []
    if method == "mixto":
        details_raw = getattr(sale, "payment_details", "") or ""
        try:
            for detalle in _json.loads(details_raw) if details_raw.startswith("[") else []:
                nombre = str(detalle.get("method", "") or "Pago").upper()
                filas.append((f"PAGA CON {nombre}", moneda(detalle.get("amount"))))
        except Exception:
            pass
        if cambio > 0:
            filas.append(("VUELTO", moneda(cambio)))
    elif method == "efectivo":
        filas.append(("PAGA CON EFECTIVO", moneda(recibido or total)))
        if cambio > 0:
            filas.append(("VUELTO", moneda(cambio)))
    elif method in ("tarjeta", "sinpe"):
        filas.append((f"PAGA CON {method.upper()}", moneda(recibido or total)))
    elif method == "credito":
        filas.append(("VENTA A CRÉDITO", moneda(total)))
    return filas


def ticket_html(sale, company: dict, es_reimpresion: bool = False,
                font_pt: float = DEFAULT_FONT_PT,
                line_spacing: float = DEFAULT_LINE_SPACING,
                formato: dict | None = None) -> str:
    """HTML legible del tiquete térmico para una venta guardada.

    Los productos se presentan en bloques de dos líneas en lugar de cuatro
    columnas estrechas, que se pegaban entre sí en algunos drivers de 80 mm.
    """
    company = company or {}
    opciones = normalizar_formato_ticket(formato)
    items = sale.items or []
    currency = str(getattr(sale, "currency", "CRC") or "CRC")
    rate = float(getattr(sale, "exchange_rate", 0) or 0)
    # Los montos de la venta se guardan en CRC; el ticket los muestra en la
    # moneda en que se cobró (los detalles de pago ya vienen en esa moneda).
    factor = (1.0 / rate) if currency == "USD" and rate > 0 else 1.0

    def moneda(valor: float) -> str:
        return format_currency(float(valor or 0) * factor, currency)

    def fila_total(etiqueta: str, valor: str,
                   clase_etiqueta: str = "et") -> str:
        """Fila de totales con anchos en atributos: Qt ignora los width en CSS
        y las columnas se pegaban (label y monto sin separación)."""
        return (f'<tr><td class="{clase_etiqueta}" width="52%">{etiqueta}</td>'
                f'<td class="rtot" width="48%" align="right">{valor}</td></tr>')

    is_simplified = getattr(sale, "invoice_type", "general") == "simplificada"
    es_credito = str(getattr(sale, "payment_method", "") or "").lower() == "credito"
    condicion = "CRÉDITO" if es_credito else "CONTADO"
    if is_simplified:
        title = f"TIQUETE ELECTRÓNICO {condicion}"
    elif getattr(sale, "electronic_invoice", False):
        title = f"FACTURA ELECTRÓNICA {condicion}"
    else:
        title = f"FACTURA {condicion}"

    filas = []
    for item in items:
        cantidad = _fnum(item.quantity)
        precio = moneda(item.unit_price)
        descripcion = _html_escape(item.product_name or "Artículo")
        filas.append(
            '<div class="item">'
            f'<div class="item-name">{descripcion}</div>'
            '<table class="item-meta" width="100%"><tr>'
            f'<td class="item-unit" width="64%">{cantidad} × {precio}</td>'
            f'<td class="item-total" width="36%" align="right">'
            f'{moneda(item.total or 0)}</td>'
            '</tr></table></div>'
        )
    rows = "\n".join(filas)

    descuento_total = float(getattr(sale, "discount", 0) or 0)
    discount_line = ""
    if descuento_total > 0:
        discount_line = fila_total("DESCUENTO", moneda(descuento_total))

    subtotal_val = float(getattr(sale, "subtotal", 0) or 0)
    tax_val = float(getattr(sale, "tax_amount", 0) or 0)
    if is_simplified:
        tax_val = 0.0

    impuesto_label = "EXENTO DE IVA" if is_simplified else "IMPUESTOS/IVA"
    impuesto_valor = "" if is_simplified else moneda(tax_val)

    equiv_line = ""
    if (opciones["show_equivalent_crc"] and currency == "USD" and rate > 0
            and Config.MOSTRAR_EQUIVALENTE_CRC):
        equiv_line = fila_total(
            f"{currency} · Equivalente CRC",
            format_currency(float(sale.total), "CRC"))

    pago_rows = ""
    if opciones["show_payments"]:
        pago_rows = "".join(
            fila_total(_html_escape(etiqueta), monto)
            for etiqueta, monto in _pagos_ticket(sale, moneda))

    son_line = ""
    if opciones["show_amount_words"]:
        son_line = (f'<div class="mini wrap son"><b>SON:</b> '
                    f'{_html_escape(monto_en_letras(float(sale.total) * factor, currency))}'
                    f'</div>')

    nombre_cliente = getattr(sale, "client_name", "") or "Consumidor Final"
    cliente_html = ""
    if opciones["show_customer"]:
        if is_simplified:
            nombre_cliente = "Cliente General"
        cliente_html = (
            '<div class="cliente"><b>CLIENTE</b><br>'
            f'{_html_escape(nombre_cliente)}</div>')

    clave_html = ""
    if opciones["show_hacienda_key"] and not is_simplified:
        clave = str(getattr(sale, "hacienda_key", "") or "")
        if clave:
            clave_html = f'<div class="clave"><b>CLAVE:</b> {_html_escape(clave)}</div>'

    logo_uri = _logo_data_uri(company.get("logo", "")) if opciones["show_logo"] else ""
    logo_html = (
        f'<div class="centro logo"><img src="{logo_uri}" '
        f'width="{opciones["logo_width_px"]}"></div>' if logo_uri else "")

    empresa_lineas = []
    if opciones["show_address"] and company.get("address"):
        empresa_lineas.append(_html_escape(company.get("address", "")))
    contacto = []
    if opciones["show_phone"] and company.get("phone"):
        contacto.append(f'Tel: {_html_escape(company.get("phone", ""))}')
    if opciones["show_email"] and company.get("email"):
        contacto.append(_html_escape(company.get("email", "")))
    if contacto:
        empresa_lineas.append(" · ".join(contacto))
    if opciones["show_company_id"] and company.get("company_id"):
        empresa_lineas.append(f'Céd. jurídica: {_html_escape(company.get("company_id", ""))}')
    if opciones["show_activity"] and company.get("activity_code"):
        empresa_lineas.append(
            f'Actividad económica: {_html_escape(company.get("activity_code", ""))}')
    nombre_empresa = ""
    if opciones["show_company_name"]:
        nombre_empresa = _html_escape(company.get("company_name") or "POS La Loma")
    empresa_html = "".join(
        f'<div class="centro mini empresa-linea">{linea}</div>'
        for linea in empresa_lineas)

    def dato_html(etiqueta: str, valor: str) -> str:
        valor = str(valor or "").strip()
        if not valor:
            return ""
        return (f'<tr><td class="dato-label" width="32%">{etiqueta}</td>'
                f'<td class="dato-value" width="68%">{_html_escape(valor)}</td></tr>')

    datos_html = "".join((
        dato_html("Factura", getattr(sale, "invoice_number", "")),
        dato_html("Fecha", _fecha_corta(getattr(sale, "created_at", ""))),
        dato_html("Caja", getattr(sale, "station", "")),
        dato_html("Cajero", getattr(sale, "user_name", "")),
    ))

    banco_html = ""
    if opciones["show_transfer_details"] and (company.get("iban") or company.get("sinpe")):
        filas_banco = ['<div class="centro mini negrita">PARA TRANSFERENCIA O DEPÓSITO:</div>']
        if company.get("iban"):
            filas_banco.append(
                f'<div class="centro mini">IBAN: {_html_escape(company.get("iban", ""))}</div>')
        if company.get("sinpe"):
            filas_banco.append(
                f'<div class="centro mini">SINPE MÓVIL: '
                f'{_html_escape(company.get("sinpe", ""))}</div>')
        banco_html = "".join(filas_banco)

    estado_html = ""
    if opciones["show_status"]:
        if is_simplified:
            estado_html = (
                "Régimen de Tributación Simplificada — "
                "sin crédito fiscal de IVA")
        else:
            estado = str(getattr(sale, "hacienda_status", "") or "").upper() or "ENVIADA"
            estado_html = f"Comprobante electrónico: {estado}"

    reimpresion_html = ('<div class="centro negrita">*** REIMPRESIÓN ***</div>'
                        if es_reimpresion else "")

    gracias_html = ""
    if opciones["show_thank_you"] and opciones["thank_you_text"]:
        gracias_html = (
            f'<div class="centro negrita gracias">'
            f'{_html_escape(opciones["thank_you_text"])}</div>')
    pie_personalizado = _html_escape(opciones["footer_text"]).replace("\n", "<br>")
    pie_html = f'<div class="centro mini pie">{pie_personalizado}</div>' if pie_personalizado else ""

    base = max(6.0, min(20.0, float(font_pt or DEFAULT_FONT_PT)))
    espaciado = max(1.0, min(2.0, float(line_spacing or DEFAULT_LINE_SPACING)))
    return f"""<html><head><style>
body {{ font-family: Arial, 'Segoe UI', sans-serif; font-size: {base:.1f}pt; color: #000; margin: 0; }}
div {{ line-height: {espaciado:.2f}; }}
.centro {{ text-align: center; }}
.nombre {{ font-weight: bold; font-size: {base + 2.5:.1f}pt; margin-bottom: 2px; }}
.mini {{ font-size: {base:.1f}pt; }}
.negrita {{ font-weight: bold; }}
.wrap {{ word-wrap: break-word; }}
.logo {{ margin-bottom: 3px; }}
.empresa-linea {{ margin: 1px 0; }}
.linea {{ border-top: 1px dashed #555; margin: 5px 0; }}
.titulo {{ font-weight: bold; font-size: {base + 1.5:.1f}pt; text-align: center; margin: 4px 0; }}
table {{ width: 100%; border-collapse: collapse; }}
td {{ padding: 1px 0; vertical-align: top; }}
table.datos td {{ padding: 1px 0; }}
.dato-label {{ font-weight: bold; font-size: {base + 0.5:.1f}pt; }}
.dato-value {{ word-wrap: break-word; }}
.cliente {{ border-top: 1px solid #888; border-bottom: 1px solid #888; padding: 4px 0; margin: 4px 0; }}
.clave {{ font-size: {base - 1:.1f}pt; word-wrap: break-word; margin: 3px 0; }}
.section-title {{ font-weight: bold; font-size: {base + 0.5:.1f}pt; margin: 4px 0 2px; }}
.item-header td {{ border-top: 1px solid #555; border-bottom: 1px solid #555; padding: 3px 0; font-size: {base - 1:.1f}pt; font-weight: bold; }}
.item {{ border-bottom: 1px dotted #999; padding: 3px 0; }}
.item-name {{ font-weight: bold; font-size: {base + 0.5:.1f}pt; word-wrap: break-word; }}
.item-meta td {{ padding: 1px 0; font-size: {base:.1f}pt; }}
.item-unit {{ word-wrap: break-word; }}
td.item-total {{ text-align: right; white-space: nowrap; font-weight: bold; font-size: {base + 0.5:.1f}pt; }}
table.totales {{ margin-top: 3px; }}
table.totales td {{ padding: 2px 0; }}
.rtot {{ text-align: right; white-space: nowrap; font-size: {base:.1f}pt; }}
.et {{ font-weight: bold; font-size: {base + 0.5:.1f}pt; }}
.total td {{ border-top: 1px solid #555; padding-top: 4px; font-weight: bold; font-size: {base + 1:.1f}pt; }}
.son {{ margin: 4px 0; }}
.gracias {{ margin: 5px 0 3px; }}
.pie {{ margin-top: 2px; }}
</style></head><body>
{logo_html}
{f'<div class="centro nombre">{nombre_empresa}</div>' if nombre_empresa else ''}
{empresa_html}
<div class="linea"></div>
<div class="titulo">{title}</div>
<table class="datos" width="100%">{datos_html}</table>
{clave_html}
{cliente_html}
<div class="section-title">DETALLE</div>
<table class="item-header" width="100%"><tr><td class="item-unit-label" width="64%">CANT. × PRECIO</td><td class="item-total-label" width="36%" align="right">IMPORTE</td></tr></table>
<div class="items">{rows}</div>
<table class="totales" width="100%">
<tr><td class="et" width="52%">SUBTOTAL</td><td class="rtot" width="48%" align="right">{moneda(subtotal_val)}</td></tr>
{discount_line}
<tr><td class="et" width="52%">{impuesto_label}</td><td class="rtot" width="48%" align="right">{impuesto_valor}</td></tr>
<tr class="total"><td width="52%">MONTO TOTAL</td><td class="rtot" width="48%" align="right">{moneda(float(sale.total))}</td></tr>
{equiv_line}
{pago_rows}
</table>
{son_line}
<div class="linea"></div>
{gracias_html}
{banco_html}
{f'<div class="centro mini">{_html_escape(estado_html)}</div>' if estado_html else ''}
{pie_html}
{reimpresion_html}
</body></html>"""


def ticket_prueba_html(extra: str = "", font_pt: float = DEFAULT_FONT_PT,
                       line_spacing: float = DEFAULT_LINE_SPACING) -> str:
    """Ticket de prueba para verificar la impresora (con datos de soporte)."""
    extra_html = (f'<div class="centro mini">{_html_escape(extra)}</div>'
                  if extra else "")
    base = max(6.0, min(20.0, float(font_pt or DEFAULT_FONT_PT)))
    espaciado = max(1.0, min(2.0, float(line_spacing or DEFAULT_LINE_SPACING)))
    return f"""<html><head><style>
body {{ font-family: 'Courier New', monospace; font-size: {base:.1f}pt; color: #000; }}
div {{ line-height: {espaciado:.2f}; }}
.centro {{ text-align: center; }}
.mini {{ font-size: {base - 1:.1f}pt; color: #333; }}
.linea {{ border-top: 1px dashed #000; margin: 3px 0; }}
</style></head><body>
<div class="centro"><b>PRUEBA DE IMPRESORA</b></div>
<div class="centro">POS La Loma</div>
<div class="linea"></div>
<div>Si puede leer este ticket, la impresora</div>
<div>esta configurada correctamente.</div>
<div class="linea"></div>
<div class="centro">Gracias</div>
""" + extra_html + """
</body></html>"""


# ---------- impresión ----------

PAPER_WINDOWS = "windows"
PAPER_LABEL = "etiqueta"
PAPER_MODES = {
    PAPER_WINDOWS: "Papel configurado en Windows",
    PAPER_LABEL: "Etiqueta (una por ticket)",
}
# Reducción mínima aceptable cuando el ticket no cabe en la página.
_ESCALA_MINIMA = 0.6


def elegir_papel(soportadas: list[tuple[str, float, float]], modo: str,
                 ancho_mm: float = _TICKET_WIDTH_MM) -> tuple[str, float, float] | None:
    """Elige (nombre, ancho, alto) del papel según el modo.

    `soportadas` es una lista de (nombre, ancho_mm, alto_mm) del driver.
    - etiqueta: la de ancho ~80mm más parecida (la etiqueta estándar).
    - windows: None (se respeta el papel que ya tiene el driver).
    """
    if not soportadas:
        return None
    validas = [p for p in soportadas
               if str(p[0] or "").strip() and p[1] > 0 and p[2] > 0]
    if not validas:
        return None
    candidatas = [p for p in validas if abs(p[1] - ancho_mm) <= 5]
    if not candidatas:
        candidatas = validas
    if modo == PAPER_LABEL:
        return min(candidatas, key=lambda p: (abs(p[1] - ancho_mm), p[2]))
    return None


def _documento(html: str) -> QTextDocument:
    doc = QTextDocument()
    doc.setHtml(html)
    return doc


def _medir_alto(html: str, width_mm: float = _TICKET_WIDTH_MM,
                margin_mm: float = _MARGIN_MM) -> float:
    """Estima el alto (mm) del ticket según su contenido."""
    try:
        mm_to_px = 96.0 / 25.4
        ancho = max(20.0, float(width_mm or _TICKET_WIDTH_MM))
        margen = max(0.0, float(margin_mm if margin_mm is not None else _MARGIN_MM))
        width_px = max(1.0, (ancho - 2 * margen) * mm_to_px)
        doc = _documento(html)
        doc.setPageSize(QSizeF(width_px, 100000.0))
        alto_mm = (doc.size().height() / mm_to_px) + 2 * margen
        return min(max(alto_mm, 30.0), 1000.0)
    except Exception:
        return 297.0


class GeometriaTicket(NamedTuple):
    """Geometría del ticket en milímetros.

    La comparten el visor y la impresora para que la pantalla y el papel
    coincidan: mismo ancho útil, mismos márgenes y desplazamiento.
    """

    contenido_mm: float        # ancho útil del texto
    visor_mm: float            # ancho de la tira que muestra el visor
    visor_izq_mm: float        # margen izquierdo dentro de la tira del visor
    dispositivo_mm: float      # ancho del área de dibujo del QPrinter
    dispositivo_alto_mm: float  # alto del área de dibujo del QPrinter
    visor_arriba_mm: float = _MARGIN_MM   # margen superior de la tira
    visor_abajo_mm: float = _MARGIN_MM    # margen inferior de la tira


def _desplazamiento(valor, maximo: float = 8.0) -> float:
    """Normaliza un desplazamiento en mm (-maximo..maximo)."""
    try:
        numero = float(valor or 0)
    except (TypeError, ValueError):
        return 0.0
    return max(-maximo, min(maximo, numero))


def geometria_ticket(printer: QPrinter | None,
                     width_mm: float = _TICKET_WIDTH_MM,
                     margin_mm: float = _MARGIN_MM,
                     offset_x_mm: float = 0.0,
                     offset_y_mm: float = 0.0) -> GeometriaTicket:
    """Calcula el ancho útil real según el papel y los márgenes del driver.

    Con QPrinter el área de dibujo ya descuenta los márgenes configurados,
    así que el contenido se limita al ancho pedido y se centra dentro de esa
    área (nunca se estira al ancho completo del papel). El desplazamiento
    mueve el contenido dentro de la tira del visor y del papel.
    """
    ancho = max(20.0, float(width_mm or _TICKET_WIDTH_MM))
    margen = max(0.0, float(margin_mm if margin_mm is not None else _MARGIN_MM))
    offset_x = _desplazamiento(offset_x_mm)
    offset_y = _desplazamiento(offset_y_mm)
    dispositivo_mm = ancho
    dispositivo_alto_mm = 297.0
    if printer is not None:
        try:
            res = float(printer.resolution()) or 96.0
            ancho_dev = float(printer.width()) * 25.4 / res
            alto_dev = float(printer.height()) * 25.4 / res
            if ancho_dev > 0:
                dispositivo_mm = ancho_dev
            if alto_dev > 0:
                dispositivo_alto_mm = alto_dev
        except Exception:
            pass
    contenido = min(max(1.0, ancho - 2 * margen), dispositivo_mm)
    contenido = max(contenido, min(20.0, dispositivo_mm))
    izq = min(max(0.0, margen + offset_x), ancho)
    der = max(0.0, margen - offset_x)
    visor = min(ancho, izq + contenido + der)
    arriba = max(0.0, margen + offset_y)
    abajo = max(0.0, margen - offset_y)
    return GeometriaTicket(contenido, visor, izq, dispositivo_mm,
                           dispositivo_alto_mm, arriba, abajo)


def dpi_para_impresion(printer: QPrinter | None,
                       maximo: int = 300) -> int:
    """Resolución (dpi) para renderizar el ticket como el papel.

    Se usa la del driver para que el visor y el papel se dibujen con la misma
    métrica de fuente; se limita para no gastar memoria en drivers de 1200 dpi.
    """
    if printer is None:
        return 150
    try:
        res = int(round(float(printer.resolution())))
    except Exception:
        res = 150
    return max(96, min(res, int(maximo)))


def resolver_impresora(printer_name: str = "") -> str:
    """Devuelve el nombre real de la impresora en Windows.

    Acepta el nombre exacto, sin distinguir mayúsculas, o una coincidencia
    parcial (el driver a veces aparece con "(Copiar 1)"); si no encuentra nada,
    usa la predeterminada.
    """
    try:
        disponibles = [p.printerName() for p in QPrinterInfo.availablePrinters()]
    except Exception:
        disponibles = []
    if not disponibles:
        return printer_name or ""
    if printer_name:
        if printer_name in disponibles:
            return printer_name
        buscado = printer_name.strip().lower()
        for nombre in disponibles:
            if nombre.lower() == buscado:
                return nombre
        for nombre in disponibles:
            if buscado and buscado in nombre.lower():
                return nombre
    try:
        predeterminada = QPrinterInfo.defaultPrinterName()
    except Exception:
        predeterminada = ""
    if predeterminada:
        return predeterminada
    return disponibles[0]


def tamanos_soportados(printer_name: str) -> list[tuple[str, float, float]]:
    """Tamaños de papel válidos que el driver reporta (nombre, ancho, alto mm).

    OJO: en Qt6 la lista la da QPrinterInfo (QPrinter ya no tiene
    supportedPageSizes); ese era el motivo de que el modo de papel no se
    aplicara y el ticket se paginara con el formulario corto del driver.
    Se descartan las entradas inválidas (nombre vacío o medidas <= 0).
    """
    if not printer_name:
        return []
    try:
        info = QPrinterInfo.printerInfo(printer_name)
        if info is None or info.isNull():
            return []
        tamanos: list[tuple[str, float, float]] = []
        for size in info.supportedPageSizes():
            mm = size.size(QPageSize.Unit.Millimeter)
            nombre = str(size.name() or "").strip()
            if not nombre or mm.width() <= 0 or mm.height() <= 0:
                continue
            tamanos.append((nombre, mm.width(), mm.height()))
        return tamanos
    except Exception:
        return []


def _tamano_que_mejor_encaja(soportadas: list[tuple[str, float, float]],
                             alto_contenido: float,
                             ancho_mm: float = _TICKET_WIDTH_MM) -> tuple[str, float, float] | None:
    """El tamaño de ~80mm más chico que alcance el ticket (o el mayor si ninguno)."""
    validas = [p for p in soportadas
               if str(p[0] or "").strip() and p[1] > 0 and p[2] > 0]
    candidatas = [p for p in validas if abs(p[1] - ancho_mm) <= 5]
    if not candidatas:
        candidatas = validas
    if not candidatas:
        return None
    alcanzan = [p for p in candidatas if p[2] + 1 >= alto_contenido]
    if alcanzan:
        return min(alcanzan, key=lambda p: p[2])
    return max(candidatas, key=lambda p: p[2])


def _es_impresora_pdf(name: str) -> bool:
    lower = (name or "").lower()
    return "pdf" in lower or "xps" in lower


def _es_impresora_prueba(name: str) -> bool:
    """True para la impresora virtual de pruebas (POS-Test)."""
    lower = (name or "").lower()
    return "pos-test" in lower or "pos_test" in lower or "prueba" in lower


def _impresora_prueba_instalada() -> str:
    """Nombre de la impresora virtual de pruebas si está instalada."""
    try:
        for info in QPrinterInfo.availablePrinters():
            if _es_impresora_prueba(info.printerName()):
                return info.printerName()
    except Exception:
        pass
    return ""


def _sera_impresora_prueba(printer_name: str = "") -> bool:
    """True si la salida terminará en una impresora virtual/PDF.

    La impresora de prueba (POS-Test) y el modo POS_PRINT_TEST guardan el
    ticket en un archivo con destino fijo; en esos casos no tiene sentido
    abrir el menú de impresión de Windows, que podría desviar la salida.
    """
    name = resolver_impresora(printer_name)
    if not name:
        return False
    if _es_impresora_prueba(name):
        return True
    if _es_impresora_pdf(name):
        return bool(Config.PRINT_TEST_MODE or _impresora_prueba_instalada())
    return False


_ULTIMA_SALIDA_PDF = ""


def ultima_salida_pdf() -> str:
    """Ruta del último PDF de prueba generado ("" si no hubo)."""
    return _ULTIMA_SALIDA_PDF


def _carpeta_pruebas() -> Path:
    """Carpeta visible para los PDF de prueba (Documentos\\PosLaLoma\\pruebas)."""
    if Config.PRINT_TEST_DIR:
        return Path(Config.PRINT_TEST_DIR)
    documentos = Path.home() / "Documents"
    if not documentos.is_dir():
        documentos = Path.home()
    return documentos / "PosLaLoma" / "pruebas"


def _destino_pdf_prueba() -> Path | None:
    """Archivo PDF de salida para impresoras virtuales/prueba."""
    try:
        if Config.PRINT_TEST_PDF:
            destino = Path(Config.PRINT_TEST_PDF)
            destino.parent.mkdir(parents=True, exist_ok=True)
            return destino
        carpeta = _carpeta_pruebas()
        carpeta.mkdir(parents=True, exist_ok=True)
        return carpeta / f"ticket_{datetime.now():%Y%m%d_%H%M%S}.pdf"
    except Exception:
        return None


def _preparar_impresora(printer_name: str = "", modo: str = "",
                        html: str = "", copias: int = 1,
                        width_mm: float = _TICKET_WIDTH_MM,
                        margin_mm: float = _MARGIN_MM,
                        offset_x_mm: float = 0.0,
                        offset_y_mm: float = 0.0) -> QPrinter | None:
    """Crea el QPrinter usando SIEMPRE un tamaño soportado por el driver.

    Reglas:
    - etiqueta: se elige de la lista de tamaños del driver (nunca se inventa
      un tamaño, que era lo que hacía que Windows alimentara papel en blanco
      sin fin); el más chico que alcance.
    - windows: respeta el papel actual y, si es más corto que el ticket,
      salta al tamaño soportado que mejor encaje (aunque no alcance, se usa
      el mayor para no reducir de más la letra).
    - El alto nunca se inventa: si el ticket no cabe en la página, el pintado
      lo reduce para que entre en una sola página.
    - Con POS_PRINT_TEST=1 se permite imprimir a PDF (impresora virtual) para
      pruebas, guardando el archivo en POS_PRINT_TEST_PDF o en %TEMP%.
    """
    name = resolver_impresora(printer_name)
    if not name:
        return None
    global _ULTIMA_SALIDA_PDF
    _ULTIMA_SALIDA_PDF = ""
    es_pdf = _es_impresora_pdf(name)
    es_prueba = _es_impresora_prueba(name)
    if es_pdf and not (Config.PRINT_TEST_MODE or es_prueba):
        # La configurada/predeterminada es de PDF: si hay una impresora
        # virtual de pruebas, se usa para que el ticket salga como PDF visible.
        sustituta = _impresora_prueba_instalada()
        if sustituta:
            name = sustituta
            es_pdf = False
            es_prueba = True
        else:
            return None
    printer = None
    try:
        info = QPrinterInfo.printerInfo(name)
        if info is not None and not info.isNull():
            # El QPrinter debe nacer del QPrinterInfo de ESA impresora: al
            # usar setPrinterName el layout se queda con el papel del driver
            # predeterminado y el tamaño elegido no correspondía.
            printer = QPrinter(info, QPrinter.PrinterMode.HighResolution)
    except Exception:
        printer = None
    if printer is None:
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setPrinterName(name)
    if copias > 1:
        try:
            printer.setCopyCount(int(copias))
        except Exception:
            pass
    if es_pdf or es_prueba:
        # Impresora virtual: el PDF sale a un archivo visible (Documentos\
        # PosLaLoma\pruebas) para poder verlo/abrirlo después de imprimir.
        destino = _destino_pdf_prueba()
        if destino is not None:
            try:
                printer.setOutputFileName(str(destino))
                _ULTIMA_SALIDA_PDF = str(destino)
            except Exception:
                _ULTIMA_SALIDA_PDF = ""
    modo = modo if modo in PAPER_MODES else PAPER_WINDOWS

    actual = printer.pageLayout().pageSize()
    actual_mm = actual.size(QPageSize.Unit.Millimeter)
    alto_actual = actual_mm.height()
    aplicado = f"actual {actual_mm.width():.0f}x{alto_actual:.0f}mm"

    alto_contenido = _medir_alto(html, width_mm, margin_mm) if html else 0.0
    soportadas = tamanos_soportados(name)
    elegida = None
    if modo == PAPER_LABEL:
        elegida = _tamano_que_mejor_encaja(soportadas, alto_contenido, width_mm)
    elif modo == PAPER_WINDOWS and html and alto_actual + 1 < alto_contenido:
        # El papel del driver no alcanza (p. ej. etiqueta 80x15): se usa el
        # mayor tamaño de ~80mm que ofrezca el driver.
        elegida = _tamano_que_mejor_encaja(soportadas, alto_contenido, width_mm)
        if elegida is not None:
            aplicado += " (papel corto)"
    if elegida is not None:
        printer.setPageSize(QPageSize(
            QSizeF(elegida[1], elegida[2]), QPageSize.Unit.Millimeter,
            elegida[0], QPageSize.SizeMatchPolicy.ExactMatch))
        aplicado = (f"{elegida[0]} {elegida[1]:.0f}x{elegida[2]:.0f}mm"
                    + (" (el papel del driver era corto)"
                       if "papel corto" in aplicado else ""))

    margen = max(0.0, float(margin_mm if margin_mm is not None else _MARGIN_MM))
    # Los desplazamientos consumen el margen del lado hacia el que se mueve
    # el ticket: a la izquierda/arriba reducen el margen respectivo; a la
    # derecha/abajo hacen lo mismo con el otro lado.
    offset_x = _desplazamiento(offset_x_mm)
    offset_y = _desplazamiento(offset_y_mm)
    izquierda = max(0.0, margen + min(0.0, offset_x))
    derecha = max(0.0, margen - max(0.0, offset_x))
    arriba = max(0.0, margen + min(0.0, offset_y))
    abajo = max(0.0, margen - max(0.0, offset_y))
    printer.setPageMargins(
        QMarginsF(izquierda, arriba, derecha, abajo),
        QPageLayout.Unit.Millimeter)
    _log_impresora(name, actual_mm, modo, aplicado, soportadas)
    return printer


def _log_impresora(name: str, actual_mm, modo: str, aplicado: str,
                   soportadas: list[tuple[str, float, float]]) -> None:
    try:
        from utils.diagnostico import escribir_log

        lista = ", ".join(
            f"{n} {w:.0f}x{h:.0f}" for n, w, h in soportadas[:8])
        escribir_log(
            f"Impresora '{name}': papel actual {actual_mm.width():.0f}x"
            f"{actual_mm.height():.0f}mm; modo={modo}; usado={aplicado}; "
            f"soportados({len(soportadas)}): {lista or 'n/d'}")
    except Exception:
        pass


def escala_necesaria(printer: QPrinter, html: str,
                     width_mm: float = _TICKET_WIDTH_MM,
                     margin_mm: float = _MARGIN_MM,
                     offset_x_mm: float = 0.0,
                     offset_y_mm: float = 0.0) -> float:
    """Escala (<= 1.0) que necesita el ticket para caber en una página.

    Usa el mismo ancho útil que el visor y el pintado; si se midiera con el
    ancho completo del área imprimible la escala no correspondería.
    """
    try:
        res = float(printer.resolution()) or 96.0
        geo = geometria_ticket(printer, width_mm, margin_mm,
                               offset_x_mm, offset_y_mm)
        doc = _documento(html)
        doc.setTextWidth(max(1.0, geo.contenido_mm * res / 25.4))
        alto_doc = float(doc.size().height())
        alto_pagina = geo.dispositivo_alto_mm * res / 25.4
        if alto_doc <= 0 or alto_pagina <= 0 or alto_doc <= alto_pagina:
            return 1.0
        return max(_ESCALA_MINIMA, alto_pagina / alto_doc)
    except Exception:
        return 1.0


def _escala_para_caber(alto_pagina: float, alto_doc: float,
                       minimo: float = _ESCALA_MINIMA) -> float:
    """Escala pura (para tests): 1.0 si cabe, proporcional si no, con mínimo."""
    if alto_doc <= 0 or alto_pagina <= 0 or alto_doc <= alto_pagina:
        return 1.0
    return max(minimo, alto_pagina / alto_doc)


def _imprimir_una_pagina(html: str, printer: QPrinter,
                         reducir: bool = True,
                         width_mm: float = _TICKET_WIDTH_MM,
                         margin_mm: float = _MARGIN_MM,
                         offset_x_mm: float = 0.0,
                         offset_y_mm: float = 0.0) -> bool:
    """Dibuja el ticket en UNA sola página, igual que la vista previa.

    No usa QTextDocument.print() (que pagina el contenido y era el origen de
    las "13 páginas"): pinta el documento una vez, recortado al área de dibujo
    y reducido si no cabe (salvo que `reducir` sea False). Así nunca se emite
    más de una página ni papel en blanco sin fin.

    OJO: con QPrinter el origen del QPainter YA está en el borde del área
    imprimible (los márgenes configurados se descuentan solos), por lo que no
    se debe volver a trasladar por el margen: eso corría el ticket a la
    derecha y recortaba el lado derecho respecto del visor. Los desplazamientos
    mueven el contenido a izquierda/derecha y arriba/abajo: el margen del lado
    hacia el que se mueve se reduce en `_preparar_impresora` y aquí el
    contenido se ancla a ese lado.
    """
    try:
        res = float(printer.resolution()) or 96.0
        per_mm = res / 25.4
        dev_w = max(1, int(printer.width()))
        dev_h = max(1, int(printer.height()))
        geo = geometria_ticket(printer, width_mm, margin_mm,
                               offset_x_mm, offset_y_mm)
        contenido_px = max(1.0, geo.contenido_mm * per_mm)
        doc = _documento(html)
        doc.setTextWidth(contenido_px)
        alto_doc = float(doc.size().height())
        escala = (_escala_para_caber(float(dev_h), alto_doc)
                  if reducir else 1.0)
        offset_x = _desplazamiento(offset_x_mm)
        offset_y = _desplazamiento(offset_y_mm)
        painter = QPainter(printer)
        try:
            painter.setClipRect(0, 0, dev_w, dev_h)
            if offset_x < 0:
                # Se movió a la izquierda: el contenido arranca en el borde
                # del área de dibujo (el margen izquierdo ya se redujo).
                x = 0.0
            elif offset_x > 0:
                # Se movió a la derecha: anclado al borde derecho del área.
                x = max(0.0, dev_w - contenido_px * escala)
            else:
                # Centrado en el área de dibujo: en papel angosto (58 mm)
                # ocupa todo; en papel ancho (A4/Carta) queda centrado.
                x = max(0.0, (dev_w - contenido_px * escala) / 2.0)
            y = (offset_y * per_mm) if offset_y > 0 else 0.0
            painter.translate(x, y)
            if escala < 1.0:
                painter.scale(escala, escala)
            doc.drawContents(painter)
        finally:
            painter.end()
        if escala < 1.0:
            try:
                from utils.diagnostico import escribir_log
                escribir_log(
                    f"Ticket reducido al {escala * 100:.0f}% para que quepa "
                    f"en una sola página.")
            except Exception:
                pass
        return True
    except Exception:
        return False


def advertencia_papel(printer: QPrinter, html: str,
                      width_mm: float = _TICKET_WIDTH_MM,
                      margin_mm: float = _MARGIN_MM) -> str:
    """Aviso si el ticket no cabe en el papel y se va a reducir."""
    try:
        pagina = printer.pageLayout().pageSize().size(QPageSize.Unit.Millimeter)
        alto_contenido = _medir_alto(html, width_mm, margin_mm)
        if pagina.height() + 1 < alto_contenido:
            return (f"El papel elegido ({pagina.width():.0f}×"
                    f"{pagina.height():.0f} mm) es más corto que el ticket "
                    f"({alto_contenido:.0f} mm): se reducirá para que entre "
                    f"en una sola página. Para evitarlo use un papel más alto "
                    f"en el driver de la impresora.")
    except Exception:
        pass
    return ""


def imprimir_ticket(html: str, printer_name: str = "", modo_papel: str = "",
                    copias: int = 1, width_mm: float = _TICKET_WIDTH_MM,
                    margin_mm: float = _MARGIN_MM,
                    reducir: bool = True,
                    offset_x_mm: float = 0.0,
                    offset_y_mm: float = 0.0) -> bool:
    """Imprime el ticket en la impresora indicada (o la predeterminada).

    True si se envió a imprimir. False si no hay impresora válida o la
    seleccionada es un PDF/XPS (salvo en modo de prueba POS_PRINT_TEST=1).
    """
    printer = _preparar_impresora(printer_name, modo_papel, html, copias,
                                  width_mm, margin_mm, offset_x_mm, offset_y_mm)
    if printer is None:
        return False
    return _imprimir_una_pagina(html, printer, reducir, width_mm, margin_mm,
                                offset_x_mm, offset_y_mm)


def imprimir_ticket_con_dialogo(html: str, printer_name: str = "",
                                modo_papel: str = "", copias: int = 1,
                                width_mm: float = _TICKET_WIDTH_MM,
                                margin_mm: float = _MARGIN_MM,
                                reducir: bool = True,
                                offset_x_mm: float = 0.0,
                                offset_y_mm: float = 0.0) -> bool:
    """Imprime mostrando el menú de impresión de Windows (Imprimir/Cancelar).

    Devuelve False si el usuario cancela o no hay impresora válida.
    """
    from PyQt6.QtWidgets import QDialog, QPrintDialog

    printer = _preparar_impresora(printer_name, modo_papel, html, copias,
                                  width_mm, margin_mm, offset_x_mm, offset_y_mm)
    if printer is None:
        return False
    dialog = QPrintDialog(printer)
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return False
    return _imprimir_una_pagina(html, printer, reducir, width_mm, margin_mm,
                                offset_x_mm, offset_y_mm)


def previsualizar_ticket(html: str, printer_name: str = "",
                         modo_papel: str = "", parent=None, db=None,
                         html_factory=None,
                         ajustes: dict | None = None) -> bool:
    """Muestra el visor de vista previa estilo Chrome (editable).

    `html_factory(font_pt, line_spacing, extra)` reconstruye el HTML cuando el
    usuario cambia la letra o el interlineado. Devuelve False solo si no hay
    ninguna impresora válida para preparar.
    """
    from ui.ticket_preview import TicketPreviewDialog

    ajustes = ajustes or (get_ticket_settings(db) if db is not None else {})
    printer = _preparar_impresora(
        printer_name, modo_papel, html,
        width_mm=ajustes.get("width_mm", _TICKET_WIDTH_MM),
        margin_mm=ajustes.get("margin_mm", _MARGIN_MM),
        offset_x_mm=ajustes.get("offset_x_mm", 0.0),
        offset_y_mm=ajustes.get("offset_y_mm", 0.0))
    if printer is None:
        return False
    dialog = TicketPreviewDialog(html, printer_name, modo_papel, parent,
                                 db=db, html_factory=html_factory,
                                 ajustes=ajustes)
    dialog.exec()
    return True


def imprimir_ticket_venta(sale, company: dict, db=None,
                          printer_name: str = "",
                          es_reimpresion: bool = False) -> bool:
    """Genera e imprime el ticket de una venta en la impresora configurada.

    Si en Configuración se activó el diálogo de impresión, se muestra el menú
    (Imprimir/Cancelar); si no, se imprime directo. Con la impresora virtual
    de prueba no se abre el menú: el destino ya es un PDF fijo que se abre
    solo al terminar.
    """
    name = printer_name or (get_printer_name(db) if db is not None else "")
    modo = get_paper_mode(db) if db is not None else ""
    ajustes = get_ticket_settings(db) if db is not None else {}
    formato = get_ticket_format(db)
    html = ticket_html(sale, company, es_reimpresion=es_reimpresion,
                       font_pt=ajustes.get("font_pt", DEFAULT_FONT_PT),
                       line_spacing=ajustes.get("line_spacing",
                                                DEFAULT_LINE_SPACING),
                       formato=formato)
    mostrar_dialogo = (
        db is not None and get_show_dialog(db)
        and not _sera_impresora_prueba(name))
    if mostrar_dialogo:
        return imprimir_ticket_con_dialogo(
            html, name, modo,
            width_mm=ajustes.get("width_mm", _TICKET_WIDTH_MM),
            margin_mm=ajustes.get("margin_mm", _MARGIN_MM),
            reducir=ajustes.get("scale_mode", SCALE_FIT) != SCALE_REAL,
            offset_x_mm=ajustes.get("offset_x_mm", 0.0),
            offset_y_mm=ajustes.get("offset_y_mm", 0.0))
    return imprimir_ticket(
        html, name, modo,
        width_mm=ajustes.get("width_mm", _TICKET_WIDTH_MM),
        margin_mm=ajustes.get("margin_mm", _MARGIN_MM),
        reducir=ajustes.get("scale_mode", SCALE_FIT) != SCALE_REAL,
        offset_x_mm=ajustes.get("offset_x_mm", 0.0),
        offset_y_mm=ajustes.get("offset_y_mm", 0.0))


def imprimir_prueba(printer_name: str = "", db=None) -> bool:
    """Imprime un ticket de prueba. True si se envió a imprimir."""
    modo = get_paper_mode(db) if db is not None else ""
    ajustes = get_ticket_settings(db) if db is not None else {}
    html = ticket_prueba_html(
        font_pt=ajustes.get("font_pt", DEFAULT_FONT_PT),
        line_spacing=ajustes.get("line_spacing", DEFAULT_LINE_SPACING))
    return imprimir_ticket(
        html, printer_name, modo,
        width_mm=ajustes.get("width_mm", _TICKET_WIDTH_MM),
        margin_mm=ajustes.get("margin_mm", _MARGIN_MM),
        offset_x_mm=ajustes.get("offset_x_mm", 0.0),
        offset_y_mm=ajustes.get("offset_y_mm", 0.0))


# ---------- configuración de impresora (app_config) ----------

def _get_config(db, key: str, default: str = "") -> str:
    try:
        rows = db.execute_query(
            "SELECT value FROM app_config WHERE key = ?", (key,))
        return str(rows[0]["value"]) if rows else default
    except Exception:
        return default


def _set_config(db, key: str, value: str) -> None:
    try:
        db.execute_update(
            "INSERT OR REPLACE INTO app_config (key, value) VALUES (?, ?)",
            (key, str(value)))
    except Exception:
        pass


def get_ticket_format(db) -> dict:
    """Carga el diseño editable del ticket desde app_config."""
    if db is None:
        return dict(TICKET_FORMAT_DEFAULTS)
    raw = _get_config(db, "ticket_format", "")
    if not raw:
        return dict(TICKET_FORMAT_DEFAULTS)
    try:
        value = _json.loads(raw)
    except (TypeError, ValueError):
        return dict(TICKET_FORMAT_DEFAULTS)
    return normalizar_formato_ticket(value)


def save_ticket_format(db, formato: dict) -> None:
    """Guarda los bloques y textos del diseño del ticket en app_config."""
    if db is None:
        return
    limpio = normalizar_formato_ticket(formato)
    _set_config(db, "ticket_format", _json.dumps(
        limpio, ensure_ascii=False, separators=(",", ":")))


def get_printer_name(db) -> str:
    """Nombre de la impresora de tickets guardada en app_config."""
    return _get_config(db, "printer_name")


def save_printer_name(db, name: str) -> None:
    """Guarda el nombre de la impresora de tickets en app_config."""
    _set_config(db, "printer_name", name)


def get_paper_mode(db) -> str:
    """Modo de papel del ticket: windows/etiqueta."""
    modo = _get_config(db, "ticket_paper_mode", PAPER_WINDOWS)
    return modo if modo in PAPER_MODES else PAPER_WINDOWS


def _num_config(db, key: str, default: float, minimo: float,
                maximo: float) -> float:
    try:
        valor = float(_get_config(db, key, str(default)))
    except (TypeError, ValueError):
        return default
    return max(minimo, min(maximo, valor))


def get_ticket_settings(db) -> dict:
    """Parámetros de impresión del ticket (app_config, con valores por defecto)."""
    if db is None:
        return {
            "font_pt": DEFAULT_FONT_PT,
            "margin_mm": _MARGIN_MM,
            "width_mm": _TICKET_WIDTH_MM,
            "line_spacing": DEFAULT_LINE_SPACING,
            "scale_mode": SCALE_FIT,
            "offset_x_mm": 0.0,
            "offset_y_mm": 0.0,
        }
    modo = _get_config(db, "ticket_scale_mode", SCALE_FIT)
    return {
        "font_pt": _num_config(db, "ticket_font_pt", DEFAULT_FONT_PT, 6, 20),
        "margin_mm": _num_config(db, "ticket_margin_mm", _MARGIN_MM, 0, 12),
        "width_mm": _num_config(db, "ticket_width_mm", _TICKET_WIDTH_MM, 40, 112),
        "line_spacing": _num_config(db, "ticket_line_spacing",
                                    DEFAULT_LINE_SPACING, 1.0, 2.0),
        "scale_mode": modo if modo in SCALE_MODES else SCALE_FIT,
        "offset_x_mm": _num_config(db, "ticket_offset_x_mm", 0.0, -8, 8),
        "offset_y_mm": _num_config(db, "ticket_offset_y_mm", 0.0, -8, 8),
    }


def save_ticket_settings(db, font_pt: float = DEFAULT_FONT_PT,
                         margin_mm: float = _MARGIN_MM,
                         width_mm: float = _TICKET_WIDTH_MM,
                         line_spacing: float = DEFAULT_LINE_SPACING,
                         scale_mode: str = SCALE_FIT,
                         offset_x_mm: float = 0.0,
                         offset_y_mm: float = 0.0) -> None:
    """Guarda los parámetros de impresión del ticket (app_config)."""
    _set_config(db, "ticket_font_pt", f"{float(font_pt):.1f}")
    _set_config(db, "ticket_margin_mm", f"{float(margin_mm):.1f}")
    _set_config(db, "ticket_width_mm", f"{float(width_mm):.1f}")
    _set_config(db, "ticket_line_spacing", f"{float(line_spacing):.2f}")
    _set_config(db, "ticket_scale_mode",
                scale_mode if scale_mode in SCALE_MODES else SCALE_FIT)
    _set_config(db, "ticket_offset_x_mm",
                f"{_desplazamiento(offset_x_mm):.1f}")
    _set_config(db, "ticket_offset_y_mm",
                f"{_desplazamiento(offset_y_mm):.1f}")


def save_paper_mode(db, modo: str) -> None:
    """Guarda el modo de papel del ticket."""
    _set_config(db, "ticket_paper_mode",
                modo if modo in PAPER_MODES else PAPER_WINDOWS)


def get_show_dialog(db) -> bool:
    """True si se debe mostrar el menú de impresión antes de cada ticket."""
    return _get_config(db, "ticket_show_dialog") == "1"


def save_show_dialog(db, mostrar: bool) -> None:
    """Activa o desactiva el menú de impresión para las ventas."""
    _set_config(db, "ticket_show_dialog", "1" if mostrar else "0")
