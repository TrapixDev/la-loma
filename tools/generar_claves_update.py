"""Genera el par de llaves Ed25519 para firmar las actualizaciones del POS.

Uso (en la PC del desarrollador, una sola vez):

    python tools/generar_claves_update.py

Escribe la clave privada en %APPDATA%\\PosLaLoma\\updates\\update-signing.key
(NO la comparta ni la suba al repositorio) e imprime la clave pública para
ponerla en el config.ini de cada caja o en config.py:

    update_public_key = <base64>
"""

import os
import sys
from pathlib import Path


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

    base = Path(os.environ.get("APPDATA", str(Path.home())))
    carpeta = base / "PosLaLoma" / "updates"
    carpeta.mkdir(parents=True, exist_ok=True)
    destino = carpeta / "update-signing.key"

    if destino.is_file():
        print(f"Ya existe una clave de firma: {destino}")
        print("Borre el archivo solo si quiere reemplazarla (habría que "
              "re-firmar los setups y cambiar update_public_key en las cajas).")
        return 1

    clave = Ed25519PrivateKey.generate()
    destino.write_bytes(clave.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ))
    try:
        os.chmod(destino, 0o600)
    except OSError:
        pass
    publica = clave.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    import base64

    print(f"Clave privada (NO compartir): {destino}")
    print()
    print("Clave pública (ponga esto en cada caja, config.ini):")
    print(f"update_public_key = {base64.b64encode(publica).decode('ascii')}")
    print()
    print("Firme cada setup antes de publicarlo:")
    print("    python tools/firmar_setup.py "
          "dist\\PosLaLoma_Setup_X.Y.Z.exe")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
