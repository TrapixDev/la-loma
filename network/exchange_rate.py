"""Obtención del tipo de cambio USD↔CRC desde una API pública.

Utiliza la API gratuita de exchangerate-api.com (sin llave ni registro).
Si falla, devuelve None para que el sistema use el último valor guardado.
"""

import json
import urllib.error
import urllib.request
from datetime import datetime

_API_URL = "https://open.er-api.com/v6/latest/USD"


def fetch_exchange_rate() -> float | None:
    """Obtiene el tipo de cambio (CRC por USD) desde la API.

    Returns:
        Tipo de cambio como float, o None si no se pudo obtener.
    """
    try:
        req = urllib.request.Request(
            _API_URL,
            headers={"User-Agent": "POS-LaLoma/1.0", "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())

        if not isinstance(data, dict):
            return None
        rates = data.get("rates")
        if not isinstance(rates, dict):
            return None
        crc = rates.get("CRC")
        if crc is None:
            return None
        value = float(crc)
        return value if value > 0 else None

    except (urllib.error.URLError, OSError, json.JSONDecodeError,
            KeyError, ValueError, TypeError):
        return None


def get_exchange_rate_from_db(db_manager) -> tuple[float, str]:
    """Obtiene el tipo de cambio actual de la base de datos.

    Returns:
        Tupla de (tipo_de_change, fecha_ultima_actualizacion)
    """
    row = db_manager.execute_query(
        "SELECT value FROM app_config WHERE key = 'exchange_rate'"
    )
    rate = float(row[0]["value"]) if row else 520.0

    date_row = db_manager.execute_query(
        "SELECT value FROM app_config WHERE key = 'exchange_rate_date'"
    )
    date_str = date_row[0]["value"] if date_row else ""

    return rate, date_str


def save_exchange_rate(db_manager, rate: float) -> None:
    """Guarda el tipo de cambio y la fecha de actualización."""
    db_manager.execute_update(
        "INSERT OR REPLACE INTO app_config (key, value) VALUES ('exchange_rate', ?)",
        (str(rate),),
    )
    db_manager.execute_update(
        "INSERT OR REPLACE INTO app_config (key, value) VALUES ('exchange_rate_date', ?)",
        (datetime.now().strftime("%Y-%m-%d %H:%M"),),
    )


def update_exchange_rate(db_manager) -> tuple[float, str, bool]:
    """Intenta actualizar el tipo de cambio desde la API.

    Returns:
        Tupla de (tipo_de_cambio, fecha_ultima_actualizacion, se_actualizo).
        se_actualizo es True si la API respondió un valor nuevo.
        Si la API falla, devuelve el último valor guardado con False.
    """
    new_rate = fetch_exchange_rate()
    if new_rate is not None and new_rate > 0:
        save_exchange_rate(db_manager, new_rate)
        rate, date_str = get_exchange_rate_from_db(db_manager)
        return rate, date_str, True
    rate, date_str = get_exchange_rate_from_db(db_manager)
    return rate, date_str, False
