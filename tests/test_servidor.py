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


def test_descarga_verifica_sha256_y_firma():
    import base64

    import config as config_module
    from network import updater

    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey,
    )

    TMP_DIR.mkdir(parents=True, exist_ok=True)
    fake = TMP_DIR / "PosLaLoma_Setup_9.9.8.exe"
    contenido = b"FAKE-SETUP-SHA256-FIRMADO"
    fake.write_bytes(contenido)
    clave = Ed25519PrivateKey.generate()
    firma = base64.b64encode(clave.sign(contenido)).decode("ascii")
    (TMP_DIR / "PosLaLoma_Setup_9.9.8.exe.sig").write_text(firma + "\n",
                                                           encoding="utf-8")

    original_dir = config_module.Config.UPDATE_DIR
    original_url = config_module.Config.SERVER_URL
    original_key = config_module.Config.UPDATE_PUBLIC_KEY
    config_module.Config.UPDATE_DIR = str(TMP_DIR)
    config_module.Config.UPDATE_PUBLIC_KEY = base64.b64encode(
        clave.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw)).decode("ascii")
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
        assert setup.get("signature") == firma
        ruta = updater.descargar_setup(setup, destino)
        assert ruta.read_bytes() == contenido

        alterado = {**setup, "sha256": "0" * 64}
        try:
            updater.descargar_setup(alterado, destino)
            raise AssertionError("debía rechazar el hash alterado")
        except updater.UpdateError:
            pass

        sin_hash = {k: v for k, v in setup.items() if k != "sha256"}
        try:
            updater.descargar_setup(sin_hash, destino)
            raise AssertionError("debía rechazar la descarga sin SHA-256")
        except updater.UpdateError:
            pass

        sin_firma = {k: v for k, v in setup.items() if k != "signature"}
        try:
            updater.descargar_setup(sin_firma, destino)
            raise AssertionError("debía rechazar la descarga sin firma")
        except updater.UpdateError:
            pass

        firma_mala = {**setup, "signature": base64.b64encode(
            b"x" * 64).decode("ascii")}
        try:
            updater.descargar_setup(firma_mala, destino)
            raise AssertionError("debía rechazar la firma inválida")
        except updater.UpdateError:
            pass

        ruta = updater.descargar_setup(setup, destino)
        assert ruta.read_bytes() == contenido

        # Un nombre con ruta no puede escribir fuera de la carpeta destino.
        travesura = {**setup, "filename": "..\\PosLaLoma_Setup_9.9.8.exe"}
        try:
            updater.descargar_setup(travesura, destino / "sub")
            raise AssertionError("debía rechazar el nombre con traversal")
        except updater.UpdateError:
            pass
        print("[OK] descarga verifica SHA-256, firma y nombre contenido")
    finally:
        srv.shutdown()
        srv.server_close()
        config_module.Config.UPDATE_DIR = original_dir
        config_module.Config.SERVER_URL = original_url
        config_module.Config.UPDATE_PUBLIC_KEY = original_key
        fake.unlink(missing_ok=True)
        (TMP_DIR / "PosLaLoma_Setup_9.9.8.exe.sig").unlink(missing_ok=True)
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
    )
    for sql in permitidas:
        assert validate_sql(sql), sql

    bloqueadas = (
        "SELECT * FROM users",
        "SELECT name FROM users WHERE id = 1",
        'SELECT name FROM "users"',
        "SELECT name FROM main.users",
        "SELECT name FROM [users]",
        "SELECT * FROM sqlite_master",
        "INSERT INTO users (name) VALUES ('x')",
        "UPDATE users SET pin_hash = 'x'",
        "DELETE FROM users",
        "DELETE FROM sales",
        "DELETE FROM audit_log",
        "DELETE FROM counters",
        "DELETE FROM expenses WHERE id = 1",
        "DELETE FROM credit_payments WHERE id = 1",
        "DELETE FROM credit_accounts WHERE id = 1",
        "DELETE FROM credit_notes WHERE id = 1",
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
                    "DELETE FROM audit_log",
                    "DELETE FROM expenses WHERE id = 1",
                    "DELETE FROM credit_payments WHERE id = 1",
                    # El authorizer bloquea la lectura de users aunque el
                    # SELECT de origen use comillas, corchetes o esquema.
                    "INSERT INTO app_config (key, value) "
                    "SELECT 'x', pin_hash FROM users",
                    "INSERT INTO app_config (key, value) "
                    'SELECT \'x\', pin_hash FROM "users"',
                    "UPDATE audit_log SET detail = 'falso'"):
            status, body = post(base + "/api/execute", {"sql": bad}, token)
            assert status == 400, (bad, status, body)

        for bad_select in ("SELECT * FROM users",
                           'SELECT pin_hash FROM "users"',
                           "SELECT pin_hash FROM main.users",
                           "SELECT pin_hash FROM [users]"):
            status, body = post(base + "/api/query", {"sql": bad_select}, token)
            assert status == 400, (bad_select, status, body)

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
