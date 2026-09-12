import sqlite3
from contextlib import contextmanager
from pathlib import Path

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    description TEXT,
    color TEXT DEFAULT '#3498db',
    icon TEXT,
    image_path TEXT,
    active BOOLEAN DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    updated_at TEXT DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE,
    barcode TEXT UNIQUE,
    name TEXT NOT NULL,
    description TEXT,
    category_id INTEGER,
    cost_price REAL DEFAULT 0,
    sale_price REAL NOT NULL,
    stock_quantity REAL DEFAULT 0,
    min_stock REAL DEFAULT 0,
    unit_of_measure TEXT DEFAULT 'Unid',
    wood_type TEXT,
    cabys_code TEXT,
    tax_type TEXT DEFAULT 'gravado',
    tax_rate REAL DEFAULT 13.0,
    active BOOLEAN DEFAULT 1,
    image_path TEXT,
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    updated_at TEXT DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (category_id) REFERENCES categories (id)
);

CREATE TABLE IF NOT EXISTS clients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    id_type TEXT DEFAULT '02',
    id_number TEXT UNIQUE,
    name TEXT NOT NULL DEFAULT 'Consumidor Final',
    email TEXT,
    phone TEXT,
    address TEXT,
    province TEXT,
    canton TEXT,
    district TEXT,
    activity_code TEXT
);

CREATE TABLE IF NOT EXISTS sales (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_number TEXT,
    client_id INTEGER,
    subtotal REAL DEFAULT 0,
    discount REAL DEFAULT 0,
    tax_amount REAL DEFAULT 0,
    total REAL DEFAULT 0,
    payment_method TEXT DEFAULT 'efectivo',
    cash_received REAL DEFAULT 0,
    change_amount REAL DEFAULT 0,
    payment_details TEXT,
    invoice_type TEXT DEFAULT 'general',
    currency TEXT DEFAULT 'CRC',
    exchange_rate REAL DEFAULT 0,
    sale_reference TEXT,
    status TEXT DEFAULT 'completada',
    hacienda_key TEXT,
    hacienda_status TEXT,
    xml_generated BOOLEAN DEFAULT 0,
    electronic_invoice BOOLEAN DEFAULT 0,
    excluir_reporte INTEGER DEFAULT 0,
    station TEXT,
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (client_id) REFERENCES clients (id)
);

CREATE TABLE IF NOT EXISTS sale_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sale_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    product_name TEXT,
    quantity REAL DEFAULT 0,
    unit_price REAL DEFAULT 0,
    discount REAL DEFAULT 0,
    tax_amount REAL DEFAULT 0,
    total REAL DEFAULT 0,
    FOREIGN KEY (sale_id) REFERENCES sales (id),
    FOREIGN KEY (product_id) REFERENCES products (id)
);

CREATE TABLE IF NOT EXISTS hacienda_config (
    id INTEGER PRIMARY KEY DEFAULT 1,
    username TEXT,
    password TEXT,
    pin TEXT,
    certificate_path TEXT,
    environment TEXT DEFAULT 'sandbox',
    consecutive_fe TEXT DEFAULT '0010000001',
    consecutive_te TEXT DEFAULT '0010000001',
    branch TEXT DEFAULT '001',
    terminal TEXT DEFAULT '001',
    activity_code TEXT,
    company_name TEXT,
    company_id TEXT,
    company_phone TEXT,
    company_address TEXT,
    updated_at TEXT DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    pin_salt TEXT NOT NULL,
    pin_hash TEXT NOT NULL,
    active BOOLEAN DEFAULT 1,
    failed_attempts INTEGER DEFAULT 0,
    locked_until TEXT,
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    last_login_at TEXT
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    user_id INTEGER,
    user_name TEXT,
    station TEXT,
    event TEXT NOT NULL,
    detail TEXT
);

CREATE TABLE IF NOT EXISTS expense_categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    active BOOLEAN DEFAULT 1
);

