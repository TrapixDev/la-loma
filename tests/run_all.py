"""Ejecuta todos los tests del proyecto:  python -m tests.run_all

Corre pytest por cada archivo en un subproceso aislado (Qt y BD temporales).
Cubre tanto archivos estilo script como estilo pytest. Código de salida 0 si
todo pasa.
"""

import os
import subprocess
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
TESTS_DIR = Path(__file__).resolve().parent

TEST_FILES = sorted(
    p.name for p in TESTS_DIR.glob("test_*.py") if p.name != "run_all.py"
)


def main() -> int:
    env = dict(os.environ)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    env["PYTHONIOENCODING"] = "utf-8"
    (TESTS_DIR / ".tmp").mkdir(parents=True, exist_ok=True)

    check = subprocess.run(
        [sys.executable, "-c", "import pytest"],
        cwd=str(PROJECT_DIR), env=env,
    )
    if check.returncode != 0:
        print("ERROR: pytest no está instalado. Instale las dependencias de "
              "desarrollo: pip install -r requirements-dev.txt")
        return 1

    if not TEST_FILES:
        print("No se encontraron archivos test_*.py en tests/")
        return 1

    fallidos = []
    for nombre in TEST_FILES:
        print(f"\n===== {nombre} =====")
        result = subprocess.run(
            [sys.executable, "-m", "pytest", str(TESTS_DIR / nombre), "-q",
             "-p", "no:cacheprovider"],
            cwd=str(PROJECT_DIR),
            env=env,
            timeout=300,
        )
        if result.returncode != 0:
            fallidos.append(nombre)

    print("\n" + "=" * 50)
    if fallidos:
        print(f"RESULTADO: {len(fallidos)} archivo(s) con fallos: "
              f"{', '.join(fallidos)}")
        return 1
    print(f"RESULTADO: todos los tests pasaron ({len(TEST_FILES)} archivos)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
