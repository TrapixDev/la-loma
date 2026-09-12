"""Acceso remoto a la base de datos del servidor POS.

Implementa la misma interfaz de DatabaseManager (execute_query,
execute_insert, execute_update, transaction) para que los servicios del
negocio funcionen sin cambios sobre HTTP, con autenticación por token y
transacciones atómicas en el servidor.
"""

import json
import urllib.error
import urllib.request
from contextlib import contextmanager

from network.session import session


class AuthError(Exception):
    """La sesión no es válida o expiró."""


class ServerError(Exception):
    """El servidor rechazó la operación o está fuera de alcance."""


class RemoteCursor:
    """Cursor con resultados de una sentencia ejecutada en el servidor."""

    def __init__(self, result: dict) -> None:
        self._rows = result.get("rows", [])
        self._index = 0
        self.lastrowid = result.get("lastrowid")
        self.rowcount = result.get("rowcount", 0)

    def fetchone(self) -> dict | None:
        if self._index >= len(self._rows):
            return None
        row = self._rows[self._index]
        self._index += 1
        return row

    def fetchall(self) -> list[dict]:
        rows = self._rows[self._index:]
        self._index = len(self._rows)
        return rows


class TxConnection:
    """Conexión dentro de una transacción remota."""

    def __init__(self, db: "RemoteDatabase", tx_id: str) -> None:
        self.db = db
        self.tx_id = tx_id

    def execute(self, sql: str, params: tuple = ()) -> RemoteCursor:
        result = self.db._post("/api/tx/exec", {"tx_id": self.tx_id, "sql": sql,
                                                "params": list(params)})
        return RemoteCursor(result)

    def commit(self) -> None:
        self.db._post("/api/tx/commit", {"tx_id": self.tx_id})

    def rollback(self) -> None:
        self.db._post("/api/tx/rollback", {"tx_id": self.tx_id})


class RemoteDatabase:
    """Cliente de la API del servidor POS con interfaz tipo DatabaseManager."""

    def __init__(self, base_url: str, station: str = "") -> None:
        self.base_url = base_url.rstrip("/")
        self.station = station

    # ---------- transporte ----------

    def _post(self, path: str, payload: dict, login_attempt: bool = False) -> dict:
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=body,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        if session.token:
            request.add_header("Authorization", f"Bearer {session.token}")
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            message = ""
            try:
                data = json.loads(exc.read().decode("utf-8"))
                message = data.get("error", "")
            except Exception:
                pass
            if exc.code == 401:
                if login_attempt:
                    raise ServerError(message or "PIN incorrecto") from exc
                raise AuthError(message or "Sesión expirada") from exc
            raise ServerError(message or f"Error del servidor ({exc.code})") from exc
        except urllib.error.URLError as exc:
            raise ServerError(
                f"No se pudo conectar con el servidor en {self.base_url}. "
                f"Verifique que esté encendido y alcance esta dirección."
            ) from exc

    def _check(self, result: dict) -> dict:
        if "error" in result:
            raise ServerError(result["error"])
        return result

    def _ensure_auth(self) -> None:
        if not session.authenticated:
            raise AuthError("No hay sesión iniciada")

    # ---------- interfaz DatabaseManager ----------

    def initialize(self) -> None:
        pass

    def close(self) -> None:
        pass

    def count_users(self) -> int:
        result = self._check(self._post("/api/health", {}))
        return int(result.get("users", 0))

    def needs_setup(self) -> bool:
        return self.count_users() == 0

    def audit(self, user_id, user_name, station, event, detail="") -> None:
        """Registra auditoría en el servidor (best-effort, no rompe la venta)."""
        if not session.authenticated:
            return
        try:
            self._post("/api/audit", {"event": event, "detail": detail})
        except (AuthError, ServerError):
            pass

    def execute_query(self, sql: str, params: tuple = ()) -> list[dict]:
        self._ensure_auth()
        result = self._check(self._post("/api/query", {"sql": sql, "params": list(params)}))
        return result.get("rows", [])

    def execute_insert(self, sql: str, params: tuple = ()) -> int:
        self._ensure_auth()
        result = self._check(self._post("/api/execute", {"sql": sql, "params": list(params)}))
        return int(result.get("lastrowid") or 0)

    def execute_update(self, sql: str, params: tuple = ()) -> bool:
        self._ensure_auth()
        result = self._check(self._post("/api/execute", {"sql": sql, "params": list(params)}))
        return bool(result.get("rowcount", 0) > 0)

    @contextmanager
    def transaction(self):
        self._ensure_auth()
        result = self._check(self._post("/api/tx/begin", {}))
        tx_id = str(result["tx_id"])
        connection = TxConnection(self, tx_id)
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise

    # ---------- autenticación ----------

    def health(self) -> dict:
        return self._check(self._post("/api/health", {}))

    def check_connection(self, timeout: float = 3.0) -> bool:
        """Verifica rápido si el servidor responde (sin requerir sesión)."""
        request = urllib.request.Request(
            f"{self.base_url}/api/health",
            data=b"{}",
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
                return bool(payload.get("ok"))
        except Exception:
            return False

    def login(self, pin: str) -> dict:
        result = self._post("/api/login", {"pin": pin, "station": self.station},
                            login_attempt=True)
        if "error" in result:
            raise ServerError(result["error"])
        session.set(result["token"], result["user_id"], result["user_name"], self.station)
        return result

    def setup(self, name: str, pin: str) -> dict:
        result = self._post("/api/setup", {"name": name, "pin": pin,
                                           "station": self.station},
                            login_attempt=True)
        if "error" in result:
            raise ServerError(result["error"])
        session.set(result["token"], result["user_id"], result["user_name"], self.station)
        return result

    def logout(self) -> None:
        try:
            self._post("/api/logout", {})
        except Exception:
            pass
        session.clear()
