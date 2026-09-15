"""Widget y diálogo de clientes con consulta a Hacienda."""

from dataclasses import fields as dataclass_fields

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from database.models import Client
from utils.helpers import (
    ajustar_anchos_encabezado,
    EmptyStateTable,
    NoWheelComboBox,
)

ID_TYPES = [
    ("01", "01 - Cédula Física"),
    ("02", "02 - Cédula Jurídica"),
    ("03", "03 - DIMEX"),
    ("04", "04 - NITE"),
    ("05", "05 - Extranjero"),
    ("06", "06 - No contribuyente"),
]


def _build_dataclass(cls, **kwargs):
    names = {f.name for f in dataclass_fields(cls)}
    return cls(**{key: value for key, value in kwargs.items() if key in names})


class ClientDialog(QDialog):
    def __init__(self, services: dict, client=None, parent=None):
        super().__init__(parent)
        self.services = services
        self.client = client
        self.setWindowTitle("Editar Cliente" if client else "Nuevo Cliente")
        self.setMinimumWidth(420)
        self._setup_ui()
        if client:
            self._load_client(client)

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        self.id_type_combo = NoWheelComboBox()
        for value, label in ID_TYPES:
            self.id_type_combo.addItem(label, value)

        id_row = QHBoxLayout()
        self.id_number_input = QLineEdit()
        self.id_number_input.setPlaceholderText("Número de identificación")
        consult_button = QPushButton("Consultar Hacienda")
        consult_button.setObjectName("primaryButton")
        consult_button.clicked.connect(self._consult_hacienda)
        id_row.addWidget(self.id_number_input, 1)
        id_row.addWidget(consult_button)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Nombre completo")
        self.email_input = QLineEdit()
        self.email_input.setPlaceholderText("Correo electrónico")
        self.phone_input = QLineEdit()
        self.phone_input.setPlaceholderText("Teléfono")
        self.address_input = QLineEdit()
        self.address_input.setPlaceholderText("Dirección")

        layout.addWidget(QLabel("Tipo de identificación:"))
        layout.addWidget(self.id_type_combo)
        layout.addWidget(QLabel("Identificación:"))
        layout.addLayout(id_row)
        layout.addWidget(QLabel("Nombre:"))
        layout.addWidget(self.name_input)
        layout.addWidget(QLabel("Correo:"))
        layout.addWidget(self.email_input)
        layout.addWidget(QLabel("Teléfono:"))
        layout.addWidget(self.phone_input)
        layout.addWidget(QLabel("Dirección:"))
        layout.addWidget(self.address_input)

        buttons = QHBoxLayout()
        save_button = QPushButton("Guardar")
        save_button.setObjectName("primaryButton")
        save_button.clicked.connect(self._save)
        cancel_button = QPushButton("Cancelar")
        cancel_button.clicked.connect(self.reject)
        buttons.addWidget(save_button)
        buttons.addWidget(cancel_button)
        layout.addLayout(buttons)

    def _load_client(self, client) -> None:
        index = self.id_type_combo.findData(getattr(client, "id_type", "01"))
        if index >= 0:
            self.id_type_combo.setCurrentIndex(index)
        self.id_number_input.setText(getattr(client, "id_number", "") or "")
        self.name_input.setText(getattr(client, "name", "") or "")
        self.email_input.setText(getattr(client, "email", "") or "")
        self.phone_input.setText(getattr(client, "phone", "") or "")
        self.address_input.setText(getattr(client, "address", "") or "")

    def _consult_hacienda(self) -> None:
        id_number = self.id_number_input.text().strip()
        if not id_number:
            QMessageBox.warning(self, "Consulta Hacienda", "Ingrese el número de identificación.")
            return
        try:
            data = self.services["hacienda"].get_taxpayer_info(id_number)
        except Exception as exc:
            QMessageBox.warning(self, "Consulta Hacienda", f"No se pudo consultar Hacienda:\n{exc}")
            return
        if data:
            nombre = data.get("nombre") or data.get("razon_social") or data.get("name") or ""
            if nombre:
                self.name_input.setText(str(nombre))
            tipo = str(data.get("tipo_persona", "") or "").lower()
            if "jurid" in tipo:
                self.id_type_combo.setCurrentIndex(1)
            QMessageBox.information(self, "Consulta Hacienda", "Información obtenida correctamente.")
            return
        is_physical = len(id_number) == 9 and id_number.isdigit()
        if is_physical:
            self.id_type_combo.setCurrentIndex(5)
            if not self.name_input.text().strip():
                self.name_input.setText("Consumidor Final")
            QMessageBox.information(
                self,
                "Consumidor Final",
                "La identificación no corresponde a un contribuyente activo.\n"
                "Se tratará como Consumidor Final.",
            )
        else:
            QMessageBox.warning(self, "Consulta Hacienda", "No se encontró información para esa identificación.")

    def _save(self) -> None:
        id_number = self.id_number_input.text().strip()
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Datos incompletos", "El nombre del cliente es obligatorio.")
            return
        client = _build_dataclass(
            Client,
            id=self.client.id if self.client else 0,
            id_type=self.id_type_combo.currentData(),
            id_number=id_number,
            name=name,
            email=self.email_input.text().strip(),
            phone=self.phone_input.text().strip(),
            address=self.address_input.text().strip(),
            province="",
            canton="",
            district="",
            activity_code="",
        )
        service = self.services["client"]
        if self.client:
            service.update(client)
        else:
            client.id = service.create(client)
        self.client = client
        self.accept()


