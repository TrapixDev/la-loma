"""XML <NotaCreditoElectronica> v4.3 de respaldo (estilo FEAT).

Referencia la factura original mediante InformacionReferencia. Usa
xml.etree (stdlib) igual que la factura de respaldo.
"""

from datetime import datetime
from xml.etree import ElementTree as ET

NS = "http://tribunet.hacienda.gob.cr/docs/esquemas/2017/v4.3/notaCreditoElectronica"
ROOT_TAG = "{http://tribunet.hacienda.gob.cr/docs/esquemas/2017/v4.3/notaCreditoElectronica}NotaCreditoElectronica"

# Códigos de motivo de la referencia (Codigo)
MOTIVOS = {
    "01": "Anula documento de referencia",
    "02": "Corrige texto de documento de referencia",
    "04": "Referencia a otro documento",
    "05": "Sustituye comprobante provisional",
    "06": "Devolución de mercancía",
    "09": "Nota de crédito financiera",
    "99": "Otros",
}


def _fmt(value) -> str:
    try:
        num = float(value or 0)
    except (TypeError, ValueError):
        return str(value)
    if num == int(num):
        return str(int(num))
    return f"{num:.5f}".rstrip("0").rstrip(".")


def build_nota_credito_payload(company: dict, sale, items: list,
                               totals: dict, consecutivo: str,
                               referencia: dict, motivo: str = "",
                               cliente=None) -> dict:
    """Payload de la nota de crédito, reutilizando la data de la venta original."""
    detail = []
    for item in items:
        quantity = float(getattr(item, "quantity", 0) or 0)
        unit_price = float(getattr(item, "unit_price", 0) or 0)
        discount = float(getattr(item, "discount", 0) or 0)
        base = max(0.0, quantity * unit_price - discount)
        rate = float(getattr(item, "tax_rate", 0) or 0)
        if rate <= 0 and base > 0:
            rate = (float(getattr(item, "tax_amount", 0) or 0) / base)
        line_tax = round(base * rate / 100.0, 2)
        detail.append({
            "codigo": getattr(item, "cabys_code", "") or "0000000000000",
            "cantidad": quantity,
            "detalle": getattr(item, "product_name", ""),
            "precio_unitario": unit_price,
            "monto_total": float(getattr(item, "total", 0) or 0),
            "impuesto": {"codigo": "01" if rate > 0 else "04",
                         "tarifa": rate, "monto": line_tax},
        })

    if cliente is None:
        cliente = {"id_type": "06", "id_number": "0", "name": "Consumidor Final"}
    return {
        "clave": "",
        "consecutivo": consecutivo,
        "fecha_emision": datetime.now().strftime("%Y-%m-%dT%H:%M:%S-06:00"),
        "referencia": referencia,
        "razon": motivo or MOTIVOS.get(str(referencia.get("codigo", "01")), ""),
        "emisor": {
            "nombre": company.get("company_name", ""),
            "identificacion": company.get("company_id", ""),
            "telefono": company.get("phone", ""),
            "direccion": company.get("address", ""),
            "actividad": company.get("activity_code", ""),
        },
        "receptor": {
            "tipo_identificacion": getattr(cliente, "id_type", "06"),
            "numero_identificacion": getattr(cliente, "id_number", "0"),
            "nombre": getattr(cliente, "name", "Consumidor Final"),
            "correo": getattr(cliente, "email", ""),
        },
        "detalle": detail,
        "resumen": {
            "codigo_moneda": "CRC",
            "tipo_cambio": "1",
            "subtotal": float(getattr(sale, "subtotal", 0) or 0),
            "total_descuento": float(getattr(sale, "discount", 0) or 0),
            "total_impuesto": float(getattr(sale, "tax_amount", 0) or 0),
            "total_factura": float(getattr(sale, "total", 0) or 0),
        },
    }


def build_nota_credito_xml(payload: dict, clave: str = "") -> str:
    """XML <NotaCreditoElectronica> v4.3 como texto UTF-8."""
    root = ET.Element(ROOT_TAG)
    root.set("xmlns", NS)
    _text(root, "Clave", clave)
    actividad = (payload.get("emisor") or {}).get("actividad", "")
    if actividad:
        _text(root, "CodigoActividad", actividad)
    _text(root, "NumeroConsecutivo", payload.get("consecutivo", ""))
    _text(root, "FechaEmision", payload.get("fecha_emision", ""))
    _text(root, "CondicionVenta", "01")

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

    referencia = payload.get("referencia") or {}
    _info = _sub(root, "InformacionReferencia")
    _text(_info, "TipoDoc", referencia.get("tipo_doc", "01"))
    _text(_info, "Numero", referencia.get("numero", ""))
    _text(_info, "FechaEmision", referencia.get("fecha_emision", ""))
    _text(_info, "Codigo", referencia.get("codigo", "01"))
    _text(_info, "Razon", payload.get("razon", ""))

    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="UTF-8", xml_declaration=True).decode("utf-8")


def _sub(parent, tag: str) -> ET.Element:
    return ET.SubElement(parent, tag)


def _text(parent, tag: str, value) -> None:
    element = ET.SubElement(parent, tag)
    element.text = "" if value is None else str(value)