"""Ventana principal del POS La Loma."""

from threading import Thread

from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from config import Config
from modules.categories.category_widget import CategoryWidget
from modules.clients.client_widget import ClientWidget
from modules.pos.pos_widget import POSWidget
from modules.products.product_widget import ProductWidget
from modules.reports.reports_widget import ReportsWidget
from modules.settings.settings_widget import SettingsWidget
from network.session import session

from ui.login_dialog import LoginDialog

NAV_ITEMS = [
    ("Punto de Venta", "pos"),
    ("Categorías", "categories"),
    ("Productos", "products"),
    ("Clientes", "clients"),
    ("Reportes", "reports"),
    ("Configuración", "settings"),
]

CHECK_INTERVAL_MS = 60_000


class ConnectionWorker(QObject):
    finished = pyqtSignal(bool)

    def run(self, service) -> None:
        try:
            ok = bool(service.check_connection())
        except Exception:
            ok = False
        self.finished.emit(ok)


class MainWindow(QMainWindow):
    def __init__(self, services: dict, parent: QWidget | None = None):
        super().__init__(parent)
        self.services = services
        self._jobs: list[dict] = []
        self.setWindowTitle("POS - La Loma")
        self.setMinimumSize(1100, 700)
        self._setup_ui()
        self._wire_signals()
        self._start_connection_checker()

    def _setup_ui(self) -> None:
        central = QWidget()
        central.setObjectName("centralContainer")
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QWidget()
        header.setObjectName("headerBar")
        header.setFixedHeight(52)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 8, 0)
        header_layout.setSpacing(0)

        title = QLabel("POS - La Loma")
        title.setObjectName("appTitle")
        header_layout.addWidget(title)
        header_layout.addSpacing(16)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav_buttons: dict[str, QPushButton] = {}
        self.pages = QStackedWidget()
        for label, key in NAV_ITEMS:
            button = QPushButton(label)
            button.setObjectName("navButton")
            button.setCheckable(True)
            self.nav_group.addButton(button)
            self.nav_buttons[key] = button
            header_layout.addWidget(button)

        header_layout.addStretch(1)

        self.logout_button = QPushButton("Salir")
        self.logout_button.setObjectName("logoutButton")
        self.logout_button.setFixedHeight(34)
        self.logout_button.clicked.connect(self._logout)
        header_layout.addWidget(self.logout_button)

        root.addWidget(header)
        root.addWidget(self.pages, 1)
        self.setCentralWidget(central)

        self.pos_widget = POSWidget(self.services)
        self.category_widget = CategoryWidget(self.services)
        self.product_widget = ProductWidget(self.services)
        self.client_widget = ClientWidget(self.services)
        self.reports_widget = ReportsWidget(self.services)
        self.settings_widget = SettingsWidget(self.services)
        self.page_keys = [key for _, key in NAV_ITEMS]
        for widget in (
            self.pos_widget,
            self.category_widget,
            self.product_widget,
            self.client_widget,
            self.reports_widget,
            self.settings_widget,
        ):
            self.pages.addWidget(widget)

        for key, button in self.nav_buttons.items():
            button.clicked.connect(lambda checked=False, k=key: self._set_page(k))
        self.nav_buttons["pos"].setChecked(True)

        station = getattr(Config, "STATION", "CAJA-1")
        self.statusBar().showMessage(f"Estación: {station}")

        self.user_label = QLabel()
        self.statusBar().addPermanentWidget(self.user_label)

        self.connection_label = QLabel()
        self.statusBar().addPermanentWidget(self.connection_label)
        self._set_connection_indicator(None)
        self._update_user_label()

        self.server_connection_label = QLabel()
        self.statusBar().addPermanentWidget(self.server_connection_label)
        self._set_server_indicator(True)
        if Config.MODE == "server":
            self._start_server_checker()

    def _wire_signals(self) -> None:
        self.pos_widget.sale_completed.connect(self._on_sale_completed)
        self.category_widget.data_changed.connect(self.pos_widget.refresh_categories)
        self.category_widget.data_changed.connect(self.product_widget.refresh)
        self.product_widget.data_changed.connect(self.pos_widget.refresh_products)
        self.product_widget.data_changed.connect(self.category_widget.refresh)

    def _set_page(self, key: str) -> None:
        try:
            index = self.page_keys.index(key)
        except ValueError:
            return
        self.pages.setCurrentIndex(index)
        if key == "reports":
            self.reports_widget.refresh()
        if key == "settings":
            self.settings_widget._load_config()

    def _on_sale_completed(self, data: dict) -> None:
        self.product_widget.refresh()
        self.category_widget.refresh()
        self.reports_widget.refresh()

    def _start_connection_checker(self) -> None:
        self._check_hacienda()
        timer = QTimer(self)
        timer.timeout.connect(self._check_hacienda)
        timer.start(CHECK_INTERVAL_MS)

    def _spawn_check(self, service, handler) -> None:
        worker = ConnectionWorker()
        entry = {"worker": worker, "thread": None}
        worker.finished.connect(handler)
        worker.finished.connect(
            lambda *_, e=entry: self._jobs.remove(e) if e in self._jobs else None)
        thread = Thread(target=worker.run, args=(service,), daemon=True)
        entry["thread"] = thread
        self._jobs.append(entry)
        thread.start()

    def _check_hacienda(self) -> None:
        self._set_connection_indicator(None)
        self._spawn_check(self.services["hacienda"], self._on_connection_result)

    def _on_connection_result(self, ok: bool) -> None:
        self._set_connection_indicator(ok)

    def _start_server_checker(self) -> None:
        self._check_server()
        timer = QTimer(self)
        timer.timeout.connect(self._check_server)
        timer.start(5_000)

    def _check_server(self) -> None:
        self._spawn_check(self.services["db"], self._on_server_connection_result)

    def _on_server_connection_result(self, ok: bool) -> None:
        self._set_server_indicator(ok)

    def _set_server_indicator(self, ok: bool | None) -> None:
        if ok is None:
            text = "● Servidor: verificando…"
            color = "#f59e0b"
        elif ok:
            text = "● Servidor en línea"
            color = "#2fbf71"
        else:
            text = "● Servidor sin conexión"
            color = "#ef4444"
        self.server_connection_label.setText(text)
        self.server_connection_label.setStyleSheet(
            f"color: {color}; font-weight: bold; padding: 0 8px;")

    def _update_user_label(self) -> None:
        if session.user_name:
            self.user_label.setText(f"Usuario: {session.user_name}")
        else:
            self.user_label.setText("Usuario: sin sesión")
        self.user_label.setStyleSheet("color: #b9c2cf; padding: 0 8px;")

    def _logout(self) -> None:
        if session.token:
            try:
                self.services["db"].logout()
            except Exception:
                pass
        dialog = LoginDialog(self.services["db"], station=getattr(Config, "STATION", "CAJA1"), parent=self)
        if dialog.exec() == dialog.DialogCode.Accepted:
            self._update_user_label()
        else:
            self.close()

    def _set_connection_indicator(self, ok: bool | None) -> None:
        if ok is None:
            text = "● Verificando Hacienda…"
            color = "#f59e0b"
        elif ok:
            text = "● Hacienda en línea"
            color = "#2fbf71"
        else:
            text = "● Hacienda sin conexión"
            color = "#ef4444"
        self.connection_label.setText(text)
        self.connection_label.setStyleSheet(f"color: {color}; font-weight: bold; padding: 0 8px;")

    def closeEvent(self, event) -> None:
        db = self.services.get("db")
        if db is not None and hasattr(db, "close"):
            try:
                db.close()
            except Exception:
                pass
        event.accept()
