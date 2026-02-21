"""
Libiry - A cross-platform ebook library viewer.

Supports Windows, Linux, macOS, Android, and iOS.
"""

import sys
import re
import shutil
from pathlib import Path
from functools import partial

# Probeer send2trash te importeren voor prullenbak support
# Als niet beschikbaar, gebruik dan permanente verwijdering als fallback
try:
    from send2trash import send2trash
    HAS_SEND2TRASH = True
except ImportError:
    HAS_SEND2TRASH = False

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

# Windows taskbar icon fix - must be before kivy imports
if sys.platform == 'win32':
    import ctypes
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('libiry.app.1.0')


def is_hidden(filepath: Path) -> bool:
    """
    Check of een bestand of folder hidden is.

    Werkt cross-platform:
    - Unix/Mac: checkt of naam begint met '.'
    - Windows: checkt ook het hidden attribuut (voor $Recycle.Bin etc.)
    """
    # Unix-style: begint met punt
    if filepath.name.startswith('.'):
        return True

    # Windows: check hidden attribuut
    if sys.platform == 'win32':
        try:
            # FILE_ATTRIBUTE_HIDDEN = 0x2
            attrs = ctypes.windll.kernel32.GetFileAttributesW(str(filepath))
            if attrs != -1:  # -1 = INVALID_FILE_ATTRIBUTES
                return bool(attrs & 0x2)
        except Exception:
            pass

    return False

from kivy.config import Config

# Set window icon before importing other kivy modules
app_path = Path(__file__).parent
icon_path = app_path / "resources" / "icons" / "Libiry.ico"
if icon_path.exists():
    # Use forward slashes for Kivy config
    Config.set('kivy', 'window_icon', str(icon_path).replace('\\', '/'))

# Disable multitouch emulation (voorkomt rode stippen bij muis-interactie)
Config.set('input', 'mouse', 'mouse,multitouch_on_demand')

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.relativelayout import RelativeLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.image import Image, AsyncImage
from kivy.uix.popup import Popup
from kivy.uix.filechooser import FileChooserListView
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.widget import Widget
from kivy.core.window import Window
from kivy.clock import Clock
from kivy.properties import StringProperty, ObjectProperty, ListProperty, NumericProperty
from kivy.graphics import Color, Rectangle, RoundedRectangle, Triangle
from kivy.metrics import dp
from kivy.storage.jsonstore import JsonStore
from threading import Thread
from PIL import Image as PILImage

from core.cover_cache import CoverCache
from core.cover_extractor import CoverExtractor
from core.file_opener import open_in_default_app
from core.metadata_extractor import MetadataExtractor, BookMetadata


# Default supported formats
DEFAULT_FORMATS = {'.epub', '.mobi', '.azw', '.azw3', '.pdf', '.cbz', '.cbr', '.md'}


def parse_color(color_str: str) -> tuple:
    """Parse color string to RGBA tuple (0-1 range)."""
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


def load_selected_types(app_path: Path) -> set:
    """Load selected file types from selected types.txt."""
    types = set()

    for folder in ['customize', 'resources']:
        types_path = app_path / folder / 'selected types.txt'
        if types_path.exists():
            try:
                content = types_path.read_text(encoding='utf-8')
                for line in content.split('\n'):
                    line = line.strip().lower()
                    if line and line.startswith('.'):
                        types.add(line)
                if types:
                    return types
            except Exception as e:
                print(f"Error loading selected types: {e}")

    return DEFAULT_FORMATS


def load_customization(app_path: Path) -> dict:
    """Load customization settings from customize.txt."""
    settings = {
        'location': '',
        'background_color': (0.44, 0.62, 0.62, 1),
        'button_color': (0.47, 0.25, 0.31, 1),
        'button_font_color': (1, 1, 1, 1),
        'search_box_color': (1, 1, 1, 1),
        'tile_font_color': (0, 0, 0, 1),
        'background_font_color': (1, 1, 1, 1),
        'search_box_font_color': (0, 0, 0, 1),
        'rounded_corners': True,
        'only_selected_types': True,
        'fuzzy_search': False,  # Standaard uit - exacte substring match
        'scrollbar_width': 10,  # Scrollbar dikte in dp
        'scrollbar_always_visible': True,  # Scrollbar altijd zichtbaar
        'show_book_title': False,  # Toon titel/auteur op covers met afbeelding
        'ui_font_size': 12,  # Font size voor UI-elementen (knoppen, labels, etc.)
        # Configurable field names for markdown parsing
        'field_names': {},
    }

    for folder in ['customize', 'resources']:
        config_path = app_path / folder / 'customize.txt'
        if config_path.exists():
            try:
                content = config_path.read_text(encoding='utf-8')
                for line in content.split('\n'):
                    if ':' in line:
                        key, value = line.split(':', 1)
                        key = key.strip().lower()
                        value = value.strip()

                        # Location: customize heeft voorrang boven resources
                        # Alleen overschrijven als nog niet ingevuld
                        if key == 'location' and value and not settings['location']:
                            settings['location'] = value
                        elif key == 'background color' and value:
                            settings['background_color'] = parse_color(value)
                        elif key == 'button color' and value:
                            settings['button_color'] = parse_color(value)
                        elif key == 'button font color' and value:
                            settings['button_font_color'] = parse_color(value)
                        elif key == 'search box color' and value:
                            settings['search_box_color'] = parse_color(value)
                        elif key == 'tile font color' and value:
                            settings['tile_font_color'] = parse_color(value)
                        elif key == 'background font color' and value:
                            settings['background_font_color'] = parse_color(value)
                        elif key == 'search box font color' and value:
                            settings['search_box_font_color'] = parse_color(value)
                        elif key == 'rounded corners y/n' and value:
                            settings['rounded_corners'] = value.lower() != 'n'
                        elif key == 'only selected file types y/n' and value:
                            settings['only_selected_types'] = value.lower() != 'n'
                        elif key == 'fuzzy search y/n' and value:
                            settings['fuzzy_search'] = value.lower() == 'y'
                        elif key == 'scrollbar width' and value:
                            try:
                                settings['scrollbar_width'] = int(value)
                            except ValueError:
                                pass
                        elif key == 'scrollbar always visible y/n' and value:
                            settings['scrollbar_always_visible'] = value.lower() != 'n'
                        elif key == 'show book title y/n' and value:
                            settings['show_book_title'] = value.lower() == 'y'
                        elif key in ('font size', 'ui font size') and value:  # ui font size voor backwards compatibility
                            try:
                                settings['ui_font_size'] = int(value)
                            except ValueError:
                                pass
                        # Configurable field names
                        elif key == 'field name cover' and value:
                            settings['field_names']['cover'] = value
                        elif key == 'field name booktitle' and value:
                            settings['field_names']['booktitle'] = value
                        elif key == 'field name author' and value:
                            settings['field_names']['author'] = value
                        elif key == 'field name isbn' and value:
                            settings['field_names']['isbn'] = value
                        elif key == 'field name publisher' and value:
                            settings['field_names']['publisher'] = value
                        elif key == 'field name year' and value:
                            settings['field_names']['year'] = value
                        elif key == 'field name language' and value:
                            settings['field_names']['language'] = value
                        elif key == 'field name description' and value:
                            settings['field_names']['description'] = value
                        elif key == 'field name tags' and value:
                            settings['field_names']['tags'] = value
                        elif key == 'field name series' and value:
                            settings['field_names']['series'] = value
                        elif key == 'field name series_index' and value:
                            settings['field_names']['series_index'] = value
                        elif key == 'field name rating' and value:
                            settings['field_names']['rating'] = value
                        elif key == 'field name notes' and value:
                            settings['field_names']['notes'] = value
                break
            except Exception as e:
                print(f"Error loading customization: {e}")

    return settings


def get_icon_path(app_path: Path, icon_name: str) -> str:
    """Get icon path, preferring customize folder over resources."""
    customize_path = app_path / 'customize' / icon_name
    if customize_path.exists():
        return str(customize_path)

    resources_path = app_path / 'resources' / 'icons' / icon_name
    if resources_path.exists():
        return str(resources_path)

    return ''


def get_file_type(filepath: Path) -> str:
    """Get the file type (extension) for a file."""
    return filepath.suffix.lower()


def get_document_type(filepath: Path) -> str:
    """
    Get the document type from markdown files.

    For files WITH YAML frontmatter: search only in frontmatter for type:
    For files WITHOUT YAML frontmatter: search entire file for first type:

    Returns empty string for non-markdown files or if no type: is found.
    """
    suffix = filepath.suffix.lower()

    if suffix in ('.md', '.markdown'):
        try:
            content = filepath.read_text(encoding='utf-8')
            content = content.replace('\r\n', '\n').replace('\r', '\n')

            # Check for YAML frontmatter
            yaml_match = re.match(r'^---[ \t]*\n(.*?)\n---', content, re.DOTALL)

            if yaml_match:
                # YAML frontmatter exists - ONLY search in frontmatter
                yaml_content = yaml_match.group(1)
                type_match = re.search(r'^type:\s*(.+?)$', yaml_content, re.MULTILINE)
                if type_match:
                    return type_match.group(1).strip().strip('"\'')
            else:
                # No frontmatter - search entire file for first occurrence of type:
                type_match = re.search(r'^type:\s*(.+?)$', content, re.MULTILINE)
                if type_match:
                    return type_match.group(1).strip().strip('"\'')
        except Exception:
            pass

    return ''


class RoundedBackground(Widget):
    """
    Reusable background widget with optional rounded corners.

    Used for SearchBox, Settings input fields, and other UI elements
    that need a colored background with consistent styling.

    Args:
        bg_color: Background color tuple (r, g, b, a)
        rounded: If True, all corners rounded. If False, no rounding.
        radius: Custom radius list [top-left, top-right, bottom-right, bottom-left].
                Overrides 'rounded' parameter if provided.
    """

    def __init__(self, bg_color, rounded, radius=None, **kwargs):
        super().__init__(**kwargs)
        self._bg_color = bg_color
        self._rounded = rounded
        self._radius = radius
        self.bg_rect = None
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


# Alias for backward compatibility
SearchBoxBackground = RoundedBackground


class SearchBox(RelativeLayout):
    """Search box with magnifying glass icon overlay."""

    def __init__(self, app_path, custom, on_text_change, font_size=None, **kwargs):
        super().__init__(**kwargs)
        self.app_path = app_path
        self.custom = custom
        self._font_size = font_size if font_size else dp(14)

        # Get colors
        bg_color = custom['search_box_color']
        fg_color = custom['search_box_font_color']
        rounded = custom['rounded_corners']

        # Background widget
        self.bg_widget = SearchBoxBackground(
            bg_color=bg_color,
            rounded=rounded,
            size_hint=(1, 1),
            pos_hint={'x': 0, 'y': 0},
        )
        self.add_widget(self.bg_widget)

        # Text input (transparent)
        # Padding schaalt mee met font size: verticaal minimaal zodat tekst niet
        # wordt afgesneden bij kleinere bar heights
        h_pad = dp(10)  # Horizontale padding links
        v_pad = self._font_size * 0.3  # Verticale padding proportioneel aan font size
        r_pad = dp(40)  # Rechts extra ruimte voor zoek-icoon
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

        # Search icon (magnifying glass) - bottom right with gray overlay
        icon_size = self._font_size * 1.7
        search_icon = get_icon_path(app_path, 'search.png')
        if search_icon:
            self.search_img = Image(
                source=search_icon,
                size_hint=(None, None),
                size=(icon_size, icon_size),
                pos_hint={'right': 0.95, 'center_y': 0.5},
                color=(1, 1, 1, 1),  # No overlay
            )
            self.add_widget(self.search_img)

    @property
    def text(self):
        return self.text_input.text

    @text.setter
    def text(self, value):
        self.text_input.text = value


class LocationBox(RelativeLayout):
    """Location/path box (transparent)."""

    def __init__(self, custom, font_size=None, **kwargs):
        super().__init__(**kwargs)
        self.custom = custom
        self._font_size = font_size if font_size else dp(14)

        fg_color = custom['background_font_color']

        # Text input (transparent background, no border, readonly)
        # Padding schaalt mee met font size: horizontaal ruimer, verticaal minimaal
        # zodat tekst niet wordt afgesneden bij kleinere bar heights
        h_pad = dp(10)  # Horizontale padding vast
        v_pad = self._font_size * 0.3  # Verticale padding proportioneel aan font size
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

    @property
    def text(self):
        return self.text_input.text

    @text.setter
    def text(self, value):
        self.text_input.text = value


