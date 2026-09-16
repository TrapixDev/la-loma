"""ACLs NTFS: endurecimiento de las carpetas de datos del POS."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_DIR = str(Path(__file__).resolve().parents[1])
sys.path.insert(0, PROJECT_DIR)
os.chdir(PROJECT_DIR)

from utils import seguridad

TMP = Path(PROJECT_DIR) / "tests" / ".tmp" / "acl_pos"


def _icacls(ruta: Path) -> str:
    result = subprocess.run(["icacls", str(ruta)], capture_output=True,
                            text=True, timeout=30)
    return result.stdout


@pytest.mark.skipif(not seguridad.disponible(), reason="Requiere Windows")
def test_endurecer_quita_herencia():
    if TMP.exists():
        subprocess.run(["icacls", str(TMP), "/reset", "/t"], capture_output=True)
        import shutil
        shutil.rmtree(TMP, ignore_errors=True)
    TMP.mkdir(parents=True, exist_ok=True)
    (TMP / "pos.db").write_text("datos", encoding="utf-8")

    antes = _icacls(TMP)
    assert "(I)" in antes, "La carpeta temporal debería heredar permisos"

    assert seguridad.endurecer_carpeta(TMP) is True

    despues = _icacls(TMP)
    assert "(I)" not in despues, "La herencia debe quedar quitada"
    usuario = seguridad._usuario_actual()
    assert usuario.lower() in despues.lower()

    # Idempotente
    assert seguridad.endurecer_carpeta(TMP) is True


def test_rutas_no_aplicables(tmp_path):
    assert seguridad.es_ruta_de_red(r"\\SERVIDOR\documentos") is True
    assert seguridad.es_ruta_de_red(str(tmp_path)) is False
    assert seguridad.endurecer_carpeta(r"\\SERVIDOR\no-existe") is False
    assert seguridad.endurecer_carpeta(tmp_path / "no-existe") is False
