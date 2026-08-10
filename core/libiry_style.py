"""Libiry Style - Shared styling and utilities for all Libiry tools
This is the central module for:
- Resource file loading (customize folder overrides resources folder)
- Styling (colors, fonts, etc.)
- Field name mappings
- Rating conversion (Calibre 0-10 to Libiry 0-5 with quarter stars)
- Language/author normalization
- Other shared functionality
"""
from kivy.app import App
from pathlib import Path
from typing import Dict, Any
import re
import sys
import os
from kivy.storage.jsonstore import JsonStore
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.widget import Widget
from kivy.uix.label import Label
from kivy.uix.relativelayout import RelativeLayout
from kivy.uix.textinput import TextInput
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.popup import Popup
from kivy.uix.image import Image
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.graphics import Color, Rectangle, RoundedRectangle, Line, InstructionGroup
from kivy.properties import StringProperty, ObjectProperty
from kivy.core.window import Window

# =============================================================================
# Resource File Loading (customize folder overrides resources folder)
# =============================================================================

def draw_capsule_bar(sv, bar_color, bar_width, _attr='_capsule_bar_group'):
    """Draw a capsule scrollbar on any ScrollView
    Shared by RoundedScrollView and _style_filechooser so both produce identical output"""
    old = getattr(sv, _attr, None)
    if old is not None:
        try:
            sv.canvas.after.remove(old)
        except ValueError:
            pass
    if not hasattr(sv, 'viewport_size') or sv.viewport_size[1] <= sv.height:
        return
    viewport_ratio = sv.height / sv.viewport_size[1]
    bar_height = max(bar_width * 3, viewport_ratio * sv.height)
    bar_x = sv.right - bar_width - dp(2)
    bar_y = sv.y + (sv.height - bar_height) * sv.scroll_y
    group = InstructionGroup()
    group.add(Color(*bar_color))
    group.add(RoundedRectangle(
        pos=(bar_x, bar_y),
        size=(bar_width, bar_height),
        radius=[bar_width / 2],
    ))
    setattr(sv, _attr, group)
    sv.canvas.after.add(group)

def get_script_dir() -> Path:
    """Get the Libiry root directory (parent of core/)"""
    return Path(__file__).parent.parent

def get_user_data_dir() -> Path:
    r"""Platform-specific user data directory for Libiry settings:
    Windows: %APPDATA%\Libiry
    macOS:   ~/Library/Application Support/Libiry
    Linux:   $XDG_DATA_HOME/Libiry or ~/.local/share/Libiry"""
    if sys.platform == 'win32':
        base = Path(os.environ.get('APPDATA', str(Path.home() / 'AppData' / 'Roaming')))
    elif sys.platform == 'darwin':
        base = Path.home() / 'Library' / 'Application Support'
    else:
        xdg = os.environ.get('XDG_CONFIG_HOME', '')
        base = Path(xdg) if xdg else Path.home() / '.config'
    return base / 'Libiry'
    
def get_cache_dir() -> Path:
    r"""Platform-specific cache directory for Libiry
    Windows: %LOCALAPPDATA%\Libiry\cache
    macOS:   ~/Library/Caches/Libiry
    Linux:   $XDG_CACHE_HOME/Libiry or ~/.cache/Libiry"""
    if sys.platform == 'win32':
        base = Path(os.environ.get('LOCALAPPDATA', str(Path.home() / 'AppData' / 'Local')))
        return base / 'Libiry' / 'cache'
    elif sys.platform == 'darwin':
        return Path.home() / 'Library' / 'Caches' / 'Libiry'
    else:
        xdg = os.environ.get('XDG_CACHE_HOME', '')
        base = Path(xdg) if xdg else Path.home() / '.cache'
        return base / 'Libiry'    

def get_customize_dirs() -> list:
    """Customize directories in priority order: user data first, app dir as dev/portable fallback
    Callers must check if path.exists() themselves"""
    return [
        get_user_data_dir() / 'customize',
        get_script_dir() / 'customize',
    ]

def load_selected_types() -> set:
    """Load selected file types from selected types.txt
    BEWARE: This function has ANOTHER sequence than other resource loading!
    - First customize/selected types.txt 
    - Then resources/selected types.txt 
    Because if a user specifies types, we only use those
    Returns: Set with extensions (f.e. {'.epub', '.mobi', '.pdf'})"""
    script_dir = get_script_dir()

    # Default extensions
    default_types = {'.epub', '.mobi', '.azw', '.azw3', '.pdf', '.cbr', '.cbz', '.md', '.markdown'}

    # BEWARE: customize FIRST, THEN resources (no merge but override)
    for types_dir in get_customize_dirs() + [script_dir / 'resources']:
        types_path = types_dir / 'selected types.txt'
        
        if types_path.exists():
            try:
                content = types_path.read_text(encoding='utf-8', errors='replace')
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

def is_os_hidden(path: Path) -> bool:
    """Returns True if path is hidden at the OS level
    Works cross-platform. Hidden items:
    - Unix/Mac: name starts with '.'
    - Windows: has hidden attribute (e.g., $Recycle.Bin)"""
    # 1 Unix-style doc or folder: starts with dot
    if path.name.startswith('.'):
        return True
    # 2 Windows: check hidden attribute
    if sys.platform == 'win32':
        try:
            import ctypes
            attrs = ctypes.windll.kernel32.GetFileAttributesW(str(path))
            if attrs != -1 and (attrs & 0x2):
                return True
        except Exception:
            pass
    return False

def is_hidden(filepath: Path, selected_types) -> bool:
    """Checks if a file or folder should be hidden in Libiry
    - Files whose extension is not in selected_types
    - Files ending with '[selected_types].md' (metadata sidecars)
    - Files ending with '.opf' (metadata sidecars)
    Args: filepath: Path object to check
    Returns: True if the item should be hidden from display"""

    name = filepath.name
    
    # 1-2 OS-level: dot-prefix (Unix) or Windows hidden attribute
    if is_os_hidden(filepath):
        return True

    # 3 All folders that passed the criteria up until now must be shown
    if filepath.is_dir():
        return False

    # 4 The following criteria are for files only
    name_lower = name.lower()

    # 5 Skip opf sidecars
    if name_lower.endswith('.opf'): 
        return True 

    #print(f"DEBUG filepath.suffix.lower(): '{filepath.suffix.lower()}'")
    #print(f"selected_types): '{selected_types}'")

    # 6 Hide markdown sidecars for hidden file types. Only markdown BOOKS are shown, based on naming alone. Note that the logic in Check_and_consolidate_metadata.py/ cleanup_redundant_sidecars is much more precise
    if name_lower.endswith(('.md', '.markdown')):
        if len(Path(name_lower).suffixes) >= 2:   # compound → sidecar
            return True # Does about the same as get_document_type in main.py
        
    # 7 Hide files whose extension is not in selected_types
    if filepath.suffix.lower() not in selected_types:
        return True   

    return False

def load_key_value_file(filename: str, script_dir: Path = None) -> Dict[str, str]:
    """Load a key value mapping file, merging resources and customize
    First loads from resources/ (defaults), then customize/ (overrides)
    This allows users to extend or override default values
    Args:
        filename: Name of the file to load (e.g., 'language_codes.txt')
        script_dir: Libiry root directory (default: auto-detect)
    Returns Dict with all key-value pairs (customize values override resources)"""
    if script_dir is None:
        script_dir = get_script_dir()

    result = {}

    # Load in order: resources first (defaults), customize second (overrides)
    for directory in [script_dir / 'resources'] + get_customize_dirs():
        filepath = directory / filename
        if file_path.exists():
            try:
                for line in file_path.read_text(encoding='utf-8', errors='replace').splitlines():
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

# =============================================================================
# Default field names (shared by metadata_extractor, cover_extractor, etc.)
# =============================================================================

DEFAULT_FIELD_NAMES = {
    'cover': 'cover',
    'booktitle': 'booktitle',
    'author': 'author',
    'author_sort': 'author_sort',
    'isbn': 'isbn',
    'rating': 'rating',
    'publisher': 'publisher',
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
    'book_created': 'book_created',
    'book_modified': 'book_modified',
}