class CoverImage(ButtonBehavior, BoxLayout):
    """A clickable book cover or folder icon."""

    source = StringProperty('')
    item_name = StringProperty('')
    item_type = StringProperty('file')
    item_path = StringProperty('')
    file_type = StringProperty('')
    document_type = StringProperty('')
    is_selected = ObjectProperty(False)

    # Metadata properties
    booktitle = StringProperty('')
    isbn = StringProperty('')
    authors = ListProperty([])
    tags = ListProperty([])
    rating = NumericProperty(0)
    series = StringProperty('')
    series_index = NumericProperty(0)
    cover_url = StringProperty('')

    def __init__(self, **kwargs):
        self.item_path = kwargs.pop('item_path', '')
        self.item_type = kwargs.pop('item_type', 'file')
        self.item_name = kwargs.pop('item_name', '')
        self.file_type = kwargs.pop('file_type', '')
        self.document_type = kwargs.pop('document_type', '')
        self.source = kwargs.pop('source', '')
        self.on_double_tap_callback = kwargs.pop('on_double_tap', None)
        self.on_tap_callback = kwargs.pop('on_tap', None)
        self.tile_font_color = kwargs.pop('tile_font_color', (0, 0, 0, 1))
        self.rounded_corners = kwargs.pop('rounded_corners', True)
        self.background_color = kwargs.pop('background_color', (0.44, 0.62, 0.62, 1))

        # Metadata fields
        self.booktitle = kwargs.pop('booktitle', '')
        self.isbn = kwargs.pop('isbn', '')
        self.authors = kwargs.pop('authors', [])
        self.tags = kwargs.pop('tags', [])
        self.rating = kwargs.pop('rating', 0)
        self.series = kwargs.pop('series', '')
        self.series_index = kwargs.pop('series_index', 0)
        self.cover_url = kwargs.pop('cover_url', '')

        super().__init__(**kwargs)
        self.orientation = 'vertical'
        self.size_hint = (None, None)
        self.padding = 0
        self.spacing = 0

        self._last_touch_time = 0
        self._build_ui()

    def _build_ui(self):
        """Build the cover UI - image fills tile completely, no bezel/margin."""
        # Use RelativeLayout to allow text overlay on image
        self.img_container = RelativeLayout(size_hint=(1, 1))

        self._has_real_cover = False
        if self.source and Path(self.source).exists():
            self.img = Image(source=self.source, size_hint=(1, 1), allow_stretch=True, keep_ratio=False)
            self._has_real_cover = True
        else:
            # Use fallback image based on type
            if self.item_type == 'folder':
                fallback = self._get_fallback_image('folder.png')
            else:
                fallback = self._get_fallback_image('book.png')

            if fallback:
                self.img = Image(source=fallback, size_hint=(1, 1), allow_stretch=True, keep_ratio=False)
            else:
                self.img = Image(size_hint=(1, 1))

        self.img_container.add_widget(self.img)

        # Add text overlay for folders and books without covers
        if self.item_type == 'folder' or not self._has_real_cover:
            # For files: show "[author] - [booktitle]", for folders: show folder name
            if self.item_type != 'folder' and self.authors:
                author_str = ', '.join(self.authors[:2])
                title = self.booktitle if self.booktitle else self.item_name
                display_name = f"{author_str} - {title}"
            else:
                title = self.booktitle if self.booktitle else self.item_name
                display_name = title
            self.text_overlay = Label(
                text=display_name,
                halign='center',
                valign='middle',
                size_hint=(1, 1),
                pos_hint={'center_x': 0.5, 'center_y': 0.5},
                font_size=dp(11),
                color=self.tile_font_color,
                bold=False,
            )
            self.text_overlay.bind(size=lambda *x: setattr(self.text_overlay, 'text_size', (self.text_overlay.width - dp(10), None)))
            self.img_container.add_widget(self.text_overlay)

        self.add_widget(self.img_container)

        # Title overlay voor tiles met covers (standaard verborgen)
        # Kan getoond worden via "Show Title" knop
        self._title_overlay = None
        self._title_overlay_bg = None
        if self._has_real_cover and self.item_type != 'folder':
            self._create_title_overlay()

        # Selection indicator (shown when selected)
        self.bg_rect = None
        self.bg_color_inst = None
        self.bind(pos=self._update_rect, size=self._update_rect)
        Clock.schedule_once(self._initial_draw, 0.1)

    def _get_fallback_image(self, filename):
        """Get fallback image from customize or resources folder."""
        app_path = Path(__file__).parent
        # Check customize folder first
        customize_path = app_path / 'customize' / filename
        if customize_path.exists():
            return str(customize_path)
        # Then check resources/icons
        resources_path = app_path / 'resources' / 'icons' / filename
        if resources_path.exists():
            return str(resources_path)
        # Finally check resources root
        resources_path = app_path / 'resources' / filename
        if resources_path.exists():
            return str(resources_path)
        return None

    def _create_title_overlay(self):
        """Create the title overlay label (hidden by default).

        Toont [author] - [booktitle] in wit op zwart wanneer
        de "Show Title" knop actief is.
        """
        # Bouw de display tekst: "[author] - [booktitle]"
        if self.authors:
            author_str = ', '.join(self.authors[:2])
            title = self.booktitle if self.booktitle else self.item_name
            display_text = f"{author_str} - {title}"
        else:
            display_text = self.booktitle if self.booktitle else self.item_name

        # Maak een label met zwarte achtergrond en witte tekst
        self._title_overlay = Label(
            text=display_text,
            halign='center',
            valign='middle',
            size_hint=(1, None),
            height=dp(40),
            pos_hint={'center_x': 0.5, 'y': 0},  # Onderaan de tile
            font_size=dp(10),
            color=(1, 1, 1, 1),  # Wit
            bold=False,
            opacity=0,  # Standaard verborgen
        )
        self._title_overlay.bind(
            size=lambda *x: setattr(self._title_overlay, 'text_size', (self._title_overlay.width - dp(6), None))
        )

        # Voeg een zwarte achtergrond toe aan de label
        with self._title_overlay.canvas.before:
            self._title_overlay_color = Color(0, 0, 0, 0.8)  # Zwart met transparantie
            self._title_overlay_bg = Rectangle(pos=self._title_overlay.pos, size=self._title_overlay.size)

        # Bind om achtergrond mee te laten bewegen
        self._title_overlay.bind(pos=self._update_title_overlay_bg, size=self._update_title_overlay_bg)

        self.img_container.add_widget(self._title_overlay)

    def _update_title_overlay_bg(self, *args):
        """Update de achtergrond positie/grootte van de title overlay."""
        if self._title_overlay_bg and self._title_overlay:
            self._title_overlay_bg.pos = self._title_overlay.pos
            self._title_overlay_bg.size = self._title_overlay.size

    def set_title_overlay_visible(self, visible: bool):
        """Toon of verberg de title overlay.

        Alleen voor tiles met echte covers - tiles zonder cover tonen
        al standaard de titel.
        """
        if not self._title_overlay:
            return

        if visible:
            self._title_overlay.opacity = 1
            if hasattr(self, '_title_overlay_color'):
                self._title_overlay_color.a = 0.8
        else:
            self._title_overlay.opacity = 0
            if hasattr(self, '_title_overlay_color'):
                self._title_overlay_color.a = 0

    def _draw_document_type_triangle(self):
        """Draw a colored triangle in bottom-right corner based on tags.

        Kijkt naar de tags van het boek:
        - Rood driehoekje als 'summary' in tags zit
        - Grijs driehoekje als 'analog' in tags zit
        - Summary heeft voorrang boven analog
        """
        if not self.tags:
            return

        # Normalize tags to lowercase for case-insensitive matching
        tags_lower = [tag.lower().strip() for tag in self.tags]

        # Determine triangle color based on tags (summary prevails over analog)
        if 'summary' in tags_lower:
            triangle_color = (1, 0, 0, 1)  # Red for summary
        elif 'analog' in tags_lower:
            triangle_color = (0.5, 0.5, 0.5, 1)  # Gray for analog
        else:
            return  # No triangle for other tags

        # Store triangle info for later updates
        self._triangle_color = triangle_color
        self._has_triangle = True

        # Draw triangle on canvas.after so it's on top
        self._update_triangle()

    def _update_triangle(self):
        """Update the triangle position at the very bottom-right corner."""
        if not hasattr(self, '_has_triangle') or not self._has_triangle:
            return

        # Remove old triangle if exists
        if hasattr(self, '_triangle_instr') and self._triangle_instr:
            self.canvas.after.remove(self._triangle_color_instr)
            self.canvas.after.remove(self._triangle_instr)

        # Triangle at the very bottom-right corner of the tile
        triangle_size = dp(20)

        # Triangle points: bottom-right corner (uiterst rechts helemaal onderin)
        x = self.x + self.width
        y = self.y

        # Three points of triangle (bottom-right corner)
        points = [
            x, y,  # bottom-right corner
            x - triangle_size, y,  # left along bottom
            x, y + triangle_size,  # up along right side
        ]

        with self.canvas.after:
            self._triangle_color_instr = Color(*self._triangle_color)
            self._triangle_instr = Triangle(points=points)

    def _redraw_triangle(self):
        """Redraw triangle at updated position (bottom-right corner)."""
        if not hasattr(self, '_triangle_instr') or not self._triangle_instr:
            return

        triangle_size = dp(20)

        # Bottom-right corner
        x = self.x + self.width
        y = self.y

        points = [
            x, y,
            x - triangle_size, y,
            x, y + triangle_size,
        ]

        self._triangle_instr.points = points

    def _initial_draw(self, dt):
        """Draw document type triangle."""
        self._draw_document_type_triangle()

    def _update_rect(self, *args):
        """Update selection indicator and triangle."""
        # Handle selection indicator - uitgrijzen van hele tile bij selectie
        if self.is_selected:
            if self.bg_rect is None:
                with self.canvas.after:
                    # Grijs overlay over hele tile (zoals in ebookgrid)
                    self.bg_color_inst = Color(0.3, 0.3, 0.3, 0.5)
                    self.bg_rect = Rectangle(pos=self.pos, size=self.size)
            else:
                self.bg_rect.pos = self.pos
                self.bg_rect.size = self.size
        else:
            if self.bg_rect is not None:
                if self.bg_color_inst:
                    self.canvas.after.remove(self.bg_color_inst)
                    self.bg_color_inst = None
                if self.bg_rect:
                    self.canvas.after.remove(self.bg_rect)
                    self.bg_rect = None

        # Update triangle position if it exists
        if hasattr(self, '_has_triangle') and self._has_triangle:
            self._redraw_triangle()

    def on_touch_down(self, touch):
        """Handle touch events."""
        if self.collide_point(*touch.pos):
            import time
            current_time = time.time()
            if current_time - self._last_touch_time < 0.3:
                if self.on_double_tap_callback:
                    self.on_double_tap_callback(self.item_path, self.item_type)
                self._last_touch_time = 0
                return True
            else:
                self._last_touch_time = current_time
                if self.on_tap_callback:
                    self.on_tap_callback(self)
                return True
        return super().on_touch_down(touch)


class HoverBehavior:
    """Mixin voor hover detectie op widgets.

    Voegt on_enter en on_leave events toe die worden getriggerd wanneer
    de muis over de widget beweegt. Ondersteunt ook een tooltip_text
    property die automatisch een tooltip toont bij hover.

    Gebruik: Combineer met andere widget classes, bijv:
        class MyButton(HoverBehavior, ButtonBehavior, Label):
            pass
    """

    # Property voor tooltip tekst - None betekent geen tooltip
    tooltip_text = None
    _hover_tooltip_widget = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Registreer voor mouse motion events
        Window.bind(mouse_pos=self._on_mouse_pos)
        self._is_hovering = False

    def _on_mouse_pos(self, window, pos):
        """Track mouse position en trigger enter/leave events."""
        # Check of muis binnen widget bounds is
        if not self.get_root_window():
            return

        inside = self.collide_point(*pos)

        if inside and not self._is_hovering:
            self._is_hovering = True
            self.on_enter()
        elif not inside and self._is_hovering:
            self._is_hovering = False
            self.on_leave()

    def on_enter(self):
        """Called when mouse enters widget. Override for custom behavior."""
        if self.tooltip_text:
            self._show_tooltip()

    def on_leave(self):
        """Called when mouse leaves widget. Override for custom behavior."""
        self._hide_tooltip()

    def _show_tooltip(self):
        """Toon tooltip label bij de widget.

        Positioneert tooltip onder de button, maar past positie aan als
        de tooltip anders van het scherm zou vallen (links of rechts).
        """
        if self._hover_tooltip_widget:
            return

        # Maak tooltip label
        tooltip = Label(
            text=self.tooltip_text,
            size_hint=(None, None),
            font_size=dp(12),
            color=(1, 1, 1, 1),
            padding=(dp(8), dp(4)),
        )
        # Bereken grootte op basis van tekst
        tooltip.texture_update()
        tooltip.size = (tooltip.texture_size[0] + dp(16), tooltip.texture_size[1] + dp(8))

        # Bereken x positie, gecentreerd onder button
        x_pos = self.center_x - tooltip.width / 2

        # Voorkom dat tooltip van scherm valt
        # Links: minimaal 5dp margin
        if x_pos < dp(5):
            x_pos = dp(5)
        # Rechts: maximaal window width - tooltip width - 5dp margin
        max_x = Window.width - tooltip.width - dp(5)
        if x_pos > max_x:
            x_pos = max_x

        # Positioneer onder de button
        tooltip.pos = (x_pos, self.y - tooltip.height - dp(5))

        # Voeg achtergrond toe
        with tooltip.canvas.before:
            Color(0.2, 0.2, 0.2, 0.9)
            RoundedRectangle(pos=tooltip.pos, size=tooltip.size, radius=[dp(4)])

        # Voeg toe aan root window
        root = self.get_root_window()
        if root:
            root.add_widget(tooltip)
            self._hover_tooltip_widget = tooltip

    def _hide_tooltip(self):
        """Verberg en verwijder tooltip."""
        if self._hover_tooltip_widget:
            root = self.get_root_window()
            if root:
                root.remove_widget(self._hover_tooltip_widget)
            self._hover_tooltip_widget = None


class ImageButton(HoverBehavior, ButtonBehavior, Image):
    """A button with an image. Supports hover tooltips via tooltip_text property."""
    pass


class ColoredButton(ButtonBehavior, Label):
    """A button with background color and optional rounded corners.

    Args:
        bg_color: Background color tuple (r, g, b, a)
        rounded: If True, all corners rounded. If False, no rounding.
        radius: Custom radius list [top-left, top-right, bottom-right, bottom-left].
                Overrides 'rounded' parameter if provided.
    """

    def __init__(self, bg_color=(0.5, 0.5, 0.5, 1), rounded=True, radius=None, **kwargs):
        super().__init__(**kwargs)
        self._bg_color = bg_color
        self._rounded = rounded
        self._radius = radius  # Custom radius per hoek
        self.bg_rect = None
        Clock.schedule_once(self._draw_bg, 0.1)
        self.bind(pos=self._update_rect, size=self._update_rect)

    def _draw_bg(self, dt):
        """Draw background after widget has size."""
        with self.canvas.before:
            Color(*self._bg_color)
            if self._radius is not None:
                # Custom radius per hoek
                self.bg_rect = RoundedRectangle(pos=self.pos, size=self.size, radius=self._radius)
            elif self._rounded:
                self.bg_rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(5)])
            else:
                self.bg_rect = Rectangle(pos=self.pos, size=self.size)

    def _update_rect(self, *args):
        if self.bg_rect:
            self.bg_rect.pos = self.pos
            self.bg_rect.size = self.size


class StyledCheckBox(ButtonBehavior, Widget):
    """
    Custom checkbox met witte achtergrond en zwarte checkmark.

    Vervangt de standaard Kivy CheckBox die moeilijk te stylen is.
    Tekent een witte box met optionele rounded corners en een zwarte
    checkmark als active=True.
    """

    active = ObjectProperty(False)

    def __init__(self, rounded=True, **kwargs):
        self.active = kwargs.pop('active', False)
        super().__init__(**kwargs)
        self._rounded = rounded
        self.size_hint = (None, None)
        self.size = (dp(24), dp(24))
        self.bind(pos=self._update, size=self._update, active=self._update)
        Clock.schedule_once(lambda dt: self._update(), 0.1)

    def _update(self, *args):
        """Teken checkbox: witte box met optionele checkmark."""
        self.canvas.clear()
        with self.canvas:
            # Witte achtergrond
            Color(1, 1, 1, 1)
            if self._rounded:
                RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(3)])
            else:
                Rectangle(pos=self.pos, size=self.size)

            # Zwarte checkmark als active
            if self.active:
                Color(0, 0, 0, 1)
                # Teken checkmark met twee lijnen (als driehoeken voor dikte)
                cx, cy = self.pos[0] + self.size[0] / 2, self.pos[1] + self.size[1] / 2
                # Checkmark punten (relatief aan center)
                # Start links-midden, naar beneden-midden, naar rechts-boven
                from kivy.graphics import Line
                Line(
                    points=[
                        cx - dp(6), cy,           # links
                        cx - dp(2), cy - dp(5),   # onder-midden
                        cx + dp(6), cy + dp(5),   # rechts-boven
                    ],
                    width=dp(2),
                )

    def on_release(self):
        """Toggle active state bij klik."""
        self.active = not self.active


class RoundedScrollView(ScrollView):
    """
    ScrollView met rounded scrollbar (capsule-vorm) of standaard rechthoekige scrollbar.

    Bij rounded=True: tekent eigen capsule-vormige scrollbar met RoundedRectangle.
    Bij rounded=False: gebruikt Kivy's standaard scrollbar maar met de huisstijl kleur.

    Scrollbar is ALTIJD klikbaar/sleepbaar (scroll_type moet 'bars' bevatten).
    De always_visible parameter bepaalt alleen of de bar altijd zichtbaar is of
    alleen wanneer er iets te scrollen is.

    Args:
        rounded: bool - True voor capsule scrollbar, False voor rechthoekige
        bar_color_override: tuple - kleur voor de scrollbar (beide modes)
        always_visible: bool - True = altijd zichtbaar, False = alleen bij scroll content
    """

    def __init__(self, rounded=True, bar_color_override=None, always_visible=True, **kwargs):
        # Sla bar kleur op - wordt gebruikt voor beide modes
        self._bar_color_override = bar_color_override or kwargs.get('bar_color', (0.5, 0.5, 0.5, 1))
        self._rounded_bar = rounded
        self._always_visible = always_visible

        if rounded:
            # Verberg standaard scrollbar door transparant te maken
            # (we tekenen onze eigen rounded scrollbar)
            kwargs['bar_color'] = (0, 0, 0, 0)
            kwargs['bar_inactive_color'] = (0, 0, 0, 0)
        else:
            # Gebruik standaard rechthoekige scrollbar maar met huisstijl kleur
            kwargs['bar_color'] = self._bar_color_override
            # Bij not always_visible: bar_inactive_color transparant zodat bar
            # alleen zichtbaar is wanneer er iets te scrollen is
            if always_visible:
                kwargs['bar_inactive_color'] = self._bar_color_override
            else:
                kwargs['bar_inactive_color'] = (0, 0, 0, 0)

        super().__init__(**kwargs)

        if rounded:
            # Bindingen voor scrollbar redraw
            self.bind(scroll_y=self._draw_rounded_bar)
            self.bind(size=self._draw_rounded_bar)
            self.bind(viewport_size=self._draw_rounded_bar)
            Clock.schedule_once(lambda dt: self._draw_rounded_bar(), 0.2)

    def _draw_rounded_bar(self, *args):
        """Teken rounded scrollbar."""
        # Verwijder oude rounded bar graphics
        if hasattr(self, '_rounded_bar_group'):
            try:
                self.canvas.after.remove(self._rounded_bar_group)
            except ValueError:
                pass

        if not self._rounded_bar:
            return

        # Check of scrollbar nodig is
        if not hasattr(self, 'viewport_size') or self.viewport_size[1] <= self.height:
            return  # Geen scrollbar nodig

        # Scrollbar dimensies
        bar_width = self.bar_width
        viewport_ratio = self.height / self.viewport_size[1]
        bar_height = max(dp(30), viewport_ratio * self.height)

        # Scrollbar positie (rechts, afhankelijk van scroll_y)
        scroll_range = self.height - bar_height
        bar_x = self.right - bar_width - dp(2)
        bar_y = self.y + scroll_range * self.scroll_y

        # Teken rounded scrollbar
        from kivy.graphics import InstructionGroup
        self._rounded_bar_group = InstructionGroup()

        # Kleur
        self._rounded_bar_group.add(Color(*self._bar_color_override))

        # Capsule-vorm: radius is halve breedte
        radius = bar_width / 2
        self._rounded_bar_group.add(
            RoundedRectangle(
                pos=(bar_x, bar_y),
                size=(bar_width, bar_height),
                radius=[radius]
            )
        )

        self.canvas.after.add(self._rounded_bar_group)


