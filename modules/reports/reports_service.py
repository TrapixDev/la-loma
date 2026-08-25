"""Consultas de reportes (mensual/anual) ligadas al POS: ventas y gastos."""

from database.db_manager import DatabaseManager

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


def _to_crc(amount: float, currency: str, exchange_rate: float) -> float:
    """Convierte un monto a CRC si está en USD."""
    if currency == "USD" and exchange_rate > 0:
        return round(amount * exchange_rate, 2)
    return amount


def _date_filters(start: str = "", end: str = "") -> tuple[str, list[object]]:
    """Cláusula y parámetros para filtrar ventas por created_at."""
    clause = "WHERE 1 = 1"
    params: list[object] = []
    if start:
        clause += " AND s.created_at >= ?"
        params.append(start)
    if end:
        clause += " AND s.created_at <= ?"
        params.append(end)
    return clause, params


def _expense_filters(start: str = "", end: str = "") -> tuple[str, list[object]]:
    """Cláusula y parámetros para filtrar gastos por expense_date."""
    clause = "WHERE 1 = 1"
    params: list[object] = []
    if start:
        clause += " AND expense_date >= ?"
        params.append(start)
    if end:
        clause += " AND expense_date <= ?"
        params.append(end)
    return clause, params


def _exclusion_clause() -> str:
    """Ventas anuladas señaladas NO cuentan en ingresos/ganancias/costos."""
    return "AND (s.status <> 'anulada' OR COALESCE(s.excluir_reporte, 0) = 0)"


