import os
import sys
from datetime import datetime, timedelta

from database.db_manager import DatabaseManager

BASE_CATEGORIES = [
    "Muebles de Sala",
    "Muebles de Comedor",
    "Muebles de Dormitorio",
    "Muebles de Cocina",
    "Muebles de Oficina",
    "Muebles Exteriores",
    "Decoración",
    "Aserradero",
    "Servicios",
]

DEFAULT_CLIENT = ("000000000", "Consumidor Final", "02")

BASE_EXPENSE_CATEGORIES = [
    "Salarios",
    "Servicios",
    "Alquiler",
    "Proveedores",
    "Mantenimiento",
    "Transporte",
    "Publicidad",
    "Impuestos",
    "Otros",
]

# Renombres de categorías antiguas a las nuevas (fletes se registran en "Servicios")
EXPENSE_CATEGORY_RENAMES = {
    "Sueldos": "Salarios",
    "Servicios públicos": "Servicios",
}

# Datos de demostración: (categoría, código, código de barras EAN-13, nombre,
# descripción, costo de fabricación, precio de venta, stock, unidad, CABYS)
DEMO_PRODUCTS = [
    # Muebles de Sala
    ("Muebles de Sala", "SL-001", "74410000000014", "Sofá 3 puestos chenille gris",
     "Estructura de cedro y tapizado chenille color gris", 95000, 189000, 8, "Unid", "310201"),
    ("Muebles de Sala", "SL-002", "74410000000024", "Sofá seccional en L tapizado",
     "Seccional en L con chaise longue, tela antimanchas", 145000, 289000, 4, "Unid", "310201"),
    ("Muebles de Sala", "SL-003", "74410000000034", "Sillón individual reclinable",
     "Sillón reclinable con reposapiés integrado", 48000, 95000, 10, "Unid", "310201"),
    ("Muebles de Sala", "SL-004", "74410000000044", "Mesa de centro de cedro",
     "Mesa de centro maciza de cedro con acabado natural", 25000, 59000, 12, "Unid", "310201"),
    ("Muebles de Sala", "SL-005", "74410000000054", "Centro de entretenimiento TV",
     "Mueble para TV de 55 pulgadas con gavetas", 38000, 85000, 9, "Unid", "310201"),
    # Muebles de Comedor
    ("Muebles de Comedor", "CM-101", "74410000000064", "Juego de comedor 6 puestos",
     "Mesa rectangular de cedro con 6 sillas tapizadas", 160000, 320000, 5, "Unid", "310202"),
    ("Muebles de Comedor", "CM-102", "74410000000074", "Mesa redonda de cedro 1.20 m",
     "Mesa redonda maciza de cedro, 1.20 m de diámetro", 45000, 99000, 7, "Unid", "310202"),
    ("Muebles de Comedor", "CM-103", "74410000000084", "Silla de comedor tapizada",
     "Silla de comedor con espuma y tela resistente", 14000, 32000, 30, "Unid", "310202"),
    ("Muebles de Comedor", "CM-104", "74410000000094", "Aparador de cedro 2 puertas",
     "Aparador con 2 puertas y 2 gavetas", 55000, 115000, 6, "Unid", "310202"),
    # Muebles de Dormitorio
    ("Muebles de Dormitorio", "DR-201", "74410000000101", "Cama matrimonial con base",
     "Cama matrimonial con base de cedro y cabecera", 65000, 135000, 8, "Unid", "310203"),
    ("Muebles de Dormitorio", "DR-202", "74410000000111", "Cama king con cabecera",
     "Cama king size con cabecera acolchada", 90000, 185000, 5, "Unid", "310203"),
    ("Muebles de Dormitorio", "DR-203", "74410000000121", "Ropero 3 puertas con espejo",
     "Closet de 3 puertas con espejo y barra", 120000, 245000, 6, "Unid", "310203"),
    ("Muebles de Dormitorio", "DR-204", "74410000000131", "Velador de cedro",
     "Velador macizo de cedro con gaveta", 12000, 28000, 15, "Unid", "310203"),
    ("Muebles de Dormitorio", "DR-205", "74410000000141", "Cómoda 3 gavetas",
     "Cómoda con 3 gavetas y rieles metálicos", 18000, 42000, 10, "Unid", "310203"),
    # Muebles de Cocina
    ("Muebles de Cocina", "CO-301", "74410000000151", "Mueble modular de cocina 2.4 m",
     "Mueble bajo y alto de cocina a medida, 2.4 m", 180000, 360000, 3, "Unid", "310204"),
    ("Muebles de Cocina", "CO-302", "74410000000161", "Barra de desayuno con 2 bancos",
     "Barra de desayuno de cedro con 2 bancos altos", 52000, 110000, 6, "Unid", "310204"),
    ("Muebles de Cocina", "CO-303", "74410000000171", "Estante de cocina con puertas",
     "Estante de 1.6 m con puertas y repisas", 22000, 48000, 8, "Unid", "310204"),
    # Muebles de Oficina
    ("Muebles de Oficina", "OF-401", "74410000000181", "Escritorio ejecutivo de cedro",
     "Escritorio de cedro con cajonera lateral", 68000, 145000, 7, "Unid", "310205"),
    ("Muebles de Oficina", "OF-402", "74410000000191", "Silla ejecutiva ergonómica",
     "Silla con soporte lumbar y reposabrazos", 38000, 85000, 12, "Unid", "310205"),
    ("Muebles de Oficina", "OF-403", "74410000000208", "Archivador 4 gavetas",
     "Archivador metálico forrado en madera, 4 gavetas", 42000, 92000, 6, "Unid", "310205"),
    ("Muebles de Oficina", "OF-404", "74410000000218", "Librera 5 niveles",
     "Librera abierta de cedro con 5 repisas", 35000, 78000, 8, "Unid", "310205"),
    # Muebles Exteriores
    ("Muebles Exteriores", "EX-501", "74410000000228", "Juego de terraza 4 sillas + mesa",
     "Juego de exterior con mesa y 4 sillas", 75000, 155000, 4, "Unid", "310206"),
    ("Muebles Exteriores", "EX-502", "74410000000238", "Mesa plegable de jardín",
     "Mesa plegable de madera tratada", 15000, 35000, 9, "Unid", "310206"),
    ("Muebles Exteriores", "EX-503", "74410000000248", "Banco rústico de madera",
     "Banco rústico de tronco de cedro", 20000, 45000, 11, "Unid", "310206"),
    ("Muebles Exteriores", "EX-504", "74410000000258", "Hamaca con soporte",
     "Hamaca con soporte de madera", 18000, 42000, 10, "Unid", "310206"),
    # Decoración
    ("Decoración", "DC-601", "74410000000268", "Espejo de pared enmarcado",
     "Espejo 60x90 cm con marco de cedro", 12000, 29000, 14, "Unid", "310207"),
    ("Decoración", "DC-602", "74410000000278", "Lámpara colgante de madera",
     "Lámpara colgante artesanal", 9000, 22000, 16, "Unid", "310207"),
    ("Decoración", "DC-603", "74410000000288", "Par de cojines decorativos",
     "Cojines 45x45 cm con relleno", 4500, 11000, 25, "Unid", "310207"),
    ("Decoración", "DC-604", "74410000000298", "Florero de cerámica grande",
     "Florero decorativo de cerámica", 6000, 15000, 18, "Unid", "310207"),
    # Aserradero
    ("Aserradero", "AS-701", "74410000000305", "Tabla de cedro 2x6x3 m",
     "Tabla de cedro cepillada, 2 x 6 pulgadas, 3 metros", 8500, 15000, 40, "Unid", "310208"),
    ("Aserradero", "AS-702", "74410000000315", "Pie tablar de cedro",
     "Pie tablar de cedro seleccionado", 1800, 3200, 200, "Unid", "310208"),
    ("Aserradero", "AS-703", "74410000000325", "Puerta de madera sólida",
     "Puerta sólida de cedro 80x200 cm", 32000, 68000, 10, "Unid", "310208"),
    ("Aserradero", "AS-704", "74410000000335", "Viga de laurel 3x3x3 m",
     "Viga de laurel cepillada", 7500, 13500, 30, "Unid", "310208"),
    # Servicios
    ("Servicios", "SV-801", "74410000000345", "Armado de mueble a medida",
     "Mano de obra por hora para muebles a medida", 2500, 6000, 0, "Hr", "310209"),
    ("Servicios", "SV-802", "74410000000355", "Barnizado y acabado",
     "Barnizado, laca o laqueado por mueble", 15000, 35000, 0, "Hr", "310209"),
    ("Servicios", "SV-803", "74410000000365", "Tapizado de sillón",
     "Re-tapizado completo de sillón", 40000, 85000, 0, "Hr", "310209"),
    ("Servicios", "SV-804", "74410000000375", "Transporte y entrega",
     "Entrega e instalación dentro del GAM", 6000, 12000, 0, "Unid", "310209"),
]

