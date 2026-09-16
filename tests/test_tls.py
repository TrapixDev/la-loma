"""TLS opcional: certificado autofirmado, servidor HTTPS y cliente con CA."""

import json
import os
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

PROJECT_DIR = str(Path(__file__).resolve().parents[1])
sys.path.insert(0, PROJECT_DIR)
os.chdir(PROJECT_DIR)
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from config import Config
from network.remote_db import RemoteDatabase
from server import start_server

pytestmark = pytest.mark.skipif(
    subprocess.run([sys.executable, "-c", "import cryptography"],
                   capture_output=True).returncode != 0,
    reason="Requiere el paquete cryptography (solo para pruebas)")


def _generar_certificado(destino: Path) -> None:
    result = subprocess.run(
        [sys.executable, "tools/generar_certificado.py",
         "--host", "127.0.0.1", "--out", str(destino)],
        capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
    assert destino.is_file()


def _post_https(url: str, cacert: Path | None, context=None) -> int:
    request = urllib.request.Request(
        url, data=b"{}", method="POST",
        headers={"Content-Type": "application/json"})
    if context is None:
        context = ssl.create_default_context(cafile=str(cacert) if cacert else None)
    with urllib.request.urlopen(request, timeout=8, context=context) as response:
        return response.status


def test_tls_servidor_y_cliente():
    tmpdir = Path(tempfile.mkdtemp(prefix="pos_tls_"))
    pem = tmpdir / "server.pem"
    _generar_certificado(pem)

    original = (Config.TLS_CERT, Config.TLS_KEY, Config.TLS_CA, Config.TLS_INSECURE)
    Config.TLS_CERT = str(pem)
    Config.TLS_KEY = ""
    Config.TLS_INSECURE = False
    os.environ["POS_DEMO_DATA"] = "0"
    srv = start_server(db_path=str(tmpdir / "srv.db"), host="127.0.0.1", port=0)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.3)
    assert srv.tls is True, "El servidor debía activar TLS con el certificado"
    url = f"https://127.0.0.1:{srv.server_address[1]}/api/health"
    try:
        assert _post_https(url, pem) == 200

        # Sin confiar en el certificado, la conexión debe fallar.
        fallo = False
        try:
            _post_https(url, None)
        except ssl.SSLError:
            fallo = True
        except urllib.error.URLError as exc:
            fallo = isinstance(exc.reason, ssl.SSLError)
        assert fallo, "El cliente no debía aceptar el certificado sin CA"

        # Cliente del POS con la CA configurada.
        db = RemoteDatabase(f"https://127.0.0.1:{srv.server_address[1]}", "CAJA1")
        Config.TLS_CA = str(pem)
        assert db.check_connection() is True
        Config.TLS_CA = ""
        assert db.check_connection() is False
        Config.TLS_INSECURE = True
        assert db.check_connection() is True
        Config.TLS_INSECURE = False
    finally:
        srv.shutdown()
        srv.server_close()
        (Config.TLS_CERT, Config.TLS_KEY, Config.TLS_CA,
         Config.TLS_INSECURE) = original
