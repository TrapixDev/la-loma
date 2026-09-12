"""Servidor central del POS La Loma (solo biblioteca estándar).

Ejecutar en la PC que guarda la base de datos:
    python server.py

El servidor expone una API JSON protegida por token de sesión. Los clientes
(POS) nunca tocan la base de datos directamente: envían consultas
parametrizadas y el servidor valida que sean SELECT/INSERT/UPDATE/DELETE
simples, registra cada operación en el log de auditoría y aplica bloqueo por
intentos fallidos de PIN.
"""

import base64
import hashlib
import json
import re
import shutil
import socket
import sqlite3
import sys
import threading
import time
import zipfile
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from socket import gethostbyname, gethostname

from config import Config
from database.db_manager import DatabaseManager
from database.seed import seed_initial_data
from security import auth
from utils.arranque import asegurar_estructura, migrar_datos_si_vacio

ALLOWED_PREFIXES = ("SELECT", "INSERT INTO", "INSERT OR REPLACE INTO",
                    "UPDATE", "DELETE FROM")
FORBIDDEN_PREFIXES = ("PRAGMA", "ATTACH", "DETACH", "VACUUM", "REINDEX",
                      "ANALYZE", "CREATE", "DROP", "ALTER", "BEGIN",
                      "COMMIT", "ROLLBACK", "EXPLAIN")
AUTH_HEADER = "Authorization"
AUTH_PREFIX = "Bearer "
DETAIL_MAX = 300

# Política de tablas: los clientes solo pueden escribir tablas de negocio.
# `users` queda fuera de todo DML (se administra con /api/login y /api/setup)
# y las tablas contables no admiten DELETE (se anulan, no se borran).
DML_ALLOWED_TABLES = {
    "categories", "products", "clients", "sales", "sale_items", "expenses",
    "expense_categories", "product_images", "counters", "app_config",
    "hacienda_config", "credit_accounts", "credit_payments",
    "credit_payment_images", "credit_notes", "audit_log",
}
DELETE_ALLOWED_TABLES = {
    "categories", "products", "clients", "expenses", "expense_categories",
    "product_images", "credit_accounts", "credit_payments",
    "credit_payment_images", "credit_notes",
}
FORBIDDEN_SELECT_TABLES = {"users", "sqlite_master", "sqlite_schema"}
_TABLE_PATTERN = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)")
RATE_WINDOW_SECONDS = 600
RATE_MAX_ATTEMPTS = 20


def _statement_table(statement: str, keyword: str) -> str:
    """Extrae el nombre de tabla que sigue a una palabra clave."""
    rest = statement[len(keyword):].lstrip()
    if keyword.upper().startswith("INSERT"):
        rest = re.sub(r"^OR\s+[A-Za-z]+\s+", "", rest, flags=re.IGNORECASE)
        rest = re.sub(r"^INTO\s+", "", rest, flags=re.IGNORECASE)
    match = _TABLE_PATTERN.match(rest)
    return match.group(1).lower() if match else ""


def validate_sql(sql: str) -> str:
    """Valida que el SQL sea una sola sentencia permitida y la devuelve limpia.

    Además del tipo de sentencia, aplica una allowlist de tablas: los clientes
    no pueden leer `users` (hashes de PIN) ni escribir fuera de las tablas de
    negocio, y no pueden borrar ventas ni registros contables.
    """
    if not isinstance(sql, str):
        raise ValueError("SQL debe ser texto")
    statement = sql.strip()
    while statement.endswith(";"):
        statement = statement[:-1].rstrip()
    if not statement:
        raise ValueError("SQL vacío")
    if ";" in statement:
        raise ValueError("No se permiten múltiples sentencias")
    upper = statement.upper()
    if any(upper.startswith(word) for word in FORBIDDEN_PREFIXES):
        raise ValueError(f"Operación no permitida: {upper.split()[0]}")
    if not any(upper.startswith(word) for word in ALLOWED_PREFIXES):
        raise ValueError("Solo se permiten SELECT, INSERT, UPDATE o DELETE")

    if upper.startswith("SELECT"):
        tables = {m.lower() for m in re.findall(
            r"\b(?:FROM|JOIN)\s+([A-Za-z_][A-Za-z0-9_]*)",
            statement, re.IGNORECASE)}
        if tables & FORBIDDEN_SELECT_TABLES:
            raise ValueError("Consulta a tabla no permitida")
        return statement

    if upper.startswith("DELETE FROM"):
        table = _statement_table(statement, "DELETE FROM")
        if table not in DELETE_ALLOWED_TABLES:
            raise ValueError(f"DELETE no permitido en '{table or '?'}'")
        return statement

    if upper.startswith("UPDATE"):
        table = _statement_table(statement, "UPDATE")
        if table not in DML_ALLOWED_TABLES:
            raise ValueError(f"UPDATE no permitido en '{table or '?'}'")
        return statement

    table = _statement_table(statement, "INSERT")
    if table not in DML_ALLOWED_TABLES:
        raise ValueError(f"INSERT no permitido en '{table or '?'}'")
    return statement


