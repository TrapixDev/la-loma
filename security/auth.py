"""Seguridad del POS: hash de PIN, tokens y bloqueo por intentos.

El PIN nunca se guarda ni se transmite en texto plano: solo su hash PBKDF2
con sal aleatoria. El hash y la verificación se hacen en el servidor; el
cliente solo envía el PIN durante el ingreso.
"""

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta

PBKDF2_ITERATIONS = 200_000
PIN_MIN = 4
PIN_MAX = 6


def valid_pin(pin: str) -> bool:
    """Valida que el PIN tenga entre 4 y 6 dígitos."""
    return isinstance(pin, str) and pin.isdigit() and PIN_MIN <= len(pin) <= PIN_MAX


def hash_pin(pin: str) -> tuple[str, str]:
    """Devuelve (salt_hex, hash_hex) del PIN con sal aleatoria."""
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", pin.encode("utf-8"), salt, PBKDF2_ITERATIONS
    )
    return salt.hex(), digest.hex()


def verify_pin(pin: str, salt_hex: str, hash_hex: str) -> bool:
    """Verifica el PIN contra su sal y hash guardados."""
    try:
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
    except ValueError:
        return False
    digest = hashlib.pbkdf2_hmac(
        "sha256", pin.encode("utf-8"), salt, PBKDF2_ITERATIONS
    )
    return hmac.compare_digest(digest, expected)


def new_token() -> str:
    """Genera un token de sesión seguro."""
    return secrets.token_hex(32)


def utcnow() -> datetime:
    return datetime.utcnow()


def lockout_deadline(attempts: int, lockout_minutes: int) -> datetime | None:
    """Devuelve cuándo se desbloquea el usuario si alcanzó el máximo de intentos."""
    if attempts >= 5:
        return utcnow() + timedelta(minutes=lockout_minutes)
    return None


def remaining_minutes(deadline_iso: str | None) -> int:
    """Minutos restantes de bloqueo, 0 si ya expiró o no existe fecha."""
    if not deadline_iso:
        return 0
    try:
        deadline = datetime.fromisoformat(deadline_iso)
    except ValueError:
        return 0
    remaining = deadline - utcnow()
    return max(0, int(remaining.total_seconds() // 60) + 1)
