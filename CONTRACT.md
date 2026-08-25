# CONTRATO DE INTERFACES - POS La Loma
# Este archivo define la API compartida entre el backend (Agente 1) y el frontend (Agente 2).
# NO MODIFICAR las firmas de estos métodos sin coordinación.

## ==== database/db_manager.py (Agente 1) ====

class DatabaseManager:
    def __init__(self, db_path: str): ...
    def initialize(self) -> None: ...  # Crea tablas si no existen + migraciones
    def execute_query(self, sql: str, params: tuple = ()) -> list[dict]  # SELECT -> lista de dicts
    def execute_insert(self, sql: str, params: tuple = ()) -> int         # INSERT -> id
    def execute_update(self, sql: str, params: tuple = ()) -> bool        # UPDATE/DELETE
    @contextmanager
    def transaction(self) -> connection   # commit/rollback automático
    def count_users(self) -> int
    def audit(self, user_id, user_name, station, event, detail="") -> None
    def close(self) -> None: ...

## ==== database/models.py (Agente 1) - dataclasses ====

@dataclass
class Category: id, name, description, color, icon, active, created_at, updated_at
@dataclass
class Product:
    id, code, barcode, name, description, category_id, cost_price, sale_price,
    stock_quantity, min_stock, unit_of_measure, cabys_code, tax_type, tax_rate,
    active, image_path, category_name (default "", read-join)
@dataclass
class Client:
    id, id_type, id_number, name, email, phone, address, province, canton, district, activity_code
@dataclass
class SaleItem: id, sale_id, product_id, product_name, quantity, unit_price, discount, tax_amount, total
@dataclass
class Sale:
    id, invoice_number, client_id, client_name, subtotal, discount, tax_amount, total,
    payment_method, cash_received, change_amount, payment_details, invoice_type,
    sale_reference, currency, exchange_rate, status, hacienda_key, hacienda_status,
    electronic_invoice, station, user_id, user_name, created_at, items: list[SaleItem]
# sale_reference: UUID único por intento de venta (idempotencia: el reintento
# tras perder la red devuelve la venta existente en lugar de duplicar).

## ==== database/seed.py (Agente 1) ====
def seed_initial_data(db: DatabaseManager) -> None:  # Categorías base mueblería

## ==== modules/categories/category_service.py (Agente 1) ====

class CategoryService:
    def __init__(self, db: DatabaseManager)
    def get_all(self, active_only: bool = True) -> list[Category]
    def get_by_id(self, category_id: int) -> Category | None
    def create(self, category: Category) -> int
    def update(self, category: Category) -> bool
    def delete(self, category_id: int) -> bool
    def get_product_count(self, category_id: int) -> int

## ==== modules/products/product_service.py (Agente 1) ====

class ProductService:
    def __init__(self, db: DatabaseManager)
    def get_all(self, category_id: int | None = None, active_only: bool = True) -> list[Product]
    def get_by_id(self, product_id: int) -> Product | None
    def search(self, query: str, category_id: int | None = None) -> list[Product]
    def create(self, product: Product) -> int
    def update(self, product: Product) -> bool
    def delete(self, product_id: int) -> bool

## ==== modules/pos/cart_service.py (Agente 1) ====

class CartService:
    def __init__(self, db: DatabaseManager)
    def create_sale(self, sale: Sale, items: list[SaleItem]) -> int          # Inserta venta + items
    # Idempotente por sale_reference. El stock se ignora (se fabrica a pedido),
    # así que las ventas se registran sin validar ni descontar existencias.
    def get_sale(self, sale_id: int) -> Sale | None
    def get_recent_sales(self, limit: int = 50) -> list[Sale]
    def update_hacienda_status(self, sale_id: int, key: str, status: str) -> bool

## ==== modules/clients/client_service.py (Agente 1) ====

class ClientService:
    def __init__(self, db: DatabaseManager)
    def get_all(self) -> list[Client]
    def get_by_id(self, client_id: int) -> Client | None
    def get_by_id_number(self, id_number: str) -> Client | None
    def create(self, client: Client) -> int
    def update(self, client: Client) -> bool
    def search(self, query: str) -> list[Client]

## ==== modules/hacienda/hacienda_client.py (Agente 1) ====

class HaciendaClient:
    BASE_URL = "https://api.hacienda.go.cr"
    def __init__(self, provider_url: str = "", api_key: str = "")  # Proveedor FE (Almendro), vacío = solo API pública
    def get_taxpayer_info(self, id_number: str) -> dict | None
    def get_exchange_rate(self) -> dict | None
    def search_cabys(self, query: str, limit: int = 10) -> list[dict]
    def get_exoneration(self, authorization: str) -> dict | None
    def send_electronic_invoice(self, invoice_data: dict) -> dict | None   # 202 + clave
    def get_voucher_status(self, key: str) -> dict | None
    def cancel_voucher(self, key: str) -> dict | None
    def check_connection(self) -> bool  # True si puede alcanzar api.hacienda.go.cr

