"""Widget de cuentas por cobrar (Crédito) con tabla, resumen y diálogos."""

import json
import os
import shutil
from dataclasses import fields as dataclass_fields
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from config import Config
from database.models import (
    CreditAccount,
    CreditPayment,
    CreditPaymentImage,
    Sale,
    SaleItem,
)
from modules.credit.credit_service import CreditService
from network.session import session
from utils.helpers import format_currency, NoWheelComboBox, calculate_totals

_CREDIT_DOCS = os.path.join(
    os.environ.get("APPDATA", ""), "PosLaLoma", "documentos", "creditos")


def _ensure_docs_dir() -> str:
    Path(_CREDIT_DOCS).mkdir(parents=True, exist_ok=True)
    return _CREDIT_DOCS


def _build_dataclass(cls, **kwargs):
    names = {f.name for f in dataclass_fields(cls)}
    return cls(**{key: value for key, value in kwargs.items() if key in names})


class PaymentDialog(QDialog):
    """Diálogo para registrar un abono a una cuenta por cobrar."""

    def __init__(self, account: CreditAccount, services: dict,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.services = services
        self.account = account
        self.payment_id: int | None = None
        self.payment_reference = uuid4().hex
        self.setWindowTitle("Registrar Abono")
        self.setMinimumWidth(420)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        info = QLabel(
            f"Venta: {self.account.invoice_number}  |  "
            f"Saldo: {format_currency(self.account.balance)}")
        info.setObjectName("sectionTitle")
        info.setWordWrap(True)
        layout.addWidget(info)

        amount_row = QHBoxLayout()
        amount_label = QLabel("Monto:")
        self.amount_input = QLineEdit()
        self.amount_input.setPlaceholderText("0")
        self.amount_input.setText("0")
        self.amount_input.setAlignment(Qt.AlignmentFlag.AlignRight)
        amount_row.addWidget(amount_label)
        amount_row.addWidget(self.amount_input, 1)
        layout.addLayout(amount_row)

        method_row = QHBoxLayout()
        method_label = QLabel("Método:")
        self.method_combo = NoWheelComboBox()
        self.method_combo.addItems(["Efectivo", "Tarjeta", "Sinpe", "Mixto"])
        method_row.addWidget(method_label)
        method_row.addWidget(self.method_combo, 1)
        layout.addLayout(method_row)

        notes_row = QHBoxLayout()
        notes_label = QLabel("Notas:")
        self.notes_input = QLineEdit()
        self.notes_input.setPlaceholderText("Opcional")
        notes_row.addWidget(notes_label)
        notes_row.addWidget(self.notes_input, 1)
        layout.addLayout(notes_row)

        self.images_container = QVBoxLayout()
        self.images_container.setSpacing(4)
        layout.addLayout(self.images_container)

        self.attach_button = QPushButton("+ Adjuntar comprobante")
        self.attach_button.clicked.connect(self._attach_image)
        layout.addWidget(self.attach_button)

        self.attached_images: list[dict] = []

        btn_row = QHBoxLayout()
        self.pay_button = QPushButton("Registrar Abono")
        self.pay_button.setObjectName("primaryButton")
        self.pay_button.clicked.connect(self._on_pay)
        cancel_button = QPushButton("Cancelar")
        cancel_button.clicked.connect(self.reject)
        btn_row.addWidget(self.pay_button)
        btn_row.addWidget(cancel_button)
        layout.addLayout(btn_row)

    def _on_pay(self) -> None:
        try:
            amount = float(self.amount_input.text().replace(",", "").strip() or "0")
        except ValueError:
            QMessageBox.warning(self, "Monto inválido", "Ingrese un monto numérico.")
            return
        if amount <= 0:
            QMessageBox.warning(self, "Monto inválido", "El monto debe ser mayor a cero.")
            return
        if amount > self.account.balance:
            QMessageBox.warning(
                self, "Monto excedido",
                f"El monto ({format_currency(amount)}) supera el saldo "
                f"({format_currency(self.account.balance)}).")
            return
        method = self.method_combo.currentText().lower()
        notes = self.notes_input.text().strip()
        svc: CreditService = self.services["credit"]
        try:
            self.payment_id = svc.make_payment(
                self.account.id, amount, method, notes=notes,
                reference=self.payment_reference)
        except ValueError as exc:
            QMessageBox.warning(self, "Abono no registrado", str(exc))
            return
        except Exception as exc:
            QMessageBox.critical(
                self, "Abono no registrado",
                f"No se pudo registrar el abono:\n{exc}")
            return
        if self.payment_id and self.attached_images:
            docs_dir = _ensure_docs_dir()
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            for img in self.attached_images:
                src = img["source_path"]
                ext = Path(src).suffix or ".jpg"
                dest_name = f"pago_{self.payment_id}_{ts}_{uuid4().hex[:8]}{ext}"
                dest = Path(docs_dir) / dest_name
                try:
                    shutil.copy2(src, dest)
                    svc.add_payment_image(self.payment_id, str(dest), img.get("desc", ""))
                except Exception:
                    pass
        self.accept()

    def _attach_image(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Seleccionar comprobantes", "",
            "Imágenes (*.png *.jpg *.jpeg *.webp *.bmp);;Todos los archivos (*)")
        if not paths:
            return
        for path in paths:
            self.attached_images.append({"source_path": path, "desc": ""})
            self._add_image_preview(path, len(self.attached_images) - 1)

    def _add_image_preview(self, path: str, index: int) -> None:
        row = QHBoxLayout()
        thumb = QLabel()
        pixmap = QPixmap(path)
        if not pixmap.isNull():
            thumb.setPixmap(pixmap.scaled(
                32, 32,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation))
        else:
            thumb.setText("IMG")
        thumb.setFixedSize(32, 32)
        row.addWidget(thumb)
        name = Path(path).name
        if len(name) > 35:
            name = name[:32] + "..."
        lbl = QLabel(name)
        lbl.setStyleSheet("font-size: 13px;")
        row.addWidget(lbl, 1)
        remove_btn = QPushButton("×")
        remove_btn.setFixedSize(24, 24)
        remove_btn.setStyleSheet("font-size: 15px; font-weight: bold; color: #e74c3c;")
        remove_btn.clicked.connect(lambda _, idx=index: self._remove_image(idx))
        row.addWidget(remove_btn)
        self.images_container.addLayout(row)
        self.images_container.parent().update()

    def _remove_image(self, index: int) -> None:
        if 0 <= index < len(self.attached_images):
            self.attached_images.pop(index)
            self._refresh_images_ui()

    def _refresh_images_ui(self) -> None:
        while self.images_container.count():
            item = self.images_container.takeAt(0)
            if item.layout():
                while item.layout().count():
                    w = item.layout().takeAt(0).widget()
                    if w:
                        w.deleteLater()
        self.attached_images = list(self.attached_images)
        for idx, img in enumerate(self.attached_images):
            self._add_image_preview(img["source_path"], idx)


class PaymentGalleryDialog(QDialog):
    """Galería de comprobantes (imágenes) adjuntos a un abono."""

    def __init__(self, payment: CreditPayment, services: dict,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.services = services
        self.payment = payment
        self.images: list[CreditPaymentImage] = []
        self.index = 0
        self.setWindowTitle(f"Comprobantes — Abono #{payment.id}")
        self.setMinimumSize(640, 560)
        self.setMaximumHeight(720)
        self._setup_ui()
        self._load_images()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        title = QLabel(
            f"Comprobantes del abono #{self.payment.id}  |  "
            f"{format_currency(self.payment.amount)}")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)

        meta = QLabel(
            f"Cliente: {self.payment.client_name or '—'}  |  "
            f"Factura: {self.payment.invoice_number or '—'}  |  "
            f"Fecha: {self.payment.created_at[:16] if self.payment.created_at else '—'}")
        meta.setStyleSheet("font-size: 13px; color: #8b93a3;")
        layout.addWidget(meta)

        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setMinimumHeight(300)
        self.image_label.setWordWrap(True)
        self.image_label.setStyleSheet(
            "border: 1px solid #2e3440; border-radius: 8px; background: #1a1f28;")
        layout.addWidget(self.image_label, 1)

        nav = QHBoxLayout()
        nav.setSpacing(10)
        prev_btn = QPushButton("←")
        prev_btn.setObjectName("secondaryButton")
        prev_btn.setFixedWidth(60)
        prev_btn.clicked.connect(lambda: self._navigate(-1))
        next_btn = QPushButton("→")
        next_btn.setObjectName("secondaryButton")
        next_btn.setFixedWidth(60)
        next_btn.clicked.connect(lambda: self._navigate(1))
        self.counter_label = QLabel("")
        self.counter_label.setObjectName("formLabel")
        self.counter_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        nav.addWidget(prev_btn)
        nav.addStretch(1)
        nav.addWidget(self.counter_label)
        nav.addStretch(1)
        nav.addWidget(next_btn)
        layout.addLayout(nav)

        self.thumbs_layout = QHBoxLayout()
        self.thumbs_layout.setSpacing(8)
        self._thumbs_container = QWidget()
        self._thumbs_container.setLayout(self.thumbs_layout)
        layout.addWidget(self._thumbs_container)

        action_row = QHBoxLayout()
        open_btn = QPushButton("Abrir archivo")
        open_btn.setObjectName("secondaryButton")
        open_btn.clicked.connect(self._open_external)
        action_row.addWidget(open_btn)
        action_row.addStretch(1)
        close_btn = QPushButton("Cerrar")
        close_btn.clicked.connect(self.accept)
        action_row.addWidget(close_btn)
        layout.addLayout(action_row)

    def _load_images(self) -> None:
        svc: CreditService = self.services["credit"]
        self.images = svc.list_payment_images(self.payment.id)
        self.index = 0
        self._render()

    def _current(self) -> CreditPaymentImage | None:
        if 0 <= self.index < len(self.images):
            return self.images[self.index]
        return None

    def _render(self) -> None:
        while self.thumbs_layout.count():
            item = self.thumbs_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        if not self.images:
            self.image_label.setPixmap(QPixmap())
            self.image_label.setText("Sin comprobantes adjuntos")
            self.counter_label.setText("0 / 0")
            return
        self.counter_label.setText(f"{self.index + 1} / {len(self.images)}")
        self._show_current()
        self._build_thumbs()

    def _show_current(self) -> None:
        img = self._current()
        if img is None:
            return
        pixmap = QPixmap(img.image_path)
        if pixmap.isNull():
            self.image_label.setPixmap(QPixmap())
            self.image_label.setText(
                f"Archivo no encontrado:\n{Path(img.image_path).name}")
            return
        size = self.image_label.size()
        scaled = pixmap.scaled(
            max(320, size.width() - 24), max(220, size.height() - 24),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation)
        self.image_label.setPixmap(scaled)

    def _build_thumbs(self) -> None:
        for i, img in enumerate(self.images):
            btn = QPushButton()
            btn.setFixedSize(64, 64)
            btn.setObjectName("thumbnail")
            btn.setCheckable(True)
            btn.setChecked(i == self.index)
            btn.setStyleSheet(
                "QPushButton#thumbnail { border: 2px solid #2e3440; border-radius: 6px;"
                " padding: 2px; background: #1a1f28; }"
                "QPushButton#thumbnail:checked { border-color: #2fbf71; }")
            desc = img.description or Path(img.image_path).name
            btn.setToolTip(desc)
            pixmap = QPixmap(img.image_path)
            if not pixmap.isNull():
                btn.setIcon(QIcon(pixmap.scaled(
                    56, 56,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation)))
            btn.clicked.connect(lambda checked=False, idx=i: self._go_to(idx))
            self.thumbs_layout.addWidget(btn)
        self.thumbs_layout.addStretch(1)

    def _go_to(self, index: int) -> None:
        if 0 <= index < len(self.images):
            self.index = index
            self._render()

    def _navigate(self, step: int) -> None:
        if not self.images:
            return
        self.index = (self.index + step) % len(self.images)
        self._render()

    def _open_external(self) -> None:
        img = self._current()
        if img is None:
            return
        try:
            os.startfile(img.image_path)
        except Exception as exc:
            QMessageBox.warning(
                self, "Comprobante", f"No se pudo abrir el archivo:\n{exc}")

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self.images:
            self._show_current()


class CreditDetailDialog(QDialog):
    """Detalle de una cuenta por cobrar con historial de abonos."""

    data_changed = pyqtSignal()

    def __init__(self, account: CreditAccount, services: dict,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.services = services
        self.account = account
        self.setWindowTitle(f"Cuenta {account.invoice_number}")
        self.setMinimumSize(560, 440)
        self._setup_ui()
        self._load_data()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        self.info_label = QLabel()
        self.info_label.setObjectName("sectionTitle")
        self.info_label.setWordWrap(True)
        layout.addWidget(self.info_label)

        self.summary_label = QLabel()
        self.summary_label.setStyleSheet("font-size: 14px;")
        layout.addWidget(self.summary_label)

        sep = QFrame()
        sep.setObjectName("separator")
        sep.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(sep)

        history_title = QLabel("Historial de Abonos")
        history_title.setObjectName("subtitleLabel")
        layout.addWidget(history_title)

        history_hint = QLabel(
            "Doble clic en un abono para ver sus comprobantes adjuntos.")
        history_hint.setStyleSheet("font-size: 13px; color: #8b93a3;")
        layout.addWidget(history_hint)

        self.payments_table = QTableWidget(0, 4)
        self.payments_table.setHorizontalHeaderLabels(
            ["Fecha", "Monto", "Método", "Notas"])
        self.payments_table.horizontalHeader().setObjectName("tableHeader")
        self.payments_table.verticalHeader().setVisible(False)
        self.payments_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows)
        self.payments_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers)
        self.payments_table.setAlternatingRowColors(True)
        self.payments_table.doubleClicked.connect(self._open_payment_gallery)
        layout.addWidget(self.payments_table, 1)

        btn_row = QHBoxLayout()
        self.pay_button = QPushButton("Registrar Abono")
        self.pay_button.setObjectName("primaryButton")
        self.pay_button.clicked.connect(self._open_payment)
        btn_row.addWidget(self.pay_button)
        btn_row.addStretch(1)
        close_btn = QPushButton("Cerrar")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    def _load_data(self) -> None:
        a = self.account
        self.info_label.setText(
            f"Cliente: {a.client_name}  |  Factura: {a.invoice_number}")
        if a.status == "pendiente":
            status_color = "#f59e0b"
        elif a.status == "anulada":
            status_color = "#8b93a3"
        else:
            status_color = "#2fbf71"
        self.summary_label.setText(
            f"Total: {format_currency(a.total)}  |  "
            f"Pagado: {format_currency(a.amount_paid)}  |  "
            f"Saldo: <span style='color:{status_color};font-weight:bold'>"
            f"{format_currency(a.balance)}</span>  |  "
            f"Estado: {a.status.upper()}")
        self.pay_button.setEnabled(a.status == "pendiente")
        svc: CreditService = self.services["credit"]
        payments = svc.get_payments(a.id)
        self.payments_table.setRowCount(len(payments))
        for row, p in enumerate(payments):
            notes = p.notes or ""
            images_count = len(svc.list_payment_images(p.id))
            if images_count:
                notes = f"📎 {images_count}  {notes}".strip()
            values = [
                p.created_at[:16] if p.created_at else "",
                format_currency(p.amount),
                p.payment_method.capitalize(),
                notes,
            ]
            for col, val in enumerate(values):
                item = QTableWidgetItem(val)
                item.setData(Qt.ItemDataRole.UserRole, p)
                self.payments_table.setItem(row, col, item)
        self.payments_table.resizeColumnsToContents()

    def _open_payment_gallery(self) -> None:
        row = self.payments_table.currentRow()
        if row < 0:
            return
        item = self.payments_table.item(row, 0)
        payment = item.data(Qt.ItemDataRole.UserRole) if item else None
        if payment is None:
            return
        svc: CreditService = self.services["credit"]
        if not svc.list_payment_images(payment.id):
            QMessageBox.information(
                self, "Comprobantes",
                "Este abono no tiene comprobantes adjuntos.")
            return
        dialog = PaymentGalleryDialog(payment, self.services, parent=self)
        dialog.exec()

    def _open_payment(self) -> None:
        svc: CreditService = self.services["credit"]
        account = svc.get_by_id(self.account.id)
        if account is None:
            return
        dialog = PaymentDialog(account, self.services, parent=self)
        if dialog.exec() and dialog.payment_id is not None:
            self.account = svc.get_by_id(self.account.id) or self.account
            self._load_data()
            self.data_changed.emit()


