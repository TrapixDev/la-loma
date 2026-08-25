from database.db_manager import DatabaseManager
from database.models import Client


class ClientService:
    """Servicio de CRUD para clientes."""

    def __init__(self, db: DatabaseManager):
        self.db = db

    def get_all(self) -> list[Client]:
        rows = self.db.execute_query("SELECT * FROM clients ORDER BY name")
        return [Client(**row) for row in rows]

    def get_by_id(self, client_id: int) -> Client | None:
        rows = self.db.execute_query("SELECT * FROM clients WHERE id = ?", (client_id,))
        return Client(**rows[0]) if rows else None

    def get_by_id_number(self, id_number: str) -> Client | None:
        rows = self.db.execute_query("SELECT * FROM clients WHERE id_number = ?", (id_number,))
        return Client(**rows[0]) if rows else None

    def create(self, client: Client) -> int:
        return self.db.execute_insert(
            "INSERT INTO clients (id_type, id_number, name, email, phone, address, "
            "province, canton, district, activity_code) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (client.id_type, client.id_number, client.name, client.email, client.phone,
             client.address, client.province, client.canton, client.district,
             client.activity_code),
        )

    def update(self, client: Client) -> bool:
        return self.db.execute_update(
            "UPDATE clients SET id_type = ?, id_number = ?, name = ?, email = ?, "
            "phone = ?, address = ?, province = ?, canton = ?, district = ?, "
            "activity_code = ? WHERE id = ?",
            (client.id_type, client.id_number, client.name, client.email, client.phone,
             client.address, client.province, client.canton, client.district,
             client.activity_code, client.id),
        )

    def search(self, query: str) -> list[Client]:
        pattern = f"%{query}%"
        rows = self.db.execute_query(
            "SELECT * FROM clients WHERE name LIKE ? OR id_number LIKE ? ORDER BY name",
            (pattern, pattern),
        )
        return [Client(**row) for row in rows]