# =============================================================================
# Rating conversion (Calibre 0-10 to Libiry 0-5, quarter stars)
# =============================================================================

CALIBRE_RATING_MAX = 10.0
LIBIRY_RATING_MAX = 5.0
RATING_STEP = 0.25  # Quarter stars

def convert_calibre_rating(calibre_rating: float) -> float:
    """Convert Calibre rating (0-10) to Libiry rating (0-5) with quarter-star precision
    Args: calibre_rating: Rating from Calibre (0-10 scale)
    Returns: Rating in Libiry format (0-5 scale, rounded to nearest 0.25)"""
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

# =============================================================================
# Language code normalization
# =============================================================================

# Cache for language code mapping (loaded once)
_language_code_mapping: Dict[str, str] = None

def load_language_code_mapping() -> Dict[str, str]:
    """Load ISO 639-1 to ISO 639-2 mapping
    Loads from resources/language_codes.txt (defaults) and
    customize/language_codes.txt (user overrides).
    Returns Dict mapping 2-letter codes to 3-letter codes (all lowercase)"""
    global _language_code_mapping

    if _language_code_mapping is not None:
        return _language_code_mapping

    raw_mapping = load_key_value_file('language_codes.txt')
    # Normalize to lowercase
    _language_code_mapping = {k.lower(): v.lower() for k, v in raw_mapping.items()}
    return _language_code_mapping

def normalize_language_code(lang: str) -> str:
    """Normalize a language code for comparison
    - Converts to lowercase
    - Maps ISO 639-1 (2-letter) to ISO 639-2 (3-letter) if mapping exists
    - Preserves locale suffixes (en-GB stays eng-gb after base normalization)
    Examples:
        'NL' -> 'nld'
        'en' -> 'eng'
        'en-GB' -> 'eng-gb'
        'nld' -> 'nld' (already 3-letter)
    Args: lang: Language code string
    Returns: Normalized language code (lowercase, 3-letter if mapping exists)"""
    if not lang:
        return ''

    lang = str(lang).strip().lower()

    # Check if it has a local suffix (e.g., en-GB, nl-NL)
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
    """Check if a language code represents an undefined/unknown language
    Args: lang: Language code string
    Returns: True if the language is undefined (UND, undetermined, unknown, etc.)"""
    if not lang:
        return True

    lang_lower = lang.lower().strip()

    # Common undefined language codes
    undefined_codes = {'und', 'undetermined', 'unknown', 'unk', 'zxx', ''}

    return lang_lower in undefined_codes

def normalize_author_name(name: str) -> str:
    """Normalizes an author name for comparison
    Converts "Last, First" to "first last" format, lowercased
    This allows comparing "Niccolò Machiavelli" with "Machiavelli, Niccolò"
    Args: name: Author name string
    Returns: Normalized name in lowercase "first last" format"""
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
    """Checks if two author values represent the same author(s)
    Handles different formats:
    - "First Last" vs "Last, First"
    - List vs string
    - Single author vs list with one author
    Args:
        authors1: First author value (string or list)
        authors2: Second author value (string or list)
    Returns True if authors are equivalent after normalization"""
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
# Styling constants
# =============================================================================

# Default Libiry settings
DEFAULT_SETTINGS = {
    'location': '',
    'background_color': (0.44, 0.62, 0.62, 1), # Teal '#6F9D9F' 
    'background_font_color': (0, 0, 0, 1),     # Black '#000000'
    'accent_color': (0.47, 0.25, 0.31),        # Aubergine '#793F4E' 
    'accent_font_color': (1, 1, 1, 1),         # White '#FFFFFF' 
    'tile_font_color': (0, 0, 0, 1),           # Font color on grid tiles     
    'rounded_corners': True,
    'fuzzy_search': False,  # Default off - exact substring match
    'metadata_in_sidecar': False,  # Default off - keep metadata in book files when possible
    'scrollbar_width': 10,  # Scrollbar thickness in dp
    'scrollbar_always_visible': True,  # Scrollbar altijd zichtbaar
    'show_book_title': False,  # Show title/author on covers with image
    'show_tags': True,  # Show tag list at the bottom of LibiryApp
    'tag_lines': 3,  # Max visible lines in tag bar before scrolling
    'font_size': 12,
    #'button_height': 40, venv field, not used
    #'row_height': 40, venv field, not used
    # Configurable field names for markdown parsing
    'field_names': {},   
}

def parse_color(color_str: str) -> tuple:
    """Parse color string to RGBA tuple (0-1 range)
       Accepts some named colors
       Hex:  '#RRGGBB'  or  '#RRGGBBAA'
       Falls back to light grey (0.9, 0.9, 0.9, 1) on parse failure"""
    color_str = color_str.strip().lower()

    named_colors = {
        'white': (1, 1, 1, 1),
        'black': (0, 0, 0, 1),
        'red': (1, 0, 0, 1),
        'green': (0, 1, 0, 1),
        'blue': (0, 0, 1, 1),
        'gray': (0.5, 0.5, 0.5, 1),
        'grey': (0.5, 0.5, 0.5, 1),
        'purple': (0.5, 0, 0.5, 1),
        'lila': (0.8, 0.6, 0.8, 1), 
    }

    if color_str in named_colors:
        return named_colors[color_str]

    if color_str.startswith('#'):
        hex_color = color_str[1:]
        if len(hex_color) == 6:
            r = int(hex_color[0:2], 16) / 255
            g = int(hex_color[2:4], 16) / 255
            b = int(hex_color[4:6], 16) / 255
            return (r, g, b, 1)
        elif len(hex_color) == 8:
            r = int(hex_color[0:2], 16) / 255
            g = int(hex_color[2:4], 16) / 255
            b = int(hex_color[4:6], 16) / 255
            a = int(hex_color[6:8], 16) / 255
            return (r, g, b, a)

    return (0.9, 0.9, 0.9, 1)

def parse_bool(value: str) -> bool:
    """Parse a boolean value from customize.txt"""
    return value.strip().lower() not in ('n', 'no', 'false', '0')

# =============================================================================
# Customization loading
# =============================================================================
def get_icon_path(app_path: Path, icon_name: str) -> str:
    """Get icon path, preferring customize folder over resources
    Args:
        app_path: Base application path
        icon_name: Name of the icon file (e.g., 'back.png')"""

    # Customize folder has priority 
    for cust_dir in get_customize_dirs():
        customize_path = cust_dir / 'icons' / icon_name
        if customize_path.exists():
            return str(customize_path)

    # Use iconsdarkmode folder in dark mode, otherwise icons folder
    resources_path = app_path / 'resources' / 'icons' / icon_name
    if resources_path.exists():
        return str(resources_path)

    return ''

def measure_text_size(text: str, font_size, h_padding=None, v_padding=None):
    """Returns (width, height) needed to render text at font_size plus padding
    h_padding (horizontal padding) defaults to dp(24) — 12dp each side, for buttons
    v_padding (vertical padding) defaults to dp(8) — 4dp each side, for labels
    Uses Label.texture_update() for synchronous measurement — same technique as _show_tooltip. Kept at module level so both LibiryKivyApp methods and HoverBehavior (a widget mixin) can call it without App coupling"""
    
    tmp = Label(text=text, font_size=font_size)
    tmp.texture_update()
    h = tmp.texture_size[0] + (h_padding if h_padding is not None else dp(24))
    v = tmp.texture_size[1] + (v_padding if v_padding is not None else dp(8))
    return h, v

def _scroll_to_end(inst, *_):
    """Bind target: scrolls a TextInput so the rightmost text is visible
    Works regardless of focus or readonly state by setting scroll_x directly"""
    def _do(dt):
        if not inst.text:
            inst.scroll_x = 0
            return
        tmp = Label(text=inst.text, font_size=inst.font_size)
        tmp.texture_update()
        text_w = tmp.texture_size[0]
        avail = inst.width - inst.padding[0] - inst.padding[2]
        inst.scroll_x = max(0, text_w - avail)
    Clock.schedule_once(_do, 0)

