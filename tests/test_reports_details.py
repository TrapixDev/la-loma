"""Detalle por doble clic en movimientos del día e historial de ventas."""

import os
import sys
from pathlib import Path

PROJECT_DIR = str(Path(__file__).resolve().parents[1])
sys.path.insert(0, PROJECT_DIR)
os.chdir(PROJECT_DIR)
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])

from database.db_manager import DatabaseManager
from modules.credit.credit_service import CreditService
from modules.expenses.expense_service import ExpenseService
from modules.pos.cart_service import CartService
from modules.reports.reports_service import ReportsService
from network.session import session

session.set("test-token", 1, "Tester", "CAJA-1")

TEST_DB = os.path.join(PROJECT_DIR, "tests", ".tmp", "test_reports_details.db")

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


def _db() -> DatabaseManager:
    global _last_db
    db = DatabaseManager(TEST_DB)
    db.initialize()
    _last_db = db
    return db


def _services(db) -> dict:
    return {
        "db": db,
        "cart": CartService(db),
        "credit": CreditService(db),
        "expenses": ExpenseService(db),
        "reports": ReportsService(db),
    }


def _seed_sale(db, total=100000.0, method="efectivo", currency="CRC",
               payment_details="", client_name="Cliente de prueba"):
    """Crea cliente + venta + artículo. Devuelve (client_id, sale_id)."""
    global _counter
    _counter += 1
    client_id = db.execute_insert(
        "INSERT INTO clients (id_type, id_number, name) VALUES (?, ?, ?)",
        ("01", f"30000000{_counter:02d}", client_name),
    )
    sale_id = db.execute_insert(
        "INSERT INTO sales (invoice_number, client_id, subtotal, discount, "
        "tax_amount, total, payment_method, cash_received, change_amount, "
        "payment_details, invoice_type, currency, exchange_rate, status, "
        "hacienda_key, hacienda_status, electronic_invoice, station, user_name) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (f"V-{_counter:05d}", client_id, round(total * 0.885, 2), 0.0,
         round(total * 0.115, 2), total, method, total, 0.0, payment_details,
         "general", currency, 520.0, "completada",
         "50625092500310112345600100001010000000001111111", "ACEPTADA", 1,
         "CAJA1", "Cajero"),
    )
    product_id = db.execute_insert(
        "INSERT INTO products (name, sale_price, cost_price) VALUES (?, ?, ?)",
        (f"Producto {_counter}", total, round(total * 0.4, 2)),
    )
    db.execute_insert(
        "INSERT INTO sale_items (sale_id, product_id, product_name, quantity, "
        "unit_price, unit_cost, total) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (sale_id, product_id, f"Producto {_counter}", 1.0, total,
         round(total * 0.4, 2), total),
    )
    return client_id, sale_id


# ---------- servicios ----------

def test_get_expense_roundtrip():
    db = _db()
    service = ExpenseService(db)
    expense_id = service.add_expense(15000.0, "Transporte", "Flete",
                                     "efectivo", "2026-09-25")
    expense = service.get_expense(expense_id)
    assert expense is not None
    assert expense.category == "Transporte"
    assert expense.amount == 15000.0
    assert expense.description == "Flete"
    assert service.get_expense(999999) is None


def test_get_payment_roundtrip():
    db = _db()
    services = _services(db)
    client_id, sale_id = _seed_sale(db, total=50000.0, method="credito")
    account_id = services["credit"].create_account(
        sale_id, client_id, "V-00050", 50000.0)
    payment_id = services["credit"].make_payment(
        account_id, 20000.0, "efectivo", notes="Abono parcial")
    payment = services["credit"].get_payment(payment_id)
    assert payment is not None
    assert payment.amount == 20000.0
    assert payment.notes == "Abono parcial"
    assert payment.invoice_number == "V-00050"
    assert payment.client_name
    assert services["credit"].get_payment(999999) is None


