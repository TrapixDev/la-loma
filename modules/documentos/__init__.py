"""Documentos de venta: XML de Hacienda (respaldo) y PDF/imagen para imprimir."""

from .factura_service import (
    generar_documentos,
    reimprimir_factura,
    generar_nota_credito,
)
from .ticket import (
    PAPER_LABEL,
    PAPER_MODES,
    PAPER_ROLL,
    PAPER_WINDOWS,
    elegir_papel,
    get_paper_mode,
    get_printer_name,
    get_show_dialog,
    imprimir_prueba,
    imprimir_ticket,
    imprimir_ticket_con_dialogo,
    imprimir_ticket_venta,
    previsualizar_ticket,
    save_paper_mode,
    save_printer_name,
    save_show_dialog,
    ticket_html,
)

__all__ = [
    "generar_documentos",
    "reimprimir_factura",
    "generar_nota_credito",
    "ticket_html",
    "elegir_papel",
    "imprimir_ticket",
    "imprimir_ticket_con_dialogo",
    "imprimir_ticket_venta",
    "imprimir_prueba",
    "previsualizar_ticket",
    "get_printer_name",
    "save_printer_name",
    "get_paper_mode",
    "save_paper_mode",
    "get_show_dialog",
    "save_show_dialog",
    "PAPER_WINDOWS",
    "PAPER_ROLL",
    "PAPER_LABEL",
    "PAPER_MODES",
]
