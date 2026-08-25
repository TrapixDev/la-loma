"""Documentos de venta: XML de Hacienda (respaldo) y PDF/imagen para imprimir."""

from .factura_service import (
    generar_documentos,
    reimprimir_factura,
    generar_nota_credito,
)
from .ticket import (
    ticket_html,
    imprimir_ticket,
    imprimir_ticket_venta,
    imprimir_prueba,
    get_printer_name,
    save_printer_name,
)

__all__ = [
    "generar_documentos",
    "reimprimir_factura",
    "generar_nota_credito",
    "ticket_html",
    "imprimir_ticket",
    "imprimir_ticket_venta",
    "imprimir_prueba",
    "get_printer_name",
    "save_printer_name",
]
