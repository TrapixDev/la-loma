"""Diálogos de detalle de Reportes: venta, gasto, abono y nota de crédito.

Se abren con doble clic en los movimientos del día y en el historial de
ventas. Son de solo lectura (el gasto también) y el detalle de venta permite
reimprimir la factura reutilizando el flujo existente.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from utils.helpers import EmptyStateTable, format_currency


def _texto(valor, default: str = "—") -> str:
    texto = str(valor or "").strip()
    return texto or default


def _esc(valor) -> str:
    """Escapa texto que viene de la base antes de meterlo en un QLabel."""
    texto = "" if valor is None else str(valor)
    return (texto.replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _fecha(value) -> str:
    texto = str(value or "").strip()
    if len(texto) >= 16:
        return texto[:16]
    return texto or "—"


def _cantidad(value) -> str:
    try:
        numero = float(value or 0)
    except (TypeError, ValueError):
        return str(value or "")
    if numero == int(numero):
        return str(int(numero))
    return f"{numero:g}"


def reimprimir_venta(parent, services: dict, sale_id: int) -> bool:
    """Reimprime una venta (térmica/A4) y muestra los avisos de siempre."""
    from modules.documentos import reimprimir_factura

    db = (services or {}).get("db")
    cart = (services or {}).get("cart")
    if db is None or cart is None:
        QMessageBox.warning(parent, "Reimprimir",
                            "No hay acceso a los datos de ventas.")
        return False
    resultado = reimprimir_factura(db, cart, int(sale_id), imprimir=True)
    if not resultado or not resultado.get("pdf"):
        QMessageBox.warning(parent, "Reimprimir",
                            "No se encontró el documento de esa venta.")
        return False
    if resultado.get("impreso"):
        QMessageBox.information(
            parent, "Reimprimir",
            f"Factura reimpresa y guardada en:\n{resultado.get('pdf')}")
    else:
        QMessageBox.information(
            parent, "Reimprimir",
            f"No se pudo imprimir en la impresora térmica ni en una de "
            f"hojas.\nLa factura quedó guardada en:\n{resultado.get('pdf')}\n\n"
            f"Para imprimirla, elija una impresora A4 en "
            f"Configuración → Impresora y docs.")
    return True


class _DetalleBase(QDialog):
    """Base de los detalles: título, filas etiqueta/valor y botón Cerrar."""

    def __init__(self, titulo: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(titulo)
        self.setMinimumWidth(540)
        self._layout = QVBoxLayout(self)
        self._layout.setSpacing(10)
        self._grid = QGridLayout()
        self._grid.setHorizontalSpacing(14)
        self._grid.setVerticalSpacing(4)
        self._grid.setColumnStretch(1, 1)
        self._grid_agregado = False
        self._fila = 0
        self.filas: dict[str, str] = {}

    # ---------- construcción ----------

    def _titulo(self, texto: str) -> None:
        label = QLabel()
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setText(texto)
        label.setObjectName("sectionTitle")
        label.setWordWrap(True)
        label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        self._layout.addWidget(label)

    def _meta(self, texto: str, html: bool = False) -> None:
        """Línea de datos; por defecto en texto plano (los valores vienen de
        la base y no deben interpretarse como HTML)."""
        label = QLabel()
        label.setTextFormat(Qt.TextFormat.RichText if html
                            else Qt.TextFormat.PlainText)
        label.setText(texto)
        label.setStyleSheet("font-size: 13px; color: #8b93a3;")
        label.setWordWrap(True)
        label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        self._layout.addWidget(label)

    def _subtitulo(self, texto: str) -> None:
        label = QLabel()
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setText(texto)
        label.setObjectName("subtitleLabel")
        self._layout.addWidget(label)

    def _separador(self) -> None:
        linea = QFrame()
        linea.setObjectName("separator")
        linea.setFrameShape(QFrame.Shape.HLine)
        self._layout.addWidget(linea)

    def _valor(self, etiqueta: str, valor, negrita: bool = False,
               color: str = "") -> None:
        if not self._grid_agregado:
            # La grilla se inserta al usarla: así queda después de la tabla de
            # artículos (o del separador) y no antes.
            self._layout.addLayout(self._grid)
            self._grid_agregado = True
        self.filas[etiqueta] = str(valor)
        nombre = QLabel(f"{etiqueta}:")
        nombre.setStyleSheet("color: #8b93a3;")
        nombre.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        dato = QLabel()
        dato.setTextFormat(Qt.TextFormat.PlainText)
        dato.setText(str(valor))
        dato.setWordWrap(True)
        dato.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        estilo = ""
        if negrita:
            estilo += "font-weight: bold;"
        if color:
            estilo += f"color: {color};"
        if estilo:
            dato.setStyleSheet(estilo)
        self._grid.addWidget(nombre, self._fila, 0)
        self._grid.addWidget(dato, self._fila, 1)
        self._fila += 1

    def _botones(self, extra: list[QPushButton] | None = None) -> None:
        fila = QHBoxLayout()
        for boton in extra or []:
            fila.addWidget(boton)
        fila.addStretch(1)
        cerrar = QPushButton("Cerrar")
        cerrar.setObjectName("secondaryButton")
        cerrar.clicked.connect(self.accept)
        fila.addWidget(cerrar)
        self._layout.addLayout(fila)


class SaleDetailDialog(_DetalleBase):
    """Detalle de una venta: artículos, totales, pagos y estado."""

    def __init__(self, services: dict, sale_id: int, parent=None):
        super().__init__("Detalle de venta", parent)
        self.services = services or {}
        self.sale = None
        casa = self.services.get("cart")
        if casa is not None and sale_id:
            try:
                self.sale = casa.get_sale(int(sale_id))
            except Exception:
                self.sale = None
        if self.sale is None:
            self._titulo("Venta no encontrada")
            self._meta("No se pudo cargar la venta seleccionada.")
            self._botones()
            return
        self._construir()

    def _construir(self) -> None:
        from modules.documentos.ticket import _pagos_ticket

        sale = self.sale
        currency = str(getattr(sale, "currency", "CRC") or "CRC")
        rate = float(getattr(sale, "exchange_rate", 0) or 0)
        factor = (1.0 / rate) if currency == "USD" and rate > 0 else 1.0

        def moneda(valor) -> str:
            return format_currency(float(valor or 0) * factor, currency)

        anulada = (sale.status or "").lower() == "anulada"
        numero = sale.invoice_number or str(sale.id)
        self._titulo(f"Factura {numero} — {moneda(sale.total)}")
        tiene_clave = bool(getattr(sale, "electronic_invoice", False))
        comprobante = "Electrónica" if tiene_clave else (
            "Simplificada" if (sale.invoice_type or "") == "simplificada"
            else "General")
        estado = "ANULADA" if anulada else (sale.status or "completada").capitalize()
        color_estado = "#ef4444" if anulada else "#2fbf71"
        self._meta(
            f"Fecha: {_fecha(sale.created_at)}  |  "
            f"Cliente: {_texto(sale.client_name, 'Consumidor Final')}")
        self._meta(
            f"Caja: {_texto(sale.station)}  |  "
            f"Cajero: {_texto(sale.user_name)}  |  "
            f"Comprobante: {comprobante}  |  "
            f"Estado: <span style='color:{color_estado};font-weight:bold'>"
            f"{_esc(estado)}</span>", html=True)

        self._subtitulo("Artículos")
        items = list(getattr(sale, "items", None) or [])
        self._items_table = EmptyStateTable(
            "Esta venta no tiene artículos registrados.", 0, 4)
        self._items_table.setHorizontalHeaderLabels(
            ["Cant.", "Producto", "P. unitario", "Total"])
        self._items_table.horizontalHeader().setObjectName("tableHeader")
        self._items_table.verticalHeader().setVisible(False)
        self._items_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows)
        self._items_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers)
        self._items_table.setAlternatingRowColors(True)
        self._items_table.setRowCount(len(items))
        for row, item in enumerate(items):
            valores = [
                _cantidad(item.quantity),
                item.product_name or "Artículo",
                moneda(item.unit_price),
                moneda(item.total),
            ]
            for column, valor in enumerate(valores):
                self._items_table.setItem(row, column, QTableWidgetItem(str(valor)))
        header = self._items_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self._items_table.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._items_table.setMaximumHeight(210)
        self._layout.addWidget(self._items_table)

        self._separador()
        self._valor("Subtotal", moneda(sale.subtotal))
        descuento = float(getattr(sale, "discount", 0) or 0)
        if descuento > 0:
            self._valor("Descuento", moneda(descuento))
        self._valor("Impuestos/IVA", moneda(sale.tax_amount))
        self._valor("Monto total", moneda(sale.total), negrita=True)
        if currency == "USD" and rate > 0:
            self._valor("Equivalente CRC",
                        format_currency(float(sale.total), "CRC"))

        pagos = _pagos_ticket(sale, moneda)
        if not pagos:
            metodo = (sale.payment_method or "").capitalize()
            pagos = [("Forma de pago", metodo or "—")]
        for etiqueta, monto in pagos:
            self._valor(etiqueta.capitalize(), monto)

        if sale.hacienda_key:
            self._valor("Clave Hacienda", sale.hacienda_key)
        if tiene_clave:
            estado_fe = str(sale.hacienda_status or "PENDIENTE").upper()
            self._valor("Estado Hacienda", estado_fe)

        reimprimir = QPushButton("Reimprimir")
        reimprimir.setObjectName("secondaryButton")
        reimprimir.clicked.connect(self._reimprimir)
        self._botones([reimprimir])

    def _reimprimir(self) -> None:
        if self.sale is not None:
            reimprimir_venta(self, self.services, int(self.sale.id))


class ExpenseDetailDialog(_DetalleBase):
    """Detalle de un gasto (solo lectura)."""

    def __init__(self, services: dict, expense_id: int, parent=None):
        super().__init__("Detalle del gasto", parent)
        servicio = (services or {}).get("expenses")
        expense = None
        if servicio is not None and expense_id:
            try:
                expense = servicio.get_expense(int(expense_id))
            except Exception:
                expense = None
        if expense is None:
            self._titulo("Gasto no encontrado")
            self._meta("No se pudo cargar el gasto seleccionado.")
            self._botones()
            return
        self._titulo(f"Gasto — {format_currency(float(expense.amount or 0))}")
        self._meta(f"Categoría: {_texto(expense.category)}  |  "
                   f"Fecha: {_fecha(expense.expense_date)}")
        self._separador()
        self._valor("Monto", format_currency(float(expense.amount or 0)),
                    negrita=True)
        self._valor("Categoría", _texto(expense.category))
        self._valor("Descripción", _texto(expense.description, "(sin descripción)"))
        self._valor("Método de pago", _texto(expense.payment_method))
        self._valor("Fecha del gasto", _fecha(expense.expense_date))
        self._valor("Registrado por", _texto(expense.user_name))
        self._valor("Caja", _texto(expense.station))
        self._valor("Registrado el", _fecha(expense.created_at))
        self._botones()


class CreditPaymentDetailDialog(_DetalleBase):
    """Detalle de un abono a una cuenta por cobrar."""

    def __init__(self, services: dict, payment_id: int, parent=None):
        super().__init__("Detalle del abono", parent)
        self.services = services or {}
        self.payment = None
        servicio = self.services.get("credit")
        if servicio is not None and payment_id:
            try:
                self.payment = servicio.get_payment(int(payment_id))
            except Exception:
                self.payment = None
        if self.payment is None:
            self._titulo("Abono no encontrado")
            self._meta("No se pudo cargar el abono seleccionado.")
            self._botones()
            return
        pago = self.payment
        self._titulo(f"Abono — {format_currency(float(pago.amount or 0))}")
        self._meta(f"Cliente: {_texto(pago.client_name)}  |  "
                   f"Factura: {_texto(pago.invoice_number)}  |  "
                   f"Fecha: {_fecha(pago.created_at)}")
        self._separador()
        self._valor("Monto", format_currency(float(pago.amount or 0)),
                    negrita=True)
        self._valor("Cliente", _texto(pago.client_name))
        self._valor("Factura", _texto(pago.invoice_number))
        self._valor("Método", _texto(pago.payment_method).capitalize())
        self._valor("Notas", _texto(pago.notes, "(sin notas)"))
        self._valor("Referencia", _texto(pago.payment_reference))
        self._valor("Registrado por", _texto(pago.user_name))
        self._valor("Fecha", _fecha(pago.created_at))

        extra: list[QPushButton] = []
        imagenes = self._imagenes()
        if imagenes:
            ver = QPushButton(f"Ver comprobantes ({imagenes})")
            ver.setObjectName("secondaryButton")
            ver.clicked.connect(self._ver_comprobantes)
            extra.append(ver)
        self._botones(extra)

    def _imagenes(self) -> int:
        servicio = self.services.get("credit")
        if servicio is None or self.payment is None:
            return 0
        try:
            return len(servicio.list_payment_images(int(self.payment.id)))
        except Exception:
            return 0

    def _ver_comprobantes(self) -> None:
        from modules.credit.credit_widget import PaymentGalleryDialog

        PaymentGalleryDialog(self.payment, self.services, self).exec()


class CreditNoteDetailDialog(_DetalleBase):
    """Detalle de una nota de crédito emitida."""

    def __init__(self, services: dict, note_id: int, parent=None):
        super().__init__("Detalle de nota de crédito", parent)
        servicio = (services or {}).get("reports")
        nota = None
        if servicio is not None and note_id:
            try:
                nota = servicio.get_credit_note(int(note_id))
            except Exception:
                nota = None
        if nota is None:
            self._titulo("Nota de crédito no encontrada")
            self._meta("No se pudo cargar la nota seleccionada.")
            self._botones()
            return
        numero = _texto(nota.get("invoice_number"))
        total = float(nota.get("total") or 0)
        self._titulo(f"Nota de crédito {numero} — {format_currency(total)}")
        self._meta(f"Fecha: {_fecha(nota.get('created_at'))}  |  "
                   f"Cliente: {_texto(nota.get('client_name'))}  |  "
                   f"Factura original: {_texto(nota.get('factura_original'))}")
        self._separador()
        self._valor("Monto acreditado", format_currency(total), negrita=True)
        self._valor("Subtotal", format_currency(float(nota.get("subtotal") or 0)))
        self._valor("Impuestos/IVA",
                    format_currency(float(nota.get("tax_amount") or 0)))
        self._valor("Motivo", _texto(nota.get("razon") or nota.get("motivo")))
        self._valor("Código de referencia", _texto(nota.get("codigo_referencia")))
        self._valor("Estado", _texto(nota.get("estado")))
        if nota.get("hacienda_key"):
            self._valor("Clave Hacienda", nota.get("hacienda_key"))
        self._valor("Registrada por", _texto(nota.get("user_name")))
        self._valor("Caja", _texto(nota.get("station")))
        self._botones()