class ReportsService:
    """Resúmenes de ingresos, costos, ganancias y gastos por período."""

    def __init__(self, db: DatabaseManager):
        self.db = db

    # ---------- ventas ----------

    def summary(self, start: str = "", end: str = "") -> dict:
        """Ingresos, número de ventas, costo y ganancia bruta del período."""
        clause, params = _date_filters(start, end)
        clause += " " + _exclusion_clause()
        rows = self.db.execute_query(
            f"""
            SELECT
                (SELECT COUNT(*) FROM sales s {clause}) AS sale_count,
                (SELECT COALESCE(SUM(CASE WHEN currency = 'USD' AND exchange_rate > 0
                    THEN total * exchange_rate ELSE total END), 0) FROM sales s {clause}) AS ingresos,
                (SELECT COALESCE(SUM(CASE WHEN currency = 'USD' AND exchange_rate > 0
                    THEN tax_amount * exchange_rate ELSE tax_amount END), 0) FROM sales s {clause}) AS tax_amount,
                (SELECT COALESCE(SUM(i.quantity * i.unit_cost), 0)
                 FROM sale_items i JOIN sales s ON i.sale_id = s.id {clause}) AS cost
            """,
            tuple(params * 4),
        )
        row = rows[0]
        ingresos = float(row["ingresos"] or 0)
        cost = float(row["cost"] or 0)
        return {
            "sale_count": int(row["sale_count"] or 0),
            "ingresos": round(ingresos, 2),
            "tax_amount": round(float(row["tax_amount"] or 0), 2),
            "cost": round(cost, 2),
            "gross_profit": round(ingresos - cost, 2),
        }

    def daily_breakdown(self, start: str = "", end: str = "") -> list[dict]:
        """Desglose diario: ventas, ingresos, costo fab., gastos y ganancia por día."""
        clause, params = _date_filters(start, end)
        clause += " " + _exclusion_clause()
        sales_rows = self.db.execute_query(
            f"""
            SELECT substr(s.created_at, 1, 10) AS day,
                   COUNT(*) AS sale_count,
                   COALESCE(SUM(CASE WHEN s.currency = 'USD' AND s.exchange_rate > 0
                       THEN s.total * s.exchange_rate ELSE s.total END), 0) AS ingresos
            FROM sales s {clause}
            GROUP BY day ORDER BY day
            """,
            tuple(params),
        )
        cost_rows = self.db.execute_query(
            f"""
            SELECT substr(s.created_at, 1, 10) AS day,
                   COALESCE(SUM(i.quantity * i.unit_cost), 0) AS cost
            FROM sale_items i JOIN sales s ON i.sale_id = s.id {clause}
            GROUP BY day
            """,
            tuple(params),
        )
        exp_clause, exp_params = _expense_filters(start, end)
        expense_rows = self.db.execute_query(
            f"""
            SELECT expense_date AS day, COALESCE(SUM(amount), 0) AS expenses
            FROM expenses {exp_clause}
            GROUP BY day
            """,
            tuple(exp_params),
        )
        costs = {row["day"]: float(row["cost"] or 0) for row in cost_rows}
        expenses = {row["day"]: float(row["expenses"] or 0) for row in expense_rows}
        sales = {row["day"]: row for row in sales_rows}
        result = []
        for day in sorted(set(sales) | set(costs) | set(expenses)):
            row = sales.get(day, {})
            ingresos = float(row.get("ingresos") or 0)
            cost = costs.get(day, 0.0)
            gastos = expenses.get(day, 0.0)
            result.append({
                "day": day,
                "sale_count": int(row.get("sale_count") or 0),
                "ingresos": round(ingresos, 2),
                "cost": round(cost, 2),
                "expenses": round(gastos, 2),
                "net_profit": round(ingresos - cost - gastos, 2),
            })
        return result

    def monthly_breakdown(self, year: int) -> list[dict]:
        """Desglose mensual (12 filas) del año: ventas, ingresos, costo fab., gastos y ganancia."""
        excl = _exclusion_clause()
        sales_rows = self.db.execute_query(
            f"""
            SELECT CAST(substr(s.created_at, 6, 2) AS INTEGER) AS month,
                   COUNT(*) AS sale_count,
                   COALESCE(SUM(CASE WHEN s.currency = 'USD' AND s.exchange_rate > 0
                       THEN s.total * s.exchange_rate ELSE s.total END), 0) AS ingresos
            FROM sales s
            WHERE substr(s.created_at, 1, 4) = ? {excl}
            GROUP BY month
            """,
            (str(year),),
        )
        cost_rows = self.db.execute_query(
            f"""
            SELECT CAST(substr(s.created_at, 6, 2) AS INTEGER) AS month,
                   COALESCE(SUM(i.quantity * i.unit_cost), 0) AS cost
            FROM sale_items i JOIN sales s ON i.sale_id = s.id
            WHERE substr(s.created_at, 1, 4) = ? {excl}
            GROUP BY month
            """,
            (str(year),),
        )
        expense_rows = self.db.execute_query(
            """
            SELECT CAST(substr(expense_date, 6, 2) AS INTEGER) AS month,
                   COALESCE(SUM(amount), 0) AS expenses
            FROM expenses
            WHERE substr(expense_date, 1, 4) = ?
            GROUP BY month
            """,
            (str(year),),
        )
        costs = {row["month"]: float(row["cost"] or 0) for row in cost_rows}
        expenses = {row["month"]: float(row["expenses"] or 0) for row in expense_rows}
        sales_by_month = {row["month"]: row for row in sales_rows}
        result = []
        for month in range(1, 13):
            row = sales_by_month.get(month)
            if row is None:
                result.append({
                    "month": month,
                    "sale_count": 0,
                    "ingresos": 0.0,
                    "cost": 0.0,
                    "expenses": 0.0,
                    "net_profit": 0.0,
                })
            else:
                ingresos = float(row["ingresos"] or 0)
                cost = costs.get(month, 0.0)
                gastos = expenses.get(month, 0.0)
                result.append({
                    "month": month,
                    "sale_count": int(row["sale_count"] or 0),
                    "ingresos": round(ingresos, 2),
                    "cost": round(cost, 2),
                    "expenses": round(gastos, 2),
                    "net_profit": round(ingresos - cost - gastos, 2),
                })
        return result

    def list_sales(self, start: str = "", end: str = "", limit: int = 50) -> list[dict]:
        clause, params = _date_filters(start, end)
        params.append(limit)
        rows = self.db.execute_query(
            SALE_SELECT + f" {clause} ORDER BY s.id DESC LIMIT ?", tuple(params))
        return [dict(row) for row in rows]

    # ---------- gastos ----------

    def expenses_total(self, start: str = "", end: str = "") -> float:
        clause, params = _expense_filters(start, end)
        rows = self.db.execute_query(
            f"SELECT COALESCE(SUM(amount), 0) AS total FROM expenses {clause}",
            tuple(params),
        )
        return float(rows[0]["total"]) if rows else 0.0

    def expenses_by_category(self, start: str = "", end: str = "") -> list[dict]:
        clause, params = _expense_filters(start, end)
        rows = self.db.execute_query(
            f"""
            SELECT category, COUNT(*) AS count, COALESCE(SUM(amount), 0) AS total
            FROM expenses {clause}
            GROUP BY category ORDER BY total DESC
            """,
            tuple(params),
        )
        return [{"category": row["category"], "count": int(row["count"] or 0),
                 "total": round(float(row["total"] or 0), 2)} for row in rows]

    def list_movements(self, start: str = "", end: str = "") -> list[dict]:
        """Movimientos del período (ventas + gastos) ordenados por fecha descendente.

        Cada movimiento incluye 'tipo' (VENTA/GASTO), 'detalle', 'metodo',
        'monto', 'fecha' y un 'id' propio para poder ubicarlo.
        """
        # Si se pide un día concreto (start == end sin hora), incluir todo el día
        # en las ventas, cuyo created_at lleva hora:YYYY-MM-DD HH:MM:SS.
        if start and start == end and " " not in start:
            end_ventas = end + " 23:59:59"
        else:
            end_ventas = end
        venta_clause, venta_params = _date_filters(start, end_ventas)
        ventas = self.db.execute_query(
            SALE_SELECT
            + f" {venta_clause} "
              "AND (s.status <> 'anulada' OR COALESCE(s.excluir_reporte, 0) = 0) "
              "ORDER BY s.created_at DESC",
            tuple(venta_params),
        )
        movimientos: list[dict] = []
        for v in ventas:
            monto = _to_crc(float(v["total"] or 0), v["currency"], float(v["exchange_rate"] or 0))
            movimientos.append({
                "id": v["id"],
                "invoice_number": v["invoice_number"],
                "tipo": "VENTA",
                "detalle": v["client_name"] or "Consumidor Final",
                "metodo": v["payment_method"] or "",
                "monto": round(monto, 2),
                "fecha": v["created_at"] or "",
            })

        exp_clause, exp_params = _expense_filters(start, end_ventas)
        gastos = self.db.execute_query(
            f"SELECT id, expense_date AS fecha, category, description, amount, "
            f"payment_method FROM expenses {exp_clause} ORDER BY fecha DESC",
            tuple(exp_params),
        )
        for g in gastos:
            detalle = g["category"] or ""
            if g["description"]:
                detalle = f"{detalle} — {g['description']}"
            movimientos.append({
                "id": g["id"],
                "invoice_number": "",
                "tipo": "GASTO",
                "detalle": detalle or "Gasto",
                "metodo": g["payment_method"] or "",
                "monto": round(float(g["amount"] or 0), 2),
                "fecha": g["fecha"] or "",
            })

        movimientos.sort(key=lambda m: m["fecha"] or "", reverse=True)
        return movimientos

    # ---------- combinado ----------

    def full_summary(self, start: str = "", end: str = "") -> dict:
        """Todo para las tarjetas: ingresos, costo de fabricación, gastos y ganancia neta."""
        sales = self.summary(start, end)
        expenses = self.expenses_total(start, end)
        result = dict(sales)
        result["expenses"] = round(expenses, 2)
        result["net_profit"] = round(sales["gross_profit"] - expenses, 2)
        return result

    # ---------- notas de crédito ----------

    def create_credit_note(self, sale_id: int, motivo: str, razon: str,
                           codigo: str = "01", total: float = 0.0,
                           clave: str = "", estado: str = "PENDIENTE") -> int:
        """Crea un registro de nota de crédito (consecutivo propio) y devuelve su id.

        Requiere que la venta exista. El consecutivo es independiente de las
        facturas (contador 'credit_note').
        """
        sale = self.db.execute_query(
            "SELECT * FROM sales WHERE id = ?", (sale_id,))
        if not sale:
            raise ValueError(f"La venta {sale_id} no existe.")
        row = sale[0]
        from network.session import session
        with self.db.transaction() as connection:
            connection.execute(
                "INSERT INTO counters (name, value) VALUES ('credit_note', 1) "
                "ON CONFLICT(name) DO UPDATE SET value = value + 1")
            counter = connection.execute(
                "SELECT value FROM counters WHERE name = 'credit_note'").fetchone()
            numero = f"NC-{int(counter['value']) if counter else 1:05d}"
            cursor = connection.execute(
                """
                INSERT INTO credit_notes (sale_id, invoice_number, client_id,
                    subtotal, tax_amount, total, motivo, razon, codigo_referencia,
                    estado, hacienda_key, hacienda_status, user_id, user_name,
                    station, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    COALESCE(?, datetime('now', 'localtime')))
                """,
                (sale_id, numero, row["client_id"], row["subtotal"],
                 row["tax_amount"], total or row["total"], motivo, razon, codigo,
                 estado, clave, "", session.user_id, session.user_name,
                 session.station, None),
            )
            return cursor.lastrowid

    def get_credit_notes(self, start: str = "", end: str = "") -> list[dict]:
        clause = "WHERE 1 = 1"
        params: list[object] = []
        if start:
            clause += " AND created_at >= ?"
            params.append(start)
        if end:
            clause += " AND created_at <= ?"
            params.append(end)
        rows = self.db.execute_query(
            f"""SELECT n.*, s.invoice_number AS factura_original
                FROM credit_notes n LEFT JOIN sales s ON s.id = n.sale_id
                {clause} ORDER BY n.id DESC""",
            tuple(params),
        )
        return [dict(row) for row in rows]
