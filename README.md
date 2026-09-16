# POS La Loma 1.0.1

Punto de venta para Mueblería y Aserradero La Loma (negocio pequeño).
Python + PyQt6, base SQLite, servidor local para varias cajas (LAN).

## Funcionalidades

- Venta normal, factura simplificada (sin IVA, régimen de tributación simplificada)
  y factura electrónica (Hacienda vía proveedor, opcional).
- Cobro en **colones o USD** (tipo de cambio editable y desde API de mercado,
  no BCCR oficial) y **pago mixto** (Efectivo + Tarjeta/SINPE) con Enter.
- **Ticket térmico 80 mm** (impresora configurable por caja) y **PDF A4** (Qt).
- Reimpresión y anulación de ventas, notas de crédito, reportes (ingresos,
  ganancias, gastos), clientes, productos con fotos, categorías.
- Varias cajas conectadas a un **servidor central** por HTTP local
  (transacciones atómicas, idempotencia de ventas).
- **Respaldos automáticos** (BD + fotos) cada 6 h, se conservan 14.
- **Actualizaciones por red local**: el servidor sirve el setup nuevo y las
  cajas lo descargan e instalan sin internet.

## Instalación (PC del negocio)

1. Ejecute `PosLaLoma_Setup_1.0.1.exe` (Siguiente/Siguiente/Finalizar).
   Instala por usuario, sin permisos de administrador.
2. Siga `INSTRUCCIONES.txt` (carpeta compartida, IP fija, firewall, cajas).

El instalador se genera con `build\build_pos.ps1` (requiere PyInstaller e
Inno Setup 6). El `.exe` no necesita Python en la PC destino.

## Rutas

| Qué | Modo fuente (`python main.py`) | Modo instalado (.exe) |
|---|---|---|
| Base y respaldos | `data\` | `%APPDATA%\PosLaLoma\data\` |
| Respaldos | `data\backups\` | `%APPDATA%\PosLaLoma\data\backups\` |
| Fotos | `data\product_images\` | `%APPDATA%\PosLaLoma\data\product_images\` |
| Updates LAN | `updates\` | `%APPDATA%\PosLaLoma\updates\` |
| Documentos XML/PDF | `DOCS_PATH` o Documentos\PosLaLoma | ídem |

**Carpeta de documentos**: `DOCS_PATH` en `config.ini` apunta a la carpeta
compartida en red (p. ej. `\\SERVIDOR\documentos`). Si no responde, se usa
`Documentos\PosLaLoma` y, si tampoco, `%APPDATA%\PosLaLoma\documentos`.

## config.ini (por PC, opcional)

`%APPDATA%\PosLaLoma\config.ini` (en modo fuente: `config.ini` junto al proyecto):

```ini
[pos]
server_url = http://192.168.1.10:8000   ; solo estaciones (no el servidor)
station = CAJA2
docs_path = \\192.168.1.10\documentos
mode = server                            ; server | local (pruebas)
```

## Ejecutar desde el código (desarrollo)

```
python -m pip install -r requirements.txt
python main.py            # estación (levanta el servidor local automáticamente)
python main.py --server   # servidor central sin ventana
python main.py --selftest # valida BD + servicios sin abrir la UI
python -m tests.run_all   # todos los tests (necesita PyQt6, QT_QPA_PLATFORM=offscreen)
```

## Arquitectura

- `server.py`: API HTTP estándar (sin dependencias). SQL de una sentencia,
  token Bearer, PIN hasheado PBKDF2, bloqueo por PIN fallidos, auditoría,
  transacciones remotas `tx/begin|exec|commit|rollback`, respaldos, endpoints
  `/api/update/info` y `/api/update/download/*`.
- `network/remote_db.py`: cliente con la misma interfaz de `DatabaseManager`;
  los servicios no distinguen local/remoto.
- `modules/documentos/`: XML FEAT (ElementTree), PDF (Qt), ticket térmico (Qt).
- `utils/arranque.py`: en modo .exe migra `data\` (USB) a `%APPDATA%` la
  primera vez.
- Ventas: cada venta lleva `sale_reference` único (UUID) con índice UNIQUE →
  reintentar tras perder la red no duplica. El stock no se controla: se
  fabrica a pedido, por lo que un producto puede venderse con existencias en 0.

## Seguridad (para producción)

- No exponga el puerto 8000 a internet; solo red local del negocio (para
  acceso remoto use una VPN, nunca abra el puerto en el router).
- **Credenciales fiscales cifradas**: la clave y el PIN del proveedor FE se
  guardan cifrados con la DPAPI de Windows (nunca en texto plano).
- **Permisos restringidos**: `%APPDATA%\PosLaLoma` queda con ACLs que solo
  permiten acceso al usuario que ejecuta el POS, SYSTEM y Administradores.
- **Firewall**: ejecute `build\firewall_pos.ps1` como administrador para
  aceptar conexiones al puerto solo desde la red local (`remoteip=LocalSubnet`).
- **Solo redes privadas**: el servidor rechaza peticiones desde IP públicas
  (`lan_only = 0` en config.ini lo desactiva, no recomendado).
- **HTTPS opcional**: genere un certificado con
  `python tools/generar_certificado.py --host <IP-del-servidor>` y las cajas
  usan `tls_ca` (o `tls_insecure = 1` dentro de la red).
- **Límites de entrada**: tamaño máximo de petición, de parámetros y de fotos;
  el tráfico entre cajas y servidor se audita en `audit_log`.
- **Actualizaciones verificadas** con SHA-256 antes de instalar.

## Notas fiscales pendientes

- Confirmar con el contador que "Factura Simplificada sin IVA" corresponde al
  régimen (tributación simplificada).
- El tipo de cambio USD proviene de `open.er-api.com` (mercado), no del BCCR.
- Los tickets en USD muestran además el equivalente en colones
  (configurable con `mostrar_equivalente_crc` en config.ini; el PDF va en
  colones).

## Versiones

- 1.0.1 — seguridad: credenciales cifradas con DPAPI, ACLs restringidas en
  `%APPDATA%\PosLaLoma`, servidor solo para redes privadas con límites de
  entrada, HTTPS opcional, firewall acotado a la red local y actualizaciones
  verificadas con SHA-256.
- 1.0.0 — release inicial del instalador (USD, impresoras, tickets, exención,
  carpeta compartida, actualizaciones LAN, idempotencia).
