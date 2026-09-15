"""Diálogo de descuento manual para el carrito (porcentaje o monto fijo)."""

from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from utils.helpers import NoWheelComboBox, NoWheelSpinBox

MAX_MONTO = 99_999_999.0


class ManualDiscountDialog(QDialog):
    """Pide un descuento manual: % o monto, con motivo opcional."""

    def __init__(self, actual: dict | None = None,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.actual = actual or {}
        self.resultado: dict | None = None
        self.setWindowTitle("Descuento manual")
        self.setMinimumWidth(380)
        self._setup_ui()
        self._load()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        hint = QLabel(
            "Se aplica sobre el total del carrito (después de las "
            "promociones) y se reparte por línea para la factura.")
        hint.setWordWrap(True)
        hint.setStyleSheet("font-size: 13px; color: #8b93a3;")
        layout.addWidget(hint)

        form = QFormLayout()
        form.setSpacing(10)

        self.mode_combo = NoWheelComboBox()
        self.mode_combo.addItem("Porcentaje (%)", "percent")
        self.mode_combo.addItem("Monto (₡)", "amount")
        self.mode_combo.currentIndexChanged.connect(self._update_range)
        form.addRow("Tipo:", self.mode_combo)

        self.value_input = NoWheelSpinBox()
        self.value_input.setDecimals(2)
        form.addRow("Valor:", self.value_input)

        self.reason_input = QLineEdit()
        self.reason_input.setPlaceholderText("Motivo (opcional)")
        form.addRow("Motivo:", self.reason_input)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel)
        self.ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.ok_button.setText("Aplicar")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        buttons.accepted.connect(self._apply)
        buttons.rejected.connect(self.reject)
        if self.actual:
            quitar = buttons.addButton("Quitar descuento",
                                       QDialogButtonBox.ButtonRole.DestructiveRole)
            quitar.clicked.connect(self._clear)
        layout.addWidget(buttons)
        self._update_range()

    def _update_range(self) -> None:
        if self.mode_combo.currentData() == "percent":
            self.value_input.setRange(0.0, 100.0)
            self.value_input.setSuffix(" %")
            self.value_input.setPrefix("")
        else:
            self.value_input.setRange(0.0, MAX_MONTO)
            self.value_input.setSuffix("")
            self.value_input.setPrefix("₡ ")

    def _load(self) -> None:
        if not self.actual:
            self.value_input.setValue(0.0)
            return
        index = self.mode_combo.findData(self.actual.get("mode", "percent"))
        if index >= 0:
            self.mode_combo.setCurrentIndex(index)
        self.value_input.setValue(float(self.actual.get("value") or 0.0))
        self.reason_input.setText(self.actual.get("reason", ""))

    def _apply(self) -> None:
        value = float(self.value_input.value())
        if value <= 0:
            QMessageBox.warning(self, "Descuento",
                                "Ingrese un descuento mayor a cero.")
            return
        self.resultado = {
            "mode": self.mode_combo.currentData(),
            "value": value,
            "reason": self.reason_input.text().strip(),
        }
        self.accept()

    def _clear(self) -> None:
        self.resultado = None
        self.accept()
