"""Tests del servidor: endpoints de actualización, política de tablas y login."""

import hashlib
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

from server import start_server, validate_sql

TMP_DIR = Path(PROJECT_DIR) / "tests" / ".tmp" / "updates"


def get(url, timeout=8):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def post(url, payload, token="", timeout=8):
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, method="POST")
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


def test_update_info_y_descarga():
    import config as config_module
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    fake = TMP_DIR / "PosLaLoma_Setup_9.9.9.exe"
    fake.write_bytes(b"FAKE-SETUP-DATA")

    original_dir = config_module.Config.UPDATE_DIR
    config_module.Config.UPDATE_DIR = str(TMP_DIR)
    srv = start_server(port=0)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.3)
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        info = get(base + "/api/update/info")
        ok_info = (info.get("server_version") == config_module.Config.APP_VERSION
                   and any(s["filename"] == "PosLaLoma_Setup_9.9.9.exe" for s in info.get("setups", [])))
        print(f"[{'OK' if ok_info else 'FAIL'}] /api/update/info lista el setup")

        with urllib.request.urlopen(base + "/api/update/download/PosLaLoma_Setup_9.9.9.exe", timeout=8) as r:
            data = r.read()
        ok_dl = data == b"FAKE-SETUP-DATA"
        print(f"[{'OK' if ok_dl else 'FAIL'}] /api/update/download devuelve el archivo")

        try:
            urllib.request.urlopen(base + "/api/update/download/..%2F..%2Fpos.db", timeout=8)
            ok_traversal = False
        except urllib.error.HTTPError as exc:
            ok_traversal = exc.code in (400, 404)
        except urllib.error.URLError:
            ok_traversal = True
        print(f"[{'OK' if ok_traversal else 'FAIL'}] traversal bloqueado")

        assert ok_info and ok_dl and ok_traversal
    finally:
        srv.shutdown()
        srv.server_close()
        config_module.Config.UPDATE_DIR = original_dir
        fake.unlink(missing_ok=True)


def test_descarga_verifica_sha256():
    import config as config_module
    from network import updater

    TMP_DIR.mkdir(parents=True, exist_ok=True)
    fake = TMP_DIR / "PosLaLoma_Setup_9.9.8.exe"
    contenido = b"FAKE-SETUP-SHA256"
    fake.write_bytes(contenido)

    original_dir = config_module.Config.UPDATE_DIR
    original_url = config_module.Config.SERVER_URL
    config_module.Config.UPDATE_DIR = str(TMP_DIR)
    srv = start_server(port=0)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.3)
    config_module.Config.SERVER_URL = f"http://127.0.0.1:{srv.server_address[1]}"
    destino = TMP_DIR / "descargas"
    try:
        info = updater.consultar_actualizaciones()
        setup = updater.setup_mas_nuevo(info)
        assert setup is not None
        assert setup.get("sha256") == hashlib.sha256(contenido).hexdigest()
        ruta = updater.descargar_setup(setup, destino)
        assert ruta.read_bytes() == contenido

        alterado = {**setup, "sha256": "0" * 64}
        try:
            updater.descargar_setup(alterado, destino)
            raise AssertionError("debía rechazar el hash alterado")
        except updater.UpdateError:
            pass

        solo_md5 = {k: v for k, v in setup.items() if k != "sha256"}
        ruta = updater.descargar_setup(solo_md5, destino)
        assert ruta.read_bytes() == contenido
        print("[OK] descarga verifica SHA-256 (y MD5 como respaldo)")
    finally:
        srv.shutdown()
        srv.server_close()
        config_module.Config.UPDATE_DIR = original_dir
        config_module.Config.SERVER_URL = original_url
        fake.unlink(missing_ok=True)
        import shutil
        shutil.rmtree(destino, ignore_errors=True)


def test_validate_sql_politica_tablas():
    permitidas = (
        "SELECT * FROM sales",
        "SELECT id FROM credit_payments WHERE credit_account_id = 1",
        "INSERT INTO credit_payments (amount) VALUES (1)",
        "INSERT INTO counters (name, value) VALUES ('invoice', 1) "
        "ON CONFLICT(name) DO UPDATE SET value = value + 1",
        "UPDATE sales SET status = 'anulada' WHERE id = 1",
        "UPDATE products SET active = 0 WHERE id = 1",
        "INSERT INTO promotions (name, type) VALUES ('x', 'payment')",
        "DELETE FROM promotions WHERE id = 1",
        "DELETE FROM product_images WHERE id = 1",
        "DELETE FROM expenses WHERE id = 1",
    )
    for sql in permitidas:
        assert validate_sql(sql), sql

    bloqueadas = (
        "SELECT * FROM users",
        "SELECT name FROM users WHERE id = 1",
        "SELECT * FROM sqlite_master",
        "INSERT INTO users (name) VALUES ('x')",
        "UPDATE users SET pin_hash = 'x'",
        "DELETE FROM users",
        "DELETE FROM sales",
        "DELETE FROM audit_log",
        "DELETE FROM counters",
        "DROP TABLE sales",
        "SELECT 1; DELETE FROM sales",
    )
    for sql in bloqueadas:
        try:
            validate_sql(sql)
            raise AssertionError(f"no se bloqueó: {sql}")
        except ValueError:
            pass
    print(f"[OK] política de tablas: {len(permitidas)} permitidas, "
          f"{len(bloqueadas)} bloqueadas")


def test_login_y_politica_dml():
    tmpdir = tempfile.mkdtemp(prefix="pos_srv_")
    db_path = os.path.join(tmpdir, "srv.db")
    os.environ["POS_DEMO_DATA"] = "0"
    srv = start_server(db_path=db_path, port=0)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.3)
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        status, setup = post(base + "/api/setup", {"name": "Tester", "pin": "1234"})
        assert status == 200 and setup.get("token"), (status, setup)
        token = setup["token"]

        status, body = post(base + "/api/query",
                            {"sql": "SELECT COUNT(*) AS t FROM sales"}, token)
        assert status == 200 and "rows" in body, (status, body)

        for bad in ("UPDATE users SET name = 'x'",
                    "INSERT INTO users (name) VALUES ('x')",
                    "DELETE FROM sales",
                    "DELETE FROM audit_log"):
            status, body = post(base + "/api/execute", {"sql": bad}, token)
            assert status == 400, (bad, status, body)

        status, body = post(base + "/api/query",
                            {"sql": "SELECT * FROM users"}, token)
        assert status == 400, (status, body)

        status, body = post(base + "/api/audit",
                            {"event": "PRUEBA_AUDIT", "detail": "test"}, token)
        assert status == 200, (status, body)
        import sqlite3
        connection = sqlite3.connect(db_path)
        try:
            evento = connection.execute(
                "SELECT COUNT(*) FROM audit_log WHERE event = 'PRUEBA_AUDIT'"
            ).fetchone()[0]
        finally:
            connection.close()
        assert evento == 1

        # Varios logins válidos seguidos no deben agotar el rate limit.
        for _ in range(3):
            status, body = post(base + "/api/login", {"pin": "1234"})
            assert status == 200 and body.get("token"), (status, body)
        print("[OK] login válido + DML restringido + auditoría remota")
    finally:
        srv.shutdown()
        srv.server_close()
