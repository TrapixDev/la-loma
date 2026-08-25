"""Widget de CRUD de categorías de productos."""

from dataclasses import fields as dataclass_fields

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
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

from database.models import Category
from network.image_store import ImageStore


def _build_dataclass(cls, **kwargs):
    names = {f.name for f in dataclass_fields(cls)}
    return cls(**{key: value for key, value in kwargs.items() if key in names})


class CategoryDialog(QDialog):
    def __init__(self, services: dict, category=None, parent=None):
        super().__init__(parent)
        self.services = services
        self.category = category
        self._pending_image: str | None = None
        self._remove_image_flag = False
        self.setWindowTitle("Editar Categoría" if category else "Nueva Categoría")
        self.setMinimumWidth(420)
        self._setup_ui()
        if category:
            self._load_category(category)

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Nombre de la categoría")

        self.description_input = QLineEdit()
        self.description_input.setPlaceholderText("Descripción")

        layout.addWidget(QLabel("Nombre:"))
        layout.addWidget(self.name_input)
        layout.addWidget(QLabel("Descripción:"))
        layout.addWidget(self.description_input)

        layout.addWidget(QLabel("Foto de la categoría:"))
        self.image_preview = QLabel()
        self.image_preview.setFixedSize(100, 100)
        self.image_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_preview.setStyleSheet("border: 1px solid #2e3440; border-radius: 6px;")
        layout.addWidget(self.image_preview)

        image_buttons = QHBoxLayout()
        select_button = QPushButton("Seleccionar imagen…")
        select_button.clicked.connect(self._select_image)
        remove_button = QPushButton("Quitar imagen")
        remove_button.clicked.connect(self._remove_image)
        image_buttons.addWidget(select_button)
        image_buttons.addWidget(remove_button)
        layout.addLayout(image_buttons)

        buttons = QHBoxLayout()
        save_button = QPushButton("Guardar")
        save_button.setObjectName("primaryButton")
        save_button.clicked.connect(self._save)
        cancel_button = QPushButton("Cancelar")
        cancel_button.clicked.connect(self.reject)
        buttons.addWidget(save_button)
        buttons.addWidget(cancel_button)
        layout.addLayout(buttons)

    def _load_category(self, category) -> None:
        self.name_input.setText(category.name or "")
        self.description_input.setText(getattr(category, "description", "") or "")
        self._show_current_image()

    def _show_current_image(self) -> None:
        filename = getattr(self.category, "image_path", "") or "" if self.category else ""
        store = self.services.get("images")
        if not filename or store is None:
            self._set_placeholder()
            return
        self._set_placeholder()
        store.get_pixmap_async(filename, self._set_preview_pixmap)

    def _set_placeholder(self) -> None:
        name = self.name_input.text().strip() or "?"
        self.image_preview.setPixmap(ImageStore.placeholder_pixmap(name, 80))

    def _set_preview_pixmap(self, pixmap=None) -> None:
        if pixmap is None:
            self._set_placeholder()
            return
        scaled = pixmap.scaled(
            96, 96,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.image_preview.setPixmap(scaled)

    def _select_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar imagen de categoría", "",
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
        self._set_placeholder()

    def _save(self) -> None:
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Datos incompletos", "El nombre de la categoría es obligatorio.")
            return

        store = self.services.get("images")
        old_path = getattr(self.category, "image_path", "") or "" if self.category else ""
        image_path = old_path
        if self._pending_image:
            if store is None:
                image_path = ""
            else:
                try:
                    image_path = store.upload(self._pending_image)
                    if self.category and old_path:
                        store.delete(old_path)
                except Exception as exc:
                    QMessageBox.warning(
                        self, "Foto de categoría",
                        f"No se pudo subir la foto. La categoría se guardó sin ella:\n{exc}")
                    image_path = old_path
        elif self._remove_image_flag:
            if store is not None and old_path:
                store.delete(old_path)
            image_path = ""

        category = _build_dataclass(
            Category,
            id=self.category.id if self.category else 0,
            name=name,
            description=self.description_input.text().strip(),
            color=getattr(self.category, "color", "#3498db") or "#3498db",
            icon=getattr(self.category, "icon", "") or "",
            image_path=image_path,
            active=getattr(self.category, "active", True) if self.category else True,
            created_at=getattr(self.category, "created_at", None) if self.category else None,
            updated_at=None,
        )
        service = self.services["category"]
        if self.category:
            service.update(category)
        else:
            category.id = service.create(category)
        self.category = category
        self.accept()


class CategoryWidget(QWidget):
    data_changed = pyqtSignal()

    def __init__(self, services: dict, parent: QWidget | None = None):
        super().__init__(parent)
        self.services = services
        self._setup_ui()
        self.refresh()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        buttons = QHBoxLayout()
        new_button = QPushButton("Nueva Categoría")
        new_button.clicked.connect(self._new_category)
        edit_button = QPushButton("Editar")
        edit_button.clicked.connect(self._edit_category)
        self.toggle_button = QPushButton("Desactivar/Activar")
        self.toggle_button.clicked.connect(self._toggle_category)
        refresh_button = QPushButton("Refrescar")
        refresh_button.clicked.connect(self.refresh)
        buttons.addWidget(new_button)
        buttons.addWidget(edit_button)
        buttons.addWidget(self.toggle_button)
        buttons.addStretch(1)
        buttons.addWidget(refresh_button)
        layout.addLayout(buttons)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Foto", "Nombre", "Descripción", "Productos", "Estado"])
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.setColumnWidth(0, 70)
        self.table.setColumnWidth(1, 160)
        self.table.setColumnWidth(2, 230)
        self.table.setColumnWidth(3, 80)
        self.table.setColumnWidth(4, 80)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(80)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.doubleClicked.connect(self._edit_category)
        layout.addWidget(self.table, 1)

    def refresh(self) -> None:
        service = self.services["category"]
        categories = service.get_all(active_only=False) or []
        self.table.setRowCount(len(categories))
        self._thumb_rows: dict[int, int] = {}
        for row, category in enumerate(categories):
            self._thumb_rows[category.id] = row
            active = "Activo" if getattr(category, "active", True) else "Inactivo"
            self.table.setItem(row, 1, QTableWidgetItem(category.name or ""))
            self.table.setItem(row, 2, QTableWidgetItem(getattr(category, "description", "") or ""))
            try:
                count = service.get_product_count(category.id)
            except Exception:
                count = 0
            self.table.setItem(row, 3, QTableWidgetItem(str(count)))
            self.table.setItem(row, 4, QTableWidgetItem(active))
            self.table.item(row, 1).setData(Qt.ItemDataRole.UserRole, category)
            self._set_thumb(row, category)

    def _set_thumb(self, row: int, category) -> None:
        label = QLabel()
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setFixedSize(76, 76)
        placeholder = ImageStore.placeholder_pixmap(category.name or "?", 56)
        label.setPixmap(placeholder)
        filename = getattr(category, "image_path", "") or ""
        store = self.services.get("images")
        if filename and store is not None:
            store.get_pixmap_async(
                filename,
                lambda pixmap, r=row, cid=category.id: self._apply_thumb(r, cid, pixmap))
        self.table.setCellWidget(row, 0, label)

    def _apply_thumb(self, row: int, category_id: int, pixmap) -> None:
        if self._thumb_rows.get(category_id) != row or row >= self.table.rowCount():
            return
        widget = self.table.cellWidget(row, 0)
        if widget is None or pixmap is None:
            return
        scaled = pixmap.scaled(
            72, 72,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        widget.setPixmap(scaled)

    def _selected_category(self):
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 1)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _new_category(self) -> None:
        dialog = CategoryDialog(self.services, category=None, parent=self)
        if dialog.exec():
            self.refresh()
            self.data_changed.emit()

    def _edit_category(self) -> None:
        category = self._selected_category()
        if category is None:
            QMessageBox.information(self, "Selección", "Seleccione una categoría.")
            return
        dialog = CategoryDialog(self.services, category=category, parent=self)
        if dialog.exec():
            self.refresh()
            self.data_changed.emit()

    def _toggle_category(self) -> None:
        category = self._selected_category()
        if category is None:
            QMessageBox.information(self, "Selección", "Seleccione una categoría.")
            return
        category.active = not getattr(category, "active", True)
        self.services["category"].update(category)
        self.refresh()
        self.data_changed.emit()
