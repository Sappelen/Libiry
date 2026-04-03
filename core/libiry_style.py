"""
Libiry Style - Gedeelde styling en utilities voor alle Libiry tools.

Dit is de CENTRALE module voor:
- Resource file loading (customize folder overrides resources folder)
- Styling (kleuren, fonts, etc.)
- Field name mappings
- Rating conversie (Calibre 0-10 naar Libiry 0-5 met kwart-sterren)
- Andere gedeelde functionaliteit

BELANGRIJK: Functionaliteit wordt NIET dubbel gecodeerd!
Andere modules importeren van hier.
"""

from pathlib import Path
from typing import Dict, Any, Tuple, Optional
import re


# =============================================================================
# Resource File Loading (customize folder overrides resources folder)
# =============================================================================

def get_script_dir() -> Path:
    """Get the Libiry root directory (parent of core/)."""
    return Path(__file__).parent.parent


def load_resource_file(filename: str, script_dir: Path = None) -> Optional[Path]:
    """Find a resource file, preferring customize folder over resources.

    Follows the Libiry convention: files in customize/ override files in resources/.

    Args:
        filename: Name of the file to find (e.g., 'language_codes.txt')
        script_dir: Libiry root directory (default: auto-detect)

    Returns:
        Path to the file if found (customize first, then resources), or None
    """
    if script_dir is None:
        script_dir = get_script_dir()

    # Customize folder has priority
    customize_path = script_dir / 'customize' / filename
    if customize_path.exists():
        return customize_path

    # Fallback to resources
    resources_path = script_dir / 'resources' / filename
    if resources_path.exists():
        return resources_path

    return None


def load_key_value_file(filename: str, script_dir: Path = None) -> Dict[str, str]:
    """Load a key=value mapping file, merging resources and customize.

    First loads from resources/ (defaults), then customize/ (overrides).
    This allows users to extend or override default values.

    Args:
        filename: Name of the file to load (e.g., 'language_codes.txt')
        script_dir: Libiry root directory (default: auto-detect)

    Returns:
        Dict with all key-value pairs (customize values override resources)
    """
    if script_dir is None:
        script_dir = get_script_dir()

    result = {}

    # Load in order: resources first (defaults), customize second (overrides)
    for folder in ['resources', 'customize']:
        file_path = script_dir / folder / filename
        if file_path.exists():
            try:
                for line in file_path.read_text(encoding='utf-8').splitlines():
                    line = line.strip()
                    # Skip empty lines and comments
                    if not line or line.startswith('#'):
                        continue
                    if '=' in line:
                        key, value = line.split('=', 1)
                        key = key.strip()
                        value = value.strip()
                        if key and value:
                            result[key] = value
            except Exception:
                pass  # Continue with what we have

    return result


def iter_resource_folders(script_dir: Path = None):
    """Iterate over resource folders in correct order (resources first, customize second).

    Use this to avoid duplicating the folder loop pattern.

    Args:
        script_dir: Libiry root directory (default: auto-detect)

    Yields:
        Tuple of (folder_name, folder_path) for each existing folder
    """
    if script_dir is None:
        script_dir = get_script_dir()

    for folder in ['resources', 'customize']:
        folder_path = script_dir / folder
        if folder_path.exists():
            yield folder, folder_path


# =============================================================================
# Default Field Names (gedeeld door metadata_extractor, cover_extractor, etc.)
# =============================================================================

DEFAULT_FIELD_NAMES = {
    'cover': 'cover',
    'booktitle': 'booktitle',
    'author': 'author',
    'author_sort': 'author_sort',
    'isbn': 'isbn',
    'rating': 'rating',
    'publisher': 'publisher',
    'year': 'year',
    'publication_date': 'publication_date',
    'language': 'language',
    'pages': 'pages',
    'tags': 'tags',
    'series': 'series',
    'series_index': 'series_index',
    'translator': 'translator',
    'illustrator': 'illustrator',
    'description': 'description',
    'notes': 'notes',
    'file_created': 'file_created',
    'file_modified': 'file_modified',
}


# =============================================================================
# Rating Conversion (Calibre 0-10 naar Libiry 0-5, kwart-sterren)
# =============================================================================

# Calibre gebruikt 0-10 schaal, Libiry gebruikt 0-5 schaal met kwart-sterren
CALIBRE_RATING_MAX = 10.0
LIBIRY_RATING_MAX = 5.0
RATING_STEP = 0.25  # Kwart-sterren


