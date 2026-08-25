def format_currency(amount: float, currency: str = "CRC") -> str:
    """Formatea un monto como moneda (₡ o $) con separadores de miles."""
    if currency.upper() == "USD":
        return f"${amount:,.2f}"
    return f"₡{amount:,.2f}"


def calculate_totals(items: list[dict], exento: bool = False) -> dict:
    """Calcula subtotal, descuento, impuesto y total a partir de los items del carrito.

    Con `exento=True` (Factura Simplificada / Régimen de Tributación
    Simplificada) la venta no cobra impuestos: tax_amount = 0 y el total
    es subtotal - descuento.
    """
    subtotal = 0.0
    discount = 0.0
    tax_amount = 0.0
    for item in items:
        quantity = float(item.get("quantity", 1))
        unit_price = float(item.get("unit_price", 0))
        tax_rate = float(item.get("tax_rate", 0))
        item_discount = float(item.get("discount", 0))
        line_subtotal = quantity * unit_price
        subtotal += line_subtotal
        discount += item_discount
        if not exento:
            tax_amount += (line_subtotal - item_discount) * (tax_rate / 100)
    total = subtotal - discount + tax_amount
    return {
        "subtotal": round(subtotal, 2),
        "discount": round(discount, 2),
        "tax_amount": round(tax_amount, 2),
        "total": round(total, 2),
    }
