"""Tests del servidor: endpoints de actualización y descarga segura."""

import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

PROJECT_DIR = str(Path(__file__).resolve().parents[1])
sys.path.insert(0, PROJECT_DIR)
os.chdir(PROJECT_DIR)
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from server import start_server

TMP_DIR = Path(PROJECT_DIR) / "tests" / ".tmp" / "updates"


def get(url, timeout=8):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


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


if __name__ == "__main__":
    failed = 0
    try:
        test_update_info_y_descarga()
    except Exception as e:
        print(f"[FAIL] test_update_info_y_descarga: {e}")
        failed += 1
    print(f"\n{'SERVIDOR OK' if failed == 0 else f'SERVIDOR FAIL: {failed}'}")
