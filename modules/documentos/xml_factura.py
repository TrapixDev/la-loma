"""Construcción del payload de factura y del XML FEAT v4.3 de respaldo."""

import sys
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree as ET

NS = "http://tribunet.hacienda.gob.cr/docs/esquemas/2017/v4.3/facturaElectronica"
ROOT_TAG = "{http://tribunet.hacienda.gob.cr/docs/esquemas/2017/v4.3/facturaElectronica}FacturaElectronica"

# Campos extra del ticket (se guardan en app_config, no en hacienda_config).
EXTRAS_EMPRESA = {
    "email": "company_email",
    "iban": "company_iban",
    "sinpe": "company_sinpe",
    "logo": "company_logo",
}


def _raiz_app() -> Path:
    """Carpeta del .exe instalado o de la raíz del proyecto en modo fuente."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def logo_por_defecto() -> Path:
    """Logo del ticket: el PNG de la raíz (o junto al .exe)."""
    raiz = _raiz_app()
    for nombre in ("logo-colegio.png", "logo.png"):
        ruta = raiz / nombre
        if ruta.is_file():
            return ruta
    return raiz / "logo-colegio.png"


def _fmt(value) -> str:
    """Formatea a número plano (punto decimal, sin notación científica)."""
    try:
        num = float(value or 0)
    except (TypeError, ValueError):
        return str(value)
    if num == int(num):
        return str(int(num))
    return f"{num:.5f}".rstrip("0").rstrip(".")


def cargar_empresa(db) -> dict:
    """Datos de la empresa emisora (hacienda_config + extras para el ticket)."""
    config: dict = {}
    if db is None:
        return config
    try:
        rows = db.execute_query("SELECT * FROM hacienda_config WHERE id = 1") or []
        if rows:
            row = {str(key): value for key, value in rows[0].items()}
            config = {
                "company_name": row.get("company_name", ""),
                "company_id": row.get("company_id", ""),
                "phone": row.get("company_phone", ""),
                "address": row.get("company_address", ""),
                "activity_code": row.get("activity_code", ""),
                "branch": row.get("branch", "001"),
                "terminal": row.get("terminal", "001"),
            }
        else:
            for row in db.execute_query("SELECT key, value FROM hacienda_config"):
                config[str(row["key"])] = row["value"]
    except Exception:
        pass
    try:
        for clave, key in EXTRAS_EMPRESA.items():
            filas = db.execute_query(
                "SELECT value FROM app_config WHERE key = ?", (key,))
            if filas and str(filas[0]["value"] or "").strip():
                config[clave] = str(filas[0]["value"]).strip()
    except Exception:
        pass
    if not config.get("logo"):
        ruta_logo = logo_por_defecto()
        if ruta_logo.is_file():
            config["logo"] = str(ruta_logo)
    return config


def guardar_empresa_extra(db, email: str = "", iban: str = "",
                          sinpe: str = "", logo: str = "") -> None:
    """Guarda correo, IBAN, SINPE y logo del ticket en app_config.

    Los campos vacíos se guardan vacíos: el ticket los omite.
    """
    valores = {
        "company_email": email, "company_iban": iban,
        "company_sinpe": sinpe, "company_logo": logo,
    }
    for key, value in valores.items():
        try:
            db.execute_update(
                "INSERT OR REPLACE INTO app_config (key, value) VALUES (?, ?)",
                (key, str(value or "").strip()))
        except Exception:
            pass


def _item_attr(item, name, default=""):
    if isinstance(item, dict):
        return item.get(name, default)
    return getattr(item, name, default)


def build_factura_payload(company: dict, client, items: list, totals: dict,
                          consecutivo: str) -> dict:
    """Payload idéntico al enviado al proveedor de facturación electrónica."""
    detail = []
    for item in items:
        quantity = float(_item_attr(item, "quantity", 0) or 0)
        unit_price = float(_item_attr(item, "unit_price", 0) or 0)
        discount = float(_item_attr(item, "discount", 0) or 0)
        base = max(0.0, quantity * unit_price - discount)
        tax_rate = float(_item_attr(item, "tax_rate", 0) or 0)
        if tax_rate <= 0 and base > 0:
            tax_rate = (float(_item_attr(item, "tax_amount", 0) or 0) / base)
        line_tax = round(base * tax_rate / 100.0, 2)
        detail.append(
            {
                "codigo": _item_attr(item, "cabys_code") or "0000000000000",
                "cantidad": quantity,
                "detalle": _item_attr(item, "product_name"),
                "precio_unitario": unit_price,
                "monto_total": float(_item_attr(item, "total", 0) or 0),
                "impuesto": {
                    "codigo": "01" if tax_rate > 0 else "04",
                    "tarifa": tax_rate,
                    "monto": line_tax,
                },
            }
        )

    return {
        "clave": "",
        "consecutivo": consecutivo,
        "fecha_emision": datetime.now().strftime("%Y-%m-%dT%H:%M:%S-06:00"),
        "emisor": {
            "nombre": company.get("company_name", ""),
            "identificacion": company.get("company_id", ""),
            "telefono": company.get("phone", ""),
            "direccion": company.get("address", ""),
            "actividad": company.get("activity_code", ""),
        },
        "receptor": {
            "tipo_identificacion": getattr(client, "id_type", "06"),
            "numero_identificacion": getattr(client, "id_number", "0"),
            "nombre": getattr(client, "name", "Consumidor Final"),
            "correo": getattr(client, "email", ""),
            "telefono": getattr(client, "phone", ""),
        },
        "detalle": detail,
        "resumen": {
            "codigo_moneda": "CRC",
            "tipo_cambio": "1",
            "subtotal": float(totals.get("subtotal", 0) or 0),
            "total_descuento": float(totals.get("discount", 0) or 0),
            "total_impuesto": float(totals.get("tax_amount", 0) or 0),
            "total_factura": float(totals.get("total", 0) or 0),
        },
    }


def build_factura_xml(payload: dict, clave: str = "", medio_pago: str = "01") -> str:
    """XML <FacturaElectronica> v4.3 como texto UTF-8 (respaldo/archivo local)."""
    root = ET.Element(ROOT_TAG)
    root.set("xmlns", NS)
    _text(root, "Clave", clave)
    actividad = (payload.get("emisor") or {}).get("actividad", "")
    if actividad:
        _text(root, "CodigoActividad", actividad)
    _text(root, "NumeroConsecutivo", payload.get("consecutivo", ""))
    _text(root, "FechaEmision", payload.get("fecha_emision", ""))
    _text(root, "CondicionVenta", "01")
    _text(root, "MedioPago", medio_pago if medio_pago in ("01", "02", "03", "04") else "01")

    emisor = payload.get("emisor") or {}
    emisor_el = _sub(root, "Emisor")
    _text(emisor_el, "Nombre", emisor.get("nombre", "") or "POS La Loma")
    identificacion = _sub(emisor_el, "Identificacion")
    _text(identificacion, "Tipo", "01")
    _text(identificacion, "Numero", emisor.get("identificacion", ""))
    if emisor.get("direccion"):
        _text(_sub(emisor_el, "Ubicacion"), "OtrasSenas", emisor["direccion"])
    if emisor.get("telefono"):
        _text(_sub(emisor_el, "Telefono"), "NumTelefono", emisor["telefono"])

    receptor = payload.get("receptor") or {}
    receptor_el = _sub(root, "Receptor")
    _text(receptor_el, "Nombre", receptor.get("nombre", "Consumidor Final"))
    receptor_id = _sub(receptor_el, "Identificacion")
    _text(receptor_id, "Tipo", receptor.get("tipo_identificacion", "06"))
    _text(receptor_id, "Numero", receptor.get("numero_identificacion", "0"))
    if receptor.get("correo"):
        _text(receptor_el, "CorreoElectronico", receptor["correo"])

    detalle = _sub(root, "DetalleServicio")
    for index, line in enumerate(payload.get("detalle", []), start=1):
        linea = _sub(detalle, "LineaDetalle")
        _text(linea, "NumeroLinea", str(index))
        _text(linea, "Cantidad", _fmt(line.get("cantidad")))
        _text(linea, "UnidadMedida", "Unid")
        _text(linea, "Detalle", line.get("detalle", ""))
        _text(linea, "PrecioUnitario", _fmt(line.get("precio_unitario")))
        _text(linea, "MontoTotal", _fmt(line.get("monto_total")))
        impuesto = line.get("impuesto") or {}
        if impuesto.get("monto"):
            _impuesto = _sub(linea, "Impuesto")
            _text(_impuesto, "Codigo", impuesto.get("codigo", "01"))
            tarifa = float(impuesto.get("tarifa", 0) or 0)
            _text(_impuesto, "CodigoTarifa", "08" if tarifa > 5 else "04")
            _text(_impuesto, "Tarifa", _fmt(tarifa / 100.0))
            _text(_impuesto, "Monto", _fmt(impuesto.get("monto")))

    resumen = payload.get("resumen") or {}
    _resumen = _sub(root, "ResumenFactura")
    _text(_resumen, "CodigoMoneda", resumen.get("codigo_moneda", "CRC"))
    _text(_resumen, "TipoCambio", _fmt(resumen.get("tipo_cambio", "1")))
    _text(_resumen, "TotalVenta", _fmt(resumen.get("subtotal")))
    _text(_resumen, "TotalDescuento", _fmt(resumen.get("total_descuento")))
    _text(_resumen, "TotalImpuesto", _fmt(resumen.get("total_impuesto")))
    _text(_resumen, "TotalComprobante", _fmt(resumen.get("total_factura")))

    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="UTF-8", xml_declaration=True).decode("utf-8")


def _sub(parent, tag: str) -> ET.Element:
    return ET.SubElement(parent, tag)


def _text(parent, tag: str, value) -> None:
    element = ET.SubElement(parent, tag)
    element.text = "" if value is None else str(value)