def test_get_credit_note_roundtrip():
    db = _db()
    services = _services(db)
    _, sale_id = _seed_sale(db, total=30000.0)
    note_id = services["reports"].create_credit_note(
        sale_id, "Devolución", "Devolución de mercancía", total=30000.0)
    nota = services["reports"].get_credit_note(note_id)
    venta = services["cart"].get_sale(sale_id)
    assert nota is not None
    assert venta is not None
    assert nota["invoice_number"] == "NC-00001"
    assert nota["factura_original"] == venta.invoice_number
    assert nota["total"] == 30000.0
    assert nota["client_name"]
    assert services["reports"].get_credit_note(999999) is None


# ---------- diálogos de detalle ----------

def test_detalle_venta_muestra_articulos_totales_y_pagos():
    from modules.reports.detail_dialogs import SaleDetailDialog

    db = _db()
    services = _services(db)
    _, sale_id = _seed_sale(db, total=25000.0, method="tarjeta",
                            client_name="Ana Pérez")
    dialog = SaleDetailDialog(services, sale_id)
    try:
        assert dialog.sale is not None
        assert dialog.sale.client_name == "Ana Pérez"
        assert dialog._items_table.rowCount() == 1
        assert dialog._items_table.item(0, 1).text().startswith("Producto")
        assert dialog.filas["Monto total"] == "₡25,000.00"
        assert any("Paga con" in clave for clave in dialog.filas)
    finally:
        dialog.close()


def test_detalle_venta_usd_muestra_equivalente():
    from modules.reports.detail_dialogs import SaleDetailDialog

    db = _db()
    services = _services(db)
    _, sale_id = _seed_sale(db, total=52000.0, currency="USD",
                            payment_details='[{"method":"Tarjeta","amount":100}]')
    dialog = SaleDetailDialog(services, sale_id)
    try:
        assert "Equivalente CRC" in dialog.filas
        assert dialog.filas["Equivalente CRC"] == "₡52,000.00"
    finally:
        dialog.close()


def test_detalles_de_gasto_abono_y_nota():
    from modules.reports.detail_dialogs import (
        CreditNoteDetailDialog,
        CreditPaymentDetailDialog,
        ExpenseDetailDialog,
    )

    db = _db()
    services = _services(db)

    expense_id = services["expenses"].add_expense(
        8000.0, "Renta", "Local comercial", "efectivo", "2026-09-25")
    gasto = ExpenseDetailDialog(services, expense_id)
    try:
        assert gasto.filas["Monto"] == "₡8,000.00"
        assert gasto.filas["Categoría"] == "Renta"
        assert gasto.filas["Descripción"] == "Local comercial"
        assert gasto.filas["Método de pago"] == "efectivo"
    finally:
        gasto.close()

    client_id, sale_id = _seed_sale(db, total=50000.0, method="credito")
    account_id = services["credit"].create_account(
        sale_id, client_id, "V-00050", 50000.0)
    payment_id = services["credit"].make_payment(
        account_id, 15000.0, "sinpe", notes="Abono parcial")
    abono = CreditPaymentDetailDialog(services, payment_id)
    try:
        assert abono.filas["Monto"] == "₡15,000.00"
        assert abono.filas["Notas"] == "Abono parcial"
        assert abono.filas["Método"] == "Sinpe"
    finally:
        abono.close()

    note_id = services["reports"].create_credit_note(
        sale_id, "Devolución", "Devolución de mercancía", total=5000.0)
    nota = CreditNoteDetailDialog(services, note_id)
    try:
        assert nota.filas["Monto acreditado"] == "₡5,000.00"
        assert nota.filas["Motivo"] == "Devolución de mercancía"
        assert nota.filas["Estado"] == "PENDIENTE"
    finally:
        nota.close()


def test_detalle_no_encontrado_no_falla():
    from modules.reports.detail_dialogs import (
        CreditNoteDetailDialog,
        CreditPaymentDetailDialog,
        ExpenseDetailDialog,
        SaleDetailDialog,
    )

    db = _db()
    services = _services(db)
    for clase in (SaleDetailDialog, ExpenseDetailDialog,
                  CreditPaymentDetailDialog, CreditNoteDetailDialog):
        dialog = clase(services, 999999)
        try:
            assert dialog is not None
        finally:
            dialog.close()


# ---------- doble clic ----------

