"""Widget del punto de venta: búsqueda, carrito y cobro."""

import json
from uuid import uuid4

from dataclasses import fields as dataclass_fields

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from config import Config
from database.models import Sale, SaleItem
from network.image_store import ImageStore
from network.remote_db import AuthError, ServerError
from network.session import session
from ui.login_dialog import LoginDialog
from ui.recovery_dialog import ConnectionRecoveryDialog
from utils.helpers import calculate_totals, format_currency
from modules.documentos import generar_documentos
from modules.documentos.ticket import imprimir_ticket_venta
from modules.documentos.xml_factura import build_factura_payload
from modules.pos.cobro_dialog import CobroDialog
from modules.pos.cart_service import CartService


def _build_dataclass(cls, **kwargs):
    names = {f.name for f in dataclass_fields(cls)}
    return cls(**{key: value for key, value in kwargs.items() if key in names})


class ProductCard(QWidget):
    """Tarjeta de producto en la cuadrícula del POS (foto, nombre y precio)."""

    clicked = pyqtSignal(object)

    def __init__(self, product, parent=None):
        super().__init__(parent)
        self.product = product
        self.setObjectName("productCard")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedHeight(210)
        self.setMinimumWidth(170)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        self.image_label = QLabel()
        self.image_label.setObjectName("productCardImage")
        self.image_label.setFixedHeight(112)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.image_label)

        name_label = QLabel(product.name)
        name_label.setObjectName("productCardName")
        name_label.setWordWrap(True)
        name_label.setMaximumHeight(40)
        layout.addWidget(name_label)

        price_label = QLabel(format_currency(float(getattr(product, "sale_price", 0.0))))
        price_label.setObjectName("productCardPrice")
        layout.addWidget(price_label)

        self.set_placeholder()

    def set_placeholder(self) -> None:
        self.image_label.setPixmap(
            ImageStore.placeholder_pixmap(self.product.name or "?", 96))

    def set_image_pixmap(self, pixmap) -> None:
        if pixmap is None:
            return
        scaled = pixmap.scaled(
            142, 106,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.image_label.setPixmap(scaled)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.product)
        super().mousePressEvent(event)


