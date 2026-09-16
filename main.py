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
import socket
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


def _instalar_hooks() -> None:
    """Envía cualquier excepción no controlada al archivo de log."""
    import threading

    from utils.diagnostico import escribir_log

    def _hook(exc_type, exc_value, exc_tb):
        import traceback
        detalle = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        escribir_log("Excepción no controlada:\n" + detalle)

    sys.excepthook = _hook
    threading.excepthook = lambda args: _hook(
        args.exc_type, args.exc_value, args.exc_traceback)


def _diagnostico_primera_vez() -> None:
    """Avisa solo si hay problemas de instalación (una vez por equipo)."""
    from utils.diagnostico import (
        escribir_log,
        hay_problemas,
        log_dir,
        recolectar,
        texto_reporte,
    )
    try:
        marca = log_dir() / ".diagnostico_revisado"
        if marca.is_file():
            return
        checks = recolectar()
        escribir_log(texto_reporte(checks))
        if hay_problemas(checks):
            from ui.error_dialog import mostrar_diagnostico
            mostrar_diagnostico(None, checks)
        marca.parent.mkdir(parents=True, exist_ok=True)
        marca.write_text("ok", encoding="utf-8")
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
from modules.promotions.promotion_service import PromotionService
from modules.reports.reports_service import ReportsService
from network.image_store import ImageStore
from network.remote_db import RemoteDatabase, ServerError
from network.session import session

from ui.login_dialog import LocalAuth, LoginDialog
from ui.main_window import MainWindow
from ui.styles import QSS_MAIN


class SafeApplication(QApplication):
    """QApplication que captura excepciones de la interfaz en vez de abortar."""

    _error_mostrado = False

    def notify(self, receiver, event):
        try:
            return super().notify(receiver, event)
        except Exception:
            from utils.diagnostico import registrar_traceback
            detalle = registrar_traceback("Error en la interfaz (slot/evento)")
            if not SafeApplication._error_mostrado:
                SafeApplication._error_mostrado = True
                try:
                    from ui.error_dialog import mostrar_error
                    mostrar_error(
                        None, "Error inesperado",
                        "Ocurrió un error en la interfaz, pero el POS sigue "
                        "abierto.\nPuede continuar trabajando; si se repite, "
                        "copie el diagnóstico y envíelo.",
                        detalle)
                except Exception:
                    pass
            return False


def build_services(db) -> dict:
    from utils import secretos
    try:
        secretos.migrar_secretos_en_db(db)
    except Exception:
        pass
    return {
        "db": db,
        "category": CategoryService(db),
        "product": ProductService(db),
        "client": ClientService(db),
        "cart": CartService(db),
        "credit": CreditService(db),
        "promotions": PromotionService(db),
        "expenses": ExpenseService(db),
        "reports": ReportsService(db),
        "hacienda": HaciendaClient(),
        "images": ImageStore(),
    }


def _is_local_server_url(url: str) -> bool:
    """True si la URL apunta a esta misma PC."""
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        host = ""
    return host in ("", "127.0.0.1", "localhost", "::1")


def _is_local_server() -> bool:
    """True si SERVER_URL apunta a esta misma PC."""
    return _is_local_server_url(Config.SERVER_URL)


def _port_busy(port: int | None = None) -> bool:
    """True si otro programa ocupa el puerto del servidor en 127.0.0.1."""
    port = port or Config.SERVER_PORT
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.bind(("127.0.0.1", port))
        return False
    except OSError:
        return True
    finally:
        probe.close()


def _tcp_open(host: str, port: int, timeout: float = 1.0) -> bool:
    """True si hay algo escuchando en host:port (aunque no sea el POS)."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _find_free_port(start: int, attempts: int = 20) -> int | None:
    """Primer puerto libre desde `start` (probando en 127.0.0.1)."""
    for port in range(start, min(start + attempts, 65536)):
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            probe.bind(("127.0.0.1", port))
            return port
        except OSError:
            continue
        finally:
            probe.close()
    return None


def _choose_local_port(url: str, pinned: bool) -> int | None:
    """Puerto alterno si el puerto local está ocupado por otro programa.

    Solo aplica a URLs locales y cuando el usuario no fijó puerto/URL en
    config.ini. Devuelve None cuando no hace falta mover el puerto.
    """
    if pinned or not _is_local_server_url(url):
        return None
    try:
        parsed = urlparse(url)
        port = parsed.port or 8000
        host = parsed.hostname or "127.0.0.1"
    except ValueError:
        return None
    if not _tcp_open(host, port):
        return None  # nadie escucha: no hay conflicto, se arranca normal
    if RemoteDatabase(url).check_connection(timeout=2.0):
        return None  # es el servidor del POS, no hay que mover nada
    return _find_free_port(port + 1)


def _start_server_process(port: int | None = None) -> bool:
    """Abre el servidor en un proceso propio sin ventana (si el servidor es local).

    - Modo fuente:   python server.py
    - Modo .exe:     PosLaLoma.exe --server  (misma app en rol servidor, invisible)
    `port` se pasa al hijo con POS_SERVER_PORT para usar un puerto alterno.
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
    env = None
    if port:
        env = dict(os.environ)
        env["POS_SERVER_PORT"] = str(port)
    try:
        subprocess.Popen(
            command,
            creationflags=flags,
            close_fds=True,
            env=env,
        )
        return True
    except OSError:
        return False


