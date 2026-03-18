"""
Libiry Style - Gedeelde styling voor Libiry tools (tkinter versie).

Leest kleuren en andere settings uit customize.txt zodat alle Libiry tools
er hetzelfde uitzien.

Dit is de tkinter-versie die hex kleuren retourneert.
Libiry zelf gebruikt Kivy en heeft eigen parse_color/load_customization in main.py
die RGBA tuples (0-1 range) retourneren.
"""

from pathlib import Path
from typing import Dict, Any, Tuple
import re


# Standaard Libiry kleuren - zelfde defaults als in main.py load_customization()
# maar dan als hex voor tkinter
DEFAULT_STYLE = {
    'background_color': '#6F9D9F',      # Teal (0.44, 0.62, 0.62)
    'button_color': '#793F4E',          # Bordeaux/aubergine (0.47, 0.25, 0.31)
    'button_font_color': '#FFFFFF',     # Wit
    'background_font_color': '#FFFFFF', # Wit (let op: main.py heeft dit als wit)
    'search_box_color': '#FFFFFF',      # Wit
    'search_box_font_color': '#000000', # Zwart
    'tile_font_color': '#000000',       # Zwart
    'rounded_corners': True,
    'font_size': 12,
    'scrollbar_width': 10,
    'scrollbar_always_visible': True,
}

# Bekende kleurnamen - zelfde als in main.py parse_color()
COLOR_NAMES = {
    'white': '#FFFFFF',
    'black': '#000000',
    'red': '#FF0000',
    'green': '#00FF00',
    'blue': '#0000FF',
    'gray': '#808080',
    'grey': '#808080',
    'purple': '#800080',
    'lila': '#CC99CC',  # (0.8, 0.6, 0.8)
}


def parse_color_hex(value: str) -> str:
    """
    Parse een kleurwaarde naar hex formaat (voor tkinter).

    Zelfde logica als parse_color() in main.py maar retourneert hex string
    in plaats van RGBA tuple.

    Ondersteunt:
    - Hex codes: #FF0000, FF0000
    - Kleurnamen: white, black, red, etc.
    """
    value = value.strip().lower()

    # Check bekende kleurnamen
    if value in COLOR_NAMES:
        return COLOR_NAMES[value]

    # Check hex code
    if value.startswith('#') and len(value) in (7, 9):
        return value.upper()[:7]  # Neem alleen RGB, negeer alpha

    # Check hex zonder #
    if re.match(r'^[0-9a-f]{6}$', value):
        return f'#{value.upper()}'

    # Fallback naar grijs
    return '#E6E6E6'


def parse_bool(value: str) -> bool:
    """Parse een boolean waarde uit customize.txt (zelfde logica als main.py)."""
    return value.strip().lower() not in ('n', 'no', 'false', '0')


def load_libiry_style(script_dir: Path = None) -> Dict[str, Any]:
    """
    Laad Libiry styling uit customize.txt (tkinter versie).

    Zelfde logica als load_customization() in main.py:
    - Eerst resources/customize.txt (defaults)
    - Dan customize/customize.txt (gebruikersinstellingen overschrijven defaults)

    Args:
        script_dir: Pad naar de Libiry folder (standaard: folder van dit bestand)

    Returns:
        Dict met alle style settings (kleuren als hex strings voor tkinter)
    """
    if script_dir is None:
        script_dir = Path(__file__).parent.parent

    style = DEFAULT_STYLE.copy()

    # Zelfde volgorde als main.py: eerst resources (defaults), dan customize (overschrijft)
    for folder in ['resources', 'customize']:
        customize_path = script_dir / folder / 'customize.txt'
        if customize_path.exists():
            try:
                content = customize_path.read_text(encoding='utf-8')

                for line in content.split('\n'):
                    if ':' not in line:
                        continue

                    key, value = line.split(':', 1)
                    key = key.strip().lower()
                    value = value.strip()

                    if not value:
                        continue

                    # Parse settings - zelfde keys als main.py
                    if key == 'background color':
                        style['background_color'] = parse_color_hex(value)
                    elif key == 'button color':
                        style['button_color'] = parse_color_hex(value)
                    elif key == 'button font color':
                        style['button_font_color'] = parse_color_hex(value)
                    elif key == 'background font color':
                        style['background_font_color'] = parse_color_hex(value)
                    elif key == 'search box color':
                        style['search_box_color'] = parse_color_hex(value)
                    elif key == 'search box font color':
                        style['search_box_font_color'] = parse_color_hex(value)
                    elif key == 'tile font color':
                        style['tile_font_color'] = parse_color_hex(value)
                    elif key == 'rounded corners y/n':
                        style['rounded_corners'] = parse_bool(value)
                    elif key in ('font size', 'ui font size'):
                        try:
                            style['font_size'] = int(value)
                        except ValueError:
                            pass
                    elif key == 'scrollbar width':
                        try:
                            style['scrollbar_width'] = int(value)
                        except ValueError:
                            pass
                    elif key == 'scrollbar always visible y/n':
                        style['scrollbar_always_visible'] = parse_bool(value)

            except Exception as e:
                print(f"Warning: Could not read {customize_path}: {e}")

    return style


def hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    """Convert hex kleur naar RGB tuple."""
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


def darken_color(hex_color: str, factor: float = 0.8) -> str:
    """Maak een kleur donkerder (voor hover/pressed states)."""
    r, g, b = hex_to_rgb(hex_color)
    r = int(r * factor)
    g = int(g * factor)
    b = int(b * factor)
    return f'#{r:02X}{g:02X}{b:02X}'


def lighten_color(hex_color: str, factor: float = 1.2) -> str:
    """Maak een kleur lichter."""
    r, g, b = hex_to_rgb(hex_color)
    r = min(255, int(r * factor))
    g = min(255, int(g * factor))
    b = min(255, int(b * factor))
    return f'#{r:02X}{g:02X}{b:02X}'
