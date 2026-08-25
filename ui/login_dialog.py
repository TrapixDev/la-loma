"""Diálogo de ingreso del POS: teclado PIN táctil y primer arranque."""

from contextlib import contextmanager

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from network.session import session
from security import auth

PIN_MIN = auth.PIN_MIN
PIN_MAX = auth.PIN_MAX
MAX_FAILED = 5


class LocalAuth:
    """Autenticación contra la base de datos local (modo sin servidor).

    Implementa además la interfaz de DatabaseManager para poder usarse como
    proveedor de datos y de ingreso al mismo tiempo.
    """

    def __init__(self, db) -> None:
        self.db = db

    # ---------- interfaz DatabaseManager ----------

    def initialize(self) -> None:
        self.db.initialize()

    def close(self) -> None:
        self.db.close()

    def count_users(self) -> int:
        return self.db.count_users()

    def audit(self, *args, **kwargs) -> None:
        self.db.audit(*args, **kwargs)

    def execute_query(self, sql: str, params: tuple = ()) -> list[dict]:
        return self.db.execute_query(sql, params)

    def execute_insert(self, sql: str, params: tuple = ()) -> int:
        return self.db.execute_insert(sql, params)

    def execute_update(self, sql: str, params: tuple = ()) -> bool:
        return self.db.execute_update(sql, params)

    @contextmanager
    def transaction(self):
        with self.db.transaction() as connection:
            yield connection

    # ---------- autenticación ----------

    def needs_setup(self) -> bool:
        return self.db.count_users() == 0

    def login(self, pin: str) -> dict:
        users = self.db.execute_query("SELECT * FROM users WHERE active = 1")
        user = None
        for candidate in users:
            if auth.verify_pin(pin, candidate["pin_salt"], candidate["pin_hash"]):
                user = candidate
                break
        if user is None:
            return {"error": "PIN incorrecto"}
        if user["locked_until"] and auth.remaining_minutes(user["locked_until"]) > 0:
            return {"error": f"Usuario bloqueado. Intente en "
                             f"{auth.remaining_minutes(user['locked_until'])} min."}
        self.db.execute_update(
            "UPDATE users SET failed_attempts = 0, locked_until = NULL, "
            "last_login_at = datetime('now', 'localtime') WHERE id = ?",
            (user["id"],),
        )
        session.set("local", user["id"], user["name"])
        return {"user_id": user["id"], "user_name": user["name"]}

    def register_failure(self, pin: str) -> str:
        users = self.db.execute_query("SELECT * FROM users WHERE active = 1")
        for candidate in users:
            if auth.verify_pin(pin, candidate["pin_salt"], candidate["pin_hash"]):
                failed = int(candidate["failed_attempts"] or 0) + 1
                if failed >= MAX_FAILED:
                    deadline = auth.lockout_deadline(MAX_FAILED, 15)
                    self.db.execute_update(
                        "UPDATE users SET failed_attempts = ?, locked_until = ? WHERE id = ?",
                        (failed, deadline.isoformat(), candidate["id"]),
                    )
                    return f"Demasiados intentos. Bloqueado 15 minutos."
                self.db.execute_update(
                    "UPDATE users SET failed_attempts = ? WHERE id = ?",
                    (failed, candidate["id"]),
                )
                return f"PIN incorrecto. Intento {failed} de {MAX_FAILED}."
        return "PIN incorrecto"

    def setup(self, name: str, pin: str) -> dict:
        salt, digest = auth.hash_pin(pin)
        user_id = self.db.execute_insert(
            "INSERT INTO users (name, pin_salt, pin_hash) VALUES (?, ?, ?)",
            (name, salt, digest),
        )
        session.set("local", user_id, name)
        return {"user_id": user_id, "user_name": name}

    def logout(self) -> None:
        session.clear()


