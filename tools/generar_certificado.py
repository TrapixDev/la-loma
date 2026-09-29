"""Genera el certificado del servidor POS (HTTPS) y su clave separada.

Uso recomendado (en la PC servidor, con la IP de la red del negocio):

    python tools/generar_certificado.py --host 192.168.1.10

Salida:
  - %APPDATA%\\PosLaLoma\\certs\\server-cert.pem  (público: se copia a las cajas)
  - %APPDATA%\\PosLaLoma\\certs\\server-key.pem   (privado: NUNCA sale del servidor)

En cada caja, config.ini:
    server_url = https://192.168.1.10:8000
    tls_ca = ruta\\a\\server-cert.pem

Requiere el paquete `cryptography` (solo para generar; el POS no lo necesita
para funcionar, salvo que use actualizaciones firmadas).
"""

import argparse
import ipaddress
import os
import socket
import sys
from datetime import datetime, timedelta
from pathlib import Path


def _certs_dir() -> Path:
    base = Path(os.environ.get("APPDATA", str(Path.home())))
    return base / "PosLaLoma" / "certs"


def _restringir_clave(ruta: Path) -> None:
    """Best-effort: deja la clave solo para el usuario, SYSTEM y admins."""
    try:
        os.chmod(ruta, 0o600)
    except OSError:
        pass
    if sys.platform != "win32":
        return
    try:
        import subprocess

        usuario = os.environ.get("USERNAME") or ""
        dominio = os.environ.get("USERDOMAIN") or ""
        cuenta = f"{dominio}\\{usuario}" if usuario and dominio else usuario
        if not cuenta:
            return
        args = [str(ruta), "/inheritance:r", "/grant:r", f"{cuenta}:F",
                "/grant:r", "*S-1-5-18:F", "/grant:r", "*S-1-5-32-544:F",
                "/remove:g", "*S-1-5-11", "*S-1-5-32-545", "*S-1-1-0"]
        subprocess.run(["icacls", *args], capture_output=True, text=True,
                       timeout=30,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        pass


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
    parser.add_argument("--out", default=str(_certs_dir() / "server-cert.pem"),
                        help="Certificado público de salida (se copia a las cajas)")
    parser.add_argument("--key-out", default="",
                        help="Clave privada de salida (por defecto, junto al "
                             "certificado como server-key.pem)")
    args = parser.parse_args()

    destino = Path(args.out)
    clave_destino = Path(args.key_out) if args.key_out else (
        destino.with_name(destino.stem.replace("-cert", "") + "-key.pem")
        if destino.stem.endswith("-cert") else destino.with_name(
            destino.stem + "-key.pem"))
    if destino.resolve() == clave_destino.resolve():
        print("El certificado y la clave no pueden ir en el mismo archivo.")
        return 1

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
        # No es una CA: solo sirve para este servidor. Las cajas confían en
        # este certificado concreto (tls_ca), no en una autoridad.
        .add_extension(x509.BasicConstraints(ca=False, path_length=None),
                       critical=True)
        .add_extension(x509.ExtendedKeyUsage(
            [x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .sign(key, hashes.SHA256())
    )

    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(certificado.public_bytes(serialization.Encoding.PEM))
    clave_destino.write_bytes(key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ))
    _restringir_clave(clave_destino)

    print(f"Certificado público: {destino}")
    print(f"Clave privada:       {clave_destino}")
    print(f"Válido para: {args.host}, localhost, 127.0.0.1 ({args.dias} días)")
    print()
    print("En el SERVIDOR: reinicie el POS; usará HTTPS automáticamente.")
    print("En cada CAJA copie SOLO el certificado y configure:")
    print(f"    server_url = https://{args.host}:8000")
    print(f"    tls_ca = {destino}")
    print()
    print("NUNCA copie la clave privada (server-key.pem) a las cajas.")
    print("Dentro de la red del negocio puede usar tls_insecure = 1 "
          "(menos seguro).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