# (nombre, cédula, tipo, teléfono, correo, dirección, provincia, cantón, distrito)
DEMO_CLIENTS = [
    ("María Rodríguez Chaves", "1-1234-5678", "01", "8888-1234",
     "maria.rodriguez@gmail.com", "San Rafael de Escazú, 200 m oeste de la iglesia",
     "San José", "Escazú", "San Rafael"),
    ("Carlos Jiménez Vargas", "1-0987-6543", "01", "8765-4321",
     "carlosjv@hotmail.com", "Barrio El Carmen, Cartago centro",
     "Cartago", "Cartago", "Oriental"),
    ("Constructora El Roble S.A.", "3-101-456789", "02", "2200-1234",
     "info@elroble.cr", "Zona Franca América, La Ribera",
     "Heredia", "Belén", "La Ribera"),
    ("Ana Lucía Mora Solano", "1-2345-6789", "01", "8888-9999",
     "anamora@gmail.com", "Tres Ríos, contiguo a la plaza de deportes",
     "Cartago", "La Unión", "Tres Ríos"),
    ("Hotel Mirador del Valle S.A.", "3-102-765432", "02", "2233-4455",
     "reservas@miradordelvalle.cr", "Pozos de Santa Ana, frente a la pista",
     "San José", "Santa Ana", "Pozos"),
    ("Luis Fernando Castro Mena", "1-3456-7890", "01", "8999-0000",
     "", "Paraíso centro, 100 m norte del parque",
     "Cartago", "Paraíso", "Paraíso"),
]

