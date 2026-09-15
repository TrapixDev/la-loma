"""Diálogo de alta/edición de promociones y descripción legible de reglas."""

import json

from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from database.models import Promotion
from modules.promotions.promotion_service import (
    PAYMENT_METHODS,
    TYPE_LABELS,
)
from utils.helpers import EmptyStateTable, NoWheelComboBox, NoWheelSpinBox


def describe_promotion(promotion: Promotion, products_by_id: dict) -> str:
    """Resumen legible de una promoción para la lista de configuración."""
    try:
        params = json.loads(promotion.params or "{}")
    except (TypeError, ValueError):
        params = {}

    def _name(product_id) -> str:
        product = products_by_id.get(int(product_id or 0))
        return getattr(product, "name", f"Producto {product_id}")

    if promotion.type == "bundle":
        return (f"{params.get('percent', 0):g}% en {_name(params.get('discount_product_id'))} "
                f"al llevar {_name(params.get('product_id'))}")
    if promotion.type == "volume":
        tramos = ", ".join(f"{int(t[0])}+ → {float(t[1]):g}%"
                           for t in params.get("tiers") or [])
        return f"{_name(params.get('product_id'))}: {tramos}"
    if promotion.type == "payment":
        metodos = " / ".join(str(m).capitalize()
                             for m in params.get("methods") or [])
        return f"{params.get('percent', 0):g}% pagando con {metodos}"
    if promotion.type == "financing":
        meses = ", ".join(str(int(m)) for m in params.get("months") or [])
        return (f"Desde ₡{float(params.get('min_total', 0)):,.0f}: "
                f"{meses} meses sin intereses")
    return ""


