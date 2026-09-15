"""Diálogos de error y diagnóstico con opción de copiar el reporte.

En pruebas se puede desactivar cualquier diálogo con POS_NO_ERROR_DIALOG=1.
"""

import os

from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

_SIMBOLOS = {"ok": "✓", "aviso": "⚠", "error": "✗"}
_COLORES = {"ok": "#2fbf71", "aviso": "#f59e0b", "error": "#ef4444"}


def dialogos_habilitados() -> bool:
    return not os.environ.get("POS_NO_ERROR_DIALOG")


def copiar_texto(texto: str) -> None:
    portapapeles = QApplication.clipboard()
    if portapapeles is not None:
        portapapeles.setText(texto)


def mostrar_error(parent, titulo: str, mensaje: str, detalle: str = "") -> None:
    """Aviso no fatal: muestra el error y permite copiar el diagnóstico."""
    if not dialogos_habilitados():
        return
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle(titulo)
    box.setText(mensaje)
    if detalle:
        box.setDetailedText(detalle)
    copiar = box.addButton("Copiar diagnóstico", QMessageBox.ButtonRole.ActionRole)
    box.addButton("Cerrar", QMessageBox.ButtonRole.AcceptRole)
    box.exec()
    if box.clickedButton() is copiar:
        copiar_texto(detalle or mensaje)


def mostrar_diagnostico(parent, checks: list[dict]) -> None:
    """Ventana con los chequeos de instalación y botón para copiar el reporte."""
    if not dialogos_habilitados():
        return
    from utils.diagnostico import texto_reporte

    dialog = QDialog(parent)
    dialog.setWindowTitle("Diagnóstico de instalación")
    dialog.setMinimumSize(540, 380)
    layout = QVBoxLayout(dialog)
    layout.setSpacing(10)

    titulo = QLabel("Diagnóstico de instalación")
    titulo.setObjectName("sectionTitle")
    layout.addWidget(titulo)

    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    contenedor = QWidget()
    interno = QVBoxLayout(contenedor)
    for check in checks:
        nivel = check.get("nivel", "ok")
        label = QLabel(
            f"{_SIMBOLOS.get(nivel, '?')} <b>{check.get('titulo', '')}</b>: "
            f"{check.get('detalle', '')}")
        label.setWordWrap(True)
        label.setStyleSheet(f"color: {_COLORES.get(nivel, '#d3dae5')};")
        interno.addWidget(label)
    interno.addStretch(1)
    scroll.setWidget(contenedor)
    layout.addWidget(scroll, 1)

    botones = QHBoxLayout()
    copiar = QPushButton("Copiar reporte")
    copiar.setObjectName("primaryButton")
    copiar.clicked.connect(lambda: copiar_texto(texto_reporte(checks)))
    cerrar = QPushButton("Cerrar")
    cerrar.clicked.connect(dialog.accept)
    botones.addWidget(copiar)
    botones.addStretch(1)
    botones.addWidget(cerrar)
    layout.addLayout(botones)

    dialog.exec()
