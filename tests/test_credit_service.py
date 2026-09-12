"""Tests del servicio de crédito: cuentas por cobrar, abonos y comprobantes."""

import os
import sys
from pathlib import Path

PROJECT_DIR = str(Path(__file__).resolve().parents[1])
sys.path.insert(0, PROJECT_DIR)
os.chdir(PROJECT_DIR)
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from database.db_manager import DatabaseManager
from database.models import CreditAccount, CreditPayment, CreditPaymentImage
from modules.credit.credit_service import CreditService
from network.session import session

TEST_DB = os.path.join(PROJECT_DIR, "tests", ".tmp", "test_credit_svc.db")

# Inicializar sesión para que make_payment no falle
session.set("test-token", 1, "Tester", "CAJA-1")

_counter = 0
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
    return CreditService(db), db


def _seed_client_and_sale(db, client_name="Juan Pérez", total=100000.0):
    """Crea un cliente y una venta de prueba, retorna (client_id, sale_id)."""
    global _counter
    _counter += 1
    id_number = f"10000000{_counter:02d}"
    client_id = db.execute_insert(
        "INSERT INTO clients (id_type, id_number, name) VALUES (?, ?, ?)",
        ("01", id_number, client_name),
    )
    sale_id = db.execute_insert(
        "INSERT INTO sales (invoice_number, client_id, total, payment_method, status) "
        "VALUES (?, ?, ?, ?, ?)",
        (f"V-{_counter:05d}", client_id, total, "credito", "completada"),
    )
    return client_id, sale_id


def test_create_account():
    svc, db = _svc()
    client_id, sale_id = _seed_client_and_sale(db)
    account_id = svc.create_account(sale_id, client_id, "V-00001", 100000.0)
    assert account_id > 0
    account = svc.get_by_id(account_id)
    assert account is not None
    assert account.total == 100000.0
    assert account.balance == 100000.0
    assert account.amount_paid == 0.0
    assert account.status == "pendiente"
    assert account.client_name == "Juan Pérez"


def test_get_all():
    svc, db = _svc()
    client_id, sale_id = _seed_client_and_sale(db)
    svc.create_account(sale_id, client_id, "V-00001", 50000.0)
    accounts = svc.get_all()
    assert len(accounts) == 1
    assert accounts[0].total == 50000.0


def test_get_all_filter_status():
    svc, db = _svc()
    c1, s1 = _seed_client_and_sale(db, "Activo", 10000.0)
    c2, s2 = _seed_client_and_sale(db, "Pagado", 20000.0)
    a1 = svc.create_account(s1, c1, f"V-{_counter-1:05d}", 10000.0)
    a2 = svc.create_account(s2, c2, f"V-{_counter:05d}", 20000.0)
    svc.make_payment(a2, 20000.0)
    pendientes = svc.get_all(status_filter="pendiente")
    pagadas = svc.get_all(status_filter="pagada")
    assert len(pendientes) == 1
    assert pendientes[0].id == a1
    assert len(pagadas) == 1
    assert pagadas[0].id == a2


def test_get_all_filter_client_search():
    svc, db = _svc()
    c1, s1 = _seed_client_and_sale(db, "María López", 10000.0)
    c2, s2 = _seed_client_and_sale(db, "Carlos Ruiz", 20000.0)
    svc.create_account(s1, c1, f"V-{_counter-1:05d}", 10000.0)
    svc.create_account(s2, c2, f"V-{_counter:05d}", 20000.0)
    results = svc.get_all(client_search="María")
    assert len(results) == 1
    assert results[0].client_name == "María López"


def test_get_by_client():
    svc, db = _svc()
    c1, s1 = _seed_client_and_sale(db, "Cliente A", 10000.0)
    c2, s2 = _seed_client_and_sale(db, "Cliente B", 20000.0)
    svc.create_account(s1, c1, f"V-{_counter-1:05d}", 10000.0)
    svc.create_account(s2, c2, f"V-{_counter:05d}", 20000.0)
    accounts = svc.get_by_client(c1)
    assert len(accounts) == 1
    assert accounts[0].client_name == "Cliente A"


def test_make_payment_updates_balance():
    svc, db = _svc()
    client_id, sale_id = _seed_client_and_sale(db, total=100000.0)
    account_id = svc.create_account(sale_id, client_id, f"V-{_counter:05d}", 100000.0)
    svc.make_payment(account_id, 30000.0)
    account = svc.get_by_id(account_id)
    assert account.amount_paid == 30000.0
    assert account.balance == 70000.0
    assert account.status == "pendiente"


def test_make_full_payment_marks_pagada():
    svc, db = _svc()
    client_id, sale_id = _seed_client_and_sale(db, total=50000.0)
    account_id = svc.create_account(sale_id, client_id, f"V-{_counter:05d}", 50000.0)
    svc.make_payment(account_id, 50000.0)
    account = svc.get_by_id(account_id)
    assert account.amount_paid == 50000.0
    assert account.balance == 0.0
    assert account.status == "pagada"


def test_make_multiple_payments():
    svc, db = _svc()
    client_id, sale_id = _seed_client_and_sale(db, total=100000.0)
    account_id = svc.create_account(sale_id, client_id, f"V-{_counter:05d}", 100000.0)
    svc.make_payment(account_id, 40000.0, "efectivo")
    svc.make_payment(account_id, 25000.0, "sinpe")
    svc.make_payment(account_id, 35000.0, "tarjeta")
    account = svc.get_by_id(account_id)
    assert account.amount_paid == 100000.0
    assert account.balance == 0.0
    assert account.status == "pagada"


