"""Almacén de fotos de productos: subida, descarga y caché local.

En modo servidor las imágenes viven en la PC servidor y se transfieren por
HTTP; en modo local se leen y escriben directamente en disco. El cliente
mantiene una caché en disco y en memoria para no re-descargar.
"""

import base64
import json
import random
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from PyQt6.QtCore import QBuffer, QIODevice, QObject, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPixmap

from config import Config
from network.remote_db import AuthError, ServerError
from network.session import session


class ImageFetchWorker(QObject):
    """Descarga una imagen en segundo plano; devuelve los bytes crudos."""

    finished = pyqtSignal(str, object)

    def __init__(self, store: "ImageStore"):
        super().__init__()
        self.store = store

    def run(self, filename: str) -> None:
        try:
            self.finished.emit(filename, self.store.download(filename))
        except Exception:
            self.finished.emit(filename, None)


class ImageStore:
    """Servicio de fotos de productos con caché local."""

    def __init__(self):
        self._remote = Config.MODE == "server"
        self.base_url = Config.SERVER_URL.rstrip("/")
        self._cache_dir = Path(Config.IMAGE_CACHE_DIR)
        self._pixmaps: dict[str, QPixmap] = {}
        self._in_flight: set[str] = set()
        self._jobs: list[dict] = []
        self._lock = threading.Lock()

    # ---------- transporte ----------

    def _post(self, path: str, payload: dict) -> dict:
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
                raise AuthError(message or "Sesión expirada") from exc
            raise ServerError(message or f"Error del servidor ({exc.code})") from exc
        except urllib.error.URLError as exc:
            raise ServerError(
                f"No se pudo conectar con el servidor en {self.base_url}."
            ) from exc

    # ---------- subida / borrado ----------

    def upload(self, source_path: str) -> str:
        """Redimensiona la imagen y la sube al servidor. Devuelve el nombre."""
        pixmap = QPixmap(source_path)
        if pixmap.isNull():
            raise ServerError("No se pudo leer la imagen seleccionada.")
        max_side = Config.IMAGE_MAX_SIDE
        if pixmap.width() > max_side or pixmap.height() > max_side:
            pixmap = pixmap.scaled(
                max_side, max_side,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        if not pixmap.save(buffer, "PNG"):
            raise ServerError("No se pudo procesar la imagen.")
        data = bytes(buffer.data())
        filename = f"p{int(time.time() * 1000)}{random.randint(0, 0xFFFF):04x}.png"

        if not self._remote:
            target = Path(Config.PRODUCT_IMAGES_DIR) / filename
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            return filename

        result = self._post("/api/image/upload", {
            "name": filename,
            "data": base64.b64encode(data).decode("ascii"),
        })
        if "error" in result:
            raise ServerError(result["error"])
        self._drop_cache(filename)
        return filename

    def delete(self, filename: str) -> bool:
        """Elimina la imagen del servidor (mejor esfuerzo)."""
        if not filename:
            return False
        if not self._remote:
            try:
                Path(Config.PRODUCT_IMAGES_DIR, filename).unlink(missing_ok=True)
            except OSError:
                pass
            self._drop_cache(filename)
            return True
        try:
            result = self._post("/api/image/delete", {"filename": filename})
            self._drop_cache(filename)
            return "error" not in result
        except Exception:
            return False

    # ---------- descarga / caché ----------

    def download(self, filename: str) -> bytes | None:
        """Devuelve los bytes de la imagen; None si no se pudo obtener."""
        if not filename:
            return None
        if not self._remote:
            path = Path(Config.PRODUCT_IMAGES_DIR) / filename
            try:
                return path.read_bytes() if path.is_file() else None
            except OSError:
                return None
        request = urllib.request.Request(
            f"{self.base_url}/api/image/{filename}",
            headers={"Accept": "image/*"},
            method="GET",
        )
        if session.token:
            request.add_header("Authorization", f"Bearer {session.token}")
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                data = response.read()
        except Exception:
            return None
        try:
            self._cache_file(filename).parent.mkdir(parents=True, exist_ok=True)
            self._cache_file(filename).write_bytes(data)
        except OSError:
            pass
        return data

    def _cache_file(self, filename: str) -> Path:
        return self._cache_dir / filename

    def _drop_cache(self, filename: str) -> None:
        with self._lock:
            self._pixmaps.pop(filename, None)
            self._in_flight.discard(filename)
        try:
            self._cache_file(filename).unlink(missing_ok=True)
        except OSError:
            pass

    def get_pixmap(self, filename: str) -> QPixmap | None:
        """Devuelve la imagen desde memoria o disco (nunca red)."""
        if not filename:
            return None
        with self._lock:
            pixmap = self._pixmaps.get(filename)
        if pixmap is not None:
            return pixmap
        cached = self._cache_file(filename)
        if cached.is_file():
            pixmap = QPixmap(str(cached))
            if not pixmap.isNull():
                with self._lock:
                    self._pixmaps[filename] = pixmap
                return pixmap
        return None

    def get_pixmap_async(self, filename: str, callback) -> None:
        """Carga la imagen en segundo plano; llama a callback(QPixmap | None).

        El callback se ejecuta en el hilo principal. Si ya hay una descarga en
        curso para el mismo archivo, se omite (la red re-renderiza y vuelve a
        consultar).
        """
        if not filename:
            callback(None)
            return
        pixmap = self.get_pixmap(filename)
        if pixmap is not None:
            callback(pixmap)
            return
        with self._lock:
            if filename in self._in_flight:
                return
            self._in_flight.add(filename)
        worker = ImageFetchWorker(self)
        entry = {"worker": worker, "thread": None}
        worker.finished.connect(
            lambda name, data: self._on_fetched(name, data, callback, entry))
        thread = threading.Thread(target=worker.run, args=(filename,), daemon=True)
        entry["thread"] = thread
        self._jobs.append(entry)
        thread.start()

    def _on_fetched(self, filename: str, data, callback, entry) -> None:
        with self._lock:
            self._in_flight.discard(filename)
        if entry in self._jobs:
            self._jobs.remove(entry)
        if not data:
            callback(None)
            return
        pixmap = QPixmap()
        if not pixmap.loadFromData(data):
            callback(None)
            return
        with self._lock:
            self._pixmaps[filename] = pixmap
        callback(pixmap)

    # ---------- utilidades ----------

    @staticmethod
    def placeholder_pixmap(name: str, size: int = 96) -> QPixmap:
        """Placeholder oscuro con la inicial del producto."""
        pixmap = QPixmap(size, size)
        pixmap.fill(QColor("#232a36"))
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        colors = ["#2fbf71", "#3b82f6", "#f59e0b", "#8b5cf6", "#ec4899", "#14b8a6"]
        color = colors[sum(ord(ch) for ch in name or "?") % len(colors)]
        painter.setPen(QColor(color))
        font = QFont()
        font.setPointSize(int(size * 0.42))
        font.setBold(True)
        painter.setFont(font)
        initial = (name[:1].upper() or "?")
        painter.drawText(QRectF(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, initial)
        painter.end()
        return pixmap
