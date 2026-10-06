"""Configuración por pestañas: estructura y widgets clave."""

import os
import sys
from pathlib import Path

PROJECT_DIR = str(Path(__file__).resolve().parents[1])
sys.path.insert(0, PROJECT_DIR)
os.chdir(PROJECT_DIR)
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt6.QtWidgets import QApplication, QPushButton, QTabWidget

from database.db_manager import DatabaseManager
from main import build_services
from modules.settings.settings_widget import SettingsWidget

TEST_DB = os.path.join(PROJECT_DIR, "tests", ".tmp", "test_settings_tabs.db")

app = QApplication.instance() or QApplication([])

_last_db: DatabaseManager | None = None


def cleanup():
    global _last_db
    if _last_db is not None:
        _last_db.close()
        _last_db = None
    for _ in range(5):
        try:
            if os.path.exists(TEST_DB):
                os.remove(TEST_DB)
            for ext in ("-wal", "-shm"):
                p = TEST_DB + ext
                if os.path.exists(p):
                    os.remove(p)
            break
        except PermissionError:
            import time
            time.sleep(0.1)


def setup_function():
    cleanup()


def teardown_function():
    cleanup()


def test_configuracion_por_pestanas():
    global _last_db
    db = DatabaseManager(TEST_DB)
    db.initialize()
    _last_db = db
    widget = SettingsWidget(build_services(db))

    tabs = widget.findChild(QTabWidget, "settingsTabs")
    assert tabs is not None, "falta el QTabWidget de configuración"
    titulos = [tabs.tabText(i) for i in range(tabs.count())]
    assert titulos == ["Empresa", "Promociones", "Hacienda",
                       "Impresora y docs", "Apariencia", "Sistema"], titulos

    for atributo in ("company_name_input", "promotions_table",
                     "environment_combo", "printer_combo",
                     "docs_path_label", "version_label"):
        assert hasattr(widget, atributo), atributo

    botones = [boton.text() for boton in widget.findChildren(QPushButton)]
    assert "Formato del ticket…" in botones

    # Cada página tiene contenido y se puede cambiar de pestaña.
    for i in range(tabs.count()):
        tabs.setCurrentIndex(i)
        app.processEvents()
        assert tabs.currentWidget() is not None


def test_formato_del_ticket_en_ventana_emergente():
    global _last_db
    db = DatabaseManager(TEST_DB)
    db.initialize()
    _last_db = db
    widget = SettingsWidget(build_services(db))

    widget.company_name_input.setText("Mueblería de prueba")
    dialog = widget._crear_ticket_format_dialog()

    assert "Mueblería de prueba" in dialog.ticket_preview_html
    assert dialog.ticket_preview_label.pixmap() is not None

    dialog.ticket_format_checks["show_company_name"].setChecked(False)
    app.processEvents()
    assert "Mueblería de prueba" not in dialog.ticket_preview_html

    dialog.ticket_format_checks["show_email"].setChecked(False)
    dialog.ticket_thank_you_input.setText("Gracias por su compra")
    assert dialog._persist_ticket_editor()
    from modules.documentos.ticket import get_ticket_format

    guardado = get_ticket_format(db)
    assert guardado["show_email"] is False
    assert guardado["thank_you_text"] == "Gracias por su compra"

    dialog._reset_ticket_format()
    assert dialog.ticket_format_checks["show_email"].isChecked()
    dialog.deleteLater()


def test_campos_no_cambian_con_la_rueda_del_mouse():
    """La rueda no debe cambiar valores de combos ni campos numéricos."""
    from PyQt6.QtCore import QPoint, QPointF, Qt
    from PyQt6.QtGui import QWheelEvent

    from utils.helpers import NoWheelComboBox, NoWheelIntSpinBox, NoWheelSpinBox

    global _last_db
    db = DatabaseManager(TEST_DB)
    db.initialize()
    _last_db = db
    widget = SettingsWidget(build_services(db))
    dialog = widget._crear_ticket_format_dialog()

    assert isinstance(dialog.ticket_font_spin, NoWheelSpinBox)
    assert isinstance(dialog.ticket_logo_width_spin, NoWheelIntSpinBox)
    assert isinstance(dialog.ticket_scale_combo, NoWheelComboBox)

    evento = QWheelEvent(
        QPointF(5, 5), QPointF(5, 5), QPoint(0, 0), QPoint(0, -120),
        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase, False)
    antes = dialog.ticket_font_spin.value()
    dialog.ticket_font_spin.wheelEvent(evento)
    assert dialog.ticket_font_spin.value() == antes
    dialog.deleteLater()


def test_campos_numericos_vacios_en_cero():
    """Los campos numéricos en 0 se muestran vacíos (evita guardar 0 por error)."""
    from utils.helpers import NoWheelIntSpinBox, NoWheelSpinBox

    spin = NoWheelSpinBox()
    spin.setRange(0.0, 100.0)
    assert spin.value() == 0.0
    assert spin.text().strip() == ""
    spin.setValue(25.5)
    assert spin.text().strip() == "25.50"
    spin.setValue(0.0)
    assert spin.text().strip() == ""

    entero = NoWheelIntSpinBox()
    entero.setRange(0, 10)
    assert entero.text().strip() == ""
    entero.setValue(3)
    assert entero.text().strip() == "3"
