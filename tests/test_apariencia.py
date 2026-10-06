"""Apariencia: tokens QSS, persistencia compartida y editor guiado."""

import os
import sys
from pathlib import Path

PROJECT_DIR = str(Path(__file__).resolve().parents[1])
sys.path.insert(0, PROJECT_DIR)
os.chdir(PROJECT_DIR)
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt6.QtWidgets import QApplication, QTabWidget, QPushButton

from database.db_manager import DatabaseManager
from main import build_services
from modules.settings.settings_widget import SettingsWidget
from ui import theme

TEST_DB = os.path.join(PROJECT_DIR, "tests", ".tmp", "test_apariencia.db")

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


def test_render_de_tokens_no_deja_pendientes():
    oscuro = theme.build_stylesheet({"theme": "dark"})
    claro = theme.build_stylesheet(
        {"theme": "light", "accent": "#8b5cf6", "font_scale": 1.2,
         "density": "amplia"})
    assert "@" not in oscuro, "quedaron tokens sin resolver (oscuro)"
    assert "@" not in claro, "quedaron tokens sin resolver (claro)"
    assert theme.build_palette({"theme": "dark"})["accent"] == "#2fbf71"
    assert theme.build_palette({"accent": "#8b5cf6"})["accent"] == "#8b5cf6"


def test_normalizacion_de_valores_invalidos():
    raro = theme.normalize_appearance(
        {"theme": "noexiste", "accent": "azul", "font_scale": 99,
         "density": "gigante"})
    assert raro["theme"] == "dark"
    assert raro["accent"] == theme.DEFAULT_APPEARANCE["accent"]
    assert raro["font_scale"] == 1.35  # se limita al máximo, no falla
    assert raro["density"] == "normal"
    assert theme.normalize_appearance({"font_scale": 1.2})["font_scale"] == 1.2


def test_guardar_y_cargar_compartida():
    global _last_db
    db = DatabaseManager(TEST_DB)
    db.initialize()
    _last_db = db

    theme.save_appearance(db, {"theme": "light", "accent": "#f59e0b",
                               "font_scale": 1.15, "density": "compacta"})
    cargada = theme.load_appearance(db)
    assert cargada["theme"] == "light"
    assert cargada["accent"] == "#f59e0b"
    assert cargada["font_scale"] == 1.15
    assert cargada["density"] == "compacta"


def test_pestana_apariencia_aplica_y_guarda():
    global _last_db
    db = DatabaseManager(TEST_DB)
    db.initialize()
    _last_db = db
    widget = SettingsWidget(build_services(db))

    tabs = widget.findChild(QTabWidget, "settingsTabs")
    titulos = [tabs.tabText(i) for i in range(tabs.count())]
    assert "Apariencia" in titulos, titulos
    assert "Sistema" in titulos, titulos

    # Valor por defecto.
    assert theme.current_appearance()["theme"] == "dark"

    # Cambiar el tema aplica la vista previa global.
    indice_claro = widget.appearance_theme_combo.findData("light")
    widget.appearance_theme_combo.setCurrentIndex(indice_claro)
    app.processEvents()
    assert theme.current_appearance()["theme"] == "light"

    # Elegir acento de la paleta guiada.
    widget._pick_accent("#3b82f6")
    app.processEvents()
    assert theme.current_appearance()["accent"] == "#3b82f6"

    # Guardar en app_config y volver a leer.
    widget._save_appearance()
    guardada = theme.load_appearance(db)
    assert guardada["theme"] == "light"
    assert guardada["accent"] == "#3b82f6"

    # Restablecer deja los controles en valores de fábrica.
    widget._apply_appearance_controls(dict(theme.DEFAULT_APPEARANCE))
    assert widget._appearance_values() == theme.DEFAULT_APPEARANCE

    # La pestaña se puede cambiar sin errores.
    tabs.setCurrentWidget(widget.findChild(QTabWidget, "settingsTabs")
                          .widget(titulos.index("Apariencia")))
    app.processEvents()

    assert any(isinstance(b, QPushButton) and "apariencia" in b.text().lower()
               for b in widget.findChildren(QPushButton))


def test_sistema_muestra_estado_de_estacion():
    global _last_db
    db = DatabaseManager(TEST_DB)
    db.initialize()
    _last_db = db
    widget = SettingsWidget(build_services(db))
    assert hasattr(widget, "station_value")
    assert hasattr(widget, "mode_value")
    assert hasattr(widget, "server_value")
    assert widget.server_value.text()
