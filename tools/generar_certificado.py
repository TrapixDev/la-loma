"""Genera un certificado autofirmado para el servidor POS (HTTPS opcional).

Uso recomendado (en la PC servidor, con la IP de la red del negocio):

    python tools/generar_certificado.py --host 192.168.1.10

El archivo se guarda en %APPDATA%\\PosLaLoma\\certs\\server.pem y el servidor
lo usa automáticamente al arrancar (TLS_CERT en config.py). Las estaciones
deben apuntar a esa ruta con tls_ca en su config.ini o usar tls_insecure = 1
solo dentro de la red local.

Requiere el paquete `cryptography` (solo para generar el certificado; el POS
no lo necesita para funcionar).
"""

import argparse
import ipaddress
import os
import socket
import sys
from datetime import datetime, timedelta
from pathlib import Path


def _salida_por_defecto() -> Path:
    base = Path(os.environ.get("APPDATA", str(Path.home())))
    return base / "PosLaLoma" / "certs" / "server.pem"


def main() -> int:
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID
    except ImportError:
        print("Falta el paquete 'cryptography'.")
        print("Instálelo solo para generar el certificado:")
        print("    python -m pip install cryptography")
        return 1

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=socket.gethostname(),
                        help="Nombre o IP del servidor (la que usan las cajas)")
    parser.add_argument("--dias", type=int, default=3650,
                        help="Días de vigencia (por defecto 10 años)")
    parser.add_argument("--out", default=str(_salida_por_defecto()),
                        help="Ruta del PEM de salida (clave + certificado)")
    args = parser.parse_args()

    nombres = [x509.DNSName(args.host)]
    try:
        nombres.append(x509.IPAddress(ipaddress.ip_address(args.host)))
    except ValueError:
        pass
    nombres.append(x509.DNSName("localhost"))
    nombres.append(x509.IPAddress(ipaddress.ip_address("127.0.0.1")))

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, args.host),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "POS La Loma"),
    ])
    ahora = datetime.utcnow()
    certificado = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(ahora - timedelta(minutes=5))
        .not_valid_after(ahora + timedelta(days=args.dias))
        .add_extension(x509.SubjectAlternativeName(nombres), critical=False)
        .add_extension(x509.BasicConstraints(ca=True, path_length=None),
                       critical=True)
        .sign(key, hashes.SHA256())
    )

    destino = Path(args.out)
    destino.parent.mkdir(parents=True, exist_ok=True)
    pem = (
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
        + certificado.public_bytes(serialization.Encoding.PEM)
    )
    destino.write_bytes(pem)
    try:
        os.chmod(destino, 0o600)
    except OSError:
        pass

    print(f"Certificado generado: {destino}")
    print(f"Válido para: {args.host}, localhost, 127.0.0.1 ({args.dias} días)")
    print()
    print("En el SERVIDOR: reinicie el POS; usará HTTPS automáticamente.")
    print("En cada CAJA (config.ini):")
    print(f"    server_url = https://{args.host}:8000")
    print(f"    tls_ca = {destino}")
    print("o, dentro de la red del negocio, tls_insecure = 1 (menos seguro).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
