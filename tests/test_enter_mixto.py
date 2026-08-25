"""Pruebas: Enter con efectivo insuficiente pasa el faltante a otro método."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt6.QtWidgets import QApplication

app = QApplication([])

from modules.pos.cobro_dialog import CobroDialog

TOTAL = 169500.0
FALTANTE = 114500.0  # 169500 - 55000


def test_enter_insuficiente_switch_mixto():
    dlg = CobroDialog(TOTAL)
    dlg.cash_input.setText("55000")
    assert not dlg.cobrar_btn.isEnabled(), "efectivo insuficiente deshabilita COBRAR"
    dlg.cash_input.returnPressed.emit()
    assert dlg.method == "Mixto", f"debe pasar a Mixto, quedo en {dlg.method}"
    assert dlg.pages.currentIndex() == 1, "debe mostrar la pagina Mixto"
    assert dlg._parse_amount(dlg.mix_amount_a.text()) == 55000.0, "efectivo conservado"
    assert dlg._parse_amount(dlg.mix_amount_b.text()) == FALTANTE, \
        f"faltante pre-llenado: {dlg.mix_amount_b.text()}"
    assert dlg.cobrar_btn.isEnabled(), "con el faltante puesto, COBRAR se habilita"
    assert "Faltan" in dlg.mix_status_label.text() and "114,500" in dlg.mix_status_label.text(), \
        dlg.mix_status_label.text()
    print("[OK] Enter con efectivo insuficiente -> Mixto con faltante pre-llenado")


def test_enter_suficiente_cobra_normal():
    dlg = CobroDialog(TOTAL)
    dlg.cash_input.setText("170000")
    assert dlg.cobrar_btn.isEnabled()
    dlg.cash_input.returnPressed.emit()
    assert dlg.method == "Efectivo", "monto suficiente no debe cambiar a Mixto"
    res = dlg.result()
    assert res["method"] == "Efectivo"
    assert res["cash_received"] == 170000.0
    assert res["change"] == 500.0
    print("[OK] Enter con monto suficiente cobra normal sin pasar a Mixto")


def test_enter_vacio_no_hace_nada():
    dlg = CobroDialog(TOTAL)
    dlg.cash_input.setText("")
    dlg.cash_input.returnPressed.emit()
    assert dlg.method == "Efectivo", "sin monto no debe cambiar a Mixto"
    assert dlg.pages.currentIndex() == 0
    print("[OK] Enter con campo vacio no hace nada")


def test_tarjeta_insuficiente_no_cambia_mixto():
    dlg = CobroDialog(TOTAL)
    dlg._select_method("Tarjeta")
    dlg.cash_input.setText("50000")
    dlg.cash_input.returnPressed.emit()
    assert dlg.method == "Tarjeta", "solo Efectivo dispara el cambio a Mixto"
    assert dlg.pages.currentIndex() == 0
    assert not dlg.cobrar_btn.isEnabled()
    print("[OK] Tarjeta insuficiente no cambia a Mixto (solo Efectivo)")


def test_switch_mixto_y_enter_cobra():
    dlg = CobroDialog(TOTAL)
    dlg.cash_input.setText("55000")
    dlg.cash_input.returnPressed.emit()
    dlg.mix_method_b.setCurrentText("Sinpe")
    dlg.mix_amount_b.returnPressed.emit()
    res = dlg.result()
    assert res["method"] == "Mixto"
    assert res["payment_details"] == [
        {"method": "Efectivo", "amount": 55000.0},
        {"method": "Sinpe", "amount": FALTANTE},
    ], res["payment_details"]
    assert res["cash_received"] == 55000.0
    assert res["change"] == 0.0
    print("[OK] Mixto automatico -> elegir Sinpe + Enter -> cobra completo")


def test_switch_mixto_respecta_moneda_usd():
    dlg = CobroDialog(169500.0, exchange_rate=453.0)
    dlg._set_currency("USD")
    total_usd = dlg.total  # 169500 / 453 = 374.17
    dlg.cash_input.setText("100")
    dlg.cash_input.returnPressed.emit()
    assert dlg.method == "Mixto"
    missing = round(total_usd - 100.0, 2)
    assert abs(dlg._parse_amount(dlg.mix_amount_b.text()) - missing) < 0.01, \
        f"faltante en USD: {dlg.mix_amount_b.text()} (esperado {missing})"
    assert dlg.cobrar_btn.isEnabled()
    print(f"[OK] Mixto automatico respeta moneda USD (faltante {missing})")


if __name__ == "__main__":
    tests = [
        test_enter_insuficiente_switch_mixto,
        test_enter_suficiente_cobra_normal,
        test_enter_vacio_no_hace_nada,
        test_tarjeta_insuficiente_no_cambia_mixto,
        test_switch_mixto_y_enter_cobra,
        test_switch_mixto_respecta_moneda_usd,
    ]
    failed = 0
    for t in tests:
        try:
            t()
        except Exception as e:
            print(f"[FAIL] {t.__name__}: {e}")
            failed += 1
    print(f"\n{'ENTER MIXTO OK' if failed == 0 else f'ENTER MIXTO FAIL: {failed}'}")