class LoginDialog(QDialog):
    """Ingreso con PIN; en primer arranque permite crear el PIN inicial."""

    def __init__(self, db, station: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self.db = db
        self.station = station
        self.setup_mode = False
        self.setup_phase = 0
        self.first_pin = ""
        self.setWindowTitle("Ingreso - POS La Loma")
        self.setObjectName("loginDialog")
        self.setModal(True)
        self.setFixedSize(420, 620)
        self._build_ui()
        self._prepare_mode()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 28, 24, 24)
        root.setSpacing(12)

        self.title_label = QLabel("POS - La Loma")
        self.title_label.setObjectName("loginTitle")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.title_label)

        self.subtitle_label = QLabel("Ingrese su PIN para continuar")
        self.subtitle_label.setObjectName("loginSubtitle")
        self.subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.subtitle_label)

        self.error_label = QLabel("")
        self.error_label.setObjectName("loginError")
        self.error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.error_label.setWordWrap(True)
        root.addWidget(self.error_label)

        self.name_input = QLineEdit()
        self.name_input.setObjectName("loginName")
        self.name_input.setPlaceholderText("Nombre del usuario")
        self.name_input.setMaxLength(60)
        root.addWidget(self.name_input)

        self.pin_display = QLineEdit()
        self.pin_display.setObjectName("pinDisplay")
        self.pin_display.setEchoMode(QLineEdit.EchoMode.Password)
        self.pin_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pin_display.setReadOnly(True)
        self.pin_display.setMaxLength(PIN_MAX)
        root.addWidget(self.pin_display)

        pad = QGridLayout()
        pad.setSpacing(8)
        keys = ["1", "2", "3", "4", "5", "6", "7", "8", "9"]
        for index, key in enumerate(keys):
            button = QPushButton(key)
            button.setObjectName("pinKey")
            button.setFixedHeight(58)
            button.clicked.connect(lambda checked=False, k=key: self._press(k))
            pad.addWidget(button, index // 3, index % 3)
        self.back_button = QPushButton("⌫")
        self.back_button.setObjectName("pinKey")
        self.back_button.setFixedHeight(58)
        self.back_button.clicked.connect(lambda: self._press("back"))
        pad.addWidget(self.back_button, 3, 0)
        zero = QPushButton("0")
        zero.setObjectName("pinKey")
        zero.setFixedHeight(58)
        zero.clicked.connect(lambda: self._press("0"))
        pad.addWidget(zero, 3, 1)
        self.ok_button = QPushButton("OK")
        self.ok_button.setObjectName("pinOk")
        self.ok_button.setFixedHeight(58)
        self.ok_button.clicked.connect(self._submit)
        pad.addWidget(self.ok_button, 3, 2)
        root.addLayout(pad)
        root.addStretch(1)

    def _prepare_mode(self) -> None:
        self.setup_mode = bool(self.db.needs_setup())
        self.name_input.setVisible(self.setup_mode)
        if self.setup_mode:
            self.subtitle_label.setText("Primer arranque: cree el PIN del administrador")
            self.error_label.setText("El PIN debe tener entre 4 y 6 dígitos.")
            self.error_label.setProperty("hint", True)
        self._update_style()

    def _update_style(self) -> None:
        self.error_label.setProperty("hint", False)
        self.error_label.style().unpolish(self.error_label)
        self.error_label.style().polish(self.error_label)

    def _press(self, key: str) -> None:
        if key == "back":
            self.pin_display.setText(self.pin_display.text()[:-1])
            return
        if len(self.pin_display.text()) < PIN_MAX:
            self.pin_display.setText(self.pin_display.text() + key)

    def _show_error(self, message: str) -> None:
        self.error_label.setText(message)
        self.error_label.setProperty("hint", False)
        self.error_label.style().unpolish(self.error_label)
        self.error_label.style().polish(self.error_label)

    def _clear_pin(self) -> None:
        self.pin_display.clear()
        self.ok_button.setEnabled(True)

    def _submit(self) -> None:
        pin = self.pin_display.text()
        if not auth.valid_pin(pin):
            self._show_error(f"El PIN debe tener entre {PIN_MIN} y {PIN_MAX} dígitos.")
            self._clear_pin()
            return

        if self.setup_mode:
            self._handle_setup(pin)
            return

        try:
            result = self.db.login(pin)
        except Exception as exc:
            self._show_error(str(exc))
            self._clear_pin()
            return
        if "error" in result:
            message = result["error"]
            if "incorrecto" in message.lower() and hasattr(self.db, "register_failure"):
                message = self.db.register_failure(pin)
            self._show_error(message)
            self._clear_pin()
            return
        self.accept()

    def _handle_setup(self, pin: str) -> None:
        name = self.name_input.text().strip()
        if not name:
            self._show_error("Escriba un nombre para el usuario.")
            return
        if self.setup_phase == 0:
            self.first_pin = pin
            self.setup_phase = 1
            self.subtitle_label.setText("Repita el PIN para confirmar")
            self.error_label.setText("")
            self._clear_pin()
            return
        if pin != self.first_pin:
            self.setup_phase = 0
            self.first_pin = ""
            self._show_error("Los PIN no coinciden. Intente de nuevo.")
            self._clear_pin()
            return
        try:
            self.db.setup(name, pin)
        except Exception as exc:
            self._show_error(str(exc))
            return
        self.accept()

    def keyPressEvent(self, event) -> None:
        key = event.key()
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._submit()
        elif key == Qt.Key.Key_Backspace:
            self._press("back")
        elif Qt.Key.Key_0 <= key <= Qt.Key.Key_9:
            self._press(chr(key))
        elif key == Qt.Key.Key_Escape:
            self.reject()
        else:
            super().keyPressEvent(event)