# Ventas demo: (cliente, días atrás, hora "HH:MM", método de pago, [(código, cantidad)])
# Cubren ~30 días con 2-3 ventas al día, más los gastos distribuidos en los mismos días.
DEMO_SALES = [
    # día -30
    ("María Rodríguez Chaves", 30, "09:10", "efectivo", [("SL-004", 1), ("DC-601", 1)]),
    ("Carlos Jiménez Vargas", 30, "11:20", "tarjeta", [("CM-103", 2)]),
    # día -29
    ("Constructora El Roble S.A.", 29, "10:00", "transferencia", [("OF-401", 1), ("OF-402", 2)]),
    ("Ana Lucía Mora Solano", 29, "15:30", "efectivo", [("DR-201", 1), ("DR-204", 1)]),
    ("Hotel Mirador del Valle S.A.", 29, "09:45", "sinpe", [("EX-501", 1)]),
    # día -28
    ("Luis Fernando Castro Mena", 28, "17:00", "efectivo", [("SL-003", 1)]),
    ("Carlos Jiménez Vargas", 28, "12:00", "tarjeta", [("DC-603", 2), ("DC-602", 1)]),
    # día -27
    ("María Rodríguez Chaves", 27, "10:30", "sinpe", [("CM-101", 1)]),
    ("Constructora El Roble S.A.", 27, "14:20", "transferencia", [("CO-301", 1)]),
    # día -26
    ("Ana Lucía Mora Solano", 26, "11:00", "efectivo", [("SL-005", 1)]),
    ("Hotel Mirador del Valle S.A.", 26, "16:45", "sinpe", [("DR-203", 1)]),
    ("Luis Fernando Castro Mena", 26, "09:30", "efectivo", [("CM-102", 1), ("CM-103", 1)]),
    # día -25
    ("Carlos Jiménez Vargas", 25, "13:15", "tarjeta", [("EX-502", 1)]),
    ("María Rodríguez Chaves", 25, "10:15", "sinpe", [("OF-404", 1)]),
    # día -24
    ("Constructora El Roble S.A.", 24, "15:40", "transferencia", [("SL-001", 1)]),
    ("Ana Lucía Mora Solano", 24, "12:30", "efectivo", [("DR-202", 1)]),
    # día -23
    ("Hotel Mirador del Valle S.A.", 23, "09:00", "sinpe", [("CO-302", 1)]),
    ("Carlos Jiménez Vargas", 23, "11:45", "tarjeta", [("DC-604", 1), ("DC-601", 1)]),
    # día -22
    ("Luis Fernando Castro Mena", 22, "16:20", "efectivo", [("AS-702", 30)]),
    ("María Rodríguez Chaves", 22, "10:10", "sinpe", [("SL-002", 1)]),
    ("Constructora El Roble S.A.", 22, "14:50", "transferencia", [("OF-403", 1), ("OF-404", 1)]),
    # día -21
    ("Ana Lucía Mora Solano", 21, "09:40", "efectivo", [("CM-104", 1)]),
    ("Hotel Mirador del Valle S.A.", 21, "13:00", "sinpe", [("EX-503", 1)]),
    # día -20
    ("Luis Fernando Castro Mena", 20, "11:10", "efectivo", [("DR-205", 1), ("DR-204", 1)]),
    ("Carlos Jiménez Vargas", 20, "16:30", "tarjeta", [("SL-004", 1)]),
    ("María Rodríguez Chaves", 20, "10:20", "efectivo", [("CO-303", 1)]),
    # día -19
    ("Constructora El Roble S.A.", 19, "15:00", "transferencia", [("CM-101", 1)]),
    ("Ana Lucía Mora Solano", 19, "09:50", "tarjeta", [("SL-003", 1)]),
    # día -18
    ("Hotel Mirador del Valle S.A.", 18, "12:40", "sinpe", [("DR-204", 2)]),
    ("Luis Fernando Castro Mena", 18, "17:10", "efectivo", [("AS-703", 1)]),
    # día -17
    ("Carlos Jiménez Vargas", 17, "11:30", "tarjeta", [("EX-504", 1)]),
    ("María Rodríguez Chaves", 17, "14:15", "sinpe", [("OF-402", 1)]),
    ("Constructora El Roble S.A.", 17, "10:05", "transferencia", [("CO-302", 1), ("CO-303", 1)]),
    # día -16
    ("Ana Lucía Mora Solano", 16, "16:00", "efectivo", [("SL-005", 1)]),
    ("Hotel Mirador del Valle S.A.", 16, "09:20", "sinpe", [("CM-103", 3)]),
    # día -15
    ("Luis Fernando Castro Mena", 15, "13:40", "efectivo", [("DC-603", 2)]),
    ("María Rodríguez Chaves", 15, "11:55", "efectivo", [("DR-201", 1)]),
    ("Carlos Jiménez Vargas", 15, "15:30", "tarjeta", [("OF-401", 1)]),
    # día -14
    ("Ana Lucía Mora Solano", 14, "10:00", "efectivo", [("SL-001", 1)]),
    ("Constructora El Roble S.A.", 14, "14:10", "transferencia", [("SL-002", 1)]),
    # día -13
    ("Hotel Mirador del Valle S.A.", 13, "09:35", "sinpe", [("DR-202", 1)]),
    ("Luis Fernando Castro Mena", 13, "16:45", "efectivo", [("CM-104", 1)]),
    # día -12
    ("María Rodríguez Chaves", 12, "11:15", "sinpe", [("EX-501", 1)]),
    ("Carlos Jiménez Vargas", 12, "14:30", "tarjeta", [("DC-602", 1), ("DC-604", 1)]),
    ("Ana Lucía Mora Solano", 12, "10:25", "efectivo", [("SL-004", 1)]),
    # día -11
    ("Constructora El Roble S.A.", 11, "15:20", "transferencia", [("OF-404", 1), ("OF-403", 1)]),
    ("Hotel Mirador del Valle S.A.", 11, "09:10", "sinpe", [("CM-102", 1)]),
    # día -10
    ("Luis Fernando Castro Mena", 10, "13:00", "efectivo", [("AS-701", 5)]),
    ("Carlos Jiménez Vargas", 10, "16:10", "tarjeta", [("SL-005", 1)]),
    ("María Rodríguez Chaves", 10, "12:00", "efectivo", [("DR-203", 1)]),
    # día -9
    ("Ana Lucía Mora Solano", 9, "09:45", "efectivo", [("CO-301", 1)]),
    ("Hotel Mirador del Valle S.A.", 9, "14:40", "sinpe", [("EX-504", 1)]),
    # día -8
    ("Constructora El Roble S.A.", 8, "10:30", "transferencia", [("CM-103", 2)]),
    ("Luis Fernando Castro Mena", 8, "15:50", "efectivo", [("SL-002", 1)]),
    # día -7
    ("María Rodríguez Chaves", 7, "11:05", "sinpe", [("OF-401", 1)]),
    ("Carlos Jiménez Vargas", 7, "13:30", "tarjeta", [("DR-201", 1)]),
    ("Ana Lucía Mora Solano", 7, "10:40", "efectivo", [("SL-001", 1)]),
    # día -6
    ("Hotel Mirador del Valle S.A.", 6, "16:00", "sinpe", [("CO-303", 1)]),
    ("Constructora El Roble S.A.", 6, "09:30", "transferencia", [("SL-003", 1)]),
    # día -5
    ("Luis Fernando Castro Mena", 5, "14:20", "efectivo", [("EX-502", 1), ("DC-601", 1)]),
    ("María Rodríguez Chaves", 5, "10:00", "efectivo", [("CM-103", 2)]),
    ("Carlos Jiménez Vargas", 5, "12:30", "tarjeta", [("SL-004", 1)]),
    # día -4
    ("Ana Lucía Mora Solano", 4, "15:40", "efectivo", [("DR-204", 2)]),
    ("Hotel Mirador del Valle S.A.", 4, "09:05", "sinpe", [("OF-404", 1)]),
    # día -3
    ("Constructora El Roble S.A.", 3, "14:50", "transferencia", [("CM-104", 1)]),
    ("Luis Fernando Castro Mena", 3, "11:25", "efectivo", [("DC-602", 1), ("DC-603", 2)]),
    # día -2
    ("María Rodríguez Chaves", 2, "10:35", "sinpe", [("DR-202", 1)]),
    ("Carlos Jiménez Vargas", 2, "16:20", "tarjeta", [("EX-503", 1)]),
    ("Ana Lucía Mora Solano", 2, "09:50", "efectivo", [("SL-005", 1)]),
    # día -1
    ("Hotel Mirador del Valle S.A.", 1, "13:15", "sinpe", [("SL-001", 1)]),
    ("Constructora El Roble S.A.", 1, "15:30", "transferencia", [("OF-402", 1), ("OF-401", 1)]),
    # día 0 (hoy)
    ("Luis Fernando Castro Mena", 0, "09:15", "efectivo", [("AS-702", 20)]),
    ("María Rodríguez Chaves", 0, "10:30", "tarjeta", [("SV-803", 1)]),
    ("Carlos Jiménez Vargas", 0, "11:05", "efectivo", [("SV-804", 1)]),
]

