"""Reportes mensuales y anuales (2026-2040) ligados a ventas y gastos."""

import csv
from datetime import date, datetime, timedelta

from PyQt6.QtCore import QDate, Qt
from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
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

from utils.helpers import format_currency, NoWheelSpinBox, NoWheelComboBox
from modules.documentos import reimprimir_factura, generar_nota_credito

MONTH_NAMES = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
]
YEAR_MIN = 2026
YEAR_MAX = 2040
PAYMENT_METHODS = ["Efectivo", "Tarjeta", "Transferencia", "Otro"]


def _sale_date_text(value) -> str:
    if isinstance(value, datetime):
        return value.strftime("%d/%m/%Y %H:%M")
    if isinstance(value, date):
        return value.strftime("%d/%m/%Y")
    text = str(value)
    if len(text) >= 16:
        return text[:16]
    return text


def _fmt_day(value) -> str:
    text = str(value)
    if len(text) >= 10:
        return text[8:10] + "/" + text[5:7] + "/" + text[:4]
    return text


class ExpenseDialog(QDialog):
    """Formulario discreto para registrar un gasto."""

    def __init__(self, services: dict, parent: QWidget | None = None):
        super().__init__(parent)
        self.services = services
        self.setWindowTitle("Registrar gasto")
        self.setMinimumWidth(380)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.amount_input = NoWheelSpinBox()
        self.amount_input.setRange(0.0, 99_999_999.0)
        self.amount_input.setDecimals(2)
        self.amount_input.setPrefix("₡ ")
        form.addRow("Monto:", self.amount_input)

        self.category_input = NoWheelComboBox()
        self.category_input.setEditable(True)
        try:
            categories = self.services["expenses"].get_categories()
        except Exception:
            categories = []
        for name in categories:
            self.category_input.addItem(name)
        if not categories:
            self.category_input.addItem("Otros")
        form.addRow("Categoría:", self.category_input)

        self.description_input = QLineEdit()
        self.description_input.setPlaceholderText("Opcional")
        form.addRow("Descripción:", self.description_input)

        self.method_input = NoWheelComboBox()
        for method in PAYMENT_METHODS:
            self.method_input.addItem(method)
        form.addRow("Método de pago:", self.method_input)

        self.date_input = QDateEdit(QDate.currentDate())
        self.date_input.setCalendarPopup(True)
        self.date_input.setDisplayFormat("dd/MM/yyyy")
        form.addRow("Fecha:", self.date_input)

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Guardar")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _save(self) -> None:
        amount = self.amount_input.value()
        if amount <= 0:
            QMessageBox.warning(self, "Monto inválido", "Ingrese un monto mayor a cero.")
            return
        category = self.category_input.currentText().strip() or "Otros"
        date_text = self.date_input.date().toString("yyyy-MM-dd")
        try:
            self.services["expenses"].add_expense(
                amount,
                category,
                self.description_input.text().strip(),
                self.method_input.currentText(),
                date_text,
            )
        except Exception as exc:
            QMessageBox.critical(self, "Error al guardar", f"No se pudo registrar el gasto:\n{exc}")
            return
        self.accept()


_MOTIVOS_NOTA = [
    ("01", "Anula documento de referencia"),
    ("06", "Devolución de mercancía"),
    ("02", "Corrige texto de documento de referencia"),
    ("99", "Otros"),
]


