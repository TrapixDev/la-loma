"""Configuración por pestañas: estructura y widgets clave."""

import os
import sys
from pathlib import Path

PROJECT_DIR = str(Path(__file__).resolve().parents[1])
sys.path.insert(0, PROJECT_DIR)
os.chdir(PROJECT_DIR)
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt6.QtWidgets import QApplication, QTabWidget

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
                       "Impresora y docs", "Sistema"], titulos

    for atributo in ("company_name_input", "promotions_table",
                     "environment_combo", "printer_combo",
                     "docs_path_label", "version_label"):
        assert hasattr(widget, atributo), atributo

    # Cada página tiene contenido y se puede cambiar de pestaña.
    for i in range(tabs.count()):
        tabs.setCurrentIndex(i)
        app.processEvents()
        assert tabs.currentWidget() is not None
