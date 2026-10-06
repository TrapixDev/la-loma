"""Servicio de gastos del POS (registro, consulta y categorías)."""

from datetime import date

from database.db_manager import DatabaseManager
from database.models import Expense

from network.session import session


class ExpenseService:
    """Gastos del negocio: cada registro queda auditado por el servidor."""

    def __init__(self, db: DatabaseManager):
        self.db = db

    def add_expense(self, amount: float, category: str, description: str = "",
                    payment_method: str = "efectivo",
                    expense_date: str | None = None) -> int:
        """Registra un gasto. La categoría nueva se crea automáticamente."""
        amount = round(float(amount), 2)
        category = str(category).strip() or "Otros"
        if expense_date is None:
            expense_date = date.today().isoformat()
        self._ensure_category(category)
        return self.db.execute_insert(
            "INSERT INTO expenses (expense_date, category, description, amount, "
            "payment_method, user_id, user_name, station) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (expense_date, category, description, amount, payment_method,
             session.user_id, session.user_name, session.station),
        )

    def update_expense(self, expense_id: int, amount: float, category: str,
                       description: str = "",
                       payment_method: str = "efectivo",
                       expense_date: str | None = None) -> bool:
        """Edita un gasto existente. La categoría nueva se crea sola."""
        amount = round(float(amount), 2)
        category = str(category).strip() or "Otros"
        if expense_date is None:
            expense_date = date.today().isoformat()
        self._ensure_category(category)
        return self.db.execute_update(
            "UPDATE expenses SET expense_date = ?, category = ?, description = ?, "
            "amount = ?, payment_method = ? WHERE id = ?",
            (expense_date, category, description, amount, payment_method,
             int(expense_id)),
        )

    def get_expense(self, expense_id: int) -> Expense | None:
        """Devuelve un gasto por id (para el detalle del movimiento)."""
        rows = self.db.execute_query(
            "SELECT * FROM expenses WHERE id = ?", (expense_id,))
        return Expense(**rows[0]) if rows else None

    def delete_expense(self, expense_id: int) -> bool:
        return self.db.execute_update("DELETE FROM expenses WHERE id = ?", (expense_id,))

    def get_expenses_by_category(self, category: str, start: str = "",
                                 end: str = "",
                                 limit: int = 500) -> list[Expense]:
        """Gastos de una categoría en un período (detalle del reporte)."""
        sql = "SELECT * FROM expenses WHERE category = ?"
        params: list[object] = [str(category)]
        if start:
            sql += " AND expense_date >= ?"
            params.append(start)
        if end:
            sql += " AND expense_date <= ?"
            params.append(end)
        sql += " ORDER BY expense_date DESC, id DESC LIMIT ?"
        params.append(int(limit))
        rows = self.db.execute_query(sql, tuple(params))
        return [Expense(**row) for row in rows]

    def get_expenses(self, start: str = "", end: str = "",
                     limit: int = 200) -> list[Expense]:
        sql = "SELECT * FROM expenses"
        params: list[object] = []
        if start:
            sql += " WHERE expense_date >= ?"
            params.append(start)
            if end:
                sql += " AND expense_date <= ?"
                params.append(end)
        elif end:
            sql += " WHERE expense_date <= ?"
            params.append(end)
        sql += " ORDER BY expense_date DESC, id DESC LIMIT ?"
        params.append(limit)
        rows = self.db.execute_query(sql, tuple(params))
        return [Expense(**row) for row in rows]

    def summary_by_category(self, start: str = "", end: str = "") -> list[dict]:
        sql = (
            "SELECT category, COUNT(*) AS count, SUM(amount) AS total "
            "FROM expenses WHERE 1 = 1"
        )
        params: list[object] = []
        if start:
            sql += " AND expense_date >= ?"
            params.append(start)
        if end:
            sql += " AND expense_date <= ?"
            params.append(end)
        sql += " GROUP BY category ORDER BY total DESC"
        rows = self.db.execute_query(sql, tuple(params))
        return [{"category": row["category"], "count": row["count"],
                 "total": float(row["total"] or 0)} for row in rows]

    def total_amount(self, start: str = "", end: str = "") -> float:
        sql = "SELECT COALESCE(SUM(amount), 0) AS total FROM expenses WHERE 1 = 1"
        params: list[object] = []
        if start:
            sql += " AND expense_date >= ?"
            params.append(start)
        if end:
            sql += " AND expense_date <= ?"
            params.append(end)
        rows = self.db.execute_query(sql, tuple(params))
        return float(rows[0]["total"]) if rows else 0.0

    def get_categories(self) -> list[str]:
        rows = self.db.execute_query(
            "SELECT name FROM expense_categories WHERE active = 1 ORDER BY name")
        return [row["name"] for row in rows]

    def _ensure_category(self, name: str) -> None:
        rows = self.db.execute_query(
            "SELECT id FROM expense_categories WHERE name = ?", (name,))
        if not rows:
            self.db.execute_insert(
                "INSERT INTO expense_categories (name) VALUES (?)", (name,))