class POSWidget(QWidget):
    sale_completed = pyqtSignal(dict)

    def __init__(self, services: dict, parent: QWidget | None = None):
        super().__init__(parent)
        self.services = services
        self.cart: list[dict] = []
        self.client = None
        self.categories: list = []
        self._setup_ui()
        self._refresh_categories()
        self._rebuild_product_grid()

    def _setup_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        left = QVBoxLayout()
        left.setContentsMargins(12, 12, 12, 12)
        left.setSpacing(8)

        self.search_input = QLineEdit()
        self.search_input.setObjectName("searchInput")
        self.search_input.setPlaceholderText("Buscar por nombre, código o madera")
        self.search_input.textChanged.connect(lambda _: self._rebuild_product_grid())

        self.category_combo = QComboBox()
        self.category_combo.currentIndexChanged.connect(lambda _: self._rebuild_product_grid())

        left.addWidget(self.search_input)
        left.addWidget(self.category_combo)

        self.products_scroll = QScrollArea()
        self.products_scroll.setWidgetResizable(True)
        self.products_container = QWidget()
        self.products_layout = QGridLayout(self.products_container)
        self.products_layout.setContentsMargins(4, 4, 4, 4)
        self.products_layout.setSpacing(10)
        self.products_scroll.setWidget(self.products_container)
        left.addWidget(self.products_scroll, 1)

        root.addLayout(left, 6)

        right = QWidget()
        right.setObjectName("cartPanel")
        right.setFixedWidth(480)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(12, 12, 12, 12)
        right_layout.setSpacing(8)

        title = QLabel("Carrito de Compra")
        title.setObjectName("cartPanelTitle")
        right_layout.addWidget(title)

        client_row = QHBoxLayout()
        self.client_label = QLabel("Cliente: Consumidor Final")
        self.client_label.setObjectName("cartValue")
        client_row.addWidget(self.client_label, 1)
        self.client_button = QPushButton("Seleccionar Cliente")
        self.client_button.setObjectName("primaryButton")
        self.client_button.clicked.connect(self.select_client)
        client_row.addWidget(self.client_button)
        right_layout.addLayout(client_row)

        self.cart_table = QTableWidget(0, 4)
        self.cart_table.setObjectName("cartTable")
        self.cart_table.setHorizontalHeaderLabels(["Producto", "Cant.", "Precio", "Total"])
        self.cart_table.horizontalHeader().setObjectName("cartHeader")
        self.cart_table.setColumnWidth(0, 190)
        self.cart_table.setColumnWidth(1, 50)
        self.cart_table.setColumnWidth(2, 100)
        self.cart_table.setColumnWidth(3, 100)
        self.cart_table.verticalHeader().setVisible(False)
        self.cart_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.cart_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.cart_table.doubleClicked.connect(self._remove_selected_item)
        right_layout.addWidget(self.cart_table, 1)

        totals_grid = QGridLayout()
        self.subtotal_label = QLabel("₡0.00")
        self.discount_label = QLabel("₡0.00")
        self.tax_label = QLabel("₡0.00")
        self.total_label = QLabel("₡0.00")
        self.total_label.setObjectName("totalLabel")
        self.total_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        for row, (text, widget) in enumerate(
            [
                ("Subtotal:", self.subtotal_label),
                ("Descuento:", self.discount_label),
                ("IVA:", self.tax_label),
            ]
        ):
            label = QLabel(text)
            label.setObjectName("cartLabel")
            totals_grid.addWidget(label, row, 0)
            widget.setObjectName("cartValue")
            widget.setAlignment(Qt.AlignmentFlag.AlignRight)
            totals_grid.addWidget(widget, row, 1)
        totals_grid.addWidget(QLabel("TOTAL:"), 3, 0)
        totals_grid.addWidget(self.total_label, 3, 1)
        right_layout.addLayout(totals_grid)

        self.payment_group = QButtonGroup(self)
        self.payment_group.setExclusive(True)
        self.payment_buttons: dict[str, QPushButton] = {}
        payment_row = QHBoxLayout()
        for method in ("Efectivo", "Tarjeta", "Sinpe"):
            button = QPushButton(method)
            button.setObjectName("paymentButton")
            button.setCheckable(True)
            button.setFixedHeight(36)
            self.payment_group.addButton(button)
            self.payment_buttons[method] = button
            payment_row.addWidget(button)
        self.payment_buttons["Efectivo"].setChecked(True)
        right_layout.addLayout(payment_row)

        self.invoice_button = QPushButton("Factura Electrónica")
        self.invoice_button.setObjectName("invoiceToggle")
        self.invoice_button.setCheckable(True)
        self.invoice_button.setFixedHeight(36)
        self.invoice_button.clicked.connect(self._on_invoice_toggle)
        right_layout.addWidget(self.invoice_button)

        self.simplified_button = QPushButton("Fact. Simplificada")
        self.simplified_button.setObjectName("invoiceToggle")
        self.simplified_button.setCheckable(True)
        self.simplified_button.setFixedHeight(36)
        self.simplified_button.clicked.connect(self._on_simplified_toggle)
        right_layout.addWidget(self.simplified_button)

        self.charge_button = QPushButton("COBRAR")
        self.charge_button.setObjectName("primaryButton")
        self.charge_button.clicked.connect(self.process_payment)
        right_layout.addWidget(self.charge_button)

        self.cancel_button = QPushButton("Cancelar Venta")
        self.cancel_button.setObjectName("dangerButton")
        self.cancel_button.clicked.connect(self._clear_cart)
        right_layout.addWidget(self.cancel_button)

        root.addWidget(right, 0)

    def _refresh_categories(self) -> None:
        service = self.services["category"]
        self.categories = service.get_all(active_only=True) or []
        current = self.category_combo.currentData()
        self.category_combo.blockSignals(True)
        self.category_combo.clear()
        self.category_combo.addItem("Todas", None)
        for category in self.categories:
            self.category_combo.addItem(category.name, category.id)
        index = self.category_combo.findData(current)
        if index >= 0:
            self.category_combo.setCurrentIndex(index)
        self.category_combo.blockSignals(False)

    def _rebuild_product_grid(self) -> None:
        while self.products_layout.count():
            item = self.products_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        query = self.search_input.text().strip()
        category_id = self.category_combo.currentData()
        service = self.services["product"]
        if query:
            products = service.search(query, category_id) or []
        else:
            products = service.get_all(category_id=category_id, active_only=True) or []

        row, column = 0, 0
        image_store = self.services.get("images")
        for product in products:
            if not getattr(product, "active", True):
                continue
            card = ProductCard(product)
            card.clicked.connect(lambda checked=False, p=product: self.add_to_cart(p))
            self.products_layout.addWidget(card, row, column)
            image_path = getattr(product, "image_path", "") or ""
            if image_path and image_store is not None:
                image_store.get_pixmap_async(image_path, card.set_image_pixmap)
            column += 1
            if column >= 4:
                column = 0
                row += 1
        self.products_layout.setRowStretch(row + 1, 1)
        for index in range(4):
            self.products_layout.setColumnStretch(index, 1)

    def add_to_cart(self, product) -> None:
        product_id = product.id
        for item in self.cart:
            if item["product_id"] == product_id:
                item["quantity"] += 1
                self._update_cart_display()
                return
        self.cart.append(
            {
                "product_id": product_id,
                "product_name": product.name,
                "quantity": 1,
                "unit_price": float(getattr(product, "sale_price", 0.0)),
                "tax_rate": float(getattr(product, "tax_rate", 0.0)),
                "discount": 0.0,
                "cabys_code": getattr(product, "cabys_code", "") or "",
                "total": float(getattr(product, "sale_price", 0.0)),
            }
        )
        self._update_cart_display()

    def _remove_selected_item(self) -> None:
        row = self.cart_table.currentRow()
        if 0 <= row < len(self.cart):
            del self.cart[row]
            self._update_cart_display()

    def _update_cart_display(self) -> None:
        self.cart_table.setRowCount(len(self.cart))
        for row, item in enumerate(self.cart):
            item["total"] = item["unit_price"] * item["quantity"] - item.get("discount", 0.0)
            values = [
                item["product_name"],
                str(item["quantity"]),
                format_currency(item["unit_price"]),
                format_currency(item["total"]),
            ]
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                if column > 0:
                    cell.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.cart_table.setItem(row, column, cell)
        self.cart_table.resizeRowsToContents()
        self._update_totals()

    def _update_totals(self) -> None:
        totals = calculate_totals(self.cart, exento=self.simplified_button.isChecked())
        self.subtotal_label.setText(format_currency(totals["subtotal"]))
        self.discount_label.setText(format_currency(totals["discount"]))
        self.tax_label.setText(format_currency(totals["tax_amount"]))
        self.total_label.setText(format_currency(totals["total"]))

    def _current_payment_method(self) -> str | None:
        for method, button in self.payment_buttons.items():
            if button.isChecked():
                return method
        return None

    def _on_invoice_toggle(self) -> None:
        if self.invoice_button.isChecked():
            self.simplified_button.setChecked(False)
        self._update_totals()

    def _on_simplified_toggle(self) -> None:
        if self.simplified_button.isChecked():
            self.invoice_button.setChecked(False)
        self._update_totals()

    def select_client(self) -> None:
        from modules.clients.client_widget import ClientPickerDialog

        dialog = ClientPickerDialog(self.services, parent=self)
        if dialog.exec() and dialog.selected is not None:
            self.client = dialog.selected
            self.client_label.setText(f"Cliente: {dialog.selected.name} ({dialog.selected.id_number})")

    def process_payment(self) -> None:
        if not self.cart:
            QMessageBox.warning(self, "Carrito vacío", "Agregue productos antes de cobrar.")
            return

        method = self._current_payment_method()
        if method is None:
            QMessageBox.warning(self, "Método de pago", "Seleccione un método de pago.")
            return

        electronic = self.invoice_button.isChecked()
        simplified = self.simplified_button.isChecked()
        totals = calculate_totals(self.cart, exento=simplified)

        if electronic and self.client is None:
            QMessageBox.warning(self, "Factura Electrónica", "Seleccione un cliente para emitir factura electrónica.")
            return

        if electronic and self.client is not None:
            id_type = str(getattr(self.client, "id_type", ""))
            id_number = str(getattr(self.client, "id_number", ""))
            if id_type == "06" or not id_number:
                answer = QMessageBox.question(
                    self,
                    "Consumidor Final",
                    "El cliente no tiene una cédula real de contribuyente.\n"
                    "¿Desea continuar y emitir la factura como Consumidor Final?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if answer != QMessageBox.StandardButton.Yes:
                    return

        dialog = CobroDialog(totals["total"], parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        result = dialog.result()
        method = result["method"]
        cash_received = result["cash_received"]
        change = result["change"]
        payment_details = result.get("payment_details") or []
        currency = result.get("currency", "CRC")
        exchange_rate = result.get("exchange_rate", 0.0)
        total_crc = result.get("total_crc", totals["total"])

        client_id = self.client.id if self.client is not None else None
        client_name = self.client.name if self.client is not None else "Consumidor Final"

        sale = _build_dataclass(
            Sale,
            id=0,
            invoice_number="",
            client_id=client_id,
            client_name=client_name,
            subtotal=totals["subtotal"],
            discount=totals["discount"],
            tax_amount=totals["tax_amount"],
            total=total_crc,
            payment_method=method,
            cash_received=cash_received,
            change_amount=change,
            payment_details=json.dumps(payment_details, ensure_ascii=False),
            invoice_type="simplificada" if simplified else "general",
            sale_reference=uuid4().hex,
            currency=currency,
            exchange_rate=exchange_rate,
            status="PENDIENTE",
            hacienda_key="",
            hacienda_status="PENDIENTE",
            electronic_invoice=electronic,
            station=getattr(Config, "STATION", "CAJA-1"),
            user_id=session.user_id,
            user_name=session.user_name,
            created_at=None,
            items=[],
        )

        items = [
            _build_dataclass(
                SaleItem,
                id=0,
                sale_id=0,
                product_id=item["product_id"],
                product_name=item["product_name"],
                quantity=item["quantity"],
                unit_price=item["unit_price"],
                discount=item.get("discount", 0.0),
                tax_amount=item.get("tax_amount", 0.0),
                total=item["total"],
            )
            for item in self.cart
        ]

        try:
            sale_id = self._create_sale_with_recovery(sale, items)
        except Exception as exc:
            QMessageBox.critical(self, "Error al guardar", f"No se pudo guardar la venta:\n{exc}")
            return
        if sale_id is None:
            return

        clave = ""
        payload = {}
        if electronic and self.client is not None:
            clave, payload = self._send_electronic_invoice(sale_id, sale, items, totals)

        result = {
            "sale_id": sale_id,
            "total": totals["total"],
            "change": change,
            "clave": clave,
            "method": method,
            "print_requested": dialog.print_requested,
        }

        documents = self._generar_y_imprimir(
            sale_id, sale, payload, clave, method,
            print_requested=result.get("print_requested", False))

        self.sale_completed.emit(result)

        self._clear_cart()

    def _generar_y_imprimir(self, sale_id: int, sale, payload: dict, clave: str,
                            method: str, print_requested: bool = False) -> dict:
        """Guarda XML+PDF en Documentos y ofrece imprimir la factura en físico.

        Nunca bloquea la venta: si falla, solo se avisa y se continúa.
        Devuelve el dict de documentos generado.
        """
        try:
            saved = self.services["cart"].get_sale(sale_id)
        except Exception:
            saved = None
        if saved is None:
            return {}
        try:
            medio = "02" if method.lower() in ("tarjeta", "sinpe") else "01"
            if method.lower() == "mixto":
                try:
                    detalles = json.loads(saved.payment_details or "[]")
                    tiene_no_efectivo = any(
                        d.get("method", "").lower() in ("tarjeta", "sinpe")
                        for d in detalles)
                    medio = "02" if tiene_no_efectivo else "01"
                except Exception:
                    medio = "01"
            company = self._load_company_config()
            if getattr(saved, "invoice_type", "general") == "simplificada":
                payload = None
            documents = generar_documentos(saved, company,
                                           payload=payload or None, clave=clave,
                                           medio_pago=medio)
        except Exception as exc:
            QMessageBox.warning(self, "Documentos",
                                f"No se pudieron generar los respaldos:\n{exc}")
            return {}

        if print_requested:
            try:
                ok = imprimir_ticket_venta(saved, company, self.services["db"])
            except Exception:
                ok = False
            if not ok:
                QMessageBox.information(
                    self, "Impresión",
                    f"No se pudo imprimir el ticket. El PDF quedó guardado en:\n{documents.get('pdf', '')}")
        return documents

    def _create_sale_with_recovery(self, sale: Sale, items: list[SaleItem]) -> int | None:
        """Guarda la venta; ante fallos de red/sesión ofrece recuperación.

        Devuelve el id de la venta o None si el usuario canceló. El carrito se
        conserva intacto mientras tanto.
        """
        while True:
            try:
                return self.services["cart"].create_sale(sale, items)
            except AuthError as exc:
                if Config.MODE != "server" or not self._relogin():
                    QMessageBox.critical(self, "Error al guardar",
                                         f"No se pudo guardar la venta:\n{exc}")
                    return None
            except ServerError as exc:
                if Config.MODE != "server":
                    QMessageBox.critical(self, "Error al guardar",
                                         f"No se pudo guardar la venta:\n{exc}")
                    return None
                dialog = ConnectionRecoveryDialog(self.services["db"], str(exc), parent=self)
                if dialog.exec() != QDialog.DialogCode.Accepted:
                    return None
            except Exception as exc:
                QMessageBox.critical(self, "Error al guardar",
                                     f"No se pudo guardar la venta:\n{exc}")
                return None

    def _relogin(self) -> bool:
        """Pide el PIN de nuevo tras una sesión expirada. True si reingresó."""
        dialog = LoginDialog(self.services["db"],
                             station=getattr(Config, "STATION", "CAJA1"),
                             parent=self)
        return dialog.exec() == QDialog.DialogCode.Accepted

    def _send_electronic_invoice(self, sale_id: int, sale, items, totals: dict) -> tuple[str, dict]:
        missing_cabys = [item for item in self.cart if not item.get("cabys_code")]
        if missing_cabys:
            QMessageBox.warning(
                self,
                "CABYS faltante",
                "Algunos productos no tienen código CABYS. Se usará 0000000000000 en la factura.",
            )

        company = self._load_company_config()
        consecutivo = f"{company.get('branch', '001')}-{company.get('terminal', '001')}-{sale_id:010d}"
        payload = build_factura_payload(
            company, self.client, self.cart, totals, consecutivo)

        try:
            response = self.services["hacienda"].send_electronic_invoice(payload)
        except Exception as exc:
            QMessageBox.warning(self, "Hacienda", f"No se pudo enviar la factura electrónica:\n{exc}")
            return "", {}

        if not response:
            QMessageBox.warning(self, "Hacienda", "Hacienda no aceptó la factura. La venta se guardó sin clave.")
            return "", {}

        clave = str(response.get("clave", ""))
        status = "ACEPTADA" if clave else "ENVIADA"
        try:
            self.services["cart"].update_hacienda_status(sale_id, clave, status)
        except Exception:
            pass
        return clave, payload

    def _load_company_config(self) -> dict:
        config: dict = {}
        db = self.services.get("db")
        if db is None:
            return config
        try:
            rows = db.execute_query("SELECT * FROM hacienda_config WHERE id = 1") or []
            if rows:
                row = {str(key): value for key, value in rows[0].items()}
                return {
                    "company_name": row.get("company_name", ""),
                    "company_id": row.get("company_id", ""),
                    "phone": row.get("company_phone", ""),
                    "address": row.get("company_address", ""),
                    "activity_code": row.get("activity_code", ""),
                    "branch": row.get("branch", "001"),
                    "terminal": row.get("terminal", "001"),
                }
        except Exception:
            pass
        try:
            for row in db.execute_query("SELECT key, value FROM hacienda_config"):
                config[str(row["key"])] = row["value"]
        except Exception:
            pass
        return config

    def _clear_cart(self) -> None:
        self.cart.clear()
        self.client = None
        self.client_label.setText("Cliente: Consumidor Final")
        self.payment_buttons["Efectivo"].setChecked(True)
        self.invoice_button.setChecked(False)
        self.simplified_button.setChecked(False)
        self._update_cart_display()

    def refresh_products(self) -> None:
        self._refresh_categories()
        self._rebuild_product_grid()

    def refresh_categories(self) -> None:
        self._refresh_categories()
