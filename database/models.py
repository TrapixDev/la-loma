from dataclasses import dataclass, field


@dataclass
class Category:
    id: int = 0
    name: str = ""
    description: str = ""
    color: str = "#3498db"
    icon: str = ""
    image_path: str = ""
    active: bool = True
    created_at: str = ""
    updated_at: str = ""


@dataclass
class Product:
    id: int = 0
    code: str = ""
    barcode: str = ""
    name: str = ""
    description: str = ""
    category_id: int | None = None
    cost_price: float = 0.0
    sale_price: float = 0.0
    stock_quantity: float = 0.0
    min_stock: float = 0.0
    unit_of_measure: str = "Unid"
    wood_type: str = ""
    cabys_code: str = ""
    tax_type: str = "gravado"
    tax_rate: float = 13.0
    active: bool = True
    image_path: str = ""
    category_name: str = ""


@dataclass
class Client:
    id: int = 0
    id_type: str = "02"
    id_number: str = ""
    name: str = ""
    email: str = ""
    phone: str = ""
    address: str = ""
    province: str = ""
    canton: str = ""
    district: str = ""
    activity_code: str = ""


@dataclass
class SaleItem:
    id: int = 0
    sale_id: int = 0
    product_id: int = 0
    product_name: str = ""
    quantity: float = 1.0
    unit_price: float = 0.0
    unit_cost: float = 0.0
    discount: float = 0.0
    tax_amount: float = 0.0
    total: float = 0.0


@dataclass
class Sale:
    id: int = 0
    invoice_number: str = ""
    client_id: int | None = None
    client_name: str = ""
    subtotal: float = 0.0
    discount: float = 0.0
    tax_amount: float = 0.0
    total: float = 0.0
    payment_method: str = "efectivo"
    cash_received: float = 0.0
    change_amount: float = 0.0
    payment_details: str = ""
    invoice_type: str = "general"
    sale_reference: str = ""
    currency: str = "CRC"
    exchange_rate: float = 0.0
    status: str = "completada"
    hacienda_key: str = ""
    hacienda_status: str = ""
    electronic_invoice: bool = False
    excluir_reporte: bool = False
    station: str = ""
    user_id: int | None = None
    user_name: str = ""
    created_at: str | None = None
    items: list[SaleItem] = field(default_factory=list)


@dataclass
class Expense:
    id: int = 0
    expense_date: str = ""
    category: str = ""
    description: str = ""
    amount: float = 0.0
    payment_method: str = "efectivo"
    user_id: int | None = None
    user_name: str = ""
    station: str = ""
    created_at: str = ""


@dataclass
class CreditAccount:
    id: int = 0
    sale_id: int = 0
    client_id: int = 0
    invoice_number: str = ""
    total: float = 0.0
    amount_paid: float = 0.0
    balance: float = 0.0
    status: str = "pendiente"
    notes: str = ""
    created_at: str = ""
    updated_at: str = ""
    client_name: str = ""
    client_id_number: str = ""
    client_phone: str = ""


@dataclass
class CreditPayment:
    id: int = 0
    credit_account_id: int = 0
    amount: float = 0.0
    payment_method: str = "efectivo"
    payment_details: str = ""
    notes: str = ""
    payment_reference: str = ""
    user_id: int | None = None
    user_name: str = ""
    created_at: str = ""
    client_name: str = ""
    invoice_number: str = ""


@dataclass
class CreditPaymentImage:
    id: int = 0
    payment_id: int = 0
    image_path: str = ""
    description: str = ""
    is_cover: bool = False
    created_at: str = ""
