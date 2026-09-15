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


def _end_of_day(value: str) -> str:
    """Extiende una fecha sin hora hasta el final del día (23:59:59)."""
    value = (value or "").strip()
    if value and " " not in value:
        return value + " 23:59:59"
    return value


def _date_filters(start: str = "", end: str = "") -> tuple[str, list[object]]:
    """Cláusula y parámetros para filtrar ventas por created_at."""
    clause = "WHERE 1 = 1"
    params: list[object] = []
    if start:
        clause += " AND s.created_at >= ?"
        params.append(start)
    if end:
        clause += " AND s.created_at <= ?"
        params.append(_end_of_day(end))
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


# Costo de fabricación: los encargos/apartados lo reconocen en la fecha de
# entrega; mientras están pendientes no cuentan en los reportes.
_COST_JOIN = (
    "LEFT JOIN credit_accounts ca ON ca.sale_id = s.id "
    "AND ca.account_type <> 'credito'"
)
_COST_DATE = (
    "COALESCE(CASE WHEN ca.id IS NOT NULL AND ca.delivery_status = 'entregado' "
    "THEN NULLIF(ca.delivered_at, '') ELSE s.created_at END, s.created_at)"
)
_COST_SCOPE = "AND (ca.id IS NULL OR ca.delivery_status = 'entregado')"


def _cost_filters(start: str = "", end: str = "") -> tuple[str, list[object]]:
    """Cláusula de costo con fecha efectiva (entrega para encargos)."""
    clause = "WHERE 1 = 1"
    params: list[object] = []
    if start:
        clause += f" AND {_COST_DATE} >= ?"
        params.append(start)
    if end:
        clause += f" AND {_COST_DATE} <= ?"
        params.append(_end_of_day(end))
    clause += " " + _exclusion_clause() + " " + _COST_SCOPE
    return clause, params


CREDIT_METHOD = "credito"

# Abonos pertenecientes a cuentas cuya venta fue anulada y excluida del
# reporte no cuentan como ingreso.
_EXCLUDED_CREDIT_ACCOUNTS = (
    "AND credit_account_id NOT IN ("
    " SELECT exca.id FROM credit_accounts exca"
    " JOIN sales exs ON exs.id = exca.sale_id"
    " WHERE exs.status = 'anulada' AND COALESCE(exs.excluir_reporte, 0) = 1)"
)


def _credit_payment_filters(start: str = "", end: str = "",
                            column: str = "created_at") -> tuple[str, list[object]]:
    """Cláusula y parámetros para filtrar abonos por created_at.

    Los abonos de cuentas por cobrar representan ingreso en base a caja: solo
    cuentan cuando el cliente paga, no al momento de la venta a crédito. Se
    excluyen los abonos de ventas anuladas y excluidas del reporte.
    """
    clause = "WHERE 1 = 1"
    params: list[object] = []
    if start:
        clause += f" AND {column} >= ?"
        params.append(start)
    if end:
        clause += f" AND {column} <= ?"
        params.append(_end_of_day(end))
    clause += " " + _EXCLUDED_CREDIT_ACCOUNTS
    return clause, params


def _credit_payments_total(db: DatabaseManager, start: str = "", end: str = "") -> float:
    clause, params = _credit_payment_filters(start, end)
    rows = db.execute_query(
        f"SELECT COALESCE(SUM(amount), 0) AS total FROM credit_payments {clause}",
        tuple(params),
    )
    return float(rows[0]["total"] or 0) if rows else 0.0


# Las notas de crédito de ventas de contado restan de los ingresos. Las de
# ventas a crédito reducen el saldo de la cuenta por cobrar (ver
# create_credit_note), por lo que no se restan para no duplicar el efecto.
_CREDIT_NOTE_SCOPE = (
    f"AND COALESCE(s.payment_method, '') <> '{CREDIT_METHOD}' "
    "AND (s.status <> 'anulada' OR COALESCE(s.excluir_reporte, 0) = 0)"
)


