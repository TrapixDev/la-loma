"""Punto de entrada del POS La Loma.

Modos:
  python main.py            UI de venta (estación).
  python main.py --server   Servidor central sin ventana (solo modo fuente;
                            el .exe lo lanza automáticamente).
  python main.py --selftest Valida BD + semilla + servicios sin abrir la UI.
"""

import argparse
import ctypes
import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

_MUTEX_HANDLE = None


def _crear_mutex_app() -> None:
    """Mutex global 'PosLaLomaMutex' para que el instalador detecte y cierre
    la app antes de actualizar (Inno Setup, CloseApplications)."""
    global _MUTEX_HANDLE
    if sys.platform != "win32":
        return
    try:
        kernel32 = ctypes.windll.kernel32
        _MUTEX_HANDLE = kernel32.CreateMutexW(None, False, "PosLaLomaMutex")
    except Exception:
        _MUTEX_HANDLE = None


def _redirigir_salida_sin_consola() -> None:
    """En el .exe sin consola (PyInstaller --windowed), sys.stdout y sys.stderr
    son None y cualquier print() reventaría la app. Se redirigen a un archivo
    de log para que el auto-arranque del servidor no falle silenciosamente.
    En modo fuente (python main.py) no hace nada: hay consola."""
    if not getattr(sys, "frozen", False):
        return
    try:
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
        log_dir = base / "PosLaLoma" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "app.log"
        if sys.stdout is None:
            sys.stdout = open(log_path, "a", encoding="utf-8", errors="replace")
        if sys.stderr is None:
            sys.stderr = open(log_path, "a", encoding="utf-8", errors="replace")
    except Exception:
        pass

try:
    from PyQt6.QtWidgets import QApplication, QDialog, QMessageBox
except ImportError as exc:
    print("ERROR: PyQt6 no está instalado. Ejecute: pip install PyQt6")
    print(f"Detalle: {exc}")
    raise SystemExit(1)

from config import Config
from database.db_manager import DatabaseManager
from database.seed import seed_initial_data
from modules.categories.category_service import CategoryService
from modules.clients.client_service import ClientService
from modules.credit.credit_service import CreditService
from modules.expenses.expense_service import ExpenseService
from modules.hacienda.hacienda_client import HaciendaClient
from modules.pos.cart_service import CartService
from modules.products.product_service import ProductService
from modules.reports.reports_service import ReportsService
from network.image_store import ImageStore
from network.remote_db import RemoteDatabase, ServerError
from network.session import session

from ui.login_dialog import LocalAuth, LoginDialog
from ui.main_window import MainWindow
from ui.styles import QSS_MAIN


def build_services(db) -> dict:
    return {
        "db": db,
        "category": CategoryService(db),
        "product": ProductService(db),
        "client": ClientService(db),
        "cart": CartService(db),
        "credit": CreditService(db),
        "expenses": ExpenseService(db),
        "reports": ReportsService(db),
        "hacienda": HaciendaClient(),
        "images": ImageStore(),
    }


def _is_local_server() -> bool:
    """True si SERVER_URL apunta a esta misma PC."""
    try:
        host = (urlparse(Config.SERVER_URL).hostname or "").lower()
    except Exception:
        host = ""
    return host in ("", "127.0.0.1", "localhost", "::1")


def _start_server_process() -> bool:
    """Abre el servidor en un proceso propio sin ventana (si el servidor es local).

    - Modo fuente:   python server.py
    - Modo .exe:     PosLaLoma.exe --server  (misma app en rol servidor, invisible)
    """
    from config import IS_FROZEN
    if IS_FROZEN:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        command = [sys.executable, "--server"]
    else:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        script = Path(__file__).resolve().parent / "server.py"
        if not script.exists():
            return False
        command = [sys.executable, str(script)]
    try:
        subprocess.Popen(
            command,
            creationflags=flags,
            close_fds=True,
        )
        return True
    except OSError:
        return False


def _run_server_mode() -> int:
    """Rol servidor (sin UI). Usado por el .exe lanzado con --server."""
    import threading
    import server as server_module

    from utils.arranque import asegurar_estructura, migrar_datos_si_vacio
    asegurar_estructura()
    migrar_datos_si_vacio()
    try:
        server = server_module.start_server()
    except OSError as exc:
        if getattr(exc, "winerror", None) == 10048:
            print(f"El puerto {Config.SERVER_PORT} ya está en uso.")
            return 0
        print(f"No se pudo iniciar el servidor: {exc}")
        return 1
    thread = threading.Thread(target=server_module.backup_loop, args=(server,),
                              daemon=True)
    thread.start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.close_transactions()
        server.server_close()
    return 0