def test_get_payments():
    svc, db = _svc()
    client_id, sale_id = _seed_client_and_sale(db)
    account_id = svc.create_account(sale_id, client_id, f"V-{_counter:05d}", 100000.0)
    svc.make_payment(account_id, 20000.0, "efectivo", notes="Primer abono")
    svc.make_payment(account_id, 10000.0, "sinpe", notes="Segundo abono")
    payments = svc.get_payments(account_id)
    assert len(payments) == 2
    assert payments[0].amount == 10000.0  # más reciente primero
    assert payments[1].amount == 20000.0
    assert payments[1].notes == "Primer abono"


def test_get_summary():
    svc, db = _svc()
    c1, s1 = _seed_client_and_sale(db, "Pendiente 1", 100000.0)
    c2, s2 = _seed_client_and_sale(db, "Pendiente 2", 50000.0)
    c3, s3 = _seed_client_and_sale(db, "Pagado", 30000.0)
    a1 = svc.create_account(s1, c1, f"V-{_counter-2:05d}", 100000.0)
    a2 = svc.create_account(s2, c2, f"V-{_counter-1:05d}", 50000.0)
    a3 = svc.create_account(s3, c3, f"V-{_counter:05d}", 30000.0)
    svc.make_payment(a1, 40000.0)
    svc.make_payment(a3, 30000.0)
    summary = svc.get_summary()
    assert summary["total_cuentas"] == 3
    assert summary["cuentas_pendientes"] == 2
    assert summary["total_pendiente"] == 110000.0  # (100000-40000) + 50000
    assert summary["total_pagado"] == 70000.0  # 40000 + 30000


def test_add_and_list_payment_images():
    svc, db = _svc()
    client_id, sale_id = _seed_client_and_sale(db)
    account_id = svc.create_account(sale_id, client_id, f"V-{_counter:05d}", 100000.0)
    payment_id = svc.make_payment(account_id, 25000.0, "sinpe")
    img_id = svc.add_payment_image(payment_id, "comprobante_001.jpg", "Transferencia")
    assert img_id > 0
    images = svc.list_payment_images(payment_id)
    assert len(images) == 1
    assert images[0].image_path == "comprobante_001.jpg"
    assert images[0].description == "Transferencia"


def test_remove_payment_image():
    svc, db = _svc()
    client_id, sale_id = _seed_client_and_sale(db)
    account_id = svc.create_account(sale_id, client_id, f"V-{_counter:05d}", 100000.0)
    payment_id = svc.make_payment(account_id, 25000.0)
    img_id = svc.add_payment_image(payment_id, "foto.jpg")
    removed = svc.remove_payment_image(img_id)
    assert removed is True
    images = svc.list_payment_images(payment_id)
    assert len(images) == 0


def test_payment_details_json():
    svc, db = _svc()
    client_id, sale_id = _seed_client_and_sale(db)
    account_id = svc.create_account(sale_id, client_id, f"V-{_counter:05d}", 100000.0)
    import json
    details = json.dumps([{"method": "Efectivo", "amount": 15000},
                          {"method": "Sinpe", "amount": 10000}])
    payment_id = svc.make_payment(account_id, 25000.0, "mixto", details)
    payments = svc.get_payments(account_id)
    assert payments[0].payment_details == details


def test_update_status():
    svc, db = _svc()
    client_id, sale_id = _seed_client_and_sale(db)
    account_id = svc.create_account(sale_id, client_id, f"V-{_counter:05d}", 100000.0)
    updated = svc.update_status(account_id, "anulada")
    assert updated is True
    account = svc.get_by_id(account_id)
    assert account.status == "anulada"


def test_overpayment_rejected():
    svc, db = _svc()
    client_id, sale_id = _seed_client_and_sale(db, total=50000.0)
    account_id = svc.create_account(sale_id, client_id, f"V-{_counter:05d}", 50000.0)
    try:
        svc.make_payment(account_id, 60000.0)
        raised = False
    except ValueError:
        raised = True
    assert raised
    account = svc.get_by_id(account_id)
    assert account.amount_paid == 0.0
    assert account.balance == 50000.0


def test_payment_reference_idempotent():
    svc, db = _svc()
    client_id, sale_id = _seed_client_and_sale(db, total=100000.0)
    account_id = svc.create_account(sale_id, client_id, f"V-{_counter:05d}", 100000.0)
    first = svc.make_payment(account_id, 20000.0, reference="ref-abc")
    retry = svc.make_payment(account_id, 20000.0, reference="ref-abc")
    assert first == retry
    assert len(svc.get_payments(account_id)) == 1
    account = svc.get_by_id(account_id)
    assert account.amount_paid == 20000.0


def test_payment_on_anulled_account_rejected():
    svc, db = _svc()
    client_id, sale_id = _seed_client_and_sale(db)
    account_id = svc.create_account(sale_id, client_id, f"V-{_counter:05d}", 100000.0)
    svc.update_status(account_id, "anulada")
    try:
        svc.make_payment(account_id, 10000.0)
        raised = False
    except ValueError:
        raised = True
    assert raised


def test_remove_payment_image_deletes_file():
    import tempfile
    svc, db = _svc()
    client_id, sale_id = _seed_client_and_sale(db)
    account_id = svc.create_account(sale_id, client_id, f"V-{_counter:05d}", 100000.0)
    payment_id = svc.make_payment(account_id, 25000.0)
    tmpdir = tempfile.mkdtemp(prefix="pos_comp_")
    path = os.path.join(tmpdir, "comprobante.png")
    with open(path, "wb") as handle:
        handle.write(b"PNG")
    img_id = svc.add_payment_image(payment_id, path, "Prueba")
    assert svc.remove_payment_image(img_id) is True
    assert not os.path.exists(path)
    assert svc.list_payment_images(payment_id) == []