def _credit_note_filters(start: str = "", end: str = "",
                         column: str = "n.created_at") -> tuple[str, list[object]]:
    clause = "WHERE 1 = 1"
    params: list[object] = []
    if start:
        clause += f" AND {column} >= ?"
        params.append(start)
    if end:
        clause += f" AND {column} <= ?"
        params.append(_end_of_day(end))
    return clause, params


def _credit_note_amount_sql() -> str:
    return "COALESCE(SUM(n.total), 0)"


def _credit_notes_total(db: DatabaseManager, start: str = "", end: str = "") -> float:
    clause, params = _credit_note_filters(start, end)
    rows = db.execute_query(
        f"""
        SELECT {_credit_note_amount_sql()} AS total
        FROM credit_notes n
        JOIN sales s ON s.id = n.sale_id
        {clause} {_CREDIT_NOTE_SCOPE}
        """,
        tuple(params),
    )
    return float(rows[0]["total"] or 0) if rows else 0.0


class ReportsService:
    """Resúmenes de ingresos, costos, ganancias y gastos por período."""

    def __init__(self, db: DatabaseManager):
        self.db = db

    # ---------- ventas ----------

    def summary(self, start: str = "", end: str = "") -> dict:
        """Ingresos, número de ventas, costo y ganancia bruta del período.

        Ingresos en base a caja: las ventas a crédito no suman al momento de la
        venta; suman conforme se reciben los abonos. El costo de fabricación se
        cuenta en la fecha de la venta, salvo encargos/apartados, que lo
        reconocen en la fecha de entrega (y no cuentan si están pendientes).
        """
        clause, params = _date_filters(start, end)
        clause += " " + _exclusion_clause()
        rows = self.db.execute_query(
            f"""
            SELECT
                (SELECT COUNT(*) FROM sales s {clause}) AS sale_count,
                (SELECT COALESCE(SUM(CASE
                    WHEN COALESCE(s.payment_method, '') = '{CREDIT_METHOD}' THEN 0
                    ELSE s.total END), 0)
                 FROM sales s {clause}) AS ingresos_ventas,
                (SELECT COALESCE(SUM(s.tax_amount), 0)
                 FROM sales s {clause}) AS tax_amount
            """,
            tuple(params * 3),
        )
        cost_clause, cost_params = _cost_filters(start, end)
        cost_rows = self.db.execute_query(
            f"""
            SELECT COALESCE(SUM(i.quantity * i.unit_cost), 0) AS cost
            FROM sale_items i JOIN sales s ON i.sale_id = s.id
            {_COST_JOIN}
            {cost_clause}
            """,
            tuple(cost_params),
        )
        row = rows[0]
        notas = _credit_notes_total(self.db, start, end)
        ingresos = (float(row["ingresos_ventas"] or 0)
                    + _credit_payments_total(self.db, start, end) - notas)
        cost = float((cost_rows[0]["cost"] if cost_rows else 0) or 0)
        return {
            "sale_count": int(row["sale_count"] or 0),
            "ingresos": round(ingresos, 2),
            "tax_amount": round(float(row["tax_amount"] or 0), 2),
            "cost": round(cost, 2),
            "credit_notes": round(notas, 2),
            "gross_profit": round(ingresos - cost, 2),
        }

    def daily_breakdown(self, start: str = "", end: str = "") -> list[dict]:
        """Desglose diario: ventas, ingresos (base caja), costo fab., gastos y ganancia."""
        clause, params = _date_filters(start, end)
        clause += " " + _exclusion_clause()
        sales_rows = self.db.execute_query(
            f"""
            SELECT substr(s.created_at, 1, 10) AS day,
                   COUNT(*) AS sale_count,
                   COALESCE(SUM(CASE
                       WHEN COALESCE(s.payment_method, '') = '{CREDIT_METHOD}' THEN 0
                       ELSE s.total END), 0) AS ingresos
            FROM sales s {clause}
            GROUP BY day ORDER BY day
            """,
            tuple(params),
        )
        cost_clause, cost_params = _cost_filters(start, end)
        cost_rows = self.db.execute_query(
            f"""
            SELECT substr({_COST_DATE}, 1, 10) AS day,
                   COALESCE(SUM(i.quantity * i.unit_cost), 0) AS cost
            FROM sale_items i JOIN sales s ON s.id = i.sale_id
            {_COST_JOIN}
            {cost_clause}
            GROUP BY day
            """,
            tuple(cost_params),
        )
        cp_clause, cp_params = _credit_payment_filters(start, end)
        credit_rows = self.db.execute_query(
            f"""
            SELECT substr(created_at, 1, 10) AS day,
                   COALESCE(SUM(amount), 0) AS abonos
            FROM credit_payments {cp_clause}
            GROUP BY day
            """,
            tuple(cp_params),
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
        note_clause, note_params = _credit_note_filters(start, end)
        note_rows = self.db.execute_query(
            f"""
            SELECT substr(n.created_at, 1, 10) AS day,
                   {_credit_note_amount_sql()} AS notas
            FROM credit_notes n
            JOIN sales s ON s.id = n.sale_id
            {note_clause} {_CREDIT_NOTE_SCOPE}
            GROUP BY day
            """,
            tuple(note_params),
        )
        costs = {row["day"]: float(row["cost"] or 0) for row in cost_rows}
        expenses = {row["day"]: float(row["expenses"] or 0) for row in expense_rows}
        credit = {row["day"]: float(row["abonos"] or 0) for row in credit_rows}
        notes = {row["day"]: float(row["notas"] or 0) for row in note_rows}
        sales = {row["day"]: row for row in sales_rows}
        result = []
        for day in sorted(set(sales) | set(costs) | set(expenses) | set(credit) | set(notes)):
            row = sales.get(day, {})
            ingresos = (float(row.get("ingresos") or 0)
                        + credit.get(day, 0.0) - notes.get(day, 0.0))
            cost = costs.get(day, 0.0)
            gastos = expenses.get(day, 0.0)
            result.append({
                "day": day,
                "sale_count": int(row.get("sale_count") or 0),
                "ingresos": round(ingresos, 2),
                "cost": round(cost, 2),
                "expenses": round(gastos, 2),
                "egresos": round(cost + gastos, 2),
                "net_profit": round(ingresos - cost - gastos, 2),
            })
        return result

    def monthly_breakdown(self, year: int) -> list[dict]:
        """Desglose mensual (12 filas) del año: ventas, ingresos (base caja),
        costo fab., gastos y ganancia."""
        excl = _exclusion_clause()
        sales_rows = self.db.execute_query(
            f"""
            SELECT CAST(substr(s.created_at, 6, 2) AS INTEGER) AS month,
                   COUNT(*) AS sale_count,
                   COALESCE(SUM(CASE
                       WHEN COALESCE(s.payment_method, '') = '{CREDIT_METHOD}' THEN 0
                       ELSE s.total END), 0) AS ingresos
            FROM sales s
            WHERE substr(s.created_at, 1, 4) = ? {excl}
            GROUP BY month
            """,
            (str(year),),
        )
        cost_rows = self.db.execute_query(
            f"""
            SELECT CAST(substr({_COST_DATE}, 6, 2) AS INTEGER) AS month,
                   COALESCE(SUM(i.quantity * i.unit_cost), 0) AS cost
            FROM sale_items i JOIN sales s ON s.id = i.sale_id
            {_COST_JOIN}
            WHERE substr({_COST_DATE}, 1, 4) = ? {excl} {_COST_SCOPE}
            GROUP BY month
            """,
            (str(year),),
        )
        credit_rows = self.db.execute_query(
            f"""
            SELECT CAST(substr(created_at, 6, 2) AS INTEGER) AS month,
                   COALESCE(SUM(amount), 0) AS abonos
            FROM credit_payments
            WHERE substr(created_at, 1, 4) = ? {_EXCLUDED_CREDIT_ACCOUNTS}
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
        note_rows = self.db.execute_query(
            f"""
            SELECT CAST(substr(n.created_at, 6, 2) AS INTEGER) AS month,
                   {_credit_note_amount_sql()} AS notas
            FROM credit_notes n
            JOIN sales s ON s.id = n.sale_id
            WHERE substr(n.created_at, 1, 4) = ? {_CREDIT_NOTE_SCOPE}
            GROUP BY month
            """,
            (str(year),),
        )
        costs = {row["month"]: float(row["cost"] or 0) for row in cost_rows}
        expenses = {row["month"]: float(row["expenses"] or 0) for row in expense_rows}
        credit = {row["month"]: float(row["abonos"] or 0) for row in credit_rows}
        notes = {row["month"]: float(row["notas"] or 0) for row in note_rows}
        sales_by_month = {row["month"]: row for row in sales_rows}
        result = []
        for month in range(1, 13):
            row = sales_by_month.get(month, {})
            ingresos = (float(row.get("ingresos") or 0)
                        + credit.get(month, 0.0) - notes.get(month, 0.0))
            cost = costs.get(month, 0.0)
            gastos = expenses.get(month, 0.0)
            result.append({
                "month": month,
                "sale_count": int(row.get("sale_count") or 0),
                "ingresos": round(ingresos, 2),
                "cost": round(cost, 2),
                "expenses": round(gastos, 2),
                "egresos": round(cost + gastos, 2),
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
            monto = float(v["total"] or 0)
            es_credito = (v["payment_method"] or "").lower() == CREDIT_METHOD
            movimientos.append({
                "id": v["id"],
                "invoice_number": v["invoice_number"],
                "tipo": "CRÉDITO" if es_credito else "VENTA",
                "detalle": v["client_name"] or "Consumidor Final",
                "metodo": v["payment_method"] or "",
                "monto": round(monto, 2),
                "fecha": v["created_at"] or "",
            })

        cp_clause, cp_params = _credit_payment_filters(start, end_ventas, "cp.created_at")
        abonos = self.db.execute_query(
            f"""
            SELECT cp.id, cp.created_at AS fecha, cp.amount, cp.payment_method,
                   ca.invoice_number, c.name AS client_name
            FROM credit_payments cp
            JOIN credit_accounts ca ON ca.id = cp.credit_account_id
            LEFT JOIN clients c ON c.id = ca.client_id
            {cp_clause}
            ORDER BY cp.created_at DESC
            """,
            tuple(cp_params),
        )
        for a in abonos:
            detalle = a["client_name"] or "Cliente"
            if a["invoice_number"]:
                detalle = f"{detalle} — {a['invoice_number']}"
            movimientos.append({
                "id": a["id"],
                "invoice_number": a["invoice_number"] or "",
                "tipo": "ABONO",
                "detalle": detalle,
                "metodo": a["payment_method"] or "",
                "monto": round(float(a["amount"] or 0), 2),
                "fecha": a["fecha"] or "",
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

        note_clause, note_params = _credit_note_filters(start, end_ventas)
        notas = self.db.execute_query(
            f"""
            SELECT n.id, n.invoice_number, n.total, n.created_at AS fecha,
                   c.name AS client_name
            FROM credit_notes n
            JOIN sales s ON s.id = n.sale_id
            LEFT JOIN clients c ON c.id = s.client_id
            {note_clause} {_CREDIT_NOTE_SCOPE}
            ORDER BY n.created_at DESC
            """,
            tuple(note_params),
        )
        for n in notas:
            monto = float(n["total"] or 0)
            detalle = f"NC {n['invoice_number']}"
            if n["client_name"]:
                detalle = f"{detalle} — {n['client_name']}"
            movimientos.append({
                "id": n["id"],
                "invoice_number": n["invoice_number"] or "",
                "tipo": "NOTA",
                "detalle": detalle,
                "metodo": "nota crédito",
                "monto": round(-monto, 2),
                "fecha": n["fecha"] or "",
            })

        movimientos.sort(key=lambda m: m["fecha"] or "", reverse=True)
        return movimientos

    # ---------- combinado ----------

    def full_summary(self, start: str = "", end: str = "") -> dict:
        """Todo para las tarjetas: ingresos, egresos (costo + gastos) y ganancia neta."""
        sales = self.summary(start, end)
        expenses = self.expenses_total(start, end)
        result = dict(sales)
        result["expenses"] = round(expenses, 2)
        result["egresos"] = round(sales["cost"] + expenses, 2)
        result["net_profit"] = round(sales["gross_profit"] - expenses, 2)
        return result

    # ---------- notas de crédito ----------

    def reserve_credit_note_number(self) -> int:
        """Reserva atómicamente el siguiente consecutivo de nota de crédito.

        El diálogo lo usa para que el XML/PDF y el registro en la base usen el
        mismo número aunque haya varias cajas emitiendo a la vez.
        """
        with self.db.transaction() as connection:
            connection.execute(
                "INSERT INTO counters (name, value) VALUES ('credit_note', 1) "
                "ON CONFLICT(name) DO UPDATE SET value = value + 1")
            row = connection.execute(
                "SELECT value FROM counters WHERE name = 'credit_note'").fetchone()
            return int(row["value"]) if row else 1

    def create_credit_note(self, sale_id: int, motivo: str, razon: str,
                           codigo: str = "01", total: float = 0.0,
                           clave: str = "", estado: str = "PENDIENTE",
                           numero: int | None = None) -> int:
        """Crea un registro de nota de crédito y devuelve su id.

        Requiere que la venta exista. Si `numero` viene dado (reservado con
        `reserve_credit_note_number`) se usa ese consecutivo; si no, se reserva
        uno aquí.
        """
        sale = self.db.execute_query(
            "SELECT * FROM sales WHERE id = ?", (sale_id,))
        if not sale:
            raise ValueError(f"La venta {sale_id} no existe.")
        row = sale[0]
        nota_total = float(total or row["total"] or 0)
        if numero is None:
            numero = self.reserve_credit_note_number()
        numero_str = f"NC-{int(numero):05d}"
        from network.session import session
        with self.db.transaction() as connection:
            cursor = connection.execute(
                """
                INSERT INTO credit_notes (sale_id, invoice_number, client_id,
                    subtotal, tax_amount, total, motivo, razon, codigo_referencia,
                    estado, hacienda_key, hacienda_status, user_id, user_name,
                    station, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    COALESCE(?, datetime('now', 'localtime')))
                """,
                (sale_id, numero_str, row["client_id"], row["subtotal"],
                 row["tax_amount"], nota_total, motivo, razon, codigo,
                 estado, clave, "", session.user_id, session.user_name,
                 session.station, None),
            )
            # En ventas a crédito la nota reduce lo que el cliente debe: se
            # descuenta del total y del saldo de la cuenta por cobrar.
            if (row["payment_method"] or "").lower() == CREDIT_METHOD:
                connection.execute(
                    "UPDATE credit_accounts SET "
                    "total = MAX(0, total - ?), "
                    "balance = MAX(0, balance - ?), "
                    "status = CASE WHEN MAX(0, balance - ?) <= 0 "
                    "THEN 'pagada' ELSE status END, "
                    "updated_at = datetime('now', 'localtime') "
                    "WHERE sale_id = ?",
                    (nota_total, nota_total, nota_total, sale_id),
                )
            return cursor.lastrowid

    def get_credit_notes(self, start: str = "", end: str = "") -> list[dict]:
        clause = "WHERE 1 = 1"
        params: list[object] = []
        if start:
            clause += " AND n.created_at >= ?"
            params.append(start)
        if end:
            clause += " AND n.created_at <= ?"
            params.append(end)
        rows = self.db.execute_query(
            f"""SELECT n.*, s.invoice_number AS factura_original
                FROM credit_notes n LEFT JOIN sales s ON s.id = n.sale_id
                {clause} ORDER BY n.id DESC""",
            tuple(params),
        )
        return [dict(row) for row in rows]
