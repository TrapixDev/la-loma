"""Ticket térmico 80mm: HTML compacto y envío a la impresora térmica.

Usa el driver de Windows de la impresora (Epson, Star, etc.) vía QPrinter
con página de 80mm y alto calculado según el contenido, para no desperdiciar
papel y cortar justo después del ticket.
"""

import base64
import json as _json
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QMarginsF, QSizeF
from PyQt6.QtGui import QPageLayout, QPageSize, QPainter, QTextDocument
from PyQt6.QtPrintSupport import QPrinter, QPrinterInfo

from config import Config
from utils.helpers import format_currency, monto_en_letras

_TICKET_WIDTH_MM = 80.0
_MARGIN_MM = 3.0
# Predeterminados de impresión (editables en el visor y guardados por caja).
DEFAULT_FONT_PT = 12.0
DEFAULT_LINE_SPACING = 1.35
SCALE_FIT = "ajustar"
SCALE_REAL = "real"
SCALE_MODES = {
    SCALE_FIT: "Ajustar al papel",
    SCALE_REAL: "Tamaño real (sin reducir)",
}


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
    """Convierte el logo a data URI para incrustarlo en el HTML del ticket."""
    try:
        path = Path(ruta)
        if not path.is_file():
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
                line_spacing: float = DEFAULT_LINE_SPACING) -> str:
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
        cantidad = float(item.quantity or 0)
        precio = float(item.unit_price or 0)
        filas.append(
            f'<tr>'
            f'<td class="q">{_fnum(cantidad)}</td>'
            f'<td class="d">{_html_escape(item.product_name)}</td>'
            f'<td class="r">{moneda(precio)}</td>'
            f'<td class="r">{moneda(item.total or 0)}</td>'
            f'</tr>'
        )
    rows = "\n".join(filas)

    descuento_total = float(getattr(sale, "discount", 0) or 0)
    discount_line = ""
    if descuento_total > 0:
        discount_line = (f'<tr><td class="et">DESCUENTO</td>'
                         f'<td class="rtot">{moneda(descuento_total)}</td></tr>')

    subtotal_val = float(getattr(sale, "subtotal", 0) or 0)
    tax_val = float(getattr(sale, "tax_amount", 0) or 0)
    if is_simplified:
        tax_val = 0.0

    impuesto_label = "EXENTO DE IVA" if is_simplified else "IMPUESTOS/IVA"
    impuesto_valor = "" if is_simplified else moneda(tax_val)

    equiv_line = ""
    if currency == "USD" and rate > 0 and Config.MOSTRAR_EQUIVALENTE_CRC:
        equiv_line = (f'<tr><td class="et">{currency} · Equivalente CRC</td>'
                      f'<td class="rtot">{format_currency(float(sale.total), "CRC")}</td></tr>')

    pago_rows = "".join(
        f'<tr><td class="et">{_html_escape(etiqueta)}</td>'
        f'<td class="rtot">{monto}</td></tr>'
        for etiqueta, monto in _pagos_ticket(sale, moneda))

    son_line = (f'<div class="mini wrap"><b>SON:</b> '
                f'{_html_escape(monto_en_letras(float(sale.total) * factor, currency))}'
                f'</div>')

    nombre_cliente = getattr(sale, "client_name", "") or "Consumidor Final"
    cliente_html = ""
    if not is_simplified:
        cliente_html = (f'<div>CLIENTE: <b>{_html_escape(nombre_cliente)}</b></div>')
    else:
        cliente_html = '<div>CLIENTE: Cliente General</div>'

    clave_html = ""
    if not is_simplified:
        clave = str(getattr(sale, "hacienda_key", "") or "")
        if clave:
            clave_html = f'<div class="clave">CLAVE: {_html_escape(clave)}</div>'
    else:
        clave_html = ('<div class="clave">Régimen de Tributación '
                      'Simplificada (sin clave)</div>')

    logo_uri = _logo_data_uri(company.get("logo", ""))
    logo_html = (f'<div class="centro"><img src="{logo_uri}" width="128"></div>'
                 if logo_uri else "")

    empresa_lineas = []
    if company.get("address"):
        empresa_lineas.append(_html_escape(company.get("address", "")))
    contacto = []
    if company.get("phone"):
        contacto.append(f'Tel: {_html_escape(company.get("phone", ""))}')
    if company.get("email"):
        contacto.append(_html_escape(company.get("email", "")))
    if contacto:
        empresa_lineas.append(" · ".join(contacto))
    if company.get("company_id"):
        empresa_lineas.append(f'Céd. jurídica: {_html_escape(company.get("company_id", ""))}')
    empresa_html = "".join(
        f'<div class="centro mini">{linea}</div>' for linea in empresa_lineas)

    banco_html = ""
    if company.get("iban") or company.get("sinpe"):
        filas_banco = ['<div class="centro mini negrita">PARA TRANSFERENCIA O DEPÓSITO:</div>']
        if company.get("iban"):
            filas_banco.append(
                f'<div class="centro mini">IBAN: {_html_escape(company.get("iban", ""))}</div>')
        if company.get("sinpe"):
            filas_banco.append(
                f'<div class="centro mini">SINPE MÓVIL: '
                f'{_html_escape(company.get("sinpe", ""))}</div>')
        banco_html = "".join(filas_banco)

    if is_simplified:
        estado_html = "Régimen de Tributación Simplificada"
    else:
        estado = str(getattr(sale, "hacienda_status", "") or "").upper() or "ENVIADA"
        estado_html = f"Comprobante electrónico: {estado}"

    reimpresion_html = ('<div class="centro negrita">*** REIMPRESIÓN ***</div>'
                        if es_reimpresion else "")

    fecha = _fecha_corta(getattr(sale, "created_at", ""))
    base = max(6.0, min(20.0, float(font_pt or DEFAULT_FONT_PT)))
    espaciado = max(1.0, min(2.0, float(line_spacing or DEFAULT_LINE_SPACING)))
    return f"""<html><head><style>
body {{ font-family: 'Courier New', monospace; font-size: {base:.1f}pt; color: #000; margin: 0; }}
div {{ line-height: {espaciado:.2f}; }}
.centro {{ text-align: center; }}
.nombre {{ font-weight: bold; font-size: {base + 1.5:.1f}pt; }}
.mini {{ font-size: {base - 1:.1f}pt; }}
.negrita {{ font-weight: bold; }}
.wrap {{ word-wrap: break-word; }}
.linea {{ border-top: 1px dashed #000; margin: 3px 0; }}
table {{ width: 100%; border-collapse: collapse; table-layout: fixed; }}
td {{ padding: 0; vertical-align: top; }}
th {{ font-size: {base - 1.5:.1f}pt; text-align: left; font-weight: bold; }}
.q {{ width: 10%; text-align: right; }}
.d {{ width: 46%; word-wrap: break-word; }}
.r {{ width: 22%; text-align: right; white-space: nowrap; font-size: {base - 1:.1f}pt; }}
.rtot {{ width: 48%; text-align: right; white-space: nowrap; font-size: {base - 1:.1f}pt; }}
.et {{ font-weight: bold; }}
table.lineas td {{ font-size: {base - 2:.1f}pt; }}
.total {{ font-weight: bold; font-size: {base + 0.5:.1f}pt; }}
.clave {{ font-size: {base - 2:.1f}pt; word-break: break-all; margin-top: 3px; }}
</style></head><body>
{logo_html}
<div class="centro nombre">{_html_escape(company.get("company_name", "POS La Loma"))}</div>
{empresa_html}
<div class="linea"></div>
<div class="centro negrita">{title}</div>
<div class="centro mini">Factura: {_html_escape(getattr(sale, 'invoice_number', '') or '')}</div>
<div class="centro mini">Fecha: {fecha}</div>
<div class="centro mini">Caja: {_html_escape(getattr(sale, 'station', '') or '')} · Usuario: {_html_escape(getattr(sale, 'user_name', '') or '')}</div>
{clave_html}
<div class="linea"></div>
{cliente_html}
<div class="linea"></div>
<table class="lineas">
<tr><th class="q">CANT</th><th class="d">DETALLE</th><th class="r">PRECIO</th><th class="r">TOTAL</th></tr>
{rows}
</table>
<div class="linea"></div>
<table>
<tr><td class="et">SUBTOTAL</td><td class="rtot">{moneda(subtotal_val)}</td></tr>
{discount_line}
<tr><td class="et">{impuesto_label}</td><td class="rtot">{impuesto_valor}</td></tr>
<tr class="total"><td>MONTO TOTAL</td><td class="rtot">{moneda(float(sale.total))}</td></tr>
{equiv_line}
{pago_rows}
</table>
{son_line}
<div class="linea"></div>
<div class="centro negrita">GRACIAS POR SU PREFERENCIA</div>
{banco_html}
<div class="centro mini">{estado_html}</div>
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
.mini {{ font-size: {base - 1.5:.1f}pt; color: #333; }}
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
PAPER_ROLL = "rollo"
PAPER_LABEL = "etiqueta"
PAPER_MODES = {
    PAPER_WINDOWS: "Papel configurado en Windows",
    PAPER_ROLL: "Rollo continuo 80 mm",
    PAPER_LABEL: "Etiqueta (una por ticket)",
}
# Reducción mínima aceptable cuando el ticket no cabe en la página.
_ESCALA_MINIMA = 0.6


def elegir_papel(soportadas: list[tuple[str, float, float]], modo: str,
                 ancho_mm: float = _TICKET_WIDTH_MM) -> tuple[str, float, float] | None:
    """Elige (nombre, ancho, alto) del papel según el modo.

    `soportadas` es una lista de (nombre, ancho_mm, alto_mm) del driver.
    - rollo: la de ancho ~80mm con mayor alto (papel continuo).
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
    if modo == PAPER_ROLL:
        return max(candidatas, key=lambda p: p[2])
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
                        margin_mm: float = _MARGIN_MM) -> QPrinter | None:
    """Crea el QPrinter usando SIEMPRE un tamaño soportado por el driver.

    Reglas:
    - rollo/etiqueta: se elige de la lista de tamaños del driver (nunca se
      inventa un tamaño, que era lo que hacía que Windows alimentara papel
      en blanco sin fin).
    - rollo: el de ~80mm con mayor alto; etiqueta: el más chico que alcance.
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
    if modo == PAPER_ROLL:
        elegida = elegir_papel(soportadas, PAPER_ROLL, width_mm)
    elif modo == PAPER_LABEL:
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
    printer.setPageMargins(
        QMarginsF(margen, margen, margen, margen),
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


def escala_necesaria(printer: QPrinter, html: str) -> float:
    """Escala (<= 1.0) que necesita el ticket para caber en una página."""
    try:
        rect = printer.pageLayout().paintRectPixels(printer.resolution())
        doc = _documento(html)
        doc.setTextWidth(max(1.0, float(rect.width())))
        alto_doc = float(doc.size().height())
        alto_pagina = float(rect.height())
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
                         reducir: bool = True) -> bool:
    """Dibuja el ticket en UNA sola página.

    No usa QTextDocument.print() (que pagina el contenido y era el origen de
    las "13 páginas"): pinta el documento una vez, recortado al área imprimible
    y reducido si no cabe (salvo que `reducir` sea False). Así nunca se emite
    más de una página ni papel en blanco sin fin.
    """
    try:
        rect = printer.pageLayout().paintRectPixels(printer.resolution())
        doc = _documento(html)
        doc.setTextWidth(max(1.0, float(rect.width())))
        alto_doc = float(doc.size().height())
        escala = (_escala_para_caber(float(rect.height()), alto_doc)
                  if reducir else 1.0)
        painter = QPainter(printer)
        try:
            painter.setClipRect(rect)
            painter.translate(rect.left(), rect.top())
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


def advertencia_papel(printer: QPrinter, html: str) -> str:
    """Aviso si el ticket no cabe en el papel y se va a reducir."""
    try:
        pagina = printer.pageLayout().pageSize().size(QPageSize.Unit.Millimeter)
        alto_contenido = _medir_alto(html)
        if pagina.height() + 1 < alto_contenido:
            return (f"El papel elegido ({pagina.width():.0f}×"
                    f"{pagina.height():.0f} mm) es más corto que el ticket "
                    f"({alto_contenido:.0f} mm): se reducirá para que entre "
                    f"en una sola página. Para evitarlo elija «Rollo continuo "
                    f"80 mm».")
    except Exception:
        pass
    return ""


def imprimir_ticket(html: str, printer_name: str = "", modo_papel: str = "",
                    copias: int = 1, width_mm: float = _TICKET_WIDTH_MM,
                    margin_mm: float = _MARGIN_MM,
                    reducir: bool = True) -> bool:
    """Imprime el ticket en la impresora indicada (o la predeterminada).

    True si se envió a imprimir. False si no hay impresora válida o la
    seleccionada es un PDF/XPS (salvo en modo de prueba POS_PRINT_TEST=1).
    """
    printer = _preparar_impresora(printer_name, modo_papel, html, copias,
                                  width_mm, margin_mm)
    if printer is None:
        return False
    return _imprimir_una_pagina(html, printer, reducir)


def imprimir_ticket_con_dialogo(html: str, printer_name: str = "",
                                modo_papel: str = "", copias: int = 1,
                                width_mm: float = _TICKET_WIDTH_MM,
                                margin_mm: float = _MARGIN_MM,
                                reducir: bool = True) -> bool:
    """Imprime mostrando el menú de impresión de Windows (Imprimir/Cancelar).

    Devuelve False si el usuario cancela o no hay impresora válida.
    """
    from PyQt6.QtWidgets import QDialog, QPrintDialog

    printer = _preparar_impresora(printer_name, modo_papel, html, copias,
                                  width_mm, margin_mm)
    if printer is None:
        return False
    dialog = QPrintDialog(printer)
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return False
    return _imprimir_una_pagina(html, printer, reducir)


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
        margin_mm=ajustes.get("margin_mm", _MARGIN_MM))
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
    (Imprimir/Cancelar); si no, se imprime directo.
    """
    name = printer_name or (get_printer_name(db) if db is not None else "")
    modo = get_paper_mode(db) if db is not None else ""
    ajustes = get_ticket_settings(db) if db is not None else {}
    html = ticket_html(sale, company, es_reimpresion=es_reimpresion,
                       font_pt=ajustes.get("font_pt", DEFAULT_FONT_PT),
                       line_spacing=ajustes.get("line_spacing",
                                                DEFAULT_LINE_SPACING))
    if db is not None and get_show_dialog(db):
        return imprimir_ticket_con_dialogo(
            html, name, modo,
            width_mm=ajustes.get("width_mm", _TICKET_WIDTH_MM),
            margin_mm=ajustes.get("margin_mm", _MARGIN_MM),
            reducir=ajustes.get("scale_mode", SCALE_FIT) != SCALE_REAL)
    return imprimir_ticket(
        html, name, modo,
        width_mm=ajustes.get("width_mm", _TICKET_WIDTH_MM),
        margin_mm=ajustes.get("margin_mm", _MARGIN_MM),
        reducir=ajustes.get("scale_mode", SCALE_FIT) != SCALE_REAL)


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
        margin_mm=ajustes.get("margin_mm", _MARGIN_MM))


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


