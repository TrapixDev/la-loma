"""Recursos temporales compartidos por las pruebas del servidor."""

import pytest


@pytest.fixture
def servidor_aislado(tmp_path, monkeypatch):
    """Evita abrir la BD real o cambiar permisos de las carpetas del negocio."""
    from config import Config

    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    for name, relative in {
        "DB_PATH": "data/pos.db",
        "BACKUP_DIR": "data/backups",
        "PRODUCT_IMAGES_DIR": "data/product_images",
        "IMAGE_CACHE_DIR": "cache/images",
        "UPDATE_DIR": "updates",
        "TLS_CERT": "certs/server-cert.pem",
        "TLS_KEY": "certs/server-key.pem",
    }.items():
        monkeypatch.setattr(Config, name, str(tmp_path / relative))
    monkeypatch.setattr(Config, "SERVER_HOST", "127.0.0.1")