class LibiryApp(App):
    """Main Libiry application."""

    current_path = StringProperty('')
    status_text = StringProperty('Select a folder to browse')

    CACHE_DIR = Path.home() / ".libiry" / "cache"

    ZOOM_LEVELS = [
        (dp(100), dp(150)),
        (dp(150), dp(225)),
        (dp(200), dp(300)),
        (dp(250), dp(375)),
    ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._zoom_level = 1
        self._history = []
        self._history_index = -1
        self._current_folder = None
        self._items = []
        self._selected_items = set()
        self._hidden_widgets = []  # Verborgen widgets door zoekfilter
        self._search_text = ''
        self._search_root = None  # Root folder voor recursieve search
        self._app_path = Path(__file__).parent

        # Load customization
        self.custom = load_customization(self._app_path)
        self.selected_types = load_selected_types(self._app_path)

        # Initialize core components
        self.cache = CoverCache(self.CACHE_DIR)
        # Clear cache bij opstarten zodat covers altijd vers geëxtraheerd worden
        self.cache.clear_cache()
        # Pass configured field names to extractors
        field_names = self.custom.get('field_names', {})
        self.extractor = CoverExtractor(field_names=field_names)
        self.metadata_extractor = MetadataExtractor(field_names=field_names)

        # Settings storage
        settings_dir = Path.home() / ".libiry"
        settings_dir.mkdir(parents=True, exist_ok=True)
        self.store = JsonStore(str(settings_dir / "settings.json"))

    def build(self):
        """Build the main UI."""
        self.title = 'Libiry'
        Window.bind(on_keyboard=self._on_keyboard)

        # Set window icon from resources
        icon_path = self._app_path / "resources" / "icons" / "Libiry.ico"
        if icon_path.exists():
            Window.set_icon(str(icon_path))
            # Windows taskbar icon - set after window is created with retries
            if sys.platform == 'win32':
                # Try multiple times to ensure window is ready
                for delay in [0.5, 1.0, 2.0]:
                    Clock.schedule_once(lambda dt, p=str(icon_path): self._set_windows_icon(p), delay)

        # Consistent alignment distance X
        self.margin_x = dp(10)

        # Font size en bar heights (dynamisch op basis van font size)
        self.ui_font_size = dp(self.custom['ui_font_size'])
        self.ui_bar_height = dp(self.custom['ui_font_size'] * 2.5)

        # Main layout with background color - spacing equals margin_x for consistent distance X
        self.root = BoxLayout(orientation='vertical', spacing=self.margin_x, padding=[self.margin_x, self.margin_x, self.margin_x, self.margin_x])
        with self.root.canvas.before:
            Color(*self.custom['background_color'])
            self.root_bg = Rectangle(pos=self.root.pos, size=self.root.size)
        self.root.bind(pos=self._update_root_bg, size=self._update_root_bg)

        # Toolbar
        toolbar = self._build_toolbar()
        self.root.add_widget(toolbar)

        # Path bar
        path_bar = self._build_path_bar()
        self.root.add_widget(path_bar)

        # Grid area with scrollbar in button color
        # Scrollbar styling: dikte en zichtbaarheid uit customize settings
        # RoundedScrollView tekent een capsule-vormige scrollbar als rounded_corners aan staat
        scrollbar_width = dp(self.custom['scrollbar_width'])
        scrollbar_always = self.custom['scrollbar_always_visible']
        use_rounded_scrollbar = self.custom['rounded_corners']
        self.scroll_view = RoundedScrollView(
            rounded=use_rounded_scrollbar,
            bar_color_override=self.custom['button_color'],
            do_scroll_x=False,
            bar_width=scrollbar_width,
            # Altijd 'bars' in scroll_type zodat scrollbar klikbaar/sleepbaar is
            scroll_type=['bars', 'content'],
            # Scrollbar zichtbaarheid: always_visible bepaalt of bar blijft staan of fade-out
            always_visible=scrollbar_always,
        )
        self.grid = GridLayout(
            cols=4,
            spacing=dp(10),
            padding=[0, 0, 0, 0],  # No extra padding, main layout already has margin_x
            size_hint_y=None,
        )
        self.grid.bind(minimum_height=self.grid.setter('height'))
        self.scroll_view.add_widget(self.grid)
        self.root.add_widget(self.scroll_view)

        # Tag list bar - TIJDELIJK VERBORGEN
        # TODO: Weer activeren wanneer tag functionaliteit volledig getest is
        # self.tag_list_label = Label(
        #     text='',
        #     size_hint=(1, None),
        #     height=0,
        #     halign='left',
        #     valign='top',
        #     color=self.custom['background_font_color'],
        #     font_size=self.ui_font_size,
        #     padding=[0, 0],
        #     markup=True,
        # )
        # self.tag_list_label.bind(
        #     texture_size=lambda instance, size: setattr(instance, 'height', size[1] if instance.text else 0)
        # )
        # self.tag_list_label.bind(
        #     width=lambda instance, width: setattr(instance, 'text_size', (width, None))
        # )
        # self.tag_list_label.bind(on_ref_press=self._on_tag_ref_press)
        # self.root.add_widget(self.tag_list_label)
        self.tag_list_label = None  # Placeholder voor wanneer tags weer geactiveerd worden

        # Status bar with Move/Delete buttons
        status_bar = BoxLayout(size_hint_y=None, height=self.ui_bar_height, spacing=dp(5))

        self.status_label = Label(
            text=self.status_text,
            size_hint=(1, 1),
            halign='left',
            valign='middle',
            color=self.custom['background_font_color'],
            font_size=self.ui_font_size,
            padding=[0, 0],
        )
        self.status_label.bind(size=lambda *x: setattr(self.status_label, 'text_size', self.status_label.size))
        status_bar.add_widget(self.status_label)

        button_color = self.custom['button_color']
        # Button width schaalt mee met font size
        btn_width_short = self.ui_font_size * 7
        btn_width_long = self.ui_font_size * 9

        # Show book title instelling uit settings (niet meer een knop)
        self._show_titles_active = self.custom.get('show_book_title', False)

        self.btn_move = ColoredButton(
            text='Move Selected',
            size_hint_x=None,
            width=btn_width_long,
            bg_color=button_color,
            rounded=self.custom['rounded_corners'],
            color=self.custom['button_font_color'],
            font_size=self.ui_font_size,
            disabled=True,
        )
        self.btn_move.bind(on_release=lambda x: self._move_selected())
        status_bar.add_widget(self.btn_move)

        self.btn_delete = ColoredButton(
            text='Delete Selected',
            size_hint_x=None,
            width=btn_width_long,
            bg_color=button_color,
            rounded=self.custom['rounded_corners'],
            color=self.custom['button_font_color'],
            font_size=self.ui_font_size,
            disabled=True,
        )
        self.btn_delete.bind(on_release=lambda x: self._delete_selected())
        status_bar.add_widget(self.btn_delete)

        self.root.add_widget(status_bar)

        self._load_settings()
        Window.bind(on_resize=self._on_window_resize)
        Clock.schedule_once(lambda dt: self._update_grid_cols(), 0.1)

        return self.root

    def _update_root_bg(self, *args):
        """Update root background rectangle."""
        self.root_bg.pos = self.root.pos
        self.root_bg.size = self.root.size

    def _build_toolbar(self):
        """Build the toolbar."""
        toolbar = BoxLayout(size_hint_y=None, height=self.ui_bar_height, spacing=dp(5))
        button_color = self.custom['button_color']
        icon_size = self.ui_bar_height  # Icons schalen mee met bar height

        # Back button - goes to parent directory
        back_icon = get_icon_path(self._app_path, 'back.png')
        if back_icon:
            self.btn_back = ImageButton(source=back_icon, size_hint=(None, None), size=(icon_size, icon_size))
        else:
            self.btn_back = Button(text='<', size_hint_x=None, width=icon_size, background_color=button_color, font_size=self.ui_font_size)
        self.btn_back.bind(on_release=lambda x: self.go_up())
        self.btn_back.opacity = 0  # Hidden until parent exists
        toolbar.add_widget(self.btn_back)

        refresh_icon = get_icon_path(self._app_path, 'refresh.png')
        if refresh_icon:
            btn_refresh = ImageButton(source=refresh_icon, size_hint=(None, None), size=(icon_size, icon_size))
        else:
            btn_refresh = Button(text='Refresh', size_hint_x=None, width=icon_size * 2, background_color=button_color, font_size=self.ui_font_size)
        btn_refresh.bind(on_release=lambda x: self._refresh())
        toolbar.add_widget(btn_refresh)

        toolbar.add_widget(BoxLayout(size_hint_x=0.02))

        # Search box with magnifying glass icon
        self.search_box = SearchBox(
            app_path=self._app_path,
            custom=self.custom,
            font_size=self.ui_font_size,
            on_text_change=self._on_search_changed,
            size_hint=(1, 1),
        )
        toolbar.add_widget(self.search_box)

        toolbar.add_widget(BoxLayout(size_hint_x=0.02))

        # === TOOLBAR BUTTONS (volgorde: information, gear, bento/plus, twins) ===

        # 1. Information button (leftmost of the icon group)
        info_icon = get_icon_path(self._app_path, 'information.png')
        if not info_icon:
            info_icon = get_icon_path(self._app_path, 'information.ico')
        if info_icon:
            self.btn_info = ImageButton(source=info_icon, size_hint=(None, None), size=(icon_size, icon_size))
            self.btn_info.tooltip_text = 'About Libiry'
        else:
            self.btn_info = Button(text='i', size_hint_x=None, width=icon_size, background_color=button_color, font_size=self.ui_font_size)
        self.btn_info.bind(on_release=self._on_info_click)
        toolbar.add_widget(self.btn_info)

        # 2. Settings/gear button
        gear_icon = get_icon_path(self._app_path, 'gear.png')
        if gear_icon:
            self.btn_gear = ImageButton(source=gear_icon, size_hint=(None, None), size=(icon_size, icon_size))
            self.btn_gear.tooltip_text = 'Settings'
        else:
            self.btn_gear = Button(text='⚙', size_hint_x=None, width=icon_size, background_color=button_color, font_size=self.ui_font_size)
        self.btn_gear.bind(on_release=self._on_gear_click)
        toolbar.add_widget(self.btn_gear)

        # 3. Bento button (was plus) - "Libiry apps" menu (BookSpineScanner)
        plus_icon = get_icon_path(self._app_path, 'plus.png')
        if plus_icon:
            self.btn_bento = ImageButton(source=plus_icon, size_hint=(None, None), size=(icon_size, icon_size))
            self.btn_bento.tooltip_text = 'Libiry apps'
        else:
            self.btn_bento = Button(text='+', size_hint_x=None, width=icon_size, background_color=button_color, font_size=self.ui_font_size)
        self.btn_bento.bind(on_release=lambda x: self._show_libiry_apps_popup())
        toolbar.add_widget(self.btn_bento)

        # 4. Twins filter button (rightmost)
        twins_icon = get_icon_path(self._app_path, 'twins.png')
        if twins_icon:
            self.btn_twins = ImageButton(source=twins_icon, size_hint=(None, None), size=(icon_size, icon_size))
            self.btn_twins.tooltip_text = 'Find duplicates'
        else:
            self.btn_twins = Button(text='2x', size_hint_x=None, width=icon_size, background_color=button_color, font_size=self.ui_font_size)
        self.btn_twins.bind(on_release=lambda x: self._toggle_twins_filter())
        self._twins_filter_active = False
        self._twins_filter_root = None  # Root folder voor relatief pad berekening
        # Tag filter state - voor filteren op specifieke tag via dubbelklik in tag lijst
        self._tag_filter_active = False
        self._tag_filter_tag = None  # De actieve tag waarop gefilterd wordt
        self._tag_filter_root = None  # Root folder voor relatief pad berekening
        toolbar.add_widget(self.btn_twins)

        return toolbar

    def _build_path_bar(self):
        """Build the path bar."""
        path_bar = BoxLayout(size_hint_y=None, height=self.ui_bar_height, spacing=dp(5))

        # Location box (no "Location:" label)
        self.path_box = LocationBox(
            custom=self.custom,
            font_size=self.ui_font_size,
            size_hint=(1, 1),
        )
        path_bar.add_widget(self.path_box)

        # Choose folder button
        btn_browse = ColoredButton(
            text='Choose folder',
            size_hint_x=None,
            width=self.ui_font_size * 9,
            bg_color=self.custom['button_color'],
            rounded=self.custom['rounded_corners'],
            color=self.custom['button_font_color'],
            font_size=self.ui_font_size,
        )
        btn_browse.bind(on_release=lambda x: self._show_folder_chooser())
        path_bar.add_widget(btn_browse)

        return path_bar

    def _show_folder_chooser(self):
        """Show folder chooser dialog."""
        content = BoxLayout(orientation='vertical')

        start_path = str(self._current_folder) if self._current_folder else str(Path.home())
        filechooser = FileChooserListView(
            path=start_path,
            dirselect=True,
            filters=[''],
        )
        # Gebruik modulaire helper voor consistente FileChooser styling
        self._style_filechooser(filechooser)
        content.add_widget(filechooser)

        btn_layout = self._create_popup_button_row()
        btn_cancel = self._create_popup_button('Cancel')
        btn_select = self._create_popup_button('Select')
        btn_layout.add_widget(btn_cancel)
        btn_layout.add_widget(btn_select)
        content.add_widget(btn_layout)

        popup = self._create_popup('Select', content, size_hint=(0.9, 0.9))

        def on_select(instance):
            if filechooser.selection:
                selected = filechooser.selection[0]
                if Path(selected).is_dir():
                    self.navigate_to(Path(selected))
            popup.dismiss()

        btn_cancel.bind(on_release=lambda x: popup.dismiss())
        btn_select.bind(on_release=on_select)
        popup.open()

    def navigate_to(self, path: Path, add_to_history: bool = True):
        """Navigate to a folder."""
        if not path.exists() or not path.is_dir():
            self._show_error(f"Folder not found: {path}")
            return

        if add_to_history and self._current_folder and self._current_folder != path:
            self._history = self._history[:self._history_index + 1]
            self._history.append(self._current_folder)
            self._history_index = len(self._history) - 1

        self._current_folder = path
        self.current_path = str(path)
        self.path_box.text = str(path)
        self.search_box.text = ''
        self._search_text = ''
        self._search_root = None

        # Reset twins filter on navigation
        if self._twins_filter_active:
            self._twins_filter_active = False
            self.btn_twins.opacity = 1.0

        # Reset tag filter on navigation
        if self._tag_filter_active:
            self._tag_filter_active = False
            self._tag_filter_tag = None
            self._tag_filter_root = None

        self._load_folder(path)
        self._update_nav_buttons()
        self._save_session_state()

    def _load_folder(self, folder_path: Path):
        """Load folder contents into grid. Handles missing/deleted folders gracefully."""
        self.grid.clear_widgets()
        self._items = []
        self._selected_items.clear()
        self._hidden_widgets = []  # Reset verborgen widgets van zoekfilter
        self.btn_move.disabled = True
        self.btn_delete.disabled = True
        self.btn_move.opacity = 0.5
        self.btn_delete.opacity = 0.5

        self.status_text = f"Loading {folder_path.name}..."
        self.status_label.text = self.status_text

        if not folder_path.exists():
            self.status_text = "Folder not found"
            self.status_label.text = self.status_text
            return

        try:
            items = sorted(folder_path.iterdir(), key=lambda x: x.name.lower())
        except PermissionError:
            self._show_error("Access denied")
            return
        except OSError as e:
            self.status_text = f"Error reading folder: {e}"
            self.status_label.text = self.status_text
            return

        folders = []
        files = []
        folder_count = 0
        file_count = 0

        if self.custom['only_selected_types']:
            allowed_formats = self.selected_types
        else:
            allowed_formats = None

        for item in items:
            try:
                # Skip hidden files/folders (Unix: begint met '.', Windows: hidden attribuut)
                if is_hidden(item):
                    continue

                if item.is_dir():
                    folders.append(item)
                    folder_count += 1
                elif item.is_file():
                    suffix = item.suffix.lower()
                    if allowed_formats is None or suffix in allowed_formats:
                        files.append(item)
                        file_count += 1
            except OSError:
                # Skip items that disappeared or can't be accessed
                continue

        self._items = folders + files

        # Add widgets in batches to keep UI responsive
        all_items = [(f, 'folder') for f in folders] + [(f, 'file') for f in files]
        self._pending_items = all_items
        self._load_batch_index = 0
        self._folder_count = folder_count
        self._file_count = file_count
        self._load_version = getattr(self, '_load_version', 0) + 1
        self._load_items_batch()

    def _load_items_batch(self, dt=None):
        """Load a batch of items into the grid, then schedule the next batch."""
        # Guard against stale batches from a previous _load_folder call
        if self._pending_items is None:
            return
        current_version = self._load_version

        BATCH_SIZE = 20
        items = self._pending_items
        start = self._load_batch_index
        end = min(start + BATCH_SIZE, len(items))

        for i in range(start, end):
            item_path, item_type = items[i]
            try:
                if item_type == 'folder':
                    self._add_folder_widget(item_path)
                else:
                    self._add_file_widget(item_path)
            except OSError:
                continue

        self._load_batch_index = end

        # Check if a new load was started while we were processing
        if self._load_version != current_version:
            return

        if end < len(items):
            self.status_label.text = f"Loading... {end}/{len(items)}"
            Clock.schedule_once(self._load_items_batch, 0)
        else:
            self.status_text = f"{self._folder_count} folders, {self._file_count} files"
            self.status_label.text = self.status_text
            self._pending_items = None
            # Update tag lijst na kleine delay (wacht op async metadata loading)
            Clock.schedule_once(lambda dt: self._update_tag_list(), 1.0)

    def _add_folder_widget(self, path: Path):
        """Add a folder widget to the grid."""
        try:
            # Tel items, maar respecteer de "only_selected_types" filter
            # zodat de count consistent is met wat je ziet als je de folder opent
            if self.custom['only_selected_types']:
                allowed = self.selected_types
                count = sum(
                    1 for f in path.iterdir()
                    if not f.name.startswith('.')
                    and (f.is_dir() or f.suffix.lower() in allowed)
                )
            else:
                count = sum(1 for f in path.iterdir() if not f.name.startswith('.'))
            name = f"{path.name}\n({count})"
        except (PermissionError, OSError):
            name = path.name

        w, h = self.ZOOM_LEVELS[self._zoom_level]
        widget = CoverImage(
            item_path=str(path),
            item_type='folder',
            item_name=name,
            file_type='folder',
            source='',
            size=(w, h + dp(20)),
            on_double_tap=self._on_item_double_tap,
            on_tap=self._on_item_tap,
            tile_font_color=self.custom['tile_font_color'],
            rounded_corners=self.custom['rounded_corners'],
            background_color=self.custom['background_color'],
        )
        self.grid.add_widget(widget)

    def _add_file_widget(self, path: Path):
        """Add a file widget to the grid. For multi-book markdown files, adds multiple widgets.

        Bij search mode (_search_root is set) worden alleen matchende boeken getoond.
        """
        file_type = get_file_type(path)
        document_type = get_document_type(path)

        # Check if this is a multi-book markdown file (no YAML frontmatter, multiple covers)
        if file_type in ('.md', '.markdown'):
            books = self.metadata_extractor.extract_all_books_from_markdown(path)
            if len(books) > 1:
                # Multi-book file: add a widget for each book
                # Bij search mode, filter op matchende boeken
                search_filter = self._search_text if self._search_root else None
                self._add_multi_book_widgets(path, books, document_type, search_filter)
                return

        # Single book/file: normal flow
        w, h = self.ZOOM_LEVELS[self._zoom_level]
        widget = CoverImage(
            item_path=str(path),
            item_type='file',
            item_name=path.stem,
            file_type=file_type,
            document_type=document_type,
            source='',
            size=(w, h + dp(20)),
            on_double_tap=self._on_item_double_tap,
            on_tap=self._on_item_tap,
            tile_font_color=self.custom['tile_font_color'],
            rounded_corners=self.custom['rounded_corners'],
            background_color=self.custom['background_color'],
        )
        self.grid.add_widget(widget)

        Thread(target=self._load_cover_async, args=(path, widget), daemon=True).start()

    def _add_multi_book_widgets(self, path: Path, books: list, document_type: str,
                                 search_filter: str = None):
        """Add multiple widgets for a multi-book markdown file.

        Args:
            path: Path to the markdown file
            books: List of BookMetadata objects
            document_type: Document type string
            search_filter: Als set, toon alleen boeken die matchen met deze zoekterm.
                          Dit voorkomt false positives bij multi-book files in search resultaten.
        """
        w, h = self.ZOOM_LEVELS[self._zoom_level]
        is_fuzzy = self.custom.get('fuzzy_search', False)

        for book_index, book_meta in enumerate(books):
            # Bij search mode: filter boeken die niet matchen
            if search_filter:
                matches = False
                # Check filename (altijd)
                if self._search_match(search_filter, path.name):
                    matches = True
                # Check booktitle
                elif book_meta.booktitle and self._search_match(search_filter, book_meta.booktitle):
                    matches = True
                # Check authors
                else:
                    for author in book_meta.authors:
                        if self._search_match(search_filter, author):
                            matches = True
                            break
                # Bij fuzzy search, ook ISBN en cover checken
                if not matches and is_fuzzy:
                    if book_meta.isbn and self._search_match(search_filter, book_meta.isbn):
                        matches = True
                    elif book_meta.cover_url and self._search_match(search_filter, book_meta.cover_url):
                        matches = True

                if not matches:
                    continue  # Skip dit boek - matcht niet met zoekterm
            # Use booktitle as display name, fallback to "Book N" if empty
            display_name = book_meta.booktitle if book_meta.booktitle else f"{path.stem} #{book_index + 1}"

            widget = CoverImage(
                item_path=str(path),
                item_type='file',
                item_name=display_name,
                file_type='.md',
                document_type=document_type,
                source='',
                size=(w, h + dp(20)),
                on_double_tap=self._on_item_double_tap,
                on_tap=self._on_item_tap,
                tile_font_color=self.custom['tile_font_color'],
                rounded_corners=self.custom['rounded_corners'],
                background_color=self.custom['background_color'],
                # Pre-fill metadata from extraction
                booktitle=book_meta.booktitle,
                authors=book_meta.authors,
                isbn=book_meta.isbn,
                cover_url=book_meta.cover_url,
                tags=book_meta.tags if book_meta.tags else [],  # Tags meegeven voor tag list
            )
            # Store book index for cover loading
            widget.book_index = book_index
            self.grid.add_widget(widget)

            # Load cover in background (pass book_index for multi-book)
            Thread(
                target=self._load_cover_async_multibook,
                args=(path, widget, book_index),
                daemon=True
            ).start()

    def _load_cover_async_multibook(self, path: Path, widget: CoverImage, book_index: int):
        """Load cover for a specific book in a multi-book markdown file."""
        try:
            if not path.exists():
                return

            # Get all covers from the file
            covers = self.extractor.extract_markdown_covers(path)

            if book_index < len(covers):
                cover_img, cover_ref = covers[book_index]

                if cover_img:
                    # Save to cache with unique key for this book
                    thumb_path = self.cache.get_cache_path(path, suffix=f"_book{book_index}")

                    # Create thumbnail
                    thumb_size = (300, 450)
                    cover_img.thumbnail(thumb_size, PILImage.Resampling.LANCZOS)

                    # Save thumbnail
                    thumb_path.parent.mkdir(parents=True, exist_ok=True)
                    if cover_img.mode in ('RGBA', 'P'):
                        cover_img = cover_img.convert('RGB')
                    cover_img.save(thumb_path, 'JPEG', quality=85)

                    # Schedule UI update
                    Clock.schedule_once(
                        lambda dt, w=widget, tp=str(thumb_path): self._update_multibook_cover(w, tp),
                        0
                    )
        except Exception as e:
            print(f"Error loading multi-book cover: {e}")

    def _update_multibook_cover(self, widget: CoverImage, thumb_path: str):
        """Update widget with loaded cover for multi-book file."""
        if Path(thumb_path).exists():
            widget.img_container.clear_widgets()
            widget.img = Image(source=thumb_path, size_hint=(1, 1), allow_stretch=True, keep_ratio=False)
            widget.img_container.add_widget(widget.img)
            widget._has_real_cover = True

            # Creëer title overlay voor tiles met covers (Show Title functie)
            widget._create_title_overlay()
            # Pas huidige show titles state toe
            if self._show_titles_active:
                widget.set_title_overlay_visible(True)
            if hasattr(widget, 'text_overlay'):
                widget.text_overlay = None

    def _load_cover_async(self, path: Path, widget: CoverImage):
        """Load cover and metadata in background thread. Handles missing files gracefully."""
        try:
            # Check if file still exists before trying to load
            if not path.exists():
                return

            # Extract metadata (booktitle, isbn, tags, etc.)
            metadata = self.metadata_extractor.extract(path)

            # Get cover thumbnail
            thumb_path = self.cache.get_cover(path, self.extractor)
            has_real_cover = self.cache.has_real_cover(path)


            # Schedule UI update on main thread
            Clock.schedule_once(
                lambda dt: self._update_cover_and_metadata(widget, str(thumb_path), has_real_cover, metadata), 0
            )
        except Exception as e:
            # Log the error so we can debug
            print(f"Error loading cover for {path}: {e}")
            import traceback
            traceback.print_exc()

    def _update_cover_and_metadata(self, widget: CoverImage, thumb_path: str, has_real_cover: bool, metadata: BookMetadata):
        """Update widget with loaded cover and metadata."""
        # Update metadata on widget
        widget.booktitle = metadata.booktitle
        widget.isbn = metadata.isbn
        widget.authors = metadata.authors
        widget.tags = metadata.tags
        widget.rating = metadata.rating if metadata.rating else 0
        widget.series = metadata.series
        widget.series_index = metadata.series_index if metadata.series_index else 0
        widget.cover_url = metadata.cover_url if metadata.cover_url else ''

        # Herteken tag indicator driehoekje nu tags beschikbaar zijn
        # (summary = rood, analog = grijs)
        widget._draw_document_type_triangle()

        # Determine display title (booktitle if different from filename, otherwise filename)
        display_title = metadata.booktitle if metadata.booktitle and metadata.booktitle != widget.item_name else widget.item_name

        if has_real_cover and Path(thumb_path).exists():
            # Clear the image container and add new cover
            widget.img_container.clear_widgets()
            widget.img = Image(source=thumb_path, size_hint=(1, 1), allow_stretch=True, keep_ratio=False)
            widget.img_container.add_widget(widget.img)
            widget._has_real_cover = True
            # Remove text overlay reference since container was cleared
            if hasattr(widget, 'text_overlay'):
                widget.text_overlay = None

            # Creëer title overlay voor tiles met covers (Show Title functie)
            widget._create_title_overlay()
            # Pas huidige show titles state toe
            if self._show_titles_active:
                widget.set_title_overlay_visible(True)
        else:
            # No real cover - update text overlay with "[author] - [booktitle]"
            if hasattr(widget, 'text_overlay') and widget.text_overlay:
                author_str = ', '.join(metadata.authors[:2]) if metadata.authors else ''
                if author_str and display_title:
                    overlay_text = f"{author_str} - {display_title}"
                elif display_title:
                    overlay_text = display_title
                elif author_str:
                    overlay_text = author_str
                else:
                    overlay_text = widget.item_name
                widget.text_overlay.text = overlay_text

    def _on_item_tap(self, widget):
        """Handle item tap - toggle selection."""
        widget.is_selected = not widget.is_selected
        if widget.is_selected:
            self._selected_items.add(widget.item_path)
        else:
            self._selected_items.discard(widget.item_path)
        widget._update_rect()
        # Enable/disable Move and Delete buttons based on selection
        has_selection = len(self._selected_items) > 0
        self.btn_move.disabled = not has_selection
        self.btn_delete.disabled = not has_selection
        self.btn_move.opacity = 1.0 if has_selection else 0.5
        self.btn_delete.opacity = 1.0 if has_selection else 0.5
        # Update status label with selection count
        self._update_status_with_selection()

    def _update_status_with_selection(self):
        """Update status label to include selection count if items are selected.

        Als twins filter actief is en er is precies 1 item geselecteerd,
        toon dan ook het relatieve pad vanaf de twins filter root folder.
        """
        selected_count = len(self._selected_items)
        if selected_count > 0:
            # Tel apart hoeveel folders en files geselecteerd zijn
            selected_folders = sum(1 for p in self._selected_items if Path(p).is_dir())
            selected_files = selected_count - selected_folders

            folder_text = f"{self._folder_count} folders"
            if selected_folders > 0:
                folder_text += f" ({selected_folders} selected)"

            file_text = f"{self._file_count} files"
            if selected_files > 0:
                file_text += f" ({selected_files} selected)"

            base_text = f"{folder_text}, {file_text}"

            # Als precies 1 item geselecteerd is, toon extensie + size + foldernaam + tags
            # Dit geldt ALTIJD, niet alleen bij twins filter (per user request)
            if selected_count == 1:
                selected_path = Path(list(self._selected_items)[0])
                # Toon extensie en file size voor bestanden (niet voor folders)
                if selected_path.is_file():
                    ext_text = selected_path.suffix.lower()
                    size_text = ""
                    try:
                        size_bytes = selected_path.stat().st_size
                        if size_bytes < 1024:
                            size_text = f"{size_bytes} B"
                        elif size_bytes < 1024 * 1024:
                            size_text = f"{size_bytes / 1024:.1f} KB"
                        else:
                            size_text = f"{size_bytes / (1024 * 1024):.1f} MB"
                    except OSError:
                        size_text = ""

                    # Zoek tags van geselecteerd item (formaat: #tag1, #tag2)
                    tags_text = ""
                    for child in self.grid.children:
                        if hasattr(child, 'item_path') and child.item_path == str(selected_path):
                            if hasattr(child, 'tags') and child.tags:
                                tags_text = "  " + ", ".join(f"#{tag}" for tag in child.tags)
                            break

                    # Bij twins filter of search: toon relatief pad vanaf root
                    # Anders (normale folder view): toon alleen de parent folder naam
                    if self._twins_filter_active and self._twins_filter_root:
                        try:
                            rel_path = selected_path.parent.relative_to(self._twins_filter_root)
                            if rel_path != Path('.'):
                                base_text += f"  |  {ext_text} {size_text} {rel_path}{tags_text}"
                            else:
                                base_text += f"  |  {ext_text} {size_text} (root){tags_text}"
                        except ValueError:
                            base_text += f"  |  {ext_text} {size_text} {selected_path.parent.name}{tags_text}"
                    elif self._search_root:
                        # Search modus: toon relatief pad vanaf search root
                        try:
                            rel_path = selected_path.parent.relative_to(self._search_root)
                            if rel_path != Path('.'):
                                base_text += f"  |  {ext_text} {size_text} {rel_path}{tags_text}"
                            else:
                                base_text += f"  |  {ext_text} {size_text} (root){tags_text}"
                        except ValueError:
                            base_text += f"  |  {ext_text} {size_text} {selected_path.parent.name}{tags_text}"
                    else:
                        # Normale modus: toon alleen parent folder naam
                        base_text += f"  |  {ext_text} {size_text} {selected_path.parent.name}{tags_text}"

            self.status_label.text = base_text
        else:
            self.status_label.text = f"{self._folder_count} folders, {self._file_count} files"

    def _update_tag_list(self):
        """Update the tag list at the bottom of the screen.

        Verzamelt alle tags van zichtbare boeken en toont ze gesorteerd
        op count (aflopend). Tags zijn klikbaar: een klik filtert op die tag.

        TIJDELIJK UITGESCHAKELD: tag_list_label is None zolang tags verborgen zijn.
        """
        # Skip als tag list verborgen is
        if self.tag_list_label is None:
            return

        from collections import Counter

        # Verzamel alle tags van zichtbare items in de grid
        tag_counter = Counter()
        for child in self.grid.children:
            if hasattr(child, 'tags') and child.tags:
                for tag in child.tags:
                    if tag:  # Skip lege tags
                        tag_counter[tag.lower().strip()] += 1

        if not tag_counter:
            self.tag_list_label.text = ''
            return

        # Sorteer op count (aflopend), dan alfabetisch
        sorted_tags = sorted(tag_counter.items(), key=lambda x: (-x[1], x[0]))

        # Format: [ref=tagname][u]#tag[/u][/ref] - klikbaar en onderstreept, zonder count
        tag_strings = [f"[ref={tag}][u]#{tag}[/u][/ref]" for tag, count in sorted_tags]
        self.tag_list_label.text = ", ".join(tag_strings)

    def _on_tag_ref_press(self, instance, ref_value):
        """Handle click op een tag in de tag lijst.

        De ref_value is de tag naam (zonder #). Filter op boeken met die tag.
        """
        tag = ref_value.strip().lower()
        if not tag:
            return

        # Filter op deze tag
        self._tag_filter_tag = tag
        self._tag_filter_active = True
        self._tag_filter_root = self._current_folder
        self._apply_tag_filter()

    def _apply_tag_filter(self):
        """Filter de huidige view om alleen boeken met de actieve tag te tonen.

        Voor multi-book markdown bestanden: toont alleen de boeken die de tag hebben,
        niet alle boeken in het bestand.
        """
        if not self._tag_filter_tag:
            return

        tag = self._tag_filter_tag
        self.status_label.text = f"Filtering on #{tag}..."

        # Verzamel recursief alle bestanden
        all_files = []
        try:
            self._collect_files_recursive(self._current_folder, all_files)
        except Exception:
            self.status_label.text = "Error scanning files"
            return

        if not all_files:
            self.status_label.text = "No files found"
            return

        # Update UI
        self.grid.clear_widgets()
        self._file_count = 0
        self._folder_count = 0

        # Verwerk elk bestand
        for filepath in all_files:
            try:
                file_type = filepath.suffix.lower()

                # Multi-book markdown: check elke book apart
                if file_type in ('.md', '.markdown'):
                    books = self.metadata_extractor.extract_all_books_from_markdown(filepath)
                    if len(books) > 1:
                        # Toon alleen boeken met de tag
                        for book_index, book_meta in enumerate(books):
                            if book_meta.tags:
                                book_tags = [t.lower().strip() for t in book_meta.tags if t]
                                if tag in book_tags:
                                    self._add_tag_filter_widget(filepath, book_index, book_meta)
                                    self._file_count += 1
                        continue

                # Single-book: normale check
                meta = self.metadata_extractor.extract(filepath)
                if meta and meta.tags:
                    file_tags = [t.lower().strip() for t in meta.tags if t]
                    if tag in file_tags:
                        self._add_file_widget(filepath)
                        self._file_count += 1
            except Exception:
                pass

        if self._file_count == 0:
            self.status_label.text = f"No books found with tag #{tag}"
            if self.tag_list_label:
                self.tag_list_label.text = ''
        else:
            self._update_status(files_only=True)
            self._update_tag_list()

    def _add_tag_filter_widget(self, path: Path, book_index: int, book_meta):
        """Voeg widget toe voor één boek uit een multi-book bestand (voor tag filter)."""
        w, h = self.ZOOM_LEVELS[self._zoom_level]
        document_type = get_document_type(path)
        display_name = book_meta.booktitle if book_meta.booktitle else f"{path.stem} #{book_index + 1}"

        widget = CoverImage(
            item_path=str(path),
            item_type='file',
            item_name=display_name,
            file_type='.md',
            document_type=document_type,
            source='',
            size=(w, h + dp(20)),
            on_double_tap=self._on_item_double_tap,
            on_tap=self._on_item_tap,
            tile_font_color=self.custom['tile_font_color'],
            rounded_corners=self.custom['rounded_corners'],
            background_color=self.custom['background_color'],
            booktitle=book_meta.booktitle,
            authors=book_meta.authors if book_meta.authors else [],
            isbn=book_meta.isbn if book_meta.isbn else '',
            cover_url=book_meta.cover_url if book_meta.cover_url else '',
            tags=book_meta.tags if book_meta.tags else [],
        )
        widget.book_index = book_index
        self.grid.add_widget(widget)

        # Load cover
        Thread(
            target=self._load_cover_async_multibook,
            args=(path, widget, book_index),
            daemon=True
        ).start()

    def _on_item_double_tap(self, path_str: str, item_type: str):
        """Handle item double tap."""
        path = Path(path_str)
        if item_type == 'folder':
            self.navigate_to(path)
        else:
            self.status_label.text = f"Opening {path.name}..."
            if open_in_default_app(path):
                self.status_label.text = f"Opened {path.name}"
            else:
                self._show_error(f"Could not open: {path.name}")

    def _move_selected(self):
        """Move selected items to another folder."""
        if not self._selected_items:
            return

        selected_paths = [Path(p) for p in self._selected_items]

        # Show folder chooser
        content = BoxLayout(orientation='vertical')
        start_path = str(self._current_folder) if self._current_folder else str(Path.home())
        filechooser = FileChooserListView(path=start_path, dirselect=True, filters=[''])
        # Gebruik modulaire helper voor consistente FileChooser styling
        self._style_filechooser(filechooser)
        content.add_widget(filechooser)

        btn_layout = self._create_popup_button_row()
        btn_cancel = self._create_popup_button('Cancel')
        btn_move = self._create_popup_button('Move here')
        btn_layout.add_widget(btn_cancel)
        btn_layout.add_widget(btn_move)
        content.add_widget(btn_layout)

        popup = self._create_popup(f'Move {len(selected_paths)} item(s) to...', content, size_hint=(0.9, 0.9))

        def on_move(instance):
            if not filechooser.selection:
                return
            dest = Path(filechooser.selection[0])
            if not dest.is_dir():
                return
            popup.dismiss()

            moved = 0
            errors = []
            for path in selected_paths:
                try:
                    new_path = dest / path.name
                    if new_path.exists():
                        # Skip files that already exist at destination
                        errors.append(f"{path.name}: already exists at destination")
                        continue
                    shutil.move(str(path), str(new_path))
                    moved += 1
                except Exception as e:
                    errors.append(f"{path.name}: {e}")

            # Als twins filter of search actief is: verwijder alleen widgets uit grid
            if self._twins_filter_active or self._search_root:
                widgets_to_remove = []
                for child in self.grid.children:
                    if hasattr(child, 'item_path') and child.item_path in self._selected_items:
                        widgets_to_remove.append(child)
                for widget in widgets_to_remove:
                    self.grid.remove_widget(widget)
                self._selected_items.clear()
                remaining = len(self.grid.children)
                if self._twins_filter_active:
                    self.status_label.text = f"Moved {moved} items. {remaining} duplicates remaining"
                else:
                    self.status_label.text = f"Moved {moved} items. {remaining} search results remaining"
                self._file_count = remaining
            else:
                self._selected_items.clear()
                self._refresh()
                self.status_label.text = f"Moved {moved} items to {dest.name}"

            if errors:
                self._show_error(f"Moved {moved} items.\n\nErrors:\n" + "\n".join(errors[:5]))

        btn_cancel.bind(on_release=lambda x: popup.dismiss())
        btn_move.bind(on_release=on_move)
        popup.open()

    def _delete_selected(self):
        """Delete selected items after confirmation."""
        if not self._selected_items:
            return

        selected_paths = [Path(p) for p in self._selected_items]
        count = len(selected_paths)

        # Check of er multi-book markdown files geselecteerd zijn
        has_multibook = False
        for path in selected_paths:
            if path.is_file() and path.suffix.lower() in ('.md', '.markdown'):
                books = self.metadata_extractor.extract_all_books_from_markdown(path)
                if len(books) > 1:
                    has_multibook = True
                    break

        # Check of er folders zijn met bestanden erin
        # (telt alle bestanden, ongeacht of ze getoond worden in de tool)
        folders_with_files = 0
        for path in selected_paths:
            if path.is_dir():
                try:
                    # Check of folder niet leeg is (any() stopt bij eerste hit)
                    if any(path.iterdir()):
                        folders_with_files += 1
                except (PermissionError, OSError):
                    pass

        # Bepaal waarschuwingstekst
        if has_multibook:
            warning_text = "Beware! This action will delete multiple books!"
        elif folders_with_files == 1:
            warning_text = "Beware! This action will delete the files in this folder too!"
        elif folders_with_files > 1:
            warning_text = "Beware! This action will delete the files in these folders too!"
        elif HAS_SEND2TRASH:
            warning_text = f"Move {count} item(s) to trash?"
        else:
            warning_text = f"Delete {count} item(s)?\n\nThis cannot be undone!"

        # Confirmation popup
        content = BoxLayout(orientation='vertical', padding=dp(10), spacing=dp(10))
        warning_label = self._create_popup_label(warning_text, halign='center', valign='middle')
        content.add_widget(warning_label)

        btn_layout = self._create_popup_button_row()
        btn_cancel = self._create_popup_button('Cancel')
        btn_confirm = self._create_popup_button('Delete', danger=True)
        btn_layout.add_widget(btn_cancel)
        btn_layout.add_widget(btn_confirm)
        content.add_widget(btn_layout)

        popup = self._create_popup('Confirm Delete', content, size_hint=(0.5, 0.3))

        def on_delete(instance):
            popup.dismiss()
            deleted = 0
            errors = []
            for path in selected_paths:
                try:
                    if HAS_SEND2TRASH:
                        # Gebruik send2trash voor cross-platform prullenbak support
                        send2trash(str(path))
                    else:
                        # Fallback: permanente verwijdering als send2trash niet beschikbaar
                        if path.is_file():
                            path.unlink()
                        elif path.is_dir():
                            shutil.rmtree(path)
                    deleted += 1
                except Exception as e:
                    errors.append(f"{path.name}: {e}")

            # Als twins filter of search actief is: verwijder alleen widgets uit grid
            # zonder de hele folder opnieuw te laden (voorkomt herberekening/reset)
            if self._twins_filter_active or self._search_root:
                # Verwijder widgets van verwijderde bestanden uit grid
                widgets_to_remove = []
                for child in self.grid.children:
                    if hasattr(child, 'item_path') and child.item_path in self._selected_items:
                        widgets_to_remove.append(child)
                for widget in widgets_to_remove:
                    self.grid.remove_widget(widget)
                self._selected_items.clear()
                # Update status met aantal resterende items
                remaining = len(self.grid.children)
                action = "Moved" if HAS_SEND2TRASH else "Deleted"
                if self._twins_filter_active:
                    self.status_label.text = f"{action} {deleted} items. {remaining} duplicates remaining"
                else:
                    self.status_label.text = f"{action} {deleted} items. {remaining} search results remaining"
                self._file_count = remaining
            else:
                self._selected_items.clear()
                self._refresh()

            if errors:
                action = "Moved to trash" if HAS_SEND2TRASH else "Deleted"
                self._show_error(f"{action} {deleted} items.\n\nErrors:\n" + "\n".join(errors[:5]))

        btn_cancel.bind(on_release=lambda x: popup.dismiss())
        btn_confirm.bind(on_release=on_delete)
        popup.open()

    def _on_search_changed(self, instance, value):
        """Handle search text change - triggers recursive search with debouncing.

        Debouncing: wacht 400ms nadat gebruiker stopt met typen voordat search start.
        Dit voorkomt dat bij elke toetsaanslag een zware recursieve search wordt gestart.
        """
        self._search_text = value.lower().strip()

        # Cancel eventuele geplande search
        if hasattr(self, '_search_event') and self._search_event:
            self._search_event.cancel()
            self._search_event = None

        if not self._search_text:
            # Zoekterm gewist - herstel normale folder view
            self._clear_search()
        else:
            # Schedule search na 400ms debounce delay
            self._search_event = Clock.schedule_once(
                lambda dt: self._start_async_search(), 0.4
            )

    def _search_match(self, pattern: str, text: str) -> bool:
        """Check of pattern matcht met text, afhankelijk van fuzzy_search setting.

        Als fuzzy_search=False: alleen exacte substring match (case insensitive)
        Als fuzzy_search=True: ook fuzzy match (alle chars verschijnen in volgorde)
        """
        pattern = pattern.lower()
        text = text.lower()

        # Altijd eerst exacte substring match proberen
        if pattern in text:
            return True

        # Alleen fuzzy match als setting aan staat
        if self.custom.get('fuzzy_search', False):
            pattern_idx = 0
            for char in text:
                if pattern_idx < len(pattern) and char == pattern[pattern_idx]:
                    pattern_idx += 1
            return pattern_idx == len(pattern)

        return False

    def _fuzzy_match(self, pattern: str, text: str) -> bool:
        """Alias voor backwards compatibility - gebruikt _search_match."""
        return self._search_match(pattern, text)

    def _start_async_search(self):
        """Start asynchrone search - verzamelt eerst bestanden, dan batch processing."""
        if not self._current_folder or not self._search_text:
            return

        # Sla search root op zodat we terug kunnen naar normale view
        if not self._search_root:
            self._search_root = self._current_folder

        # Cancel eventuele lopende scheduled batches
        if hasattr(self, '_search_batch_event') and self._search_batch_event:
            self._search_batch_event.cancel()
            self._search_batch_event = None
        if hasattr(self, '_search_results_event') and self._search_results_event:
            self._search_results_event.cancel()
            self._search_results_event = None

        # Increment search version om oude searches te cancelen
        self._search_version = getattr(self, '_search_version', 0) + 1
        current_version = self._search_version

        self.status_label.text = f"Searching for '{self._search_text}'..."

        # Clear grid alvast
        self.grid.clear_widgets()
        self._selected_items.clear()
        self._hidden_widgets = []

        # Verzamel recursief alle bestanden (dit is snel, alleen filesystem)
        all_files = []
        self._collect_files_recursive(self._current_folder, all_files, max_depth=10)

        # Start batch processing voor metadata matching
        self._pending_search_files = all_files
        self._search_matches = []
        self._search_batch_index = 0
        self._current_search_version = current_version
        # Geef expected_version expliciet mee zodat de batch chain deze versie volgt
        self._process_search_batch(expected_version=current_version)

    def _process_search_batch(self, dt=None, expected_version=None):
        """Verwerk een batch bestanden voor search matching.

        Verwerkt 50 bestanden per batch om UI responsief te houden.
        Controleert search_version om te stoppen als er een nieuwe search is gestart.

        Parameters:
            dt: delta time van Clock scheduler (niet gebruikt)
            expected_version: de search versie waarvoor deze batch is gestart.
                             Als dit niet overeenkomt met _search_version, is er
                             een nieuwe search gestart en stoppen we.
        """
        # Stop als search is gecanceld of nieuwe search is gestart
        # We vergelijken de expected_version (vastgelegd bij schedulen) met de huidige versie
        if expected_version is None:
            expected_version = getattr(self, '_current_search_version', None)
        if expected_version is None:
            return
        if expected_version != self._search_version:
            return
        if not self._search_text:
            return

        BATCH_SIZE = 50
        files = self._pending_search_files
        start_idx = self._search_batch_index
        end_idx = min(start_idx + BATCH_SIZE, len(files))

        # Verwerk deze batch
        for i in range(start_idx, end_idx):
            file_path = files[i]
            # Filename check eerst (snel) - altijd doorzoeken
            if self._search_match(self._search_text, file_path.name):
                self._search_matches.append(file_path)
            # Alleen metadata check als filename niet matcht (traag)
            elif self._file_matches_search_metadata(file_path):
                self._search_matches.append(file_path)

        self._search_batch_index = end_idx

        # Update status
        progress = int((end_idx / len(files)) * 100) if files else 100
        self.status_label.text = f"Searching... {progress}% ({len(self._search_matches)} found)"

        if end_idx < len(files):
            # Meer te verwerken - schedule volgende batch
            # Sla event op zodat het gecanceld kan worden bij nieuwe search
            # Gebruik partial om expected_version vast te leggen op schedule-moment
            self._search_batch_event = Clock.schedule_once(
                partial(self._process_search_batch, expected_version=expected_version), 0)
        else:
            # Klaar - toon resultaten
            self._show_search_results(expected_version)

    def _show_search_results(self, expected_version=None):
        """Toon zoekresultaten na batch processing.

        Parameters:
            expected_version: de search versie waarvoor deze resultaten zijn.
                             Wordt doorgegeven aan _add_search_results_batch.
        """
        # Gebruik expected_version als gegeven, anders val terug op _current_search_version
        if expected_version is None:
            expected_version = getattr(self, '_current_search_version', None)
        if expected_version is None:
            return
        if expected_version != self._search_version:
            return  # Gecanceld - er is een nieuwere search gestart

        matching_files = self._search_matches

        # Sorteer alfabetisch op naam
        matching_files.sort(key=lambda p: p.name.lower())

        # BELANGRIJK: Clear grid voordat we resultaten tonen
        self.grid.clear_widgets()
        self._selected_items.clear()

        # Voeg widgets toe in batches voor grote resultaten
        self._pending_search_results = matching_files
        self._search_results_index = 0
        # Geef expected_version door zodat de batch weet welke versie hij verwacht
        self._add_search_results_batch(expected_version=expected_version)

    def _add_search_results_batch(self, dt=None, expected_version=None):
        """Voeg zoekresultaten toe aan grid in batches.

        Parameters:
            dt: delta time van Clock scheduler (niet gebruikt)
            expected_version: de search versie waarvoor deze batch is.
                             Als dit niet overeenkomt met _search_version, stoppen we.
        """
        # Gebruik expected_version als gegeven, anders val terug op _current_search_version
        if expected_version is None:
            expected_version = getattr(self, '_current_search_version', None)
        if expected_version is None:
            return
        if expected_version != self._search_version:
            return  # Gecanceld - er is een nieuwere search gestart

        BATCH_SIZE = 20
        files = self._pending_search_results
        start_idx = self._search_results_index
        end_idx = min(start_idx + BATCH_SIZE, len(files))

        for i in range(start_idx, end_idx):
            self._add_file_widget(files[i])

        self._search_results_index = end_idx

        if end_idx < len(files):
            # Sla event op zodat het gecanceld kan worden bij nieuwe search
            # Gebruik partial om expected_version vast te leggen op schedule-moment
            self._search_results_event = Clock.schedule_once(
                partial(self._add_search_results_batch, expected_version=expected_version), 0)
        else:
            # Klaar
            self._folder_count = 0
            self._file_count = len(files)
            self.status_label.text = f"Found {len(files)} files matching '{self._search_text}'"

    def _file_matches_search_metadata(self, file_path: Path) -> bool:
        """Check of bestand metadata matcht met de zoekterm (NIET filename).

        Dit is de trage versie die alleen wordt aangeroepen als filename niet matcht.

        Bij fuzzy_search=True: doorzoekt booktitle, author, isbn, cover_url
        Bij fuzzy_search=False: doorzoekt ALLEEN booktitle en author (exacte substring match)
        """
        file_type = file_path.suffix.lower()
        is_fuzzy = self.custom.get('fuzzy_search', False)

        try:
            if file_type in ('.md', '.markdown'):
                # Markdown file - extract metadata
                # extract_all_books_from_markdown retourneert BookMetadata dataclass objecten
                books = self.metadata_extractor.extract_all_books_from_markdown(file_path)
                for book in books:
                    # Altijd booktitle en author doorzoeken
                    # BookMetadata heeft booktitle (str) en authors (List[str])
                    if book.booktitle and self._search_match(self._search_text, book.booktitle):
                        return True
                    # Doorzoek alle auteurs in de lijst
                    for author in book.authors:
                        if self._search_match(self._search_text, author):
                            return True
                    # ISBN en cover_url alleen bij fuzzy search
                    if is_fuzzy:
                        if book.isbn and self._search_match(self._search_text, book.isbn):
                            return True
                        if book.cover_url and self._search_match(self._search_text, book.cover_url):
                            return True
            elif file_type in ('.epub', '.mobi', '.azw', '.azw3'):
                # Ebook - extract metadata (kan traag zijn)
                # extract() retourneert ook een BookMetadata dataclass
                metadata = self.metadata_extractor.extract(file_path)
                if metadata:
                    # Altijd title en author doorzoeken
                    if metadata.booktitle and self._search_match(self._search_text, metadata.booktitle):
                        return True
                    # Doorzoek alle auteurs in de lijst
                    for author in metadata.authors:
                        if self._search_match(self._search_text, author):
                            return True
                    # ISBN alleen bij fuzzy search
                    if is_fuzzy:
                        if metadata.isbn and self._search_match(self._search_text, metadata.isbn):
                            return True
        except Exception:
            # Bij fouten (corrupt bestand, permission error, etc.) gewoon skippen
            pass

        return False

    def _clear_search(self):
        """Wis zoekresultaten en herstel normale folder view."""
        # Cancel eventuele lopende search
        if hasattr(self, '_search_event') and self._search_event:
            self._search_event.cancel()
            self._search_event = None
        # Increment version om batch processing te stoppen
        self._search_version = getattr(self, '_search_version', 0) + 1

        self._search_root = None
        self._hidden_widgets = []
        if self._current_folder:
            self._load_folder(self._current_folder)

    def _normalize_title(self, title: str) -> str:
        """
        Normalize title for duplicate comparison (Calibre-style).
        - Lowercase
        - Remove common prefixes: A, An, The, De, Het, Een
        - Remove punctuation
        - Collapse whitespace
        """
        if not title:
            return ""

        title = title.lower().strip()

        # Remove common prefixes (English and Dutch)
        prefixes = ['the ', 'a ', 'an ', 'de ', 'het ', 'een ']
        for prefix in prefixes:
            if title.startswith(prefix):
                title = title[len(prefix):]
                break

        # Remove punctuation and special characters
        title = re.sub(r'[^\w\s]', '', title)

        # Collapse whitespace
        title = re.sub(r'\s+', ' ', title).strip()

        return title

    def _normalize_author(self, author: str) -> str:
        """
        Normalize author name for duplicate comparison (Calibre-style).
        - Lowercase
        - Remove jr, sr, phd, md, etc.
        - Remove punctuation
        - Simplify to lastname + first initial(s)
        """
        if not author:
            return ""

        author = author.lower().strip()

        # Remove common suffixes
        suffixes = [' jr', ' sr', ' jr.', ' sr.', ' phd', ' ph.d', ' md', ' m.d', ' iii', ' ii', ' iv']
        for suffix in suffixes:
            if author.endswith(suffix):
                author = author[:-len(suffix)]

        # Remove punctuation
        author = re.sub(r'[^\w\s]', '', author)

        # Collapse whitespace
        author = re.sub(r'\s+', ' ', author).strip()

        # Try to extract lastname (assume "First Last" or "Last, First" format)
        parts = author.split()
        if len(parts) >= 2:
            # Check for "Last, First" format (comma was removed, but typically last name first)
            # Simplify to just the parts for comparison
            # Sort parts to make "john smith" and "smith john" match
            parts = sorted(parts)

        return ' '.join(parts)

    def _get_normalized_authors(self, widget) -> list:
        """Get list of normalized author names from widget."""
        if hasattr(widget, 'authors') and widget.authors:
            return [self._normalize_author(a) for a in widget.authors if a]
        return []

    def _titles_match(self, title1: str, title2: str) -> bool:
        """Check if two titles are similar enough to be duplicates."""
        norm1 = self._normalize_title(title1)
        norm2 = self._normalize_title(title2)

        if not norm1 or not norm2:
            return False

        # Exact match after normalization
        if norm1 == norm2:
            return True

        # Check if one is substring of the other (for subtitles)
        if norm1 in norm2 or norm2 in norm1:
            # Only match if the shorter is at least 70% of the longer
            shorter = min(len(norm1), len(norm2))
            longer = max(len(norm1), len(norm2))
            if shorter / longer >= 0.7:
                return True

        return False

    def _authors_match(self, authors1: list, authors2: list) -> bool:
        """Check if author lists have any matching authors."""
        if not authors1 or not authors2:
            return False

        norm1 = set(self._normalize_author(a) for a in authors1 if a)
        norm2 = set(self._normalize_author(a) for a in authors2 if a)

        # Any overlapping author is a match
        return bool(norm1 & norm2)

    def _toggle_twins_filter(self):
        """Toggle filter to show duplicate books (by ISBN or by title+author)."""
        self._twins_filter_active = not self._twins_filter_active

        if self._twins_filter_active:
            self._apply_twins_filter()
            # Visual feedback - dim the button or change appearance
            self.btn_twins.opacity = 0.6
        else:
            # Restore all items
            self._clear_twins_filter()
            self.btn_twins.opacity = 1.0
            # Re-apply search filter if active
            if self._search_text:
                self._start_async_search()
            else:
                self.status_label.text = f"Filter cleared"

    def _apply_twins_filter(self):
        """
        Show only duplicate books using Calibre-style logic.
        BELANGRIJK: Doorzoekt recursief ALLE subfolders vanaf de huidige locatie.

        Duplicates worden gevonden op basis van:
        1. Identical ISBN
        2. Similar title AND similar author (fuzzy matching)

        Resultaten worden gegroepeerd per duplicate set zodat gerelateerde
        boeken bij elkaar staan.

        Gebruikt een background thread voor de zware operaties om de UI
        responsive te houden. Clock.schedule_once wordt gebruikt om de
        UI-updates terug op de main thread te doen.
        """
        self.status_label.text = "Scanning all subfolders for duplicates..."

        # Bewaar root folder voor relatieve pad berekening
        self._twins_filter_root = self._current_folder

        # Start background thread voor de zware operaties
        def background_scan():
            from concurrent.futures import ThreadPoolExecutor, as_completed

            # DEBUG mode: alleen als twins_debug.txt al bestaat in de folder
            # (gebruiker kan dit bestand aanmaken om debug output te krijgen)
            debug_file = self._current_folder / "twins_debug.txt"
            debug_mode = debug_file.exists()
            debug_lines = [] if debug_mode else None

            if debug_mode:
                debug_lines.append(f"=== TWINS FILTER DEBUG ===")
                debug_lines.append(f"Root folder: {self._current_folder}")
                debug_lines.append("")
                debug_lines.append("=== FILE COLLECTION ===")

            # Stap 1: Verzamel recursief alle bestanden uit alle subfolders
            all_files = []
            self._collect_files_recursive(self._current_folder, all_files,
                                          debug_lines=debug_lines if debug_mode else None)

            if not all_files:
                Clock.schedule_once(lambda dt: setattr(self.status_label, 'text', "No files found"))
                return

            if debug_mode:
                debug_lines.append("")
                debug_lines.append(f"Total files collected: {len(all_files)}")
                debug_lines.append("")

            num_files = len(all_files)
            Clock.schedule_once(lambda dt: setattr(self.status_label, 'text', f"Analyzing {num_files} files..."))

            # Stap 2: Haal metadata op met parallelle verwerking (veel sneller!)
            # Gebruik ThreadPoolExecutor voor I/O-bound metadata extractie
            def extract_metadata(filepath):
                """Extract metadata voor één bestand.

                Voor multi-book markdown files wordt een lijst van metadata entries
                geretourneerd, één per boek. Elk entry heeft een 'book_index' key.
                Voor andere bestanden wordt een lijst met één entry geretourneerd.
                """
                try:
                    file_type = filepath.suffix.lower()

                    # Voor markdown files: check op multi-book
                    if file_type in ('.md', '.markdown'):
                        books = self.metadata_extractor.extract_all_books_from_markdown(filepath)
                        if len(books) > 1:
                            # Multi-book file: retourneer metadata voor elk boek
                            results = []
                            for book_index, meta in enumerate(books):
                                results.append({
                                    'path': filepath,
                                    'book_index': book_index,
                                    'isbn': meta.isbn or '',
                                    'booktitle': meta.booktitle or f"{filepath.stem} #{book_index + 1}",
                                    'authors': meta.authors or [],
                                })
                            return results

                    # Single book file: normale extractie
                    meta = self.metadata_extractor.extract(filepath)
                    return [{
                        'path': filepath,
                        'book_index': None,  # Geen multi-book
                        'isbn': meta.isbn or '',
                        'booktitle': meta.booktitle or filepath.stem,
                        'authors': meta.authors or [],
                    }]
                except Exception:
                    return [{
                        'path': filepath,
                        'book_index': None,
                        'isbn': '',
                        'booktitle': filepath.stem,
                        'authors': [],
                    }]

            file_metadata = []
            # Gebruik max 8 threads voor metadata extractie
            max_workers = min(8, num_files)
            processed = 0

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {executor.submit(extract_metadata, fp): fp for fp in all_files}

                for future in as_completed(futures):
                    # extract_metadata retourneert nu een lijst (voor multi-book support)
                    metadata_list = future.result()
                    file_metadata.extend(metadata_list)
                    processed += 1

                    # Update status elke 100 bestanden
                    if processed % 100 == 0:
                        pct = int(processed / num_files * 100)
                        Clock.schedule_once(
                            lambda dt, p=processed, n=num_files, pc=pct:
                            setattr(self.status_label, 'text', f"Analyzing... {p}/{n} ({pc}%)"), 0)

            if debug_mode:
                debug_lines.append("=== EXTRACTED METADATA ===")
                for meta in file_metadata:
                    book_idx = meta.get('book_index')
                    if book_idx is not None:
                        debug_lines.append(f"File: {meta['path'].name} [Book #{book_idx + 1}]")
                    else:
                        debug_lines.append(f"File: {meta['path'].name}")
                    debug_lines.append(f"  booktitle: '{meta['booktitle']}'")
                    debug_lines.append(f"  authors: {meta['authors']}")
                    debug_lines.append(f"  isbn: '{meta['isbn']}'")
                    debug_lines.append("")

            # Stap 3: Vind duplicates en groepeer ze per set
            # duplicate_sets is een lijst van lijsten - elke sublijst bevat
            # metadata van bestanden die duplicates van elkaar zijn
            duplicate_sets = []
            # processed_items slaat (path, book_index) tuples op zodat multi-book files
            # correct worden bijgehouden - elk boek is een apart item
            processed_items = set()

            def get_item_key(meta):
                """Genereer unieke key voor een metadata entry (ondersteunt multi-book)."""
                return (meta['path'], meta.get('book_index'))

            # Method 1: ISBN duplicates
            if debug_mode:
                debug_lines.append("=== ISBN MATCHING ===")
            isbn_to_files = {}
            for meta in file_metadata:
                isbn = meta['isbn']
                if isbn:
                    if isbn not in isbn_to_files:
                        isbn_to_files[isbn] = []
                    isbn_to_files[isbn].append(meta)

            for isbn, files in isbn_to_files.items():
                if debug_mode:
                    debug_lines.append(f"ISBN {isbn}: {len(files)} file(s)")
                    for f in files:
                        book_idx = f.get('book_index')
                        suffix = f" [Book #{book_idx + 1}]" if book_idx is not None else ""
                        debug_lines.append(f"  - {f['path'].name}{suffix}")
                if len(files) > 1:
                    # Voeg alleen items toe die nog niet verwerkt zijn
                    new_set = [f for f in files if get_item_key(f) not in processed_items]
                    if len(new_set) > 1:
                        if debug_mode:
                            debug_lines.append(f"  -> DUPLICATE SET FOUND!")
                        duplicate_sets.append(new_set)
                        for f in new_set:
                            processed_items.add(get_item_key(f))
            if debug_mode:
                debug_lines.append("")

            # Method 2: Title + Author duplicates
            # BELANGRIJK: We bouwen groepen voor ALLE bestanden (ook die al in ISBN sets zitten)
            # zodat een bestand zonder ISBN alsnog gematcht kan worden met een bestand
            # dat wel een ISBN heeft maar dezelfde titel/auteur.
            if debug_mode:
                debug_lines.append("=== TITLE+AUTHOR MATCHING ===")
            title_author_groups = {}
            for meta in file_metadata:
                title = meta['booktitle']
                if not title:
                    continue

                norm_title = self._normalize_title(title)
                norm_authors = tuple(sorted(self._normalize_author(a) for a in meta['authors'] if a)) if meta['authors'] else ()

                key = (norm_title, norm_authors)
                if key not in title_author_groups:
                    title_author_groups[key] = []
                title_author_groups[key].append(meta)

            if debug_mode:
                debug_lines.append("")
                debug_lines.append("Title+Author groups:")
            for key, files in title_author_groups.items():
                norm_title, norm_authors = key
                if debug_mode:
                    debug_lines.append(f"  Key: title='{norm_title}', authors={norm_authors}")
                    for f in files:
                        book_idx = f.get('book_index')
                        suffix = f" [Book #{book_idx + 1}]" if book_idx is not None else ""
                        in_isbn_set = "(ISBN set)" if get_item_key(f) in processed_items else ""
                        debug_lines.append(f"    - {f['path'].name}{suffix} {in_isbn_set}")

                if len(files) > 1:
                    # Check hoeveel items nog niet verwerkt zijn
                    unprocessed = [f for f in files if get_item_key(f) not in processed_items]
                    already_processed = [f for f in files if get_item_key(f) in processed_items]

                    if len(unprocessed) > 0 and len(already_processed) > 0:
                        # Er zijn items die nog niet gematcht zijn maar WEL dezelfde
                        # titel/auteur hebben als items in een ISBN set.
                        # Voeg ALLEEN de unprocessed items toe - de already_processed
                        # zitten al in een andere set en hoeven niet dubbel getoond.
                        if debug_mode:
                            debug_lines.append(f"    -> CROSS-MATCH: adding {len(unprocessed)} new items (matched with {len(already_processed)} from ISBN sets)")
                        duplicate_sets.append(unprocessed)
                        for f in unprocessed:
                            processed_items.add(get_item_key(f))
                    elif len(unprocessed) > 1:
                        # Meerdere nieuwe items met dezelfde titel/auteur
                        if debug_mode:
                            debug_lines.append(f"    -> DUPLICATE SET FOUND!")
                        duplicate_sets.append(unprocessed)
                        for f in unprocessed:
                            processed_items.add(get_item_key(f))
            if debug_mode:
                debug_lines.append("")

            # Fuzzy title matching - voeg toe aan bestaande sets of maak nieuwe
            if debug_mode:
                debug_lines.append("=== FUZZY TITLE MATCHING ===")
            title_keys = list(title_author_groups.keys())
            for i, (title1, authors1) in enumerate(title_keys):
                if not title1:
                    continue
                for j, (title2, authors2) in enumerate(title_keys[i+1:], i+1):
                    if not title2:
                        continue

                    titles_match = self._titles_match(title1, title2)
                    if titles_match:
                        if not authors1 or not authors2:
                            authors_ok = True
                            reason = "one has no authors"
                        else:
                            authors_ok = bool(set(authors1) & set(authors2))
                            reason = f"author overlap: {set(authors1) & set(authors2)}" if authors_ok else "no author overlap"

                        if debug_mode:
                            debug_lines.append(f"Comparing: '{title1}' vs '{title2}'")
                            debug_lines.append(f"  titles_match: {titles_match}, authors_ok: {authors_ok} ({reason})")

                        if authors_ok:
                            files1 = [f for f in title_author_groups[(title1, authors1)] if get_item_key(f) not in processed_items]
                            files2 = [f for f in title_author_groups[(title2, authors2)] if get_item_key(f) not in processed_items]
                            combined = files1 + files2
                            if debug_mode:
                                debug_lines.append(f"  files1: {[f['path'].name for f in files1]}")
                                debug_lines.append(f"  files2: {[f['path'].name for f in files2]}")
                            if len(combined) > 1:
                                if debug_mode:
                                    debug_lines.append(f"  -> FUZZY DUPLICATE SET FOUND!")
                                duplicate_sets.append(combined)
                                for f in combined:
                                    processed_items.add(get_item_key(f))

            # DEBUG: Write summary and save file (only if debug mode is on)
            if debug_mode:
                debug_lines.append("")
                debug_lines.append("=== SUMMARY ===")
                debug_lines.append(f"Total duplicate sets found: {len(duplicate_sets)}")
                for i, dup_set in enumerate(duplicate_sets):
                    debug_lines.append(f"  Set {i+1}:")
                    for f in dup_set:
                        book_idx = f.get('book_index')
                        suffix = f" [Book #{book_idx + 1}]" if book_idx is not None else ""
                        debug_lines.append(f"    - {f['path'].name}{suffix}")
                debug_lines.append("")
                debug_lines.append("Debug file saved to: " + str(debug_file))

                # Write debug file
                try:
                    with open(debug_file, 'w', encoding='utf-8') as f:
                        f.write('\n'.join(debug_lines))
                    print(f"Twins debug output written to: {debug_file}")
                except Exception as e:
                    print(f"Failed to write debug file: {e}")

            # Schedule UI update op main thread
            Clock.schedule_once(lambda dt: self._show_duplicates_result(duplicate_sets, file_metadata))

        Thread(target=background_scan, daemon=True).start()

    def _show_duplicates_result(self, duplicate_sets: list, file_metadata: list):
        """
        Toon de gevonden duplicates in de grid, gegroepeerd per set.

        duplicate_sets is een lijst van lijsten - elke sublijst bevat metadata
        van bestanden die duplicates van elkaar zijn. Door ze per set te tonen
        staan gerelateerde boeken bij elkaar in de grid.

        Voor multi-book markdown files wordt elk boek als apart item behandeld,
        met de juiste book_index zodat de correcte cover wordt geladen.

        Deze functie wordt aangeroepen vanuit Clock.schedule_once om ervoor te
        zorgen dat UI updates op de main thread gebeuren.
        """
        if not duplicate_sets:
            self.status_label.text = "No duplicates found in any subfolders"
            return

        # Maak grid leeg en vul met duplicates per set
        self.grid.clear_widgets()
        self._selected_items.clear()

        w, h = self.ZOOM_LEVELS[self._zoom_level]
        total_files = 0

        # Track welke items al getoond zijn om duplicaten te voorkomen
        # Gebruik (path, book_index) tuples voor multi-book support
        shown_items = set()

        # Loop door elke duplicate set en voeg de bestanden toe
        # Hierdoor staan duplicates van elkaar altijd bij elkaar
        for dup_set in duplicate_sets:
            # Sorteer binnen de set op folder pad zodat zelfde folders bij elkaar staan
            sorted_set = sorted(dup_set, key=lambda m: str(m['path'].parent))

            for meta in sorted_set:
                # Genereer unieke key voor dit item (ondersteunt multi-book)
                book_index = meta.get('book_index')
                item_key = (meta['path'], book_index)

                # Skip als dit item al getoond is
                if item_key in shown_items:
                    continue
                shown_items.add(item_key)

                filepath = meta['path']
                file_type = get_file_type(filepath)
                document_type = get_document_type(filepath)

                # Voor multi-book files: gebruik booktitle als display name
                if book_index is not None:
                    display_name = meta['booktitle'] or f"{filepath.stem} #{book_index + 1}"
                else:
                    display_name = filepath.stem

                widget = CoverImage(
                    item_path=str(filepath),
                    item_type='file',
                    item_name=display_name,
                    file_type=file_type,
                    document_type=document_type,
                    source='',
                    size=(w, h + dp(20)),
                    on_double_tap=self._on_item_double_tap,
                    on_tap=self._on_item_tap,
                    tile_font_color=self.custom['tile_font_color'],
                    rounded_corners=self.custom['rounded_corners'],
                    background_color=self.custom['background_color'],
                    booktitle=meta['booktitle'],
                    authors=meta['authors'],
                    isbn=meta['isbn'],
                )

                # Sla book_index op voor multi-book cover loading
                if book_index is not None:
                    widget.book_index = book_index

                self.grid.add_widget(widget)

                # Gebruik juiste cover loader voor multi-book vs single-book
                if book_index is not None:
                    Thread(
                        target=self._load_cover_async_multibook,
                        args=(filepath, widget, book_index),
                        daemon=True
                    ).start()
                else:
                    Thread(target=self._load_cover_async, args=(filepath, widget), daemon=True).start()

                total_files += 1

        self._folder_count = 0
        self._file_count = total_files
        self.status_label.text = f"Found {total_files} duplicates in {len(duplicate_sets)} sets"

    def _collect_files_recursive(self, folder: Path, result: list, max_depth: int = 10, debug_lines: list = None):
        """Verzamel recursief alle bestanden uit folder en subfolders."""
        if max_depth <= 0:
            if debug_lines is not None:
                debug_lines.append(f"  MAX DEPTH REACHED at {folder}")
            return

        try:
            if debug_lines is not None:
                debug_lines.append(f"  Scanning: {folder} (depth remaining: {max_depth})")

            for item in folder.iterdir():
                # Skip hidden files/folders (Unix: '.', Windows: hidden attribuut)
                if is_hidden(item):
                    if debug_lines is not None:
                        debug_lines.append(f"    SKIPPED (hidden): {item.name}")
                    continue

                if item.is_file():
                    # Filter op toegestane bestandstypes
                    if self.custom['only_selected_types']:
                        if item.suffix.lower() not in self.selected_types:
                            if debug_lines is not None:
                                debug_lines.append(f"    SKIPPED (type filter): {item.name}")
                            continue
                    result.append(item)
                    if debug_lines is not None:
                        debug_lines.append(f"    ADDED: {item.name}")
                elif item.is_dir():
                    self._collect_files_recursive(item, result, max_depth - 1, debug_lines)
        except PermissionError as e:
            if debug_lines is not None:
                debug_lines.append(f"  PERMISSION ERROR: {folder} - {e}")
        except Exception as e:
            if debug_lines is not None:
                debug_lines.append(f"  ERROR scanning {folder}: {e}")

    def _clear_twins_filter(self):
        """Clear the twins filter and restore normal folder view.

        Omdat de nieuwe recursive twins filter de hele grid content vervangt
        met alleen duplicate files uit alle subfolders, moeten we de normale
        folder view herstellen door de huidige folder opnieuw te laden.
        """
        self._twins_filter_root = None
        if self._current_folder:
            self._load_folder(self._current_folder)

    def go_up(self):
        """Navigate to parent folder."""
        if self._current_folder and self._current_folder.parent != self._current_folder:
            self.navigate_to(self._current_folder.parent)

    def _update_nav_buttons(self):
        """Update navigation button visibility."""
        # Back button: visible if parent folder exists
        has_parent = (
            self._current_folder is not None and
            self._current_folder.parent != self._current_folder
        )
        self.btn_back.opacity = 1 if has_parent else 0
        self.btn_back.disabled = not has_parent

    def _refresh(self):
        """Refresh current view (folder, twins, tag filter, or search)."""
        if self._twins_filter_active:
            # Twins filter actief: voer twins filter opnieuw uit
            self._apply_twins_filter()
        elif self._tag_filter_active:
            # Tag filter actief: voer tag filter opnieuw uit
            self._apply_tag_filter()
        elif self._search_root and self._search_text:
            # Search actief: voer search opnieuw uit
            self._start_async_search()
        elif self._current_folder:
            # Normale folder view
            self._load_folder(self._current_folder)

    def _zoom_in(self):
        """Zoom in (larger covers)."""
        if self._zoom_level < len(self.ZOOM_LEVELS) - 1:
            self._zoom_level += 1
            self._update_grid_cols()
            self._refresh()

    def _zoom_out(self):
        """Zoom out (smaller covers)."""
        if self._zoom_level > 0:
            self._zoom_level -= 1
            self._update_grid_cols()
            self._refresh()

    def _open_bookspinescanner(self):
        """Open BookSpineScanner website in default browser."""
        import webbrowser
        webbrowser.open('https://sappelen.github.io/BookSpineScanner/')

    def _open_libiry2go(self):
        """Start Libiry2Go.bat lokaal.

        Libiry2Go wordt meegeïnstalleerd met Libiry en gebruikt dezelfde
        settings. Het .bat bestand wordt gezocht in:
        1. Dezelfde map als Libiry
        2. Sibling folder 'Libiry2Go'
        3. Parent folder
        """
        import subprocess
        import os

        # Zoek Libiry2Go.bat op verschillende locaties
        possible_paths = [
            self._app_path / 'Libiry2Go.bat',
            self._app_path.parent / 'Libiry2Go' / 'Libiry2Go.bat',
            self._app_path.parent / 'Libiry2Go.bat',
        ]

        bat_path = None
        for path in possible_paths:
            if path.exists():
                bat_path = path
                break

        if bat_path:
            try:
                # Start batch file in eigen venster (niet wachten op resultaat)
                subprocess.Popen(
                    ['cmd', '/c', str(bat_path)],
                    cwd=str(bat_path.parent),
                    creationflags=subprocess.CREATE_NEW_CONSOLE
                )
            except Exception as e:
                self._show_error(f"Could not start Libiry2Go: {e}")
        else:
            self._show_error(
                f"Libiry2Go.bat not found.\n\n"
                f"Searched in:\n"
                f"- {possible_paths[0]}\n"
                f"- {possible_paths[1]}\n"
                f"- {possible_paths[2]}"
            )

    def _show_libiry_apps_popup(self):
        """Toon popup met Libiry apps (BookSpineScanner).

        Dit is de "bento" menu popup, analoog aan Google Apps in Gmail.
        Compact design: alleen app buttons en cancel, geen instructietekst.
        Gestyled volgens huisstijl met _create_popup helpers.
        """
        content = BoxLayout(orientation='vertical', spacing=dp(10), padding=dp(15))

        # App buttons - elk in eigen row voor consistente hoogte
        btn_row_bss = self._create_popup_button_row()
        btn_bss = self._create_popup_button('BookSpineScanner')
        btn_row_bss.add_widget(btn_bss)
        content.add_widget(btn_row_bss)

        # Spacer
        content.add_widget(BoxLayout(size_hint_y=1))

        # Cancel button
        btn_row_cancel = self._create_popup_button_row()
        btn_cancel = self._create_popup_button('Cancel')
        btn_row_cancel.add_widget(btn_cancel)
        content.add_widget(btn_row_cancel)

        # Popup aanmaken - compacter formaat
        popup = self._create_popup('Libiry apps', content, size_hint=(0.4, 0.3))

        def on_bss(instance):
            popup.dismiss()
            self._open_bookspinescanner()

        btn_bss.bind(on_release=on_bss)
        btn_cancel.bind(on_release=lambda x: popup.dismiss())

        popup.open()

    def _update_grid_cols(self):
        """Update grid columns based on window size and zoom level."""
        w, h = self.ZOOM_LEVELS[self._zoom_level]
        available_width = Window.width - dp(40)
        cols = max(1, int(available_width / (w + dp(20))))
        self.grid.cols = cols

    def _on_window_resize(self, window, width, height):
        """Handle window resize."""
        self._update_grid_cols()

    def _on_keyboard(self, window, key, scancode, codepoint, modifier):
        """Handle keyboard shortcuts."""
        if 'ctrl' in modifier and (codepoint == '=' or codepoint == '+'):
            self._zoom_in()
            return True
        if 'ctrl' in modifier and codepoint == '-':
            self._zoom_out()
            return True
        if key == 286:  # F5
            self._refresh()
            return True
        if 'alt' in modifier and key == 276:  # Left arrow - go to parent
            self.go_up()
            return True
        if 'alt' in modifier and key == 273:  # Up arrow
            self.go_up()
            return True
        return False

    # === POPUP STYLING HELPERS ===
    # Modulaire helpers voor consistente popup styling.
    # Alle popups gebruiken dezelfde font size, button grootte en kleuren als het main screen.
    # BELANGRIJK: Gebruik ALTIJD deze helpers, nooit hardcoded waardes zoals dp(35) of dp(14).

    def _create_popup_label(self, text: str, bold: bool = False, size_hint_x: float = None,
                            halign: str = 'left', valign: str = 'middle') -> Label:
        """
        Maak een gestylde label voor gebruik in popups.
        Gebruikt ui_font_size en background_font_color voor consistentie.

        Args:
            text: Label tekst
            bold: True voor vette tekst
            size_hint_x: Breedte hint (None = auto)
            halign: Horizontale uitlijning
            valign: Verticale uitlijning

        Returns:
            Label met consistente styling
        """
        display_text = f'[b]{text}[/b]' if bold else text
        label = Label(
            text=display_text,
            markup=bold,  # Alleen markup aanzetten als bold nodig is
            font_size=self.ui_font_size,
            color=self.custom['background_font_color'],
            halign=halign,
            valign=valign,
        )
        if size_hint_x is not None:
            label.size_hint_x = size_hint_x
        # Bind text_size voor correcte uitlijning
        label.bind(size=lambda *x: setattr(label, 'text_size', label.size))
        return label

    def _create_popup_text_input(self, text: str = '', multiline: bool = False,
                                  readonly: bool = False) -> TextInput:
        """
        Maak een gestylde text input voor gebruik in popups.
        Transparante achtergrond, font size en padding consistent met rest van UI.

        Args:
            text: Initiële tekst
            multiline: True voor meerdere regels
            readonly: True voor alleen-lezen

        Returns:
            TextInput met consistente styling
        """
        # Padding voor visuele centrering van tekst in de row
        # ui_bar_height = font_size * 2.5, dus voor centrering:
        # v_pad = (bar_height - font_size) / 2 ≈ font_size * 0.75
        # Maar tekst heeft ook line height, dus iets minder: 0.5
        h_pad = dp(8)
        v_pad = self.ui_font_size * 0.5
        return TextInput(
            text=str(text) if text else '',
            multiline=multiline,
            readonly=readonly,
            background_color=(0, 0, 0, 0),  # Transparant
            background_normal='',
            background_active='',
            foreground_color=(0, 0, 0, 1),  # Zwarte tekst
            font_size=self.ui_font_size,
            padding=[h_pad, v_pad, h_pad, v_pad],
            size_hint=(1, 1),
            pos_hint={'x': 0, 'y': 0},
        )

    def _create_form_row(self, height_multiplier: float = 1.0, spacing: int = 10) -> BoxLayout:
        """
        Maak een form row voor settings/dialogen.
        Hoogte is gebaseerd op ui_bar_height voor consistentie.

        Args:
            height_multiplier: Vermenigvuldiger voor hoogte (bijv. 4.0 voor textarea)
            spacing: Ruimte tussen elementen

        Returns:
            BoxLayout met correcte hoogte
        """
        return BoxLayout(
            size_hint_y=None,
            height=self.ui_bar_height * height_multiplier,
            spacing=dp(spacing),
        )

    def _create_popup_button(self, text: str, danger: bool = False) -> 'ColoredButton':
        """
        Maak een gestylde button voor gebruik in popups.
        Gebruikt dezelfde styling als buttons in het main screen.

        Args:
            text: Button tekst
            danger: True voor rode (delete/danger) buttons

        Returns:
            ColoredButton met consistente styling
        """
        bg_color = (1, 0.3, 0.3, 1) if danger else self.custom['button_color']
        return ColoredButton(
            text=text,
            bg_color=bg_color,
            rounded=self.custom['rounded_corners'],
            color=self.custom['button_font_color'],
            font_size=self.ui_font_size,
        )

    def _create_popup_button_row(self, spacing: int = 10) -> BoxLayout:
        """
        Maak een button row voor onderaan popups.
        Hoogte is gebaseerd op ui_bar_height voor consistentie.

        Returns:
            BoxLayout met correcte hoogte voor popup buttons
        """
        return BoxLayout(
            size_hint_y=None,
            height=self.ui_bar_height,
            spacing=dp(spacing),
        )

    def _style_filechooser(self, filechooser):
        """
        Style een FileChooserListView consistent met de huisstijl.
        - Alle tekst in background_font_color (niet wit)
        - Font size consistent met ui_font_size
        - Header "Name" hernoemd naar "Folder"
        - Header "Size" verborgen

        BELANGRIJK: Styled alleen FileChooser widgets, NIET ColoredButton of andere
        popup elementen die hun eigen styling hebben.

        De styling wordt meerdere keren toegepast omdat FileChooser widgets
        dynamisch worden aangemaakt en soms pas later beschikbaar zijn.
        Bindings op path en files zorgen ervoor dat ook bij navigatie
        de styling opnieuw wordt toegepast.

        Args:
            filechooser: FileChooserListView instance
        """
        text_color = self.custom['background_font_color']
        font_size = self.ui_font_size

        def apply_style(*args):
            # Loop door filechooser children en style alle tekst-widgets
            # BEHALVE ColoredButton (die hebben hun eigen styling via _create_popup_button)
            for child in filechooser.walk():
                child_class_name = child.__class__.__name__
                # Skip onze eigen ColoredButton class
                if child_class_name == 'ColoredButton':
                    continue
                # Style alle widgets met color attribuut (Labels, FileChooserListLayout entries, etc.)
                # Dit vangt zowel Label widgets als FileChooserListEntry items
                if hasattr(child, 'color') and hasattr(child, 'text'):
                    child.color = text_color
                if hasattr(child, 'font_size'):
                    child.font_size = font_size
                # Hernoem "Name" naar "Folder" en verberg "Size"
                if hasattr(child, 'text'):
                    if child.text == 'Name':
                        child.text = 'Folder'
                    elif child.text == 'Size':
                        child.text = ''
                        if hasattr(child, 'width'):
                            child.width = 0
                            child.size_hint_x = 0

        # Schedule styling meerdere keren om late-created widgets te vangen
        # FileChooser maakt lijst-items vaak pas iets later aan
        Clock.schedule_once(apply_style, 0.05)
        Clock.schedule_once(apply_style, 0.15)
        Clock.schedule_once(apply_style, 0.3)

        # Re-apply styling bij path changes (navigatie naar andere folder)
        filechooser.bind(path=lambda *x: Clock.schedule_once(apply_style, 0.1))
        # Re-apply styling wanneer de files lijst verandert (ook bij refresh)
        filechooser.bind(files=lambda *x: Clock.schedule_once(apply_style, 0.1))

    def _create_popup(self, title: str, content, size_hint: tuple = (0.8, 0.8)) -> Popup:
        """
        Maak een popup met consistente styling.
        Titel is bold, kleuren uit huisstijl, geen grijze Kivy border.

        Args:
            title: Popup titel (wordt automatisch bold)
            content: Popup content widget
            size_hint: Grootte relatief aan scherm

        Returns:
            Popup met consistente styling
        """
        popup = Popup(
            title=title,
            title_size=self.ui_font_size,
            content=content,
            size_hint=size_hint,
            title_color=self.custom['background_font_color'],
            separator_height=0,
            background_color=self.custom['background_color'],
            background='',  # Verwijder standaard grijze Kivy border
        )
        # Bold titel: Kivy Popup heeft geen markup parameter, dus we zetten het
        # op de interne title label nadat de popup is aangemaakt
        # De title label is toegankelijk via popup.children[0].children[1] (of via _container)
        def enable_bold_title(*args):
            try:
                # Zoek de title label in de popup structuur
                for child in popup.walk():
                    if hasattr(child, 'text') and child.text == title:
                        child.bold = True
                        child.font_size = self.ui_font_size
                        break
            except Exception:
                pass  # Silently fail als structuur anders is
        Clock.schedule_once(enable_bold_title, 0)
        return popup

    def _show_error(self, message: str):
        """Show error popup."""
        label = self._create_popup_label(message, halign='center', valign='middle')
        popup = self._create_popup('Error', label, size_hint=(0.6, 0.3))
        popup.open()

    def _on_info_click(self, instance):
        """Handle info button click - show about.txt."""
        self._show_about()

    def _show_about(self):
        """Show about.txt content in a popup with background color and font color."""
        about_path = self._app_path / 'resources' / 'about.txt'
        if not about_path.exists():
            about_path = self._app_path / 'about.txt'

        if about_path.exists():
            try:
                content = about_path.read_text(encoding='utf-8')
            except Exception:
                content = "Could not read about.txt"
        else:
            content = "About file not found."

        # Create content layout with background color
        content_layout = BoxLayout(orientation='vertical', padding=dp(10))
        with content_layout.canvas.before:
            Color(*self.custom['background_color'])
            self._about_bg = Rectangle(pos=content_layout.pos, size=content_layout.size)
        content_layout.bind(
            pos=lambda *x: setattr(self._about_bg, 'pos', content_layout.pos),
            size=lambda *x: setattr(self._about_bg, 'size', content_layout.size)
        )

        # Create scrollable label for about content
        # Scrollbar styling: dikte en zichtbaarheid uit customize settings
        scrollbar_always = self.custom['scrollbar_always_visible']
        use_rounded_scrollbar = self.custom['rounded_corners']
        scroll = RoundedScrollView(
            rounded=use_rounded_scrollbar,
            bar_color_override=self.custom['button_color'],
            size_hint=(1, 1),
            bar_width=dp(self.custom['scrollbar_width']),
            scroll_type=['bars', 'content'],
            always_visible=scrollbar_always,
        )
        # Label met speciale bindings voor scrollbare content
        label = self._create_popup_label(content, halign='left', valign='top')
        label.size_hint_y = None  # Nodig voor scrollbare content
        label.bind(texture_size=lambda *x: setattr(label, 'height', label.texture_size[1]))
        label.bind(width=lambda *x: setattr(label, 'text_size', (label.width - dp(20), None)))
        scroll.add_widget(label)
        content_layout.add_widget(scroll)

        popup = self._create_popup('About Libiry', content_layout, size_hint=(0.8, 0.8))
        popup.open()

    def _on_gear_click(self, instance):
        """Handle gear button click - show settings."""
        self._show_settings()

    def _show_settings(self):
        """Show settings popup for editing customize.txt and selected types.txt."""
        from kivy.uix.textinput import TextInput

        # Main content layout
        content_layout = BoxLayout(orientation='vertical', padding=dp(10), spacing=dp(10))
        with content_layout.canvas.before:
            Color(*self.custom['background_color'])
            self._settings_bg = Rectangle(pos=content_layout.pos, size=content_layout.size)
        content_layout.bind(
            pos=lambda *x: setattr(self._settings_bg, 'pos', content_layout.pos),
            size=lambda *x: setattr(self._settings_bg, 'size', content_layout.size)
        )

        # Scrollable form
        # Scrollbar styling: dikte en zichtbaarheid uit customize settings
        scrollbar_always = self.custom['scrollbar_always_visible']
        use_rounded_scrollbar = self.custom['rounded_corners']
        scroll = RoundedScrollView(
            rounded=use_rounded_scrollbar,
            bar_color_override=self.custom['button_color'],
            size_hint=(1, 1),
            bar_width=dp(self.custom['scrollbar_width']),
            scroll_type=['bars', 'content'],
            always_visible=scrollbar_always,
        )
        form = BoxLayout(orientation='vertical', size_hint_y=None, spacing=dp(8), padding=dp(5))
        form.bind(minimum_height=form.setter('height'))

        # Store references to input fields for saving
        self._settings_inputs = {}

        # Haal rounded setting op voor consistente styling
        use_rounded = self.custom['rounded_corners']

        def add_field(label_text, key, value, is_color=False):
            """Add a labeled input field to the form with rounded background."""
            row = self._create_form_row()
            label = self._create_popup_label(label_text, size_hint_x=0.4)
            row.add_widget(label)

            # Container met rounded achtergrond (zoals SearchBox)
            input_container = RelativeLayout(size_hint_x=0.6)

            # Achtergrond widget
            bg_widget = RoundedBackground(
                bg_color=(1, 1, 1, 1),
                rounded=use_rounded,
                size_hint=(1, 1),
                pos_hint={'x': 0, 'y': 0},
            )
            input_container.add_widget(bg_widget)

            # Transparante text input met consistente styling
            text_input = self._create_popup_text_input(value)
            input_container.add_widget(text_input)

            row.add_widget(input_container)
            form.add_widget(row)
            self._settings_inputs[key] = text_input

        def add_location_field(label_text, key, value):
            """Add a location field with browse button, both in one rounded container."""
            row = self._create_form_row()
            label = self._create_popup_label(label_text, size_hint_x=0.4)
            row.add_widget(label)

            # Outer container voor text input + browse button
            outer_container = RelativeLayout(size_hint_x=0.6)

            # Witte achtergrond alleen voor text input (linkerhoeken rond)
            input_bg_radius = [dp(5), 0, 0, dp(5)] if use_rounded else None
            bg_widget = RoundedBackground(
                bg_color=(1, 1, 1, 1),
                rounded=False,
                radius=input_bg_radius,
                size_hint=(0.75, 1),
                pos_hint={'x': 0, 'y': 0},
            )
            outer_container.add_widget(bg_widget)

            # Inner BoxLayout voor text input + button (geen spacing, strak tegen elkaar)
            inner_container = BoxLayout(
                spacing=0,
                size_hint=(1, 1),
                pos_hint={'x': 0, 'y': 0},
            )

            # Transparante text input met consistente styling
            text_input = self._create_popup_text_input(value)
            text_input.size_hint_x = 0.75
            inner_container.add_widget(text_input)

            def on_browse(instance):
                from plyer import filechooser
                try:
                    selection = filechooser.choose_dir(title="Select default folder")
                    if selection:
                        text_input.text = selection[0]
                except Exception:
                    pass

            # Browse button met aubergine achtergrond en witte tekst
            # Alleen rechterhoeken rond (als rounded_corners aan staat)
            btn_radius = [0, dp(5), dp(5), 0] if use_rounded else [0, 0, 0, 0]
            browse_btn = ColoredButton(
                text='...',
                size_hint_x=0.25,
                bg_color=self.custom['button_color'],
                radius=btn_radius,
                color=self.custom['button_font_color'],
                font_size=self.ui_font_size,
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

        def add_yn_field(label_text, key, value):
            """Add a Y/N checkbox field with styled checkbox."""
            row = self._create_form_row()
            label = self._create_popup_label(label_text, size_hint_x=0.4)
            row.add_widget(label)

            checkbox_container = BoxLayout(size_hint_x=0.6)
            # StyledCheckBox: witte box met zwarte checkmark
            checkbox = StyledCheckBox(active=value, rounded=use_rounded)
            checkbox_container.add_widget(checkbox)
            checkbox_container.add_widget(BoxLayout())  # spacer
            row.add_widget(checkbox_container)
            form.add_widget(row)
            self._settings_inputs[key] = checkbox

        def add_section_header(text):
            """Add a section header, left-aligned."""
            header = self._create_popup_label(text, bold=True)
            header.size_hint_y = None
            header.height = self.ui_bar_height
            form.add_widget(header)

        # === SELECTED FILE TYPES === (bovenaan voor snelle toegang)
        add_section_header('Selected File Types')
        types_str = '\n'.join(sorted(self.selected_types)) if self.selected_types else ''
        # Textarea row is 4x normale hoogte
        types_row = self._create_form_row(height_multiplier=4.0)
        types_label = self._create_popup_label('One per line', size_hint_x=0.4, valign='top')
        types_row.add_widget(types_label)

        # Container met rounded achtergrond voor types input
        types_container = RelativeLayout(size_hint_x=0.6)

        types_bg = RoundedBackground(
            bg_color=(1, 1, 1, 1),
            rounded=use_rounded,
            size_hint=(1, 1),
            pos_hint={'x': 0, 'y': 0},
        )
        types_container.add_widget(types_bg)

        types_input = self._create_popup_text_input(types_str, multiline=True)
        types_container.add_widget(types_input)
        types_row.add_widget(types_container)
        form.add_widget(types_row)
        self._settings_inputs['selected_types'] = types_input

        # === APPEARANCE SETTINGS ===
        add_section_header('Appearance')
        add_location_field('Start location', 'location', self.custom.get('location', ''))
        add_field('Background color', 'background_color_hex', self._color_to_hex(self.custom['background_color']))
        add_field('Button color', 'button_color_hex', self._color_to_hex(self.custom['button_color']))
        add_field('Button font color', 'button_font_color_hex', self._color_to_hex(self.custom['button_font_color']))
        add_field('Search box color', 'search_box_color_hex', self._color_to_hex(self.custom['search_box_color']))
        add_field('Search box font color', 'search_box_font_color_hex', self._color_to_hex(self.custom['search_box_font_color']))
        add_field('Tile font color', 'tile_font_color_hex', self._color_to_hex(self.custom['tile_font_color']))
        add_field('Background font color', 'background_font_color_hex', self._color_to_hex(self.custom['background_font_color']))
        add_field('Font size', 'ui_font_size', str(self.custom.get('ui_font_size', 12)))
        add_field('Scrollbar width', 'scrollbar_width', str(self.custom.get('scrollbar_width', 10)))
        add_yn_field('Scrollbar always visible', 'scrollbar_always_visible', self.custom.get('scrollbar_always_visible', True))
        add_yn_field('Show book title', 'show_book_title', self.custom.get('show_book_title', False))
        add_yn_field('Rounded corners', 'rounded_corners', self.custom['rounded_corners'])
        add_yn_field('Only selected file types', 'only_selected_types', self.custom['only_selected_types'])
        add_yn_field('Fuzzy search', 'fuzzy_search', self.custom.get('fuzzy_search', False))

        # === FIELD NAME SETTINGS ===
        add_section_header('Field Names')
        add_field('Cover', 'field_cover', self.custom.get('field_cover', 'cover'))
        add_field('Booktitle', 'field_booktitle', self.custom.get('field_booktitle', 'booktitle'))
        add_field('Author', 'field_author', self.custom.get('field_author', 'author'))
        add_field('ISBN', 'field_isbn', self.custom.get('field_isbn', 'isbn'))
        add_field('Tags', 'field_tags', self.custom.get('field_tags', 'tags'))

        scroll.add_widget(form)
        content_layout.add_widget(scroll)

        # Button row met helpers voor consistente styling
        btn_row = self._create_popup_button_row()
        btn_cancel = self._create_popup_button('Cancel')
        btn_save = self._create_popup_button('Save')

        btn_row.add_widget(btn_cancel)
        btn_row.add_widget(btn_save)
        content_layout.add_widget(btn_row)

        popup = self._create_popup('Settings', content_layout, size_hint=(0.85, 0.9))

        def on_save(instance):
            self._save_settings()
            # Toon melding dat wijzigingen pas na herstart actief worden
            # Settings popup blijft open zodat gebruiker verder kan werken
            info_label = self._create_popup_label(
                'Your changes will become effective after restart.',
                halign='center',
                valign='middle',
            )
            info_popup = self._create_popup('Settings saved', info_label, size_hint=(0.6, 0.3))
            # Achtergrondkleur voor de popup content
            with info_popup.content.canvas.before:
                Color(*self.custom['background_color'])
                info_popup._info_bg = Rectangle(pos=info_popup.content.pos, size=info_popup.content.size)
            info_popup.content.bind(
                pos=lambda *x: setattr(info_popup._info_bg, 'pos', info_popup.content.pos),
                size=lambda *x: setattr(info_popup._info_bg, 'size', info_popup.content.size)
            )
            info_popup.open()

        btn_cancel.bind(on_release=lambda x: popup.dismiss())
        btn_save.bind(on_release=on_save)
        popup.open()

    def _color_to_hex(self, color):
        """Convert RGBA tuple to hex string or named color.

        Als de kleur overeenkomt met een bekende kleurnaam, toon die naam
        zodat gebruikers weten dat ze ook kleurnamen kunnen invoeren.
        """
        if isinstance(color, str):
            return color

        # Bekende kleuren: tuple -> naam mapping
        # Vergelijk met kleine tolerantie voor floating point
        named_colors = {
            (1, 1, 1): 'white',
            (0, 0, 0): 'black',
            (1, 0, 0): 'red',
            (0, 1, 0): 'green',
            (0, 0, 1): 'blue',
            (0.5, 0.5, 0.5): 'gray',
            (0.5, 0, 0.5): 'purple',
            (0.8, 0.6, 0.8): 'lila',
        }

        # Check of kleur (afgerond) overeenkomt met bekende kleur
        r, g, b = round(color[0], 2), round(color[1], 2), round(color[2], 2)
        for known_rgb, name in named_colors.items():
            if (abs(r - known_rgb[0]) < 0.05 and
                abs(g - known_rgb[1]) < 0.05 and
                abs(b - known_rgb[2]) < 0.05):
                return name

        # Geen bekende kleur, gebruik hex
        r_int, g_int, b_int = int(color[0] * 255), int(color[1] * 255), int(color[2] * 255)
        return f'#{r_int:02X}{g_int:02X}{b_int:02X}'

    def _save_settings(self):
        """Save settings to customize.txt and selected types.txt."""
        inputs = self._settings_inputs

        # Build customize.txt content
        lines = []
        lines.append(f"Location: {inputs['location'].text}")
        lines.append(f"Background color: {inputs['background_color_hex'].text}")
        lines.append(f"Button color: {inputs['button_color_hex'].text}")
        lines.append(f"Button font color: {inputs['button_font_color_hex'].text}")
        lines.append(f"Search box color: {inputs['search_box_color_hex'].text}")
        lines.append(f"Tile font color: {inputs['tile_font_color_hex'].text}")
        lines.append(f"Background font color: {inputs['background_font_color_hex'].text}")
        lines.append(f"Search box font color: {inputs['search_box_font_color_hex'].text}")
        lines.append(f"Rounded corners y/n: {'Y' if inputs['rounded_corners'].active else 'N'}")
        lines.append(f"Only selected file types y/n: {'Y' if inputs['only_selected_types'].active else 'N'}")
        lines.append(f"Fuzzy search y/n: {'Y' if inputs['fuzzy_search'].active else 'N'}")
        lines.append(f"Scrollbar width: {inputs['scrollbar_width'].text}")
        lines.append(f"Scrollbar always visible y/n: {'Y' if inputs['scrollbar_always_visible'].active else 'N'}")
        lines.append(f"Show book title y/n: {'Y' if inputs['show_book_title'].active else 'N'}")
        lines.append(f"Font size: {inputs['ui_font_size'].text}")
        lines.append("")
        lines.append("# Configurable field names")
        lines.append(f"Field name cover: {inputs['field_cover'].text}")
        lines.append(f"Field name booktitle: {inputs['field_booktitle'].text}")
        lines.append(f"Field name author: {inputs['field_author'].text}")
        lines.append(f"Field name isbn: {inputs['field_isbn'].text}")
        lines.append(f"Field name tags: {inputs['field_tags'].text}")

        # Write customize.txt
        customize_path = self._app_path / 'customize' / 'customize.txt'
        try:
            customize_path.parent.mkdir(parents=True, exist_ok=True)
            customize_path.write_text('\n'.join(lines), encoding='utf-8')
        except Exception as e:
            self._show_error(f"Could not save customize.txt: {e}")
            return

        # Write selected types.txt
        types_path = self._app_path / 'customize' / 'selected types.txt'
        types_text = inputs['selected_types'].text.strip()
        types_lines = [t.strip() for t in types_text.split('\n') if t.strip()]
        try:
            types_path.write_text('\n'.join(types_lines) + '\n', encoding='utf-8')
        except Exception as e:
            self._show_error(f"Could not save selected types.txt: {e}")
            return

        # Settings worden pas na restart actief, dus geen reload nodig
        # (reload tijdens runtime kan crashes veroorzaken door format mismatches)

    def _load_settings(self):
        """Load saved settings.

        Folder location logica (prioriteit hoog naar laag):
        1. Location uit customize/customize.txt
        2. Location uit resources/customize.txt (alleen als customize leeg)
        3. Laatst gebruikte folder uit settings.json
        4. Huidige werkdirectory
        Als de gekozen folder niet bestaat, gebruik huidige werkdirectory.
        """
        start_path = None

        # Stap 1+2: Location uit customize.txt (customize heeft al voorrang boven resources)
        if self.custom['location']:
            loc = Path(self.custom['location'])
            if loc.exists() and loc.is_dir():
                start_path = loc

        # Stap 3: Laatst gebruikte folder uit settings.json
        if not start_path:
            try:
                if self.store.exists('last_path'):
                    last_path = self.store.get('last_path')['value']
                    if last_path and Path(last_path).exists():
                        start_path = Path(last_path)
            except Exception as e:
                print(f"Error loading settings: {e}")

        # Stap 4: Fallback naar huidige werkdirectory
        if not start_path:
            cwd = Path.cwd()
            if cwd.exists() and cwd.is_dir():
                start_path = cwd

        # Extra check: als gekozen pad niet (meer) bestaat, gebruik huidige werkdirectory
        if start_path and not start_path.exists():
            start_path = Path.cwd()

        try:
            if self.store.exists('zoom_level'):
                self._zoom_level = self.store.get('zoom_level')['value']
        except Exception:
            pass

        if start_path:
            Clock.schedule_once(lambda dt: self.navigate_to(start_path, add_to_history=False), 0.5)

    def _save_session_state(self):
        """Save session state (last path, zoom level) to JsonStore.

        Note: Dit is APART van _save_settings() die customize.txt en selected types.txt opslaat.
        Deze functie slaat alleen de runtime session state op naar ~/.libiry/settings.json.
        """
        try:
            Path.home().joinpath(".libiry").mkdir(parents=True, exist_ok=True)
            if self._current_folder:
                self.store.put('last_path', value=str(self._current_folder))
            self.store.put('zoom_level', value=self._zoom_level)
        except Exception as e:
            print(f"Error saving session state: {e}")

    def _set_windows_icon(self, icon_path):
        """Set Windows taskbar icon using Windows API."""
        try:
            import ctypes
            from ctypes import wintypes

            # Normalize path and convert to absolute path
            icon_path = str(Path(icon_path).resolve())

            if not Path(icon_path).exists():
                print(f"Icon file not found: {icon_path}")
                return

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
                # Get window handle - try multiple methods
                hwnd = user32.GetActiveWindow()
                if not hwnd:
                    hwnd = user32.GetForegroundWindow()
                if not hwnd:
                    # Try to find by window class (Kivy uses SDL)
                    hwnd = user32.FindWindowW('SDL_app', None)
                if not hwnd:
                    # Try to find by window title
                    hwnd = user32.FindWindowW(None, 'Libiry')

                if hwnd:
                    # Set icon for both small (title bar) and big (taskbar) icons
                    WM_SETICON = 0x0080
                    ICON_SMALL = 0
                    ICON_BIG = 1

                    user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT,
                                                    wintypes.WPARAM, wintypes.LPARAM]
                    user32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, hicon)
                    user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, hicon)
                else:
                    print("Could not find window handle for icon")
            else:
                error_code = ctypes.get_last_error()
                print(f"Could not load icon from {icon_path}, error: {error_code}")
        except Exception as e:
            print(f"Could not set Windows taskbar icon: {e}")

    def on_stop(self):
        """Handle app stop."""
        self._save_session_state()


def clear_cache():
    """Clear the entire Libiry cache folder.

    Wordt aangeroepen bij opstartproblemen om corrupte cache te verwijderen.
    """
    cache_dir = Path.home() / '.libiry' / 'cache'
    if cache_dir.exists():
        try:
            shutil.rmtree(cache_dir)
            print(f"Cache cleared: {cache_dir}")
        except Exception as e:
            print(f"Error clearing cache: {e}")


def main():
    """Main entry point.

    Bij opstartproblemen wordt de cache automatisch geleegd en
    de app opnieuw gestart.
    """
    try:
        LibiryApp().run()
    except Exception as e:
        print(f"Startup error: {e}")
        print("Clearing cache and restarting...")
        clear_cache()
        # Probeer opnieuw te starten na cache legen
        try:
            LibiryApp().run()
        except Exception as e2:
            print(f"Failed to restart after cache clear: {e2}")
            raise


if __name__ == '__main__':
    main()
