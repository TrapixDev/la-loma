"""Apariencia del POS: paletas, editor guiado y persistencia compartida.

Los colores de la interfaz viven en `ui/styles.py` como tokens (@accent@,
@panel@, ...). Este módulo resuelve esos tokens según la apariencia elegida
(tema oscuro/claro, color de acento, tamaño de texto y densidad) y guarda la
selección en `app_config`, por lo que se comparte entre todas las cajas.

El editor es "guiado": se ofrecen temas y acentos predefinidos para mantener
el contraste legible en lugar de permitir colores libres.
"""

import json
import re

from ui.styles import QSS_TEMPLATE

APPEARANCE_KEY = "ui_appearance"

DENSITY_FACTORS = {
    "compacta": 0.88,
    "normal": 1.0,
    "amplia": 1.12,
}
DENSITY_LABELS = {
    "compacta": "Compacta",
    "normal": "Normal",
    "amplia": "Amplia",
}

# Acentos predefinidos (nombre visible, color).
ACCENT_PRESETS = [
    ("Verde La Loma", "#2fbf71"),
    ("Azul", "#3b82f6"),
    ("Turquesa", "#14b8a6"),
    ("Violeta", "#8b5cf6"),
    ("Ámbar", "#f59e0b"),
    ("Rojo", "#ef4444"),
]

DEFAULT_APPEARANCE = {
    "theme": "dark",
    "accent": "#2fbf71",
    "font_scale": 1.0,
    "density": "normal",
}

THEME_LABELS = {"dark": "Oscuro", "light": "Claro"}

# Paletas base. El acento se calcula aparte (accent/accent_hover/...).
_DARK = {
    "bg": "#14161c",
    "bg_deep": "#0e1116",
    "cart_panel_bg": "#101318",
    "cart_table_bg": "#12151b",
    "bg_panel": "#161a21",
    "cart_alt": "#171b23",
    "table_alt": "#1a1f28",
    "card_pressed": "#191d25",
    "input": "#1a1e26",
    "input_focus": "#1d222c",
    "header": "#1b1f28",
    "panel": "#1e222b",
    "header_section": "#1e232d",
    "button_secondary": "#1f2530",
    "pressed": "#1f242e",
    "surface": "#232a36",
    "gridline": "#232836",
    "hover": "#242a36",
    "button": "#262b36",
    "button_hover": "#262d3a",
    "nav_hover": "#2e3542",
    "stat_card": "#1b2030",
    "warn_on": "#1c1205",
    "border": "#2a2f3a",
    "border2": "#2e3440",
    "border3": "#343b49",
    "border_hover": "#3d4557",
    "border_hover2": "#454f63",
    "border_grid": "#262c38",
    "text": "#e6e9ef",
    "text_bright": "#ffffff",
    "text_strong": "#eef2f8",
    "text_title": "#c9d1dd",
    "text_dim": "#d3dae5",
    "text_dim2": "#b9c2cf",
    "text_muted": "#9aa4b2",
    "text_faint": "#8b93a3",
    "text_disabled": "#5b6472",
    "info_soft_text": "#a8cfff",
    "warn_soft_text": "#ffd18a",
    "warn_soft_text2": "#f5b23c",
    "danger": "#ef4444",
    "danger_hover": "#f87171",
    "danger_pressed": "#dc2626",
    "danger_border": "#7f1d1d",
    "warn": "#f59e0b",
    "warn_hover": "#fbbf24",
    "info": "#3b82f6",
    "info_hover": "#60a5fa",
    "info_pressed": "#2563eb",
    "neutral_button": "#374151",
    "neutral_button_hover": "#4b5563",
    "warn_a30": "rgba(245, 158, 11, 0.30)",
    "warn_a12": "rgba(245, 158, 11, 0.12)",
    "warn_a22": "rgba(245, 158, 11, 0.22)",
    "danger_a12": "rgba(239, 68, 68, 0.12)",
    "danger_a20": "rgba(239, 68, 68, 0.20)",
    "info_a28": "rgba(59, 130, 246, 0.28)",
    "warn_a14": "rgba(245, 158, 11, 0.14)",
    "warn_a45": "rgba(245, 158, 11, 0.45)",
}

