"""Cifrado de secretos en reposo con la DPAPI de Windows.

Las credenciales fiscales (usuario/clave del proveedor FE) nunca deben quedar
en texto plano dentro de la base de datos. Este módulo las cifra con la
Windows Data Protection API, que usa las credenciales del usuario de Windows
que ejecuta la aplicación (no hace falta guardar ninguna clave maestra).

Formato del valor cifrado: ``dpapi1:<base64>``. Todo lo que no empiece con ese
prefijo se considera texto plano (compatibilidad con datos previos) y se migra
al arrancar el servidor.
"""

import base64
import ctypes
import sys
from ctypes import wintypes

PREFIX = "dpapi1:"
SECRET_KEYS = ("password", "pin")

_IS_WINDOWS = sys.platform == "win32"


class _DataBlob(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_char)),
    ]


def disponible() -> bool:
    """True si la DPAPI está disponible (Windows)."""
    return _IS_WINDOWS


def es_cifrado(valor: str) -> bool:
    """True si el valor ya está cifrado por este módulo."""
    return isinstance(valor, str) and valor.startswith(PREFIX)


def _blob_desde(data: bytes) -> tuple[_DataBlob, ctypes.Array]:
    buffer = ctypes.create_string_buffer(data, len(data))
    blob = _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))
    return blob, buffer


def _bytes_desde(blob: _DataBlob) -> bytes:
    return ctypes.string_at(blob.pbData, blob.cbData)


def _configurar_api() -> tuple:
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    crypt32.CryptProtectData.argtypes = [
        ctypes.POINTER(_DataBlob), wintypes.LPCWSTR, ctypes.POINTER(_DataBlob),
        ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD,
        ctypes.POINTER(_DataBlob),
    ]
    crypt32.CryptProtectData.restype = wintypes.BOOL
    crypt32.CryptUnprotectData.argtypes = [
        ctypes.POINTER(_DataBlob), ctypes.POINTER(wintypes.LPWSTR),
        ctypes.POINTER(_DataBlob), ctypes.c_void_p, ctypes.c_void_p,
        wintypes.DWORD, ctypes.POINTER(_DataBlob),
    ]
    crypt32.CryptUnprotectData.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [wintypes.HLOCAL]
    kernel32.LocalFree.restype = wintypes.HLOCAL
    return crypt32, kernel32


def cifrar(texto: str) -> str:
    """Cifra un texto con DPAPI. Si ya está cifrado o está vacío, lo devuelve igual."""
    if not texto or es_cifrado(texto):
        return texto
    if not _IS_WINDOWS:
        return texto
    crypt32, kernel32 = _configurar_api()
    blob, _buffer = _blob_desde(texto.encode("utf-8"))
    salida = _DataBlob()
    ok = crypt32.CryptProtectData(
        ctypes.byref(blob), "PosLaLoma", None, None, None, 0,
        ctypes.byref(salida))
    if not ok:
        raise OSError("No se pudo cifrar el dato con DPAPI")
    try:
        cifrado = _bytes_desde(salida)
    finally:
        kernel32.LocalFree(salida.pbData)
    return PREFIX + base64.b64encode(cifrado).decode("ascii")


def descifrar(valor: str) -> str:
    """Descifra un valor DPAPI. Devuelve el texto plano o "" si no se puede."""
    if not valor or not es_cifrado(valor):
        return valor
    if not _IS_WINDOWS:
        return ""
    crypt32, kernel32 = _configurar_api()
    try:
        data = base64.b64decode(valor[len(PREFIX):], validate=True)
    except (ValueError, TypeError):
        return ""
    blob, _buffer = _blob_desde(data)
    salida = _DataBlob()
    ok = crypt32.CryptUnprotectData(
        ctypes.byref(blob), None, None, None, None, 0, ctypes.byref(salida))
    if not ok:
        return ""
    try:
        plano = _bytes_desde(salida)
    finally:
        kernel32.LocalFree(salida.pbData)
    try:
        return plano.decode("utf-8")
    except UnicodeDecodeError:
        return ""


def cifrar_campos(config: dict) -> dict:
    """Devuelve una copia del dict con los campos secretos cifrados."""
    resultado = dict(config)
    for key in SECRET_KEYS:
        if key in resultado:
            resultado[key] = cifrar(str(resultado[key] or ""))
    return resultado


def descifrar_campos(config: dict) -> dict:
    """Devuelve una copia del dict con los campos secretos en texto plano."""
    resultado = dict(config)
    for key in SECRET_KEYS:
        if key in resultado:
            resultado[key] = descifrar(str(resultado[key] or ""))
    return resultado


def migrar_secretos_en_db(db) -> int:
    """Recifra secretos que quedaron en texto plano. Devuelve cuántos migró.

    Acepta cualquier objeto con ``execute_query``/``execute_update`` (el
    DatabaseManager local o el remoto). Es tolerante a errores: si la tabla no
    existe o no se puede escribir, no altera el arranque.
    """
    migrados = 0
    try:
        filas = db.execute_query(
            "SELECT * FROM hacienda_config WHERE id = 1") or []
    except Exception:
        return 0
    if filas:
        fila = {str(k): v for k, v in filas[0].items()}
        cambios = {}
        for key in SECRET_KEYS:
            actual = str(fila.get(key) or "")
            if actual and not es_cifrado(actual):
                cambios[key] = cifrar(actual)
        if cambios:
            try:
                columnas = ", ".join(f"{col} = ?" for col in cambios)
                db.execute_update(
                    f"UPDATE hacienda_config SET {columnas} WHERE id = 1",
                    tuple(cambios.values()))
                migrados += len(cambios)
            except Exception:
                pass
    try:
        filas = db.execute_query(
            "SELECT key, value FROM hacienda_config WHERE key IN (?, ?)",
            tuple(SECRET_KEYS)) or []
    except Exception:
        return migrados
    for fila in filas:
        key = str(fila.get("key") or "")
        actual = str(fila.get("value") or "")
        if key in SECRET_KEYS and actual and not es_cifrado(actual):
            try:
                db.execute_update(
                    "UPDATE hacienda_config SET value = ? WHERE key = ?",
                    (cifrar(actual), key))
                migrados += 1
            except Exception:
                continue
    return migrados