def convert_calibre_rating(calibre_rating: float) -> float:
    """Convert Calibre rating (0-10) to Libiry rating (0-5) with quarter-star precision.

    Args:
        calibre_rating: Rating from Calibre (0-10 scale)

    Returns:
        Rating in Libiry format (0-5 scale, rounded to nearest 0.25)
    """
    if calibre_rating is None:
        return None

    try:
        rating = float(calibre_rating)
    except (TypeError, ValueError):
        return None

    # Convert 0-10 to 0-5
    rating = rating * (LIBIRY_RATING_MAX / CALIBRE_RATING_MAX)

    # Clamp to valid range
    rating = max(0.0, min(LIBIRY_RATING_MAX, rating))

    # Round to nearest quarter-star
    rating = round(rating / RATING_STEP) * RATING_STEP

    return rating


def normalize_rating(rating: float) -> float:
    """Normalize any rating to 0-5 scale with quarter-star precision.

    Args:
        rating: Rating value (assumed to be 0-5 scale already)

    Returns:
        Rating clamped to 0-5 and rounded to nearest 0.25
    """
    if rating is None:
        return None

    try:
        rating = float(rating)
    except (TypeError, ValueError):
        return None

    # Clamp to valid range
    rating = max(0.0, min(LIBIRY_RATING_MAX, rating))

    # Round to nearest quarter-star
    rating = round(rating / RATING_STEP) * RATING_STEP

    return rating


# =============================================================================
# Language Code Normalization
# =============================================================================

# Cache for language code mapping (loaded once)
_language_code_mapping: Dict[str, str] = None


def load_language_code_mapping() -> Dict[str, str]:
    """Load ISO 639-1 to ISO 639-2 mapping.

    Loads from resources/language_codes.txt (defaults) and
    customize/language_codes.txt (user overrides).

    Returns:
        Dict mapping 2-letter codes to 3-letter codes (all lowercase)
    """
    global _language_code_mapping

    if _language_code_mapping is not None:
        return _language_code_mapping

    raw_mapping = load_key_value_file('language_codes.txt')
    # Normalize to lowercase
    _language_code_mapping = {k.lower(): v.lower() for k, v in raw_mapping.items()}
    return _language_code_mapping


def normalize_language_code(lang: str) -> str:
    """Normalize a language code for comparison.

    - Converts to lowercase
    - Maps ISO 639-1 (2-letter) to ISO 639-2 (3-letter) if mapping exists
    - Preserves locale suffixes (en-GB stays eng-gb after base normalization)

    Examples:
        'NL' -> 'nld'
        'en' -> 'eng'
        'en-GB' -> 'eng-gb'
        'nld' -> 'nld' (already 3-letter)

    Args:
        lang: Language code string

    Returns:
        Normalized language code (lowercase, 3-letter if mapping exists)
    """
    if not lang:
        return ''

    lang = str(lang).strip().lower()

    # Check if it has a locale suffix (e.g., en-GB, nl-NL)
    if '-' in lang:
        base, suffix = lang.split('-', 1)
        mapping = load_language_code_mapping()
        if base in mapping:
            return f"{mapping[base]}-{suffix}"
        return lang

    # Simple code without suffix
    mapping = load_language_code_mapping()
    if lang in mapping:
        return mapping[lang]

    return lang


def is_undefined_language(lang: str) -> bool:
    """Check if a language code represents an undefined/unknown language.

    Args:
        lang: Language code string

    Returns:
        True if the language is undefined (UND, undetermined, unknown, etc.)
    """
    if not lang:
        return True

    lang_lower = lang.lower().strip()

    # Common undefined language codes
    undefined_codes = {'und', 'undetermined', 'unknown', 'unk', 'zxx', ''}

    return lang_lower in undefined_codes


def languages_equivalent(lang1: str, lang2: str) -> bool:
    """Check if two language codes represent the same language.

    Normalizes both codes before comparison.
    Note: UND (undefined) is NOT considered equivalent to any real language.

    Args:
        lang1: First language code
        lang2: Second language code

    Returns:
        True if languages are equivalent after normalization
    """
    if not lang1 or not lang2:
        return False

    # Undefined languages are never equivalent to anything
    if is_undefined_language(lang1) or is_undefined_language(lang2):
        return False

    return normalize_language_code(lang1) == normalize_language_code(lang2)


