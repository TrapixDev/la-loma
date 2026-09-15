"""Servicio de cuentas por cobrar (crédito)."""

import os

from database.db_manager import DatabaseManager
from database.models import CreditAccount, CreditPayment, CreditPaymentImage

from network.session import session


class CreditService:
    """CRUD de cuentas por cobrar, abonos y comprobantes."""

    def __init__(self, db: DatabaseManager):
        self.db = db

    # ---------- cuentas ----------

    def create_account(self, sale_id: int, client_id: int, invoice_number: str,
                       total: float, notes: str = "",
                       account_type: str = "credito",
                       delivery_status: str = "entregado",
                       due_date: str = "",
                       financing_months: int = 0,
                       financing_installment: float = 0.0) -> int:
        return self.db.execute_insert(
            "INSERT INTO credit_accounts "
            "(sale_id, client_id, invoice_number, total, amount_paid, balance, "
            "account_type, delivery_status, due_date, financing_months, "
            "financing_installment, notes) "
            "VALUES (?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?, ?)",
            (sale_id, client_id, invoice_number, total, total,
             account_type, delivery_status, due_date,
             int(financing_months or 0),
             round(float(financing_installment or 0.0), 2), notes),
        )

    def get_all(self, status_filter: str = "",
                client_search: str = "",
                type_filter: str = "") -> list[CreditAccount]:
        sql = (
            "SELECT ca.*, c.name AS client_name, c.id_number AS client_id_number, "
            "c.phone AS client_phone "
            "FROM credit_accounts ca "
            "JOIN clients c ON c.id = ca.client_id "
            "WHERE 1 = 1"
        )
        params: list[object] = []
        if status_filter:
            sql += " AND ca.status = ?"
            params.append(status_filter)
        if type_filter == "credito":
            sql += " AND ca.account_type = 'credito'"
        elif type_filter == "encargo":
            sql += " AND ca.account_type <> 'credito'"
        if client_search:
            sql += " AND (c.name LIKE ? OR c.id_number LIKE ?)"
            pattern = f"%{client_search}%"
            params.extend([pattern, pattern])
        sql += " ORDER BY ca.created_at DESC"
        rows = self.db.execute_query(sql, tuple(params))
        return [CreditAccount(**row) for row in rows]

    def get_by_id(self, account_id: int) -> CreditAccount | None:
        rows = self.db.execute_query(
            "SELECT ca.*, c.name AS client_name, c.id_number AS client_id_number, "
            "c.phone AS client_phone "
            "FROM credit_accounts ca "
            "JOIN clients c ON c.id = ca.client_id "
            "WHERE ca.id = ?",
            (account_id,),
        )
        return CreditAccount(**rows[0]) if rows else None

    def get_by_client(self, client_id: int) -> list[CreditAccount]:
        rows = self.db.execute_query(
            "SELECT ca.*, c.name AS client_name, c.id_number AS client_id_number, "
            "c.phone AS client_phone "
            "FROM credit_accounts ca "
            "JOIN clients c ON c.id = ca.client_id "
            "WHERE ca.client_id = ? "
            "ORDER BY ca.created_at DESC",
            (client_id,),
        )
        return [CreditAccount(**row) for row in rows]

    def update_status(self, account_id: int, status: str) -> bool:
        return self.db.execute_update(
            "UPDATE credit_accounts SET status = ?, "
            "updated_at = datetime('now', 'localtime') WHERE id = ?",
            (status, account_id),
        )

    # ---------- abonos ----------

    def make_payment(self, account_id: int, amount: float,
                     payment_method: str = "efectivo",
                     payment_details: str = "",
                     notes: str = "",
                     reference: str = "") -> int:
        """Registra un abono de forma atómica y validada.

        Si `reference` ya fue registrada, devuelve el id existente (idempotencia
        ante reintentos por caída de red). Valida monto > 0 y <= saldo.
        """
        amount = round(float(amount), 2)
        if amount <= 0:
            raise ValueError("El monto del abono debe ser mayor a cero.")
        if reference:
            rows = self.db.execute_query(
                "SELECT id FROM credit_payments WHERE payment_reference = ?",
                (reference,),
            )
            if rows:
                return int(rows[0]["id"])
        with self.db.transaction() as connection:
            account = connection.execute(
                "SELECT balance, status FROM credit_accounts WHERE id = ?",
                (account_id,),
            ).fetchone()
            if account is None:
                raise ValueError("La cuenta por cobrar no existe.")
            if (account["status"] or "") != "pendiente":
                raise ValueError("La cuenta no está pendiente de pago.")
            balance = float(account["balance"] or 0)
            if amount > balance + 0.001:
                raise ValueError(
                    f"El monto ({amount:,.2f}) supera el saldo pendiente "
                    f"({balance:,.2f}).")
            cursor = connection.execute(
                "INSERT INTO credit_payments "
                "(credit_account_id, amount, payment_method, payment_details, notes, "
                "payment_reference, user_id, user_name) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (account_id, amount, payment_method, payment_details, notes,
                 reference or None, session.user_id, session.user_name),
            )
            payment_id = int(cursor.lastrowid)
            self._refresh_balance_conn(connection, account_id)
        return payment_id

    def get_payments(self, account_id: int) -> list[CreditPayment]:
        rows = self.db.execute_query(
            "SELECT cp.*, c.name AS client_name, ca.invoice_number "
            "FROM credit_payments cp "
            "JOIN credit_accounts ca ON ca.id = cp.credit_account_id "
            "JOIN clients c ON c.id = ca.client_id "
            "WHERE cp.credit_account_id = ? "
            "ORDER BY cp.id DESC",
            (account_id,),
        )
        return [CreditPayment(**row) for row in rows]

    def _refresh_balance(self, account_id: int) -> None:
        """Recalcula amount_paid y balance de una cuenta."""
        with self.db.transaction() as connection:
            self._refresh_balance_conn(connection, account_id)

    def _refresh_balance_conn(self, connection, account_id: int) -> None:
        """Recalcula la cuenta usando una conexión/transacción existente."""
        row = connection.execute(
            "SELECT COALESCE(SUM(amount), 0) AS paid "
            "FROM credit_payments WHERE credit_account_id = ?",
            (account_id,),
        ).fetchone()
        paid = float(row["paid"]) if row else 0.0
        account = connection.execute(
            "SELECT total, status FROM credit_accounts WHERE id = ?",
            (account_id,),
        ).fetchone()
        if account is None:
            return
        total = float(account["total"] or 0)
        balance = round(max(0.0, total - paid), 2)
        status = "pagada" if balance <= 0 else "pendiente"
        if (account["status"] or "") == "anulada":
            status = "anulada"
        connection.execute(
            "UPDATE credit_accounts SET amount_paid = ?, balance = ?, status = ?, "
            "updated_at = datetime('now', 'localtime') WHERE id = ?",
            (paid, balance, status, account_id),
        )

    # ---------- entrega (encargos/apartados) ----------

    def mark_delivered(self, account_id: int) -> bool:
        """Marca un encargo/apartado como entregado (con fecha de hoy)."""
        return self.db.execute_update(
            "UPDATE credit_accounts SET delivery_status = 'entregado', "
            "delivered_at = datetime('now', 'localtime'), "
            "updated_at = datetime('now', 'localtime') WHERE id = ?",
            (account_id,),
        )

    # ---------- resumen ----------

    def get_summary(self) -> dict:
        rows = self.db.execute_query(
            "SELECT "
            "COALESCE(SUM(CASE WHEN status = 'pendiente' THEN balance ELSE 0 END), 0) "
            "AS total_pendiente, "
            "COALESCE(SUM(amount_paid), 0) AS total_pagado, "
            "COUNT(*) AS total_cuentas, "
            "COALESCE(SUM(CASE WHEN status = 'pendiente' THEN 1 ELSE 0 END), 0) "
            "AS cuentas_pendientes, "
            "COALESCE(SUM(CASE WHEN account_type <> 'credito' "
            "AND delivery_status = 'pendiente' THEN 1 ELSE 0 END), 0) "
            "AS encargos_pendientes, "
            "COALESCE(SUM(CASE WHEN account_type <> 'credito' "
            "AND delivery_status = 'pendiente' THEN balance ELSE 0 END), 0) "
            "AS total_encargos "
            "FROM credit_accounts"
        )
        r = rows[0] if rows else {}
        return {
            "total_pendiente": float(r.get("total_pendiente", 0) or 0),
            "total_pagado": float(r.get("total_pagado", 0) or 0),
            "total_cuentas": int(r.get("total_cuentas", 0) or 0),
            "cuentas_pendientes": int(r.get("cuentas_pendientes", 0) or 0),
            "encargos_pendientes": int(r.get("encargos_pendientes", 0) or 0),
            "total_encargos": float(r.get("total_encargos", 0) or 0),
        }

    # ---------- comprobantes ----------

    def add_payment_image(self, payment_id: int, image_path: str,
                          description: str = "") -> int:
        return self.db.execute_insert(
            "INSERT INTO credit_payment_images (payment_id, image_path, description) "
            "VALUES (?, ?, ?)",
            (payment_id, image_path, description),
        )

    def remove_payment_image(self, image_id: int) -> bool:
        rows = self.db.execute_query(
            "SELECT image_path FROM credit_payment_images WHERE id = ?",
            (image_id,),
        )
        removed = self.db.execute_update(
            "DELETE FROM credit_payment_images WHERE id = ?", (image_id,))
        if removed and rows:
            path = rows[0]["image_path"] or ""
            try:
                if path and os.path.exists(path):
                    os.remove(path)
            except OSError:
                pass
        return removed

    def list_payment_images(self, payment_id: int) -> list[CreditPaymentImage]:
        rows = self.db.execute_query(
            "SELECT * FROM credit_payment_images WHERE payment_id = ? "
            "ORDER BY is_cover DESC, created_at ASC",
            (payment_id,),
        )
        return [CreditPaymentImage(**row) for row in rows]
