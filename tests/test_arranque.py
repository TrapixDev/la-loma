"""Tests de arranque: config.ini, DOCS_PATH, versiones y actualizaciones."""

import os
import sys
import time
from pathlib import Path

PROJECT_DIR = str(Path(__file__).resolve().parents[1])
sys.path.insert(0, PROJECT_DIR)
os.chdir(PROJECT_DIR)
os.environ["QT_QPA_PLATFORM"] = "offscreen"


def test_version_key():
    from network.updater import version_key
    ok = version_key("1.0.0") == (1, 0, 0) and version_key("1.2.10") > version_key("1.2.9")
    print(f"[{'OK' if ok else 'FAIL'}] version_key compara correctamente")
    assert ok


def test_setup_mas_nuevo():
    from network.updater import setup_mas_nuevo
    info = {"setups": [
        {"filename": "PosLaLoma_Setup_1.0.0.exe", "md5": "a"},
        {"filename": "PosLaLoma_Setup_1.1.0.exe", "md5": "b"},
        {"filename": "notas.txt"},
    ]}
    mejor = setup_mas_nuevo(info)
    ok = mejor is not None and mejor["version"] == "1.1.0"
    print(f"[{'OK' if ok else 'FAIL'}] setup_mas_nuevo elige 1.1.0: {mejor and mejor.get('version')}")
    assert ok


def test_hay_actualizacion():
    from network.updater import hay_actualizacion
    from config import Config
    info = {"server_version": Config.APP_VERSION, "setups": [
        {"filename": "PosLaLoma_Setup_9.9.9.exe", "md5": "x"}]}
    hay, nueva, setup = hay_actualizacion(info)
    ok1 = hay and nueva == "9.9.9" and setup is not None
    info2 = {"server_version": Config.APP_VERSION, "setups": [
        {"filename": "PosLaLoma_Setup_0.0.1.exe", "md5": "x"}]}
    hay2, _, _ = hay_actualizacion(info2)
    print(f"[{'OK' if ok1 else 'FAIL'}] detecta version superior")
    print(f"[{'OK' if not hay2 else 'FAIL'}] no detecta version inferior")
    assert ok1 and not hay2


def test_docs_path_compartida():
    """Si DOCS_PATH apunta a una carpeta escribible, se usa esa raiz."""
    import modules.documentos.paths as paths
    from config import Config
    from pathlib import Path as P
    tmp = P(PROJECT_DIR) / "tests" / ".tmp" / "documentos_red"
    tmp.mkdir(parents=True, exist_ok=True)
    original = paths._FALLBACK_LOCAL
    paths._FALLBACK_LOCAL = None
    old_docs = Config.DOCS_PATH
    Config.DOCS_PATH = str(tmp)
    try:
        raiz = paths.facturas_root()
        ok = raiz == tmp / "Facturas"
        print(f"[{'OK' if ok else 'FAIL'}] DOCS_PATH usado: {raiz}")
        assert ok
    finally:
        Config.DOCS_PATH = old_docs
        paths._FALLBACK_LOCAL = original


def test_docs_path_fallback_offline():
    """DOCS_PATH inaccesible -> Documentos/PosLaLoma (y no explota)."""
    import modules.documentos.paths as paths
    from config import Config
    original = paths._FALLBACK_LOCAL
    paths._FALLBACK_LOCAL = None
    old_docs = Config.DOCS_PATH
    inexistente = "\\\\192.0.2.1\\share_que_no_existe\\documentos"
    Config.DOCS_PATH = inexistente
    try:
        raiz = paths.facturas_root()
        ok = "Facturas" in str(raiz)
        print(f"[{'OK' if ok else 'FAIL'}] fallback a carpeta local: {raiz}")
        assert ok
    finally:
        Config.DOCS_PATH = old_docs
        paths._FALLBACK_LOCAL = original


def test_carpeta_factura_crea_mes():
    from modules.documentos.paths import carpeta_factura
    import modules.documentos.paths as paths
    from config import Config
    original = paths._FALLBACK_LOCAL
    paths._FALLBACK_LOCAL = None
    old_docs = Config.DOCS_PATH
    tmp = Path(PROJECT_DIR) / "tests" / ".tmp" / "documentos_mes"
    Config.DOCS_PATH = str(tmp)
    try:
        carpeta = carpeta_factura("2026-08-09 10:00:00")
        ok = carpeta.name == "2026-08" and carpeta.is_dir()
        print(f"[{'OK' if ok else 'FAIL'}] carpeta mensual: {carpeta}")
        assert ok
    finally:
        Config.DOCS_PATH = old_docs
        paths._FALLBACK_LOCAL = original


if __name__ == "__main__":
    tests = [
        test_version_key,
        test_setup_mas_nuevo,
        test_hay_actualizacion,
        test_docs_path_compartida,
        test_docs_path_fallback_offline,
        test_carpeta_factura_crea_mes,
    ]
    failed = 0
    for t in tests:
        try:
            t()
        except Exception as e:
            print(f"[FAIL] {t.__name__}: {e}")
            failed += 1
    print(f"\n{'ARRANQUE OK' if failed == 0 else f'ARRANQUE FAIL: {failed}'}")