def _json_safe(value):
    if isinstance(value, bytes):
        return str(value, errors="replace")
    return value


IMAGE_EXTENSIONS = {".png": "image/png", ".jpg": "image/jpeg",
                    ".jpeg": "image/jpeg", ".webp": "image/webp"}


def _validate_image_name(name: str) -> str:
    """Valida un nombre de archivo de imagen (sin rutas ni traversal)."""
    name = name.strip()
    if not re.fullmatch(r"[A-Za-z0-9_\-]+\.[A-Za-z0-9]+", name):
        raise ValueError("Nombre de imagen no permitido")
    if Path(name).suffix.lower() not in IMAGE_EXTENSIONS:
        raise ValueError("Formato de imagen no permitido")
    return name


def _image_magic(data: bytes) -> str | None:
    """Detecta el formato real por los bytes iniciales."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return ".webp"
    return None


def _images_dir(db_path: str) -> Path:
    """Directorio de fotos junto a la base de datos."""
    path = Path(db_path).resolve().parent / "product_images"
    path.mkdir(parents=True, exist_ok=True)
    return path


class POSServer(ThreadingHTTPServer):
    """Servidor HTTP con estado compartido (sesiones y transacciones)."""

    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, server_address, handler, db_path: str, station: str):
        super().__init__(server_address, handler)
        self.db_path = db_path
        self.station = station
        self.sessions: dict[str, dict] = {}
        self.transactions: dict[str, dict] = {}
        self.login_attempts: dict[str, list[float]] = {}
        self.login_failures: dict[str, dict] = {}
        self.state_lock = threading.Lock()
        self.backup_lock = threading.Lock()

    def _open_conn(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=10, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def close_transactions(self) -> None:
        for tx in self.transactions.values():
            try:
                tx["connection"].close()
            except Exception:
                pass
        self.transactions.clear()


class Handler(BaseHTTPRequestHandler):
    server: POSServer

    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):
        status = str(args[1]) if len(args) > 1 else "0"
        if status.isdigit() and int(status) >= 400:
            print(f"[{self.log_date_time_string()}] {self.address_string()} {format % args}")

    # ---------- utilidades ----------

    def _send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            return payload if isinstance(payload, dict) else {}
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}

    def _authenticate(self) -> dict | None:
        header = self.headers.get(AUTH_HEADER, "")
        if not header.startswith(AUTH_PREFIX):
            return None
        token = header[len(AUTH_PREFIX):].strip()
        session = self.server.sessions.get(token)
        if session is None:
            return None
        if auth.utcnow().timestamp() > session["expires"]:
            with self.server.state_lock:
                self.server.sessions.pop(token, None)
            return None
        return session

    def _require_auth(self) -> dict | None:
        session = self._authenticate()
        if session is None:
            self._send_json({"error": "Sesión no válida o expirada"}, 401)
        return session

    def _audit(self, session: dict | None, event: str, detail: str = "") -> None:
        db = DatabaseManager(self.server.db_path)
        try:
            db.audit(
                (session or {}).get("user_id"),
                (session or {}).get("user_name", "sistema"),
                (session or {}).get("station", self.server.station),
                event,
                detail[:DETAIL_MAX],
            )
        finally:
            db.close()

    def _rate_limited(self) -> bool:
        """True si la IP superó el máximo de intentos fallidos recientes."""
        ip = self.client_address[0]
        now = time.time()
        with self.server.state_lock:
            window = [t for t in self.server.login_attempts.get(ip, [])
                      if now - t < RATE_WINDOW_SECONDS]
            self.server.login_attempts[ip] = window
            return len(window) >= RATE_MAX_ATTEMPTS

    def _register_rate_attempt(self) -> None:
        """Cuenta solo intentos fallidos (los logins válidos no gastan cupo)."""
        ip = self.client_address[0]
        now = time.time()
        with self.server.state_lock:
            window = [t for t in self.server.login_attempts.get(ip, [])
                      if now - t < RATE_WINDOW_SECONDS]
            window.append(now)
            self.server.login_attempts[ip] = window

    def _run_query(self, connection: sqlite3.Connection, statement: str,
                   params: tuple) -> dict:
        cursor = connection.execute(statement, params)
        if statement.upper().startswith("SELECT"):
            rows = [
                dict(zip(row.keys(), (_json_safe(value) for value in row)))
                for row in cursor.fetchall()
            ]
            return {"rows": rows}
        connection.commit()
        return {"lastrowid": cursor.lastrowid, "rowcount": cursor.rowcount}

    # ---------- rutas ----------

    def do_GET(self) -> None:
        path = self.path.split("?")[0]
        if path == "/api/health":
            self._health({})
            return
        if path == "/api/update/info":
            self._update_info()
            return
        prefix = "/api/update/download/"
        if path.startswith(prefix):
            self._update_download(path[len(prefix):])
            return
        prefix = "/api/image/"
        if path.startswith(prefix):
            self._image_get(path[len(prefix):])
            return
        self._send_json({"error": "Ruta no encontrada"}, 404)

    def do_POST(self) -> None:
        path = self.path.split("?")[0]
        handlers = {
            "/api/health": self._health,
            "/api/setup": self._setup,
            "/api/login": self._login,
            "/api/logout": self._logout,
            "/api/query": self._query,
            "/api/execute": self._execute,
            "/api/audit": self._audit_event,
            "/api/tx/begin": self._tx_begin,
            "/api/tx/exec": self._tx_exec,
            "/api/tx/commit": self._tx_commit,
            "/api/tx/rollback": self._tx_rollback,
            "/api/image/upload": self._image_upload,
            "/api/image/delete": self._image_delete,
        }
        handler = handlers.get(path)
        if handler is None:
            self._send_json({"error": "Ruta no encontrada"}, 404)
            return
        try:
            handler(self._read_json())
        except Exception as exc:
            self._send_json({"error": f"Error interno: {exc}"}, 500)

    def _health(self, payload: dict) -> None:
        db = DatabaseManager(self.server.db_path)
        try:
            self._send_json({"ok": True, "users": db.count_users()})
        finally:
            db.close()

    # ---------- actualizaciones por red ----------

    def _update_info(self) -> None:
        """Lista los setup disponibles en la carpeta updates del servidor."""
        carpeta = Path(Config.UPDATE_DIR)
        setups = []
        if carpeta.is_dir():
            for archivo in sorted(carpeta.glob("*.exe"), key=lambda p: p.stat().st_mtime,
                                  reverse=True):
                try:
                    setups.append({
                        "filename": archivo.name,
                        "size": archivo.stat().st_size,
                        "md5": hashlib.md5(archivo.read_bytes()).hexdigest(),
                    })
                except OSError:
                    continue
        self._send_json({
            "server_version": Config.APP_VERSION,
            "server_url": f"http://{self.server.server_address[0]}:{self.server.server_address[1]}",
            "setups": setups,
        })

    def _update_download(self, filename: str) -> None:
        """Sirve un setup de la carpeta updates (nombres estrictamente validados)."""
        if not re.fullmatch(r"[A-Za-z0-9_.\-]+\.exe", filename):
            self._send_json({"error": "Archivo no permitido"}, 400)
            return
        carpeta = Path(Config.UPDATE_DIR)
        target = (carpeta / filename).resolve()
        if not target.is_relative_to(carpeta.resolve()) or not target.is_file():
            self._send_json({"error": "Archivo no encontrado"}, 404)
            return
        try:
            data = target.read_bytes()
        except OSError as exc:
            self._send_json({"error": f"No se pudo leer el archivo: {exc}"}, 500)
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Disposition", f'attachment; filename="{target.name}"')
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(data)

    def _setup(self, payload: dict) -> None:
        db = DatabaseManager(self.server.db_path)
        try:
            if db.count_users() > 0:
                self._send_json({"error": "El PIN inicial ya fue creado"}, 400)
                return
            name = str(payload.get("name") or "Administrador").strip()[:80]
            pin = str(payload.get("pin") or "")
            if not auth.valid_pin(pin):
                self._send_json({"error": "El PIN debe tener entre 4 y 6 dígitos"}, 400)
                return
            salt, digest = auth.hash_pin(pin)
            db.execute_insert(
                "INSERT INTO users (name, pin_salt, pin_hash) VALUES (?, ?, ?)",
                (name, salt, digest),
            )
            user = db.execute_query("SELECT * FROM users ORDER BY id DESC LIMIT 1")[0]
            token = self._create_session(user)
            db.audit(user["id"], user["name"], self.server.station, "SETUP",
                     "PIN inicial creado")
            self._send_json({
                "token": token, "user_id": user["id"], "user_name": user["name"],
            })
        finally:
            db.close()

    def _create_session(self, user: sqlite3.Row) -> str:
        token = auth.new_token()
        session = {
            "user_id": user["id"],
            "user_name": user["name"],
            "station": self.server.station,
            "expires": auth.utcnow().timestamp()
            + Config.SESSION_HOURS * 3600,
        }
        with self.server.state_lock:
            self.server.sessions[token] = session
        return token

    def _login(self, payload: dict) -> None:
        ip = self.client_address[0]
        now = time.time()
        with self.server.state_lock:
            record = self.server.login_failures.get(ip)
            if record and record.get("blocked_until") and now < record["blocked_until"]:
                wait = int((record["blocked_until"] - now) // 60) + 1
                self._send_json(
                    {"error": f"Bloqueado por intentos fallidos. Espere {wait} min."}, 423)
                return
        if self._rate_limited():
            self._send_json({"error": "Demasiados intentos. Espere unos minutos."}, 429)
            return
        pin = str(payload.get("pin") or "")
        if not auth.valid_pin(pin):
            self._send_json({"error": "PIN inválido"}, 400)
            return
        db = DatabaseManager(self.server.db_path)
        try:
            users = db.execute_query("SELECT * FROM users WHERE active = 1")
            user = None
            for candidate in users:
                if auth.verify_pin(pin, candidate["pin_salt"], candidate["pin_hash"]):
                    user = candidate
                    break
            if user is None:
                self._register_rate_attempt()
                self._register_login_failure(ip, now)
                db.audit(None, "desconocido", self.server.station,
                         "LOGIN_FAIL", "PIN incorrecto")
                self._send_json({"error": "PIN incorrecto"}, 401)
                return
            if user["locked_until"] and auth.remaining_minutes(user["locked_until"]) > 0:
                minutes = auth.remaining_minutes(user["locked_until"])
                self._send_json(
                    {"error": f"Usuario bloqueado. Intente en {minutes} min."}, 423)
                return
            token = self._create_session(user)
            with self.server.state_lock:
                self.server.login_failures.pop(ip, None)
                self.server.login_attempts.pop(ip, None)
            db.execute_update(
                "UPDATE users SET failed_attempts = 0, locked_until = NULL, "
                "last_login_at = datetime('now', 'localtime') WHERE id = ?",
                (user["id"],),
            )
            db.audit(user["id"], user["name"], self.server.station, "LOGIN_OK")
            self._send_json({
                "token": token,
                "user_id": user["id"],
                "user_name": user["name"],
            })
        finally:
            db.close()

    def _register_login_failure(self, ip: str, now: float) -> None:
        with self.server.state_lock:
            record = self.server.login_failures.setdefault(ip, {"count": 0, "blocked_until": None})
            record["count"] += 1
            if record["count"] >= Config.MAX_LOGIN_ATTEMPTS:
                record["blocked_until"] = now + Config.LOCKOUT_MINUTES * 60
                record["count"] = 0

    def _logout(self, payload: dict) -> None:
        session = self._authenticate()
        if session is not None:
            header = self.headers.get(AUTH_HEADER, "")
            token = header[len(AUTH_PREFIX):].strip()
            with self.server.state_lock:
                self.server.sessions.pop(token, None)
            self._audit(session, "LOGOUT")
        self._send_json({"ok": True})

    def _audit_event(self, payload: dict) -> None:
        """Registra un evento de auditoría enviado por una estación."""
        session = self._require_auth()
        if session is None:
            return
        event = str(payload.get("event") or "EVENTO").strip()[:80] or "EVENTO"
        detail = str(payload.get("detail") or "")
        self._audit(session, event, detail)
        self._send_json({"ok": True})

    def _query(self, payload: dict) -> None:
        session = self._require_auth()
        if session is None:
            return
        try:
            statement = validate_sql(str(payload.get("sql") or ""))
        except ValueError as exc:
            self._send_json({"error": str(exc)}, 400)
            return
        if not statement.upper().startswith("SELECT"):
            self._send_json({"error": "Solo se permiten consultas SELECT"}, 400)
            return
        connection = self.server._open_conn()
        try:
            result = self._run_query(connection, statement, tuple(payload.get("params") or []))
        finally:
            connection.close()
        self._send_json(result)

    def _execute(self, payload: dict) -> None:
        session = self._require_auth()
        if session is None:
            return
        try:
            statement = validate_sql(str(payload.get("sql") or ""))
        except ValueError as exc:
            self._send_json({"error": str(exc)}, 400)
            return
        if statement.upper().startswith("SELECT"):
            self._send_json({"error": "Use /api/query para SELECT"}, 400)
            return
        connection = self.server._open_conn()
        try:
            result = self._run_query(connection, statement, tuple(payload.get("params") or []))
        finally:
            connection.close()
        self._audit(session, "EXECUTE", statement)
        self._send_json(result)

    def _tx_begin(self, payload: dict) -> None:
        session = self._require_auth()
        if session is None:
            return
        self._expire_transactions()
        tx_id = auth.new_token()[:16]
        connection = self.server._open_conn()
        connection.execute("BEGIN")
        with self.server.state_lock:
            self.server.transactions[tx_id] = {
                "connection": connection,
                "session": session,
                "statements": [],
                "last_used": time.time(),
            }
        self._send_json({"tx_id": tx_id})

    def _expire_transactions(self) -> None:
        """Cierra transacciones huérfanas (más de 10 min sin uso) para no
        acumular conexiones abiertas cuando una caja se queda a medias."""
        ahora = time.time()
        with self.server.state_lock:
            viejas = [tx_id for tx_id, tx in self.server.transactions.items()
                      if ahora - tx["last_used"] > 600]
            for tx_id in viejas:
                tx = self.server.transactions.pop(tx_id)
                try:
                    tx["connection"].rollback()
                    tx["connection"].close()
                except Exception:
                    pass

    def _tx_exec(self, payload: dict) -> None:
        session = self._require_auth()
        if session is None:
            return
        tx_id = str(payload.get("tx_id") or "")
        with self.server.state_lock:
            tx = self.server.transactions.get(tx_id)
        if tx is None:
            self._send_json({"error": "Transacción no encontrada"}, 400)
            return
        if time.time() - tx["last_used"] > 600:
            self._send_json({"error": "Transacción expirada"}, 400)
            return
        try:
            statement = validate_sql(str(payload.get("sql") or ""))
            params = tuple(payload.get("params") or [])
        except ValueError as exc:
            self._send_json({"error": str(exc)}, 400)
            return
        try:
            # No se hace commit por sentencia: la transacción solo se confirma
            # en /api/tx/commit para que el bloque sea atómico.
            cursor = tx["connection"].execute(statement, params)
            if statement.upper().startswith("SELECT"):
                rows = [
                    dict(zip(row.keys(), (_json_safe(value) for value in row)))
                    for row in cursor.fetchall()
                ]
                result = {"rows": rows}
            else:
                result = {"lastrowid": cursor.lastrowid, "rowcount": cursor.rowcount}
        except sqlite3.Error as exc:
            self._send_json({"error": f"Error de base de datos: {exc}"}, 400)
            return
        tx["last_used"] = time.time()
        tx["statements"].append(statement)
        self._send_json(result)

    def _tx_commit(self, payload: dict) -> None:
        session = self._require_auth()
        if session is None:
            return
        tx_id = str(payload.get("tx_id") or "")
        with self.server.state_lock:
            tx = self.server.transactions.pop(tx_id, None)
        if tx is None:
            self._send_json({"error": "Transacción no encontrada"}, 400)
            return
        try:
            tx["connection"].commit()
        finally:
            tx["connection"].close()
        self._audit(tx["session"], "TRANSACTION", " | ".join(tx["statements"]))
        self._send_json({"ok": True})

    def _tx_rollback(self, payload: dict) -> None:
        session = self._require_auth()
        if session is None:
            return
        tx_id = str(payload.get("tx_id") or "")
        with self.server.state_lock:
            tx = self.server.transactions.pop(tx_id, None)
        if tx is None:
            self._send_json({"ok": True})
            return
        try:
            tx["connection"].rollback()
        finally:
            tx["connection"].close()
        self._send_json({"ok": True})

    # ---------- imágenes de productos ----------

    def _image_upload(self, payload: dict) -> None:
        session = self._require_auth()
        if session is None:
            return
        name = str(payload.get("name") or "")
        data_b64 = str(payload.get("data") or "")
        try:
            name = _validate_image_name(name)
        except ValueError as exc:
            self._send_json({"error": str(exc)}, 400)
            return
        try:
            data = base64.b64decode(data_b64, validate=True)
        except (ValueError, TypeError):
            self._send_json({"error": "Datos de imagen inválidos"}, 400)
            return
        if not data:
            self._send_json({"error": "Imagen vacía"}, 400)
            return
        if len(data) > Config.MAX_IMAGE_BYTES:
            self._send_json({"error": "La imagen supera el tamaño máximo permitido"}, 400)
            return
        if _image_magic(data) != Path(name).suffix.lower():
            self._send_json({"error": "Formato de imagen no reconocido"}, 400)
            return
        images_dir = _images_dir(self.server.db_path)
        target = (images_dir / name).resolve()
        if not target.is_relative_to(images_dir.resolve()):
            self._send_json({"error": "Nombre de imagen no permitido"}, 400)
            return
        try:
            target.write_bytes(data)
        except OSError as exc:
            self._send_json({"error": f"No se pudo guardar la imagen: {exc}"}, 500)
            return
        self._audit(session, "IMAGE_UPLOAD", name)
        self._send_json({"ok": True, "filename": name})

    def _image_delete(self, payload: dict) -> None:
        session = self._require_auth()
        if session is None:
            return
        name = str(payload.get("filename") or "")
        try:
            name = _validate_image_name(name)
        except ValueError as exc:
            self._send_json({"error": str(exc)}, 400)
            return
        images_dir = _images_dir(self.server.db_path)
        target = (images_dir / name).resolve()
        if not target.is_relative_to(images_dir.resolve()):
            self._send_json({"error": "Nombre de imagen no permitido"}, 400)
            return
        try:
            if target.is_file():
                target.unlink()
        except OSError as exc:
            self._send_json({"error": f"No se pudo borrar la imagen: {exc}"}, 500)
            return
        self._audit(session, "IMAGE_DELETE", name)
        self._send_json({"ok": True})

    def _image_get(self, filename: str) -> None:
        session = self._authenticate()
        if session is None:
            self._send_json({"error": "Sesión no válida o expirada"}, 401)
            return
        try:
            filename = _validate_image_name(filename)
        except ValueError:
            self._send_json({"error": "Imagen no encontrada"}, 404)
            return
        images_dir = _images_dir(self.server.db_path)
        target = (images_dir / filename).resolve()
        if not target.is_relative_to(images_dir.resolve()) or not target.is_file():
            self._send_json({"error": "Imagen no encontrada"}, 404)
            return
        data = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", IMAGE_EXTENSIONS[target.suffix.lower()])
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "public, max-age=31536000, immutable")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(data)


def backup_database(db_path: str, backup_dir: str, keep: int,
                    images_dir: str | None = None) -> None:
    """Copia de seguridad del archivo SQLite (API de backup de sqlite3)
    y de las fotos de productos (zip aparte)."""
    images_dir = images_dir or Config.PRODUCT_IMAGES_DIR
    Path(backup_dir).mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = Path(backup_dir) / f"pos_{stamp}.db"
    source = sqlite3.connect(db_path)
    destination = sqlite3.connect(str(target))
    try:
        with destination:
            source.backup(destination)
    finally:
        source.close()
        destination.close()
    _backup_images(Path(images_dir), Path(backup_dir), stamp)
    backups = sorted(Path(backup_dir).glob("pos_*.db"), key=lambda p: p.stat().st_mtime)
    for old in backups[:-keep]:
        old.unlink(missing_ok=True)
    image_zips = sorted(Path(backup_dir).glob("pos_*_images.zip"),
                        key=lambda p: p.stat().st_mtime)
    for old in image_zips[:-keep]:
        old.unlink(missing_ok=True)


def _backup_images(images_dir: Path, backup_dir: Path, stamp: str) -> None:
    """Empaqueta las fotos de productos en un zip (solo si hay fotos)."""
    if not images_dir.is_dir():
        return
    files = [p for p in images_dir.iterdir() if p.is_file()]
    if not files:
        return
    with zipfile.ZipFile(
            backup_dir / f"pos_{stamp}_images.zip", "w",
            compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, arcname=path.name)


def _lan_ip() -> str:
    """Devuelve la IP local de la red (la que deben usar las estaciones)."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("8.8.8.8", 80))
        return probe.getsockname()[0]
    except OSError:
        return gethostbyname(gethostname())
    finally:
        probe.close()