_LIGHT = {
    "bg": "#eef1f5",
    "bg_deep": "#e2e6ec",
    "cart_panel_bg": "#e9edf2",
    "cart_table_bg": "#ffffff",
    "bg_panel": "#ffffff",
    "cart_alt": "#f6f8fa",
    "table_alt": "#f6f8fa",
    "card_pressed": "#e4e8ee",
    "input": "#ffffff",
    "input_focus": "#ffffff",
    "header": "#ffffff",
    "panel": "#ffffff",
    "header_section": "#f3f5f8",
    "button_secondary": "#f4f6f9",
    "pressed": "#e4e8ee",
    "surface": "#eef1f5",
    "gridline": "#e6e9ee",
    "hover": "#eef1f5",
    "button": "#eef1f5",
    "button_hover": "#e4e8ee",
    "nav_hover": "#e7ebf0",
    "stat_card": "#ffffff",
    "warn_on": "#ffffff",
    "border": "#d6dbe2",
    "border2": "#d6dbe2",
    "border3": "#c4cbd4",
    "border_hover": "#aab4c0",
    "border_hover2": "#8f9aa8",
    "border_grid": "#e0e4ea",
    "text": "#1f2733",
    "text_bright": "#0d1218",
    "text_strong": "#141a22",
    "text_title": "#2b3440",
    "text_dim": "#3d4855",
    "text_dim2": "#4a5563",
    "text_muted": "#5b6673",
    "text_faint": "#6b7684",
    "text_disabled": "#9aa4b2",
    "info_soft_text": "#1d4ed8",
    "warn_soft_text": "#92400e",
    "warn_soft_text2": "#b45309",
    "danger": "#dc2626",
    "danger_hover": "#ef4444",
    "danger_pressed": "#b91c1c",
    "danger_border": "#fca5a5",
    "warn": "#d97706",
    "warn_hover": "#f59e0b",
    "info": "#2563eb",
    "info_hover": "#3b82f6",
    "info_pressed": "#1d4ed8",
    "neutral_button": "#6b7280",
    "neutral_button_hover": "#4b5563",
    "warn_a30": "rgba(217, 119, 6, 0.18)",
    "warn_a12": "rgba(217, 119, 6, 0.10)",
    "warn_a22": "rgba(217, 119, 6, 0.16)",
    "danger_a12": "rgba(220, 38, 38, 0.10)",
    "danger_a20": "rgba(220, 38, 38, 0.16)",
    "info_a28": "rgba(37, 99, 235, 0.12)",
    "warn_a14": "rgba(217, 119, 6, 0.10)",
    "warn_a45": "rgba(217, 119, 6, 0.35)",
}

_THEMES = {"dark": _DARK, "light": _LIGHT}
_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
_TOKEN_RE = re.compile(r"@[a-z0-9_]+@")


# ---------- utilidades de color ----------

def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))


def _rgb_to_hex(rgb) -> str:
    return "#%02x%02x%02x" % tuple(
        max(0, min(255, round(canal))) for canal in rgb)


def _mix(a, b, ratio: float):
    return tuple(a[i] + (b[i] - a[i]) * ratio for i in range(3))


def _accent_tokens(accent: str) -> dict:
    rgb = _hex_to_rgb(accent)
    luminancia = 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]
    return {
        "accent": _rgb_to_hex(rgb),
        "accent_hover": _rgb_to_hex(_mix(rgb, (255, 255, 255), 0.18)),
        "accent_pressed": _rgb_to_hex(_mix(rgb, (0, 0, 0), 0.18)),
        "accent_bright": _rgb_to_hex(_mix(rgb, (255, 255, 255), 0.35)),
        "on_accent": "#0e1a12" if luminancia > 140 else "#ffffff",
    }


# ---------- normalización y persistencia ----------

