def format_currency(amount: float, currency: str = "CRC") -> str:
    """Formatea un monto como moneda (₡ o $) con separadores de miles."""
    if currency.upper() == "USD":
        return f"${amount:,.2f}"
    return f"₡{amount:,.2f}"


_UNIDADES = (
    "", "UNO", "DOS", "TRES", "CUATRO", "CINCO", "SEIS", "SIETE", "OCHO",
    "NUEVE", "DIEZ", "ONCE", "DOCE", "TRECE", "CATORCE", "QUINCE",
    "DIECISÉIS", "DIECISIETE", "DIECIOCHO", "DIECINUEVE", "VEINTE",
)
_DECENAS = ("", "", "VEINTE", "TREINTA", "CUARENTA", "CINCUENTA", "SESENTA",
            "SETENTA", "OCHENTA", "NOVENTA")
_CENTENAS = ("", "CIENTO", "DOSCIENTOS", "TRESCIENTOS", "CUATROCIENTOS",
             "QUINIENTOS", "SEISCIENTOS", "SETECIENTOS", "OCHOCIENTOS",
             "NOVECIENTOS")


def _tres_digitos(numero: int) -> str:
    if numero == 0:
        return ""
    if numero == 100:
        return "CIEN"
    partes: list[str] = []
    centenas, resto = divmod(numero, 100)
    if centenas:
        partes.append(_CENTENAS[centenas])
    if resto:
        if resto <= 20:
            partes.append(_UNIDADES[resto])
        elif resto < 30:
            partes.append("VEINTI" + _UNIDADES[resto - 20])
        else:
            decenas, unidades = divmod(resto, 10)
            texto = _DECENAS[decenas]
            if unidades:
                texto += " Y " + _UNIDADES[unidades]
            partes.append(texto)
    return " ".join(partes)


def _antes_de_mil(texto: str) -> str:
    """Ajusta el final para ir delante de mil/millón (uno→un, veintiuno→veintiún)."""
    return texto.replace("VEINTIUNO", "VEINTIÚN").replace("UNO", "UN")


def _numero_en_letras(numero: int) -> str:
    if numero == 0:
        return "CERO"
    if numero < 1000:
        return _tres_digitos(numero)
    millones, resto = divmod(numero, 1_000_000)
    miles, unidades = divmod(resto, 1000)
    partes: list[str] = []
    if millones:
        if millones == 1:
            partes.append("UN MILLÓN")
        else:
            partes.append(_antes_de_mil(_numero_en_letras(millones))
                         + " MILLONES")
    if miles:
        if miles == 1:
            partes.append("MIL")
        else:
            partes.append(_antes_de_mil(_tres_digitos(miles)) + " MIL")
    if unidades:
        partes.append(_tres_digitos(unidades))
    return " ".join(partes)


def monto_en_letras(monto: float, currency: str = "CRC") -> str:
    """Monto en letras para tickets: 'QUINCE MIL COLONES CON 00/100'."""
    try:
        total = float(monto or 0)
    except (TypeError, ValueError):
        total = 0.0
    negativo = total < 0
    total = abs(round(total, 2))
    entero = int(total)
    centavos = int(round((total - entero) * 100))
    if centavos == 100:
        entero += 1
        centavos = 0
    moneda = "DÓLARES" if str(currency).upper() == "USD" else "COLONES"
    texto = f"{_numero_en_letras(entero)} {moneda}"
    if centavos:
        texto += f" CON {centavos:02d}/100"
    return ("MENOS " + texto) if negativo else texto


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
    """QDoubleSpinBox que ignora la rueda del mouse para evitar cambios accidentales.

    Con mínimo 0, el campo se muestra vacío en vez de "0.00" (se ve claro si
    ya tiene un valor o no, y evita guardar un 0 sin darse cuenta).
    """

    def wheelEvent(self, event):
        event.ignore()

    def setRange(self, minimo: float, maximo: float) -> None:
        super().setRange(minimo, maximo)
        self.setSpecialValueText(" " if minimo == 0 else "")


from PyQt6.QtWidgets import QSpinBox


class NoWheelIntSpinBox(QSpinBox):
    """QSpinBox entero que ignora la rueda del mouse para evitar cambios accidentales.

    Con mínimo 0, el campo se muestra vacío en vez de "0".
    """

    def wheelEvent(self, event):
        event.ignore()

    def setRange(self, minimo: int, maximo: int) -> None:
        super().setRange(minimo, maximo)
        self.setSpecialValueText(" " if minimo == 0 else "")


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