class CreditSaleDialog(QDialog):
    """Diálogo para crear una venta a crédito: cliente + productos + confirmación."""

    def __init__(self, services: dict, cart: list[dict] | None = None,
                 client=None, parent: QWidget | None = None):
        super().__init__(parent)
        self.services = services
        self.cart: list[dict] = [dict(item) for item in cart] if cart else []
        self.client = client
        self.setWindowTitle("Nueva Venta a Crédito")
        self.setMinimumSize(700, 520)
        self._setup_ui()
        if client:
            self._set_client(client)
        if self.cart:
            self._update_cart_display()
        self._search_products()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        client_row = QHBoxLayout()
        client_label = QLabel("Cliente:")
        self.client_label = QLabel("Sin cliente seleccionado")
        self.client_label.setStyleSheet("font-weight: bold; font-size: 15px;")
        pick_btn = QPushButton("Seleccionar Cliente")
        pick_btn.setObjectName("primaryButton")
        pick_btn.clicked.connect(self._pick_client)
        client_row.addWidget(client_label)
        client_row.addWidget(self.client_label, 1)
        client_row.addWidget(pick_btn)
        layout.addLayout(client_row)

        sep = QFrame()
        sep.setObjectName("separator")
        sep.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(sep)

        self.cart_table = QTableWidget(0, 4)
        self.cart_table.setHorizontalHeaderLabels(
            ["Producto", "Cant", "Precio", "Total"])
        self.cart_table.horizontalHeader().setObjectName("tableHeader")
        self.cart_table.verticalHeader().setVisible(False)
        self.cart_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows)
        self.cart_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers)
        self.cart_table.setAlternatingRowColors(True)
        layout.addWidget(self.cart_table, 1)

        add_row = QHBoxLayout()
        self.product_search = QLineEdit()
        self.product_search.setPlaceholderText("Buscar producto por nombre o código...")
        self.product_search.textChanged.connect(lambda _: self._search_products())
        self.product_search.returnPressed.connect(self._search_products)
        add_row.addWidget(self.product_search, 1)
        remove_btn = QPushButton("Quitar")
        remove_btn.setObjectName("dangerButton")
        remove_btn.clicked.connect(self._remove_item)
        add_row.addWidget(remove_btn)
        layout.addLayout(add_row)

        self.product_hint = QLabel(
            "Haga clic en un producto para agregarlo al carrito.")
        self.product_hint.setStyleSheet("font-size: 13px; color: #8b93a3;")
        layout.addWidget(self.product_hint)

        self.product_list = QTableWidget(0, 3)
        self.product_list.setHorizontalHeaderLabels(["Nombre", "Precio", "Agregar"])
        self.product_list.horizontalHeader().setObjectName("tableHeader")
        self.product_list.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch)
        self.product_list.verticalHeader().setVisible(False)
        self.product_list.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows)
        self.product_list.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers)
        self.product_list.setAlternatingRowColors(True)
        self.product_list.setMaximumHeight(220)
        self.product_list.itemClicked.connect(self._on_product_clicked)
        layout.addWidget(self.product_list)

        totals_row = QHBoxLayout()
        self.subtotal_label = QLabel("Subtotal: ₡0.00")
        self.tax_label = QLabel("IVA: ₡0.00")
        self.total_label = QLabel("TOTAL: ₡0.00")
        self.total_label.setStyleSheet(
            "font-size: 17px; font-weight: bold; color: #2fbf71;")
        totals_row.addWidget(self.subtotal_label)
        totals_row.addStretch(1)
        totals_row.addWidget(self.tax_label)
        totals_row.addStretch(1)
        totals_row.addWidget(self.total_label)
        layout.addLayout(totals_row)

        notes_row = QHBoxLayout()
        notes_label = QLabel("Notas:")
        self.notes_input = QLineEdit()
        self.notes_input.setPlaceholderText("Observaciones de la venta (opcional)")
        notes_row.addWidget(notes_label)
        notes_row.addWidget(self.notes_input, 1)
        layout.addLayout(notes_row)

        btn_row = QHBoxLayout()
        confirm_btn = QPushButton("Confirmar Venta a Crédito")
        confirm_btn.setObjectName("primaryButton")
        confirm_btn.clicked.connect(self._confirm)
        cancel_btn = QPushButton("Cancelar")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(confirm_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

    def _set_client(self, client) -> None:
        self.client = client
        name = getattr(client, "name", "?")
        id_num = getattr(client, "id_number", "")
        self.client_label.setText(f"{name} ({id_num})")

    def _pick_client(self) -> None:
        from modules.clients.client_widget import ClientPickerDialog
        dialog = ClientPickerDialog(self.services, parent=self)
        if dialog.exec() and dialog.selected is not None:
            self._set_client(dialog.selected)

    def _search_products(self) -> None:
        query = self.product_search.text().strip()
        service = self.services["product"]
        products = (service.search(query) if query else service.get_all()) or []
        self.product_list.setRowCount(len(products))
        for row, p in enumerate(products):
            name_item = QTableWidgetItem(p.name)
            name_item.setData(Qt.ItemDataRole.UserRole, p)
            self.product_list.setItem(row, 0, name_item)
            self.product_list.setItem(
                row, 1, QTableWidgetItem(format_currency(p.sale_price)))
            add_btn = QPushButton("+")
            add_btn.setObjectName("primaryButton")
            add_btn.setFixedHeight(24)
            add_btn.setToolTip(f"Agregar {p.name}")
            add_btn.clicked.connect(lambda _, prod=p: self._add_product(prod))
            self.product_list.setCellWidget(row, 2, add_btn)
        self.product_list.setColumnWidth(1, 100)
        self.product_list.setColumnWidth(2, 70)
        self.product_list.setVisible(True)

    def _add_product(self, product) -> None:
        if product is None:
            return
        for cart_item in self.cart:
            if cart_item["product_id"] == product.id:
                cart_item["quantity"] += 1
                self._update_cart_display()
                return
        self.cart.append({
            "product_id": product.id,
            "product_name": product.name,
            "quantity": 1,
            "unit_price": float(getattr(product, "sale_price", 0.0)),
            "tax_rate": float(getattr(product, "tax_rate", 0.0)),
            "discount": 0.0,
            "cabys_code": getattr(product, "cabys_code", "") or "",
            "total": float(getattr(product, "sale_price", 0.0)),
        })
        self._update_cart_display()

    def _on_product_clicked(self, item) -> None:
        if item is None:
            return
        name_item = self.product_list.item(item.row(), 0)
        product = name_item.data(Qt.ItemDataRole.UserRole) if name_item else None
        self._add_product(product)

    def _remove_item(self) -> None:
        row = self.cart_table.currentRow()
        if 0 <= row < len(self.cart):
            del self.cart[row]
            self._update_cart_display()

    def _update_cart_display(self) -> None:
        self.cart_table.setRowCount(len(self.cart))
        for row, item in enumerate(self.cart):
            item["total"] = (
                item["unit_price"] * item["quantity"]
                - item.get("discount", 0.0))
            values = [
                item["product_name"],
                str(item["quantity"]),
                format_currency(item["unit_price"]),
                format_currency(item["total"]),
            ]
            for col, val in enumerate(values):
                cell = QTableWidgetItem(val)
                if col > 0:
                    cell.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight
                        | Qt.AlignmentFlag.AlignVCenter)
                self.cart_table.setItem(row, col, cell)
        self.cart_table.resizeRowsToContents()
        totals = calculate_totals(self.cart)
        self.subtotal_label.setText(
            f"Subtotal: {format_currency(totals['subtotal'])}")
        self.tax_label.setText(
            f"IVA: {format_currency(totals['tax_amount'])}")
        self.total_label.setText(
            f"TOTAL: {format_currency(totals['total'])}")

    def _confirm(self) -> None:
        if not self.cart:
            QMessageBox.warning(
                self, "Carrito vacío",
                "Agregue productos antes de confirmar.")
            return
        if self.client is None:
            QMessageBox.warning(
                self, "Cliente requerido",
                "Seleccione un cliente para la venta a crédito.")
            return
        totals = calculate_totals(self.cart)
        answer = QMessageBox.question(
            self,
            "Confirmar Venta a Crédito",
            f"Cliente: {self.client.name}\n"
            f"Total: {format_currency(totals['total'])}\n\n"
            f"¿Confirmar la venta a crédito?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            cart_svc = self.services["cart"]
            sale = _build_dataclass(
                Sale,
                id=0,
                invoice_number="",
                client_id=self.client.id,
                client_name=self.client.name,
                subtotal=totals["subtotal"],
                discount=totals["discount"],
                tax_amount=totals["tax_amount"],
                total=totals["total"],
                payment_method="credito",
                cash_received=0.0,
                change_amount=0.0,
                payment_details="",
                invoice_type="general",
                sale_reference=uuid4().hex,
                currency="CRC",
                exchange_rate=0.0,
                status="PENDIENTE",
                hacienda_key="",
                hacienda_status="PENDIENTE",
                electronic_invoice=False,
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
            sale_id = cart_svc.create_sale(
                sale, items, credit_notes=self.notes_input.text().strip())
            created = cart_svc.get_sale(sale_id)
            invoice_number = created.invoice_number if created else ""
            QMessageBox.information(
                self, "Venta registrada",
                f"Venta a crédito #{invoice_number} creada correctamente.")
            self.accept()
        except Exception as exc:
            QMessageBox.critical(
                self, "Error",
                f"No se pudo crear la venta a crédito:\n{exc}")


class CreditWidget(QWidget):
    """Widget principal de la pestaña Crédito."""
    data_changed = pyqtSignal()

    def __init__(self, services: dict, parent: QWidget | None = None):
        super().__init__(parent)
        self.services = services
        self._setup_ui()
        self.refresh()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        header = QHBoxLayout()
        title = QLabel("Cuentas por Cobrar")
        title.setObjectName("sectionTitle")
        header.addWidget(title)
        header.addStretch(1)
        layout.addLayout(header)

        toolbar = QWidget()
        toolbar.setObjectName("reportToolbar")
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(10, 8, 10, 8)
        toolbar_layout.setSpacing(8)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Buscar cliente...")
        self.search_input.textChanged.connect(lambda _: self.refresh())
        toolbar_layout.addWidget(self.search_input, 1)

        self.filter_combo = NoWheelComboBox()
        self.filter_combo.addItems(["Todas", "Pendientes", "Pagadas", "Anuladas"])
        self.filter_combo.currentIndexChanged.connect(lambda _: self.refresh())
        toolbar_layout.addWidget(self.filter_combo)

        toolbar_layout.addStretch(1)

        self.new_sale_button = QPushButton("Nueva Venta a Crédito")
        self.new_sale_button.setObjectName("primaryButton")
        self.new_sale_button.clicked.connect(self._open_new_sale)
        toolbar_layout.addWidget(self.new_sale_button)

        self.pay_button = QPushButton("Registrar Abono")
        self.pay_button.setObjectName("primaryButton")
        self.pay_button.clicked.connect(self._open_payment)
        self.pay_button.setEnabled(False)
        toolbar_layout.addWidget(self.pay_button)

        layout.addWidget(toolbar)

        cards = QHBoxLayout()
        self.card_labels: dict[str, QLabel] = {}
        for key, title_text in (
            ("pendiente", "Pendiente"),
            ("pagado", "Pagado"),
            ("cuentas", "Cuentas"),
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

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels([
            "Cliente", "Identificación", "Factura", "Total",
            "Pagado", "Saldo", "Estado"])
        self.table.horizontalHeader().setObjectName("tableHeader")
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.setColumnWidth(0, 180)
        self.table.setColumnWidth(1, 120)
        self.table.setColumnWidth(2, 100)
        self.table.setColumnWidth(3, 110)
        self.table.setColumnWidth(4, 110)
        self.table.setColumnWidth(5, 110)
        self.table.setColumnWidth(6, 90)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.doubleClicked.connect(self._open_detail)
        self.table.itemSelectionChanged.connect(
            lambda: self.pay_button.setEnabled(
                self._selected_account() is not None))
        layout.addWidget(self.table, 1)

    def refresh(self) -> None:
        svc: CreditService = self.services["credit"]
        status_map = {"Todas": "", "Pendientes": "pendiente",
                      "Pagadas": "pagada", "Anuladas": "anulada"}
        status = status_map.get(self.filter_combo.currentText(), "")
        search = self.search_input.text().strip()
        accounts = svc.get_all(status_filter=status, client_search=search)
        self.table.setRowCount(len(accounts))
        for row, a in enumerate(accounts):
            if a.status == "pagada":
                status_icon = "🟢"
            elif a.status == "anulada":
                status_icon = "⚪"
            else:
                status_icon = "🟡"
            values = [
                a.client_name,
                a.client_id_number or "",
                a.invoice_number,
                format_currency(a.total),
                format_currency(a.amount_paid),
                format_currency(a.balance),
                f"{status_icon} {a.status.capitalize()}",
            ]
            for col, val in enumerate(values):
                item = QTableWidgetItem(str(val))
                if col == 5 and a.status == "pendiente":
                    item.setForeground(Qt.GlobalColor.yellow)
                self.table.setItem(row, col, item)
            self.table.item(row, 0).setData(
                Qt.ItemDataRole.UserRole, a)
        self.table.resizeColumnsToContents()
        summary = svc.get_summary()
        self.card_labels["pendiente"].setText(
            format_currency(summary["total_pendiente"]))
        self.card_labels["pagado"].setText(
            format_currency(summary["total_pagado"]))
        self.card_labels["cuentas"].setText(
            str(summary["total_cuentas"]))

    def _selected_account(self) -> CreditAccount | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _open_detail(self) -> None:
        account = self._selected_account()
        if account is None:
            return
        svc: CreditService = self.services["credit"]
        account = svc.get_by_id(account.id) or account
        dialog = CreditDetailDialog(account, self.services, parent=self)
        dialog.data_changed.connect(self._on_credit_changed)
        dialog.exec()
        # Siempre refrescar: el usuario pudo registrar abonos y cerrar con X/Esc.
        self._on_credit_changed()

    def _on_credit_changed(self) -> None:
        self.refresh()
        self.data_changed.emit()

    def _open_payment(self) -> None:
        account = self._selected_account()
        if account is None:
            QMessageBox.information(
                self, "Selección", "Seleccione una cuenta por cobrar.")
            return
        if account.status != "pendiente":
            if account.status == "anulada":
                QMessageBox.information(
                    self, "Cuenta anulada",
                    "Esta cuenta fue anulada y no admite abonos.")
            else:
                QMessageBox.information(
                    self, "Cuenta pagada", "Esta cuenta ya está pagada completamente.")
            return
        svc: CreditService = self.services["credit"]
        account = svc.get_by_id(account.id) or account
        dialog = PaymentDialog(account, self.services, parent=self)
        if dialog.exec():
            self.refresh()
            self.data_changed.emit()

    def start_new_credit_sale(self, cart: list[dict], client) -> bool:
        """Called from POS when 'Venta a Crédito' is clicked.

        Devuelve True si la venta a crédito se registró correctamente.
        """
        dialog = CreditSaleDialog(
            self.services, cart=cart, client=client, parent=self)
        if dialog.exec():
            self.refresh()
            self.data_changed.emit()
            return True
        return False

    def _open_new_sale(self) -> None:
        dialog = CreditSaleDialog(self.services, parent=self)
        if dialog.exec():
            self.refresh()
            self.data_changed.emit()
