from typing import Any

import requests


class HaciendaClient:
    """Cliente HTTP para la API pública de Hacienda CR y el proveedor FE."""

    BASE_URL = "https://api.hacienda.go.cr"

    def __init__(self, provider_url: str = "", api_key: str = ""):
        self.provider_url = provider_url
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "POS-La-Loma/1.0"})

    def get_taxpayer_info(self, id_number: str) -> dict | None:
        return self._get(f"{self.BASE_URL}/fe/ae", params={"identificacion": id_number})

    def get_exchange_rate(self) -> dict | None:
        return self._get(f"{self.BASE_URL}/indicadores/tc/dolar")

    def search_cabys(self, query: str, limit: int = 10) -> list[dict]:
        data = self._get(f"{self.BASE_URL}/fe/cabys", params={"q": query, "top": limit})
        if data is None:
            return []
        if isinstance(data, list):
            return data
        return [data]

    def get_exoneration(self, authorization: str) -> dict | None:
        return self._get(f"{self.BASE_URL}/fe/ex", params={"autorizacion": authorization})

    def send_electronic_invoice(self, invoice_data: dict) -> dict | None:
        if not self.provider_url:
            print("HaciendaClient: no hay proveedor FE configurado (provider_url vacío)")
            return None
        headers = {"Authorization": f"Bearer {self.api_key}"}
        return self._post(f"{self.provider_url}/api/v1/public/vouchers",
                          json=invoice_data, headers=headers)

    def get_voucher_status(self, key: str) -> dict | None:
        if not self.provider_url:
            print("HaciendaClient: no hay proveedor FE configurado (provider_url vacío)")
            return None
        return self._get(f"{self.provider_url}/api/v1/public/vouchers/{key}")

    def cancel_voucher(self, key: str) -> dict | None:
        if not self.provider_url:
            print("HaciendaClient: no hay proveedor FE configurado (provider_url vacío)")
            return None
        return self._post(f"{self.provider_url}/api/v1/public/vouchers/{key}/cancel")

    def check_connection(self) -> bool:
        try:
            self.session.get(self.BASE_URL, timeout=5)
            return True
        except requests.RequestException:
            return False

    def _get(self, url: str, params: dict | None = None,
             headers: dict | None = None) -> dict | list | None:
        try:
            response = self.session.get(url, params=params, headers=headers, timeout=15)
            return self._handle(response)
        except requests.RequestException:
            return None

    def _post(self, url: str, json: dict | None = None,
              headers: dict | None = None) -> dict | None:
        try:
            response = self.session.post(url, json=json, headers=headers, timeout=30)
            return self._handle(response)
        except requests.RequestException:
            return None

    @staticmethod
    def _handle(response: requests.Response) -> dict | list | None:
        if response.status_code == 429:
            print("HaciendaClient: límite de peticiones alcanzado (429)")
            return None
        if response.status_code == 204:
            return {}
        if response.status_code >= 400:
            return None
        try:
            return response.json()
        except ValueError:
            return {"status_code": response.status_code, "text": response.text}
