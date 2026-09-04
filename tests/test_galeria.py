"""Tests de la galería de fotos de producto (product_images y portada)."""

import os
import sys
import time
from pathlib import Path

PROJECT_DIR = str(Path(__file__).resolve().parents[1])
sys.path.insert(0, PROJECT_DIR)
os.chdir(PROJECT_DIR)
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from database.db_manager import DatabaseManager
from database.models import Product
from modules.products.product_service import ProductService

TEST_DB = os.path.join(PROJECT_DIR, "tests", ".tmp", "test_galeria.db")


def cleanup():
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
            time.sleep(0.1)


def get_db():
    cleanup()
    db = DatabaseManager(TEST_DB)
    db.initialize()
    return db


def make_product():
    return Product(
        code="GAL-001", name="Mesa de prueba", category_id=None,
        cost_price=100.0, sale_price=200.0, tax_type="gravado", tax_rate=13.0,
        active=True, image_path="",
    )


def test_tabla_product_images_existe():
    db = get_db()
    rows = db.execute_query(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='product_images'")
    ok = len(rows) > 0
    print(f"[{'OK' if ok else 'FAIL'}] tabla product_images existe")
    db.close()
    cleanup()
    assert ok


def test_agregar_y_listar_fotos():
    db = get_db()
    svc = ProductService(db)
    pid = svc.create(make_product())
    svc.add_image(pid, "p1.png")
    svc.add_image(pid, "p2.png")
    svc.add_image(pid, "p3.png")
    fotos = svc.list_images(pid)
    ok = fotos == ["p1.png", "p2.png", "p3.png"], fotos
    print(f"[{'OK' if ok else 'FAIL'}] fotos agregadas y listadas: {fotos}")
    db.close()
    cleanup()
    assert ok


def test_primera_foto_es_portada():
    db = get_db()
    svc = ProductService(db)
    pid = svc.create(make_product())
    svc.add_image(pid, "p1.png")
    p = svc.get_by_id(pid)
    ok = p.image_path == "p1.png"
    print(f"[{'OK' if ok else 'FAIL'}] primera foto se convierte en portada: {p.image_path}")
    db.close()
    cleanup()
    assert ok


def test_set_cover_reordena():
    db = get_db()
    svc = ProductService(db)
    pid = svc.create(make_product())
    svc.add_image(pid, "p1.png")
    svc.add_image(pid, "p2.png")
    svc.set_cover(pid, "p2.png")
    p = svc.get_by_id(pid)
    fotos = svc.list_images(pid)
    ok = p.image_path == "p2.png" and fotos[0] == "p2.png", (p.image_path, fotos)
    print(f"[{'OK' if ok else 'FAIL'}] portada p2: portada={p.image_path}, fotos={fotos}")
    db.close()
    cleanup()
    assert ok


def test_quitar_portada_toma_siguiente():
    db = get_db()
    svc = ProductService(db)
    pid = svc.create(make_product())
    svc.add_image(pid, "p1.png")
    svc.add_image(pid, "p2.png")
    svc.remove_image(pid, "p1.png")  # p1 era la portada
    p = svc.get_by_id(pid)
    fotos = svc.list_images(pid)
    ok = p.image_path == "p2.png" and fotos == ["p2.png"], (p.image_path, fotos)
    print(f"[{'OK' if ok else 'FAIL'}] tras quitar portada: portada={p.image_path}, fotos={fotos}")
    db.close()
    cleanup()
    assert ok


if __name__ == "__main__":
    tests = [
        test_tabla_product_images_existe,
        test_agregar_y_listar_fotos,
        test_primera_foto_es_portada,
        test_set_cover_reordena,
        test_quitar_portada_toma_siguiente,
    ]
    failed = 0
    for t in tests:
        try:
            t()
        except Exception as e:
            print(f"[FAIL] {t.__name__}: {e}")
            failed += 1
    print(f"\n{'GALERIA OK' if failed == 0 else f'GALERIA FAIL: {failed}'}")