## ==== modules/hacienda/xml_generator.py (Agente 1) ====

class XMLGenerator:
    def __init__(self, company_config: dict)  # {company_id, company_name, branch, terminal, activity_code}
    def generate_key(self, date, consecutive: str, terminal: str, branch: str) -> str  # 50 dígitos
    def build_invoice_payload(self, sale: Sale, sale_items: list[SaleItem],
                              client: Client | None, company_config: dict) -> dict  # Payload v4.4 para proveedor

## ==== CAPA DE RED Y SEGURIDAD (v1.1) ====
# Modo servidor: el POS se conecta por HTTP a server.py; los servicios usan
# la MISMA interfaz DatabaseManager. Modo local: LocalAuth envuelve
# DatabaseManager y también implementa la misma interfaz, así los servicios
# no distinguen entre modos.

## ==== server.py ====
# Servidor HTTP estándar (sin dependencias). Endpoints JSON:
#   POST /api/health        -> {ok, users} (sin auth)
#   POST /api/setup         -> crea PIN inicial (solo si no hay usuarios); devuelve token
#   POST /api/login         -> {pin} -> {token, user_id, user_name} (401 pin malo, 423 bloqueado)
#   POST /api/logout        -> invalida token
#   POST /api/query         -> {sql, params} SOLO SELECT (requiere token)
#   POST /api/execute       -> {sql, params} SOLO INSERT/UPDATE/DELETE (requiere token)
#   POST /api/tx/begin|exec|commit|rollback -> transacciones atómicas remotas
#   GET  /api/update/info      -> {server_version, server_url, setups:[{filename,size,md5}]} (sin auth)
#   GET  /api/update/download/<archivo.exe> -> descarga del setup (sin auth, nombre validado)
# Reglas: token Bearer por request, PIN hasheado PBKDF2-SHA256 (nunca plano),
# bloqueo por estación tras 5 PIN fallidos (15 min), SQL de una sola sentencia
# (rechaza PRAGMA/ALTER/CREATE/DROP/BEGIN/';' etc.), auditoría de login y de
# toda escritura en audit_log, respaldo automático en data/backups (14 últimos),
# transacciones huérfanas (>10 min) se cierran solas.

## ==== network/remote_db.py (cliente) ====
class RemoteDatabase:  # Misma interfaz que DatabaseManager
    def __init__(self, base_url: str, station: str = "")
    execute_query/execute_insert/execute_update/transaction()/close()/count_users()
    def health(self) -> dict
    def needs_setup(self) -> bool
    def login(self, pin: str) -> dict       # levanta ServerError; AuthError = sesión expirada
    def setup(self, name: str, pin: str) -> dict
    def logout(self) -> None

## ==== ui/login_dialog.py ====
class LoginDialog(QDialog):   # PIN pad táctil; setup automático en primer arranque
    def __init__(self, db, station: str = "", parent: QWidget | None = None)
    # db debe exponer: needs_setup(), login(pin), setup(name, pin) [+ register_failure opcional]
class LocalAuth:  # envuelve DatabaseManager y agrega auth; interfaz de proveedor completa

## ==== network/session.py ====
session  # Singleton: .token, .user_id, .user_name, .station, .set(), .clear(), .authenticated

## ==== Ventas ====
# Sale ahora incluye user_id y user_name (quién vendió). Las ventas guardan
# también station. Cada ejecución del POS exige PIN (una sesión por arranque).

## ==== Config (config.py) ====
# MODE = "server" | "local"; SERVER_HOST/PORT; SERVER_URL (estaciones);
# STATION por PC; SESSION_HOURS, MAX_LOGIN_ATTEMPTS, LOCKOUT_MINUTES,
# BACKUP_HOURS, KEEP_BACKUPS. APP_VERSION = "1.0.0".
# Rutas: modo fuente ./data; modo congelado %APPDATA%\PosLaLoma\data.
# Overrides por PC vía config.ini (sección [pos]): server_url, station,
# docs_path, mode. DOCS_PATH = carpeta compartida de red para XML/PDF.

## ==== utils/arranque.py ====
def asegurar_estructura() -> None                  # crea carpetas de datos
def migrar_datos_si_vacio() -> bool                # copia data\ (USB) a %APPDATA% si está vacío
def ruta_config_ini() -> Path                      # %APPDATA%\PosLaLoma\config.ini

## ==== network/updater.py ====
def version_key(version: str) -> tuple             # '1.2.3' -> (1,2,3)
def consultar_actualizaciones() -> dict            # GET /api/update/info
def setup_mas_nuevo(info: dict) -> dict | None     # mejor setup por versión
def hay_actualizacion(info: dict) -> (bool, str, dict | None)
def descargar_setup(setup: dict, destino: Path) -> Path   # verifica MD5
def instalar_setup(ruta: Path) -> None             # Inno silencioso
class UpdateError(Exception)

## ==== main.py ====
# --server   ejecuta el servidor central sin ventana (usado por el .exe)
# --selftest valida BD + seed + servicios sin abrir la UI (salida 0 = OK)