class RoundedBackground(Widget):
    """Reusable background widget with optional rounded corners
    Used for SearchBox, Settings input fields and other UI elements that need a colored background with consistent styling
    Args:
        bg_color: Background color tuple (r, g, b, a)
        rounded: If True, all corners rounded. If False, no rounding.
        radius: Custom radius list [top-left, top-right, bottom-right, bottom-left]"""

    def __init__(self, bg_color, rounded, radius=None, **kwargs):
        super().__init__(**kwargs)
        self._bg_color = bg_color
        self._rounded = rounded
        self._radius = radius
        self.bg_rect = None #Same name as in venv
        self.bind(pos=self._update, size=self._update)
        
    def _update(self, *args):
        self.canvas.clear()
        with self.canvas:
            Color(*self._bg_color)
            if self._radius is not None:
                self.bg_rect = RoundedRectangle(pos=self.pos, size=self.size, radius=self._radius)
            elif self._rounded:
                self.bg_rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(5)])
            else:
                self.bg_rect = Rectangle(pos=self.pos, size=self.size)

class HoverBehavior:
    """Mixin for hover detection with tooltip support.
    Uses collide_point for hit detection and widget.pos for positioning —
    both in Kivy's y-from-bottom window coordinate system.
    to_window(0,0) is NOT used: with initial=True it returns the parent's
    position, not the widget's, causing a coordinate-system mismatch."""

    tooltip_text = None
    _active_tooltip = None  # class-level singleton: one tooltip at a time

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        Window.bind(mouse_pos=self._on_mouse_pos)
        self._is_hovering = False

    def on_enter(self):
        if self.tooltip_text:
            self._show_tooltip()

    def _on_mouse_pos(self, window, pos):
        if not self.get_root_window():
            return
        # Suppress hover/tooltip when any popup is open (settings, dialogs, etc.)
        if any(isinstance(c, Popup) for c in Window.children):
            if self._is_hovering:
                self._is_hovering = False
                self.on_leave()
            return

        if isinstance(self.parent, GridLayout):
            gl = self.parent
            sv = gl.parent  # RoundedScrollView — keeps gl.pos=(0,0), positions content via canvas transform only, so gl.y never reflects visual position
            # canvas_translate = the visual upward shift applied by ScrollView's canvas transform
            # scroll_y=1.0 → content at top; scroll_y=0.0 → content at bottom
            canvas_translate = sv.y + (sv.height - gl.height) * sv.scroll_y
            corrected_y = pos[1] - canvas_translate
            inside = self.collide_point(pos[0], corrected_y)

            #print(f"DEBUG", sv.y, sv.height, gl.height, sv.scroll_y)

        elif isinstance(self.parent, RelativeLayout):
            # Wrapped toolbar icon (ImageButton inside RelativeLayout container). self.x/y is relative to the container — add container's absolute pos
            abs_x = self.parent.x + self.x
            abs_y = self.parent.y + self.y
            inside = (abs_x <= pos[0] <= abs_x + self.width) and \
                     (abs_y <= pos[1] <= abs_y + self.height)

        else:
            # Direct BoxLayout child (SearchBox, Twins, ColoredButtons)
            # self.x/y is absolute window coords — collide_point works directly
            inside = self.collide_point(*pos)

        if inside and not self._is_hovering:
            self._is_hovering = True
            self.on_enter()
        elif not inside and self._is_hovering:
            self._is_hovering = False
            self.on_leave()

    def on_leave(self):
        self._hide_tooltip()

    def _show_tooltip(self, mouse_pos=None):
        HoverBehavior._destroy_active_tooltip()
       
        app = App.get_running_app()
        # Cap at 400 dp or window width minus margin, whichever is smaller
        max_w = min(dp(400), Window.width - dp(20))
        tooltip = Label(
            text=self.tooltip_text,
            size_hint=(None, None),
            font_size=app.FONT_SIZE,
            color=app.ACCENT_FONT_COLOR,
            text_size=(None, None),
            halign='left',
            valign='top',
        )
        
        tooltip.texture_update()
        
        # Wrap tooltip if the widest line exceeds the maximum width
        if tooltip.texture_size[0] > max_w - dp(16):
            tooltip.text_size = (max_w - dp(16), None)
            tooltip.texture_update()
      
        natural_h = tooltip.texture_size[1]
        max_content_h = app.FONT_SIZE * 1.5 * 10  # cap at ~10 lines
        if natural_h > max_content_h:
            # Re-render with height cap so Kivy clips the text at line 10
            tooltip.text_size = (max_w - dp(16), max_content_h)
            tooltip.texture_update()
        tooltip.size = (
            min(tooltip.texture_size[0] + dp(16), max_w),
            min(natural_h, max_content_h) + dp(8),
        )

        if isinstance(self.parent, GridLayout):
            gl = self.parent
            sv = gl.parent
            canvas_translate = sv.y + (sv.height - gl.height) * sv.scroll_y
            abs_center_x = self.center_x  # x is correct; no horizontal scroll
            abs_y   = self.y  + canvas_translate
            abs_top = self.top + canvas_translate
            x_pos = abs_center_x - tooltip.width / 2
            y_pos = abs_y - tooltip.height - dp(5)
            if y_pos < dp(5):
                y_pos = abs_top + dp(5)
                  
        # For ImageButtons inside a RelativeLayout container, self.x/y is
        # parent-relative — compute absolute bounds manually.
        elif isinstance(self.parent, RelativeLayout):
            abs_center_x = self.parent.x + self.x + self.width / 2
            abs_y        = self.parent.y + self.y
            abs_top      = self.parent.y + self.top
            x_pos = abs_center_x - tooltip.width / 2
            y_pos = abs_y - tooltip.height - dp(5) # preferred: below widget
            if y_pos < dp(5):
                y_pos = abs_top + dp(5) # flip: above widget
        else:
            x_pos = self.center_x - tooltip.width / 2
            y_pos = self.y - tooltip.height - dp(5) # preferred: below widget
            if y_pos < dp(5):
                y_pos = self.top + dp(5) # flip: above widget

        x_pos = max(dp(5), min(x_pos, Window.width - tooltip.width - dp(5)))
        y_pos = max(dp(5), min(y_pos, Window.height - tooltip.height - dp(5)))

        tooltip.pos = (x_pos, y_pos)
        with tooltip.canvas.before:
            Color(*app.ACCENT_COLOR)
            RoundedRectangle(pos=tooltip.pos, size=tooltip.size, radius=[dp(4)])

        root = self.get_root_window()
        if root:
            root.add_widget(tooltip)
            HoverBehavior._active_tooltip = tooltip

    @classmethod
    def _destroy_active_tooltip(cls):
        if cls._active_tooltip:
            parent = cls._active_tooltip.parent
            if parent:
                parent.remove_widget(cls._active_tooltip)
            cls._active_tooltip = None

    def _hide_tooltip(self):
        HoverBehavior._destroy_active_tooltip()
          
class ColoredButton(HoverBehavior, ButtonBehavior, Label):
    """A button with background color and optional rounded corners
    Args:
        bg_color: Background color tuple (r, g, b, a)
        rounded: If True, all corners rounded. If False, no rounding.
        radius: Custom radius list [top-left, top-right, bottom-right, bottom-left]. Overrides 'rounded' parameter if provided"""

    def __init__(self, bg_color=(0.5, 0.5, 0.5, 1), rounded=True, radius=None, **kwargs):
        super().__init__(**kwargs)
        self._bg_color = bg_color
        self._rounded = rounded
        self._radius = radius  # Custom radius per corner
        self.bg_rect = None
        Clock.schedule_once(self._draw_bg, 0.1)
        self.bind(pos=self._update_tile, size=self._update_tile)
        #print(f"DEBUG tile pos and size", self.pos,  self.size)

    def _draw_bg(self, dt):
        """Draw background after widget has size"""
        with self.canvas.before:
            Color(*self._bg_color)
            if self._radius is not None:
                # Custom radius per hoek
                self.bg_rect = RoundedRectangle(pos=self.pos, size=self.size, radius=self._radius)
            elif self._rounded:
                self.bg_rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(5)])
            else:
                self.bg_rect = Rectangle(pos=self.pos, size=self.size)

    def _update_tile(self, *args):
        if self.bg_rect:
            self.bg_rect.pos = self.pos
            self.bg_rect.size = self.size 