def _selftest() -> int:
    """Valida BD + semilla + servicios básicos sin abrir la ventana."""
    from database.db_manager import DatabaseManager
    from database.seed import seed_initial_data
    from modules.categories.category_service import CategoryService
    from modules.products.product_service import ProductService
    from modules.clients.client_service import ClientService

    from utils.arranque import asegurar_estructura, migrar_datos_si_vacio
    asegurar_estructura()
    migrar_datos_si_vacio()
    print(f"POS La Loma {Config.APP_VERSION} — autocomprobación")
    try:
        db = DatabaseManager(Config.DB_PATH)
        db.initialize()
        seed_initial_data(db)
        categorias = CategoryService(db).get_all()
        productos = ProductService(db).get_all()
        clientes = ClientService(db).get_all()
        ok = len(categorias) >= 0 and len(productos) >= 0 and len(clientes) >= 0
        print(f"Categorías: {len(categorias)} | Productos: {len(productos)} "
              f"| Clientes: {len(clientes)}")
        print("Base de datos y servicios: OK" if ok else "ERROR en servicios")
        db.close()
        return 0 if ok else 1
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1


def _wait_for_server(db, seconds: int = 20) -> bool:
    """Espera hasta que el servidor responda, o se agota el tiempo."""
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            db.health()
            return True
        except ServerError:
            time.sleep(0.5)
    return False


def _try_auto_start(db) -> bool:
    """Levanta el servidor local automáticamente si falta. True si conecta."""
    if not _is_local_server():
        return False
    print("No se encontró el servidor; iniciándolo automáticamente...")
    if not _start_server_process():
        return False
    return _wait_for_server(db, seconds=20)


def ensure_server_available(db) -> bool:
    """Verifica el servidor; si falta y es local, lo crea automáticamente.

    Solo si el arranque automático falla (o el servidor es remoto) muestra
    el diálogo de recuperación.
    """
    auto_attempted = False
    while True:
        try:
            db.health()
            return True
        except ServerError:
            pass

        if not auto_attempted and _try_auto_start(db):
            return True
        auto_attempted = True

        local = _is_local_server()
        box = QMessageBox()
        box.setIcon(QMessageBox.Icon.Critical)
        box.setWindowTitle("Servidor no disponible")
        box.setText("No se pudo conectar con el servidor del POS.")
        if local:
            box.setInformativeText(
                "Se intentó iniciar el servidor automáticamente, pero no\n"
                "respondió. Revise la ventana del servidor por si muestra\n"
                "un error, o púlselo de nuevo aquí."
            )
        else:
            box.setInformativeText(
                f"Verifique que:\n\n"
                f"1) En la PC que guarda la base se ejecutó:  python server.py\n"
                f"2) En config.py de esta estación, SERVER_URL apunta al servidor.\n"
                f"   Configurado: {Config.SERVER_URL}\n"
                f"3) El Firewall de Windows de la PC servidor permite Python\n"
                f"   (acepte el aviso que aparece al iniciar el servidor)."
            )
        start_button = None
        if local:
            start_button = box.addButton(
                "Iniciar servidor", QMessageBox.ButtonRole.AcceptRole)
        retry_button = box.addButton(
            "Reintentar", QMessageBox.ButtonRole.ActionRole)
        cancel_button = box.addButton(
            "Salir", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        clicked = box.clickedButton()

        if local and clicked == start_button:
            if not _start_server_process():
                QMessageBox.warning(None, "Servidor",
                                    "No se pudo abrir server.py.")
                continue
            if _wait_for_server(db):
                return True
            QMessageBox.warning(
                None, "Servidor",
                "El servidor no respondió. Revise la ventana del servidor "
                "por si muestra un error.")
            continue
        if clicked == cancel_button:
            return False


def open_login(db) -> bool:
    dialog = LoginDialog(db, station=Config.STATION)
    return dialog.exec() == QDialog.DialogCode.Accepted


def main() -> int:
    from utils.arranque import asegurar_estructura, migrar_datos_si_vacio

    _redirigir_salida_sin_consola()

    parser = argparse.ArgumentParser(prog="pos-la-loma")
    parser.add_argument("--server", action="store_true",
                        help="ejecutar como servidor central sin ventana")
    parser.add_argument("--selftest", action="store_true",
                        help="validar BD y servicios sin abrir la ventana")
    args = parser.parse_args()
    if args.server:
        return _run_server_mode()
    if args.selftest:
        return _selftest()

    asegurar_estructura()
    migrar_datos_si_vacio()

    _crear_mutex_app()

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setApplicationName("POS - La Loma")
    app.setStyleSheet(QSS_MAIN)

    if Config.MODE == "server":
        db = RemoteDatabase(Config.SERVER_URL, station=Config.STATION)
        if not ensure_server_available(db):
            return 0
    else:
        local_db = DatabaseManager(Config.DB_PATH)
        local_db.initialize()
        seed_initial_data(local_db)
        db = LocalAuth(local_db)

    while True:
        try:
            if not open_login(db):
                return 0
            break
        except ServerError:
            if Config.MODE == "server" and ensure_server_available(db):
                continue
            QMessageBox.critical(None, "Error",
                                 "No se pudo conectar con el servidor.")
            return 1

    services = build_services(db)
    window = MainWindow(services)
    window.showMaximized()
    code = app.exec()
    if session.token:
        db.logout()
    return code


if __name__ == "__main__":
    raise SystemExit(main())