def start_server(db_path: str = "", host: str = "", port: int | None = None,
                 station: str = "") -> POSServer:
    """Arranca el servidor; usado por server.py y por las pruebas.

    Con port=0 elige un puerto libre (solo pruebas); por defecto usa
    Config.SERVER_PORT.
    """
    db_path = db_path or Config.DB_PATH
    host = host or Config.SERVER_HOST
    if port is None:
        port = Config.SERVER_PORT
    station = station or Config.STATION

    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    asegurar_estructura()
    migrar_datos_si_vacio()
    db = DatabaseManager(db_path)
    db.initialize()
    seed_initial_data(db)
    try:
        backup_database(db_path, Config.BACKUP_DIR, Config.KEEP_BACKUPS)
    except Exception as exc:
        print(f"Advertencia: no se pudo crear el respaldo inicial: {exc}")

    server = POSServer((host, port), Handler, db_path, station)
    if port == 0:
        print(f"Servidor POS La Loma escuchando en 127.0.0.1:{server.server_address[1]}")
        return server
    address = _lan_ip() if host in ("0.0.0.0", "") else host
    print("=" * 64)
    print("  SERVICIO POS - LA LOMA  ACTIVO")
    print(f"  Dirección para las estaciones:  http://{address}:{port}")
    print()
    print("  1) En cada estación (archivo config.py):")
    print(f"     SERVER_URL = 'http://{address}:{port}'")
    print("  2) Ejecute  python main.py  en cada estación.")
    print("  3) MANTENGA ABIERTA ESTA VENTANA mientras se vende.")
    print("  4) Si otras PCs no conectan, permita Python en el Firewall de")
    print("     Windows (acepte el aviso de la primera ejecución).")
    print("=" * 64)
    return server


def backup_loop(server: POSServer) -> None:
    """Respaldos periódicos en segundo plano."""
    while True:
        time.sleep(Config.BACKUP_HOURS * 3600)
        try:
            backup_database(server.db_path, Config.BACKUP_DIR, Config.KEEP_BACKUPS)
        except Exception as exc:
            print(f"Error en respaldo: {exc}")


def main() -> int:
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    try:
        server = start_server()
    except OSError as exc:
        if getattr(exc, "winerror", None) == 10048:
            print(f"El puerto {Config.SERVER_PORT} ya está en uso.")
            print("Si el servidor ya está corriendo en otra ventana, "
                  "no hace falta iniciarlo de nuevo.")
        else:
            print(f"No se pudo iniciar el servidor: {exc}")
        return 1
    thread = threading.Thread(target=backup_loop, args=(server,), daemon=True)
    thread.start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDeteniendo servidor...")
    finally:
        server.close_transactions()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
