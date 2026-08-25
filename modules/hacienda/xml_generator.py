import random
from datetime import datetime

from database.models import Client, Sale, SaleItem


class XMLGenerator:
    """Genera la clave de 50 dígitos y el payload v4.4 para el proveedor FE."""

    def __init__(self, company_config: dict):
        self.company_config = company_config

    def generate_key(self, date, consecutive: str, terminal: str, branch: str) -> str:
        date_text = self._format_date(date)
        company_id = str(self.company_config.get("company_id", "") or "").zfill(12)
        prefix = (
            "506"
            + date_text
            + company_id
            + str(consecutive).zfill(10)
            + str(branch).zfill(3)
            + str(terminal).zfill(3)
        )
        padding = 50 - len(prefix)
        if padding < 0:
            raise ValueError("La clave excede 50 dígitos")
        random_digits = "".join(str(random.randint(0, 9)) for _ in range(padding))
        return prefix + random_digits

    def build_invoice_payload(self, sale: Sale, sale_items: list[SaleItem],
                              client: Client | None, company_config: dict) -> dict:
        company = company_config or self.company_config
        if client is None:
            client = Client(id_type="02", id_number="000000000", name="Consumidor Final")
        payment_methods = ([{"tipo": "02"}]
                           if "tarjeta" in (sale.payment_method or "").lower()
                           else [{"tipo": "01"}])
        line_items = [self._build_line_item(index, item)
                      for index, item in enumerate(sale_items, start=1)]
        return {
            "voucher_type": "01",
            "situation": "1",
            "issued_at": self._parse_issued_at(sale.created_at),
            "issuer_activity_code": company.get("activity_code", ""),
            "sale_condition": "01",
            "currency_code": "CRC",
            "exchange_rate": "1.00000",
            "payment_methods": payment_methods,
            "receiver": {
                "id_type": client.id_type or "02",
                "id_number": client.id_number,
                "name": client.name,
                "emails": [client.email] if client.email else [],
            },
            "line_items": line_items,
        }

    def _build_line_item(self, line_number: int, item: SaleItem) -> dict:
        unit_price = round(float(item.unit_price), 5)
        sub_total = round(float(item.quantity) * unit_price, 5)
        base_imponible = round(sub_total - float(item.discount), 5)
        tax_code, tariff, tax_monto = self._tax_details(item, base_imponible)
        impuesto_neto = round(tax_monto, 5)
        total_line_amount = round(base_imponible + impuesto_neto, 5)
        return {
            "line_number": line_number,
            "cabys_code": getattr(item, "cabys_code", "") or "",
            "detail": item.product_name,
            "quantity": float(item.quantity),
            "unit_of_measure": getattr(item, "unit_of_measure", "") or "Unid",
            "unit_price": f"{unit_price:.5f}",
            "total_amount": f"{base_imponible:.5f}",
            "sub_total": f"{sub_total:.5f}",
            "base_imponible": f"{base_imponible:.5f}",
            "taxes": [{"codigo": "01", "codigoTarifa": tax_code,
                       "tarifa": tariff, "monto": f"{tax_monto:.5f}"}],
            "impuesto_neto": f"{impuesto_neto:.5f}",
            "total_line_amount": f"{total_line_amount:.5f}",
        }

    def _tax_details(self, item: SaleItem, base_imponible: float) -> tuple[str, float, float]:
        rate = float(getattr(item, "tax_rate", 0) or 0)
        if rate <= 0:
            rate = (float(item.tax_amount) / base_imponible) if base_imponible else 0.0
        rate = round(rate, 4)
        if 0.125 <= rate <= 0.135:
            return "08", 0.13, round(base_imponible * 0.13, 5)
        if 0.035 <= rate <= 0.05:
            return "04", 0.04, round(base_imponible * 0.04, 5)
        return "10", 0.0, 0.0

    @staticmethod
    def _format_date(date) -> str:
        if isinstance(date, datetime):
            return date.strftime("%Y%m%d")
        return str(date).replace("-", "").replace(":", "").replace(" ", "")[:8]

    @staticmethod
    def _parse_issued_at(created_at) -> str:
        if not created_at:
            created_at = datetime.now()
        if isinstance(created_at, datetime):
            return created_at.strftime("%Y-%m-%dT%H:%M:%S-06:00")
        text = str(created_at).strip()
        if "T" not in text:
            text = text.replace(" ", "T")
        return text if text.endswith("-06:00") else f"{text}-06:00"
