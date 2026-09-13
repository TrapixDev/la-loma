"""El cliente remoto no debe crashear si el puerto lo ocupa otro programa.

Caso real: un servidor ajeno (p. ej. otro proyecto con TLS) escucha en el
puerto del POS y cierra la conexión sin responder; antes eso producía
http.client.RemoteDisconnected sin capturar y tumbaba la app.
"""

import os
import socket
import sys
import threading
from pathlib import Path

PROJECT_DIR = str(Path(__file__).resolve().parents[1])
sys.path.insert(0, PROJECT_DIR)
os.chdir(PROJECT_DIR)
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from network.remote_db import RemoteDatabase, ServerError


def _start_closing_server():
    """Servidor TCP que acepta la conexión y la cierra sin responder."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", 0))
    server.listen(5)
    port = server.getsockname()[1]
    stop = threading.Event()

    def loop():
        while not stop.is_set():
            try:
                conn, _ = server.accept()
            except OSError:
                break
            try:
                conn.recv(65536)
            except OSError:
                pass
            conn.close()

    thread = threading.Thread(target=loop, daemon=True)
    thread.start()
    return server, port, stop


def test_puerto_ajeno_no_crashea():
    server, port, stop = _start_closing_server()
    db = RemoteDatabase(f"http://127.0.0.1:{port}")
    try:
        error = None
        try:
            db.health()
        except ServerError as exc:
            error = str(exc)
        assert error is not None, (
            "health() debe convertir RemoteDisconnected en ServerError")
        assert "cerró la conexión" in error, error
        assert db.check_connection(timeout=2) is False
    finally:
        stop.set()
        server.close()
    print("[OK] puerto ocupado por otro programa -> ServerError, sin crash")


def test_conexion_rechazada_es_server_error():
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.bind(("127.0.0.1", 0))
    free_port = probe.getsockname()[1]
    probe.close()

    db = RemoteDatabase(f"http://127.0.0.1:{free_port}")
    error = None
    try:
        db.health()
    except ServerError as exc:
        error = str(exc)
    assert error is not None, "conexión rechazada debe ser ServerError"
    assert db.check_connection(timeout=2) is False
    print("[OK] conexión rechazada -> ServerError")


def test_resolve_port():
    from config import _resolve_port
    assert _resolve_port("", "", 8000) == 8000
    assert _resolve_port("8001", "", 8000) == 8001
    assert _resolve_port("", "http://192.168.1.10:9000", 8000) == 9000
    assert _resolve_port("8001", "http://192.168.1.10:9000", 8000) == 8001
    assert _resolve_port("no-numero", "", 8000) == 8000
    print("[OK] resolución de puerto: clave > server_url > 8000")
