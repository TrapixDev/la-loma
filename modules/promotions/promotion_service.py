"""Motor de promociones: conjuntos, volumen, método de pago y financiamiento.

Tipos y `params` (JSON):
- bundle:   {"product_id": A, "discount_product_id": B, "percent": 15}
            si el carrito lleva A, aplica 15% de descuento sobre la línea de B.
- volume:   {"product_id": A, "tiers": [[4, 10], [6, 20]]}
            según la cantidad de A en el carrito aplica el mejor tramo.
- payment:  {"methods": ["efectivo", "sinpe"], "percent": 5}
            descuento sobre el total (tras descuentos de producto).
- financing:{"min_total": 300000, "months": [3, 6, 12]}
            plan informativo "meses sin intereses" para ventas a crédito.

Regla de acumulación: por línea gana el mejor descuento (bundle o volumen, no
se suman); el descuento por método de pago se aplica sobre el total ya
rebajado. El pago mixto no recibe descuento por método.
"""

import json

from database.db_manager import DatabaseManager
from database.models import Promotion

PROMOTION_TYPES = ("bundle", "volume", "payment", "financing")
PAYMENT_METHODS = ("efectivo", "tarjeta", "sinpe", "transferencia")
TYPE_LABELS = {
    "bundle": "Conjunto (2 productos)",
    "volume": "Volumen por cantidad",
    "payment": "Método de pago",
    "financing": "Financiamiento",
}


def distribuir_descuento_pago(cart: list[dict], monto: float) -> list[dict]:
    """Devuelve una copia del carrito con un descuento repartido por línea.

    El reparto es proporcional al subtotal de cada línea (precio × cantidad
    menos descuentos ya aplicados) y el residuo de redondeo va a la última
    línea, para que la suma coincida exactamente con `monto`.
    """
    monto = round(float(monto or 0), 2)
    copia = [dict(item) for item in cart]
    if monto <= 0 or not copia:
        return copia
    bases = [
        max(0.0, round(float(item.get("unit_price") or 0)
                       * float(item.get("quantity") or 0)
                       - float(item.get("discount") or 0), 2))
        for item in copia
    ]
    total_base = round(sum(bases), 2)
    if total_base <= 0:
        return copia
    repartido = 0.0
    last = len(copia) - 1
    for index, item in enumerate(copia):
        base = bases[index]
        if index == last:
            extra = round(monto - repartido, 2)
        else:
            extra = round(monto * base / total_base, 2)
        extra = max(0.0, min(extra, base))
        if index != last:
            repartido = round(repartido + extra, 2)
        item["discount"] = round(float(item.get("discount") or 0) + extra, 2)
    return copia