class PromotionDialog(QDialog):
    """Formulario de promoción; los campos cambian según el tipo."""

    def __init__(self, service, promotion: Promotion | None = None,
                 products: list | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.service = service
        self.promotion = promotion
        self.products = products or []
        self.products_by_id = {p.id: p for p in self.products}
        self.saved = False
        self.setWindowTitle("Editar promoción" if promotion
                            else "Nueva promoción")
        self.setMinimumWidth(520)
        self._setup_ui()
        self._load()

    # ---------- UI ----------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        form = QFormLayout()
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Ej. Combo cama + lámpara")
        form.addRow("Nombre:", self.name_input)

        self.type_combo = NoWheelComboBox()
        for key, label in TYPE_LABELS.items():
            self.type_combo.addItem(label, key)
        self.type_combo.currentIndexChanged.connect(self._show_type_fields)
        form.addRow("Tipo:", self.type_combo)

        self.active_check = QCheckBox("Activa")
        self.active_check.setChecked(True)
        form.addRow("", self.active_check)
        layout.addLayout(form)

        self.pages = QStackedWidget()
        self.pages.addWidget(self._build_bundle_page())
        self.pages.addWidget(self._build_volume_page())
        self.pages.addWidget(self._build_payment_page())
        self.pages.addWidget(self._build_financing_page())
        layout.addWidget(self.pages)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Guardar")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _product_combo(self) -> NoWheelComboBox:
        combo = NoWheelComboBox()
        combo.addItem("— Seleccione —", 0)
        for product in self.products:
            combo.addItem(product.name, product.id)
        return combo

    def _build_bundle_page(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        self.bundle_required = self._product_combo()
        self.bundle_target = self._product_combo()
        self.bundle_percent = NoWheelSpinBox()
        self.bundle_percent.setRange(1, 100)
        self.bundle_percent.setDecimals(0)
        self.bundle_percent.setSuffix(" %")
        self.bundle_percent.setValue(15)
        form.addRow("Si el carrito lleva:", self.bundle_required)
        form.addRow("Descontar a:", self.bundle_target)
        form.addRow("Descuento:", self.bundle_percent)
        return page

    def _build_volume_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        form = QFormLayout()
        self.volume_product = self._product_combo()
        form.addRow("Producto:", self.volume_product)
        layout.addLayout(form)

        self.tiers_table = EmptyStateTable("Sin tramos agregados.", 0, 2)
        self.tiers_table.setHorizontalHeaderLabels(["Cantidad (mínimo)", "%"])
        self.tiers_table.verticalHeader().setVisible(False)
        self.tiers_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tiers_table.setMaximumHeight(150)
        self.tiers_table.setColumnWidth(0, 200)
        self.tiers_table.setColumnWidth(1, 80)
        layout.addWidget(self.tiers_table)

        buttons = QHBoxLayout()
        add_btn = QPushButton("Agregar tramo")
        add_btn.clicked.connect(lambda: self._add_tier(2, 5))
        remove_btn = QPushButton("Quitar tramo")
        remove_btn.setObjectName("dangerButton")
        remove_btn.clicked.connect(self._remove_tier)
        buttons.addWidget(add_btn)
        buttons.addWidget(remove_btn)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        return page

    def _build_payment_page(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        self.payment_checks: dict[str, QCheckBox] = {}
        for method in PAYMENT_METHODS:
            check = QCheckBox(method.capitalize())
            self.payment_checks[method] = check
            form.addRow("", check)
        self.payment_percent = NoWheelSpinBox()
        self.payment_percent.setRange(1, 100)
        self.payment_percent.setDecimals(0)
        self.payment_percent.setSuffix(" %")
        self.payment_percent.setValue(5)
        form.addRow("Descuento:", self.payment_percent)
        hint = QLabel("El pago mixto no aplica descuento por método.")
        hint.setObjectName("settingsHint")
        form.addRow("", hint)
        return page

    def _build_financing_page(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        self.financing_min = NoWheelSpinBox()
        self.financing_min.setRange(1.0, 99_999_999.0)
        self.financing_min.setDecimals(0)
        self.financing_min.setPrefix("₡ ")
        self.financing_min.setValue(300000)
        self.financing_months = QLineEdit("3,6,12")
        self.financing_months.setPlaceholderText("Ej. 3,6,12")
        form.addRow("Monto mínimo:", self.financing_min)
        form.addRow("Plazos (meses):", self.financing_months)
        hint = QLabel("Plan informativo: la cuenta muestra la cuota sugerida.")
        hint.setObjectName("settingsHint")
        form.addRow("", hint)
        return page

    # ---------- datos ----------

    def _show_type_fields(self) -> None:
        index = self.type_combo.currentIndex()
        if 0 <= index < self.pages.count():
            self.pages.setCurrentIndex(index)

    def _add_tier(self, qty: int = 2, percent: int = 5) -> None:
        row = self.tiers_table.rowCount()
        self.tiers_table.insertRow(row)
        self.tiers_table.setItem(row, 0, QTableWidgetItem(str(qty)))
        self.tiers_table.setItem(row, 1, QTableWidgetItem(str(percent)))

    def _remove_tier(self) -> None:
        row = self.tiers_table.currentRow()
        if row >= 0:
            self.tiers_table.removeRow(row)

    def _set_combo_product(self, combo: NoWheelComboBox, product_id) -> None:
        index = combo.findData(int(product_id or 0))
        if index >= 0:
            combo.setCurrentIndex(index)

    def _load(self) -> None:
        if self.promotion is None:
            self._add_tier(4, 10)
            self._add_tier(6, 20)
            self.payment_checks["efectivo"].setChecked(True)
            self._show_type_fields()
            return
        promo = self.promotion
        self.name_input.setText(promo.name)
        index = self.type_combo.findData(promo.type)
        if index >= 0:
            self.type_combo.setCurrentIndex(index)
        self.type_combo.setEnabled(False)
        self.active_check.setChecked(bool(promo.active))
        params = self.service.params_dict(promo)
        if promo.type == "bundle":
            self._set_combo_product(self.bundle_required, params.get("product_id"))
            self._set_combo_product(self.bundle_target,
                                    params.get("discount_product_id"))
            self.bundle_percent.setValue(float(params.get("percent") or 15))
        elif promo.type == "volume":
            self._set_combo_product(self.volume_product, params.get("product_id"))
            self.tiers_table.setRowCount(0)
            for tier in params.get("tiers") or []:
                self._add_tier(int(tier[0]), float(tier[1]))
        elif promo.type == "payment":
            for method in params.get("methods") or []:
                if method in self.payment_checks:
                    self.payment_checks[method].setChecked(True)
            self.payment_percent.setValue(float(params.get("percent") or 5))
        elif promo.type == "financing":
            self.financing_min.setValue(float(params.get("min_total") or 300000))
            self.financing_months.setText(
                ",".join(str(int(m)) for m in params.get("months") or [3, 6, 12]))
        self._show_type_fields()

    def _params(self) -> dict:
        promotion_type = self.type_combo.currentData()
        if promotion_type == "bundle":
            return {
                "product_id": self.bundle_required.currentData(),
                "discount_product_id": self.bundle_target.currentData(),
                "percent": float(self.bundle_percent.value()),
            }
        if promotion_type == "volume":
            tiers = []
            for row in range(self.tiers_table.rowCount()):
                qty_item = self.tiers_table.item(row, 0)
                pct_item = self.tiers_table.item(row, 1)
                if qty_item is None or pct_item is None:
                    continue
                try:
                    tiers.append([int(qty_item.text()), float(pct_item.text())])
                except ValueError:
                    raise ValueError(
                        "Los tramos deben ser números (cantidad y porcentaje).")
            return {"product_id": self.volume_product.currentData(),
                    "tiers": tiers}
        if promotion_type == "payment":
            methods = [method for method, check in self.payment_checks.items()
                       if check.isChecked()]
            return {"methods": methods,
                    "percent": float(self.payment_percent.value())}
        if promotion_type == "financing":
            months = []
            for part in self.financing_months.text().replace(";", ",").split(","):
                part = part.strip()
                if not part:
                    continue
                try:
                    months.append(int(part))
                except ValueError:
                    raise ValueError("Los plazos deben ser números de meses.")
            return {"min_total": float(self.financing_min.value()),
                    "months": months}
        return {}

    def _save(self) -> None:
        try:
            params = self._params()
            name = self.name_input.text().strip()
            active = self.active_check.isChecked()
            if self.promotion is None:
                self.service.create(name, self.type_combo.currentData(),
                                    params, active)
            else:
                promo = self.promotion
                promo.name = name
                promo.type = self.type_combo.currentData()
                promo.params = json.dumps(params, ensure_ascii=False)
                promo.active = active
                self.service.update(promo)
        except ValueError as exc:
            QMessageBox.warning(self, "Promoción", str(exc))
            return
        except Exception as exc:
            QMessageBox.critical(self, "Promoción",
                                 f"No se pudo guardar:\n{exc}")
            return
        self.saved = True
        self.accept()
