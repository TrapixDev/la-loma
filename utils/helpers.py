def format_currency(amount: float, currency: str = "CRC") -> str:
    """Formatea un monto como moneda (₡ o $) con separadores de miles."""
    if currency.upper() == "USD":
        return f"${amount:,.2f}"
    return f"₡{amount:,.2f}"


def calculate_totals(items: list[dict], exento: bool = False) -> dict:
    """Calcula subtotal, descuento, impuesto y total a partir de los items del carrito.

    Con `exento=True` (Factura Simplificada / Régimen de Tributación
    Simplificada) la venta no cobra impuestos: tax_amount = 0 y el total
    es subtotal - descuento.
    """
    subtotal = 0.0
    discount = 0.0
    tax_amount = 0.0
    for item in items:
        quantity = float(item.get("quantity", 1))
        unit_price = float(item.get("unit_price", 0))
        tax_rate = float(item.get("tax_rate", 0))
        item_discount = float(item.get("discount", 0))
        line_subtotal = quantity * unit_price
        subtotal += line_subtotal
        discount += item_discount
        if not exento:
            tax_amount += (line_subtotal - item_discount) * (tax_rate / 100)
    total = subtotal - discount + tax_amount
    return {
        "subtotal": round(subtotal, 2),
        "discount": round(discount, 2),
        "tax_amount": round(tax_amount, 2),
        "total": round(total, 2),
    }


from PyQt6.QtWidgets import QDoubleSpinBox


class NoWheelSpinBox(QDoubleSpinBox):
    """QDoubleSpinBox que ignora la rueda del mouse para evitar cambios accidentales."""

    def wheelEvent(self, event):
        event.ignore()


from PyQt6.QtWidgets import QComboBox


class NoWheelComboBox(QComboBox):
    """QComboBox que ignora la rueda del mouse para evitar cambios accidentales."""

    def wheelEvent(self, event):
        event.ignore()


def ajustar_anchos_encabezado(table, anchos) -> None:
    """Garantiza que cada columna quepa su título según la fuente real.

    `anchos` puede ser una lista (columna 0, 1, 2...) o un dict {columna: ancho}.
    Usa las métricas del encabezado (ya con el estilo aplicado) y sube el ancho
    de la columna si el título se cortaría. Mantiene los anchos base cuando
    alcanzan, para no desperdiciar espacio en pantallas de 768p.
    """
    header = table.horizontalHeader()
    header.ensurePolished()
    metrics = header.fontMetrics()
    pares = anchos.items() if isinstance(anchos, dict) else enumerate(anchos)
    for col, ancho in pares:
        if col >= table.columnCount():
            break
        item = table.horizontalHeaderItem(col)
        texto = item.text() if item is not None else ""
        necesario = metrics.horizontalAdvance(texto) + 36
        table.setColumnWidth(col, max(ancho, necesario))


from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QTableWidget


class EmptyStateTable(QTableWidget):
    """QTableWidget que muestra un mensaje centrado cuando no tiene filas."""

    def __init__(self, message: str, rows: int = 0, columns: int = 1,
                 parent=None):
        super().__init__(rows, columns, parent)
        self._empty_label = QLabel(message, self.viewport())
        self._empty_label.setObjectName("emptyState")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setWordWrap(True)
        self._empty_label.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._update_empty_state()

    def set_empty_message(self, message: str) -> None:
        self._empty_label.setText(message)

    def setRowCount(self, rows: int) -> None:  # noqa: N802 - API de Qt
        super().setRowCount(rows)
        self._update_empty_state()

    def resizeEvent(self, event) -> None:  # noqa: N802 - API de Qt
        super().resizeEvent(event)
        self._update_empty_state()

    def _update_empty_state(self) -> None:
        visible = self.rowCount() == 0
        self._empty_label.setVisible(visible)
        if visible:
            self._empty_label.setGeometry(self.viewport().rect())