class PromotionService:
    """CRUD de promociones y evaluación del carrito."""

    def __init__(self, db: DatabaseManager):
        self.db = db

    # ---------- CRUD ----------

    def get_all(self, active_only: bool = False) -> list[Promotion]:
        sql = "SELECT * FROM promotions"
        if active_only:
            sql += " WHERE active = 1"
        sql += " ORDER BY priority DESC, id"
        rows = self.db.execute_query(sql)
        return [Promotion(**row) for row in rows]

    def get_by_id(self, promotion_id: int) -> Promotion | None:
        rows = self.db.execute_query(
            "SELECT * FROM promotions WHERE id = ?", (promotion_id,))
        return Promotion(**rows[0]) if rows else None

    def create(self, name: str, promotion_type: str, params: dict,
               active: bool = True, priority: int = 0) -> int:
        name = (name or "").strip()
        if not name:
            raise ValueError("La promoción necesita un nombre.")
        self._validate(promotion_type, params)
        return self.db.execute_insert(
            "INSERT INTO promotions (name, type, params, active, priority) "
            "VALUES (?, ?, ?, ?, ?)",
            (name, promotion_type,
             json.dumps(params, ensure_ascii=False), int(bool(active)),
             int(priority)),
        )

    def update(self, promotion: Promotion) -> bool:
        name = (promotion.name or "").strip()
        if not name:
            raise ValueError("La promoción necesita un nombre.")
        params = self.params_dict(promotion)
        self._validate(promotion.type, params)
        return self.db.execute_update(
            "UPDATE promotions SET name = ?, type = ?, params = ?, active = ?, "
            "priority = ?, updated_at = datetime('now', 'localtime') WHERE id = ?",
            (name, promotion.type,
             json.dumps(params, ensure_ascii=False), int(bool(promotion.active)),
             int(promotion.priority or 0), promotion.id),
        )

    def delete(self, promotion_id: int) -> bool:
        return self.db.execute_update(
            "DELETE FROM promotions WHERE id = ?", (promotion_id,))

    def set_active(self, promotion_id: int, active: bool) -> bool:
        return self.db.execute_update(
            "UPDATE promotions SET active = ?, "
            "updated_at = datetime('now', 'localtime') WHERE id = ?",
            (int(bool(active)), promotion_id),
        )

    @staticmethod
    def params_dict(promotion: Promotion) -> dict:
        raw = promotion.params
        if isinstance(raw, dict):
            return raw
        try:
            data = json.loads(raw or "{}")
        except (TypeError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    # ---------- validación ----------

    def _validate(self, promotion_type: str, params: dict) -> None:
        if promotion_type not in PROMOTION_TYPES:
            raise ValueError(f"Tipo de promoción inválido: {promotion_type}")
        if not isinstance(params, dict):
            raise ValueError("Los parámetros de la promoción son inválidos.")

        def _percent(value, campo="porcentaje"):
            try:
                percent = float(value)
            except (TypeError, ValueError):
                raise ValueError(f"El {campo} debe ser un número.")
            if not 0 < percent <= 100:
                raise ValueError(f"El {campo} debe estar entre 0 y 100.")
            return percent

        def _product_id(value):
            try:
                product_id = int(value)
            except (TypeError, ValueError):
                raise ValueError("Seleccione un producto válido.")
            if product_id <= 0:
                raise ValueError("Seleccione un producto válido.")
            return product_id

        if promotion_type == "bundle":
            required = _product_id(params.get("product_id"))
            target = _product_id(params.get("discount_product_id"))
            if required == target:
                raise ValueError(
                    "El producto requerido y el descontado deben ser distintos.")
            _percent(params.get("percent"))
        elif promotion_type == "volume":
            _product_id(params.get("product_id"))
            tiers = params.get("tiers")
            if not isinstance(tiers, list) or not tiers:
                raise ValueError("Agregue al menos un tramo de volumen.")
            for tier in tiers:
                if (not isinstance(tier, (list, tuple)) or len(tier) != 2):
                    raise ValueError("Cada tramo debe ser [cantidad, porcentaje].")
                try:
                    qty = int(tier[0])
                except (TypeError, ValueError):
                    raise ValueError("La cantidad del tramo es inválida.")
                if qty < 2:
                    raise ValueError("La cantidad del tramo debe ser 2 o más.")
                _percent(tier[1])
        elif promotion_type == "payment":
            methods = params.get("methods") or []
            if not isinstance(methods, list) or not methods:
                raise ValueError("Seleccione al menos un método de pago.")
            invalid = [m for m in methods if str(m).lower() not in PAYMENT_METHODS]
            if invalid:
                raise ValueError(f"Método de pago inválido: {invalid[0]}")
            _percent(params.get("percent"))
        elif promotion_type == "financing":
            try:
                min_total = float(params.get("min_total"))
            except (TypeError, ValueError):
                raise ValueError("El monto mínimo debe ser un número.")
            if min_total <= 0:
                raise ValueError("El monto mínimo debe ser mayor a cero.")
            months = params.get("months") or []
            if not isinstance(months, list) or not months:
                raise ValueError("Indique al menos un plazo en meses.")
            for value in months:
                try:
                    if int(value) < 1:
                        raise ValueError
                except (TypeError, ValueError):
                    raise ValueError("Los plazos deben ser meses válidos.")

    # ---------- evaluación ----------

    def evaluate(self, cart: list[dict], payment_method: str = "",
                 es_credito: bool = False) -> dict:
        """Calcula los descuentos aplicables a un carrito.

        Devuelve line_discounts (índice del carrito → monto), discount_total,
        base, total, applied (detalle para auditoría) y financing (plan).
        """
        promotions = self.get_all(active_only=True)
        winners: dict[int, dict] = {}
        for promo in promotions:
            params = self.params_dict(promo)
            if promo.type == "bundle":
                self._apply_bundle(cart, promo, params, winners)
            elif promo.type == "volume":
                self._apply_volume(cart, promo, params, winners)

        line_totals = [
            round(float(item.get("unit_price") or 0)
                  * float(item.get("quantity") or 0), 2)
            for item in cart
        ]
        product_discount = round(
            sum(info["amount"] for info in winners.values()), 2)
        base = round(sum(line_totals) - product_discount, 2)

        applied = [
            {"name": info["name"], "type": info["type"],
             "amount": round(info["amount"], 2)}
            for _, info in sorted(winners.items())
        ]

        payment_discount = 0.0
        method = (payment_method or "").lower()
        if method and method != "mixto":
            for promo in promotions:
                if promo.type != "payment":
                    continue
                params = self.params_dict(promo)
                methods = [str(m).lower() for m in params.get("methods") or []]
                if method not in methods:
                    continue
                amount = round(base * float(params.get("percent") or 0) / 100, 2)
                if amount > 0:
                    payment_discount = round(payment_discount + amount, 2)
                    applied.append({
                        "name": promo.name, "type": "payment", "amount": amount})

        total = round(max(0.0, base - payment_discount), 2)

        financing = None
        if es_credito:
            for promo in promotions:
                if promo.type != "financing":
                    continue
                params = self.params_dict(promo)
                if total >= float(params.get("min_total") or 0):
                    months = [int(m) for m in params.get("months") or []]
                    financing = {
                        "promotion": promo.name,
                        "months": months,
                        "installments": {
                            str(m): round(total / m, 2) for m in months if m > 0},
                    }
                    applied.append({
                        "name": promo.name, "type": "financing", "amount": 0.0})
                    break

        return {
            "line_discounts": {
                index: round(info["amount"], 2) for index, info in winners.items()},
            "product_discount": product_discount,
            "payment_discount": payment_discount,
            "discount_total": round(product_discount + payment_discount, 2),
            "base": base,
            "total": total,
            "applied": applied,
            "financing": financing,
        }

    def _apply_bundle(self, cart: list[dict], promo: Promotion, params: dict,
                      winners: dict[int, dict]) -> None:
        required = int(params.get("product_id") or 0)
        target = int(params.get("discount_product_id") or 0)
        percent = float(params.get("percent") or 0)
        if required <= 0 or target <= 0 or percent <= 0:
            return
        if not any(int(item.get("product_id") or 0) == required
                   and float(item.get("quantity") or 0) >= 1 for item in cart):
            return
        for index, item in enumerate(cart):
            if int(item.get("product_id") or 0) != target:
                continue
            line = round(float(item.get("unit_price") or 0)
                         * float(item.get("quantity") or 0), 2)
            self._keep_best(winners, index, round(line * percent / 100, 2),
                            promo)
            break

    def _apply_volume(self, cart: list[dict], promo: Promotion, params: dict,
                      winners: dict[int, dict]) -> None:
        product_id = int(params.get("product_id") or 0)
        tiers = sorted(params.get("tiers") or [], key=lambda t: int(t[0]))
        if product_id <= 0 or not tiers:
            return
        for index, item in enumerate(cart):
            if int(item.get("product_id") or 0) != product_id:
                continue
            qty = float(item.get("quantity") or 0)
            percent = 0.0
            for tier in tiers:
                if qty >= int(tier[0]):
                    percent = float(tier[1])
            if percent <= 0:
                continue
            line = round(float(item.get("unit_price") or 0) * qty, 2)
            self._keep_best(winners, index, round(line * percent / 100, 2),
                            promo)

    @staticmethod
    def _keep_best(winners: dict[int, dict], index: int, amount: float,
                   promo: Promotion) -> None:
        """Por línea gana el mejor descuento (no se acumulan)."""
        current = winners.get(index)
        if current is None or amount > current["amount"]:
            winners[index] = {
                "amount": amount,
                "name": promo.name,
                "type": promo.type,
            }
