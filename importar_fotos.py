"""Importador masivo de fotos de productos.

Debe ejecutarse en la PC central (donde vive la base de datos):

    python importar_fotos.py [carpeta_de_fotos]

Cada archivo se asigna por su nombre:
  - por codigo:  "SL-001.jpg", "cm-102.png"
  - por nombre:  "sofa 3 puestos chenille gris.jpg" (sin acentos, minusculas)

Las fotos se redimensionan a 400 px y se guardan en formato PNG en
data/product_images, igual que la subida desde la aplicacion. Reporta al
final las imagenes que no coincidieron con ningun producto.
"""

import random
import re
import sqlite3
import sys
import time
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from PyQt6.QtCore import QBuffer, QIODevice, Qt
from PyQt6.QtGui import QImage

from config import Config

EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9 ]+", " ", text.lower()).strip()


def process_image(source: Path, max_side: int) -> bytes | None:
    image = QImage(str(source))
    if image.isNull():
        return None
    if image.width() > max_side or image.height() > max_side:
        image = image.scaled(
            max_side, max_side,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not image.save(buffer, "PNG"):
        return None
    return bytes(buffer.data())


def main() -> None:
    folder = Path(sys.argv[1]) if len(sys.argv) > 1 else (
        Path(__file__).resolve().parent / "data" / "product_images_import")
    if not folder.is_dir():
        print(f"No existe la carpeta: {folder}")
        sys.exit(1)

    db = sqlite3.connect(Config.DB_PATH)
    db.row_factory = sqlite3.Row
    products = db.execute(
        "SELECT id, name, code, image_path FROM products").fetchall()
    by_code = {normalize(row["code"]): row for row in products if row["code"]}
    by_name = {normalize(row["name"]): row for row in products}

    images_dir = Path(Config.PRODUCT_IMAGES_DIR)
    images_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = Path(Config.IMAGE_CACHE_DIR)

    files = sorted(p for p in folder.iterdir() if p.is_file()
                   and p.suffix.lower() in EXTENSIONS)
    imported: list[str] = []
    unmatched: list[str] = []
    skipped: list[str] = []
    now = time.strftime("%Y-%m-%d %H:%M:%S")

    for source in files:
        stem = source.stem
        row = by_code.get(normalize(stem)) or by_name.get(normalize(stem))
        if row is None:
            unmatched.append(source.name)
            continue
        data = process_image(source, Config.IMAGE_MAX_SIDE)
        if data is None:
            skipped.append(source.name)
            continue
        filename = f"p{int(time.time() * 1000)}{random.randint(0, 0xFFFF):04x}.png"
        target = images_dir / filename
        target.write_bytes(data)
        old = row["image_path"]
        if old and Path(images_dir, old).is_file():
            try:
                Path(images_dir, old).unlink()
            except OSError:
                pass
        if old:
            try:
                (cache_dir / old).unlink(missing_ok=True)
            except OSError:
                pass
        db.execute("UPDATE products SET image_path=?, updated_at=? WHERE id=?",
                   (filename, now, row["id"]))
        imported.append(f"{row['code'] or row['name']} <- {source.name}")
    db.commit()
    db.close()

    print(f"\nImportadas: {len(imported)}")
    for line in imported:
        print("  ", line)
    if unmatched:
        print(f"\nSin coincidencia ({len(unmatched)}):")
        for name in unmatched:
            print("  ", name)
    if skipped:
        print(f"\nNo legibles ({len(skipped)}): {', '.join(skipped)}")


if __name__ == "__main__":
    main()
