"""Envío automático de la factura electrónica al correo del cliente (SMTP).

Diseño:
  - La configuración no secreta (activo, servidor, puerto, seguridad, usuario,
    remitente) vive en `app_config` y es compartida por todas las cajas.
  - La contraseña SMTP NO va a la base compartida: se guarda cifrada con la
    DPAPI de Windows en un archivo local de cada PC (%APPDATA%\\PosLaLoma).
    Así solo el usuario de Windows de esa caja puede descifrarla, igual que el
    resto de secretos de la aplicación.
  - El envío es una función pura (`enviar_factura`): no toca la base ni la UI,
    por lo que puede correr en un hilo sin bloquear el cobro.
  - Solo se admite conexión cifrada (SSL directo o STARTTLS) con verificación
    de certificado.
"""

import re
import smtplib
import socket
import ssl
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid
from pathlib import Path

from utils import secretos

# Claves en app_config (configuración compartida, sin secretos).
KEY_ACTIVO = "email_envio_activo"
KEY_HOST = "smtp_host"
KEY_PORT = "smtp_port"
KEY_SEGURIDAD = "smtp_seguridad"
KEY_USUARIO = "smtp_usuario"
KEY_REMITENTE = "smtp_remitente"

SEGURIDAD_SSL = "ssl"
SEGURIDAD_STARTTLS = "starttls"
SEGURIDADES = (SEGURIDAD_SSL, SEGURIDAD_STARTTLS)
PUERTO_POR_SEGURIDAD = {SEGURIDAD_SSL: 465, SEGURIDAD_STARTTLS: 587}

TIMEOUT_SEGUNDOS = 20
MAX_ADJUNTO_BYTES = 10_000_000

# Un solo correo, sin espacios, comas ni saltos de línea (evita inyección de
# encabezados y envíos a varios destinatarios).
_CORREO_RE = re.compile(r"^[A-Za-z0-9._%+\-']+@[A-Za-z0-9\-]+(\.[A-Za-z0-9\-]+)+$")

NOMBRE_ARCHIVO_SECRETO = "smtp_password.dat"


def correo_valido(valor: str) -> bool:
    """True si es exactamente una dirección de correo razonable."""
    valor = str(valor or "").strip()
    return 0 < len(valor) <= 254 and bool(_CORREO_RE.match(valor))


# ---------- contraseña local (por PC) ----------

def ruta_secreto() -> Path:
    """Archivo local donde se guarda la contraseña SMTP de esta PC."""
    from config import appdata_dir

    return appdata_dir() / NOMBRE_ARCHIVO_SECRETO


def guardar_password(password: str) -> None:
    """Guarda (cifrada con DPAPI) la contraseña SMTP en esta PC."""
    ruta = ruta_secreto()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(secretos.cifrar(str(password or "")), encoding="utf-8")
    try:
        ruta.chmod(0o600)
    except OSError:
        pass


def cargar_password() -> str:
    """Contraseña SMTP de esta PC ("" si no hay o no se puede descifrar)."""
    try:
        ruta = ruta_secreto()
        if not ruta.is_file():
            return ""
        return secretos.descifrar(ruta.read_text(encoding="utf-8").strip())
    except OSError:
        return ""


def hay_password() -> bool:
    return bool(cargar_password())


# ---------- configuración compartida ----------

def _leer(db, key: str, default: str = "") -> str:
    try:
        filas = db.execute_query(
            "SELECT value FROM app_config WHERE key = ?", (key,))
        if filas and filas[0].get("value") is not None:
            return str(filas[0]["value"]).strip()
    except Exception:
        pass
    return default


def _a_puerto(valor, seguridad: str) -> int:
    try:
        puerto = int(str(valor).strip())
        if 0 < puerto <= 65535:
            return puerto
    except (TypeError, ValueError):
        pass
    return PUERTO_POR_SEGURIDAD.get(seguridad, 587)


def cargar_config_correo(db) -> dict:
    """Configuración de envío (incluye la contraseña local de esta PC)."""
    seguridad = _leer(db, KEY_SEGURIDAD, SEGURIDAD_STARTTLS)
    if seguridad not in SEGURIDADES:
        seguridad = SEGURIDAD_STARTTLS
    usuario = _leer(db, KEY_USUARIO)
    return {
        "activo": _leer(db, KEY_ACTIVO, "0") == "1",
        "host": _leer(db, KEY_HOST),
        "port": _a_puerto(_leer(db, KEY_PORT), seguridad),
        "seguridad": seguridad,
        "usuario": usuario,
        "remitente": _leer(db, KEY_REMITENTE) or usuario,
        "password": cargar_password(),
    }


