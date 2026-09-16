"""Límites de seguridad del servidor: cuerpo, parámetros y origen de red."""

import http.client
import json
import os
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

PROJECT_DIR = str(Path(__file__).resolve().parents[1])
sys.path.insert(0, PROJECT_DIR)
os.chdir(PROJECT_DIR)
os.environ["QT_QPA_PLATFORM"] = "offscreen"

import server as server_module
from config import Config
from server import (MAX_BODY_BYTES, ip_permitida, parse_content_length,
                    start_server, valid_params)


def post(base, path, payload, token="", timeout=8):
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(base + path, data=data, method="POST")
    request.add_header("Content-Type", "application/json")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            body = json.loads(exc.read().decode("utf-8"))
        except Exception:
            body = {}
        return exc.code, body


def test_ip_permitida_solo_redes_privadas():
    assert ip_permitida("127.0.0.1") is True
    assert ip_permitida("192.168.1.25") is True
    assert ip_permitida("10.0.0.8") is True
    assert ip_permitida("172.16.5.4") is True
    assert ip_permitida("::1") is True
    assert ip_permitida("fe80::1") is True
    assert ip_permitida("::ffff:192.168.1.9") is True
    assert ip_permitida("8.8.8.8") is False
    assert ip_permitida("::ffff:8.8.8.8") is False
    assert ip_permitida("2001:4860:4860::8888") is False
    assert ip_permitida("no-es-ip") is False

    original = Config.LAN_ONLY
    Config.LAN_ONLY = False
    try:
        assert ip_permitida("8.8.8.8") is True
    finally:
        Config.LAN_ONLY = original


def test_parse_content_length():
    assert parse_content_length(None) == 0
    assert parse_content_length("10") == 10
    assert parse_content_length("0") == 0
    assert parse_content_length("abc") is None
    assert parse_content_length("-5") is None
    assert parse_content_length("9" * 40) is not None


def test_valid_params_limites():
    assert valid_params(None) == ()
    assert valid_params([1, "dos"]) == (1, "dos")
    for invalido in (
        {"a": 1}, [b"bytes"], [["anidado"]], [{"x": 1}],
        ["x" * (server_module.MAX_PARAM_CHARS + 1)],
        list(range(server_module.MAX_PARAMS + 1)),
    ):
        try:
            valid_params(invalido)
            raise AssertionError(f"no se rechazó: {type(invalido)}")
        except ValueError:
            pass


def test_servidor_rechaza_cuerpo_grande_y_params_invalidos(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="pos_limites_")
    db_path = os.path.join(tmpdir, "srv.db")
    os.environ["POS_DEMO_DATA"] = "0"
    srv = start_server(db_path=db_path, port=0)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.3)
    port = srv.server_address[1]
    base = f"http://127.0.0.1:{port}"
    try:
        status, setup = post(base, "/api/setup", {"name": "Tester", "pin": "1234"})
        assert status == 200 and setup.get("token"), (status, setup)
        token = setup["token"]

        status, body = post(base, "/api/query",
                            {"sql": "SELECT COUNT(*) AS t FROM sales",
                             "params": ["x" * (server_module.MAX_PARAM_CHARS + 1)]},
                            token)
        assert status == 400 and "largo" in body.get("error", "").lower(), (status, body)

        status, body = post(base, "/api/query",
                            {"sql": "SELECT COUNT(*) AS t FROM sales",
                             "params": list(range(server_module.MAX_PARAMS + 1))},
                            token)
        assert status == 400 and "demasiados" in body.get("error", "").lower(), (status, body)

        status, body = post(base, "/api/query",
                            {"sql": "SELECT COUNT(*) AS t FROM sales",
                             "params": {"a": 1}}, token)
        assert status == 400, (status, body)

        # Cuerpo más grande que el máximo permitido (se rechaza por cabecera).
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=8)
        try:
            conn.putrequest("POST", "/api/query")
            conn.putheader("Content-Type", "application/json")
            conn.putheader("Authorization", f"Bearer {token}")
            conn.putheader("Content-Length", str(MAX_BODY_BYTES + 1))
            conn.endheaders()
            respuesta = conn.getresponse()
            assert respuesta.status == 413, respuesta.status
        finally:
            conn.close()

        # Allowlist de red: si la IP no es de la LAN, todo responde 403.
        monkeypatch.setattr(server_module, "ip_permitida", lambda ip: False)
        try:
            with urllib.request.urlopen(base + "/api/health", timeout=8) as r:
                raise AssertionError("debía rechazar el origen")
        except urllib.error.HTTPError as exc:
            assert exc.code == 403, exc.code
        finally:
            monkeypatch.undo()
        print("[OK] límites de cuerpo, parámetros y allowlist de red")
    finally:
        srv.shutdown()
        srv.server_close()