# Gastos demo: (categoría, días atrás, monto, descripción, método de pago)
DEMO_EXPENSES = [
    ("Alquiler", 30, 250000, "Alquiler del local comercial", "sinpe"),
    ("Transporte", 29, 15000, "Combustible del camión de reparto", "efectivo"),
    ("Servicios", 27, 12300, "Recibo de agua (AyA)", "sinpe"),
    ("Proveedores", 25, 380000, "Compra de madera de cedro (aserradero proveedor)", "transferencia"),
    ("Servicios", 23, 82500, "Recibo eléctrico (CNFL)", "sinpe"),
    ("Transporte", 22, 18000, "Flete entrega a cliente en el GAM", "efectivo"),
    ("Publicidad", 20, 30000, "Anuncios en Facebook e Instagram", "sinpe"),
    ("Proveedores", 18, 96000, "Telas, espuma y herrajes para tapicería", "transferencia"),
    ("Salarios", 15, 450000, "Quincena primera del mes (equipo de producción)", "efectivo"),
    ("Mantenimiento", 14, 45000, "Afilado de sierras y repuestos de maquinaria", "efectivo"),
    ("Servicios", 12, 25000, "Flete camión (traslado de madera)", "efectivo"),
    ("Otros", 11, 12000, "Material de oficina y papelería", "efectivo"),
    ("Proveedores", 9, 215000, "Compra de madera de laurel (aserradero proveedor)", "transferencia"),
    ("Servicios", 8, 11000, "Recibo de internet y telefonía", "sinpe"),
    ("Mantenimiento", 6, 32000, "Reparación de sierra circular", "efectivo"),
    ("Publicidad", 4, 20000, "Publicidad en radio local", "sinpe"),
    ("Transporte", 3, 14000, "Combustible del camión de reparto", "efectivo"),
    ("Impuestos", 2, 120000, "Retenciones del mes anterior", "transferencia"),
    ("Salarios", 1, 460000, "Quincena segunda del mes (equipo de producción)", "efectivo"),
]