def guardar_config_correo(db, activo: bool, host: str, port, seguridad: str,
                          usuario: str, remitente: str,
                          password: str = "") -> None:
    """Guarda la configuración. Una contraseña vacía conserva la existente."""
    seguridad = seguridad if seguridad in SEGURIDADES else SEGURIDAD_STARTTLS
    valores = {
        KEY_ACTIVO: "1" if activo else "0",
        KEY_HOST: host,
        KEY_PORT: str(_a_puerto(port, seguridad)),
        KEY_SEGURIDAD: seguridad,
        KEY_USUARIO: usuario,
        KEY_REMITENTE: remitente,
    }
    with db.transaction() as connection:
        for key, value in valores.items():
            connection.execute(
                "INSERT OR REPLACE INTO app_config (key, value) VALUES (?, ?)",
                (key, str(value or "").strip()))
        if str(password or ""):
            guardar_password(password)


def config_completa(cfg: dict) -> bool:
    """Hay lo mínimo para conectar y enviar."""
    if not str(cfg.get("host") or "").strip():
        return False
    if not cfg.get("port"):
        return False
    remitente = cfg.get("remitente") or cfg.get("usuario")
    if not correo_valido(remitente):
        return False
    if cfg.get("usuario") and not cfg.get("password"):
        return False
    return True


def motivo_no_envio(cfg: dict, destinatario: str, documentos: dict | None) -> str:
    """Razón por la que NO se enviará el correo ("" si debe enviarse).

    Códigos: "desactivado", "config_incompleta", "no_electronica",
    "sin_correo_cliente".
    """
    if not cfg.get("activo"):
        return "desactivado"
    if not documentos or not documentos.get("xml"):
        return "no_electronica"
    if not correo_valido(destinatario):
        return "sin_correo_cliente"
    if not config_completa(cfg):
        return "config_incompleta"
    return ""


# ---------- mensaje y envío ----------

def _texto_seguro(valor, largo: int = 120) -> str:
    """Una sola línea sin caracteres de control (para asunto y nombres)."""
    limpio = re.sub(r"[\x00-\x1f\x7f]+", " ", str(valor or "")).strip()
    return limpio[:largo]


def construir_mensaje(cfg: dict, company: dict, sale, destinatario: str,
                      adjuntos: list[Path], clave: str = "") -> EmailMessage:
    """Arma el correo con la factura (PDF y XML) adjunta."""
    empresa = _texto_seguro(company.get("company_name"), 80) or "Mueblería La Loma"
    numero = _texto_seguro(getattr(sale, "invoice_number", ""), 40)
    cliente = _texto_seguro(getattr(sale, "client_name", ""), 80)
    remitente = cfg.get("remitente") or cfg.get("usuario")

    msg = EmailMessage()
    msg["Subject"] = f"Factura electrónica {numero} - {empresa}".replace("  ", " ")
    msg["From"] = formataddr((empresa, remitente))
    msg["To"] = destinatario
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=remitente.split("@")[-1])
    contacto = _texto_seguro(company.get("email"), 120)
    if contacto and correo_valido(contacto):
        msg["Reply-To"] = contacto

    saludo = f"Estimado(a) {cliente}," if cliente else "Estimado(a) cliente,"
    lineas = [
        saludo,
        "",
        f"Adjuntamos el PDF y el XML de respaldo de su factura {numero}.",
    ]
    if clave:
        lineas += ["", f"Clave numérica: {_texto_seguro(clave, 60)}"]
    lineas += [
        "",
        "Gracias por su compra.",
        empresa,
    ]
    telefono = _texto_seguro(company.get("phone"), 40)
    if telefono:
        lineas.append(f"Tel. {telefono}")
    msg.set_content("\n".join(lineas))

    for ruta in adjuntos:
        datos = Path(ruta).read_bytes()
        if len(datos) > MAX_ADJUNTO_BYTES:
            raise ValueError(f"El adjunto {Path(ruta).name} es demasiado grande")
        if str(ruta).lower().endswith(".pdf"):
            tipo, subtipo = "application", "pdf"
        else:
            tipo, subtipo = "application", "xml"
        msg.add_attachment(datos, maintype=tipo, subtype=subtipo,
                           filename=Path(ruta).name)
    return msg