class LocationBox(RelativeLayout):
    """Location/path box (transparent)"""

    def __init__(self, fg_color, font_size=None, **kwargs):
        super().__init__(**kwargs)
        self._font_size = font_size if font_size else dp(14)

        # Text input (transparent background, no border, readonly)
        # Padding scales with font size: horizontal broader, vertical minimal so that text is not cut off for smaller bar heights
        h_pad = dp(10)  # Horizontal padding set
        v_pad = self._font_size * 0.3  # Vertical padding proportional to font size
        self.text_input = TextInput(
            text='',
            multiline=False,
            readonly=True,
            background_color=(0, 0, 0, 0),  # Transparent
            background_normal='',  # No border
            background_active='',  # No border
            foreground_color=fg_color,
            font_size=self._font_size,
            padding=[h_pad, v_pad, h_pad, v_pad],
            size_hint=(1, 1),
            pos_hint={'x': 0, 'y': 0},
        )
        self.add_widget(self.text_input)

        # Align text boxt text to the right
        self.text_input.bind(text=_scroll_to_end, size=_scroll_to_end)

    @property
    def text(self):
        return self.text_input.text

    @text.setter
    def text(self, value):
        self.text_input.text = value

class SearchBox(HoverBehavior, RelativeLayout):
    """Search box with magnifying glass icon overlay"""
        
    def __init__(self, app_path, bg_color, fg_color, rounded, on_text_change, font_size=None, **kwargs):   
        
        super().__init__(**kwargs)
        self._font_size = font_size if font_size else dp(14)

        # Background widget
        self.bg_widget = RoundedBackground(
            bg_color=bg_color,
            rounded=rounded,
            size_hint=(1, 1),
            pos_hint={'x': 0, 'y': 0},
        )
        self.add_widget(self.bg_widget)

        # Text input (transparent)
        # Padding scales with font size for vertical centering
        h_pad = dp(10)  # Horizontal padding links
        v_pad = self._font_size * 0.5  # Vertical padding for better centering
        icon_size = self._font_size * 1.7
        # Right padding = icon width + same margin as vertical
        r_pad = icon_size + v_pad
        self.text_input = TextInput(
            hint_text='',
            multiline=False,
            background_color=(0, 0, 0, 0),  # Transparent
            background_normal='',  # No border
            background_active='',  # No border when active
            foreground_color=fg_color,
            cursor_color=fg_color,
            font_size=self._font_size,
            padding=[h_pad, v_pad, r_pad, v_pad],
            size_hint=(1, 1),
            pos_hint={'x': 0, 'y': 0},
        )
        self.text_input.bind(text=on_text_change)
        self.add_widget(self.text_input)

        # Search icon (magnifying glass) - right same margin as above/under
        # v_pad is used for consistent spacing on all sides
        search_icon = get_icon_path(app_path, 'search.png')
        if search_icon:
            self.search_img = Image(
                source=search_icon,
                size_hint=(None, None),
                size=(icon_size, icon_size),
            )
            # Bind position to parent size for absolute positioning
            def update_icon_pos(instance, value):
                # Positie: right with v_pad marge, vertical centered
                self.search_img.right = self.width - v_pad
                self.search_img.center_y = self.height / 2
            self.bind(size=update_icon_pos, pos=update_icon_pos)
            self.add_widget(self.search_img)

    @property
    def text(self):
        return self.text_input.text

    @text.setter
    def text(self, value):
        self.text_input.text = value

class StyledCheckBox(ButtonBehavior, Widget):
    """Custom checkbox. Replaces the default Kivy CheckBox that is hard to style"""

    active = ObjectProperty(False)

    def __init__(self, rounded=True, **kwargs):
        # Pop active before we call super()
        # This prevents ObjectProperty initialisation issues
        initial_active = kwargs.pop('active', False)
        super().__init__(**kwargs)
        self._rounded = rounded
        self.size_hint = (None, None)
        self.size = (dp(24), dp(24))
        self.bind(pos=self._update, size=self._update, active=self._update)
        # Set active NA binding, so that _update is called
        self.active = initial_active
        Clock.schedule_once(lambda dt: self._update(), 0.1)

    def _update(self, *args):
        """Draw checkbox with optional checkmark"""
        self.canvas.clear()
        with self.canvas:
            Color(*App.get_running_app().ACCENT_FONT_COLOR) # "white"
            
            if self._rounded:
                RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(3)])
            else:
                Rectangle(pos=self.pos, size=self.size)

            # Checkmark if active
            if self.active:
                #Color(0, 0, 0, 1)
                Color(*App.get_running_app().ACCENT_COLOR) # "aubergine"
                # Draw checkmark with two lines
                cx, cy = self.pos[0] + self.size[0] / 2, self.pos[1] + self.size[1] / 2
                # Checkmark points: left-middle -> below-middle -> Right-top
                Line(
                    points=[
                        cx - dp(6), cy,           # links
                        cx - dp(2), cy - dp(5),   # onder-midden
                        cx + dp(6), cy + dp(5),   # rechts-boven
                    ],
                    width=dp(2),
                )

    def on_release(self):
        """Toggle active state at click"""
        self.active = not self.active

# =============================================================================
# LibiryKivyApp — shared base class for all Libiry satellite apps
# - Inherits directly from kivy.app.App
# - App import is placed here (not at the top of the file) to minimize the
#   risk of triggering Kivy window initialization before Config.set() calls
#   in consuming scripts. Kivy creates the window on the first import of
#   kivy.core.window, which kivy.app triggers indirectly
# - _load_style() is called in __init__ after super().__init__(**kwargs) so
#   that Kivy's EventDispatcher is ready before we do anything with it
# =============================================================================