class ClientPickerDialog(QDialog):
    """Selector de clientes existentes en la base, con búsqueda y alta rápida."""

    def __init__(self, services: dict, parent=None):
        super().__init__(parent)
        self.services = services
        self.selected = None
        self.setWindowTitle("Seleccionar Cliente")
        self.setMinimumSize(640, 420)
        self._setup_ui()
        self.refresh()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        search_row = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Buscar por nombre o identificación…")
        self.search_input.textChanged.connect(lambda _: self.refresh())
        search_row.addWidget(self.search_input, 1)
        layout.addLayout(search_row)

        self.table = EmptyStateTable("No hay clientes registrados.", 0, 4)
        self.table.setHorizontalHeaderLabels(["Identificación", "Nombre", "Correo", "Teléfono"])
        self.table.horizontalHeader().setObjectName("tableHeader")
        self.table.horizontalHeader().setStretchLastSection(False)
        ajustar_anchos_encabezado(self.table, [145, 260, 160, 110])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.doubleClicked.connect(self._select)
        layout.addWidget(self.table, 1)

        buttons = QHBoxLayout()
        new_button = QPushButton("Nuevo Cliente")
        new_button.clicked.connect(self._new_client)
        select_button = QPushButton("Seleccionar")
        select_button.setObjectName("primaryButton")
        select_button.clicked.connect(self._select)
        cancel_button = QPushButton("Cancelar")
        cancel_button.clicked.connect(self.reject)
        buttons.addWidget(new_button)
        buttons.addStretch(1)
        buttons.addWidget(select_button)
        buttons.addWidget(cancel_button)
        layout.addLayout(buttons)

    def refresh(self) -> None:
        query = self.search_input.text().strip()
        service = self.services["client"]
        clients = service.search(query) if query else service.get_all()
        if query:
            self.table.set_empty_message(
                f"Sin clientes que coincidan con “{query}”.")
        else:
            self.table.set_empty_message("No hay clientes registrados.")
        self.table.setRowCount(len(clients))
        for row, client in enumerate(clients):
            values = [
                getattr(client, "id_number", "") or "",
                getattr(client, "name", "") or "",
                getattr(client, "email", "") or "",
                getattr(client, "phone", "") or "",
            ]
            for column, value in enumerate(values):
                self.table.setItem(row, column, QTableWidgetItem(str(value)))
            self.table.item(row, 1).setData(Qt.ItemDataRole.UserRole, client)

    def _selected_row_client(self):
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 1)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _select(self) -> None:
        client = self._selected_row_client()
        if client is None:
            QMessageBox.information(self, "Selección", "Seleccione un cliente de la lista.")
            return
        self.selected = client
        self.accept()

    def _new_client(self) -> None:
        dialog = ClientDialog(self.services, client=None, parent=self)
        if dialog.exec() and dialog.client is not None:
            self.selected = dialog.client
            self.accept()


class ClientWidget(QWidget):
    data_changed = pyqtSignal()

    def __init__(self, services: dict, parent: QWidget | None = None):
        super().__init__(parent)
        self.services = services
        self._setup_ui()
        self.refresh()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        toolbar = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Buscar cliente…")
        self.search_input.textChanged.connect(lambda _: self.refresh())
        new_button = QPushButton("Nuevo")
        new_button.clicked.connect(self._new_client)
        edit_button = QPushButton("Editar")
        edit_button.clicked.connect(self._edit_client)
        refresh_button = QPushButton("Refrescar")
        refresh_button.clicked.connect(self.refresh)

        toolbar.addWidget(self.search_input, 1)
        toolbar.addWidget(new_button)
        toolbar.addWidget(edit_button)
        toolbar.addWidget(refresh_button)
        layout.addLayout(toolbar)

        self.table = EmptyStateTable("No hay clientes registrados.", 0, 5)
        self.table.setHorizontalHeaderLabels(["Identificación", "Tipo", "Nombre", "Correo", "Teléfono"])
        self.table.horizontalHeader().setObjectName("tableHeader")
        self.table.horizontalHeader().setStretchLastSection(False)
        ajustar_anchos_encabezado(self.table, [145, 140, 240, 200, 130])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.doubleClicked.connect(self._edit_client)
        layout.addWidget(self.table, 1)

    def refresh(self) -> None:
        query = self.search_input.text().strip()
        service = self.services["client"]
        if query:
            clients = service.search(query) or []
            self.table.set_empty_message(
                f"Sin clientes que coincidan con “{query}”.")
        else:
            clients = service.get_all() or []
            self.table.set_empty_message("No hay clientes registrados.")
        self.table.setRowCount(len(clients))
        for row, client in enumerate(clients):
            values = [
                getattr(client, "id_number", "") or "",
                getattr(client, "id_type", "") or "",
                getattr(client, "name", "") or "",
                getattr(client, "email", "") or "",
                getattr(client, "phone", "") or "",
            ]
            for column, value in enumerate(values):
                self.table.setItem(row, column, QTableWidgetItem(str(value)))
            self.table.item(row, 2).setData(Qt.ItemDataRole.UserRole, client)

    def _selected_client(self):
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 2)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _new_client(self) -> None:
        dialog = ClientDialog(self.services, client=None, parent=self)
        if dialog.exec() and dialog.client is not None:
            self.refresh()
            self.data_changed.emit()

    def _edit_client(self) -> None:
        client = self._selected_client()
        if client is None:
            QMessageBox.information(self, "Selección", "Seleccione un cliente.")
            return
        dialog = ClientDialog(self.services, client=client, parent=self)
        if dialog.exec() and dialog.client is not None:
            self.refresh()
            self.data_changed.emit()
