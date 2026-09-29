"""Firma un setup de actualización con la clave privada Ed25519.

Uso (en la PC del desarrollador, después de compilar):

    python tools/firmar_setup.py dist\\PosLaLoma_Setup_1.0.3.exe
    python tools/firmar_setup.py setup.exe --key ruta\\update-signing.key

Genera `<setup>.exe.sig` con la firma en base64; el servidor la publica en
/api/update/info y cada caja la verifica con `update_public_key`.
"""

import argparse
import base64
import os
import sys
from pathlib import Path


def _clave_por_defecto() -> Path:
    base = Path(os.environ.get("APPDATA", str(Path.home())))
    return base / "PosLaLoma" / "updates" / "update-signing.key"


def main() -> int:
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PrivateKey,
        )
    except ImportError:
        print("Falta el paquete 'cryptography'.")
        print("    python -m pip install cryptography")
        return 1

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("setup", help="Archivo .exe del instalador")
    parser.add_argument("--key", default=str(_clave_por_defecto()),
                        help="Clave privada Ed25519 (por defecto la generada "
                             "por tools/generar_claves_update.py)")
    args = parser.parse_args()

    setup = Path(args.setup)
    if not setup.is_file() or setup.suffix.lower() != ".exe":
        print("El setup indicado no existe o no es un .exe.")
        return 1
    clave_ruta = Path(args.key)
    if not clave_ruta.is_file():
        print(f"No se encontró la clave privada: {clave_ruta}")
        print("Genérela primero con tools/generar_claves_update.py")
        return 1

    clave = serialization.load_pem_private_key(clave_ruta.read_bytes(), None)
    firma = clave.sign(setup.read_bytes())
    destino = setup.with_name(setup.name + ".sig")
    destino.write_text(base64.b64encode(firma).decode("ascii") + "\n",
                       encoding="utf-8")
    print(f"Firma generada: {destino}")
    print("Copie el .exe y el .sig a la carpeta updates del servidor.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
