"""Sesión del usuario autenticado en el cliente del POS."""

from config import Config


class Session:
    """Estado de sesión: token, usuario y estación (una por aplicación)."""

    def __init__(self) -> None:
        self.token: str = ""
        self.user_id: int | None = None
        self.user_name: str = ""
        self.station: str = Config.STATION

    def set(self, token: str, user_id: int, user_name: str, station: str = "") -> None:
        self.token = token
        self.user_id = user_id
        self.user_name = user_name
        if station:
            self.station = station

    def clear(self) -> None:
        self.token = ""
        self.user_id = None
        self.user_name = ""

    @property
    def authenticated(self) -> bool:
        return bool(self.token)


session = Session()