def _enviar_mensaje(cfg: dict, msg: EmailMessage) -> None:
    contexto = ssl.create_default_context()
    host, puerto = cfg["host"], int(cfg["port"])
    if cfg.get("seguridad") == SEGURIDAD_SSL:
        servidor = smtplib.SMTP_SSL(host, puerto, timeout=TIMEOUT_SEGUNDOS,
                                    context=contexto)
    else:
        servidor = smtplib.SMTP(host, puerto, timeout=TIMEOUT_SEGUNDOS)
    with servidor:
        if cfg.get("seguridad") != SEGURIDAD_SSL:
            servidor.ehlo()
            servidor.starttls(context=contexto)
            servidor.ehlo()
        if cfg.get("usuario"):
            servidor.login(cfg["usuario"], cfg.get("password", ""))
        servidor.send_message(msg)


def _explicar_error(exc: Exception) -> str:
    """Mensaje claro para la cajera; nunca incluye la contraseña."""
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return ("El servidor de correo rechazó el usuario o la contraseña. "
                "En Gmail use una contraseña de aplicación si su cuenta lo permite.")
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        return "El servidor rechazó el correo del cliente (¿está bien escrito?)."
    if isinstance(exc, smtplib.SMTPSenderRefused):
        return "El servidor rechazó el correo remitente."
    if isinstance(exc, ssl.SSLError):
        return ("No se pudo establecer la conexión segura. Revise el puerto y "
                "el tipo de seguridad (SSL/STARTTLS).")
    if isinstance(exc, (socket.timeout, TimeoutError)):
        return "El servidor de correo tardó demasiado en responder."
    if isinstance(exc, socket.gaierror):
        return "No se encontró el servidor de correo. Revise el nombre del servidor."
    if isinstance(exc, ConnectionRefusedError):
        return "El servidor de correo rechazó la conexión. Revise el puerto."
    if isinstance(exc, OSError):
        return "No hay conexión con el servidor de correo (¿sin internet?)."
    if isinstance(exc, smtplib.SMTPException):
        return f"Error del servidor de correo: {type(exc).__name__}."
    return f"No se pudo enviar el correo: {exc}"


def enviar_factura(cfg: dict, company: dict, sale, destinatario: str,
                   documentos: dict, clave: str = "") -> tuple[bool, str]:
    """Envía PDF+XML al cliente. Nunca lanza: devuelve (ok, mensaje).

    No usa base de datos ni UI: es seguro llamarla desde un hilo.
    """
    if not correo_valido(destinatario):
        return False, "Escriba un correo de destino válido."
    if not config_completa(cfg):
        return False, "Complete servidor, puerto, usuario, contraseña y remitente."
    try:
        adjuntos = []
        for llave in ("pdf", "xml"):
            ruta = documentos.get(llave) if documentos else None
            if not ruta or not Path(ruta).is_file():
                return False, "Faltan archivos de la factura: se requieren el PDF y el XML."
            adjuntos.append(Path(ruta))
        msg = construir_mensaje(cfg, company, sale, destinatario, adjuntos, clave)
        _enviar_mensaje(cfg, msg)
        return True, f"Factura enviada a {destinatario}"
    except Exception as exc:
        return False, _explicar_error(exc)


def enviar_prueba(cfg: dict, company: dict, destinatario: str) -> tuple[bool, str]:
    """Correo de prueba (sin adjuntos) para validar la configuración."""
    if not correo_valido(destinatario):
        return False, "Escriba un correo de destino válido."
    if not config_completa(cfg):
        return False, "Complete servidor, puerto, usuario, contraseña y remitente."
    try:
        empresa = _texto_seguro(company.get("company_name"), 80) or "POS La Loma"
        remitente = cfg.get("remitente") or cfg.get("usuario")
        msg = EmailMessage()
        msg["Subject"] = f"Prueba de correo - {empresa}"
        msg["From"] = formataddr((empresa, remitente))
        msg["To"] = destinatario
        msg["Date"] = formatdate(localtime=True)
        msg["Message-ID"] = make_msgid(domain=remitente.split("@")[-1])
        msg.set_content(
            "Este es un correo de prueba del POS La Loma.\n"
            "Si lo recibió, el envío automático de facturas está bien configurado.")
        _enviar_mensaje(cfg, msg)
        return True, f"Correo de prueba enviado a {destinatario}"
    except Exception as exc:
        return False, _explicar_error(exc)