def normalize_appearance(settings) -> dict:
    settings = settings if isinstance(settings, dict) else {}
    theme = str(settings.get("theme", "dark")).lower()
    if theme not in _THEMES:
        theme = "dark"
    accent = str(settings.get("accent", DEFAULT_APPEARANCE["accent"]))
    if not _HEX_RE.match(accent):
        accent = DEFAULT_APPEARANCE["accent"]
    try:
        escala = float(settings.get("font_scale", 1.0))
    except (TypeError, ValueError):
        escala = 1.0
    escala = max(0.85, min(1.35, escala))
    density = str(settings.get("density", "normal")).lower()
    if density not in DENSITY_FACTORS:
        density = "normal"
    return {
        "theme": theme,
        "accent": accent,
        "font_scale": round(escala, 2),
        "density": density,
    }


def load_appearance(db) -> dict:
    """Lee la apariencia compartida de app_config (o valores por defecto)."""
    raw = None
    if db is not None:
        try:
            rows = db.execute_query(
                "SELECT value FROM app_config WHERE key = ?", (APPEARANCE_KEY,))
            if rows:
                raw = rows[0].get("value")
        except Exception:
            raw = None
    data = {}
    if raw:
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            data = {}
    return normalize_appearance(data)


def save_appearance(db, appearance: dict) -> None:
    """Guarda la apariencia compartida en app_config (best-effort)."""
    if db is None:
        return
    value = json.dumps(normalize_appearance(appearance), ensure_ascii=False,
                       separators=(",", ":"))
    try:
        db.execute_insert(
            "INSERT OR REPLACE INTO app_config (key, value) VALUES (?, ?)",
            (APPEARANCE_KEY, value))
    except Exception:
        pass


# ---------- construcción del QSS ----------

def build_palette(appearance: dict) -> dict:
    appearance = normalize_appearance(appearance)
    palette = dict(_THEMES[appearance["theme"]])
    palette.update(_accent_tokens(appearance["accent"]))
    return palette


def _scale_fonts(qss: str, scale: float) -> str:
    return re.sub(
        r"font-size:\s*(\d+(?:\.\d+)?)px",
        lambda m: f"font-size: {max(1, round(float(m.group(1)) * scale))}px",
        qss)


def _scale_padding(qss: str, factor: float) -> str:
    def _repl(match):
        inner = re.sub(
            r"(\d+(?:\.\d+)?)px",
            lambda m: f"{max(0, round(float(m.group(1)) * factor))}px",
            match.group(1))
        return f"padding: {inner};"
    return re.sub(r"padding:\s*([^;]+);", _repl, qss)


def render_qss(template: str, appearance: dict) -> str:
    """Resuelve los @tokens@ y aplica tamaño de texto/densidad."""
    appearance = normalize_appearance(appearance)
    palette = build_palette(appearance)
    for token, value in palette.items():
        template = template.replace(f"@{token}@", value)
    pendientes = set(_TOKEN_RE.findall(template))
    if pendientes:
        raise ValueError(f"Tokens sin resolver: {sorted(pendientes)}")
    scale = appearance["font_scale"]
    if abs(scale - 1.0) > 0.001:
        template = _scale_fonts(template, scale)
    factor = DENSITY_FACTORS[appearance["density"]]
    if abs(factor - 1.0) > 0.001:
        template = _scale_padding(template, factor)
    return template


def build_stylesheet(appearance: dict) -> str:
    return render_qss(QSS_TEMPLATE, appearance)


def palette_for(appearance: dict) -> dict:
    return build_palette(appearance)


# ---------- aplicación global ----------

def apply_theme(app, appearance: dict) -> None:
    """Aplica la apariencia a la QApplication y la recuerda como activa."""
    appearance = normalize_appearance(appearance)
    app.setStyleSheet(build_stylesheet(appearance))
    try:
        app._pos_appearance = appearance
    except Exception:
        pass


def set_active_appearance(app, appearance: dict) -> None:
    """Recuerda la apariencia activa sin reaplicar la hoja global."""
    try:
        app._pos_appearance = normalize_appearance(appearance)
    except Exception:
        pass


def current_appearance() -> dict:
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance()
    appearance = getattr(app, "_pos_appearance", None) if app else None
    return normalize_appearance(appearance)


def current_palette() -> dict:
    return build_palette(current_appearance())
