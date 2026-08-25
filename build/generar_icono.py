"""Genera el icono de la app (assets/icon.ico) con Pillow."""
from pathlib import Path

from PIL import Image, ImageDraw

ASSETS = Path(__file__).resolve().parent / "assets"
ASSETS.mkdir(exist_ok=True)

SIZE = 256
img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
d = ImageDraw.Draw(img)

# Fondo: tablero de madera oscura con esquinas redondeadas
d.rounded_rectangle([8, 8, SIZE - 8, SIZE - 8], radius=40, fill=(92, 61, 36, 255))
for i in range(6):
    y = 40 + i * 36
    d.line([24, y, SIZE - 24, y], fill=(70, 46, 26, 255), width=3)

# Cajón / caja registradora estilizada
d.rounded_rectangle([48, 120, SIZE - 48, SIZE - 48], radius=16, fill=(34, 34, 34, 255))
d.rounded_rectangle([56, 128, SIZE - 56, SIZE - 40], radius=12, fill=(26, 26, 26, 255))
for i in range(3):
    x = 96 + i * 34
    d.ellipse([x, 166, x + 14, 180], fill=(120, 160, 80, 255))

# Texto "L" grande
d.text((SIZE // 2, 96), "L", font=None, fill=(255, 255, 255, 255), anchor="mm") if False else None
d.rectangle([108, 44, 148, 104], fill=(230, 200, 140, 255))
d.rectangle([108, 44, 178, 64], fill=(230, 200, 140, 255))

ico = Path(ASSETS / "icon.ico")
img.save(ico, sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("Icono generado:", ico)
