from database.db_manager import DatabaseManager
from database.models import Sale, SaleItem

SALE_SELECT = """
SELECT s.id, s.invoice_number, s.client_id, c.name AS client_name, s.subtotal,
       s.discount, s.tax_amount, s.total, s.payment_method, s.cash_received,
       s.change_amount, s.payment_details, s.invoice_type, s.currency,
       s.exchange_rate, s.status,
       s.hacienda_key, s.hacienda_status, s.electronic_invoice,
       s.excluir_reporte, s.station,
       s.user_id, s.user_name, s.created_at
FROM sales s
LEFT JOIN clients c ON c.id = s.client_id
"""


class CartService:
    """Servicio del carrito: registro de ventas y consultas."""

    def __init__(self, db: DatabaseManager):
        self.db = db

    def create_sale(self, sale: Sale, items: list[SaleItem]) -> int:
        reference = getattr(sale, "sale_reference", "") or ""
        if reference:
            # Idempotencia: si la venta ya quedó registrada (p. ej. se perdió
            # la respuesta de red al confirmar), devolver el id existente en
            # lugar de duplicar la factura.
            rows = self.db.execute_query(
                "SELECT id FROM sales WHERE sale_reference = ?", (reference,))
            if rows:
                return int(rows[0]["id"])
        with self.db.transaction() as connection:
            invoice_number = sale.invoice_number
            if not invoice_number:
                # Determinar prefijo según moneda
                currency = getattr(sale, "currency", "CRC")
                prefix = "D-" if currency == "USD" else "V-"
                counter_name = "invoice_usd" if currency == "USD" else "invoice"

                # Reserva atómica del siguiente número
                connection.execute(
                    f"INSERT INTO counters (name, value) VALUES ('{counter_name}', 1) "
                    f"ON CONFLICT(name) DO UPDATE SET value = value + 1"
                )
                row = connection.execute(
                    f"SELECT value FROM counters WHERE name = '{counter_name}'"
                ).fetchone()
                invoice_number = f"{prefix}{int(row['value']) if row else 1:05d}"
            cursor = connection.execute(
                """
                INSERT INTO sales (invoice_number, client_id, subtotal, discount,
                    tax_amount, total, payment_method, cash_received, change_amount,
                    payment_details, invoice_type, currency, exchange_rate,
                    sale_reference,
                    status, hacienda_key,
                    hacienda_status, electronic_invoice, station, user_id,
                    user_name, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    COALESCE(?, datetime('now', 'localtime')))
                """,
                (invoice_number, sale.client_id, sale.subtotal, sale.discount,
                 sale.tax_amount, sale.total, sale.payment_method, sale.cash_received,
                 sale.change_amount, sale.payment_details,
                 getattr(sale, "invoice_type", "general"),
                 getattr(sale, "currency", "CRC"),
                 getattr(sale, "exchange_rate", 0.0),
                 reference or None,
                 sale.status,
                 sale.hacienda_key, sale.hacienda_status,
                 int(sale.electronic_invoice), sale.station,
                 sale.user_id, sale.user_name,
                 sale.created_at),
            )
            sale_id = cursor.lastrowid
            for item in items:
                cost_row = connection.execute(
                    "SELECT cost_price FROM products WHERE id = ?", (item.product_id,)
                ).fetchone()
                unit_cost = float(cost_row["cost_price"]) if cost_row else 0.0
                connection.execute(
                    """
                    INSERT INTO sale_items (sale_id, product_id, product_name,
                        quantity, unit_price, unit_cost, discount, tax_amount, total)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (sale_id, item.product_id, item.product_name, item.quantity,
                     item.unit_price, unit_cost, item.discount, item.tax_amount, item.total),
                )
        return sale_id

    def get_sale(self, sale_id: int) -> Sale | None:
        rows = self.db.execute_query(SALE_SELECT + " WHERE s.id = ?", (sale_id,))
        if not rows:
            return None
        sale = Sale(**rows[0])
        item_rows = self.db.execute_query(
            "SELECT * FROM sale_items WHERE sale_id = ? ORDER BY id", (sale_id,))
        sale.items = [SaleItem(**row) for row in item_rows]
        return sale

    def get_recent_sales(self, limit: int = 50) -> list[Sale]:
        rows = self.db.execute_query(
            SALE_SELECT + " ORDER BY s.id DESC LIMIT ?", (limit,))
        sales = [Sale(**row) for row in rows]
        for sale in sales:
            item_rows = self.db.execute_query(
                "SELECT * FROM sale_items WHERE sale_id = ? ORDER BY id", (sale.id,))
            sale.items = [SaleItem(**row) for row in item_rows]
        return sales

    def update_hacienda_status(self, sale_id: int, key: str, status: str) -> bool:
        return self.db.execute_update(
            "UPDATE sales SET hacienda_key = ?, hacienda_status = ? WHERE id = ?",
            (key, status, sale_id),
        )

    def anular_venta(self, sale_id: int, motivo: str = "",
                     excluir_reporte: bool = True) -> bool:
        """Anula una venta: marca status='anulada' y, si se pide, la excluye
        del reporte financiero (ingresos/ganancias).

        Devuelve True si se anuló (no retorna nada si ya estaba anulada/inexistente).
        """
        sale = self.get_sale(sale_id)
        if sale is None:
            return False
        if (sale.status or "").lower() == "anulada":
            return False
        excluir = 1 if excluir_reporte else 0
        try:
            with self.db.transaction() as connection:
                connection.execute(
                    "UPDATE sales SET status = 'anulada', excluir_reporte = ? "
                    "WHERE id = ?",
                    (excluir, sale_id),
                )
        except Exception:
            return False
        try:
            from network.session import session
            self.db.audit(
                session.user_id, session.user_name, session.station,
                "ANULACION_VENTA",
                f"Venta {sale.invoice_number} anulada"
                f"{' (excluida del reporte)' if excluir else ''}. Motivo: "
                f"{motivo or 'Sin especificar'}",
            )
        except Exception:
            pass
        return True
