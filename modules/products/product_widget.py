"""Widget de CRUD de productos."""

from dataclasses import fields as dataclass_fields

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from database.models import Product
from network.image_store import ImageStore
from utils.helpers import (
    ajustar_anchos_encabezado,
    format_currency,
    EmptyStateTable,
    NoWheelSpinBox,
    NoWheelComboBox,
)

TAX_TYPES = [("gravado", "Gravado (IVA)"), ("exento", "Exento")]


def _build_dataclass(cls, **kwargs):
    names = {f.name for f in dataclass_fields(cls)}
    return cls(**{key: value for key, value in kwargs.items() if key in names})


class ProductDialog(QDialog):
    def __init__(self, services: dict, product=None, parent=None):
        super().__init__(parent)
        self.services = services
        self.product = product
        self._pending_image: str | None = None
        self._remove_image_flag = False
        self.setWindowTitle("Editar Producto" if product else "Nuevo Producto")
        self.setMinimumWidth(460)
        self.setMaximumHeight(500)
        self._setup_ui()
        if product:
            self._load_product(product)

    def _setup_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(18, 14, 18, 10)

        self.code_input = QLineEdit()
        self.code_input.setPlaceholderText("Código interno")
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Nombre del producto")
        self.description_input = QLineEdit()
        self.description_input.setPlaceholderText("Descripción")

        self.category_combo = NoWheelComboBox()
        for category in self.services["category"].get_all(active_only=True) or []:
            self.category_combo.addItem(category.name, category.id)

        self.cost_spin = NoWheelSpinBox()
        self.cost_spin.setRange(0.0, 99_999_999.0)
        self.cost_spin.setDecimals(2)
        self.cost_spin.setToolTip("Costo de fabricación del producto. Se resta automáticamente en los reportes por cada venta.")
        self.sale_spin = NoWheelSpinBox()
        self.sale_spin.setRange(0.0, 99_999_999.0)
        self.sale_spin.setDecimals(2)

        self.wood_input = QLineEdit()
        self.wood_input.setPlaceholderText("Tipo de madera (ej. cedro, roble)")

        self.tax_type_combo = NoWheelComboBox()
        for value, label in TAX_TYPES:
            self.tax_type_combo.addItem(label, value)
        self.tax_type_combo.currentIndexChanged.connect(self._on_tax_type_changed)

        self.tax_rate_spin = NoWheelSpinBox()
        self.tax_rate_spin.setRange(0.0, 100.0)
        self.tax_rate_spin.setDecimals(2)
        self.tax_rate_spin.setSuffix(" %")

        self.active_check = QCheckBox("Producto activo")
        self.active_check.setChecked(True)

        form = [
            ("Código:", self.code_input),
            ("Nombre:", self.name_input),
            ("Tipo de madera:", self.wood_input),
            ("Categoría:", self.category_combo),
            ("Descripción:", self.description_input),
            ("Costo de fabricación:", self.cost_spin),
            ("Precio venta:", self.sale_spin),
            ("Tipo de impuesto:", self.tax_type_combo),
            ("Tasa de impuesto:", self.tax_rate_spin),
        ]
        for label_text, widget in form:
            layout.addWidget(QLabel(label_text))
            layout.addWidget(widget)

        layout.addWidget(self.active_check)

        layout.addWidget(QLabel("Foto del producto"))

        self.image_preview = QLabel()
        self.image_preview.setObjectName("imagePreview")
        self.image_preview.setFixedSize(120, 120)
        self.image_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.image_preview)

        image_buttons = QHBoxLayout()
        select_button = QPushButton("Seleccionar imagen…")
        select_button.clicked.connect(self._select_image)
        remove_button = QPushButton("Quitar imagen")
        remove_button.clicked.connect(self._remove_image)
        image_buttons.addWidget(select_button)
        image_buttons.addWidget(remove_button)
        layout.addLayout(image_buttons)

        scroll.setWidget(container)
        root_layout.addWidget(scroll, 1)

        buttons = QHBoxLayout()
        save_button = QPushButton("Guardar")
        save_button.setObjectName("primaryButton")
        save_button.clicked.connect(self._save)
        cancel_button = QPushButton("Cancelar")
        cancel_button.clicked.connect(self.reject)
        buttons.addWidget(save_button)
        buttons.addWidget(cancel_button)
        root_layout.addLayout(buttons)

    def _on_tax_type_changed(self) -> None:
        if self.tax_type_combo.currentData() == "exento":
            self.tax_rate_spin.setValue(0.0)
        elif self.tax_rate_spin.value() == 0.0:
            self.tax_rate_spin.setValue(13.0)

    def _load_product(self, product) -> None:
        self.code_input.setText(getattr(product, "code", "") or "")
        self.name_input.setText(getattr(product, "name", "") or "")
        self.description_input.setText(getattr(product, "description", "") or "")
        index = self.category_combo.findData(getattr(product, "category_id", None))
        if index >= 0:
            self.category_combo.setCurrentIndex(index)
        self.wood_input.setText(getattr(product, "wood_type", "") or "")
        self.cost_spin.setValue(float(getattr(product, "cost_price", 0.0)))
        self.sale_spin.setValue(float(getattr(product, "sale_price", 0.0)))
        tax_type = getattr(product, "tax_type", "gravado") or "gravado"
        tax_type_index = self.tax_type_combo.findData(tax_type)
        if tax_type_index >= 0:
            self.tax_type_combo.setCurrentIndex(tax_type_index)
        self.tax_rate_spin.setValue(float(getattr(product, "tax_rate", 0.0)))
        self.active_check.setChecked(bool(getattr(product, "active", True)))
        self._show_current_image()

    def _set_preview_pixmap(self, pixmap=None) -> None:
        if pixmap is None:
            pixmap = ImageStore.placeholder_pixmap(
                self.name_input.text().strip() or "?", 96)
        scaled = pixmap.scaled(
            116, 116,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.image_preview.setPixmap(scaled)

    def _show_current_image(self) -> None:
        filename = getattr(self.product, "image_path", "") or ""
        store = self.services.get("images")
        if not filename or store is None:
            self._set_preview_pixmap(None)
            return
        self._set_preview_pixmap(None)
        store.get_pixmap_async(filename, self._set_preview_pixmap)

    def _select_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar imagen del producto", "",
            "Imágenes (*.png *.jpg *.jpeg *.webp)")
        if not path:
            return
        pixmap = QPixmap(path)
        if pixmap.isNull():
            QMessageBox.warning(self, "Imagen",
                                "No se pudo leer la imagen seleccionada.")
            return
        self._pending_image = path
        self._remove_image_flag = False
        self._set_preview_pixmap(pixmap)

    def _remove_image(self) -> None:
        self._pending_image = None
        self._remove_image_flag = True
        self._set_preview_pixmap(None)

    def _save(self) -> None:
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Datos incompletos", "El nombre del producto es obligatorio.")
            return

        store = self.services.get("images")
        old_path = getattr(self.product, "image_path", "") or "" if self.product else ""
        image_path = old_path
        if self._pending_image:
            if store is None:
                image_path = ""
            else:
                try:
                    image_path = store.upload(self._pending_image)
                    if self.product and old_path:
                        store.delete(old_path)
                except Exception as exc:
                    QMessageBox.warning(
                        self, "Foto del producto",
                        f"No se pudo subir la foto. El producto se guardó sin ella:\n{exc}")
                    image_path = old_path
        elif self._remove_image_flag:
            if store is not None and old_path:
                store.delete(old_path)
            image_path = ""

        product = _build_dataclass(
            Product,
            id=self.product.id if self.product else 0,
            code=self.code_input.text().strip(),
            name=name,
            description=self.description_input.text().strip(),
            category_id=self.category_combo.currentData(),
            cost_price=self.cost_spin.value(),
            sale_price=self.sale_spin.value(),
            stock_quantity=float(getattr(self.product, "stock_quantity", 0.0)),
            min_stock=float(getattr(self.product, "min_stock", 0.0)),
            wood_type=self.wood_input.text().strip(),
            cabys_code=getattr(self.product, "cabys_code", "") or "",
            tax_type=self.tax_type_combo.currentData(),
            tax_rate=self.tax_rate_spin.value(),
            active=self.active_check.isChecked(),
            image_path=image_path,
            category_name="",
        )
        service = self.services["product"]
        if self.product:
            service.update(product)
        else:
            product.id = service.create(product)
        self.product = product
        self.accept()


