"""Ticket térmico 80mm: HTML compacto y envío a la impresora térmica.

Usa el driver de Windows de la impresora (Epson, Star, etc.) vía QPrinter
con página de 80mm y alto calculado según el contenido, para no desperdiciar
papel y cortar justo después del ticket.
"""

import base64
import json as _json
from pathlib import Path

from PyQt6.QtCore import QMarginsF, QSizeF
from PyQt6.QtGui import QPageLayout, QPageSize, QTextDocument
from PyQt6.QtPrintSupport import QPrinter, QPrinterInfo

from config import Config
from utils.helpers import format_currency, monto_en_letras

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


def ticket_html(sale, company: dict, es_reimpresion: bool = False) -> str:
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
        descuento = float(getattr(item, "discount", 0) or 0)
        base = max(0.0, cantidad * precio - descuento)
        impuesto = float(getattr(item, "tax_amount", 0) or 0)
        if impuesto > 0 and base > 0:
            tasa = impuesto / base * 100
        else:
            tasa = float(getattr(item, "tax_rate", 0) or 0)
        filas.append(
            f'<tr>'
            f'<td class="q">{_fnum(cantidad)}</td>'
            f'<td class="d">{_html_escape(item.product_name)}</td>'
            f'<td class="r">{moneda(precio)}</td>'
            f'<td class="r">{moneda(item.total or 0)}</td>'
            f'<td class="r">{"-" if is_simplified or tasa <= 0 else f"{tasa:.0f}%"}</td>'
            f'</tr>'
        )
    rows = "\n".join(filas)

    descuento_total = float(getattr(sale, "discount", 0) or 0)
    discount_line = ""
    if descuento_total > 0:
        discount_line = (f'<tr><td class="et">DESCUENTO</td>'
                         f'<td class="r">{moneda(descuento_total)}</td></tr>')

    subtotal_val = float(getattr(sale, "subtotal", 0) or 0)
    tax_val = float(getattr(sale, "tax_amount", 0) or 0)
    if is_simplified:
        tax_val = 0.0

    impuesto_label = "EXENTO DE IVA" if is_simplified else "IMPUESTOS/IVA"
    impuesto_valor = "" if is_simplified else moneda(tax_val)

    equiv_line = ""
    if currency == "USD" and rate > 0 and Config.MOSTRAR_EQUIVALENTE_CRC:
        equiv_line = (f'<tr><td class="et">{currency} · Equivalente CRC</td>'
                      f'<td class="r">{format_currency(float(sale.total), "CRC")}</td></tr>')

    pago_rows = "".join(
        f'<tr><td class="et">{_html_escape(etiqueta)}</td>'
        f'<td class="r">{monto}</td></tr>'
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
    return f"""<html><head><style>
body {{ font-family: 'Courier New', monospace; font-size: 9pt; color: #000; margin: 0; }}
div {{ line-height: 1.35; }}
.centro {{ text-align: center; }}
.nombre {{ font-weight: bold; font-size: 10.5pt; }}
.mini {{ font-size: 8pt; }}
.negrita {{ font-weight: bold; }}
.wrap {{ word-wrap: break-word; }}
.linea {{ border-top: 1px dashed #000; margin: 3px 0; }}
table {{ width: 100%; border-collapse: collapse; }}
td {{ padding: 0; vertical-align: top; }}
th {{ font-size: 7.5pt; text-align: left; font-weight: bold; }}
.q {{ width: 8%; text-align: right; }}
.d {{ width: 40%; }}
.r {{ width: 17%; text-align: right; white-space: nowrap; font-size: 8pt; }}
.et {{ font-weight: bold; }}
table.lineas td {{ font-size: 7.5pt; }}
.total {{ font-weight: bold; font-size: 10.5pt; }}
.clave {{ font-size: 7pt; word-break: break-all; margin-top: 3px; }}
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
<tr><th class="q">CANT</th><th class="d">DETALLE</th><th class="r">PRECIO</th><th class="r">SUBTOT</th><th class="r">IVA</th></tr>
{rows}
</table>
<div class="linea"></div>
<table>
<tr><td class="et">SUBTOTAL</td><td class="r">{moneda(subtotal_val)}</td></tr>
{discount_line}
<tr><td class="et">{impuesto_label}</td><td class="r">{impuesto_valor}</td></tr>
<tr class="total"><td>MONTO TOTAL</td><td class="r">{moneda(float(sale.total))}</td></tr>
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


def ticket_prueba_html(extra: str = "") -> str:
    """Ticket de prueba para verificar la impresora (con datos de soporte)."""
    extra_html = (f'<div class="centro mini">{_html_escape(extra)}</div>'
                  if extra else "")
    return """<html><head><style>
body {{ font-family: 'Courier New', monospace; font-size: 9pt; color: #000; }}
.centro {{ text-align: center; }}
.mini {{ font-size: 7.5pt; color: #333; }}
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
_ALTO_CONTINUO_MM = 150.0


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
    candidatas = [p for p in soportadas if abs(p[1] - ancho_mm) <= 3]
    if not candidatas:
        candidatas = list(soportadas)
    if modo == PAPER_ROLL:
        return max(candidatas, key=lambda p: p[2])
    if modo == PAPER_LABEL:
        return min(candidatas, key=lambda p: (abs(p[1] - ancho_mm), p[2]))
    return None


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


def _tamanos_soportados(printer: QPrinter) -> list[tuple[str, float, float]]:
    soportadas: list[tuple[str, float, float]] = []
    try:
        for size in printer.supportedPageSizes():
            mm = size.size(QPageSize.Unit.Millimeter)
            soportadas.append((size.name(), mm.width(), mm.height()))
    except Exception:
        pass
    return soportadas


def _preparar_impresora(printer_name: str = "", modo: str = "",
                        html: str = "", copias: int = 1) -> QPrinter | None:
    """Crea el QPrinter respetando el papel elegido (Windows/rollo/etiqueta).

    Antes se forzaba un tamaño "80 x alto" con ExactMatch: si el driver no lo
    soportaba (p. ej. una impresora configurada con etiquetas), Windows usaba
    su formulario por defecto y cada línea del ticket salía en una etiqueta.
    Ahora, en modo Windows, se usa el papel del driver y solo se compacta el
    alto cuando el papel es continuo (alto >= 150mm); con etiqueta se imprime
    una por ticket sin paginar.
    """
    name = printer_name or QPrinterInfo.defaultPrinterName()
    if not name:
        return None
    lower = name.lower()
    if "pdf" in lower or "xps" in lower:
        return None
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setPrinterName(name)
    if copias > 1:
        try:
            printer.setCopyCount(int(copias))
        except Exception:
            pass
    modo = modo if modo in PAPER_MODES else PAPER_WINDOWS

    actual = printer.pageLayout().pageSize()
    actual_mm = actual.size(QPageSize.Unit.Millimeter)
    ancho, alto_actual = actual_mm.width(), actual_mm.height()
    aplicado = f"actual {ancho:.0f}x{alto_actual:.0f}mm"

    alto_contenido = _medir_alto(html) if html else 0.0
    elegida = None
    if modo in (PAPER_ROLL, PAPER_LABEL):
        elegida = elegir_papel(_tamanos_soportados(printer), modo)
    elif modo == PAPER_WINDOWS and html and alto_actual + 1 < alto_contenido:
        # Papel del driver más corto que el ticket (p. ej. etiqueta 80x15):
        # si hay un rollo de 80mm soportado, se usa para no partir el ticket.
        rollo = elegir_papel(_tamanos_soportados(printer), PAPER_ROLL)
        if rollo is not None and rollo[2] >= alto_contenido:
            elegida = rollo
            aplicado += " (papel corto: se usa rollo)"
    if elegida is not None:
        ancho = elegida[1]
        printer.setPageSize(QPageSize(
            QSizeF(elegida[1], elegida[2]), QPageSize.Unit.Millimeter,
            elegida[0], QPageSize.SizeMatchPolicy.ExactMatch))
        alto_actual = elegida[2]
        aplicado = (f"{elegida[0]} {elegida[1]:.0f}x{elegida[2]:.0f}mm"
                    + (" (papel del driver era corto)" if "papel corto" in aplicado
                       else ""))

    continuo = alto_actual >= _ALTO_CONTINUO_MM
    if continuo and modo in (PAPER_WINDOWS, PAPER_ROLL):
        # Papel continuo: compactar el alto al contenido para no desperdiciar.
        alto = alto_contenido or 297.0
        printer.setPageSize(QPageSize(
            QSizeF(ancho, alto), QPageSize.Unit.Millimeter,
            "Ticket80", QPageSize.SizeMatchPolicy.ExactMatch))
        aplicado += f" -> contenido {ancho:.0f}x{alto:.0f}mm"

    printer.setPageMargins(
        QMarginsF(_MARGIN_MM, _MARGIN_MM, _MARGIN_MM, _MARGIN_MM),
        QPageLayout.Unit.Millimeter)
    _log_impresora(name, actual_mm, modo, aplicado, printer)
    return printer


def _log_impresora(name: str, actual_mm, modo: str, aplicado: str,
                   printer: QPrinter) -> None:
    try:
        from utils.diagnostico import escribir_log

        soportados = ", ".join(
            f"{n} {w:.0f}x{h:.0f}" for n, w, h in _tamanos_soportados(printer)[:6])
        escribir_log(
            f"Impresora '{name}': papel actual {actual_mm.width():.0f}x"
            f"{actual_mm.height():.0f}mm; modo={modo}; usado={aplicado}; "
            f"soportados: {soportados or 'n/d'}")
    except Exception:
        pass


def advertencia_papel(printer: QPrinter, html: str) -> str:
    """Aviso si el papel configurado es más corto que el contenido del ticket."""
    try:
        pagina = printer.pageLayout().pageSize().size(QPageSize.Unit.Millimeter)
        alto_contenido = _medir_alto(html)
        if pagina.height() + 1 < alto_contenido:
            return (f"El papel configurado ({pagina.width():.0f}×"
                    f"{pagina.height():.0f} mm) es más corto que el ticket "
                    f"({alto_contenido:.0f} mm). Elija «Rollo continuo 80 mm» "
                    f"para que salga en una sola página.")
    except Exception:
        pass
    return ""


def imprimir_ticket(html: str, printer_name: str = "", modo_papel: str = "",
                    copias: int = 1) -> bool:
    """Imprime el ticket en la impresora indicada (o la predeterminada).

    True si se envió a imprimir. False si no hay impresora válida o la
    seleccionada es un PDF/XPS.
    """
    printer = _preparar_impresora(printer_name, modo_papel, html, copias)
    if printer is None:
        return False
    _documento(html).print(printer)
    return True


def imprimir_ticket_con_dialogo(html: str, printer_name: str = "",
                                modo_papel: str = "", copias: int = 1) -> bool:
    """Imprime mostrando el menú de impresión de Windows (Imprimir/Cancelar).

    Devuelve False si el usuario cancela o no hay impresora válida.
    """
    from PyQt6.QtWidgets import QDialog, QPrintDialog

    printer = _preparar_impresora(printer_name, modo_papel, html, copias)
    if printer is None:
        return False
    dialog = QPrintDialog(printer)
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return False
    _documento(html).print(printer)
    return True


def previsualizar_ticket(html: str, printer_name: str = "",
                         modo_papel: str = "", parent=None) -> bool:
    """Muestra el visor de vista previa estilo Chrome.

    Devuelve False solo si no hay ninguna impresora válida para preparar.
    """
    from ui.ticket_preview import TicketPreviewDialog

    printer = _preparar_impresora(printer_name, modo_papel, html)
    if printer is None:
        return False
    dialog = TicketPreviewDialog(html, printer_name, modo_papel, parent)
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
    html = ticket_html(sale, company, es_reimpresion=es_reimpresion)
    if db is not None and get_show_dialog(db):
        return imprimir_ticket_con_dialogo(html, name, modo)
    return imprimir_ticket(html, name, modo)


def imprimir_prueba(printer_name: str = "", db=None) -> bool:
    """Imprime un ticket de prueba. True si se envió a imprimir."""
    modo = get_paper_mode(db) if db is not None else ""
    return imprimir_ticket(ticket_prueba_html(), printer_name, modo)


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