class NotaCreditoDialog(QDialog):
    """Diálogo para emitir una nota de crédito sobre una venta (Hacienda).

    Genera XML+PDF de respaldo, registra la nota y opcionalmente la envía
    al proveedor FE y la imprime.
    """

    def __init__(self, services: dict, sale: dict, parent: QWidget | None = None):
        super().__init__(parent)
        self.services = services
        self.sale = sale
        self.setWindowTitle("Nota de Crédito")
        self.setMinimumWidth(420)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        info = QLabel(
            f"Factura original: <b>{self.sale.get('invoice_number') or ''}</b> — "
            f"Total: <b>{format_currency(float(self.sale.get('total') or 0))}</b>")
        info.setWordWrap(True)
        layout.addWidget(info)

        form = QFormLayout()

        self.motivo_combo = NoWheelComboBox()
        for code, label in _MOTIVOS_NOTA:
            self.motivo_combo.addItem(label, code)
        form.addRow("Motivo:", self.motivo_combo)

        self.monto_input = NoWheelSpinBox()
        self.monto_input.setRange(0.0, 99_999_999.0)
        self.monto_input.setDecimals(2)
        self.monto_input.setPrefix("₡ ")
        self.monto_input.setValue(float(self.sale.get("total") or 0))
        form.addRow("Monto a acreditar:", self.monto_input)

        self.detalle_input = QLineEdit()
        self.detalle_input.setPlaceholderText("Descripción del motivo (obligatorio)")
        form.addRow("Detalle:", self.detalle_input)

        layout.addLayout(form)

        self.enviar_hacienda = QCheckBox("Enviar al proveedor de Hacienda")
        self.enviar_hacienda.setChecked(True)
        layout.addWidget(self.enviar_hacienda)

        self.imprimir = QCheckBox("Imprimir la nota de crédito")
        self.imprimir.setChecked(False)
        layout.addWidget(self.imprimir)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Emitir nota")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _save(self) -> None:
        detalle = self.detalle_input.text().strip()
        if not detalle:
            QMessageBox.warning(self, "Detalle requerido",
                                "Escriba la descripción del motivo de la nota de crédito.")
            return
        if self.monto_input.value() <= 0:
            QMessageBox.warning(self, "Monto inválido", "Ingrese un monto mayor a cero.")
            return

        code = self.motivo_combo.currentData()
        sale_id = int(self.sale.get("id") or 0)
        try:
            clave, nota_id = self._emitir(sale_id, code, detalle)
        except Exception as exc:
            QMessageBox.critical(self, "Nota de crédito", f"No se pudo emitir la nota:\n{exc}")
            return

        self.accept()
        resumen = []
        if nota_id:
            resumen.append(f"Nota de crédito emitida correctamente.")
        if clave:
            resumen.append(f"Clave Hacienda: {clave}")
        QMessageBox.information(self, "Nota de crédito", "\n".join(resumen))

    def _emitir(self, sale_id: int, code: str, detalle: str) -> tuple[str, int]:
        """Registra, documenta y (opcional) envía la nota de crédito."""
        from modules.documentos import xml_factura as _xml, xml_nota_credito as _xmlnc
        db = self.services.get("db")
        company = _xml.cargar_empresa(db) if db else {}
        sale = self.services["cart"].get_sale(sale_id)
        if sale is None:
            raise ValueError("No se encontró la venta original.")
        cliente = self.services["client"].get_by_id(sale.client_id) if sale.client_id \
            else None

        consecutivo = self._next_consecutivo()
        referencia = {
            "tipo_doc": "01",
            "numero": getattr(sale, "hacienda_key", "") or "",
            "fecha_emision": _fecha_iso(getattr(sale, "created_at", "")),
            "codigo": code,
        }
        payload = _xmlnc.build_nota_credito_payload(
            company, sale, sale.items, _totals_sale(sale), consecutivo,
            referencia, motivo=detalle, cliente=cliente)

        clave, estado = self._enviar(payload) if self.enviar_hacienda.isChecked() \
            else ("", "PENDIENTE")

        nota = {
            "invoice_number": f"NC-{int(consecutivo or 0):05d}",
            "created_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "razon": detalle,
            "motivo": detalle,
            "total": self.monto_input.value(),
            "clave": clave,
            "referencia_clave": getattr(sale, "hacienda_key", ""),
        }
        generar_nota_credito(sale, company, nota, cliente=cliente, payload=payload,
                             clave=clave, imprimir=self.imprimir.isChecked())

        nota_id = self.services["reports"].create_credit_note(
            sale_id, detalle, detalle, codigo=code,
            total=self.monto_input.value(), clave=clave, estado=estado)
        return clave, nota_id

    def _next_consecutivo(self) -> str:
        db = self.services.get("db")
        try:
            rows = db.execute_query(
                "SELECT value FROM counters WHERE name = 'credit_note'")
            return str((int(rows[0]["value"]) if rows else 0) + 1).zfill(10)
        except Exception:
            return "1".zfill(10)

    def _enviar(self, payload: dict) -> tuple[str, str]:
        """Envía la nota al proveedor FE. Devuelve (clave, estado) best-effort."""
        try:
            response = self.services["hacienda"].send_electronic_invoice(payload)
        except Exception:
            return "", "PENDIENTE"
        if not response:
            return "", "PENDIENTE"
        clave = str(response.get("clave", ""))
        return clave, ("ACEPTADA" if clave else "ENVIADA")