class ProductGalleryDialog(QDialog):
    """Galería de fotos de un producto (varias imágenes por producto)."""

    def __init__(self, services: dict, product, parent: QWidget | None = None):
        super().__init__(parent)
        self.services = services
        self.product = product
        self.photos: list[str] = []
        self.index = 0
        self._block = False
        self.setWindowTitle(f"Galería — {getattr(product, 'name', '')}")
        self.setMinimumSize(560, 520)
        self.setMaximumHeight(720)
        self._setup_ui()
        self._reload_photos()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        title = QLabel(f"Fotos de: {getattr(self.product, 'name', '')}")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)

        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setMinimumHeight(260)
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

        self.thumbs_layout = QGridLayout()
        self.thumbs_layout.setContentsMargins(0, 0, 0, 0)
        self.thumbs_layout.setSpacing(8)
        self._thumbs_container = QWidget()
        self._thumbs_container.setLayout(self.thumbs_layout)
        layout.addWidget(self._thumbs_container)

        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        add_btn = QPushButton("Añadir foto")
        add_btn.setObjectName("primaryButton")
        add_btn.clicked.connect(self._add_photo)
        remove_btn = QPushButton("Quitar foto")
        remove_btn.setObjectName("dangerButton")
        remove_btn.clicked.connect(self._remove_photo)
        cover_btn = QPushButton("Definir portada")
        cover_btn.setObjectName("secondaryButton")
        cover_btn.clicked.connect(self._set_cover)
        action_row.addWidget(add_btn)
        action_row.addWidget(remove_btn)
        action_row.addWidget(cover_btn)
        layout.addLayout(action_row)

        close_btn = QPushButton("Cerrar")
        close_btn.setObjectName("closeButton")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

    def _product_service(self):
        return self.services["product"]

    def _image_store(self):
        return self.services.get("images")

    def _reload_photos(self) -> None:
        service = self._product_service()
        store = self._image_store()
        self.photos = service.list_images(self.product.id) if self.product.id else []
        cover = getattr(self.product, "image_path", "") or ""
        if cover and cover not in self.photos:
            self.photos.insert(0, cover)
        self.index = 0
        self._render()

    def _show_pixmap(self, filename: str) -> None:
        store = self._image_store()
        if store is None:
            self._set_placeholder()
            return
        store.get_pixmap_async(filename, lambda pixmap, name=filename: self._apply_main(name, pixmap))

    def _apply_main(self, filename: str, pixmap) -> None:
        if filename != self._current_filename():
            return
        if pixmap is None:
            self._set_placeholder()
            return
        scaled = pixmap.scaled(
            560, 400,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.image_label.setPixmap(scaled)

    def _current_filename(self) -> str:
        if 0 <= self.index < len(self.photos):
            return self.photos[self.index]
        return ""

    def _set_placeholder(self) -> None:
        self.image_label.setPixmap(
            ImageStore.placeholder_pixmap(getattr(self.product, "name", "") or "?", 300))

    def _render(self) -> None:
        # Limpia miniaturas
        while self.thumbs_layout.count():
            item = self.thumbs_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        if not self.photos:
            self._set_placeholder()
            self.counter_label.setText("Sin fotos")
            return
        self.counter_label.setText(f"{self.index + 1} / {len(self.photos)}")
        self._show_pixmap(self._current_filename())
        self._build_thumbs()

    def _build_thumbs(self) -> None:
        store = self._image_store()
        row = 0
        for i, filename in enumerate(self.photos):
            box = QVBoxLayout()
            box.setSpacing(2)
            label = QPushButton()
            label.setFixedSize(72, 72)
            label.setObjectName("thumbnail")
            label.setCheckable(True)
            label.setChecked(i == self.index)
            label.setStyleSheet(
                "QPushButton#thumbnail { border: 2px solid #2e3440; border-radius: 6px;"
                " padding: 2px; background: #1a1f28; }"
                "QPushButton#thumbnail:checked { border-color: #2fbf71; }")
            label.clicked.connect(lambda checked=False, idx=i: self._go_to(idx))
            if store is not None:
                store.get_pixmap_async(
                    filename,
                    lambda pixmap, btn=label: self._apply_thumb(btn, pixmap))
            box.addWidget(label)
            if self.index == i:
                marker = QLabel("Portada" if i == 0 else "Actual")
                marker.setObjectName("cartLabel")
                marker.setAlignment(Qt.AlignmentFlag.AlignCenter)
                box.addWidget(marker)
            self.thumbs_layout.addLayout(box, 0, row)
            row += 1

    def _apply_thumb(self, button, pixmap) -> None:
        if pixmap is None:
            return
        scaled = pixmap.scaled(
            68, 68,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        button.setIcon(QIcon(scaled))

    def _go_to(self, index: int) -> None:
        if 0 <= index < len(self.photos):
            self.index = index
            self._render()

    def _navigate(self, step: int) -> None:
        if not self.photos:
            return
        self.index = (self.index + step) % len(self.photos)
        self._render()

    def _add_photo(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar foto", "",
            "Imágenes (*.png *.jpg *.jpeg *.webp)")
        if not path:
            return
        store = self._image_store()
        if store is None:
            QMessageBox.warning(self, "Fotos", "No hay acceso al almacén de imágenes.")
            return
        try:
            filename = store.upload(path)
        except Exception as exc:
            QMessageBox.critical(self, "Fotos", f"No se pudo subir la foto:\n{exc}")
            return
        self._product_service().add_image(self.product.id, filename)
        self._reload_photos()
        self._go_to(len(self.photos) - 1)

    def _remove_photo(self) -> None:
        if not self.photos:
            return
        filename = self._current_filename()
        store = self._image_store()
        self._product_service().remove_image(self.product.id, filename)
        if store is not None:
            store.delete(filename)
        self._reload_photos()

    def _set_cover(self) -> None:
        if not self.photos:
            return
        filename = self._current_filename()
        self._product_service().set_cover(self.product.id, filename)
        self._reload_photos()


class ProductWidget(QWidget):
    data_changed = pyqtSignal()

    def __init__(self, services: dict, parent: QWidget | None = None):
        super().__init__(parent)
        self.services = services
        self._setup_ui()
        self._refresh_categories()
        self.refresh()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        toolbar = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Buscar producto…")
        self.search_input.textChanged.connect(lambda _: self.refresh())
        self.category_combo = NoWheelComboBox()
        self.category_combo.currentIndexChanged.connect(lambda _: self.refresh())

        new_button = QPushButton("Nuevo Producto")
        new_button.clicked.connect(self._new_product)
        edit_button = QPushButton("Editar")
        edit_button.clicked.connect(self._edit_product)
        delete_button = QPushButton("Eliminar")
        delete_button.setObjectName("dangerButton")
        delete_button.clicked.connect(self._delete_product)
        refresh_button = QPushButton("Refrescar")
        refresh_button.clicked.connect(self.refresh)

        toolbar.addWidget(self.search_input, 1)
        toolbar.addWidget(self.category_combo)
        toolbar.addWidget(new_button)
        toolbar.addWidget(edit_button)
        toolbar.addWidget(delete_button)
        toolbar.addWidget(refresh_button)
        layout.addLayout(toolbar)

        self.table = EmptyStateTable(
            "Aún no hay productos registrados.", 0, 9)
        self.table.setHorizontalHeaderLabels(
            ["Foto", "Código", "Tipo de Madera", "Nombre", "Categoría", "Precio Venta", "Costo Fab.", "IVA", "Estado"]
        )
        self.table.horizontalHeader().setObjectName("tableHeader")
        self.table.horizontalHeader().setStretchLastSection(False)
        ajustar_anchos_encabezado(
            self.table, [70, 90, 150, 190, 115, 115, 105, 55, 85])
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(56)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.doubleClicked.connect(self._open_gallery)
        layout.addWidget(self.table, 1)

    def _refresh_categories(self) -> None:
        current = self.category_combo.currentData()
        self.category_combo.blockSignals(True)
        self.category_combo.clear()
        self.category_combo.addItem("Todas", None)
        for category in self.services["category"].get_all(active_only=True) or []:
            self.category_combo.addItem(category.name, category.id)
        index = self.category_combo.findData(current)
        if index >= 0:
            self.category_combo.setCurrentIndex(index)
        self.category_combo.blockSignals(False)

    def refresh(self) -> None:
        query = self.search_input.text().strip()
        category_id = self.category_combo.currentData()
        service = self.services["product"]
        if query:
            products = service.search(query, category_id) or []
            self.table.set_empty_message(
                f"Sin productos que coincidan con “{query}”.")
        else:
            products = service.get_all(category_id=category_id, active_only=False) or []
            self.table.set_empty_message("Aún no hay productos registrados.")
        self.table.setRowCount(len(products))
        self._thumb_rows: dict[int, int] = {}
        for row, product in enumerate(products):
            self._thumb_rows[product.id] = row
            active = "Activo" if getattr(product, "active", True) else "Inactivo"
            values = [
                getattr(product, "code", "") or "",
                getattr(product, "wood_type", "") or "",
                getattr(product, "name", "") or "",
                getattr(product, "category_name", "") or "",
                format_currency(float(getattr(product, "sale_price", 0.0))),
                format_currency(float(getattr(product, "cost_price", 0.0))),
                f"{float(getattr(product, 'tax_rate', 0.0)):.0f}%",
                active,
            ]
            for column, value in enumerate(values):
                self.table.setItem(row, column + 1, QTableWidgetItem(str(value)))
            self.table.item(row, 3).setData(Qt.ItemDataRole.UserRole, product)
            self._set_thumb(row, product)

    def _set_thumb(self, row: int, product) -> None:
        label = QLabel()
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setFixedSize(76, 68)
        placeholder = ImageStore.placeholder_pixmap(product.name or "?", 56)
        label.setPixmap(placeholder)
        filename = getattr(product, "image_path", "") or ""
        store = self.services.get("images")
        if filename and store is not None:
            store.get_pixmap_async(
                filename,
                lambda pixmap, r=row, pid=product.id: self._apply_thumb(r, pid, pixmap))
        self.table.setCellWidget(row, 0, label)

    def _apply_thumb(self, row: int, product_id: int, pixmap) -> None:
        if self._thumb_rows.get(product_id) != row or row >= self.table.rowCount():
            return
        widget = self.table.cellWidget(row, 0)
        if widget is None or pixmap is None:
            return
        scaled = pixmap.scaled(
            72, 64,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        widget.setPixmap(scaled)

    def _selected_product(self):
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 3)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _new_product(self) -> None:
        dialog = ProductDialog(self.services, product=None, parent=self)
        if dialog.exec():
            self._refresh_categories()
            self.refresh()
            self.data_changed.emit()

    def _open_gallery(self) -> None:
        product = self._selected_product()
        if product is None:
            QMessageBox.information(self, "Selección", "Seleccione un producto.")
            return
        if not getattr(product, "id", 0):
            QMessageBox.information(self, "Galería",
                                    "Primero guarde el producto para añadirle fotos.")
            return
        dialog = ProductGalleryDialog(self.services, product, parent=self)
        dialog.exec()
        self.refresh()
        self.data_changed.emit()

    def _edit_product(self) -> None:
        product = self._selected_product()
        if product is None:
            QMessageBox.information(self, "Selección", "Seleccione un producto.")
            return
        dialog = ProductDialog(self.services, product=product, parent=self)
        if dialog.exec():
            self._refresh_categories()
            self.refresh()
            self.data_changed.emit()

    def _delete_product(self) -> None:
        product = self._selected_product()
        if product is None:
            QMessageBox.information(self, "Selección", "Seleccione un producto.")
            return
        answer = QMessageBox.question(
            self,
            "Eliminar producto",
            f"¿Eliminar el producto '{product.name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.services["product"].delete(product.id)
        self.refresh()
        self.data_changed.emit()