def test_movimientos_doble_clic_abre_el_detalle_correcto(monkeypatch):
    from modules.reports import reports_widget as rw

    llamadas: list[tuple[str, int]] = []

    class _Falso:
        def __init__(self, services, item_id, parent=None):
            llamadas.append((type(self).__name__, int(item_id)))

        def exec(self):
            return 0

    for nombre in ("SaleDetailDialog", "ExpenseDetailDialog",
                   "CreditPaymentDetailDialog", "CreditNoteDetailDialog"):
        monkeypatch.setattr(rw, nombre, type(nombre, (_Falso,), {}))

    movimientos = [
        {"tipo": "VENTA", "id": 11, "detalle": "Cliente", "metodo": "Tarjeta",
         "monto": 1000.0, "fecha": "2026-09-25 10:00:00"},
        {"tipo": "GASTO", "id": 12, "detalle": "Renta", "metodo": "Efectivo",
         "monto": 500.0, "fecha": "2026-09-25 09:00:00"},
        {"tipo": "ABONO", "id": 13, "detalle": "Cliente — V-1",
         "metodo": "Sinpe", "monto": 250.0, "fecha": "2026-09-25 08:00:00"},
        {"tipo": "NOTA", "id": 14, "detalle": "NC-00001", "metodo": "nota crédito",
         "monto": -100.0, "fecha": "2026-09-25 07:00:00"},
    ]
    dialog = rw.MovimientosDiaDialog("2026-09-25", movimientos, {})
    try:
        for row in range(len(movimientos)):
            dialog._table.setCurrentCell(row, 0)
            dialog._abrir_detalle()
    finally:
        dialog.close()

    assert [nombre for nombre, _ in llamadas] == [
        "SaleDetailDialog", "ExpenseDetailDialog",
        "CreditPaymentDetailDialog", "CreditNoteDetailDialog"]
    assert [item_id for _, item_id in llamadas] == [11, 12, 13, 14]


def test_historial_ventas_doble_clic_abre_el_detalle(monkeypatch):
    from modules.reports import reports_widget as rw

    db = _db()
    services = _services(db)
    _, sale_id = _seed_sale(db, total=10000.0)
    widget = rw.ReportsWidget(services)
    llamadas: list[int] = []

    class _Falso:
        def __init__(self, services_, item_id, parent=None):
            llamadas.append(int(item_id))

        def exec(self):
            return 0

    monkeypatch.setattr(rw, "SaleDetailDialog", _Falso)
    try:
        widget.sales_table.setCurrentCell(0, 0)
        assert widget._selected_sale() is not None
        widget._open_sale_detail()
    finally:
        widget.close()
    assert llamadas == [sale_id]


def test_reimprimir_usa_el_flujo_compartido(monkeypatch):
    from modules.reports import reports_widget as rw

    db = _db()
    services = _services(db)
    _, sale_id = _seed_sale(db, total=10000.0)
    widget = rw.ReportsWidget(services)
    llamadas: list[int] = []

    def _falso(parent, services_, item_id):
        llamadas.append(int(item_id))
        return True

    monkeypatch.setattr(rw, "reimprimir_venta", _falso)
    try:
        widget.sales_table.setCurrentCell(0, 0)
        widget._reprint_sale()
    finally:
        widget.close()
    assert llamadas == [sale_id]


# ---------- reporte anual: detalle del mes y gastos por categoría ----------

def _mes_actual() -> tuple[int, int]:
    from datetime import date

    hoy = date.today()
    return hoy.year, hoy.month


def test_detalle_mes_cuadra_con_el_reporte():
    from modules.reports.detail_dialogs import DetalleMesDialog
    from utils.helpers import format_currency

    db = _db()
    services = _services(db)
    year, month = _mes_actual()
    _seed_sale(db, total=25000.0, method="efectivo")
    services["expenses"].add_expense(8000.0, "Renta", "Local", "efectivo",
                                     f"{year:04d}-{month:02d}-15")

    fila = next(r for r in services["reports"].monthly_breakdown(year)
                if r["month"] == month)
    dialog = DetalleMesDialog(services, year, month)
    try:
        assert dialog.filas["Ventas"] == str(fila["sale_count"])
        assert dialog.filas["Ingresos"] == format_currency(fila["ingresos"])
        assert dialog.filas["Gastos"] == format_currency(fila["expenses"])
        assert dialog.filas["Ganancia neta"] == format_currency(fila["net_profit"])
    finally:
        dialog.close()


