from database.db_manager import DatabaseManager
from database.models import Category


class CategoryService:
    """Servicio de CRUD para categorías de productos."""

    def __init__(self, db: DatabaseManager):
        self.db = db

    def get_all(self, active_only: bool = True) -> list[Category]:
        sql = "SELECT * FROM categories"
        params: list[object] = []
        if active_only:
            sql += " WHERE active = 1"
        sql += " ORDER BY name"
        rows = self.db.execute_query(sql, tuple(params))
        return [Category(**row) for row in rows]

    def get_by_id(self, category_id: int) -> Category | None:
        rows = self.db.execute_query("SELECT * FROM categories WHERE id = ?", (category_id,))
        return Category(**rows[0]) if rows else None

    def create(self, category: Category) -> int:
        return self.db.execute_insert(
            "INSERT INTO categories (name, description, color, icon, image_path, active) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (category.name, category.description, category.color, category.icon,
             category.image_path, int(category.active)),
        )

    def update(self, category: Category) -> bool:
        return self.db.execute_update(
            "UPDATE categories SET name = ?, description = ?, color = ?, icon = ?, "
            "image_path = ?, active = ?, updated_at = datetime('now', 'localtime') WHERE id = ?",
            (category.name, category.description, category.color, category.icon,
             category.image_path, int(category.active), category.id),
        )

    def delete(self, category_id: int) -> bool:
        return self.db.execute_update(
            "UPDATE categories SET active = 0, updated_at = datetime('now', 'localtime') "
            "WHERE id = ?",
            (category_id,),
        )

    def get_product_count(self, category_id: int) -> int:
        rows = self.db.execute_query(
            "SELECT COUNT(*) AS total FROM products WHERE category_id = ? AND active = 1",
            (category_id,),
        )
        return rows[0]["total"] if rows else 0