class  LibiryKivyApp(App):
    """Base class for all Libiry apps with shared styling and widgets
      Usage:
          class MyApp(LibiryKivyApp):
              def __init__(self, **kwargs):
                  super().__init__(**kwargs)
                  self._setup_kivy_app('My App', 550, 350)

              def _create_widgets(self):
                  self._create_label(self._layout, 'Hello', style='title')
                  self._create_button(self._layout, 'OK', self._on_ok)

          if __name__ == '__main__':
              MyApp().run()
      """

    def __init__(self, **kwargs):
        # App.__init__ initializes Kivy's EventDispatcher and property system. Must run before _load_style() so that Kivy properties on self are ready
        super().__init__(**kwargs)
        self._current_folder = None
        self._settings_inputs = {}
        settings_dir = get_user_data_dir()
        settings_dir.mkdir(parents=True, exist_ok=True)
        self.store = JsonStore(str(settings_dir / "settings.json"))
        self._load_style()
        self.selected_types = load_selected_types()

        # Lazy import: metadata_extractor.py imports from libiry_style.py,
        # so this cannot be a module-level import without causing a circular dependency. Inside __init__ is safe because both modules are fully loaded by then
        from core.metadata_extractor import MetadataExtractor
        self.extractor = MetadataExtractor(self.field_names)
   
    def _load_customization(self) -> Dict[str, Any]:
        """Load Libiry styling from customize.txt 
        - First resources/customize.txt (defaults)
        - Then customize/customize.txt (user customizations overwrite defaults)
        Returns Dict with all settings
        A.o. the field name mappings (f.e. {'booktitle': 'titlecustomfieldname', 'author': 'authorcustomfieldname'})"""
        script_dir = get_script_dir()

        # Fallback
        settings = DEFAULT_SETTINGS.copy() 
        field_names = DEFAULT_FIELD_NAMES.copy()

        for directory in [script_dir / 'resources'] + get_customize_dirs():
            customize_path = directory / 'customize.txt'         
            
            if customize_path.exists():
                try:
                    content = customize_path.read_text(encoding='utf-8', errors='replace')

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

                        # Parse other settings 
                        if key == 'location' and value: #only overwrite if the value is not empty
                            settings['location'] = value             
                        elif key == 'background color':
                            settings['background_color'] = parse_color(value)
                        elif key == 'background font color':
                            settings['background_font_color'] = parse_color(value)
                        elif key == 'accent color':
                            settings['accent_color'] = parse_color(value)
                        elif key == 'accent font color':
                            settings['accent_font_color'] = parse_color(value)
                        elif key == 'tile font color':
                            settings['tile_font_color'] = parse_color(value)
                        elif key == 'rounded corners':
                            settings['rounded_corners'] = parse_bool(value)
                        elif key == 'fuzzy search':
                            settings['fuzzy_search'] = parse_bool(value)
                        elif key == 'metadata in sidecar':
                            settings['metadata_in_sidecar'] = parse_bool(value)
                        elif key == 'scrollbar width':
                            try:
                                settings['scrollbar_width'] = int(value)
                            except ValueError:
                                pass
                        elif key == 'scrollbar always visible':
                            settings['scrollbar_always_visible'] = parse_bool(value) 
                        elif key == 'show book title':
                            settings['show_book_title'] = parse_bool(value)
                        elif key == 'show tags':
                            settings['show_tags'] = parse_bool(value)
                        elif key == 'tag lines':
                            settings['tag_lines'] = int(value)
                        elif key in ('font size'):
                            try:
                                settings['font_size'] = int(value)
                            except ValueError:
                                pass 
                    # No break - both files must be read
                    # (resources first for defaults, customize afterwards for user overrides)
                except Exception as e:
                    print(f"Error loading customization: {e}")
                
        settings['field_names'] = field_names   

        return settings

    def _seed_customize_dir(self):
        """Copy everything from the resources folder into the user customize dir on first run. Triggered when subfolder icons is absent. Only copies files that do not exist yet"""
        import shutil
        user_customize = get_user_data_dir() / 'customize'
        if (user_customize / 'icons').exists():
            return
        src = get_script_dir() / 'resources'
        if not src.exists():
            return
        try:
            for src_file in src.rglob('*'):
                if src_file.is_file():
                    dst_file = user_customize / src_file.relative_to(src)
                    if not dst_file.exists():
                        dst_file.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(src_file, dst_file)
        except Exception as e:
            print(f"Warning: could not seed customize dir: {e}")

    def _load_style(self):
        self._seed_customize_dir()
        try:
            self.custom = self._load_customization()
        except Exception:
            self.custom = DEFAULT_SETTINGS.copy()
        
        # Field names 
        self.field_names = self.custom['field_names']
 
        # Color settings
        self.BG_COLOR = self.custom['background_color']
        self.BG_FONT_COLOR = self.custom['background_font_color']
        self.ACCENT_COLOR = self.custom['accent_color']
        self.ACCENT_FONT_COLOR = self.custom['accent_font_color']
        self.TILE_FONT_COLOR = self.custom['tile_font_color']

        # Other settings
        self.FONT_SIZE = dp(self.custom['font_size'])
        self.UI_BAR_HEIGHT = self.FONT_SIZE * 2.5
        self.SCROLLBAR_WIDTH = dp(self.custom['scrollbar_width'])
        self.SCROLLBAR_ALWAYS_VISIBLE = self.custom['scrollbar_always_visible'] 
        self.ROUNDED = self.custom['rounded_corners'] 
        self.TAG_LINES = self.custom['tag_lines']
        
    def navigate_to(self, path: Path, add_to_history: bool = False):
        """Navigate to a folder
        Updates whichever input widget is present:
        - 'input_folder' in _settings_inputs → satellite apps using _add_location_field
        - path_box attribute → main.py using _build_path_bar"""
          
        if not path.exists() or not path.is_dir():
            self._show_error(f"Folder not found: {path}")
            return
        self._current_folder = path
        if 'input_folder' in self._settings_inputs:
            self._settings_inputs['input_folder'].text = str(path)
        elif hasattr(self, 'path_box'):
            self.path_box.text = str(path)
        self._on_navigate(path, add_to_history)

    def _on_navigate(self, path: Path, add_to_history: bool):
        pass    # base does nothing; subclasses override to add app-specific behaviour
      
    def _load_last_folder(self):
        """1. Returns the last path
           2. Schedules navigate_to(last_path) via Clock.schedule_once         
        Folder location logica (priority high to low):
        1. Location from customize/customize.txt
        2. Location from resources/customize.txt (only if customize empty)
        3. Current work directory
        4. If the chosen folder does not exist, use current work directory"""
        
        start_path = None

        # Step 1+2: Location from customize.txt (folder customize takes precedence over folder resources)
        if self.custom.get('location'):
            loc = Path(self.custom['location'])
            if loc.exists() and loc.is_dir():
                start_path = loc

        # Step 3: Fallback to Home
        if not start_path:
            cwd = Path.home()
            if cwd.exists() and cwd.is_dir():
                start_path = cwd

        # Step 4: if the chosen path does not exist (anymore), use current work directory
        if start_path and not start_path.exists():
            start_path = Path.home()

        try:
            if self.store.exists('zoom_level'):
                self._zoom_level = self.store.get('zoom_level')['value']
        except Exception:
            pass

        if start_path:
            Clock.schedule_once(lambda dt: self.navigate_to(start_path), 0)
            
        return start_path

    def _build_path_bar(self, button_text='Choose folder', width=None):

        path_bar = BoxLayout(size_hint_y=None, height=self.UI_BAR_HEIGHT, spacing=dp(5))

        # Location box (no "Location:" label)
        self.path_box = LocationBox(
            fg_color=self.BG_FONT_COLOR,
            font_size=self.FONT_SIZE,
            size_hint=(1, 1),
        )
        path_bar.add_widget(self.path_box)

        # Choose folder button
        btn_browse = ColoredButton(
            text=button_text,
            size_hint_x=None,
            # width=self.FONT_SIZE * 9  ,
            width=width if width is not None else measure_text_size(button_text, self.FONT_SIZE)[0],
            bg_color=self.ACCENT_COLOR,
            rounded=self.ROUNDED,
            color=self.ACCENT_FONT_COLOR,
            font_size=self.FONT_SIZE,
        )
        btn_browse.bind(on_release=lambda x: self._show_folder_chooser())
        path_bar.add_widget(btn_browse)

        return path_bar

    def _show_folder_chooser_popup(self, start: str, title: str, on_select):
        """Shared FileChooserListView popup. Calls on_select(path_str) when confirmed"""
        from kivy.uix.filechooser import FileChooserListView

        content = BoxLayout(orientation='vertical', spacing=dp(4))

        path_label = Label(
            text=start,
            color=self.BG_FONT_COLOR,
            font_size=self.FONT_SIZE,
            size_hint_y=None,
            height=self.UI_BAR_HEIGHT,
            halign='left',
            valign='middle',
            shorten=True,
            shorten_from='left',
        )
        path_label.bind(size=lambda *x: setattr(path_label, 'text_size', path_label.size))
        content.add_widget(path_label)

        # Show all non-hidden folders (same folders as in grid)    
        fc = FileChooserListView(path=start, dirselect=True, filter_dirs=True, filters=[lambda folder, filename: (Path(folder) / filename).is_dir() and not is_os_hidden(Path(folder) / filename)], )       
        fc.bind(path=lambda inst, val: setattr(path_label, 'text', val))
        self._style_filechooser(fc)
        content.add_widget(fc)

        btn_layout = self._create_popup_button_row()
        btn_cancel = self._create_popup_button('Cancel')
        btn_select = self._create_popup_button('Select')
        btn_layout.add_widget(btn_cancel)
        btn_layout.add_widget(btn_select)
        content.add_widget(btn_layout)

        popup = self._create_popup(title, content, size_hint=(0.9, 0.9))

        def _confirm(inst):
            if fc.selection and Path(fc.selection[0]).is_dir():
                on_select(fc.selection[0])
            popup.dismiss()

        btn_cancel.bind(on_release=lambda x: popup.dismiss())
        btn_select.bind(on_release=_confirm)
        popup.open()

    def _show_folder_chooser(self):
        if self._current_folder:
            start = str(self._current_folder)
        else:
            loc = self.custom.get('location', '')
            start = loc if loc and Path(loc).is_dir() else str(Path.home())
        self._show_folder_chooser_popup(start, 'Select folder',
                                        lambda p: self.navigate_to(Path(p)))

    # === POPUP STYLING HELPERS ===
    # Modulair helpers for consistent popup styling
    # All popups use the same font size, button size and colors as the main app
 
    def _create_popup(self, title: str, content, size_hint: tuple = (0.8, 0.8)) -> Popup:
        """Makes a popup with consistent styling
        Title is bold, colors consistent, no grey Kivy border
        Args:
            title: Popup title (always bold)
            content: Popup content widget
            size_hint: Size relative to screen
        Returns Popup with consistent styling"""
        
        popup = Popup(
            title=title,
            title_size=self.FONT_SIZE,
            content=content,
            size_hint=size_hint,
            title_color=self.BG_FONT_COLOR,
            separator_height=0,
            background_color=self.BG_COLOR,
            background='',  # Remove default grey Kivy border
        )
        # Bold title: Kivy Popup has no markup parameter, so we put it on the internal title label after the popup has been created
        # The title label is accessible via popup.children[0].children[1] (or via _container)
        def enable_bold_title(*args):
            try:
                # Find the title label in the popup structure
                for child in popup.walk():
                    if hasattr(child, 'text') and child.text == title:
                        child.bold = True
                        child.font_size = self.FONT_SIZE
                        break
            except Exception:
                pass  # Silently fail if structure is different
        Clock.schedule_once(enable_bold_title, 0)
        return popup
 
    def _create_popup_row(self, height_multiplier: float = 1.0, spacing: int = 10) -> BoxLayout:
        """ Make a form row for settings/dialogs
        Height is based on ui_bar_height for consistency
        Args: height_multiplier: Multiply for height (f.e. 4.0 for textarea)
            spacing: Space between elements
        Returns: Box Layout with correct height"""
        return BoxLayout(
            size_hint_y=None,
            height=self.UI_BAR_HEIGHT * height_multiplier,
            spacing=dp(spacing),
        )

    def _create_popup_label(self, text: str, bold: bool = False, size_hint_x: float = None,
                            halign: str = 'left', valign: str = 'middle') -> Label:
        """Make a styled label for use in popups
        Uses font_size and background_font_color for consistency
        Args:
            text: Label text
            bold: True for bold text
            size_hint_x: Width hint (None = auto)
            halign: Horizontal aligment
            valign: Vertical alignment
        Returns Label with consistent styling"""
        display_text = f'[b]{text}[/b]' if bold else text
        label = Label(
            text=display_text,
            markup=bold,  # Only turn on markup if bold is needed
            font_size=self.FONT_SIZE,
            color=self.BG_FONT_COLOR,
            halign=halign,
            valign=valign,
        )
        if size_hint_x is not None:
            label.size_hint_x = size_hint_x
        # Bind text_size voor correcte uitlijning
        label.bind(size=lambda *x: setattr(label, 'text_size', label.size))
        return label

    def _create_popup_text_input(self, text: str = '', multiline: bool = False, readonly: bool = False, hint_text: str = '', white_background: bool = False, size_hint_x: float = None) -> 'Widget':
        """Makes a styled text input for use in popups
        Args:
            text: Initial text
            multiline: True for multiple lines
            readonly: True for read only
            hint_text: Placeholder text (grey, disappears when typing)
            white_background: True for white background with (optional) round corners
            size_hint_x: With as fraction (0.0-1.0), None = full width
        Returns Widget with text input. For white_background=True this is a RelativeLayout with a .text_input attribute for access to the TextInput"""
        
        h_pad = dp(10)
        # Calculate vertical padding to center the text
        v_pad = self.FONT_SIZE * 0.4
 
        if white_background:
            # Make a container with round background (like SearchBox)
            use_rounded = self.ROUNDED
            # For multiline: size_hint_y=1 so container grows with parent
            # For single line: set height with size_hint_y=None
            if multiline:
                container = RelativeLayout(
                    size_hint=(size_hint_x if size_hint_x else 1, 1)
                )
            else:
                container = RelativeLayout(
                    size_hint=(size_hint_x if size_hint_x else 1, None),
                    height=self.UI_BAR_HEIGHT
                )

            # Option for rounded corners
            bg_widget = RoundedBackground(
                bg_color=self.ACCENT_FONT_COLOR,
                rounded=use_rounded,
                size_hint=(1, 1),
                pos_hint={'x': 0, 'y': 0},
            )
            container.add_widget(bg_widget)

            # Transparent TextInput on top
            text_input = TextInput(
                text=str(text) if text else '',
                hint_text=hint_text,
                multiline=multiline,
                readonly=readonly,
                background_color=(0, 0, 0, 0),  # Transparent
                background_normal='',
                background_active='',
                foreground_color=self.ACCENT_COLOR,
                font_size=self.FONT_SIZE,
                padding=[h_pad, v_pad, h_pad, v_pad],
                size_hint=(1, 1),
                pos_hint={'x': 0, 'y': 0},
            )
            container.add_widget(text_input)
            # Save reference so we can get to .text
            container.text_input = text_input
            return container
        else:
            return TextInput(
                text=str(text) if text else '',
                hint_text=hint_text,
                multiline=multiline,
                readonly=readonly,
                background_color=(0, 0, 0, 0),  # Transparent
                background_normal='',
                background_active='',
                foreground_color=self.ACCENT_COLOR,
                font_size=self.FONT_SIZE,
                padding=[h_pad, v_pad, h_pad, v_pad],
                size_hint=(size_hint_x if size_hint_x else 1, 1),
                pos_hint={'x': 0, 'y': 0},
            )

    def _create_popup_button(self, text: str, danger: bool = False) -> 'ColoredButton':
        """Makes a styled button for use in popups
        Uses the same style as buttons in the main screen
        Args:
            text: Button text
            danger: True for danger buttons
        Returns ColoredButton with consistent styling"""
  
        accent_color = (1, 0.3, 0.3, 1) if danger else self.ACCENT_COLOR
        return ColoredButton(
            text=text,
            bg_color=accent_color,
            rounded=self.ROUNDED,
            color=self.ACCENT_FONT_COLOR,
            font_size=self.FONT_SIZE,
        )       

    def _create_popup_button_row(self, spacing: int = 10) -> BoxLayout:
        """Makes a button row to put at the bottom of
        Height is based on ui_bar_height for consistency
        Returns Box Layout with correct height for popup buttons"""
        return BoxLayout(
            size_hint_y=None,
            height=self.UI_BAR_HEIGHT,
            spacing=dp(spacing),
        )

    def _add_location_field(self, form, label_text, key, value):
        """Adds a location field with browse button, both in one rounded container"""
        row = self._create_popup_row()
        label = self._create_popup_label(label_text, size_hint_x=0.4)
        row.add_widget(label)

        # Outer container for text input + browse button
        outer_container = RelativeLayout(size_hint_x=0.6)
        
        # left courners round
        input_bg_radius = [dp(5), 0, 0, dp(5)] if self.ROUNDED else None
        bg_widget = RoundedBackground(
            bg_color=self.ACCENT_FONT_COLOR,
            rounded=False,
            radius=input_bg_radius,
            size_hint=(0.75, 1),
            pos_hint={'x': 0, 'y': 0},
        )
        outer_container.add_widget(bg_widget)

        # Inner BoxLayout for text input + button (no spacing in between)
        inner_container = BoxLayout(
            spacing=0,
            size_hint=(1, 1),
            pos_hint={'x': 0, 'y': 0},
        )

        # Transparent text input with consistent styling
        text_input = self._create_popup_text_input(value)
        text_input.size_hint_x = 0.75
        inner_container.add_widget(text_input)

        def on_browse(instance):
            start = text_input.text.strip() or str(Path.home())
            self._show_folder_chooser_popup(
            start,
            f"Choose {label_text.lower()}",
            lambda p: setattr(text_input, 'text', p),
        )

        # Browse button
        btn_radius = [0, dp(5), dp(5), 0] if self.ROUNDED else [0, 0, 0, 0]
        browse_btn = ColoredButton(
            text='...',
            size_hint_x=0.25,
            bg_color=self.ACCENT_COLOR,
            radius=btn_radius,
            color=self.ACCENT_FONT_COLOR,
            font_size=self.FONT_SIZE,
            halign='center',
            valign='middle',
            bold=True,
        )
        browse_btn.bind(size=lambda *x: setattr(browse_btn, 'text_size', browse_btn.size))
        browse_btn.bind(on_release=lambda x: on_browse(x))

        inner_container.add_widget(browse_btn)
        outer_container.add_widget(inner_container)
        row.add_widget(outer_container)
        form.add_widget(row)
        self._settings_inputs[key] = text_input

        # Align text boxt text to the right
        text_input.bind(text=_scroll_to_end, size=_scroll_to_end)

    def _add_yn_field(self, form, label_text, key, value):
        """Add a Y/N checkbox field with styled checkbox"""
        row = self._create_popup_row()
        label = self._create_popup_label(label_text, size_hint_x=0.4)
        row.add_widget(label)

        checkbox_container = BoxLayout(size_hint_x=0.6)
        checkbox = StyledCheckBox(active=value, rounded=self.ROUNDED)
        checkbox_container.add_widget(checkbox)
        checkbox_container.add_widget(BoxLayout())  # spacer
        row.add_widget(checkbox_container)
        form.add_widget(row)
        self._settings_inputs[key] = checkbox

    def _style_filechooser(self, filechooser):
        """Styles a FileChooserListView consistent with Libiry's style
        - All text in background_font_color
        - Header "Name" renamed to "Folder"
        - Header "Size" hidden

        IMPORTANT: Styles only FileChooser widgets, NOT ColoredButton or other popup elements that have their own styling
        The styling is applied multiple times because FileChooser widgets are created dynamically and are sometimes available only at a later stage. Bindings on path and files ensure that for navigation the styling is applied as well

        Args: filechooser: FileChooserListView instance
        
        The kv tree looks like:
           FileChooserListView
           └─ FileChooserListLayout
             └─ ScrollView  (id: scrollview)
                └─ Scatter
                     └─ TreeView  (id: treeview)
                        └─ FileListEntry  ← height: '48dp'  (one per file)"""

        text_color = self.BG_FONT_COLOR
        font_size = self.FONT_SIZE

        def _draw_bar(sv, *args):
            """Capsule scrollbar matching RoundedScrollView, painted on an existing ScrollView"""
            draw_capsule_bar(sv, self.ACCENT_COLOR, self.SCROLLBAR_WIDTH, '_fc_bar_inst')

        def apply_style(*args):
            # Walk through filechooser children and style all text widgets
            # EXCEPT ColoredButton (they have their own styling via _create_popup_button)
            for child in filechooser.walk():
                child_class_name = child.__class__.__name__
                # Skip our own ColoredButton class
                if child_class_name == 'ColoredButton':
                    continue
                # Style all widgets with color attribute (Labels, FileChooserListLayout entries, etc.)
                # This catches Label widgets as well as FileChooserListEntry items
                if hasattr(child, 'color') and hasattr(child, 'text'):
                    child.color = text_color
                if hasattr(child, 'font_size'):
                    child.font_size = font_size
                if hasattr(child, 'text'):
                    # Rename "Name" to "Folder" and hide "Size"
                    if child.text == 'Name':
                        child.text = 'Folder'
                    elif child.text == 'Size':
                        child.text = ''
                        if hasattr(child, 'width'):
                            child.width = 0
                            child.size_hint_x = 0
                    elif child.text.rstrip('/\\') == '..':
                        # Show "< C:\Books" when you're inside C:\Books\Fantasy     
                        child.text = f'Up to {Path(filechooser.path).parent}'

                if child_class_name == 'ScrollView':
                    child.bar_width = self.SCROLLBAR_WIDTH
                    child.scroll_type = ['bars', 'content']
                    if self.ROUNDED:
                        child.bar_color = (0, 0, 0, 0)
                        child.bar_inactive_color = (0, 0, 0, 0)
                        if not getattr(child, '_fc_bar_wired', False):
                            child._fc_bar_wired = True
                            child.bind(
                                scroll_y=lambda w, v: _draw_bar(w),
                                size=lambda w, v: _draw_bar(w),
                                viewport_size=lambda w, v: _draw_bar(w),
                            )  
                        _draw_bar(child)
                    else:
                        child.bar_color = list(self.ACCENT_COLOR)
                        child.bar_inactive_color = list(self.ACCENT_COLOR)

                # Row height — kv template sets 48dp. 28 dp gives roughly 40 % less height — still readable, far less scrolling
                elif child_class_name == 'FileListEntry':
                    child.height = dp(28)

        # Schedule styling multiple times to catch late-created widgets
        # FileChooser often creates list items a little later
        Clock.schedule_once(apply_style, 0.05)
        Clock.schedule_once(apply_style, 0.15)
        Clock.schedule_once(apply_style, 0.3)
        
        # Re-apply styling after path changes (navigation to different folder)
        filechooser.bind(path=lambda *x: Clock.schedule_once(apply_style, 0.1))
        # Re-apply styling when the files list changes (including after a refresh)
        filechooser.bind(files=lambda *x: Clock.schedule_once(apply_style, 0.1))

    def _setup_kivy_app(self, title: str, width: int = 550, height: int = 350):
        """Creates the internal Kivy App and configures window size and color
        To be called from the subclass __init__ after super().__init__()
        Window configuration must happen before run() starts the event loop, but after _load_style() has set self.BG_COLOR"""

        from kivy.core.window import Window
       
        self.title = title
        Window.size = (width, height)
        Window.clearcolor = self.BG_COLOR # background color via window
        icon_path = get_script_dir() / "resources" / "icons" / "Libiry.ico"
        if icon_path.exists():
            Window.set_icon(str(icon_path))
            if sys.platform == 'win32':
                self._icon_path = str(icon_path)
                self._icon_set_attempts = 0
                self._try_set_windows_icon()

    def build(self):
        """Called by Kivy's App.run() to construct the root widget
        Delegates to _build_ui() which calls the subclass _create_widgets() hook
        Kivy uses the returned widget as the window root"""
        return self._build_ui()

    def _build_ui(self):
        """Create root BoxLayout and populate it via _create_widgets(). Note the Title Bar is displayey higher in Windows then in Linux"""
        from kivy.uix.boxlayout import BoxLayout

        layout = BoxLayout(orientation='vertical', padding=[20, 36, 20, 20], spacing=10) #[left, top, right, bottom] — top goes from 20 to 36dp (one title line height). The extra 16dp shifts everything down just enough on Linux without being noticeable on Windows
        self._layout = layout
        self._create_widgets()
        return layout

    def _create_widgets(self):
        """Override in subclass to populate self._layout with UI widgets"""
        pass
        
    def _try_set_windows_icon(self, dt=None):
        """Try to set the Windows taskbar icon, retry until you succeed (max 20x)"""
        self._icon_set_attempts += 1
        if self._icon_set_attempts > 20:
            print("Failed to set Windows icon after 20 attempts")
            return

        success = self._set_windows_icon(self._icon_path)
        if not success:
            # Try again after 0.1 second
            Clock.schedule_once(self._try_set_windows_icon, 0.1)

    def _set_windows_icon(self, icon_path):
        """Set Windows taskbar icon using Windows API. Returns True on success. Tries multiple methods to retrieve the window handle:
        1. Via Kivy's SDL window info (most reliable)
        2. EnumWindows with process ID matching
        3. FindWindowW with various class names"""
        try:
            import ctypes
            from ctypes import wintypes

            # Normalize path and convert to absolute path
            icon_path = str(Path(icon_path).resolve())

            if not Path(icon_path).exists():
                print(f"Icon file not found: {icon_path}")
                return False

            # Load the icon using LoadImageW with proper wide string
            IMAGE_ICON = 1
            LR_LOADFROMFILE = 0x00000010
            LR_DEFAULTSIZE = 0x00000040
            LR_SHARED = 0x00008000

            # Use ctypes to properly define the function
            user32 = ctypes.windll.user32
            user32.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT,
                                          ctypes.c_int, ctypes.c_int, wintypes.UINT]
            user32.LoadImageW.restype = wintypes.HANDLE

            hicon = user32.LoadImageW(
                None, icon_path, IMAGE_ICON, 0, 0,
                LR_LOADFROMFILE | LR_DEFAULTSIZE | LR_SHARED
            )

            if not hicon:
                # Try loading as small and large icons separately
                hicon = user32.LoadImageW(
                    None, icon_path, IMAGE_ICON, 32, 32,
                    LR_LOADFROMFILE
                )

            if hicon:
                hwnd = None

                # Method 1: Try via Kivy SDL window info (most reliable)
                try:
                    from kivy.core.window import Window
                    if hasattr(Window, '_win') and Window._win:
                        sdl_win = Window._win
                        if hasattr(sdl_win, 'get_window_info'):
                            info = sdl_win.get_window_info()
                            if info and 'window' in info:
                                hwnd = info['window']
                except Exception:
                    pass

                # Method 2: EnumWindows with process ID matching
                if not hwnd:
                    try:
                        import os
                        current_pid = os.getpid()

                        # Callback type for EnumWindows
                        WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

                        found_hwnd = ctypes.c_void_p(0)

                        def enum_callback(test_hwnd, lparam):
                            # Get process ID for this window
                            pid = wintypes.DWORD()
                            user32.GetWindowThreadProcessId(test_hwnd, ctypes.byref(pid))
                            if pid.value == current_pid:
                                # Check if it's a visible top-level window
                                if user32.IsWindowVisible(test_hwnd):
                                    found_hwnd.value = test_hwnd
                                    return False  # Stop enumeration
                            return True  # Continue

                        user32.EnumWindows(WNDENUMPROC(enum_callback), 0)
                        if found_hwnd.value:
                            hwnd = found_hwnd.value
                    except Exception:
                        pass

                # Method 3: FindWindowW with various class names (fallback)
                if not hwnd:
                    hwnd = user32.GetActiveWindow()
                if not hwnd:
                    hwnd = user32.GetForegroundWindow()
                if not hwnd:
                    # SDL2 window class names (can vary per SDL version)
                    for class_name in ['SDL_app', 'SDL_Window', None]:
                        hwnd = user32.FindWindowW(class_name, 'Libiry')
                        if hwnd:
                            break

                if hwnd:
                    # Set icon for both small (title bar) and big (taskbar) icons
                    WM_SETICON = 0x0080
                    ICON_SMALL = 0
                    ICON_BIG = 1

                    user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT,
                                                    wintypes.WPARAM, wintypes.LPARAM]
                    user32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, hicon)
                    user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, hicon)
                    return True  # Success
                else:
                    return False  # Window not ready yet, retry later
            else:
                error_code = ctypes.get_last_error()
                print(f"Could not load icon from {icon_path}, error: {error_code}")
                return False
        except Exception as e:
            print(f"Could not set Windows taskbar icon: {e}")
            return False      

    # ------------------------------------------------------------------
    # Widget factories
    # ------------------------------------------------------------------

    def _create_label(self, parent_layout, text: str, style: str = 'normal') -> 'Label':
        """Creates a Label and adds it to parent_layout
        Style options:
          'title'    — large bold (FONT_SIZE + 6), height 36 dp
          'subtitle' — normal size, height 28 dp
          'warning'  — slightly smaller (FONT_SIZE - 1), height 22 dp
          'normal'   — normal size, height 24 dp
        Returns the Label so callers can store a ref and update .text later"""
        from kivy.uix.label import Label
        from kivy.metrics import dp

        font_sizes = {
            'title':    self.FONT_SIZE + 6,
            'subtitle': self.FONT_SIZE,
            'warning':  max(self.FONT_SIZE - 1, 8),
            'normal':   self.FONT_SIZE,
        }
        heights = {
            'title': dp(36), 'subtitle': dp(28),
            'warning': dp(22), 'normal': dp(24),
        }

        lbl = Label(
            text=text,
            color=self.BG_FONT_COLOR,
            font_size=font_sizes.get(style, self.FONT_SIZE),
            bold=(style == 'title'),
            size_hint_y=None,
            height=heights.get(style, dp(24)),
            halign='left',
            valign='middle',
        )
        lbl.bind(size=lambda w, s: setattr(w, 'text_size', s))
        parent_layout.add_widget(lbl)
        return lbl

    def _create_button(self, parent_layout, text: str, on_press) -> ColoredButton:
        """Creates a Button and adds it to parent_layout. Returns a ColoredButton so callers can set .disabled etc."""
        btn = ColoredButton(
            text=text,
            size_hint=(1, None),
            height=self.UI_BAR_HEIGHT,
            bg_color=self.ACCENT_COLOR,
            rounded=self.ROUNDED,
            color=self.ACCENT_FONT_COLOR,
            font_size=self.FONT_SIZE,
        )
        btn.bind(on_release=lambda inst: on_press())
        parent_layout.add_widget(btn)
        return btn
        
    # ------------------------------------------------------------------
    # Dialog helpers
    # ------------------------------------------------------------------

    def _show_popup(self, title: str, message: str):
        """Internal: open a simple text popup with a Close button"""
        content = BoxLayout(orientation='vertical', padding=dp(10), spacing=dp(10))
        msg_lbl = Label(text=message, color=self.BG_FONT_COLOR,
                        font_size=self.FONT_SIZE,
                        text_size=(dp(380), None),
                        size_hint_y=1, halign='left', valign='top')
        content.add_widget(msg_lbl)

        close_btn = ColoredButton(
            text='Close',
            size_hint_y=None,
            height=self.UI_BAR_HEIGHT,
            bg_color=self.ACCENT_COLOR,
            rounded=self.ROUNDED,
            color=self.ACCENT_FONT_COLOR,
            font_size=self.FONT_SIZE,
        )
        content.add_widget(close_btn)

        popup = self._create_popup(title, content, size_hint=(None, None))
        popup.size = (dp(440), dp(240))
        close_btn.bind(on_release=popup.dismiss)
        popup.open()

    def _show_error(self, message: str):
        """Shows an error popup (replaces messagebox.showerror)"""
        label = self._create_popup_label(message, halign='left', valign='middle')
        popup = self._create_popup('Error', label, size_hint=(0.6, 0.3))
        popup.open()

    def _show_info(self, title: str, message: str):
        """Shows an info popup (replaces messagebox.showinfo)"""
        self._show_popup(title, message)

    def _show_confirm(self, message: str, on_yes, on_no=None):
        """Shows a Yes/No confirmation popup
        on_yes is called with no arguments when the user clicks Yes
        on_no  is called with no arguments when the user clicks No (optional)
        Unlike messagebox.askyesno(), this is non-blocking: execution continues immediately; the callbacks are invoked when the user responds"""
        content = BoxLayout(orientation='vertical', padding=dp(10), spacing=dp(10))
        content.add_widget(Label(
            text=message,
            color=self.BG_FONT_COLOR,
            font_size=self.FONT_SIZE,
            text_size=(dp(380), None),
            size_hint_y=1,
            halign='left',
            valign='top',
        ))

        btn_row = self._create_popup_button_row()
        yes_btn = self._create_popup_button('Yes')
        no_btn  = self._create_popup_button('No')
        btn_row.add_widget(yes_btn)
        btn_row.add_widget(no_btn)
        content.add_widget(btn_row)

        popup = self._create_popup('Confirm', content, size_hint=(None, None))
        popup.size = (dp(440), dp(280))

        def _on_yes(inst):
            popup.dismiss()
            on_yes()

        def _on_no(inst):
            popup.dismiss()
            if on_no:
                on_no()

        yes_btn.bind(on_release=_on_yes)
        no_btn.bind(on_release=_on_no)
        popup.open()

    # ------------------------------------------------------------------
    # Threading helper
    # ------------------------------------------------------------------

    def _update_progress(self, pct: float, text: str):
        """Updates self.progress_label from any thread (thread-safe via Clock)
        Subclasses that are certain to call this only from Clock callbacks can override with a simpler direct assignment"""
          
        from kivy.clock import Clock
        if hasattr(self, 'progress_label'):
            Clock.schedule_once(
                lambda dt: setattr(self.progress_label, 'text', f'[{pct:.0f}%] {text}'), 0)