def normalize_author_name(name: str) -> str:
    """Normalize an author name for comparison.

    Converts "Last, First" to "first last" format, lowercased.
    This allows comparing "Niccolò Machiavelli" with "Machiavelli, Niccolò".

    Args:
        name: Author name string

    Returns:
        Normalized name in lowercase "first last" format
    """
    if not name:
        return ''

    name = name.strip().lower()

    # If contains comma, assume "Last, First" format - reverse it
    if ',' in name:
        parts = [p.strip() for p in name.split(',', 1)]
        if len(parts) == 2:
            # "Last, First" -> "first last"
            name = f"{parts[1]} {parts[0]}"

    return name


def authors_equivalent(authors1, authors2) -> bool:
    """Check if two author values represent the same author(s).

    Handles different formats:
    - "First Last" vs "Last, First"
    - List vs string
    - Single author vs list with one author

    Args:
        authors1: First author value (string or list)
        authors2: Second author value (string or list)

    Returns:
        True if authors are equivalent after normalization
    """
    if not authors1 or not authors2:
        return False

    # Convert to lists
    if isinstance(authors1, str):
        authors1 = [authors1]
    if isinstance(authors2, str):
        authors2 = [authors2]

    # Must have same number of authors
    if len(authors1) != len(authors2):
        return False

    # Normalize and sort both lists
    norm1 = sorted(normalize_author_name(a) for a in authors1)
    norm2 = sorted(normalize_author_name(a) for a in authors2)

    return norm1 == norm2


# =============================================================================
# Styling Constants
# =============================================================================

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

    - Eerst resources/customize.txt (defaults)
    - Dan customize/customize.txt (gebruikersinstellingen overschrijven defaults)

    Args:
        script_dir: Pad naar de Libiry folder (standaard: auto-detect)

    Returns:
        Dict met alle style settings (kleuren als hex strings voor tkinter)
    """
    if script_dir is None:
        script_dir = get_script_dir()

    style = DEFAULT_STYLE.copy()

    # Gebruik centrale iter_resource_folders helper
    for folder, folder_path in iter_resource_folders(script_dir):
        customize_path = folder_path / 'customize.txt'
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


def load_field_names(script_dir: Path = None) -> Dict[str, str]:
    """
    Laad veldnamen uit customize.txt.

    - Eerst resources/customize.txt (defaults)
    - Dan customize/customize.txt (gebruikersinstellingen overschrijven defaults)

    Args:
        script_dir: Pad naar de Libiry folder (standaard: auto-detect)

    Returns:
        Dict met veldnaam mappings (bijv. {'booktitle': 'title', 'author': 'author'})
    """
    if script_dir is None:
        script_dir = get_script_dir()

    # Start met DEFAULT_FIELD_NAMES (centrale bron)
    field_names = DEFAULT_FIELD_NAMES.copy()

    # Gebruik centrale iter_resource_folders helper
    for folder, folder_path in iter_resource_folders(script_dir):
        customize_path = folder_path / 'customize.txt'
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
                    # Parse field name settings
                    if key.startswith('field name '):
                        field_key = key.replace('field name ', '').strip()
                        if field_key in field_names:
                            field_names[field_key] = value
            except Exception as e:
                print(f"Warning: Could not read {customize_path}: {e}")

    return field_names


def load_selected_types(script_dir: Path = None) -> set:
    """
    Laad geselecteerde bestandstypes uit selected types.txt.

    LET OP: Deze functie heeft ANDERE volgorde dan andere resource loading!
    - Eerst customize/selected types.txt (gebruikersinstellingen)
    - Dan resources/selected types.txt (defaults)
    Dit is omdat als gebruiker types specificeert, we die exclusief gebruiken.

    Args:
        script_dir: Pad naar de Libiry folder (standaard: auto-detect)

    Returns:
        Set met extensies (bijv. {'.epub', '.mobi', '.pdf'})
    """
    if script_dir is None:
        script_dir = get_script_dir()

    # Default extensies
    default_types = {'.epub', '.mobi', '.azw', '.azw3', '.pdf', '.cbr', '.cbz', '.md', '.markdown'}

    # LET OP: customize EERST, dan resources (niet mergen maar overriden)
    for folder in ['customize', 'resources']:
        types_path = script_dir / folder / 'selected types.txt'
        if types_path.exists():
            try:
                content = types_path.read_text(encoding='utf-8')
                types = set()
                for line in content.split('\n'):
                    line = line.strip().lower()
                    if line and line.startswith('.'):
                        types.add(line)
                if types:
                    return types
            except Exception as e:
                print(f"Warning: Could not read {types_path}: {e}")

    return default_types


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