def seed_initial_data(db: DatabaseManager) -> None:
    """Inserta datos iniciales: categorías, configuración de Hacienda y cliente por defecto."""
    rows = db.execute_query("SELECT COUNT(*) AS total FROM categories")
    if rows[0]["total"] == 0:
        for name in BASE_CATEGORIES:
            db.execute_insert(
                "INSERT INTO categories (name, color) VALUES (?, ?)",
                (name, ""),
            )

    rows = db.execute_query("SELECT id FROM hacienda_config WHERE id = 1")
    if not rows:
        db.execute_insert("INSERT INTO hacienda_config (id) VALUES (1)")

    rows = db.execute_query("SELECT id FROM clients WHERE id_number = ?", (DEFAULT_CLIENT[0],))
    if not rows:
        db.execute_insert(
            "INSERT INTO clients (id_number, name, id_type) VALUES (?, ?, ?)",
            DEFAULT_CLIENT,
        )

    rows = db.execute_query("SELECT COUNT(*) AS total FROM expense_categories")
    if rows[0]["total"] == 0:
        for name in BASE_EXPENSE_CATEGORIES:
            db.execute_insert(
                "INSERT INTO expense_categories (name) VALUES (?)",
                (name,),
            )
    else:
        existing = {row["name"] for row in db.execute_query("SELECT name FROM expense_categories")}
        for old_name, new_name in EXPENSE_CATEGORY_RENAMES.items():
            if old_name in existing and new_name not in existing:
                db.execute_update(
                    "UPDATE expense_categories SET name = ? WHERE name = ?",
                    (new_name, old_name),
                )
        existing = {row["name"] for row in db.execute_query("SELECT name FROM expense_categories")}
        for name in BASE_EXPENSE_CATEGORIES:
            if name not in existing:
                db.execute_insert(
                    "INSERT INTO expense_categories (name) VALUES (?)",
                    (name,),
                )

    # Datos de demostración: automáticos en modo fuente (desarrollo), y
    # opcionales en el .exe con POS_DEMO_DATA=1. Se desactivan con POS_DEMO_DATA=0.
    demo = os.environ.get("POS_DEMO_DATA")
    if demo is None and not getattr(sys, "frozen", False):
        demo = "1"
    if demo == "1":
        seed_demo_data(db)


