"""Certificado del servidor y contextos TLS compartidos por la red del POS."""

import ssl
from pathlib import Path
from urllib.parse import urlparse

from config import Config

LOCAL_HOSTS = ("", "127.0.0.1", "localhost", "::1")


def certificado_efectivo() -> tuple[Path | None, Path | None, bool]:
    """(certificado, clave, es_heredado) del servidor.

    Formato nuevo: certificado y clave en archivos separados. Compatibilidad:
    si el certificado configurado no existe pero hay un `server.pem` antiguo
    (clave + certificado juntos) se usa ese y se marca `es_heredado`.
    """
    cert = Path(Config.TLS_CERT) if Config.TLS_CERT else None
    key = Path(Config.TLS_KEY) if Config.TLS_KEY else None
    if cert is not None and cert.is_file():
        clave = key if (key is not None and key.is_file()) else None
        return cert, clave, False
    if cert is not None:
        heredado = cert.parent / "server.pem"
        if heredado.is_file():
            return heredado, None, True
    return None, None, False


def contexto_cliente(url: str) -> ssl.SSLContext | None:
    """Contexto TLS para una URL https; None para http.

    Si hay `tls_ca` configurada y no se puede leer, falla (no continúa sin
    validar el certificado). `tls_insecure = 1` desactiva la validación y se
    mantiene solo para compatibilidad dentro de la red del negocio.
    """
    if not str(url or "").lower().startswith("https"):
        return None
    if Config.TLS_INSECURE:
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        return context
    cafile = Config.TLS_CA or None
    try:
        return ssl.create_default_context(cafile=cafile)
    except (OSError, ssl.SSLError) as exc:
        raise ssl.SSLError(
            f"No se pudo cargar la CA configurada ({cafile or 'del sistema'}): "
            f"{exc}") from exc


def url_insegura(url: str) -> str:
    """Mensaje si la URL usa HTTP hacia otra PC (sin cifrar), o "" si está bien."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return ""
    host = (parsed.hostname or "").lower()
    if host in LOCAL_HOSTS or parsed.scheme.lower() == "https":
        return ""
    if Config.PERMITIR_HTTP_INSECURO:
        return ""
    return ("Esta caja se conecta al servidor por HTTP (sin cifrar) y el PIN "
            "y la sesión viajarían a la vista de la red.\n\n"
            "Genere el certificado en la PC servidor "
            "(python tools\\generar_certificado.py), copie server-cert.pem a "
            "esta PC y configure en config.ini:\n"
            "    server_url = https://IP-DEL-SERVIDOR:8000\n"
            "    tls_ca = ruta\\a\\server-cert.pem\n\n"
            "Solo para una red de confianza y de forma temporal puede poner "
            "permitir_http = 1 en config.ini.")