def test_exportar_csv_mes(tmp_path):
    import csv

    from modules.reports.detail_dialogs import escribir_csv_mes

    db = _db()
    services = _services(db)
    year, month = _mes_actual()
    _seed_sale(db, total=25000.0, method="efectivo", client_name="Ana")
    services["expenses"].add_expense(8000.0, "Renta", "Local", "efectivo",
                                     f"{year:04d}-{month:02d}-15")
    ruta = tmp_path / "mes.csv"
    escribir_csv_mes(ruta, services, year, month)

    with ruta.open(encoding="utf-8-sig", newline="") as handle:
        filas = list(csv.reader(handle))
    assert any(f and f[0] == "Ganancia neta" for f in filas)
    assert any(f and f[0] == "Ventas del mes" for f in filas)
    assert any(f and f[0] == "Gastos del mes" for f in filas)
    texto = ruta.read_text(encoding="utf-8-sig")
    assert "Ana" in texto and "Renta" in texto


def test_gastos_categoria_lista_y_abre_detalle(monkeypatch):
    from modules.reports import detail_dialogs as dd

    db = _db()
    services = _services(db)
    year, _month = _mes_actual()
    for monto, categoria in ((5000.0, "Renta"), (7000.0, "Renta"),
                             (3000.0, "Transporte")):
        services["expenses"].add_expense(
            monto, categoria, "Prueba", "efectivo", f"{year:04d}-02-10")

    llamadas: list[int] = []

    class _Falso:
        def __init__(self, services_, item_id, parent=None):
            llamadas.append(int(item_id))

        def exec(self):
            return 0

    monkeypatch.setattr(dd, "ExpenseDetailDialog", _Falso)
    dialog = dd.GastosCategoriaDialog(services, year, "Renta")
    try:
        assert dialog._tabla.rowCount() == 2, "solo los de la categoría"
        assert dialog.total == 12000.0
        dialog._tabla.setCurrentCell(0, 0)
        dialog._abrir_detalle()
    finally:
        dialog.close()
    ids = {int(g.id) for g in dialog._gastos}
    assert llamadas and llamadas[0] in ids


def test_doble_clic_mes_anual_abre_detalle(monkeypatch):
    from modules.reports import reports_widget as rw

    db = _db()
    services = _services(db)
    year, month = _mes_actual()
    _seed_sale(db, total=10000.0, method="efectivo")
    widget = rw.ReportsWidget(services)
    llamadas: list[tuple[int, int]] = []

    class _Falso:
        def __init__(self, services_, year_, month_, parent=None):
            llamadas.append((int(year_), int(month_)))

        def exec(self):
            return 0

    monkeypatch.setattr(rw, "DetalleMesDialog", _Falso)
    try:
        widget.year_button.setChecked(True)
        widget.refresh()
        fila = next(row for row, item in enumerate(widget._data["breakdown"])
                    if item["month"] == month)
        widget.monthly_table.setCurrentCell(fila, 0)
        widget._open_month_detail()
    finally:
        widget.close()
    assert llamadas == [(year, month)]


def test_doble_clic_categoria_anual_abre_listado(monkeypatch):
    from modules.reports import reports_widget as rw

    db = _db()
    services = _services(db)
    year, month = _mes_actual()
    services["expenses"].add_expense(4000.0, "Renta", "X", "efectivo",
                                     f"{year:04d}-{month:02d}-05")
    widget = rw.ReportsWidget(services)
    llamadas: list[tuple[int, str]] = []

    class _Falso:
        def __init__(self, services_, year_, category, parent=None):
            llamadas.append((int(year_), str(category)))

        def exec(self):
            return 0

    monkeypatch.setattr(rw, "GastosCategoriaDialog", _Falso)
    try:
        widget.year_button.setChecked(True)
        widget.refresh()
        fila = next(row for row, item in enumerate(widget._data["categories"])
                    if item["category"] == "Renta")
        widget.category_table.setCurrentCell(fila, 0)
        widget._open_category_detail()
    finally:
        widget.close()
    assert llamadas == [(year, "Renta")]