def _run_server_mode() -> int:
    """Rol servidor (sin UI). Usado por el .exe lanzado con --server."""
    import threading
    import traceback
    import server as server_module

    from utils.arranque import asegurar_estructura, migrar_datos_si_vacio
    asegurar_estructura()
    migrar_datos_si_vacio()
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Servidor POS iniciando "
          f"en puerto {Config.SERVER_PORT} (log {Path(__file__).name})")
    try:
        server = server_module.start_server()
    except OSError as exc:
        if getattr(exc, "winerror", None) == 10048:
            print(f"El puerto {Config.SERVER_PORT} ya está en uso. "
                  f"Cierre el otro programa o cambie server_port en config.ini.")
            return 0
        traceback.print_exc()
        return 1
    except Exception:
        traceback.print_exc()
        return 1
    print(f"Servidor POS escuchando en el puerto {Config.SERVER_PORT}.")
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
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1
    try:
        from utils.diagnostico import recolectar, texto_reporte
        print()
        print(texto_reporte(recolectar()))
    except Exception:
        pass
    return 0 if ok else 1


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


def _try_auto_start(db, port: int | None = None) -> bool:
    """Levanta el servidor local automáticamente si falta. True si conecta."""
    if not _is_local_server():
        return False
    print("No se encontró el servidor; iniciándolo automáticamente...")
    if not _start_server_process(port):
        return False
    return _wait_for_server(db, seconds=20)


def ensure_server_available(db, port: int | None = None) -> bool:
    """Verifica el servidor; si falta y es local, lo crea automáticamente.

    Solo si el arranque automático falla (o el servidor es remoto) muestra
    el diálogo de recuperación. `port` es el puerto efectivo del servidor
    local (puede diferir de Config.SERVER_PORT si se auto-movió).
    """
    effective_port = port or Config.SERVER_PORT
    auto_attempted = False
    while True:
        try:
            db.health()
            return True
        except ServerError:
            pass

        if not auto_attempted and _try_auto_start(db, port):
            return True
        auto_attempted = True

        local = _is_local_server()
        box = QMessageBox()
        box.setIcon(QMessageBox.Icon.Critical)
        box.setWindowTitle("Servidor no disponible")
        box.setText("No se pudo conectar con el servidor del POS.")
        if local:
            if _port_busy(effective_port):
                box.setInformativeText(
                    f"El puerto {effective_port} está en uso (por otro\n"
                    f"programa u otra instancia del servidor). Cierre el otro\n"
                    f"programa o cambie server_port en config.ini y reintente."
                )
            else:
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
            if not _start_server_process(port):
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


def _main() -> int:
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

    app = SafeApplication(sys.argv)
    app.setStyle("Fusion")
    app.setApplicationName("POS - La Loma")
    app.setStyleSheet(QSS_MAIN)

    _diagnostico_primera_vez()

    if Config.MODE == "server":
        url = Config.SERVER_URL
        chosen_port = None
        if _is_local_server_url(url):
            chosen_port = _choose_local_port(url, Config.SERVER_PORT_PINNED)
        if chosen_port:
            busy_port = urlparse(url).port or 8000
            print(f"El puerto {busy_port} está ocupado por otro programa; "
                  f"se usará el {chosen_port} para el servidor del POS.")
            QMessageBox.information(
                None, "Servidor del POS",
                f"El puerto {busy_port} está ocupado por otro programa.\n"
                f"Se usará el puerto {chosen_port} para el servidor del POS "
                f"en esta sesión.")
            url = f"http://127.0.0.1:{chosen_port}"
        db = RemoteDatabase(url, station=Config.STATION)
        if not ensure_server_available(db, chosen_port):
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


def main() -> int:
    """Punto de entrada con blindaje: todo error queda en el log y en un aviso."""
    from utils.diagnostico import configurar_logs, registrar_traceback

    configurar_logs()
    _instalar_hooks()
    try:
        return _main()
    except SystemExit:
        raise
    except BaseException:
        detalle = registrar_traceback("Error fatal al iniciar o ejecutar el POS")
        try:
            if QApplication.instance() is not None:
                from ui.error_dialog import mostrar_error
                mostrar_error(
                    None, "Error fatal del POS",
                    "El POS no pudo continuar. El detalle quedó guardado en el "
                    "registro; puede copiarlo y reportarlo.",
                    detalle)
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
