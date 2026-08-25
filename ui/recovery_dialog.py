"""Diálogo de recuperación de red: espera a que el servidor vuelva."""

from threading import Thread

from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

CHECK_INTERVAL_MS = 2_000


class RecoveryWorker(QObject):
    finished = pyqtSignal(bool)

    def run(self, db) -> None:
        try:
            ok = bool(db.check_connection(timeout=3.0))
        except Exception:
            ok = False
        self.finished.emit(ok)


class ConnectionRecoveryDialog(QDialog):
    """Espera a que el servidor responda y deja reintentar la operación.

    Mientras la red está caída muestra el estado en vivo y permite cancelar;
    cuando la conexión vuelve, habilita "Reintentar".
    """

    def __init__(self, db, message: str = "", parent=None):
        super().__init__(parent)
        self.db = db
        self.connected = False
        self.setWindowTitle("Recuperación de conexión")
        self.setModal(True)
        self.setMinimumWidth(460)
        self._workers: list[QObject] = []
        self._threads: list[Thread] = []
        self._build_ui(message)
        self._start_monitor()

    def _build_ui(self, message: str) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(12)

        title = QLabel("No hay conexión con el servidor del POS.")
        title.setObjectName("recoveryTitle")
        root.addWidget(title)

        if message:
            detail = QLabel(message)
            detail.setWordWrap(True)
            detail.setObjectName("recoveryDetail")
            root.addWidget(detail)

        self.status_label = QLabel("Verificando conexión…")
        self.status_label.setObjectName("recoveryStatus")
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.retry_button = QPushButton("Reintentar")
        self.retry_button.setObjectName("recoveryRetry")
        self.retry_button.setEnabled(False)
        self.retry_button.clicked.connect(self.accept)
        buttons.addWidget(self.retry_button)
        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.setObjectName("recoveryCancel")
        self.cancel_button.clicked.connect(self.reject)
        buttons.addWidget(self.cancel_button)
        root.addLayout(buttons)

    def _set_status(self, text: str, color: str) -> None:
        self.status_label.setText(text)
        self.status_label.setStyleSheet(f"color: {color}; font-weight: bold;")

    def _start_monitor(self) -> None:
        self._set_status("Verificando conexión…", "#f59e0b")
        timer = QTimer(self)
        timer.timeout.connect(self._check)
        timer.start(CHECK_INTERVAL_MS)
        self._check()

    def _check(self) -> None:
        if self.connected:
            return
        worker = RecoveryWorker()
        self._workers.append(worker)
        worker.finished.connect(self._on_result)
        thread = Thread(target=worker.run, args=(self.db,), daemon=True)
        self._threads.append(thread)
        thread.start()

    def _on_result(self, ok: bool) -> None:
        if ok and not self.connected:
            self.connected = True
            self._set_status("Conexión restablecida. Puede reintentar la operación.", "#2fbf71")
            self.retry_button.setEnabled(True)
            self.retry_button.setFocus()
        elif not ok:
            self._set_status("Sin conexión. Reintentando automáticamente…", "#ef4444")

    def reject(self) -> None:
        super().reject()