def get_printer_name(db) -> str:
    """Nombre de la impresora de tickets guardada en app_config."""
    return _get_config(db, "printer_name")


def save_printer_name(db, name: str) -> None:
    """Guarda el nombre de la impresora de tickets en app_config."""
    _set_config(db, "printer_name", name)


def get_paper_mode(db) -> str:
    """Modo de papel del ticket: windows/rollo/etiqueta."""
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
        }
    modo = _get_config(db, "ticket_scale_mode", SCALE_FIT)
    return {
        "font_pt": _num_config(db, "ticket_font_pt", DEFAULT_FONT_PT, 6, 20),
        "margin_mm": _num_config(db, "ticket_margin_mm", _MARGIN_MM, 0, 12),
        "width_mm": _num_config(db, "ticket_width_mm", _TICKET_WIDTH_MM, 40, 112),
        "line_spacing": _num_config(db, "ticket_line_spacing",
                                    DEFAULT_LINE_SPACING, 1.0, 2.0),
        "scale_mode": modo if modo in SCALE_MODES else SCALE_FIT,
    }


def save_ticket_settings(db, font_pt: float = DEFAULT_FONT_PT,
                         margin_mm: float = _MARGIN_MM,
                         width_mm: float = _TICKET_WIDTH_MM,
                         line_spacing: float = DEFAULT_LINE_SPACING,
                         scale_mode: str = SCALE_FIT) -> None:
    """Guarda los parámetros de impresión del ticket (app_config)."""
    _set_config(db, "ticket_font_pt", f"{float(font_pt):.1f}")
    _set_config(db, "ticket_margin_mm", f"{float(margin_mm):.1f}")
    _set_config(db, "ticket_width_mm", f"{float(width_mm):.1f}")
    _set_config(db, "ticket_line_spacing", f"{float(line_spacing):.2f}")
    _set_config(db, "ticket_scale_mode",
                scale_mode if scale_mode in SCALE_MODES else SCALE_FIT)


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
