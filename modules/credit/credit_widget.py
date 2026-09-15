"""Widget de cuentas por cobrar (Crédito) con tabla, resumen y diálogos."""

import json
import os
import shutil
from dataclasses import fields as dataclass_fields
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from PyQt6.QtCore import QDate, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QIcon, QPixmap
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
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
from utils.helpers import (
    ajustar_anchos_encabezado,
    format_currency,
    EmptyStateTable,
    NoWheelComboBox,
    NoWheelSpinBox,
    calculate_totals,
)

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

        self.upload_label = QLabel("")
        self.upload_label.setStyleSheet("font-size: 13px; color: #2fbf71;")
        layout.addWidget(self.upload_label)

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
            self.upload_label.setText("")
            return
        self.counter_label.setText(f"{self.index + 1} / {len(self.images)}")
        self._show_current()
        self._build_thumbs()

    def _show_current(self) -> None:
        img = self._current()
        if img is None:
            return
        fecha = img.created_at[:16] if img.created_at else "—"
        self.upload_label.setText(f"Subido: {fecha}")
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
            fecha = img.created_at[:16] if img.created_at else ""
            btn.setToolTip(f"{desc}\nSubido: {fecha}" if fecha else desc)
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
        tipo = ("Encargo" if (account.account_type or "credito") != "credito"
                else "Crédito")
        self.setWindowTitle(f"Detalle de {tipo} · {account.invoice_number}")
        self.setMinimumSize(560, 440)
        self._setup_ui()
        self._load_data()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        tipo_row = QHBoxLayout()
        es_encargo = (self.account.account_type or "credito") != "credito"
        chip = QLabel("Encargo" if es_encargo else "Crédito")
        chip.setObjectName("chipOrder" if es_encargo else "chipCredit")
        chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tipo_row.addWidget(chip)
        tipo_row.addStretch(1)
        layout.addLayout(tipo_row)

        self.info_label = QLabel()
        self.info_label.setObjectName("sectionTitle")
        self.info_label.setWordWrap(True)
        layout.addWidget(self.info_label)

        self.summary_label = QLabel()
        self.summary_label.setStyleSheet("font-size: 14px;")
        layout.addWidget(self.summary_label)

        self.delivery_label = QLabel()
        self.delivery_label.setStyleSheet("font-size: 14px; color: #8b93a3;")
        layout.addWidget(self.delivery_label)

        self.financing_label = QLabel()
        self.financing_label.setStyleSheet("font-size: 14px; color: #2fbf71;")
        layout.addWidget(self.financing_label)

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

        self.payments_table = EmptyStateTable("Sin abonos registrados.", 0, 4)
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
        self.payments_table.itemSelectionChanged.connect(
            self._update_attach_state)
        layout.addWidget(self.payments_table, 1)

        btn_row = QHBoxLayout()
        self.pay_button = QPushButton("Registrar Abono")
        self.pay_button.setObjectName("primaryButton")
        self.pay_button.clicked.connect(self._open_payment)
        btn_row.addWidget(self.pay_button)
        self.attach_button = QPushButton("Adjuntar comprobante")
        self.attach_button.setObjectName("secondaryButton")
        self.attach_button.setToolTip(
            "Adjunta una o varias imágenes a un abono ya registrado "
            "(seleccione la fila del abono).")
        self.attach_button.setEnabled(False)
        self.attach_button.clicked.connect(self._attach_to_payment)
        btn_row.addWidget(self.attach_button)
        self.deliver_button = QPushButton("Entregar")
        self.deliver_button.setObjectName("secondaryButton")
        self.deliver_button.setToolTip(
            "Marca el encargo como entregado; si hay saldo, lo cobra primero.")
        self.deliver_button.clicked.connect(self._deliver)
        btn_row.addWidget(self.deliver_button)
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
        es_encargo = (a.account_type or "credito") != "credito"
        if es_encargo:
            if a.delivery_status == "entregado":
                fecha = a.delivered_at[:16] if a.delivered_at else ""
                self.delivery_label.setText(
                    f"Entrega: ENTREGADO{' el ' + fecha if fecha else ''}")
            else:
                pactada = f"  |  Pactada: {a.due_date}" if a.due_date else ""
                self.delivery_label.setText(f"Entrega: PENDIENTE{pactada}")
            self.deliver_button.setVisible(True)
            self.deliver_button.setEnabled(
                a.delivery_status != "entregado" and a.status != "anulada")
        else:
            self.delivery_label.setText("")
            self.deliver_button.setVisible(False)
        if a.financing_months and a.financing_installment:
            self.financing_label.setText(
                f"Plan: {a.financing_months} meses de "
                f"{format_currency(a.financing_installment)} (sin intereses)")
        else:
            self.financing_label.setText("")
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

    def _selected_payment(self):
        row = self.payments_table.currentRow()
        if row < 0:
            return None
        item = self.payments_table.item(row, 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _update_attach_state(self) -> None:
        self.attach_button.setEnabled(self._selected_payment() is not None)

    def _attach_to_payment(self) -> None:
        """Adjunta comprobantes a un abono ya registrado (con fecha de subida)."""
        payment = self._selected_payment()
        if payment is None:
            QMessageBox.information(
                self, "Comprobantes",
                "Seleccione un abono en el historial para adjuntarle "
                "comprobantes.")
            return
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Seleccionar comprobantes", "",
            "Imágenes (*.png *.jpg *.jpeg *.webp *.bmp);;Todos los archivos (*)")
        if not paths:
            return
        svc: CreditService = self.services["credit"]
        docs_dir = _ensure_docs_dir()
        agregadas = 0
        for path in paths:
            ext = Path(path).suffix or ".jpg"
            dest = Path(docs_dir) / f"pago_{payment.id}_{uuid4().hex[:8]}{ext}"
            try:
                shutil.copy2(path, dest)
                svc.add_payment_image(payment.id, str(dest), "")
                agregadas += 1
            except Exception as exc:
                QMessageBox.warning(
                    self, "Comprobantes",
                    f"No se pudo adjuntar {Path(path).name}:\n{exc}")
        if agregadas:
            self._load_data()
            self.data_changed.emit()

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

    def _deliver(self) -> None:
        """Entrega el encargo: cobra el saldo si hace falta y marca entregado."""
        svc: CreditService = self.services["credit"]
        account = svc.get_by_id(self.account.id)
        if account is None:
            return
        if float(account.balance or 0) > 0:
            answer = QMessageBox.question(
                self, "Entregar encargo",
                f"Saldo pendiente: {format_currency(account.balance)}.\n"
                f"¿Cobrar el saldo y marcar como entregado?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            dialog = PaymentDialog(account, self.services, parent=self)
            if not (dialog.exec() and dialog.payment_id is not None):
                return
            account = svc.get_by_id(account.id) or account
            if float(account.balance or 0) > 0:
                answer = QMessageBox.question(
                    self, "Saldo pendiente",
                    f"Queda un saldo de {format_currency(account.balance)}.\n"
                    f"¿Marcar el encargo como entregado de todas formas?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if answer != QMessageBox.StandardButton.Yes:
                    return
        svc.mark_delivered(account.id)
        self._generar_factura(account)
        self.account = svc.get_by_id(account.id) or account
        self._load_data()
        self.data_changed.emit()

    def _items_para_factura(self, sale) -> list[dict]:
        """Reconstruye las líneas (con CABYS/IVA) para el XML de la factura."""
        product_svc = self.services.get("product")
        items = []
        for item in sale.items or []:
            product = None
            if product_svc is not None:
                try:
                    product = product_svc.get_by_id(item.product_id)
                except Exception:
                    product = None
            items.append({
                "product_id": item.product_id,
                "product_name": item.product_name,
                "quantity": item.quantity,
                "unit_price": item.unit_price,
                "tax_rate": float(getattr(product, "tax_rate", 0.0) or 0.0),
                "discount": item.discount,
                "cabys_code": getattr(product, "cabys_code", "") or "",
                "total": item.total,
            })
        return items

    def _generar_factura(self, account) -> None:
        """Genera la factura del encargo entregado y ofrece imprimirla.

        Arma el respaldo XML de la factura electrónica (si hay cliente) e
        intenta enviarlo al proveedor FE; el PDF se genera siempre.
        """
        db = self.services.get("db")
        cart_svc = self.services.get("cart")
        if db is None or cart_svc is None:
            return
        try:
            from modules.documentos.factura_service import (
                generar_documentos,
                reimprimir_factura,
            )
            from modules.documentos.xml_factura import (
                build_factura_payload,
                cargar_empresa,
            )
            saved = cart_svc.get_sale(account.sale_id)
            if saved is None:
                return
            company = cargar_empresa(db)
            clave = ""
            payload = None
            client = None
            simplificada = (saved.invoice_type or "general") == "simplificada"
            if saved.client_id and not simplificada:
                client = self.services["client"].get_by_id(saved.client_id)
            if client is not None:
                totals = {
                    "subtotal": saved.subtotal,
                    "discount": saved.discount,
                    "tax_amount": saved.tax_amount,
                    "total": saved.total,
                }
                consecutivo = (f"{company.get('branch', '001')}-"
                               f"{company.get('terminal', '001')}-"
                               f"{saved.id:010d}")
                payload = build_factura_payload(
                    company, client, self._items_para_factura(saved),
                    totals, consecutivo)
                try:
                    response = self.services["hacienda"].send_electronic_invoice(
                        payload)
                except Exception:
                    response = None
                if response:
                    clave = str(response.get("clave", ""))
                    estado = "ACEPTADA" if clave else "ENVIADA"
                    try:
                        cart_svc.update_hacienda_status(saved.id, clave, estado)
                    except Exception:
                        pass
            resultado = generar_documentos(
                saved, company, payload=payload, clave=clave, medio_pago="01")
        except Exception as exc:
            QMessageBox.warning(
                self, "Factura del encargo",
                f"El encargo se entregó, pero no se pudo generar la "
                f"factura:\n{exc}")
            return
        destino = resultado.get("pdf") or resultado.get("carpeta") or ""
        answer = QMessageBox.question(
            self, "Factura del encargo",
            f"Encargo entregado. Factura guardada en:\n{destino}\n\n"
            f"¿Imprimir la factura ahora?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            reimprimir_factura(db, cart_svc, account.sale_id, imprimir=True)


class CreditSaleDialog(QDialog):
    """Diálogo para crear una venta a crédito o un encargo/apartado.

    `mode="encargo"` agrega prima (opcional) y fecha de entrega pactada.
    """

    def __init__(self, services: dict, cart: list[dict] | None = None,
                 client=None, mode: str = "credito",
                 invoice_type: str = "general",
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.services = services
        self.cart: list[dict] = [dict(item) for item in cart] if cart else []
        self.client = client
        self.mode = mode
        self._promo_result: dict = {}
        es_encargo = mode == "encargo"
        self.setWindowTitle("Nuevo Encargo" if es_encargo
                            else "Nueva Venta a Crédito")
        self.setMinimumSize(700, 560 if es_encargo else 520)
        self._setup_ui()
        index = self.invoice_combo.findData(invoice_type)
        if index >= 0:
            self.invoice_combo.setCurrentIndex(index)
        if client:
            self._set_client(client)
        if self.cart:
            self._update_cart_display()
        self._search_products()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        top_row = QHBoxLayout()
        top_row.setSpacing(8)
        top_row.addWidget(QLabel("Cliente:"))
        self.client_label = QLabel("Sin cliente seleccionado")
        self.client_label.setStyleSheet("font-weight: bold; font-size: 15px;")
        self.client_label.setMinimumWidth(120)
        self.client_label.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        top_row.addWidget(self.client_label, 1)
        pick_btn = QPushButton("Seleccionar Cliente")
        pick_btn.setObjectName("primaryButton")
        pick_btn.clicked.connect(self._pick_client)
        top_row.addWidget(pick_btn)
        top_row.addSpacing(12)
        top_row.addWidget(QLabel("Documento:"))
        self.invoice_combo = NoWheelComboBox()
        self.invoice_combo.addItem("Factura Electrónica", "general")
        self.invoice_combo.addItem("Fact. Simplificada", "simplificada")
        self.invoice_combo.setToolTip(
            "La simplificada no cobra IVA. La electrónica usa el XML de "
            "respaldo al entregar.")
        self.invoice_combo.setMinimumWidth(150)
        self.invoice_combo.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.invoice_combo.currentIndexChanged.connect(
            lambda _: self._update_cart_display())
        top_row.addWidget(self.invoice_combo)
        layout.addLayout(top_row)

        sep = QFrame()
        sep.setObjectName("separator")
        sep.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(sep)

        self.cart_table = EmptyStateTable(
            "Sin productos en el carrito.", 0, 4)
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

        self.product_list = EmptyStateTable(
            "Sin productos disponibles.", 0, 3)
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
        self.discount_label = QLabel("Descuento: ₡0.00")
        self.tax_label = QLabel("IVA: ₡0.00")
        self.total_label = QLabel("TOTAL: ₡0.00")
        self.total_label.setStyleSheet(
            "font-size: 17px; font-weight: bold; color: #2fbf71;")
        totals_row.addWidget(self.subtotal_label)
        totals_row.addStretch(1)
        totals_row.addWidget(self.discount_label)
        totals_row.addStretch(1)
        totals_row.addWidget(self.tax_label)
        totals_row.addStretch(1)
        totals_row.addWidget(self.total_label)
        layout.addLayout(totals_row)

        self.promo_label = QLabel("")
        self.promo_label.setWordWrap(True)
        self.promo_label.setStyleSheet("font-size: 13px; color: #2fbf71;")
        layout.addWidget(self.promo_label)

        self.conditions_sep = QFrame()
        self.conditions_sep.setObjectName("separator")
        self.conditions_sep.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(self.conditions_sep)

        self.conditions_title = QLabel("Condiciones")
        self.conditions_title.setObjectName("cartSectionTitle")
        layout.addWidget(self.conditions_title)

        self.order_row = QWidget()
        order_layout = QHBoxLayout(self.order_row)
        order_layout.setContentsMargins(0, 0, 0, 0)
        order_layout.setSpacing(8)
        prima_label = QLabel("Prima:")
        self.prima_input = NoWheelSpinBox()
        self.prima_input.setRange(0.0, 99_999_999.0)
        self.prima_input.setDecimals(2)
        self.prima_input.setPrefix("₡ ")
        self.prima_method = NoWheelComboBox()
        self.prima_method.addItems(["Efectivo", "Sinpe", "Tarjeta"])
        self.deliver_check = QCheckBox("Fecha de entrega pactada")
        self.due_date_input = QDateEdit(QDate.currentDate())
        self.due_date_input.setCalendarPopup(True)
        self.due_date_input.setDisplayFormat("dd/MM/yyyy")
        self.due_date_input.setEnabled(False)
        self.deliver_check.toggled.connect(self.due_date_input.setEnabled)
        order_layout.addWidget(prima_label)
        order_layout.addWidget(self.prima_input)
        order_layout.addWidget(self.prima_method)
        order_layout.addWidget(self.deliver_check)
        order_layout.addWidget(self.due_date_input)
        order_layout.addStretch(1)
        self.order_row.setVisible(self.mode == "encargo")
        layout.addWidget(self.order_row)

        self.plan_row = QWidget()
        plan_layout = QHBoxLayout(self.plan_row)
        plan_layout.setContentsMargins(0, 0, 0, 0)
        plan_layout.setSpacing(8)
        plan_layout.addWidget(QLabel("Plan:"))
        self.plan_combo = NoWheelComboBox()
        self.plan_combo.addItem("Contado (sin plan)", 0)
        plan_layout.addWidget(self.plan_combo)
        plan_hint = QLabel("Meses sin intereses (promoción)")
        plan_hint.setStyleSheet("font-size: 13px; color: #8b93a3;")
        plan_layout.addWidget(plan_hint)
        plan_layout.addStretch(1)
        self.plan_row.setVisible(False)
        layout.addWidget(self.plan_row)
        self._financing: dict | None = None
        self._update_conditions_visibility()

        notes_row = QHBoxLayout()
        notes_label = QLabel("Notas:")
        self.notes_input = QLineEdit()
        self.notes_input.setPlaceholderText("Observaciones de la venta (opcional)")
        notes_row.addWidget(notes_label)
        notes_row.addWidget(self.notes_input, 1)
        layout.addLayout(notes_row)

        btn_row = QHBoxLayout()
        confirm_btn = QPushButton(
            "Confirmar Encargo" if self.mode == "encargo"
            else "Confirmar Venta a Crédito")
        confirm_btn.setObjectName("primaryButton")
        confirm_btn.clicked.connect(self._confirm)
        cancel_btn = QPushButton("Cancelar")
        cancel_btn.setObjectName("secondaryButton")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addStretch(1)
        btn_row.addWidget(confirm_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

    def _set_client(self, client) -> None:
        self.client = client
        name = getattr(client, "name", "?")
        id_num = getattr(client, "id_number", "")
        self.client_label.setText(f"{name} ({id_num})")
        self.client_label.setToolTip(f"{name} ({id_num})")

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
        self.product_list.setColumnWidth(1, 104)
        self.product_list.setColumnWidth(2, 92)
        ajustar_anchos_encabezado(self.product_list, {1: 104, 2: 92})
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

    def _aplicar_promociones(self) -> dict:
        """Aplica promociones de producto y calcula el plan de financiamiento."""
        service = None
        if isinstance(self.services, dict):
            service = self.services.get("promotions")
        for item in self.cart:
            item["discount"] = 0.0
        self._promo_result = {}
        if service is None or not self.cart:
            self._update_financing_options({})
            return {}
        try:
            resultado = service.evaluate(
                self.cart, es_credito=(self.mode == "credito"))
        except Exception:
            self._update_financing_options({})
            return {}
        for index, amount in (resultado.get("line_discounts") or {}).items():
            try:
                self.cart[int(index)]["discount"] = float(amount)
            except (IndexError, TypeError, ValueError):
                continue
        self._promo_result = resultado
        self._update_financing_options(resultado)
        return resultado

    def _update_financing_options(self, resultado: dict) -> None:
        """Llena el selector de plan "meses sin intereses" si la promo aplica."""
        financing = (resultado or {}).get("financing")
        self._financing = financing
        self.plan_combo.blockSignals(True)
        self.plan_combo.clear()
        self.plan_combo.addItem("Contado (sin plan)", 0)
        if financing:
            for months in financing.get("months") or []:
                cuota = (financing.get("installments") or {}).get(str(months), 0.0)
                self.plan_combo.addItem(
                    f"{months} meses de {format_currency(cuota)}", int(months))
        self.plan_combo.blockSignals(False)
        self.plan_row.setVisible(bool(financing) and self.mode == "credito")
        self._update_conditions_visibility()

    def _update_conditions_visibility(self) -> None:
        """Muestra el bloque "Condiciones" solo si hay campos de condiciones."""
        visible = (not self.order_row.isHidden()) or (not self.plan_row.isHidden())
        self.conditions_sep.setVisible(visible)
        self.conditions_title.setVisible(visible)

    def _update_cart_display(self) -> None:
        resultado = self._aplicar_promociones()
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
        simplificada = self.invoice_combo.currentData() == "simplificada"
        totals = calculate_totals(self.cart, exento=simplificada)
        self.subtotal_label.setText(
            f"Subtotal: {format_currency(totals['subtotal'])}")
        self.discount_label.setText(
            f"Descuento: {format_currency(totals['discount'])}")
        self.tax_label.setText(
            f"IVA: {format_currency(totals['tax_amount'])}")
        self.total_label.setText(
            f"TOTAL: {format_currency(totals['total'])}")
        aplicadas = (resultado or {}).get("applied") or []
        if aplicadas:
            texto = " · ".join(
                f"{promo['name']} (−{format_currency(promo['amount'])})"
                for promo in aplicadas)
            self.promo_label.setText(f"Promos: {texto}")
            self.discount_label.setToolTip(texto)
        else:
            self.promo_label.setText("")
            self.discount_label.setToolTip("")

    def _confirm(self) -> None:
        if not self.cart:
            QMessageBox.warning(
                self, "Carrito vacío",
                "Agregue productos antes de confirmar.")
            return
        if self.client is None:
            QMessageBox.warning(
                self, "Cliente requerido",
                "Seleccione un cliente para continuar.")
            return
        es_encargo = self.mode == "encargo"
        simplificada = self.invoice_combo.currentData() == "simplificada"
        totals = calculate_totals(self.cart, exento=simplificada)
        prima = float(self.prima_input.value()) if es_encargo else 0.0
        if prima > totals["total"]:
            QMessageBox.warning(
                self, "Prima inválida",
                f"La prima ({format_currency(prima)}) no puede superar el "
                f"total ({format_currency(totals['total'])}).")
            return
        due_date = ""
        if es_encargo and self.deliver_check.isChecked():
            due_date = self.due_date_input.date().toString("yyyy-MM-dd")
        financing_months = 0
        financing_installment = 0.0
        if self.mode == "credito" and self.plan_row.isVisible():
            months = int(self.plan_combo.currentData() or 0)
            if months > 0:
                financing_months = months
                financing_installment = float(
                    (self._financing or {}).get("installments", {}).get(
                        str(months), 0.0))
        titulo = "Confirmar Encargo" if es_encargo else "Confirmar Venta a Crédito"
        resumen = (f"Cliente: {self.client.name}\n"
                   f"Total: {format_currency(totals['total'])}\n")
        if es_encargo:
            resumen += f"Prima: {format_currency(prima)}\n"
            if due_date:
                resumen += f"Entrega pactada: {due_date}\n"
            resumen += "\n¿Confirmar el encargo?"
        else:
            if financing_months > 0:
                resumen += (f"Plan: {financing_months} meses de "
                            f"{format_currency(financing_installment)} "
                            f"(sin intereses)\n")
            resumen += "\n¿Confirmar la venta a crédito?"
        answer = QMessageBox.question(
            self, titulo, resumen,
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
                promotions_applied=json.dumps(
                    self._promo_result.get("applied") or [], ensure_ascii=False),
                invoice_type="simplificada" if simplificada else "general",
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
                sale, items,
                credit_notes=self.notes_input.text().strip(),
                account_type="encargo" if es_encargo else "credito",
                due_date=due_date,
                prima=prima,
                prima_method=(self.prima_method.currentText().lower()
                              if es_encargo else "efectivo"),
                financing_months=financing_months,
                financing_installment=financing_installment,
            )
            created = cart_svc.get_sale(sale_id)
            invoice_number = created.invoice_number if created else ""
            etiqueta = "Encargo" if es_encargo else "Venta a crédito"
            QMessageBox.information(
                self, "Registro exitoso",
                f"{etiqueta} #{invoice_number} registrado correctamente.")
            self.accept()
        except Exception as exc:
            QMessageBox.critical(
                self, "Error",
                f"No se pudo registrar:\n{exc}")


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
        title = QLabel("Crédito y Encargos")
        title.setObjectName("sectionTitle")
        header.addWidget(title)
        header.addStretch(1)
        layout.addLayout(header)

        toolbar = QWidget()
        toolbar.setObjectName("reportToolbar")
        toolbar_root = QVBoxLayout(toolbar)
        toolbar_root.setContentsMargins(10, 8, 10, 8)
        toolbar_root.setSpacing(6)

        toolbar_layout = QHBoxLayout()
        toolbar_layout.setSpacing(8)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Buscar cliente...")
        self.search_input.textChanged.connect(lambda _: self.refresh())
        toolbar_layout.addWidget(self.search_input, 1)

        self.type_combo = NoWheelComboBox()
        self.type_combo.addItems(["Todos", "Créditos", "Encargos"])
        self.type_combo.currentIndexChanged.connect(lambda _: self.refresh())
        toolbar_layout.addWidget(self.type_combo)

        self.filter_combo = NoWheelComboBox()
        self.filter_combo.addItems(["Todas", "Pendientes", "Pagadas", "Anuladas"])
        self.filter_combo.currentIndexChanged.connect(lambda _: self.refresh())
        toolbar_layout.addWidget(self.filter_combo)

        toolbar_layout.addStretch(1)
        toolbar_root.addLayout(toolbar_layout)

        actions_layout = QHBoxLayout()
        actions_layout.setSpacing(8)

        self.new_sale_button = QPushButton("Nueva Venta a Crédito")
        self.new_sale_button.setObjectName("primaryButton")
        self.new_sale_button.clicked.connect(self._open_new_sale)
        actions_layout.addWidget(self.new_sale_button)

        self.new_order_button = QPushButton("Nuevo Encargo")
        self.new_order_button.setObjectName("primaryButton")
        self.new_order_button.setToolTip(
            "Encargo o apartado: registra la prima (opcional) y el saldo "
            "contra entrega.")
        self.new_order_button.clicked.connect(self._open_new_order)
        actions_layout.addWidget(self.new_order_button)

        actions_layout.addStretch(1)

        self.pay_button = QPushButton("Registrar Abono")
        self.pay_button.setObjectName("secondaryButton")
        self.pay_button.setToolTip(
            "Seleccione una cuenta pendiente de la tabla para abonar.")
        self.pay_button.clicked.connect(self._open_payment)
        self.pay_button.setEnabled(False)
        actions_layout.addWidget(self.pay_button)
        toolbar_root.addLayout(actions_layout)

        layout.addWidget(toolbar)

        cards = QHBoxLayout()
        self.card_labels: dict[str, QLabel] = {}
        for key, title_text in (
            ("pendiente", "Pendiente"),
            ("pagado", "Pagado"),
            ("cuentas", "Cuentas"),
            ("encargos", "Encargos"),
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

        self.table = EmptyStateTable(
            "No hay cuentas por cobrar con los filtros actuales.", 0, 9)
        self.table.setHorizontalHeaderLabels([
            "Cliente", "Tipo", "Identificación", "Factura", "Total",
            "Pagado", "Saldo", "Estado", "Entrega"])
        self.table.horizontalHeader().setObjectName("tableHeader")
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.setColumnWidth(0, 200)
        self.table.setColumnWidth(1, 112)
        self.table.setColumnWidth(2, 140)
        self.table.setColumnWidth(3, 108)
        self.table.setColumnWidth(4, 118)
        self.table.setColumnWidth(5, 118)
        self.table.setColumnWidth(6, 118)
        self.table.setColumnWidth(7, 140)
        self.table.setColumnWidth(8, 118)
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
        type_map = {"Todos": "", "Créditos": "credito", "Encargos": "encargo"}
        status = status_map.get(self.filter_combo.currentText(), "")
        tipo = type_map.get(self.type_combo.currentText(), "")
        search = self.search_input.text().strip()
        accounts = svc.get_all(status_filter=status, client_search=search,
                               type_filter=tipo)
        self.table.setRowCount(len(accounts))
        for row, a in enumerate(accounts):
            if a.status == "pagada":
                status_icon = "🟢"
            elif a.status == "anulada":
                status_icon = "⚪"
            else:
                status_icon = "🟡"
            es_encargo = (a.account_type or "credito") != "credito"
            if not es_encargo:
                entrega = "—"
            elif a.delivery_status == "entregado":
                entrega = "Entregado"
            else:
                entrega = "Pendiente"
            values = [
                a.client_name,
                "",
                a.client_id_number or "",
                a.invoice_number,
                format_currency(a.total),
                format_currency(a.amount_paid),
                format_currency(a.balance),
                f"{status_icon} {a.status.capitalize()}",
                entrega,
            ]
            for col, val in enumerate(values):
                item = QTableWidgetItem(str(val))
                if col == 6 and a.status == "pendiente":
                    item.setForeground(Qt.GlobalColor.yellow)
                elif col == 8 and es_encargo and a.delivery_status != "entregado":
                    item.setForeground(Qt.GlobalColor.yellow)
                elif col == 3 and es_encargo:
                    item.setForeground(QColor("#f5b23c"))
                self.table.setItem(row, col, item)
            self.table.item(row, 0).setData(
                Qt.ItemDataRole.UserRole, a)
            self.table.setCellWidget(
                row, 1,
                self._make_type_chip("Encargo" if es_encargo else "Crédito"))
        self.table.resizeColumnToContents(0)
        if self.table.columnWidth(0) > 200:
            self.table.setColumnWidth(0, 200)
        for col, ancho in ((1, 112), (2, 140), (3, 108), (4, 118), (5, 118),
                           (6, 118), (7, 140), (8, 118)):
            self.table.setColumnWidth(col, ancho)
        summary = svc.get_summary()
        self.card_labels["pendiente"].setText(
            format_currency(summary["total_pendiente"]))
        self.card_labels["pagado"].setText(
            format_currency(summary["total_pagado"]))
        self.card_labels["cuentas"].setText(
            str(summary["total_cuentas"]))
        self.card_labels["encargos"].setText(
            str(summary["encargos_pendientes"]))
        self.card_labels["encargos"].setToolTip(
            f"Saldo pendiente de encargos: "
            f"{format_currency(summary['total_encargos'])}")

    def _make_type_chip(self, tipo: str) -> QWidget:
        """Chip centrado para distinguir Crédito (azul) de Encargo (ámbar)."""
        chip = QLabel(tipo)
        chip.setObjectName("chipOrder" if tipo == "Encargo" else "chipCredit")
        chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        holder = QWidget()
        holder_layout = QHBoxLayout(holder)
        holder_layout.setContentsMargins(8, 4, 8, 4)
        holder_layout.addWidget(chip)
        holder_layout.addStretch(1)
        holder.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        chip.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        return holder

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

    def start_new_credit_sale(self, cart: list[dict], client,
                              invoice_type: str = "general") -> bool:
        """Called from POS when 'Venta a Crédito' is clicked.

        Devuelve True si la venta a crédito se registró correctamente.
        """
        dialog = CreditSaleDialog(
            self.services, cart=cart, client=client,
            invoice_type=invoice_type, parent=self)
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

    def _open_new_order(self) -> None:
        dialog = CreditSaleDialog(self.services, mode="encargo", parent=self)
        if dialog.exec():
            self.refresh()
            self.data_changed.emit()
