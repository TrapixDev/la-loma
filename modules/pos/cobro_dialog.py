"""Diálogo moderno de cobro con monto por método, Mixto y cambio en tiempo real."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from utils.helpers import format_currency

_COBRO_QSS = """
QDialog#CobroDialog {
    background-color: #14161c;
    border: 1px solid #2fbf71;
}
QLabel#cobroTotalLabel {
    color: #2fbf71;
    font-size: 34px;
    font-weight: bold;
}
QLabel#titleLabel {
    color: #ffffff;
    font-size: 18px;
    font-weight: bold;
}
QLabel#subtitleLabel {
    color: #9aa4b2;
    font-size: 12px;
}
QLabel#changeLabel {
    color: #2fbf71;
    font-size: 22px;
    font-weight: bold;
}
QLabel#errorLabel {
    color: #ef4444;
    font-size: 12px;
    font-weight: bold;
}
QPushButton#methodButton {
    background-color: #1f2530;
    color: #b9c2cf;
    border: 2px solid #2e3440;
    border-radius: 8px;
    padding: 10px 6px;
    font-size: 13px;
    font-weight: bold;
    min-width: 100px;
    min-height: 22px;
}
QPushButton#methodButton:hover {
    background-color: #262d3a;
    border-color: #3d4557;
}
QPushButton#methodButton:checked {
    background-color: #3b82f6;
    border-color: #3b82f6;
    color: #ffffff;
}
QPushButton#cobrarButton {
    background-color: #2fbf71;
    color: #0e1a12;
    border: none;
    border-radius: 8px;
    padding: 14px 20px;
    font-size: 18px;
    font-weight: bold;
    min-height: 28px;
}
QPushButton#cobrarButton:hover {
    background-color: #3dd081;
}
QPushButton#cobrarButton:pressed {
    background-color: #279d5c;
}
QPushButton#cobrarButton:disabled {
    background-color: #1a1e26;
    color: #5b6472;
}
QLineEdit#cashInput {
    background-color: #1f2530;
    color: #ffffff;
    border: 2px solid #3b82f6;
    border-radius: 8px;
    padding: 10px 14px;
    font-size: 22px;
    font-weight: bold;
    min-height: 22px;
}
QLineEdit#cashInput:focus {
    border-color: #2fbf71;
}
QComboBox#mixMethod {
    background-color: #262b36;
    color: #e6e9ef;
    border: 2px solid #3b82f6;
    border-radius: 8px;
    padding: 8px 10px;
    font-size: 13px;
    font-weight: bold;
    min-width: 140px;
}
QPushButton#fillButton {
    background-color: #1f2530;
    color: #3b82f6;
    border: 2px solid #3b82f6;
    border-radius: 8px;
    padding: 8px 12px;
    font-size: 13px;
    font-weight: bold;
}
QPushButton#fillButton:hover {
    background-color: #262d3a;
}
QPushButton#successButton {
    background-color: #2fbf71;
    color: #0e1a12;
    border: none;
    border-radius: 8px;
    padding: 12px 20px;
    font-size: 15px;
    font-weight: bold;
}
QPushButton#successButton:hover {
    background-color: #3dd081;
}
QPushButton#closeButton {
    background-color: #374151;
    color: #ffffff;
    border: none;
    border-radius: 8px;
    padding: 12px 20px;
    font-size: 15px;
    font-weight: bold;
}
QPushButton#closeButton:hover {
    background-color: #4b5563;
}
QFrame#separator {
    background-color: #2e3440;
    max-height: 1px;
}
"""

_METHODS = ("Efectivo", "Tarjeta", "Sinpe")


class CobroDialog(QDialog):
    """Diálogo de cobro con monto por método y opción de pago Mixto."""

    def __init__(self, total: float, exchange_rate: float = 520.0,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.total = total
        self.total_crc = total  # Guardar el total original en CRC
        self.exchange_rate = exchange_rate
        self.currency = "CRC"  # Moneda por defecto
        self.method = "Efectivo"
        self.cash_received = 0.0
        self.change = 0.0
        self.payment_details: list[dict] = []
        self.print_requested = False
        self.invoice_number = ""
        self._root: QVBoxLayout | None = None
        self.setObjectName("CobroDialog")
        self.setWindowTitle("Cobrar")
        self.setFixedSize(800, 620)
        self.setStyleSheet(_COBRO_QSS)
        self._build_ui()
        self._update_change()

    # ---------- construcción ----------

    def _build_amount_field(self) -> QLineEdit:
        field = QLineEdit()
        field.setObjectName("cashInput")
        field.setPlaceholderText("0")
        field.setAlignment(Qt.AlignmentFlag.AlignRight)
        return field

    def _build_ui(self) -> None:
        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(24, 18, 24, 18)
        self._root.setSpacing(10)

        title = QLabel("PAGAR")
        title.setObjectName("titleLabel")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._root.addWidget(title)

        # Toggle moneda CRC/USD
        currency_row = QHBoxLayout()
        currency_row.setSpacing(8)
        currency_row.addStretch()
        self.crc_btn = QPushButton("₡ CRC")
        self.crc_btn.setObjectName("methodButton")
        self.crc_btn.setCheckable(True)
        self.crc_btn.setChecked(True)
        self.usd_btn = QPushButton("$ USD")
        self.usd_btn.setObjectName("methodButton")
        self.usd_btn.setCheckable(True)
        self._currency_group = QButtonGroup(self)
        self._currency_group.setExclusive(True)
        self._currency_group.addButton(self.crc_btn)
        self._currency_group.addButton(self.usd_btn)
        self.crc_btn.clicked.connect(lambda: self._set_currency("CRC"))
        self.usd_btn.clicked.connect(lambda: self._set_currency("USD"))
        currency_row.addWidget(self.crc_btn)
        currency_row.addWidget(self.usd_btn)
        currency_row.addStretch()
        self._root.addLayout(currency_row)

        self.total_display = QLabel(format_currency(self.total))
        self.total_display.setObjectName("cobroTotalLabel")
        self.total_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._root.addWidget(self.total_display)

        self.context_label = QLabel("")
        self.context_label.setObjectName("subtitleLabel")
        self.context_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._root.addWidget(self.context_label)

        separator = QFrame()
        separator.setObjectName("separator")
        separator.setFrameShape(QFrame.Shape.HLine)
        self._root.addWidget(separator)

        method_label = QLabel("Método de pago")
        method_label.setObjectName("subtitleLabel")
        method_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._root.addWidget(method_label)

        method_row = QHBoxLayout()
        method_row.setSpacing(8)
        self.method_buttons: dict[str, QPushButton] = {}
        self._method_group = QButtonGroup(self)
        self._method_group.setExclusive(True)
        for name in (*_METHODS, "Mixto"):
            btn = QPushButton(name)
            btn.setObjectName("methodButton")
            btn.setCheckable(True)
            self._method_group.addButton(btn)
            self.method_buttons[name] = btn
            method_row.addWidget(btn)
            btn.clicked.connect(lambda checked, n=name: self._select_method(n))
        self.method_buttons["Efectivo"].setChecked(True)
        self._root.addLayout(method_row)

        self.pages = QStackedWidget()
        self.pages.addWidget(self._build_single_page())
        self.pages.addWidget(self._build_mix_page())
        self._root.addWidget(self.pages)

        self._root.addStretch()

        self.cobrar_btn = QPushButton("COBRAR")
        self.cobrar_btn.setObjectName("cobrarButton")
        self.cobrar_btn.clicked.connect(self._on_cobrar)
        self._root.addWidget(self.cobrar_btn)
        self._apply_currency_symbols()

    def _build_single_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.amount_label = QLabel("Efectivo recibido:")
        self.amount_label.setObjectName("subtitleLabel")
        layout.addWidget(self.amount_label)

        self.cash_input = self._build_amount_field()
        self.cash_input.returnPressed.connect(self._on_return_pressed)
        self.cash_input.textChanged.connect(self._update_change)
        layout.addWidget(self.cash_input)

        single_change_row = QHBoxLayout()
        change_text = QLabel("Vuelto:")
        change_text.setObjectName("subtitleLabel")
        self.change_display = QLabel(format_currency(0))
        self.change_display.setObjectName("changeLabel")
        single_change_row.addWidget(change_text)
        single_change_row.addStretch()
        single_change_row.addWidget(self.change_display)
        layout.addLayout(single_change_row)

        self.error_label = QLabel("")
        self.error_label.setObjectName("errorLabel")
        self.error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.error_label)
        layout.addStretch()
        return page

    def _build_mix_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.mix_method_a = QLabel("Efectivo")
        self.mix_method_a.setObjectName("subtitleLabel")
        self.mix_method_a.setFixedWidth(80)
        self.mix_amount_a = self._build_amount_field()

        self.mix_method_b = QComboBox()
        self.mix_method_b.setObjectName("mixMethod")
        self.mix_method_b.addItems(["Tarjeta", "Sinpe"])
        self.mix_amount_b = self._build_amount_field()

        row_a = QHBoxLayout()
        row_a.setSpacing(8)
        row_a.addWidget(self.mix_method_a)
        row_a.addWidget(self.mix_amount_a, 1)
        layout.addLayout(row_a)

        row_b = QHBoxLayout()
        row_b.setSpacing(8)
        row_b.addWidget(self.mix_method_b)
        row_b.addWidget(self.mix_amount_b, 1)
        layout.addLayout(row_b)

        self.mix_fill_btn = QPushButton("Completar falta con el otro método")
        self.mix_fill_btn.setObjectName("fillButton")
        self.mix_fill_btn.clicked.connect(self._fill_missing)
        layout.addWidget(self.mix_fill_btn)

        mix_status_row = QHBoxLayout()
        mix_status_text = QLabel("Total ingresado:")
        mix_status_text.setObjectName("subtitleLabel")
        self.mix_total_display = QLabel(format_currency(0))
        self.mix_total_display.setObjectName("changeLabel")
        mix_status_row.addWidget(mix_status_text)
        mix_status_row.addStretch()
        mix_status_row.addWidget(self.mix_total_display)
        layout.addLayout(mix_status_row)

        self.mix_status_label = QLabel("")
        self.mix_status_label.setObjectName("errorLabel")
        self.mix_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.mix_status_label)

        self.mix_change_display = QLabel(format_currency(0))
        self.mix_change_display.setObjectName("changeLabel")
        self.mix_change_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.mix_change_display)

        self.mix_amount_a.textChanged.connect(self._update_change)
        self.mix_amount_b.textChanged.connect(self._update_change)
        self.mix_amount_a.returnPressed.connect(self._on_cobrar)
        self.mix_amount_b.returnPressed.connect(self._on_cobrar)

        layout.addStretch()
        return page

    # ---------- lógica de métodos ----------

    def _select_method(self, name: str) -> None:
        self.method = name
        if name == "Mixto":
            self.pages.setCurrentIndex(1)
        else:
            self.pages.setCurrentIndex(0)
            self._update_amount_label()
            self.cash_input.setFocus()
        self._update_change()

    def _set_currency(self, currency: str) -> None:
        """Cambia la moneda de cobro entre CRC y USD.

        Los montos ya digitados se convierten (100000 -> 192.31) para que
        ninguna cifra de la moneda anterior se interprete en la nueva.
        """
        if currency == self.currency:
            return
        for field in (self.cash_input, self.mix_amount_a, self.mix_amount_b):
            self._convert_field(field)
        self.currency = currency
        if currency == "USD":
            self.total = round(self.total_crc / self.exchange_rate, 2) if self.exchange_rate > 0 else 0
        else:
            self.total = self.total_crc
        self._apply_currency_symbols()
        self._update_change()

    def _currency_symbol(self) -> str:
        return "₡" if self.currency == "CRC" else "$"

    def _convert_field(self, field: QLineEdit) -> None:
        """Convierte el monto del campo a la nueva moneda."""
        value = self._parse_amount(field.text())
        if value <= 0 or self.exchange_rate <= 0:
            return
        if self.currency == "USD":
            new_value = round(value * self.exchange_rate, 2)
        else:
            new_value = round(value / self.exchange_rate, 2)
        field.setText(f"{new_value:,.2f}")

    def _apply_currency_symbols(self) -> None:
        """Actualiza placeholders y etiquetas con la moneda vigente."""
        symbol = self._currency_symbol()
        for field in (self.cash_input, self.mix_amount_a, self.mix_amount_b):
            field.setPlaceholderText(f"{symbol} 0")
        self._update_amount_label()

    def _update_amount_label(self) -> None:
        if self.method == "Mixto":
            return
        names = {"Efectivo": "Efectivo recibido",
                 "Tarjeta": "Monto de Tarjeta",
                 "Sinpe": "Monto SINPE"}
        self.amount_label.setText(
            f"{names.get(self.method, 'Monto recibido')} ({self._currency_symbol()}):")

    def _to_crc(self, amount: float) -> float:
        """Convierte un monto de la moneda actual a CRC."""
        if self.currency == "USD":
            return round(amount * self.exchange_rate, 2)
        return amount

    def _from_crc(self, amount_crc: float) -> float:
        """Convierte un monto de CRC a la moneda actual."""
        if self.currency == "USD":
            return round(amount_crc / self.exchange_rate, 2) if self.exchange_rate > 0 else 0
        return amount_crc

    def _parse_amount(self, text: str) -> float:
        cleaned = text.strip().replace(",", "").replace("₡", "").replace("$", "")
        if not cleaned:
            return 0.0
        try:
            return float(cleaned)
        except ValueError:
            return 0.0

    def _parse_cash(self) -> float:
        return self._parse_amount(self.cash_input.text())

    def _fill_missing(self) -> None:
        amount_a = self._parse_amount(self.mix_amount_a.text())
        if amount_a <= 0:
            return
        missing = round(self.total - amount_a, 2)
        if missing <= 0:
            self.mix_amount_b.setText("0")
            return
        self.mix_amount_b.setText(f"{missing:,.2f}")

    # ---------- validación ----------

    def _single_values(self) -> tuple[float, float]:
        cash = self._parse_cash()
        change = max(0.0, cash - self.total)
        return cash, change

    def _mix_values(self) -> tuple[float, float, list[dict]]:
        amount_a = self._parse_amount(self.mix_amount_a.text())
        amount_b = self._parse_amount(self.mix_amount_b.text())
        method_b = self.mix_method_b.currentText()
        details = [{"method": "Efectivo", "amount": amount_a},
                   {"method": method_b, "amount": amount_b}]
        total_in = round(amount_a + amount_b, 2)
        change = max(0.0, total_in - self.total)
        return total_in, change, details

    def _update_change(self) -> None:
        if self.method == "Mixto":
            self._update_mix()
        else:
            self._update_single()

    def _update_single(self) -> None:
        cash, change = self._single_values()
        remaining = max(0.0, round(self.total - cash, 2))
        self.total_display.setText(format_currency(remaining, self.currency))
        self.context_label.setText(
            f"Total {format_currency(self.total, self.currency)} · "
            f"Ingresado {format_currency(cash, self.currency)}")
        self.change_display.setText(format_currency(change, self.currency))
        if cash <= 0:
            self.error_label.setText("")
            self.cobrar_btn.setEnabled(False)
        elif cash < self.total:
            self.error_label.setText(
                f"Faltan {format_currency(self.total - cash, self.currency)}")
            self.cobrar_btn.setEnabled(False)
        else:
            self.error_label.setText("")
            self.cobrar_btn.setEnabled(True)

    def _update_mix(self) -> None:
        total_in, change, _ = self._mix_values()
        remaining = max(0.0, round(self.total - total_in, 2))
        self.total_display.setText(format_currency(remaining, self.currency))
        self.context_label.setText(f"Falta por recibir: {format_currency(remaining, self.currency)}")
        self.mix_total_display.setText(format_currency(total_in, self.currency))
        self.mix_change_display.setText(format_currency(change, self.currency))
        if total_in <= 0:
            self.mix_status_label.setText("")
            self.cobrar_btn.setEnabled(False)
        elif total_in < self.total:
            self.mix_status_label.setText(
                f"Faltan {format_currency(self.total - total_in, self.currency)}")
            self.cobrar_btn.setEnabled(False)
        else:
            self.mix_status_label.setText("")
            self.cobrar_btn.setEnabled(True)

    def _on_return_pressed(self) -> None:
        """Enter en el campo de Efectivo: cobra si alcanza, o pasa el faltante
        a un segundo método (Mixto) si el monto es insuficiente."""
        if self.cobrar_btn.isEnabled():
            self._on_cobrar()
            return
        self._switch_to_mixto()

    def _switch_to_mixto(self) -> None:
        """Pasa a la página Mixto con el efectivo ingresado y el faltante
        pre-llenado en el otro método (Tarjeta/Sinpe)."""
        if self.method != "Efectivo":
            return
        cash = self._parse_cash()
        if cash <= 0:
            return
        missing = round(self.total - cash, 2)
        if missing <= 0:
            return
        self.method = "Mixto"
        self.method_buttons["Mixto"].setChecked(True)
        self.pages.setCurrentIndex(1)
        self.mix_amount_a.setText(f"{cash:,.2f}")
        self.mix_amount_b.setText(f"{missing:,.2f}")
        self._update_change()
        self.mix_status_label.setText(
            f"Faltan {format_currency(missing, self.currency)} - se colocaron en "
            f"{self.mix_method_b.currentText()}. Confirme y presione COBRAR.")
        self.mix_method_b.setFocus()

    def _on_cobrar(self) -> None:
        if not self.cobrar_btn.isEnabled():
            return
        if self.method == "Mixto":
            total_in, change, details = self._mix_values()
            if total_in < self.total:
                QMessageBox.warning(
                    self, "Monto insuficiente",
                    f"El total ingresado ({format_currency(total_in, self.currency)}) es menor "
                    f"al total ({format_currency(self.total, self.currency)}).\n"
                    f"Faltan {format_currency(self.total - total_in, self.currency)}.")
                return
            self.cash_received = self._parse_amount(
                self.mix_amount_a.text())
            self.change = change
            self.payment_details = details
        else:
            cash = self._parse_cash()
            if cash < self.total:
                QMessageBox.warning(
                    self, "Monto insuficiente",
                    f"El {self.method.lower()} recibido ({format_currency(cash, self.currency)}) "
                    f"es menor al total ({format_currency(self.total, self.currency)}).\n"
                    f"Faltan {format_currency(self.total - cash, self.currency)}.")
                return
            self.cash_received = cash
            self.change = cash - self.total
            self.payment_details = [{"method": self.method, "amount": cash}]
        self._show_success()

    # ---------- pantalla de éxito ----------

    def _hide_all_root_widgets(self) -> None:
        if self._root is None:
            return
        for index in range(self._root.count()):
            item = self._root.itemAt(index)
            if item is None:
                continue
            widget = item.widget()
            if widget is not None:
                widget.hide()

    def _show_success(self) -> None:
        self._hide_all_root_widgets()

        success_root = QVBoxLayout()
        success_root.setContentsMargins(0, 0, 0, 0)
        success_root.setSpacing(10)

        done_label = QLabel("¡VENTA EXITOSA!")
        done_label.setObjectName("titleLabel")
        done_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        success_root.addWidget(done_label)

        if self.invoice_number:
            num_label = QLabel(f"Factura: {self.invoice_number}")
            num_label.setObjectName("totalLabel")
            num_label.setStyleSheet("font-size:20px; color:#ffffff;")
            num_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            success_root.addWidget(num_label)

        total_label = QLabel(f"Total: {format_currency(self.total, self.currency)}")
        total_label.setObjectName("totalLabel")
        total_label.setStyleSheet("font-size:18px; color:#2fbf71;")
        total_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        success_root.addWidget(total_label)

        if self.payment_details:
            breakdown = " + ".join(
                f"{d['method']} {format_currency(d['amount'], self.currency)}"
                for d in self.payment_details)
            method_label = QLabel(f"Pago con: {breakdown}")
            method_label.setObjectName("subtitleLabel")
            method_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            method_label.setWordWrap(True)
            success_root.addWidget(method_label)
        else:
            method_label = QLabel(f"Pago con: {self.method}")
            method_label.setObjectName("subtitleLabel")
            method_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            success_root.addWidget(method_label)

        if self.change > 0:
            change_label = QLabel(f"Vuelto: {format_currency(self.change, self.currency)}")
            change_label.setObjectName("changeLabel")
            change_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            success_root.addWidget(change_label)

        success_root.addStretch()

        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        print_btn = QPushButton("Imprimir")
        print_btn.setObjectName("successButton")
        print_btn.clicked.connect(self._on_print)
        btn_row.addWidget(print_btn)

        close_btn = QPushButton("Cerrar")
        close_btn.setObjectName("closeButton")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        success_root.addLayout(btn_row)

        if self._root is not None:
            self._root.addLayout(success_root)
            self.setFixedHeight(600)

    def _on_print(self) -> None:
        self.print_requested = True
        self.accept()

    def result(self) -> dict:
        return {
            "method": self.method,
            "cash_received": self.cash_received,
            "change": self.change,
            "payment_details": list(self.payment_details),
            "print_requested": self.print_requested,
            "currency": self.currency,
            "exchange_rate": self.exchange_rate,
            "total_crc": self.total_crc,
        }