CREATE TABLE IF NOT EXISTS expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    expense_date TEXT DEFAULT (datetime('now', 'localtime')),
    category TEXT NOT NULL,
    description TEXT,
    amount REAL NOT NULL DEFAULT 0,
    payment_method TEXT DEFAULT 'efectivo',
    user_id INTEGER,
    user_name TEXT,
    station TEXT,
    created_at TEXT DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS counters (
    name TEXT PRIMARY KEY,
    value INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS app_config (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS credit_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sale_id INTEGER,
    invoice_number TEXT,
    client_id INTEGER,
    subtotal REAL DEFAULT 0,
    tax_amount REAL DEFAULT 0,
    total REAL DEFAULT 0,
    motivo TEXT,
    razon TEXT,
    codigo_referencia TEXT DEFAULT '01',
    estado TEXT DEFAULT 'PENDIENTE',
    hacienda_key TEXT,
    hacienda_status TEXT,
    user_id INTEGER,
    user_name TEXT,
    station TEXT,
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (sale_id) REFERENCES sales (id)
);

CREATE TABLE IF NOT EXISTS product_images (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL,
    filename TEXT NOT NULL,
    orden INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (product_id) REFERENCES products (id)
);

CREATE TABLE IF NOT EXISTS credit_accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sale_id INTEGER NOT NULL REFERENCES sales(id),
    client_id INTEGER NOT NULL REFERENCES clients(id),
    invoice_number TEXT NOT NULL,
    total REAL NOT NULL DEFAULT 0,
    amount_paid REAL NOT NULL DEFAULT 0,
    balance REAL NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pendiente',
    notes TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    updated_at TEXT DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS credit_payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    credit_account_id INTEGER NOT NULL REFERENCES credit_accounts(id),
    amount REAL NOT NULL,
    payment_method TEXT NOT NULL DEFAULT 'efectivo',
    payment_details TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    payment_reference TEXT,
    user_id INTEGER,
    user_name TEXT,
    created_at TEXT DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS credit_payment_images (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    payment_id INTEGER NOT NULL REFERENCES credit_payments(id),
    image_path TEXT NOT NULL,
    description TEXT DEFAULT '',
    is_cover INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX IF NOT EXISTS idx_products_category ON products (category_id);
CREATE INDEX IF NOT EXISTS idx_sale_items_sale ON sale_items (sale_id);
CREATE INDEX IF NOT EXISTS idx_sales_client ON sales (client_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_sales_reference ON sales (sale_reference);
CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_log (created_at);
CREATE INDEX IF NOT EXISTS idx_expenses_date ON expenses (expense_date);
CREATE INDEX IF NOT EXISTS idx_credit_accounts_sale ON credit_accounts (sale_id);
CREATE INDEX IF NOT EXISTS idx_credit_accounts_client ON credit_accounts (client_id);
CREATE INDEX IF NOT EXISTS idx_credit_accounts_status ON credit_accounts (status);
CREATE INDEX IF NOT EXISTS idx_credit_payments_account ON credit_payments (credit_account_id);
CREATE INDEX IF NOT EXISTS idx_credit_payment_images ON credit_payment_images (payment_id);
CREATE INDEX IF NOT EXISTS idx_sales_created ON sales (created_at);
CREATE INDEX IF NOT EXISTS idx_credit_notes_sale ON credit_notes (sale_id);
CREATE INDEX IF NOT EXISTS idx_expenses_category ON expenses (category);
"""


class DatabaseManager:
    """Gestor de conexión SQLite y operaciones de base de datos."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._connection: sqlite3.Connection | None = None

    def _connect(self) -> sqlite3.Connection:
        if self._connection is None:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            self._connection = sqlite3.connect(self.db_path)
            self._connection.row_factory = sqlite3.Row
            self._connection.execute("PRAGMA foreign_keys = ON")
        return self._connection

    def initialize(self) -> None:
        """Crea las tablas si no existen y aplica migraciones."""
        connection = self._connect()
        connection.executescript(SCHEMA_SQL)
        self._migrate(connection)
        connection.commit()

    def _migrate(self, connection: sqlite3.Connection) -> None:
        """Migraciones incrementales para bases existentes."""
        sales_columns = {row["name"] for row in connection.execute("PRAGMA table_info(sales)")}
        if "user_id" not in sales_columns:
            connection.execute("ALTER TABLE sales ADD COLUMN user_id INTEGER")
        if "user_name" not in sales_columns:
            connection.execute("ALTER TABLE sales ADD COLUMN user_name TEXT")
        if "excluir_reporte" not in sales_columns:
            connection.execute(
                "ALTER TABLE sales ADD COLUMN excluir_reporte INTEGER DEFAULT 0")
        if "payment_details" not in sales_columns:
            connection.execute("ALTER TABLE sales ADD COLUMN payment_details TEXT")
        if "invoice_type" not in sales_columns:
            connection.execute(
                "ALTER TABLE sales ADD COLUMN invoice_type TEXT DEFAULT 'general'")
        if "currency" not in sales_columns:
            connection.execute(
                "ALTER TABLE sales ADD COLUMN currency TEXT DEFAULT 'CRC'")
        if "exchange_rate" not in sales_columns:
            connection.execute(
                "ALTER TABLE sales ADD COLUMN exchange_rate REAL DEFAULT 0")
        if "sale_reference" not in sales_columns:
            connection.execute(
                "ALTER TABLE sales ADD COLUMN sale_reference TEXT")
            connection.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_sales_reference "
                "ON sales (sale_reference)")
        item_columns = {row["name"] for row in connection.execute("PRAGMA table_info(sale_items)")}
        if "unit_cost" not in item_columns:
            connection.execute("ALTER TABLE sale_items ADD COLUMN unit_cost REAL DEFAULT 0")
            connection.execute(
                "UPDATE sale_items SET unit_cost = COALESCE("
                "(SELECT cost_price FROM products WHERE products.id = sale_items.product_id), 0)"
            )
        product_columns = {row["name"] for row in connection.execute("PRAGMA table_info(products)")}
        if "wood_type" not in product_columns:
            connection.execute("ALTER TABLE products ADD COLUMN wood_type TEXT")
        category_columns = {row["name"] for row in connection.execute("PRAGMA table_info(categories)")}
        if "image_path" not in category_columns:
            connection.execute("ALTER TABLE categories ADD COLUMN image_path TEXT")
        payment_columns = {row["name"] for row in connection.execute("PRAGMA table_info(credit_payments)")}
        if payment_columns and "payment_reference" not in payment_columns:
            connection.execute("ALTER TABLE credit_payments ADD COLUMN payment_reference TEXT")
        if payment_columns:
            connection.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_credit_payments_reference "
                "ON credit_payments (payment_reference)"
            )
        duplicates = connection.execute(
            "SELECT invoice_number FROM sales WHERE invoice_number IS NOT NULL "
            "GROUP BY invoice_number HAVING COUNT(*) > 1"
        ).fetchall()
        if not duplicates:
            connection.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_sales_invoice ON sales (invoice_number)"
            )

        # Contador de facturas: se inicia desde la mayor numeración existente
        # para que las nuevas ventas sigan la secuencia sin duplicarse.
        connection.execute(
            "CREATE TABLE IF NOT EXISTS counters ("
            "name TEXT PRIMARY KEY, value INTEGER NOT NULL DEFAULT 0)"
        )
        if connection.execute(
            "SELECT 1 FROM counters WHERE name = 'invoice'"
        ).fetchone() is None:
            max_number = connection.execute(
                "SELECT COALESCE(MAX(CAST(substr(invoice_number, 3) AS INTEGER)), 0) AS m "
                "FROM sales WHERE invoice_number LIKE 'V-%'"
            ).fetchone()["m"]
            connection.execute(
                "INSERT INTO counters (name, value) VALUES ('invoice', ?)",
                (int(max_number or 0),),
            )

        # Inicializar app_config con tipo de cambio por defecto
        if connection.execute(
            "SELECT 1 FROM app_config WHERE key = 'exchange_rate'"
        ).fetchone() is None:
            connection.execute(
                "INSERT INTO app_config (key, value) VALUES ('exchange_rate', '520')"
            )
            connection.execute(
                "INSERT INTO app_config (key, value) VALUES ('exchange_rate_date', '')"
            )

    def count_users(self) -> int:
        """Cantidad de usuarios registrados (para detectar primer arranque)."""
        rows = self.execute_query("SELECT COUNT(*) AS total FROM users")
        return int(rows[0]["total"]) if rows else 0

    def audit(self, user_id: int | None, user_name: str, station: str,
              event: str, detail: str = "") -> None:
        """Registra un evento en el log de auditoría."""
        self.execute_insert(
            "INSERT INTO audit_log (user_id, user_name, station, event, detail) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, user_name, station, event, detail),
        )

    def execute_query(self, sql: str, params: tuple = ()) -> list[dict]:
        """Ejecuta un SELECT y devuelve una lista de dicts."""
        connection = self._connect()
        rows = connection.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def execute_insert(self, sql: str, params: tuple = ()) -> int:
        """Ejecuta un INSERT y devuelve el rowid insertado."""
        connection = self._connect()
        cursor = connection.execute(sql, params)
        connection.commit()
        return cursor.lastrowid

    def execute_update(self, sql: str, params: tuple = ()) -> bool:
        """Ejecuta un UPDATE/DELETE y devuelve True si afectó filas."""
        connection = self._connect()
        cursor = connection.execute(sql, params)
        connection.commit()
        return cursor.rowcount > 0

    @contextmanager
    def transaction(self):
        """Contexto de transacción atómica (commit/rollback automático)."""
        connection = self._connect()
        try:
            connection.execute("BEGIN")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise

    def close(self) -> None:
        """Cierra la conexión a la base de datos."""
        if self._connection is not None:
            self._connection.close()
            self._connection = None
