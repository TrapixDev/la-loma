"""Tests del motor de promociones: CRUD, bundles, volumen, pago y financiamiento."""

import os
import sys
from pathlib import Path

PROJECT_DIR = str(Path(__file__).resolve().parents[1])
sys.path.insert(0, PROJECT_DIR)
os.chdir(PROJECT_DIR)
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from database.db_manager import DatabaseManager
from modules.promotions.promotion_service import PromotionService

TEST_DB = os.path.join(PROJECT_DIR, "tests", ".tmp", "test_promotions.db")

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


def _svc():
    global _last_db
    db = DatabaseManager(TEST_DB)
    db.initialize()
    _last_db = db
    return PromotionService(db), db


def _cart(items):
    """items: [(product_id, cantidad, precio_unitario)]."""
    return [
        {"product_id": pid, "quantity": qty, "unit_price": price,
         "discount": 0.0, "total": qty * price}
        for pid, qty, price in items
    ]


def test_crud_promociones():
    svc, db = _svc()
    promo_id = svc.create("Sillas 4+ 10%", "volume",
                          {"product_id": 7, "tiers": [[4, 10]]})
    assert promo_id > 0
    promos = svc.get_all()
    assert len(promos) == 1
    assert promos[0].name == "Sillas 4+ 10%"
    assert svc.set_active(promo_id, False) is True
    assert svc.get_all(active_only=True) == []
    promo = svc.get_by_id(promo_id)
    promo.name = "Sillas volumen"
    assert svc.update(promo) is True
    assert svc.get_by_id(promo_id).name == "Sillas volumen"
    assert svc.delete(promo_id) is True
    assert svc.get_all() == []


def test_validaciones():
    svc, _ = _svc()
    casos = [
        ("", "volume", {"product_id": 1, "tiers": [[4, 10]]}),
        ("x", "volume", {"product_id": 1, "tiers": []}),
        ("x", "volume", {"product_id": 1, "tiers": [[1, 10]]}),
        ("x", "bundle", {"product_id": 1, "discount_product_id": 1,
                         "percent": 15}),
        ("x", "bundle", {"product_id": 1, "discount_product_id": 2,
                         "percent": 0}),
        ("x", "payment", {"methods": [], "percent": 5}),
        ("x", "payment", {"methods": ["bitcoin"], "percent": 5}),
        ("x", "financing", {"min_total": 0, "months": [3]}),
        ("x", "otro", {}),
    ]
    for name, promo_type, params in casos:
        try:
            svc.create(name, promo_type, params)
            raise AssertionError(f"no se validó: {name} {promo_type} {params}")
        except ValueError:
            pass


def test_bundle_aplica_descuento():
    svc, _ = _svc()
    svc.create("Combo mesa + lámpara", "bundle",
               {"product_id": 1, "discount_product_id": 2, "percent": 15})
    result = svc.evaluate(_cart([(1, 1, 100000), (2, 2, 50000)]))
    assert result["line_discounts"] == {1: 15000.0}
    assert result["product_discount"] == 15000.0
    assert result["total"] == 185000.0
    assert len(result["applied"]) == 1


def test_bundle_sin_producto_requerido_no_aplica():
    svc, _ = _svc()
    svc.create("Combo mesa + lámpara", "bundle",
               {"product_id": 1, "discount_product_id": 2, "percent": 15})
    result = svc.evaluate(_cart([(2, 2, 50000)]))
    assert result["product_discount"] == 0.0


def test_volume_por_tramos():
    svc, _ = _svc()
    svc.create("Sillas 4+ 10%, 6+ 20%", "volume",
               {"product_id": 3, "tiers": [[4, 10], [6, 20]]})
    cinco = svc.evaluate(_cart([(3, 5, 10000)]))
    assert cinco["line_discounts"] == {0: 5000.0}
    seis = svc.evaluate(_cart([(3, 6, 10000)]))
    assert seis["line_discounts"] == {0: 12000.0}
    tres = svc.evaluate(_cart([(3, 3, 10000)]))
    assert tres["product_discount"] == 0.0


def test_mejor_descuento_por_linea():
    svc, _ = _svc()
    svc.create("Combo", "bundle",
               {"product_id": 1, "discount_product_id": 2, "percent": 15})
    svc.create("Volumen", "volume",
               {"product_id": 2, "tiers": [[4, 10]]})
    result = svc.evaluate(_cart([(1, 1, 100000), (2, 4, 25000)]))
    # Línea del producto 2 = 100000: gana el bundle (15%) sobre volumen (10%).
    assert result["line_discounts"] == {1: 15000.0}
    assert len(result["applied"]) == 1


def test_descuento_por_metodo_de_pago():
    svc, _ = _svc()
    svc.create("5% efectivo", "payment",
               {"methods": ["efectivo"], "percent": 5})
    carrito = _cart([(1, 1, 100000)])
    efectivo = svc.evaluate(carrito, payment_method="efectivo")
    assert efectivo["payment_discount"] == 5000.0
    assert efectivo["total"] == 95000.0
    tarjeta = svc.evaluate(carrito, payment_method="tarjeta")
    assert tarjeta["payment_discount"] == 0.0
    mixto = svc.evaluate(carrito, payment_method="mixto")
    assert mixto["payment_discount"] == 0.0


def test_descuento_pago_sobre_total_rebajado():
    svc, _ = _svc()
    svc.create("Combo 20%", "bundle",
               {"product_id": 1, "discount_product_id": 2, "percent": 20})
    svc.create("5% efectivo", "payment",
               {"methods": ["efectivo"], "percent": 5})
    result = svc.evaluate(_cart([(1, 1, 50000), (2, 1, 50000)]),
                          payment_method="efectivo")
    assert result["product_discount"] == 10000.0
    assert result["base"] == 90000.0
    assert result["payment_discount"] == 4500.0
    assert result["total"] == 85500.0


def test_financiamiento_informativo():
    svc, _ = _svc()
    svc.create("3, 6 o 12 meses", "financing",
               {"min_total": 100000, "months": [3, 6, 12]})
    carrito = _cart([(1, 1, 120000)])
    credito = svc.evaluate(carrito, es_credito=True)
    assert credito["financing"] is not None
    assert credito["financing"]["installments"]["3"] == 40000.0
    assert credito["financing"]["installments"]["12"] == 10000.0
    contado = svc.evaluate(carrito, es_credito=False)
    assert contado["financing"] is None
    chico = svc.evaluate(_cart([(1, 1, 50000)]), es_credito=True)
    assert chico["financing"] is None