def seed_demo_data(db: DatabaseManager) -> None:
    """Inserta una base de demostración realista (productos, clientes, ventas y gastos).

    Es idempotente: solo agrega lo que falta (productos por `code`, clientes por
    `id_number`) y siembra ventas/gastos únicamente en bases vacías, para no
    duplicar en re-arranques.
    """
    categories = {row["name"]: row["id"] for row in db.execute_query("SELECT id, name FROM categories")}

    # Productos de demostración: solo los que no existan por código.
    existing_codes = {row["code"] for row in db.execute_query("SELECT code FROM products")}
    for category, code, barcode, name, description, cost, sale, stock, unit, cabys in DEMO_PRODUCTS:
        if code in existing_codes:
            continue
        db.execute_insert(
            "INSERT INTO products (code, barcode, name, description, category_id, "
            "cost_price, sale_price, stock_quantity, min_stock, unit_of_measure, "
            "cabys_code, tax_type, tax_rate, active) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, 'gravado', 13.0, 1)",
            (code, barcode, name, description, categories.get(category),
             cost, sale, stock, unit, cabys),
        )

    # Clientes de demostración: solo los que no existan por cédula.
    existing_clients = {row["id_number"] for row in db.execute_query("SELECT id_number FROM clients")}
    for name, id_number, id_type, phone, email, address, province, canton, district in DEMO_CLIENTS:
        if id_number in existing_clients:
            continue
        db.execute_insert(
            "INSERT INTO clients (id_number, name, id_type, phone, email, address, "
            "province, canton, district, activity_code) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, '31021')",
            (id_number, name, id_type, phone, email, address, province, canton, district),
        )

    client_ids = {row["name"]: row["id"] for row in db.execute_query("SELECT id, name FROM clients")}
    product_ids = {row["code"]: row["id"] for row in db.execute_query("SELECT id, code FROM products")}
    prices = {code: sale for _, code, _, _, _, _, sale, _, _, _ in DEMO_PRODUCTS}

    now = datetime.now()

    # Ventas de demostración: solo en bases sin ventas (no duplica en re-arranques).
    if db.execute_query("SELECT COUNT(*) AS t FROM sales")[0]["t"] == 0:
        with db.transaction() as connection:
            for index, (client, days_ago, time_str, method, items) in enumerate(DEMO_SALES, start=1):
                created = (now - timedelta(days=days_ago)).replace(
                    hour=int(time_str[:2]), minute=int(time_str[3:]), second=0, microsecond=0)
                stamp = created.strftime("%Y-%m-%d %H:%M:%S")
                subtotal = 0.0
                tax = 0.0
                line_items = []
                for code, qty in items:
                    unit_price = prices[code]
                    item_subtotal = unit_price * qty
                    item_tax = round(item_subtotal * 0.13, 2)
                    subtotal += item_subtotal
                    tax += item_tax
                    line_items.append((code, qty, unit_price, item_tax))
                cursor = connection.execute(
                    "INSERT INTO sales (invoice_number, client_id, subtotal, discount, "
                    "tax_amount, total, payment_method, cash_received, change_amount, "
                    "status, station, user_id, user_name, created_at) "
                    "VALUES (?, ?, ?, 0, ?, ?, ?, 0, 0, 'completada', 'CAJA1', NULL, "
                    "'Administrador', ?)",
                    (f"V-{index:05d}", client_ids.get(client, 1),
                     round(subtotal, 2), round(tax, 2), round(subtotal + tax, 2), method, stamp),
                )
                sale_id = cursor.lastrowid
                for code, qty, unit_price, item_tax in line_items:
                    product = next(p for p in DEMO_PRODUCTS if p[1] == code)
                    connection.execute(
                        "INSERT INTO sale_items (sale_id, product_id, product_name, quantity, "
                        "unit_price, unit_cost, discount, tax_amount, total) "
                        "VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?)",
                        (sale_id, product_ids[code], product[3], qty, unit_price,
                         product[5], item_tax, round(unit_price * qty + item_tax, 2)),
                    )

    # Gastos de demostración: solo en bases sin gastos.
    if db.execute_query("SELECT COUNT(*) AS t FROM expenses")[0]["t"] == 0:
        for category, days_ago, amount, description, method in DEMO_EXPENSES:
            created = now - timedelta(days=days_ago)
            # expense_date es solo la fecha (YYYY-MM-DD) para que el gasto caiga
            # en el día correcto del reporte, junto a las ventas de ese día.
            day = created.strftime("%Y-%m-%d")
            stamp = created.strftime("%Y-%m-%d %H:%M:%S")
            db.execute_insert(
                "INSERT INTO expenses (expense_date, category, description, amount, "
                "payment_method, user_id, user_name, station, created_at) "
                "VALUES (?, ?, ?, ?, ?, NULL, 'Administrador', 'CAJA1', ?)",
                (day, category, description, amount, method, stamp),
            )

    # El contador de facturas debe partir del mayor número ya usado, para que
    # las ventas reales sigan la secuencia sin duplicarse.
    max_number = db.execute_query(
        "SELECT COALESCE(MAX(CAST(substr(invoice_number, 3) AS INTEGER)), 0) AS m "
        "FROM sales WHERE invoice_number LIKE 'V-%'"
    )[0]["m"]
    db.execute_update(
        "INSERT INTO counters (name, value) VALUES ('invoice', ?) "
        "ON CONFLICT(name) DO UPDATE SET value = excluded.value",
        (int(max_number or 0),),
    )


def _seed_db_from_cli() -> None:
    """Inyección directa: python -m database.seed [--demo] [--db ruta]."""
    import argparse

    from config import Config

    parser = argparse.ArgumentParser(description="Siembra la base de datos del POS La Loma.")
    parser.add_argument("--demo", action="store_true",
                        help="Incluye los datos de demostración realistas")
    parser.add_argument("--db", default="",
                        help="Ruta de la base de datos (por defecto: la de Config)")
    args = parser.parse_args()
    if args.demo:
        os.environ["POS_DEMO_DATA"] = "1"
    db_path = args.db or Config.DB_PATH
    db = DatabaseManager(db_path)
    db.initialize()
    seed_initial_data(db)
    products = db.execute_query("SELECT COUNT(*) AS t FROM products")[0]["t"]
    sales = db.execute_query("SELECT COUNT(*) AS t FROM sales")[0]["t"]
    expenses = db.execute_query("SELECT COUNT(*) AS t FROM expenses")[0]["t"]
    print(f"Seed aplicado en {db_path}")
    print(f"  productos: {products} | ventas: {sales} | gastos: {expenses}")
    db.close()


if __name__ == "__main__":
    _seed_db_from_cli()

