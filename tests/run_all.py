"""Ejecuta todos los tests del proyecto:  python -m tests.run_all

Cada test corre en un subproceso aislado (Qt, BD temporal y servidor propio).
Código de salida 0 si todo pasa.
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

if not TEST_FILES:
    print("No se encontraron archivos test_*.py en tests/")
    raise SystemExit(1)


def main() -> int:
    env = dict(os.environ)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    env["PYTHONIOENCODING"] = "utf-8"
    (TESTS_DIR / ".tmp").mkdir(parents=True, exist_ok=True)

    fallidos = []
    for nombre in TEST_FILES:
        print(f"\n===== {nombre} =====")
        result = subprocess.run(
            [sys.executable, str(TESTS_DIR / nombre)],
            cwd=str(PROJECT_DIR),
            env=env,
            timeout=300,
        )
        if result.returncode != 0:
            fallidos.append(nombre)

    print("\n" + "=" * 50)
    if fallidos:
        print(f"RESULTADO: {len(fallidos)} archivo(s) con fallos: {', '.join(fallidos)}")
        return 1
    print(f"RESULTADO: todos los tests pasaron ({len(TEST_FILES)} archivos)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
