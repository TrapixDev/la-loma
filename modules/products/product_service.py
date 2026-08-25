from database.db_manager import DatabaseManager
from database.models import Product

SELECT_PRODUCTS = """
SELECT p.id, p.code, p.barcode, p.name, p.description, p.category_id,
       p.cost_price, p.sale_price, p.stock_quantity, p.min_stock,
       p.unit_of_measure, p.wood_type, p.cabys_code, p.tax_type, p.tax_rate,
       p.active, p.image_path, c.name AS category_name
FROM products p
LEFT JOIN categories c ON c.id = p.category_id
"""


class ProductService:
    """Servicio de CRUD para productos."""

    def __init__(self, db: DatabaseManager):
        self.db = db

    def get_all(self, category_id: int | None = None, active_only: bool = True) -> list[Product]:
        sql = SELECT_PRODUCTS
        conditions: list[str] = []
        params: list[object] = []
        if active_only:
            conditions.append("p.active = 1")
        if category_id is not None:
            conditions.append("p.category_id = ?")
            params.append(category_id)
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        sql += " ORDER BY p.name"
        rows = self.db.execute_query(sql, tuple(params))
        return [Product(**row) for row in rows]

    def get_by_id(self, product_id: int) -> Product | None:
        rows = self.db.execute_query(SELECT_PRODUCTS + " WHERE p.id = ?", (product_id,))
        return Product(**rows[0]) if rows else None

    def search(self, query: str, category_id: int | None = None) -> list[Product]:
        sql = SELECT_PRODUCTS + " WHERE (p.name LIKE ? OR p.code LIKE ? OR p.wood_type LIKE ?)"
        pattern = f"%{query}%"
        params: list[object] = [pattern, pattern, pattern]
        if category_id is not None:
            sql += " AND p.category_id = ?"
            params.append(category_id)
        sql += " ORDER BY p.name"
        rows = self.db.execute_query(sql, tuple(params))
        return [Product(**row) for row in rows]

    def create(self, product: Product) -> int:
        return self.db.execute_insert(
            "INSERT INTO products (code, barcode, name, description, category_id, "
            "cost_price, sale_price, stock_quantity, min_stock, unit_of_measure, "
            "wood_type, cabys_code, tax_type, tax_rate, active, image_path) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (product.code, product.barcode or None, product.name, product.description,
             product.category_id, product.cost_price, product.sale_price,
             product.stock_quantity, product.min_stock, product.unit_of_measure,
             product.wood_type, product.cabys_code, product.tax_type,
             product.tax_rate, int(product.active), product.image_path),
        )

    def update(self, product: Product) -> bool:
        return self.db.execute_update(
            "UPDATE products SET code = ?, barcode = ?, name = ?, description = ?, "
            "category_id = ?, cost_price = ?, sale_price = ?, stock_quantity = ?, "
            "min_stock = ?, unit_of_measure = ?, wood_type = ?, cabys_code = ?, "
            "tax_type = ?, tax_rate = ?, active = ?, image_path = ?, "
            "updated_at = datetime('now', 'localtime') WHERE id = ?",
            (product.code, product.barcode, product.name, product.description,
             product.category_id, product.cost_price, product.sale_price,
             product.stock_quantity, product.min_stock, product.unit_of_measure,
             product.wood_type, product.cabys_code, product.tax_type,
             product.tax_rate, int(product.active), product.image_path,
             product.id),
        )

    def delete(self, product_id: int) -> bool:
        return self.db.execute_update(
            "UPDATE products SET active = 0, updated_at = datetime('now', 'localtime') "
            "WHERE id = ?",
            (product_id,),
        )