def _fecha_iso(value) -> str:
    text = str(value or "").strip()
    if "T" in text:
        return text
    if len(text) >= 10:
        return text[:10] + "T00:00:00-06:00"
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S-06:00")


def _totals_sale(sale) -> dict:
    return {"subtotal": sale.subtotal, "discount": sale.discount,
            "tax_amount": sale.tax_amount, "total": sale.total}


class MovimientosDiaDialog(QDialog):
    """Ventana emergente con las ventas y gastos de un día específico."""

    def __init__(self, day: str, movimientos: list[dict],
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(f"Movimientos del día {_fmt_day(day)}")
        self.setMinimumSize(520, 250)
        self.setMaximumHeight(480)
        self._setup_ui(movimientos)

    def _setup_ui(self, movimientos: list[dict]) -> None:
        from PyQt6.QtGui import QBrush, QColor
        from PyQt6.QtWidgets import QScrollArea
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(18, 14, 18, 10)

        title = QLabel(f"Movimientos del {_fmt_day(movimientos[0]['fecha']) if movimientos else ''}")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)

        table = QTableWidget(0, 4)
        table.setHorizontalHeaderLabels(["Tipo", "Detalle", "Método", "Monto"])
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setAlternatingRowColors(True)
        table.setRowCount(len(movimientos))

        color = {
            "VENTA": QColor(34, 197, 94),
            "GASTO": QColor(249, 115, 22),
        }
        for row_index, m in enumerate(movimientos):
            tipo = m["tipo"]
            values = [
                tipo,
                m["detalle"],
                m["metodo"],
                format_currency(m["monto"]),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column == 0:
                    item.setForeground(QBrush(color.get(tipo, QColor(0, 0, 0))))
                table.setItem(row_index, column, item)
        table.setColumnWidth(0, 90)
        table.setColumnWidth(1, 240)
        table.setColumnWidth(2, 90)
        layout.addWidget(table, 1)

        scroll.setWidget(container)
        root_layout.addWidget(scroll, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText("Cerrar")
        root_layout.addWidget(buttons)


class ReportsWidget(QWidget):
    def __init__(self, services: dict, parent: QWidget | None = None):
        super().__init__(parent)
        self.services = services
        self._data: dict = {}
        self._setup_ui()
        self.refresh()

    # ---------- UI ----------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        header = QHBoxLayout()
        title = QLabel("Reportes")
        title.setObjectName("sectionTitle")
        header.addWidget(title)
        header.addStretch(1)
        layout.addLayout(header)

        toolbar = QWidget()
        toolbar.setObjectName("reportToolbar")
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(10, 8, 10, 8)
        toolbar_layout.setSpacing(8)

        self.month_button = QPushButton("Mensual")
        self.month_button.setObjectName("periodToggle")
        self.month_button.setCheckable(True)
        self.year_button = QPushButton("Anual")
        self.year_button.setObjectName("periodToggle")
        self.year_button.setCheckable(True)
        self.period_group = QButtonGroup(self)
        self.period_group.addButton(self.month_button)
        self.period_group.addButton(self.year_button)
        self.month_button.setChecked(True)
        self.month_button.clicked.connect(self.refresh)
        self.year_button.clicked.connect(self.refresh)
        toolbar_layout.addWidget(self.month_button)
        toolbar_layout.addWidget(self.year_button)

        toolbar_layout.addSpacing(12)

        self.month_combo = NoWheelComboBox()
        for index, name in enumerate(MONTH_NAMES, start=1):
            self.month_combo.addItem(name, index)
        today = date.today()
        self.month_combo.setCurrentIndex(today.month - 1)
        self.month_combo.currentIndexChanged.connect(self.refresh)
        toolbar_layout.addWidget(self.month_combo)

        self.year_combo = NoWheelComboBox()
        for year in range(YEAR_MIN, YEAR_MAX + 1):
            self.year_combo.addItem(str(year), year)
        self.year_combo.setCurrentText(str(today.year))
        self.year_combo.currentIndexChanged.connect(self.refresh)
        toolbar_layout.addWidget(self.year_combo)

        toolbar_layout.addStretch(1)

        export_button = QPushButton("Exportar CSV")
        export_button.setObjectName("primaryButton")
        export_button.clicked.connect(self._export_csv)
        toolbar_layout.addWidget(export_button)

        self.reprint_button = QPushButton("Reimprimir")
        self.reprint_button.setObjectName("secondaryButton")
        self.reprint_button.clicked.connect(self._reprint_sale)
        self.reprint_button.setEnabled(False)
        toolbar_layout.addWidget(self.reprint_button)

        self.anular_button = QPushButton("Anular")
        self.anular_button.setObjectName("secondaryButton")
        self.anular_button.clicked.connect(self._anular_sale)
        self.anular_button.setEnabled(False)
        toolbar_layout.addWidget(self.anular_button)

        self.nota_credito_button = QPushButton("Nota de crédito")
        self.nota_credito_button.setObjectName("secondaryButton")
        self.nota_credito_button.clicked.connect(self._nota_credito)
        self.nota_credito_button.setEnabled(False)
        toolbar_layout.addWidget(self.nota_credito_button)

        expense_button = QPushButton("Registrar gasto")
        expense_button.setObjectName("expenseButton")
        expense_button.clicked.connect(self._open_expense_dialog)
        toolbar_layout.addWidget(expense_button)

        layout.addWidget(toolbar)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #ef4444;")
        layout.addWidget(self.status_label)

        cards = QHBoxLayout()
        self.card_labels: dict[str, QLabel] = {}
        for key, title_text in (
            ("sale_count", "Ventas"),
            ("ingresos", "Ingresos"),
            ("cost", "Costo de fabricación"),
            ("expenses", "Gastos"),
            ("net_profit", "Ganancia"),
        ):
            frame = QFrame()
            frame.setObjectName("statCard")
            frame_layout = QVBoxLayout(frame)
            frame_layout.setContentsMargins(12, 10, 12, 10)
            title_label = QLabel(title_text)
            title_label.setObjectName("statTitle")
            value_label = QLabel("₡0.00")
            value_label.setObjectName("statValue")
            frame_layout.addWidget(title_label)
            frame_layout.addWidget(value_label)
            cards.addWidget(frame)
            self.card_labels[key] = value_label
        layout.addLayout(cards)

        self.stack = QStackedWidget()
        self.daily_table = self._make_table(
            ["Día", "Ventas", "Ingresos", "Costo fab.", "Gastos", "Ganancia"])
        self.sales_table = self._make_table(
            ["N°", "Fecha", "Cliente", "Total", "Pago", "Hacienda", "Estado"])
        self.sales_table.itemSelectionChanged.connect(self._update_action_buttons)
        self.daily_table.doubleClicked.connect(self._open_day_movements)
        self.month_page = QWidget()
        month_layout = QVBoxLayout(self.month_page)
        month_layout.setContentsMargins(0, 0, 0, 0)
        month_layout.addWidget(self.daily_table, 1)
        month_layout.addWidget(self.sales_table, 1)
        self.stack.addWidget(self.month_page)

        self.monthly_table = self._make_table(
            ["Mes", "Ventas", "Ingresos", "Costo fab.", "Gastos", "Ganancia"])
        self.category_table = self._make_table(["Categoría", "N°", "Total"])
        self.year_page = QWidget()
        year_layout = QVBoxLayout(self.year_page)
        year_layout.setContentsMargins(0, 0, 0, 0)
        year_layout.addWidget(self.monthly_table, 1)
        year_layout.addWidget(self.category_table, 1)
        self.stack.addWidget(self.year_page)
        layout.addWidget(self.stack, 1)

    def _make_table(self, headers: list[str]) -> QTableWidget:
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.horizontalHeader().setObjectName("tableHeader")
        table.verticalHeader().setVisible(False)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setAlternatingRowColors(True)
        return table

    # ---------- lógica ----------

    def _range(self) -> tuple[str, str]:
        """Devuelve (inicio, fin) del período según la vista."""
        year = int(self.year_combo.currentData())
        if self.month_button.isChecked():
            month = int(self.month_combo.currentData())
            return f"{year}-{month:02d}-01", f"{year}-{month:02d}-31"
        return f"{year}-01-01", f"{year}-12-31"

    def refresh(self) -> None:
        start, end = self._range()
        annual = self.year_button.isChecked()
        self.month_combo.setVisible(not annual)
        try:
            report = self.services["reports"]
            self._data["summary"] = report.full_summary(start, end)
            if annual:
                self._data["breakdown"] = report.monthly_breakdown(int(self.year_combo.currentData()))
                self._data["categories"] = report.expenses_by_category(start, end)
            else:
                self._data["breakdown"] = report.daily_breakdown(start, end)
                self._data["sales"] = report.list_sales(start, end, limit=50)
            self.status_label.setText("")
        except Exception as exc:
            self._data = {}
            self.status_label.setText(f"No se pudo cargar el reporte: {exc}")
            return
        self._update_cards()
        self._update_tables()
        self.stack.setCurrentWidget(self.year_page if annual else self.month_page)

    def _update_cards(self) -> None:
        summary = self._data.get("summary", {})
        self.card_labels["sale_count"].setText(str(summary.get("sale_count", 0)))
        for key in ("ingresos", "cost", "expenses"):
            self.card_labels[key].setText(format_currency(summary.get(key, 0.0)))
        net = summary.get("net_profit", 0.0)
        net_label = self.card_labels["net_profit"]
        net_label.setText(format_currency(net))
        net_label.setProperty("accent", net >= 0)
        net_label.setProperty("danger", net < 0)
        net_label.style().unpolish(net_label)
        net_label.style().polish(net_label)

    def _fill_table(self, table: QTableWidget, rows: list[list[str]],
                    widths: list[int] | None = None) -> None:
        table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            for column, value in enumerate(row):
                table.setItem(row_index, column, QTableWidgetItem(value))
        if widths:
            for column, width in enumerate(widths):
                table.setColumnWidth(column, width)

    def _update_tables(self) -> None:
        annual = self.year_button.isChecked()
        if annual:
            rows = [
                [
                    MONTH_NAMES[row["month"] - 1],
                    str(row["sale_count"]),
                    format_currency(row["ingresos"]),
                    format_currency(row["cost"]),
                    format_currency(row["expenses"]),
                    format_currency(row["net_profit"]),
                ]
                for row in self._data.get("breakdown", [])
            ]
            self._fill_table(self.monthly_table, rows, [120, 70, 120, 120, 120, 120])
            category_rows = [
                [row["category"], str(row["count"]), format_currency(row["total"])]
                for row in self._data.get("categories", [])
            ]
            self._fill_table(self.category_table, category_rows, [200, 80, 130])
        else:
            rows = [
                [
                    _fmt_day(row["day"]),
                    str(row["sale_count"]),
                    format_currency(row["ingresos"]),
                    format_currency(row["cost"]),
                    format_currency(row["expenses"]),
                    format_currency(row["net_profit"]),
                ]
                for row in self._data.get("breakdown", [])
            ]
            self._fill_table(self.daily_table, rows, [100, 60, 120, 120, 120, 120])
            sales_rows = []
            for sale in self._data.get("sales", []):
                number = sale.get("invoice_number") or str(sale.get("id", ""))
                anulada = (sale.get("status") or "").lower() == "anulada"
                sales_rows.append([
                    str(number),
                    _sale_date_text(sale.get("created_at")),
                    sale.get("client_name") or "",
                    format_currency(float(sale.get("total") or 0)),
                    sale.get("payment_method") or "",
                    sale.get("hacienda_status") or "",
                    "ANULADA" if anulada else "",
                ])
            self._fill_table(self.sales_table, sales_rows, [90, 130, 200, 110, 100, 100, 80])
            self._mark_anuladas()
            self._update_action_buttons()

    def _open_day_movements(self, index=None) -> None:
        """Abre una ventana con las ventas y gastos del día seleccionado."""
        if self.year_button.isChecked():
            return
        row = self.daily_table.currentRow()
        breakdown = self._data.get("breakdown") or []
        if row < 0 or row >= len(breakdown):
            return
        day = breakdown[row].get("day") or ""
        if not day:
            return
        report = self.services["reports"]
        movimientos = report.list_movements(day, day)
        dialog = MovimientosDiaDialog(day, movimientos, parent=self)
        dialog.exec()

    def _update_action_buttons(self) -> None:
        sale = self._selected_sale()
        anulada = bool(sale) and (sale.get("status") or "").lower() == "anulada"
        has_rows = bool(self._data.get("sales"))
        self.reprint_button.setEnabled(has_rows)
        self.anular_button.setEnabled(has_rows and not anulada)
        self.nota_credito_button.setEnabled(has_rows and not anulada)

    def _mark_anuladas(self) -> None:
        """Colorea en rojo y tacha las filas de ventas anuladas."""
        from PyQt6.QtGui import QBrush, QColor
        sales = self._data.get("sales") or []
        for row, sale in enumerate(sales):
            if (sale.get("status") or "").lower() != "anulada":
                continue
            for column in range(self.sales_table.columnCount()):
                item = self.sales_table.item(row, column)
                if item is None:
                    continue
                item.setForeground(QBrush(QColor(220, 38, 38)))
                font = item.font()
                font.setStrikeOut(True)
                item.setFont(font)

    def _reprint_sale(self) -> None:
        row = self.sales_table.currentRow()
        sales = self._data.get("sales") or []
        if row < 0 or row >= len(sales):
            QMessageBox.warning(self, "Reimprimir", "Seleccione una venta de la lista.")
            return
        sale = sales[row]
        sale_id = int(sale.get("id") or 0)
        if not sale_id:
            return
        cart_service = self.services.get("cart")
        db = self.services.get("db")
        if cart_service is None or db is None:
            QMessageBox.warning(self, "Reimprimir", "No hay acceso a los datos de ventas.")
            return
        resultado = reimprimir_factura(db, cart_service, sale_id, imprimir=True)
        if not resultado or not resultado.get("pdf"):
            QMessageBox.warning(self, "Reimprimir", "No se encontró el documento de esa venta.")
            return
        QMessageBox.information(self, "Reimprimir",
                                f"Factura reimpresa y guardada en:\n{resultado.get('pdf')}")

    def _selected_sale(self) -> dict | None:
        row = self.sales_table.currentRow()
        sales = self._data.get("sales") or []
        if row < 0 or row >= len(sales):
            return None
        return sales[row]

    def _anular_sale(self) -> None:
        sale = self._selected_sale()
        if sale is None:
            QMessageBox.warning(self, "Anular", "Seleccione una venta de la lista.")
            return
        sale_id = int(sale.get("id") or 0)
        if not sale_id:
            return
        if (sale.get("status") or "").lower() == "anulada":
            QMessageBox.information(self, "Anular", "Esa venta ya está anulada.")
            return
        answer = QMessageBox.question(
            self,
            "Anular venta",
            f"¿Anular la venta <b>{sale.get('invoice_number') or ''}</b>?\n\n"
            "La venta quedará marcada como ANULADA.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        cart = self.services.get("cart")
        if cart is None:
            QMessageBox.warning(self, "Anular", "No hay acceso a los datos de ventas.")
            return
        excluir_box = QMessageBox(self)
        excluir_box.setIcon(QMessageBox.Icon.Question)
        excluir_box.setWindowTitle("Excluir del reporte")
        excluir_box.setText(
            f"¿Excluir la venta <b>{sale.get('invoice_number') or ''}</b> "
            "del reporte financiero?")
        excluir_box.setInformativeText(
            "Sí: la venta deja de contar en ingresos, ganancias, costo y gastos.\n"
            "No: seguirá sumando al reporte (aunque esté anulada).")
        excluir_button = excluir_box.addButton("Sí, excluir",
                                               QMessageBox.ButtonRole.YesRole)
        conservar_button = excluir_box.addButton("No, conservar",
                                                 QMessageBox.ButtonRole.NoRole)
        excluir_box.exec()
        excluir = excluir_box.clickedButton() == excluir_button
        if not cart.anular_venta(sale_id, motivo="Anulación desde Reportes",
                                 excluir_reporte=excluir):
            QMessageBox.warning(self, "Anular", "No se pudo anular la venta.")
            return
        detalle = ("excluida del reporte" if excluir
                   else "conservada en el reporte")
        QMessageBox.information(self, "Anular",
                                f"Venta {sale.get('invoice_number') or ''} anulada "
                                f"({detalle}).")
        self.refresh()

    def _nota_credito(self) -> None:
        sale = self._selected_sale()
        if sale is None:
            QMessageBox.warning(self, "Nota de crédito", "Seleccione una venta de la lista.")
            return
        if (sale.get("status") or "").lower() == "anulada":
            QMessageBox.warning(self, "Nota de crédito",
                                "No se puede emitir nota de crédito sobre una venta anulada.")
            return
        dialog = NotaCreditoDialog(self.services, sale, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh()

    def _open_expense_dialog(self) -> None:
        dialog = ExpenseDialog(self.services, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            QMessageBox.information(self, "Gasto registrado", "El gasto se registró correctamente.")
            self.refresh()

    def _export_csv(self) -> None:
        if not self._data:
            QMessageBox.warning(self, "Sin datos", "No hay datos para exportar.")
            return
        annual = self.year_button.isChecked()
        default_name = (f"reporte_{self.year_combo.currentText()}_anual.csv"
                        if annual else
                        f"reporte_{self.year_combo.currentText()}_"
                        f"{int(self.month_combo.currentData()):02d}_mensual.csv")
        path, _ = QFileDialog.getSaveFileName(self, "Exportar reporte", default_name,
                                              "Archivo CSV (*.csv)")
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as handle:
                writer = csv.writer(handle)
                summary = self._data.get("summary", {})
                writer.writerow(["Concepto", "Valor"])
                writer.writerow(["Ventas", summary.get("sale_count", 0)])
                writer.writerow(["Ingresos", summary.get("ingresos", 0.0)])
                writer.writerow(["Costo de fabricación", summary.get("cost", 0.0)])
                writer.writerow(["Gastos", summary.get("expenses", 0.0)])
                writer.writerow(["Ganancia", summary.get("net_profit", 0.0)])
                writer.writerow([])
                if annual:
                    writer.writerow(["Mes", "Ventas", "Ingresos", "Costo fab.", "Gastos", "Ganancia"])
                    for row in self._data.get("breakdown", []):
                        writer.writerow([
                            MONTH_NAMES[row["month"] - 1], row["sale_count"],
                            row["ingresos"], row["cost"], row["expenses"], row["net_profit"],
                        ])
                    writer.writerow([])
                    writer.writerow(["Categoría de gasto", "N°", "Total"])
                    for row in self._data.get("categories", []):
                        writer.writerow([row["category"], row["count"], row["total"]])
                else:
                    writer.writerow(["Día", "Ventas", "Ingresos", "Costo fab.", "Gastos", "Ganancia"])
                    for row in self._data.get("breakdown", []):
                        writer.writerow([
                            _fmt_day(row["day"]), row["sale_count"],
                            row["ingresos"], row["cost"], row["expenses"], row["net_profit"],
                        ])
            QMessageBox.information(self, "Exportado", f"Reporte guardado en:\n{path}")
        except OSError as exc:
            QMessageBox.critical(self, "Error", f"No se pudo guardar el archivo:\n{exc}")
