"""
Libiry - A cross-platform ebook library viewer.

Supports Windows, Linux, macOS, Android, and iOS.
"""

import sys
import re
import shutil
import os
import tempfile
import webbrowser
from pathlib import Path
from functools import partial
from datetime import datetime

# Probeer send2trash te importeren voor prullenbak support
# Als niet beschikbaar, gebruik dan permanente verwijdering als fallback
try:
    from send2trash import send2trash
    HAS_SEND2TRASH = True
except ImportError:
    HAS_SEND2TRASH = False

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

# Gedeelde functies uit core module
from core.libiry_style import load_field_names, load_selected_types as _load_selected_types_impl

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
from kivy.graphics import Color, Rectangle, RoundedRectangle, Triangle, Line
from kivy.metrics import dp
from kivy.storage.jsonstore import JsonStore
from threading import Thread
from PIL import Image as PILImage

from core.cover_cache import CoverCache
from core.cover_extractor import CoverExtractor
from core.file_opener import open_in_default_app
from core.file_cache import FileCache, CachedFileMetadata
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
    """Load selected file types from selected types.txt.

    Gebruikt de gedeelde implementatie uit core/libiry_style.py.
    Valt terug op DEFAULT_FORMATS als geen types gevonden.
    """
    types = _load_selected_types_impl(app_path)
    return types if types else DEFAULT_FORMATS


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
        'fuzzy_search': False,  # Default off - exact substring match
        'metadata_in_sidecar': False,  # Default off - keep metadata in book files when possible
        'scrollbar_width': 10,  # Scrollbar thickness in dp
        'scrollbar_always_visible': True,  # Scrollbar altijd zichtbaar
        'show_book_title': False,  # Toon titel/auteur op covers met afbeelding
        'show_tags': False,  # Toon tag lijst onderaan scherm (standaard uit)
        'ui_font_size': 12,  # Font size voor UI-elementen (knoppen, labels, etc.)
        # multi_book_markdown setting verwijderd - detectie is nu automatisch via file_cache
        # Configurable field names for markdown parsing
        'field_names': {},
    }

    # Eerst resources (defaults), dan customize (gebruikersinstellingen overschrijven defaults)
    for folder in ['resources', 'customize']:
        config_path = app_path / folder / 'customize.txt'
        if config_path.exists():
            try:
                content = config_path.read_text(encoding='utf-8')
                for line in content.split('\n'):
                    if ':' in line:
                        key, value = line.split(':', 1)
                        key = key.strip().lower()
                        value = value.strip()

                        # Location: alleen overschrijven als waarde niet leeg is
                        if key == 'location' and value:
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
                        elif key == 'store metadata in sidecar y/n' and value:
                            settings['metadata_in_sidecar'] = value.lower() == 'y'
                        elif key == 'scrollbar width' and value:
                            try:
                                settings['scrollbar_width'] = int(value)
                            except ValueError:
                                pass
                        elif key == 'scrollbar always visible y/n' and value:
                            settings['scrollbar_always_visible'] = value.lower() != 'n'
                        elif key == 'show book title y/n' and value:
                            settings['show_book_title'] = value.lower() == 'y'
                        elif key == 'show tags y/n' and value:
                            settings['show_tags'] = value.lower() == 'y'
                        # multi-book markdown y/n: verwijderd - detectie is nu automatisch via file_cache
                        elif key in ('font size', 'ui font size') and value:  # ui font size voor backwards compatibility
                            try:
                                settings['ui_font_size'] = int(value)
                            except ValueError:
                                pass
                # Geen break - beide bestanden moeten gelezen worden
                # (resources eerst voor defaults, customize daarna voor user overrides)
            except Exception as e:
                print(f"Error loading customization: {e}")

    # Field names via gedeelde functie uit core/libiry_style.py
    settings['field_names'] = load_field_names(app_path)

    return settings


def is_dark_mode(background_color: tuple) -> bool:
    """Detect dark mode based on background color luminance.

    Uses relative luminance formula: 0.299*R + 0.587*G + 0.114*B
    Returns True if luminance < 0.5 (dark background).
    """
    if not background_color or len(background_color) < 3:
        return False
    r, g, b = background_color[:3]
    luminance = 0.299 * r + 0.587 * g + 0.114 * b
    return luminance < 0.5


def get_icon_path(app_path: Path, icon_name: str, dark_mode: bool = False) -> str:
    """Get icon path, preferring customize folder over resources.

    Args:
        app_path: Base application path
        icon_name: Name of the icon file (e.g., 'back.png')
        dark_mode: If True, look in iconsdarkmode folder instead of icons
    """
    # Customize folder has priority (no dark mode variant for custom icons)
    customize_path = app_path / 'customize' / icon_name
    if customize_path.exists():
        return str(customize_path)

    # Use iconsdarkmode folder in dark mode, otherwise icons folder
    icons_folder = 'iconsdarkmode' if dark_mode else 'icons'
    resources_path = app_path / 'resources' / icons_folder / icon_name
    if resources_path.exists():
        return str(resources_path)

    # Fallback to regular icons folder if dark mode icon not found
    if dark_mode:
        fallback_path = app_path / 'resources' / 'icons' / icon_name
        if fallback_path.exists():
            return str(fallback_path)

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
        # Padding schaalt mee met font size voor verticale centrering
        h_pad = dp(10)  # Horizontale padding links
        v_pad = self._font_size * 0.5  # Verticale padding voor betere centrering
        icon_size = self._font_size * 1.7
        # Rechts padding = icon breedte + zelfde marge als verticaal
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

        # Search icon (magnifying glass) - rechts met zelfde marge als boven/onder
        # v_pad wordt gebruikt voor consistente spacing aan alle kanten
        search_icon = get_icon_path(app_path, 'search.png')
        if search_icon:
            self.search_img = Image(
                source=search_icon,
                size_hint=(None, None),
                size=(icon_size, icon_size),
            )
            # Bind positie aan parent size voor absolute positionering
            def update_icon_pos(instance, value):
                # Positie: rechts met v_pad marge, verticaal gecentreerd
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
            # Image vult tile volledig - center crop wordt gedaan bij thumbnail creatie
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

        # Tags zijn case-sensitive
        tags_stripped = [tag.strip() for tag in self.tags]

        # Determine triangle color based on tags (summary prevails over analog)
        if 'summary' in tags_stripped:
            triangle_color = (1, 0, 0, 1)  # Red for summary
        elif 'analog' in tags_stripped:
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
        # Pop active voordat we super() aanroepen, maar wijs het pas daarna toe
        # Dit voorkomt problemen met ObjectProperty initialisatie
        initial_active = kwargs.pop('active', False)
        super().__init__(**kwargs)
        self._rounded = rounded
        self.size_hint = (None, None)
        self.size = (dp(24), dp(24))
        self.bind(pos=self._update, size=self._update, active=self._update)
        # Zet active NA binding, zodat _update wordt aangeroepen
        self.active = initial_active
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
                # Teken checkmark met twee lijnen
                cx, cy = self.pos[0] + self.size[0] / 2, self.pos[1] + self.size[1] / 2
                # Checkmark punten: links-midden -> onder-midden -> rechts-boven
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
        # Minimale hoogte is 3x de breedte (huisstijl)
        bar_width = self.bar_width
        viewport_ratio = self.height / self.viewport_size[1]
        bar_height = max(bar_width * 3, viewport_ratio * self.height)

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
        # Cache NIET legen bij opstarten - dit vertraagt startup enorm
        # en maakt caching nutteloos
        # Pass configured field names to extractors
        field_names = self.custom.get('field_names', {})
        self.extractor = CoverExtractor(field_names=field_names)
        self.metadata_extractor = MetadataExtractor(field_names=field_names)

        # Persistente file metadata cache - vervangt de session-only _tag_cache
        # Slaat metadata per boek op, waardoor multi-book detectie automatisch is
        # en tag filtering instant werkt zonder file I/O
        self.file_cache = FileCache(self.CACHE_DIR)

        # Settings storage
        settings_dir = Path.home() / ".libiry"
        settings_dir.mkdir(parents=True, exist_ok=True)
        self.store = JsonStore(str(settings_dir / "settings.json"))

    def build(self):
        """Build the main UI."""
        self.title = 'Libiry'
        Window.bind(on_keyboard=self._on_keyboard)
        # X knop sluit app direct, zonder te wachten op lopende taken
        Window.bind(on_request_close=self._on_close_request)

        # Set window icon from resources
        icon_path = self._app_path / "resources" / "icons" / "Libiry.ico"
        if icon_path.exists():
            Window.set_icon(str(icon_path))
            # Windows taskbar icon - blijf proberen tot het lukt
            if sys.platform == 'win32':
                self._icon_path = str(icon_path)
                self._icon_set_attempts = 0
                self._try_set_windows_icon()

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

        # Tag list bar - conditioneel op basis van show_tags setting
        # Toont alle tags van zichtbare boeken, klikbaar voor filtering
        if self.custom.get('show_tags', False):
            self.tag_list_label = Label(
                text='',
                size_hint=(1, None),
                height=0,
                halign='left',
                valign='top',
                color=self.custom['background_font_color'],
                font_size=self.ui_font_size,
                padding=[0, 0],
                markup=True,
            )
            self.tag_list_label.bind(
                texture_size=lambda instance, size: setattr(instance, 'height', size[1] if instance.text else 0)
            )
            self.tag_list_label.bind(
                width=lambda instance, width: setattr(instance, 'text_size', (width, None))
            )
            self.tag_list_label.bind(on_ref_press=self._on_tag_ref_press)
            self.root.add_widget(self.tag_list_label)
        else:
            self.tag_list_label = None  # Tags verborgen via setting

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
        # Button width schaalt mee met font size - alle knoppen even breed
        btn_width = self.ui_font_size * 9

        # Show book title instelling uit settings (niet meer een knop)
        self._show_titles_active = self.custom.get('show_book_title', False)

        # Edit Tags knop - alleen zichtbaar als Show tags setting aan staat
        # Dit voorkomt verwarring als tags niet getoond worden
        self.btn_edit_tags = ColoredButton(
            text='Edit',
            size_hint_x=None,
            width=btn_width,
            bg_color=button_color,
            rounded=self.custom['rounded_corners'],
            color=self.custom['button_font_color'],
            font_size=self.ui_font_size,
            disabled=True,
        )
        self.btn_edit_tags.bind(on_release=lambda x: self._show_edit_tags_popup())
        # Voeg knop alleen toe als show_tags aan staat
        if self.custom.get('show_tags', False):
            status_bar.add_widget(self.btn_edit_tags)

        self.btn_move = ColoredButton(
            text='Move',
            size_hint_x=None,
            width=btn_width,
            bg_color=button_color,
            rounded=self.custom['rounded_corners'],
            color=self.custom['button_font_color'],
            font_size=self.ui_font_size,
            disabled=True,
        )
        self.btn_move.bind(on_release=lambda x: self._move_selected())
        status_bar.add_widget(self.btn_move)

        self.btn_delete = ColoredButton(
            text='Delete',
            size_hint_x=None,
            width=btn_width,
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
        # Icon spacing: dp(12) standaard, dp(8) rond information icon (kleinere afbeelding)
        icon_spacing = dp(12)
        icon_spacing_info = dp(8)  # Kleinere spacing voor/na information icon
        toolbar = BoxLayout(size_hint_y=None, height=self.ui_bar_height, spacing=0)
        button_color = self.custom['button_color']
        icon_size = self.ui_bar_height  # Icons schalen mee met bar height
        icon_size_small = icon_size * 0.8  # 80% grootte voor alle icons behalve twins

        # Detect dark mode based on background color luminance
        dark_mode = is_dark_mode(self.custom['background_color'])

        # Helper functie voor spacer
        def add_spacer(width=icon_spacing):
            toolbar.add_widget(BoxLayout(size_hint_x=None, width=width))

        # Helper functie voor icon met bottom-alignment (voor 80% icons)
        # Container is icon_size breed, icon zelf is icon_size_small en uitgelijnd aan onderkant
        def create_icon_container(icon_btn, small=True):
            """Wrap icon in container for bottom-alignment when using smaller icons."""
            if not small:
                return icon_btn
            # Container met volledige icon_size, icon aan onderkant uitgelijnd
            container = RelativeLayout(size_hint=(None, None), size=(icon_size, icon_size))
            icon_btn.pos_hint = {'center_x': 0.5, 'y': 0}  # Bottom-aligned
            container.add_widget(icon_btn)
            return container

        # Back button - goes to parent directory (80% size)
        back_icon = get_icon_path(self._app_path, 'back.png', dark_mode)
        if back_icon:
            self.btn_back = ImageButton(source=back_icon, size_hint=(None, None), size=(icon_size_small, icon_size_small))
            toolbar.add_widget(create_icon_container(self.btn_back))
        else:
            self.btn_back = Button(text='<', size_hint_x=None, width=icon_size, background_color=button_color, font_size=self.ui_font_size)
            toolbar.add_widget(self.btn_back)
        self.btn_back.bind(on_release=lambda x: self.go_up())
        self.btn_back.opacity = 0  # Hidden until parent exists

        add_spacer()

        # Refresh button (80% size)
        refresh_icon = get_icon_path(self._app_path, 'refresh.png', dark_mode)
        if refresh_icon:
            btn_refresh = ImageButton(source=refresh_icon, size_hint=(None, None), size=(icon_size_small, icon_size_small))
            toolbar.add_widget(create_icon_container(btn_refresh))
        else:
            btn_refresh = Button(text='Refresh', size_hint_x=None, width=icon_size * 2, background_color=button_color, font_size=self.ui_font_size)
            toolbar.add_widget(btn_refresh)
        btn_refresh.bind(on_release=lambda x: self._refresh())

        add_spacer()

        # Search box with magnifying glass icon
        self.search_box = SearchBox(
            app_path=self._app_path,
            custom=self.custom,
            font_size=self.ui_font_size,
            on_text_change=self._on_search_changed,
            size_hint=(1, 1),
        )
        toolbar.add_widget(self.search_box)

        add_spacer(icon_spacing_info)  # Kleinere spacing voor information icon

        # === TOOLBAR BUTTONS (volgorde: information, gear, bento/plus, twins) ===

        # 1. Information button (80% size)
        info_icon = get_icon_path(self._app_path, 'information.png', dark_mode)
        if not info_icon:
            info_icon = get_icon_path(self._app_path, 'information.ico', dark_mode)
        if info_icon:
            self.btn_info = ImageButton(source=info_icon, size_hint=(None, None), size=(icon_size_small, icon_size_small))
            self.btn_info.tooltip_text = 'About Libiry'
            toolbar.add_widget(create_icon_container(self.btn_info))
        else:
            self.btn_info = Button(text='i', size_hint_x=None, width=icon_size, background_color=button_color, font_size=self.ui_font_size)
            toolbar.add_widget(self.btn_info)
        self.btn_info.bind(on_release=self._on_info_click)

        add_spacer(icon_spacing_info)  # Kleinere spacing na information icon

        # 2. Settings/gear button (80% size)
        gear_icon = get_icon_path(self._app_path, 'gear.png', dark_mode)
        if gear_icon:
            self.btn_gear = ImageButton(source=gear_icon, size_hint=(None, None), size=(icon_size_small, icon_size_small))
            self.btn_gear.tooltip_text = 'Settings'
            toolbar.add_widget(create_icon_container(self.btn_gear))
        else:
            self.btn_gear = Button(text='⚙', size_hint_x=None, width=icon_size, background_color=button_color, font_size=self.ui_font_size)
            toolbar.add_widget(self.btn_gear)
        self.btn_gear.bind(on_release=self._on_gear_click)

        add_spacer()

        # 3. Support button (80% size) - opent support website
        support_icon = get_icon_path(self._app_path, 'support.png', dark_mode)
        if support_icon:
            self.btn_support = ImageButton(source=support_icon, size_hint=(None, None), size=(icon_size_small, icon_size_small))
            self.btn_support.tooltip_text = 'Support'
            toolbar.add_widget(create_icon_container(self.btn_support))
        else:
            self.btn_support = Button(text='?', size_hint_x=None, width=icon_size, background_color=button_color, font_size=self.ui_font_size)
            toolbar.add_widget(self.btn_support)
        self.btn_support.bind(on_release=lambda x: webbrowser.open('https://libiry.org/Contributing'))

        add_spacer()

        # 5. Bento button (80% size)
        plus_icon = get_icon_path(self._app_path, 'plus.png', dark_mode)
        if plus_icon:
            self.btn_bento = ImageButton(source=plus_icon, size_hint=(None, None), size=(icon_size_small, icon_size_small))
            self.btn_bento.tooltip_text = 'Libiry apps'
            toolbar.add_widget(create_icon_container(self.btn_bento))
        else:
            self.btn_bento = Button(text='+', size_hint_x=None, width=icon_size, background_color=button_color, font_size=self.ui_font_size)
            toolbar.add_widget(self.btn_bento)
        self.btn_bento.bind(on_release=lambda x: self._show_libiry_apps_popup())

        add_spacer()

        # 6. Twins filter button (rightmost) - 100% size, niet verkleind
        twins_icon = get_icon_path(self._app_path, 'twins.png', dark_mode)
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
        self._tag_list_lookup = []  # Lookup tabel voor tag indices in de tag lijst
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
        """Load folder contents into grid. Handles missing/deleted folders gracefully.

        Bij dubbelklik op folder wordt eventuele lopende laadactie direct gestopt
        door _load_version te verhogen en scheduled events te annuleren.
        """
        # Cancel eventuele lopende batch loading direct
        # Dit zorgt ervoor dat dubbelklik op folder het huidige laden stopt
        if hasattr(self, '_batch_load_event') and self._batch_load_event:
            self._batch_load_event.cancel()
            self._batch_load_event = None

        # Cancel lopende tag scan en filter batches om UI responsief te houden
        self._cancel_tag_filter_batches()

        self.grid.clear_widgets()
        self._items = []
        self._selected_items.clear()
        self._hidden_widgets = []  # Reset verborgen widgets van zoekfilter
        self.btn_edit_tags.disabled = True
        self.btn_move.disabled = True
        self.btn_delete.disabled = True
        self.btn_edit_tags.opacity = 0.5
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
        self._batch_load_event = None  # Reset scheduled event reference
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
            # Bewaar referentie naar scheduled event zodat deze geannuleerd kan worden
            # bij dubbelklik op een andere folder (zie _load_folder)
            self._batch_load_event = Clock.schedule_once(self._load_items_batch, 0)
        else:
            # Singular/plural: "1 folder" vs "2 folders", "1 file" vs "2 files"
            folder_word = "folder" if self._folder_count == 1 else "folders"
            file_word = "file" if self._file_count == 1 else "files"
            self.status_text = f"{self._folder_count} {folder_word}, {self._file_count} {file_word}"
            self.status_label.text = self.status_text
            self._pending_items = None
            self._batch_load_event = None  # Laden klaar, geen pending event meer
            # Als er geen bestanden zijn (alleen folders), update tag lijst direct
            # Anders wordt het getriggerd door _update_cover_and_metadata() na metadata load
            if self._file_count == 0:
                self._schedule_tag_list_update(force=True)

    def _add_folder_widget(self, path: Path):
        """Add a folder widget to the grid."""
        # Geen item count - dit was een grote performance bottleneck
        # omdat elke folder synchroon gescand werd
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

    def _add_file_widget(self, path: Path, tag_filter: str = None, known_tags: list = None):
        """Add a file widget to the grid.

        Args:
            path: Path to the file
            tag_filter: Niet meer gebruikt (was voor multi-book), behouden voor compatibiliteit
            known_tags: Lijst met tags die al bekend zijn (voor tag filter)
        """
        file_type = get_file_type(path)
        document_type = get_document_type(path)

        # Gebruik file_cache voor snelle metadata lookup
        cached = self.file_cache.get_or_extract(path, self.metadata_extractor)

        # Haal tags uit cache indien beschikbaar
        if cached and not known_tags:
            known_tags = cached.tags

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
            tags=known_tags if known_tags else [],
        )
        self.grid.add_widget(widget)

        Thread(target=self._load_cover_async, args=(path, widget), daemon=True).start()

    def _load_cover_async(self, path: Path, widget: CoverImage):
        """Load cover and metadata in background thread. Handles missing files gracefully."""
        try:
            # Check if file still exists before trying to load
            if not path.exists():
                return

            # Gebruik file_cache voor metadata (incl. tags) - dit is consistenter
            # en voorkomt dat tags verloren gaan bij bestanden zonder YAML frontmatter
            cached = self.file_cache.get_or_extract(path, self.metadata_extractor)
            if cached:
                # Converteer CachedFileMetadata naar BookMetadata-achtig object
                from core.metadata_extractor import BookMetadata
                metadata = BookMetadata(
                    booktitle=cached.booktitle,
                    authors=cached.authors,
                    author_sort=cached.author_sort,
                    isbn=cached.isbn,
                    rating=cached.rating,
                    publisher=cached.publisher,
                    year=cached.year,
                    publication_date=cached.publication_date,
                    language=cached.language,
                    pages=cached.pages,
                    tags=cached.tags,
                    series=cached.series,
                    series_index=cached.series_index,
                    translator=cached.translator,
                    illustrator=cached.illustrator,
                    description=cached.description,
                    notes=cached.notes,
                    cover_url=cached.cover_url,
                )
            else:
                # Fallback naar directe extractie
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

        # Schedule tag list update met debouncing
        # Elke keer dat metadata binnenkomt, reset de timer
        # De tag lijst wordt pas bijgewerkt 0.3s na de LAATSTE metadata load
        self._schedule_tag_list_update()

    def _schedule_tag_list_update(self, force: bool = False):
        """Schedule tag list update met debouncing.

        Annuleert eventuele vorige scheduled update, zodat de tag lijst
        pas wordt bijgewerkt na de laatste metadata load (+ 0.3s delay).
        Dit voorkomt onnodige updates tijdens het laden.

        Args:
            force: Als True, schedule altijd. Als False, skip als er al een
                   background tag scan bezig is (voorkomt dat covers die
                   binnenkomen de lopende scan steeds resetten).
        """
        # Skip als er al een tag scan bezig is en dit geen force update is
        # De lopende scan vindt de tags zelf, dus we hoeven niet opnieuw te starten
        if not force and hasattr(self, '_tag_scan_active') and self._tag_scan_active:
            return

        if hasattr(self, '_tag_update_event') and self._tag_update_event:
            self._tag_update_event.cancel()
        self._tag_update_event = Clock.schedule_once(
            lambda dt: self._update_tag_list(), 0.3
        )

    def _on_item_tap(self, widget):
        """Handle item tap - toggle selection.

        Als een tag filter bezig is met zoeken, wordt deze onmiddellijk gestopt
        zodat de UI direct reageert op de selectie.
        """
        # Stop lopende tag filter batches onmiddellijk bij user interactie
        self._cancel_tag_filter_batches()

        widget.is_selected = not widget.is_selected
        if widget.is_selected:
            self._selected_items.add(widget.item_path)
        else:
            self._selected_items.discard(widget.item_path)
        widget._update_rect()
        # Enable/disable Move, Delete and Edit Tags buttons based on selection
        has_selection = len(self._selected_items) > 0
        self.btn_edit_tags.disabled = not has_selection
        self.btn_move.disabled = not has_selection
        self.btn_delete.disabled = not has_selection
        self.btn_edit_tags.opacity = 1.0 if has_selection else 0.5
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

            # Singular/plural: "1 folder" vs "2 folders", "1 file" vs "2 files"
            folder_word = "folder" if self._folder_count == 1 else "folders"
            file_word = "file" if self._file_count == 1 else "files"
            folder_text = f"{self._folder_count} {folder_word}"
            if selected_folders > 0:
                folder_text += f" ({selected_folders} selected)"

            file_text = f"{self._file_count} {file_word}"
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
                    # BELANGRIJK: voor multi-book files kunnen meerdere widgets
                    # dezelfde item_path hebben. Check daarom ook is_selected.
                    tags_text = ""
                    for child in self.grid.children:
                        if hasattr(child, 'item_path') and child.item_path == str(selected_path):
                            # Check of dit de daadwerkelijk geselecteerde widget is
                            if hasattr(child, 'is_selected') and child.is_selected:
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
            # Singular/plural: "1 folder" vs "2 folders", "1 file" vs "2 files"
            folder_word = "folder" if self._folder_count == 1 else "folders"
            file_word = "file" if self._file_count == 1 else "files"
            self.status_label.text = f"{self._folder_count} {folder_word}, {self._file_count} {file_word}"

    def _update_tag_list(self):
        """Update the tag list at the bottom of the screen.

        Scant ALTIJD recursief alle bestanden in de huidige folder via de file_cache.
        Dit zorgt voor consistentie: dezelfde data wordt gebruikt voor weergave én filtering.

        De UI blijft responsief - scan loopt in background thread.
        """
        # Skip als tag list verborgen is (show_tags setting staat uit)
        if self.tag_list_label is None:
            return

        # Skip als geen folder geladen
        if not self._current_folder:
            return

        # Altijd recursief scannen via cache - dit zorgt voor consistentie
        # tussen de getoonde tags en wat de filter vindt
        self._start_background_tag_scan()

    def _start_background_tag_scan(self):
        """Start een background thread om recursief alle tags te verzamelen.

        De scan loopt in een aparte thread zodat de UI responsief blijft.
        Bij navigatie naar andere folder wordt de huidige scan geannuleerd.

        Gebruikt de file_cache voor snelle tag lookup. Bestanden die al in cache
        zitten hoeven niet opnieuw gelezen te worden. Nieuwe bestanden worden
        geëxtraheerd en in cache opgeslagen.
        """
        from threading import Thread

        # Cancel eventuele lopende scan
        self._tag_scan_version = getattr(self, '_tag_scan_version', 0) + 1
        current_version = self._tag_scan_version
        scan_folder = self._current_folder

        # Markeer dat er een scan bezig is (voorkomt dat cover loads de scan resetten)
        self._tag_scan_active = True

        # Toon "All books" meteen, daarna "Scanning..."
        # Tags worden incrementeel toegevoegd tijdens het scannen (alfabetisch gesorteerd)
        # "No tag" wordt alleen getoond als er boeken zonder tags zijn
        if self.tag_list_label:
            self.tag_list_label.text = '[ref=__all_books__][u]All books[/u][/ref], Scanning tags...'

        def scan_tags_thread():
            """Background thread die recursief tags verzamelt.

            Tags worden incrementeel getoond tijdens het scannen, alfabetisch gesorteerd.
            Dit geeft snellere feedback aan de gebruiker. Bij klik op een tag stopt
            de scan automatisch (via _tag_scan_version check).

            Gebruikt file_cache.get_or_extract() zodat bestanden die al gecached zijn
            instant geladen worden, en nieuwe bestanden automatisch gecached worden.
            """
            import time

            # Set ipv Counter - we sorteren alfabetisch, count is niet nodig
            found_tags = set()
            no_tag_count = 0  # Aantal boeken zonder tags
            MAX_TAGS = 99
            MAX_FILES = 5000  # Limiet om geheugen te sparen
            TIMEOUT_SECONDS = 30
            UPDATE_INTERVAL = 0.3  # Seconden tussen UI updates
            start_time = time.time()
            last_update_time = start_time
            truncated = False
            files_scanned = 0
            tags_changed_since_update = False

            def schedule_ui_update(is_final=False):
                """Schedule een UI update op de main thread."""
                nonlocal last_update_time, tags_changed_since_update
                if self._tag_scan_version != current_version:
                    return
                # Maak kopie voor thread-safety
                tags_copy = set(found_tags)
                no_tag_copy = no_tag_count
                truncated_copy = truncated
                Clock.schedule_once(
                    lambda dt: self._display_tag_list_alphabetic(
                        tags_copy, truncated_copy, no_tag_copy, is_final
                    ),
                    0
                )
                last_update_time = time.time()
                tags_changed_since_update = False

            try:
                all_files = []
                self._collect_files_recursive(scan_folder, all_files)

                for filepath in all_files:
                    # Check of scan geannuleerd is (navigatie naar andere folder of user klik)
                    if self._tag_scan_version != current_version:
                        return

                    # Timeout check
                    if time.time() - start_time > TIMEOUT_SECONDS:
                        truncated = True
                        break

                    # Max files check
                    files_scanned += 1
                    if files_scanned > MAX_FILES:
                        truncated = True
                        break

                    # Max tags check
                    if len(found_tags) > MAX_TAGS:
                        truncated = True
                        break

                    try:
                        # Gebruik file_cache - haalt uit cache of extraheert en cached
                        # CachedFileMetadata heeft direct tags (geen multi-book structuur)
                        cached = self.file_cache.get_or_extract(filepath, self.metadata_extractor)

                        if cached and cached.tags:
                            for tag in cached.tags:
                                if tag:
                                    tag_stripped = tag.strip()
                                    if tag_stripped not in found_tags:
                                        found_tags.add(tag_stripped)
                                        tags_changed_since_update = True
                        else:
                            # Bestand zonder tags
                            no_tag_count += 1

                    except Exception:
                        no_tag_count += 1  # Bij error tellen als "no tag"

                    # Periodieke UI update (alleen als er nieuwe tags zijn)
                    if tags_changed_since_update and time.time() - last_update_time >= UPDATE_INTERVAL:
                        schedule_ui_update(is_final=False)

            except Exception as e:
                print(f"Error in tag scan: {e}")

            # Finale UI update (alleen als scan niet geannuleerd is)
            if self._tag_scan_version == current_version:
                schedule_ui_update(is_final=True)

        # Start background thread
        Thread(target=scan_tags_thread, daemon=True).start()

    def _display_tag_list_alphabetic(self, tags: set, truncated: bool, no_tag_count: int = 0,
                                        is_final: bool = False):
        """Toon de verzamelde tags in de tag lijst, alfabetisch gesorteerd.

        Wordt incrementeel aangeroepen tijdens het scannen voor snelle feedback.

        Args:
            tags: Set met gevonden tags
            truncated: True als niet alle tags geladen zijn (timeout/max)
            no_tag_count: Aantal boeken zonder tags
            is_final: True als dit de laatste update is (scan compleet)
        """
        # Markeer scan als klaar als dit de finale update is
        if is_final:
            self._tag_scan_active = False

        if self.tag_list_label is None:
            return

        # Format: klikbare tags
        # "No tag" wordt alleen getoond als er daadwerkelijk boeken zonder tags zijn
        tag_strings = ["[ref=__all_books__][u]All books[/u][/ref]"]

        # Voeg "No tag" alleen toe als er boeken zonder tags zijn
        if no_tag_count > 0:
            tag_strings.append("[ref=__no_tag__][u]No tag[/u][/ref]")

        # Sorteer alfabetisch (case-insensitive)
        sorted_tags = sorted(tags, key=lambda x: x.lower())

        tag_strings.extend([f"[ref={tag}][u]#{tag}[/u][/ref]" for tag in sorted_tags])

        # Bij truncation of nog niet klaar: voeg indicator toe
        if truncated:
            tag_strings.append("[ref=__all_books__][u]...[/u][/ref]")
        elif not is_final:
            # Nog bezig met scannen
            tag_strings.append("Scanning...")

        self.tag_list_label.text = ", ".join(tag_strings)

    def _display_tag_list(self, tag_counter, truncated: bool, no_tag_count: int = 0):
        """Toon de verzamelde tags in de tag lijst (legacy, voor compatibiliteit).

        Args:
            tag_counter: Counter met tag -> count
            truncated: True als niet alle tags geladen zijn (timeout/max)
            no_tag_count: Aantal boeken zonder tags
        """
        # Converteer Counter naar set voor de nieuwe functie
        tags = set(tag_counter.keys()) if tag_counter else set()
        self._display_tag_list_alphabetic(tags, truncated, no_tag_count, is_final=True)

    def _cancel_tag_filter_batches(self):
        """Cancel any pending tag filter/scan batch processing.

        Wordt aangeroepen bij user interactie (selectie, knoppen) om de UI
        onmiddellijk te laten reageren in plaats van te wachten tot de
        filter/scan klaar is.
        """
        # Cancel tag filter batches
        if hasattr(self, '_tag_filter_batch_event') and self._tag_filter_batch_event:
            self._tag_filter_batch_event.cancel()
            self._tag_filter_batch_event = None
        if hasattr(self, '_no_tag_filter_batch_event') and self._no_tag_filter_batch_event:
            self._no_tag_filter_batch_event.cancel()
            self._no_tag_filter_batch_event = None
        # Cancel scheduled tag update
        if hasattr(self, '_tag_update_event') and self._tag_update_event:
            self._tag_update_event.cancel()
            self._tag_update_event = None
        # Cancel tag scan (incrementeer version zodat lopende scan stopt)
        self._tag_scan_version = getattr(self, '_tag_scan_version', 0) + 1
        self._tag_scan_active = False

    def _on_tag_ref_press(self, instance, ref_value):
        """Handle click op een tag in de tag lijst.

        De ref_value is de tag naam (zonder #). Filter op boeken met die tag.
        Speciale waarde "__all_books__" reset de tag filter of doet refresh.
        Speciale waarde "__no_tag__" filtert op boeken zonder tags.
        """
        ref = ref_value.strip()
        if not ref:
            return

        # Cancel any pending tag filter batches
        self._cancel_tag_filter_batches()

        # "All books" is speciale actie: reset tag filter of refresh
        if ref == '__all_books__':
            if self._tag_filter_active or getattr(self, '_no_tag_filter_active', False):
                # Tag filter actief: reset en laad folder opnieuw
                self._tag_filter_active = False
                self._tag_filter_tag = None
                self._tag_filter_root = None
                self._no_tag_filter_active = False
                if self._current_folder:
                    self._load_folder(self._current_folder)
            else:
                # Geen tag filter actief: doe hetzelfde als refresh knop
                self._refresh()
            return

        # "No tag" filter: toon boeken zonder tags
        if ref == '__no_tag__':
            self._no_tag_filter_active = True
            self._tag_filter_active = False
            self._tag_filter_tag = None
            self._tag_filter_root = self._current_folder
            self._apply_no_tag_filter()
            return

        # Filter op deze tag
        tag = ref
        self._no_tag_filter_active = False
        self._tag_filter_tag = tag
        self._tag_filter_active = True
        self._tag_filter_root = self._current_folder
        self._apply_tag_filter()

    def _apply_tag_filter(self):
        """Filter om boeken met de actieve tag te tonen (recursief, uit cache).

        Gebruikt file_cache voor instant lookup - geen disk I/O nodig.
        Cache wordt gevuld door background tag scan en grid opbouw.
        """
        if not self._tag_filter_tag:
            return

        tag = self._tag_filter_tag

        # Verzamel bestanden met de tag uit file_cache
        # Filter op huidige folder en subfolders
        current_folder = self._tag_filter_root or self._current_folder
        matching_files = []

        # Verzamel alle bestanden recursief
        all_files = []
        self._collect_files_recursive(current_folder, all_files)

        for filepath in all_files:
            # Gebruik get_or_extract voor consistentie met tag scan
            cached = self.file_cache.get_or_extract(filepath, self.metadata_extractor)
            if cached and cached.tags:
                # Strip voor consistente vergelijking
                cached_tags_stripped = [t.strip() for t in cached.tags if t]
                if tag in cached_tags_stripped:
                    matching_files.append(filepath)

        # Sorteer alfabetisch
        matching_files.sort(key=lambda p: p.name.lower())

        # Clear grid en toon resultaten
        self.grid.clear_widgets()
        self._selected_items.clear()
        self._hidden_widgets = []
        self._file_count = 0
        self._folder_count = 0

        if not matching_files:
            self.status_label.text = f"No books found with tag #{tag}"
            if self.tag_list_label:
                self.tag_list_label.text = '[ref=__all_books__][u]All books[/u][/ref]'
            return

        # Voeg resultaten toe in batches voor grote aantallen
        self._pending_tag_results = matching_files
        self._tag_results_index = 0
        self._add_tag_results_batch()

    def _add_tag_results_batch(self, dt=None):
        """Voeg tag filter resultaten toe aan grid in batches."""
        if not self._tag_filter_active:
            return

        BATCH_SIZE = 30
        files = self._pending_tag_results
        start_idx = self._tag_results_index
        end_idx = min(start_idx + BATCH_SIZE, len(files))

        for i in range(start_idx, end_idx):
            filepath = files[i]
            try:
                # Haal tags uit cache voor widget
                cached = self.file_cache.get(filepath)
                cached_tags = cached.tags if cached else []
                self._add_file_widget(filepath, tag_filter=self._tag_filter_tag, known_tags=cached_tags)
                self._file_count += 1
            except Exception:
                pass

        self._tag_results_index = end_idx

        # Update status
        self.status_label.text = f"{self._file_count} books with #{self._tag_filter_tag}"

        if end_idx < len(files):
            # Meer te verwerken
            Clock.schedule_once(self._add_tag_results_batch, 0)
        else:
            # Klaar
            self._pending_tag_results = None

    def _apply_no_tag_filter(self):
        """Filter om boeken ZONDER tags te tonen (recursief, uit cache).

        Gebruikt file_cache voor instant lookup - geen disk I/O nodig.
        """
        # Zoek bestanden zonder tags in cache
        current_folder = self._tag_filter_root or self._current_folder
        matching_files = []

        # Verzamel alle bestanden recursief
        all_files = []
        self._collect_files_recursive(current_folder, all_files)

        for filepath in all_files:
            # Gebruik get_or_extract voor consistentie
            cached = self.file_cache.get_or_extract(filepath, self.metadata_extractor)
            if cached:
                # Check of dit bestand geen tags heeft
                # Filter lege strings eruit voor correcte check
                real_tags = [t.strip() for t in cached.tags if t and t.strip()]
                if not real_tags:
                    matching_files.append(filepath)
            else:
                # Extractie mislukt, tel als "geen tags"
                matching_files.append(filepath)

        # Sorteer alfabetisch
        matching_files.sort(key=lambda p: p.name.lower())

        # Clear grid en toon resultaten
        self.grid.clear_widgets()
        self._selected_items.clear()
        self._hidden_widgets = []
        self._file_count = 0
        self._folder_count = 0

        if not matching_files:
            self.status_label.text = "No books without tags found"
            if self.tag_list_label:
                self.tag_list_label.text = '[ref=__all_books__][u]All books[/u][/ref]'
            return

        # Voeg resultaten toe in batches
        self._pending_no_tag_results = matching_files
        self._no_tag_results_index = 0
        self._add_no_tag_results_batch()

    def _add_no_tag_results_batch(self, dt=None):
        """Voeg no-tag filter resultaten toe aan grid in batches."""
        if not getattr(self, '_no_tag_filter_active', False):
            return

        BATCH_SIZE = 30
        files = self._pending_no_tag_results
        start_idx = self._no_tag_results_index
        end_idx = min(start_idx + BATCH_SIZE, len(files))

        for i in range(start_idx, end_idx):
            filepath = files[i]
            try:
                self._add_file_widget(filepath, known_tags=[])
                self._file_count += 1
            except Exception:
                pass

        self._no_tag_results_index = end_idx

        # Update status
        self.status_label.text = f"{self._file_count} books without tags"

        if end_idx < len(files):
            Clock.schedule_once(self._add_no_tag_results_batch, 0)
        else:
            self._pending_no_tag_results = None

    # ============================================================================
    # OUDE RECURSIEVE TAG FILTER CODE (uitgeschakeld voor performance)
    #
    # Deze code scande recursief ALLE bestanden en extractte metadata van elk bestand.
    # Dit was langzaam bij grote collecties. De nieuwe versie hierboven filtert
    # alleen de bestaande widgets in de grid (instant respons).
    #
    # Om terug te zetten naar recursieve versie:
    # 1. Verwijder de twee simpele methodes hierboven (_apply_tag_filter en _apply_no_tag_filter)
    # 2. Uncomment de code hieronder
    # 3. De recursieve versie ondersteunt ook multi-book markdown filtering
    # ============================================================================
    #
    # def _apply_tag_filter_RECURSIVE(self):
    #     """Filter de huidige view om alleen boeken met de actieve tag te tonen.
    #
    #     Voor multi-book markdown bestanden: toont alleen de boeken die de tag hebben,
    #     niet alle boeken in het bestand. Gebruikt async batch processing om UI
    #     responsief te houden.
    #     """
    #     import time
    #
    #     if not self._tag_filter_tag:
    #         return
    #
    #     tag = self._tag_filter_tag
    #     self.status_label.text = f"Filtering on #{tag}..."
    #
    #     # Cancel eventuele lopende tag filter batches
    #     if hasattr(self, '_tag_filter_batch_event') and self._tag_filter_batch_event:
    #         self._tag_filter_batch_event.cancel()
    #         self._tag_filter_batch_event = None
    #
    #     # Verzamel recursief alle bestanden
    #     all_files = []
    #     try:
    #         self._collect_files_recursive(self._current_folder, all_files)
    #     except Exception:
    #         self.status_label.text = "Error scanning files"
    #         return
    #
    #     if not all_files:
    #         self.status_label.text = "No files found"
    #         return
    #
    #     # Update UI
    #     self.grid.clear_widgets()
    #     self._file_count = 0
    #     self._folder_count = 0
    #     self._selected_items.clear()
    #
    #     # Start async batch processing
    #     self._pending_tag_filter_files = all_files
    #     self._tag_filter_batch_index = 0
    #     self._tag_filter_start_time = time.time()
    #     self._tag_filter_version = getattr(self, '_tag_filter_version', 0) + 1
    #
    #     self._process_tag_filter_batch()
    #
    # def _process_tag_filter_batch_RECURSIVE(self, dt=None):
    #     """Process a batch of files for tag filtering.
    #
    #     Uses async batch processing to keep UI responsive and shows
    #     time estimate.
    #     """
    #     import time
    #
    #     # Check if filter was cancelled
    #     if not self._tag_filter_active:
    #         return
    #
    #     tag = self._tag_filter_tag
    #     if not tag:
    #         return
    #
    #     BATCH_SIZE = 50
    #     files = self._pending_tag_filter_files
    #     start_idx = self._tag_filter_batch_index
    #     end_idx = min(start_idx + BATCH_SIZE, len(files))
    #
    #     # Process this batch
    #     for i in range(start_idx, end_idx):
    #         filepath = files[i]
    #         try:
    #             file_type = filepath.suffix.lower()
    #
    #             # Multi-book markdown handling (alleen als setting aan staat)
    #             if file_type in ('.md', '.markdown') and self.custom.get('multi_book_markdown', True):
    #                 books = self.metadata_extractor.extract_all_books_from_markdown(filepath)
    #                 if len(books) > 1:
    #                     matching_count = 0
    #                     for book_meta in books:
    #                         if book_meta.tags:
    #                             book_tags = [t.strip() for t in book_meta.tags if t]
    #                             if tag in book_tags:
    #                                 matching_count += 1
    #                     if matching_count > 0:
    #                         self._add_file_widget(filepath, tag_filter=tag)
    #                         self._file_count += matching_count
    #                     continue
    #
    #             # Single-book check
    #             meta = self.metadata_extractor.extract(filepath)
    #             if meta and meta.tags:
    #                 file_tags = [t.strip() for t in meta.tags if t]
    #                 if tag in file_tags:
    #                     self._add_file_widget(filepath, known_tags=meta.tags)
    #                     self._file_count += 1
    #         except Exception:
    #             pass
    #
    #     self._tag_filter_batch_index = end_idx
    #
    #     # Update status with time estimate
    #     progress = int((end_idx / len(files)) * 100) if files else 100
    #     elapsed = time.time() - self._tag_filter_start_time
    #
    #     if progress > 0 and progress < 100:
    #         estimated_total = elapsed / (progress / 100)
    #         remaining = estimated_total - elapsed
    #         if remaining > 60:
    #             time_str = f"~{int(remaining / 60)} min remaining"
    #         else:
    #             time_str = f"~{int(remaining)} sec remaining"
    #         self.status_label.text = f"Filtering #{tag}... {progress}% ({self._file_count} found) - {time_str}"
    #     else:
    #         self.status_label.text = f"Filtering #{tag}... {progress}% ({self._file_count} found)"
    #
    #     if end_idx < len(files):
    #         # More to process - schedule next batch
    #         self._tag_filter_batch_event = Clock.schedule_once(
    #             self._process_tag_filter_batch, 0)
    #     else:
    #         # Done - show final status
    #         self._finish_tag_filter()
    #
    # def _finish_tag_filter_RECURSIVE(self):
    #     """Finish tag filter and show results."""
    #     tag = self._tag_filter_tag
    #     if self._file_count == 0:
    #         self.status_label.text = f"No books found with tag #{tag}"
    #         if self.tag_list_label:
    #             self.tag_list_label.text = '[ref=__all_books__][u]All books[/u][/ref]'
    #     else:
    #         self.status_label.text = f"{self._file_count} books with #{tag}"
    #         self._update_tag_list()
    #
    # def _apply_no_tag_filter_RECURSIVE(self):
    #     """Filter de huidige view om alleen boeken ZONDER tags te tonen.
    #
    #     Vergelijkbaar met _apply_tag_filter maar dan inverse: alleen boeken
    #     waarvan de tags lijst leeg is. Uses async batch processing.
    #     """
    #     import time
    #
    #     self.status_label.text = "Filtering on books without tags..."
    #
    #     # Cancel eventuele lopende batches
    #     if hasattr(self, '_no_tag_filter_batch_event') and self._no_tag_filter_batch_event:
    #         self._no_tag_filter_batch_event.cancel()
    #         self._no_tag_filter_batch_event = None
    #
    #     # Verzamel recursief alle bestanden
    #     all_files = []
    #     try:
    #         self._collect_files_recursive(self._current_folder, all_files)
    #     except Exception:
    #         self.status_label.text = "Error scanning files"
    #         return
    #
    #     if not all_files:
    #         self.status_label.text = "No files found"
    #         return
    #
    #     # Update UI
    #     self.grid.clear_widgets()
    #     self._file_count = 0
    #     self._folder_count = 0
    #     self._selected_items.clear()
    #
    #     # Start async batch processing
    #     self._pending_no_tag_filter_files = all_files
    #     self._no_tag_filter_batch_index = 0
    #     self._no_tag_filter_start_time = time.time()
    #
    #     self._process_no_tag_filter_batch()
    #
    # def _process_no_tag_filter_batch_RECURSIVE(self, dt=None):
    #     """Process a batch of files for no-tag filtering.
    #
    #     Uses async batch processing to keep UI responsive.
    #     """
    #     import time
    #
    #     # Check if filter was cancelled
    #     if not getattr(self, '_no_tag_filter_active', False):
    #         return
    #
    #     BATCH_SIZE = 50
    #     files = self._pending_no_tag_filter_files
    #     start_idx = self._no_tag_filter_batch_index
    #     end_idx = min(start_idx + BATCH_SIZE, len(files))
    #
    #     # Process this batch
    #     for i in range(start_idx, end_idx):
    #         filepath = files[i]
    #         try:
    #             file_type = filepath.suffix.lower()
    #
    #             # Multi-book markdown handling (alleen als setting aan staat)
    #             if file_type in ('.md', '.markdown') and self.custom.get('multi_book_markdown', True):
    #                 books = self.metadata_extractor.extract_all_books_from_markdown(filepath)
    #                 if len(books) > 1:
    #                     matching_indices = []
    #                     for idx, book_meta in enumerate(books):
    #                         if not book_meta.tags:
    #                             matching_indices.append(idx)
    #                     if matching_indices:
    #                         for idx in matching_indices:
    #                             self._add_book_widget(filepath, books[idx], book_index=idx)
    #                             self._file_count += 1
    #                     continue
    #
    #             # Single-book check
    #             meta = self.metadata_extractor.extract(filepath)
    #             if not meta or not meta.tags:
    #                 self._add_file_widget(filepath)
    #                 self._file_count += 1
    #         except Exception:
    #             pass
    #
    #     self._no_tag_filter_batch_index = end_idx
    #
    #     # Update status with time estimate
    #     progress = int((end_idx / len(files)) * 100) if files else 100
    #     elapsed = time.time() - self._no_tag_filter_start_time
    #
    #     if progress > 0 and progress < 100:
    #         estimated_total = elapsed / (progress / 100)
    #         remaining = estimated_total - elapsed
    #         if remaining > 60:
    #             time_str = f"~{int(remaining / 60)} min remaining"
    #         else:
    #             time_str = f"~{int(remaining)} sec remaining"
    #         self.status_label.text = f"Finding books without tags... {progress}% ({self._file_count} found) - {time_str}"
    #     else:
    #         self.status_label.text = f"Finding books without tags... {progress}% ({self._file_count} found)"
    #
    #     if end_idx < len(files):
    #         # More to process - schedule next batch
    #         self._no_tag_filter_batch_event = Clock.schedule_once(
    #             self._process_no_tag_filter_batch, 0)
    #     else:
    #         # Done - show final status
    #         if self._file_count == 0:
    #             self.status_label.text = "No books without tags found"
    #             if self.tag_list_label:
    #                 self.tag_list_label.text = '[ref=__all_books__][u]All books[/u][/ref]'
    #         else:
    #             self.status_label.text = f"{self._file_count} books without tags"
    #             self._update_tag_list()
    # ============================================================================
    # EINDE OUDE RECURSIEVE TAG FILTER CODE
    # ============================================================================

    def _on_item_double_tap(self, path_str: str, item_type: str):
        """Handle item double tap."""
        # Stop lopende tag scan/filter voor directe UI response
        self._cancel_tag_filter_batches()

        path = Path(path_str)
        if item_type == 'folder':
            self.navigate_to(path)
        else:
            self.status_label.text = f"Opening {path.name}..."
            if open_in_default_app(path):
                self.status_label.text = f"Opened {path.name}"
            else:
                self._show_error(f"Could not open: {path.name}")

    def _get_sidecar_files(self, path: Path) -> list:
        """
        Vind sidecar bestanden (metadata en cover) voor een boek.

        Sidecar bestanden volgen het patroon:
        - book.pdf.md voor metadata (Markdown met YAML frontmatter)
        - book.pdf.jpg/.png/.jpeg/.gif/.webp voor cover

        Returns: lijst van Path objecten voor bestaande sidecar files
        """
        if not path.is_file():
            return []

        sidecars = []

        # Metadata sidecar: book.pdf.md
        md_path = path.parent / (path.name + '.md')
        if md_path.exists():
            sidecars.append(md_path)

        # Cover sidecar: book.pdf.jpg, book.pdf.png, etc.
        cover_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp']
        for ext in cover_extensions:
            cover_path = path.parent / (path.name + ext)
            if cover_path.exists():
                sidecars.append(cover_path)
                break  # Slechts één cover per boek

        return sidecars

    def _move_selected(self):
        """Move selected items to another folder."""
        # Stop lopende tag filter batches onmiddellijk bij user interactie
        self._cancel_tag_filter_batches()

        if not self._selected_items:
            return

        selected_paths = [Path(p) for p in self._selected_items]

        # Verzamel geselecteerde widgets voor deselectie na cancel/move
        selected_widgets = []
        for child in self.grid.children:
            if hasattr(child, 'item_path') and child.item_path in self._selected_items:
                if hasattr(child, 'is_selected') and child.is_selected:
                    selected_widgets.append(child)

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

        def _deselect_all():
            """Deselecteer alle widgets - consistent met Edit Tags gedrag."""
            for widget in selected_widgets:
                if hasattr(widget, 'is_selected'):
                    widget.is_selected = False
                    if hasattr(widget, '_update_rect'):
                        widget._update_rect()
            self._selected_items.clear()
            self.btn_edit_tags.disabled = True
            self.btn_move.disabled = True
            self.btn_delete.disabled = True
            self.btn_edit_tags.opacity = 0.5
            self.btn_move.opacity = 0.5
            self.btn_delete.opacity = 0.5
            self._update_status_with_selection()

        def on_move(instance):
            if not filechooser.selection:
                return
            dest = Path(filechooser.selection[0])
            if not dest.is_dir():
                return
            popup.dismiss()

            moved = 0
            skipped = 0  # Bestanden die al in de doelmap staan
            sidecars_moved = 0
            errors = []  # Echte fouten (niet "already exists")
            moved_paths = set()  # Bijhouden welke paths daadwerkelijk verplaatst zijn
            for path in selected_paths:
                try:
                    new_path = dest / path.name
                    if new_path.exists():
                        # Bestand staat al in de doelmap - overslaan (geen error)
                        skipped += 1
                        continue

                    # Verplaats eerst sidecar files (metadata en cover)
                    for sidecar in self._get_sidecar_files(path):
                        sidecar_dest = dest / sidecar.name
                        if not sidecar_dest.exists():
                            try:
                                shutil.move(str(sidecar), str(sidecar_dest))
                                sidecars_moved += 1
                            except Exception as e:
                                # Sidecar fout niet fataal, log wel
                                errors.append(f"{sidecar.name}: {e}")

                    # Verplaats het boek zelf
                    shutil.move(str(path), str(new_path))
                    moved += 1
                    moved_paths.add(str(path))  # Onthoud succesvolle verplaatsing

                    # Update file cache: verplaats entry naar nieuwe path
                    self.file_cache.update_path(path, new_path)
                except Exception as e:
                    errors.append(f"{path.name}: {e}")

            # Als twins filter, tag filter of search actief is: verwijder alleen verplaatste widgets
            if self._twins_filter_active or self._search_root or self._tag_filter_active or getattr(self, '_no_tag_filter_active', False):
                widgets_to_remove = []
                for child in self.grid.children:
                    # Alleen verwijderen als daadwerkelijk verplaatst (niet skipped of error)
                    if hasattr(child, 'item_path') and child.item_path in moved_paths:
                        widgets_to_remove.append(child)
                for widget in widgets_to_remove:
                    self.grid.remove_widget(widget)
                # Deselecteer overgebleven widgets (skipped/error items)
                _deselect_all()
                remaining = len(self.grid.children)
                if self._twins_filter_active:
                    status = f"Moved {moved} items. {remaining} duplicates remaining"
                elif self._tag_filter_active:
                    status = f"Moved {moved} items. {remaining} with tag remaining"
                elif getattr(self, '_no_tag_filter_active', False):
                    status = f"Moved {moved} items. {remaining} without tag remaining"
                else:
                    status = f"Moved {moved} items. {remaining} search results remaining"
                if skipped:
                    status += f" ({skipped} already there)"
                self.status_label.text = status
                self._file_count = remaining
            else:
                _deselect_all()
                self._refresh()
                status = f"Moved {moved} items to {dest.name}"
                if skipped:
                    status += f" ({skipped} already there)"
                self.status_label.text = status

            # Toon alleen error popup als er echte fouten zijn (niet voor skipped files)
            if errors:
                self._show_error(f"Moved {moved} items.\n\nErrors:\n" + "\n".join(errors[:5]))

        def on_cancel(instance):
            popup.dismiss()
            _deselect_all()

        btn_cancel.bind(on_release=on_cancel)
        btn_move.bind(on_release=on_move)
        popup.open()

    def _delete_selected(self):
        """Delete selected items after confirmation."""
        # Stop lopende tag filter batches onmiddellijk bij user interactie
        self._cancel_tag_filter_batches()

        if not self._selected_items:
            return

        selected_paths = [Path(p) for p in self._selected_items]
        count = len(selected_paths)

        # Verzamel geselecteerde widgets voor deselectie na cancel/delete
        selected_widgets = []
        for child in self.grid.children:
            if hasattr(child, 'item_path') and child.item_path in self._selected_items:
                if hasattr(child, 'is_selected') and child.is_selected:
                    selected_widgets.append(child)

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

        # Bepaal waarschuwingstekst en of de actie gevaarlijk is
        # Rode knop alleen bij: folders met bestanden erin, of permanente delete (geen prullenbak)
        is_dangerous = False
        if folders_with_files == 1:
            warning_text = "Beware! This action will delete the files in this folder too!"
            is_dangerous = True
        elif folders_with_files > 1:
            warning_text = "Beware! This action will delete the files in these folders too!"
            is_dangerous = True
        elif HAS_SEND2TRASH:
            warning_text = f"Move {count} item(s) to trash?"
            is_dangerous = False  # Simpele prullenbak-operatie, niet gevaarlijk
        else:
            warning_text = f"Delete {count} item(s)?\n\nThis cannot be undone!"
            is_dangerous = True

        # Confirmation popup
        content = BoxLayout(orientation='vertical', padding=dp(10), spacing=dp(10))
        warning_label = self._create_popup_label(warning_text, halign='center', valign='middle')
        content.add_widget(warning_label)

        btn_layout = self._create_popup_button_row()
        btn_cancel = self._create_popup_button('Cancel')
        btn_confirm = self._create_popup_button('Delete', danger=is_dangerous)
        btn_layout.add_widget(btn_cancel)
        btn_layout.add_widget(btn_confirm)
        content.add_widget(btn_layout)

        popup = self._create_popup('Confirm Delete', content, size_hint=(0.5, 0.3))

        def on_delete(instance):
            popup.dismiss()
            deleted = 0
            sidecars_deleted = 0
            errors = []
            for path in selected_paths:
                try:
                    # Verwijder eerst sidecar files (metadata en cover)
                    for sidecar in self._get_sidecar_files(path):
                        try:
                            if HAS_SEND2TRASH:
                                send2trash(str(sidecar))
                            else:
                                sidecar.unlink()
                            sidecars_deleted += 1
                        except Exception as e:
                            # Sidecar fout niet fataal, log wel
                            errors.append(f"{sidecar.name}: {e}")

                    # Verwijder het boek zelf
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

                    # Verwijder uit file cache
                    self.file_cache.invalidate(path)

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

        def _deselect_all():
            """Deselecteer alle widgets - consistent met Edit Tags gedrag."""
            for widget in selected_widgets:
                if hasattr(widget, 'is_selected'):
                    widget.is_selected = False
                    if hasattr(widget, '_update_rect'):
                        widget._update_rect()
            self._selected_items.clear()
            self.btn_edit_tags.disabled = True
            self.btn_move.disabled = True
            self.btn_delete.disabled = True
            self.btn_edit_tags.opacity = 0.5
            self.btn_move.opacity = 0.5
            self.btn_delete.opacity = 0.5
            self._update_status_with_selection()

        def on_cancel(instance):
            popup.dismiss()
            _deselect_all()

        btn_cancel.bind(on_release=on_cancel)
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
        """Start asynchrone search - verzamelt eerst bestanden, dan batch processing.

        SPECIAL: Als de zoekterm een file type is uit selected_types.txt (bijv. ".epub"),
        dan worden alle bestanden van dat type getoond ipv normale text search.
        """
        import time

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

        # Check of zoekterm een file type is (bijv. ".epub", "epub", ".pdf")
        search_term = self._search_text
        if not search_term.startswith('.'):
            search_term_with_dot = '.' + search_term
        else:
            search_term_with_dot = search_term

        # Check of het een bekend file type is uit selected_types.txt
        is_file_type_search = search_term_with_dot.lower() in self.selected_types

        if is_file_type_search:
            self.status_label.text = f"Finding all {search_term_with_dot} files..."
        else:
            self.status_label.text = f"Searching for '{self._search_text}'..."

        # Clear grid alvast
        self.grid.clear_widgets()
        self._selected_items.clear()
        self._hidden_widgets = []

        # Verzamel recursief alle bestanden (dit is snel, alleen filesystem)
        all_files = []
        self._collect_files_recursive(self._current_folder, all_files, max_depth=10)

        # Bij file type search: filter direct op extensie, geen metadata matching nodig
        if is_file_type_search:
            matching_files = [f for f in all_files if f.suffix.lower() == search_term_with_dot.lower()]
            self._search_matches = matching_files
            self._pending_search_files = []  # Geen batch processing nodig
            self._search_batch_index = 0
            self._current_search_version = current_version
            # Toon direct resultaten
            self._show_search_results(expected_version=current_version)
            return

        # Start batch processing voor metadata matching
        self._pending_search_files = all_files
        self._search_matches = []
        self._search_batch_index = 0
        self._current_search_version = current_version
        # Track start time for progress estimation
        self._search_start_time = time.time()
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

        # Update status with time estimate
        import time
        progress = int((end_idx / len(files)) * 100) if files else 100
        elapsed = time.time() - getattr(self, '_search_start_time', time.time())

        if progress > 0 and progress < 100:
            # Calculate estimated time remaining
            estimated_total = elapsed / (progress / 100)
            remaining = estimated_total - elapsed
            if remaining > 60:
                time_str = f"~{int(remaining / 60)} min remaining"
            else:
                time_str = f"~{int(remaining)} sec remaining"
            self.status_label.text = f"Searching... {progress}% ({len(self._search_matches)} found) - {time_str}"
        else:
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
        Gebruikt file_cache voor snelle lookup indien beschikbaar.

        Bij fuzzy_search=True: doorzoekt booktitle, author, isbn, cover_url
        Bij fuzzy_search=False: doorzoekt ALLEEN booktitle en author (exacte substring match)
        """
        is_fuzzy = self.custom.get('fuzzy_search', False)

        try:
            # Gebruik file_cache voor snelle lookup
            cached = self.file_cache.get_or_extract(file_path, self.metadata_extractor)

            if cached:
                # CachedFileMetadata heeft direct de velden (geen multi-book structuur)
                # Altijd booktitle en author doorzoeken
                if cached.booktitle and self._search_match(self._search_text, cached.booktitle):
                    return True
                # Doorzoek alle auteurs in de lijst
                for author in cached.authors:
                    if self._search_match(self._search_text, author):
                        return True
                # ISBN en cover_url alleen bij fuzzy search
                if is_fuzzy:
                    if cached.isbn and self._search_match(self._search_text, cached.isbn):
                        return True
                    if cached.cover_url and self._search_match(self._search_text, cached.cover_url):
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
                """Extract metadata voor één bestand."""
                try:
                    # Gebruik file_cache voor snelle lookup
                    cached = self.file_cache.get_or_extract(filepath, self.metadata_extractor)

                    if cached:
                        return [{
                            'path': filepath,
                            'isbn': cached.isbn or '',
                            'booktitle': cached.booktitle or filepath.stem,
                            'authors': cached.authors or [],
                        }]

                    # Fallback: directe extractie
                    meta = self.metadata_extractor.extract(filepath)
                    return [{
                        'path': filepath,
                        'isbn': meta.isbn or '',
                        'booktitle': meta.booktitle or filepath.stem,
                        'authors': meta.authors or [],
                    }]
                except Exception:
                    return [{
                        'path': filepath,
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
                    debug_lines.append(f"File: {meta['path'].name}")
                    debug_lines.append(f"  booktitle: '{meta['booktitle']}'")
                    debug_lines.append(f"  authors: {meta['authors']}")
                    debug_lines.append(f"  isbn: '{meta['isbn']}'")
                    debug_lines.append("")

            # Stap 3: Vind duplicates en groepeer ze per set
            # duplicate_sets is een lijst van lijsten - elke sublijst bevat
            # metadata van bestanden die duplicates van elkaar zijn
            duplicate_sets = []
            processed_items = set()

            def get_item_key(meta):
                """Genereer unieke key voor een metadata entry."""
                return meta['path']

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
                        debug_lines.append(f"  - {f['path'].name}")
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
                        in_isbn_set = "(ISBN set)" if get_item_key(f) in processed_items else ""
                        debug_lines.append(f"    - {f['path'].name} {in_isbn_set}")

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
                        debug_lines.append(f"    - {f['path'].name}")
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
        shown_items = set()

        # Loop door elke duplicate set en voeg de bestanden toe
        # Hierdoor staan duplicates van elkaar altijd bij elkaar
        for dup_set in duplicate_sets:
            # Sorteer binnen de set op folder pad zodat zelfde folders bij elkaar staan
            sorted_set = sorted(dup_set, key=lambda m: str(m['path'].parent))

            for meta in sorted_set:
                filepath = meta['path']

                # Skip als dit item al getoond is
                if filepath in shown_items:
                    continue
                shown_items.add(filepath)

                file_type = get_file_type(filepath)
                document_type = get_document_type(filepath)

                widget = CoverImage(
                    item_path=str(filepath),
                    item_type='file',
                    item_name=filepath.stem,
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

                self.grid.add_widget(widget)
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
        """Toon popup met Libiry companion apps.

        Dit is de "bento" menu popup, analoog aan Google Apps in Gmail.
        Compact design: alleen app buttons en cancel, geen instructietekst.
        Gestyled volgens huisstijl met _create_popup helpers.

        Apps:
        - BookSpineScanner: opent website in browser
        - Calibre2Libiry: start lokale tool (.bat op Windows, .py op Mac/Linux)
        - Libiry2Go: start lokale tool (.bat op Windows, .py op Mac/Linux)
        """
        content = BoxLayout(orientation='vertical', spacing=dp(10), padding=dp(15))

        # App buttons - elk in eigen row voor consistente hoogte
        # 1. BookSpineScanner
        btn_row_bss = self._create_popup_button_row()
        btn_bss = self._create_popup_button('BookSpineScanner')
        btn_row_bss.add_widget(btn_bss)
        content.add_widget(btn_row_bss)

        # 2. Calibre2Libiry
        btn_row_c2l = self._create_popup_button_row()
        btn_c2l = self._create_popup_button('Calibre2Libiry')
        btn_row_c2l.add_widget(btn_c2l)
        content.add_widget(btn_row_c2l)

        # 3. Libiry2Go
        btn_row_l2g = self._create_popup_button_row()
        btn_l2g = self._create_popup_button('Libiry2Go')
        btn_row_l2g.add_widget(btn_l2g)
        content.add_widget(btn_row_l2g)

        # Spacer
        content.add_widget(BoxLayout(size_hint_y=1))

        # Cancel button
        btn_row_cancel = self._create_popup_button_row()
        btn_cancel = self._create_popup_button('Cancel')
        btn_row_cancel.add_widget(btn_cancel)
        content.add_widget(btn_row_cancel)

        # Popup aanmaken
        popup = self._create_popup('Libiry apps', content, size_hint=(0.4, 0.4))

        def on_bss(instance):
            popup.dismiss()
            self._open_bookspinescanner()

        def on_c2l(instance):
            popup.dismiss()
            self._start_companion_tool('Calibre2Libiry')

        def on_l2g(instance):
            popup.dismiss()
            self._start_companion_tool('Libiry2Go')

        btn_bss.bind(on_release=on_bss)
        btn_c2l.bind(on_release=on_c2l)
        btn_l2g.bind(on_release=on_l2g)
        btn_cancel.bind(on_release=lambda x: popup.dismiss())

        popup.open()

    def _start_companion_tool(self, tool_name: str):
        """Start een Libiry companion tool.

        Op Windows wordt de .bat file gestart, op Mac/Linux de .py file.
        De tools delen settings met Libiry via customize/customize.txt.

        Args:
            tool_name: Naam van de tool (bijv. 'Calibre2Libiry' of 'Libiry2Go')
        """
        import subprocess
        import sys

        # Bepaal het pad naar de tool
        app_dir = self._app_path

        if sys.platform == 'win32':
            # Windows: gebruik .bat file
            tool_path = app_dir / f'{tool_name}.bat'
            if tool_path.exists():
                try:
                    # Start in eigen console venster zodat de tool onafhankelijk draait
                    subprocess.Popen(
                        ['cmd', '/c', 'start', '', str(tool_path)],
                        cwd=str(app_dir),
                        shell=True
                    )
                    self.status_label.text = f"Started {tool_name}"
                except Exception as e:
                    self._show_error(f"Could not start {tool_name}: {e}")
            else:
                self._show_error(f"{tool_name}.bat not found")
        else:
            # Mac/Linux: gebruik .py file met Python
            tool_path = app_dir / f'{tool_name.lower()}.py'
            # Probeer ook met originele casing
            if not tool_path.exists():
                tool_path = app_dir / f'{tool_name}.py'

            if tool_path.exists():
                try:
                    # Start Python script in achtergrond
                    subprocess.Popen(
                        [sys.executable, str(tool_path)],
                        cwd=str(app_dir),
                        start_new_session=True
                    )
                    self.status_label.text = f"Started {tool_name}"
                except Exception as e:
                    self._show_error(f"Could not start {tool_name}: {e}")
            else:
                self._show_error(f"{tool_name}.py not found")

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
        """Handle keyboard shortcuts.

        Op Windows kan codepoint None zijn bij Ctrl+letter combinaties,
        daarom gebruiken we key codes als fallback.
        Key codes: a=97, -=45, ==61, +=43
        """
        if 'ctrl' in modifier:
            # Zoom in: Ctrl+= of Ctrl++
            if codepoint in ('=', '+') or key in (61, 43):
                self._zoom_in()
                return True
            # Zoom out: Ctrl+-
            if codepoint == '-' or key == 45:
                self._zoom_out()
                return True
            # Select all: Ctrl+A (key code 97)
            if codepoint == 'a' or key == 97:
                self._select_all_books()
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

    def _select_all_books(self):
        """Toggle selectie van alle zichtbare boeken in het grid (geen folders).

        Ctrl+A shortcut werkt als toggle:
        - Als niet alles geselecteerd is: selecteer alle boeken
        - Als alles al geselecteerd is: deselecteer alles

        Folders worden overgeslagen. Werkt ook met multi-book markdown files.
        """
        # Check of grid bestaat en items heeft
        if not hasattr(self, 'grid') or self.grid is None:
            return
        if not self.grid.children:
            return

        try:
            # Tel hoeveel boeken er zijn en hoeveel geselecteerd
            book_widgets = []
            for child in self.grid.children:
                # Skip folders - alleen bestanden
                if hasattr(child, 'item_type') and child.item_type == 'folder':
                    continue
                if hasattr(child, 'item_path') and hasattr(child, 'is_selected'):
                    book_widgets.append(child)

            if not book_widgets:
                return

            # Check of alles al geselecteerd is
            all_selected = all(w.is_selected for w in book_widgets)

            widgets_to_update = []

            if all_selected:
                # Deselecteer alles
                for child in book_widgets:
                    if child.is_selected:
                        child.is_selected = False
                        self._selected_items.discard(child.item_path)
                        widgets_to_update.append(child)
            else:
                # Selecteer alles
                for child in book_widgets:
                    if not child.is_selected:
                        child.is_selected = True
                        self._selected_items.add(child.item_path)
                        widgets_to_update.append(child)

            # Batch visuele updates na de loop (voorkomt "not responding")
            for child in widgets_to_update:
                if hasattr(child, '_update_rect'):
                    child._update_rect()

            # Update UI buttons
            has_selection = len(self._selected_items) > 0
            self.btn_edit_tags.disabled = not has_selection
            self.btn_move.disabled = not has_selection
            self.btn_delete.disabled = not has_selection
            self.btn_edit_tags.opacity = 1.0 if has_selection else 0.5
            self.btn_move.opacity = 1.0 if has_selection else 0.5
            self.btn_delete.opacity = 1.0 if has_selection else 0.5
            self._update_status_with_selection()

        except Exception as e:
            print(f"Error in _select_all_books: {e}")
            import traceback
            traceback.print_exc()

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
                                  readonly: bool = False, hint_text: str = '',
                                  white_background: bool = False,
                                  size_hint_x: float = None) -> 'Widget':
        """
        Maak een gestylde text input voor gebruik in popups.

        Args:
            text: Initiële tekst
            multiline: True voor meerdere regels
            readonly: True voor alleen-lezen
            hint_text: Placeholder tekst (grijs, verdwijnt bij typen)
            white_background: True voor witte achtergrond met (optioneel) ronde hoeken
            size_hint_x: Breedte als fractie (0.0-1.0), None = volledige breedte

        Returns:
            Widget met text input. Bij white_background=True is dit een RelativeLayout
            met een .text_input attribuut voor toegang tot de TextInput.
        """
        h_pad = dp(10)
        # Verticale padding berekenen voor centrering
        v_pad = self.ui_font_size * 0.4

        if white_background:
            # Maak een container met ronde achtergrond (zoals SearchBox)
            use_rounded = self.custom.get('rounded_corners', True)
            # Bij multiline: size_hint_y=1 zodat container meegroeit met parent
            # Bij single-line: vaste hoogte met size_hint_y=None
            if multiline:
                container = RelativeLayout(
                    size_hint=(size_hint_x if size_hint_x else 1, 1)
                )
            else:
                container = RelativeLayout(
                    size_hint=(size_hint_x if size_hint_x else 1, None),
                    height=self.ui_bar_height
                )

            # Witte achtergrond met optioneel ronde hoeken
            bg_widget = RoundedBackground(
                bg_color=(1, 1, 1, 1),
                rounded=use_rounded,
                size_hint=(1, 1),
                pos_hint={'x': 0, 'y': 0},
            )
            container.add_widget(bg_widget)

            # Transparante TextInput eroverheen
            text_input = TextInput(
                text=str(text) if text else '',
                hint_text=hint_text,
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
            container.add_widget(text_input)
            # Sla referentie op zodat we bij .text kunnen
            container.text_input = text_input
            return container
        else:
            return TextInput(
                text=str(text) if text else '',
                hint_text=hint_text,
                multiline=multiline,
                readonly=readonly,
                background_color=(0, 0, 0, 0),  # Transparant
                background_normal='',
                background_active='',
                foreground_color=(0, 0, 0, 1),  # Zwarte tekst
                font_size=self.ui_font_size,
                padding=[h_pad, v_pad, h_pad, v_pad],
                size_hint=(size_hint_x if size_hint_x else 1, 1),
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

    def _show_edit_tags_popup(self):
        """Show popup for editing metadata on selected items.

        Voor 1 item: volledige metadata editor met alle velden
        Voor meerdere items: alleen tags editor (bulk editing)

        Ondersteunde velden (voor 1 item):
        - cover, booktitle, author, isbn, rating, publisher, year, language
        - series, series_index, tags, description, notes

        Tags worden getoond in een multiline tekstvak (één tag per regel),
        net zoals "selected file types" in de Settings popup.
        """
        # Stop lopende tag filter batches onmiddellijk bij user interactie
        self._cancel_tag_filter_batches()

        if not self._selected_items:
            return

        # Bewaar selected_paths voor gebruik in on_save callback
        selected_paths = [Path(p) for p in self._selected_items]

        # Verzamel widgets
        selected_widgets = []
        for child in self.grid.children:
            if hasattr(child, 'item_path') and child.item_path in self._selected_items:
                if hasattr(child, 'is_selected') and child.is_selected:
                    selected_widgets.append(child)

        item_count = len(selected_widgets) if selected_widgets else len(selected_paths)

        # Voor 1 item: toon volledige metadata editor
        # Voor meerdere items: toon alleen tags editor
        if item_count == 1:
            self._show_full_metadata_editor(selected_widgets, selected_paths)
        else:
            self._show_tags_only_editor(selected_widgets, selected_paths)

    def _show_tags_only_editor(self, selected_widgets, selected_paths):
        """Toon alleen tags editor voor bulk editing van meerdere items."""
        # Verzamel tags per WIDGET
        all_tags_per_item = []
        for widget in selected_widgets:
            widget_tags = set()
            if hasattr(widget, 'tags') and widget.tags:
                for tag in widget.tags:
                    if tag:
                        widget_tags.add(tag.strip())
            all_tags_per_item.append(widget_tags)

        # Fallback: als geen widgets gevonden, gebruik paths
        if not all_tags_per_item:
            for path in selected_paths:
                file_tags = set()
                try:
                    meta = self.metadata_extractor.extract(path)
                    if meta and meta.tags:
                        for tag in meta.tags:
                            if tag:
                                file_tags.add(tag.strip())
                except Exception:
                    pass
                all_tags_per_item.append(file_tags)

        # Vind gemeenschappelijke tags (intersectie van alle sets)
        if all_tags_per_item:
            common_tags = all_tags_per_item[0].copy()
            for item_tags in all_tags_per_item[1:]:
                common_tags &= item_tags
        else:
            common_tags = set()

        # Sorteer tags alfabetisch
        common_tags_sorted = sorted(common_tags)
        original_tags = set(common_tags_sorted)
        tags_str = '\n'.join(common_tags_sorted)

        # Bouw popup content
        content = BoxLayout(orientation='vertical', padding=dp(10), spacing=dp(10))

        tags_label = self._create_popup_label("Common tags (one per line, without #):")
        content.add_widget(tags_label)

        tags_row = BoxLayout(orientation='horizontal', size_hint_y=None, height=dp(150))
        tags_container = self._create_popup_text_input(
            tags_str, multiline=True, white_background=True, size_hint_x=1.0
        )
        tags_row.add_widget(tags_container)
        content.add_widget(tags_row)

        btn_layout = self._create_popup_button_row()
        btn_cancel = self._create_popup_button('Cancel')
        btn_save = self._create_popup_button('Save')
        btn_layout.add_widget(btn_cancel)
        btn_layout.add_widget(btn_save)
        content.add_widget(btn_layout)

        popup = self._create_popup('Edit Tags', content, size_hint=(0.5, 0.5))

        def _deselect_all_widgets():
            for widget in selected_widgets:
                if hasattr(widget, 'is_selected'):
                    widget.is_selected = False
                    if hasattr(widget, '_update_rect'):
                        widget._update_rect()
            self._selected_items.clear()
            self.btn_edit_tags.disabled = True
            self.btn_move.disabled = True
            self.btn_delete.disabled = True
            self.btn_edit_tags.opacity = 0.5
            self.btn_move.opacity = 0.5
            self.btn_delete.opacity = 0.5
            self._update_status_with_selection()

        def on_cancel(instance):
            popup.dismiss()
            _deselect_all_widgets()

        def on_save(instance):
            popup.dismiss()
            input_widget = tags_container.text_input if hasattr(tags_container, 'text_input') else tags_container
            new_tags_text = input_widget.text.strip()
            new_tags = set()
            for line in new_tags_text.split('\n'):
                tag = line.strip()  # Behoud originele case
                if tag.startswith('#'):
                    tag = tag[1:].strip()
                if tag:
                    new_tags.add(tag)

            # Tags zijn case-sensitive: directe vergelijking
            tags_to_remove = original_tags - new_tags
            tags_to_add = new_tags - original_tags

            if not tags_to_remove and not tags_to_add:
                _deselect_all_widgets()
                return

            from collections import defaultdict
            widgets_by_path = defaultdict(list)
            for widget in selected_widgets:
                widgets_by_path[widget.item_path].append(widget)

            self._start_async_tag_save(
                widgets_by_path, tags_to_remove, tags_to_add,
                selected_widgets, _deselect_all_widgets
            )

        btn_cancel.bind(on_release=on_cancel)
        btn_save.bind(on_release=on_save)
        popup.open()

    def _show_full_metadata_editor(self, selected_widgets, selected_paths):
        """Toon volledige metadata editor voor een enkel item.

        Velden: cover, booktitle, author, author_sort, isbn, rating, publisher, year,
        publication_date, language, pages, series, series_index, translator, illustrator,
        tags, description, notes
        """
        # Haal metadata op van het geselecteerde item
        widget = selected_widgets[0] if selected_widgets else None
        path = selected_paths[0]

        # Lees huidige metadata uit cache (consistenter dan directe extractie)
        # Dit voorkomt dat metadata verloren gaat door inconsistente extractie
        try:
            cached = self.file_cache.get_or_extract(path, self.metadata_extractor)
            if cached:
                # Converteer CachedFileMetadata naar BookMetadata-achtig object
                from core.metadata_extractor import BookMetadata
                meta = BookMetadata(
                    booktitle=cached.booktitle,
                    authors=cached.authors,
                    author_sort=cached.author_sort,
                    isbn=cached.isbn,
                    rating=cached.rating,
                    publisher=cached.publisher,
                    year=cached.year,
                    publication_date=cached.publication_date,
                    language=cached.language,
                    pages=cached.pages,
                    tags=cached.tags,
                    series=cached.series,
                    series_index=cached.series_index,
                    translator=cached.translator,
                    illustrator=cached.illustrator,
                    description=cached.description,
                    notes=cached.notes,
                    cover_url=cached.cover_url,
                )
            else:
                # Fallback naar directe extractie
                meta = self.metadata_extractor.extract(path)
        except Exception as e:
            print(f"Error reading metadata: {e}")
            meta = None

        # Haal geconfigureerde veldnamen op
        field_names = self.custom.get('field_names', {})

        # Standaard waarden
        current = {
            'cover': meta.cover_url if meta else '',
            'booktitle': getattr(widget, 'booktitle', '') or (meta.booktitle if meta else '') or '',
            'author': ', '.join(meta.authors) if meta and meta.authors else '',
            'author_sort': meta.author_sort if meta else '',
            'isbn': getattr(widget, 'isbn', '') or (meta.isbn if meta else '') or '',
            'rating': str(meta.rating) if meta and meta.rating is not None else '',
            'publisher': meta.publisher if meta else '',
            'publication_date': meta.publication_date if meta else '',
            'language': meta.language if meta else '',
            'pages': meta.pages if meta else '',
            'series': meta.series if meta else '',
            'series_index': str(meta.series_index) if meta and meta.series_index is not None else '',
            'translator': meta.translator if meta else '',
            'illustrator': meta.illustrator if meta else '',
            'tags': '\n'.join(sorted(meta.tags)) if meta and meta.tags else '',
            'description': meta.description if meta else '',
            'notes': meta.notes if meta else '',
        }

        # Bewaar originele tags voor vergelijking (behoud case)
        original_tags = set(t.strip() for t in (meta.tags if meta else []) if t)

        # Bouw scrollable popup content
        # Hoofd container
        main_content = BoxLayout(orientation='vertical', padding=dp(10), spacing=dp(5))

        # Scrollable form area met huisstijl scrollbar (capsule-vorm)
        use_rounded = self.custom.get('rounded_corners', True)
        scrollbar_width = self.custom.get('scrollbar_width', 10)
        scrollbar_always = self.custom.get('scrollbar_always_visible', True)
        scroll = RoundedScrollView(
            size_hint=(1, 1),
            do_scroll_x=False,
            bar_width=dp(scrollbar_width),
            rounded=use_rounded,
            bar_color_override=self.custom.get('button_color', (0.5, 0.25, 0.31, 1)),  # Aubergine
            scroll_type=['bars', 'content'],  # Nodig voor touch interactie
            always_visible=scrollbar_always,
        )
        form = BoxLayout(orientation='vertical', size_hint_y=None, spacing=dp(8), padding=[0, 0, dp(10), 0])
        form.bind(minimum_height=form.setter('height'))

        # Dictionary om input widgets bij te houden
        inputs = {}

        # Helper voor form rows (label + input)
        def add_field(name, label_text, value, multiline=False, height_mult=1.0):
            row = BoxLayout(orientation='horizontal', size_hint_y=None,
                           height=dp(100 * height_mult) if multiline else self.ui_bar_height)
            row.spacing = dp(10)

            # Label (30% breedte)
            lbl = self._create_popup_label(label_text, size_hint_x=0.3, halign='right')
            lbl.valign = 'top' if multiline else 'middle'
            row.add_widget(lbl)

            # Input (70% breedte)
            inp = self._create_popup_text_input(
                value, multiline=multiline, white_background=True, size_hint_x=0.7
            )
            row.add_widget(inp)
            inputs[name] = inp

            form.add_widget(row)

        # Voeg alle velden toe
        # Sectie: Basis informatie
        add_field('cover', field_names.get('cover', 'cover') + ':', current['cover'])
        add_field('booktitle', field_names.get('booktitle', 'booktitle') + ':', current['booktitle'])
        add_field('author', field_names.get('author', 'author') + ':', current['author'])
        add_field('isbn', field_names.get('isbn', 'isbn') + ':', current['isbn'])

        # Sectie: Publicatie info
        add_field('publisher', field_names.get('publisher', 'publisher') + ':', current['publisher'])
        add_field('language', field_names.get('language', 'language') + ':', current['language'])

        # Sectie: Serie info
        add_field('series', field_names.get('series', 'series') + ':', current['series'])
        add_field('series_index', field_names.get('series_index', 'series_index') + ':', current['series_index'])

        # Sectie: Beoordeling
        add_field('rating', field_names.get('rating', 'rating') + ' (0-5):', current['rating'])

        # Sectie: Tags (multiline)
        add_field('tags', field_names.get('tags', 'tags') + ':', current['tags'], multiline=True, height_mult=1.2)

        # Sectie: Extra velden
        add_field('author_sort', field_names.get('author_sort', 'author_sort') + ':', current['author_sort'])
        add_field('publication_date', field_names.get('publication_date', 'publication_date') + ':', current['publication_date'])
        add_field('pages', field_names.get('pages', 'pages') + ':', current['pages'])
        add_field('translator', field_names.get('translator', 'translator') + ':', current['translator'])
        add_field('illustrator', field_names.get('illustrator', 'illustrator') + ':', current['illustrator'])

        # Sectie: Beschrijving (multiline)
        add_field('description', field_names.get('description', 'description') + ':', current['description'], multiline=True, height_mult=1.5)

        # Sectie: Notities (multiline)
        add_field('notes', field_names.get('notes', 'notes') + ':', current['notes'], multiline=True, height_mult=1.2)

        scroll.add_widget(form)
        main_content.add_widget(scroll)

        # Buttons onderaan
        btn_layout = self._create_popup_button_row()
        btn_cancel = self._create_popup_button('Cancel')
        btn_save = self._create_popup_button('Save')
        btn_layout.add_widget(btn_cancel)
        btn_layout.add_widget(btn_save)
        main_content.add_widget(btn_layout)

        # Popup met grotere size voor alle velden
        # 0.8 breed x 0.95 hoog voor minder scrollen
        popup = self._create_popup('Edit Metadata', main_content, size_hint=(0.8, 0.95))

        def _deselect_all_widgets():
            for w in selected_widgets:
                if hasattr(w, 'is_selected'):
                    w.is_selected = False
                    if hasattr(w, '_update_rect'):
                        w._update_rect()
            self._selected_items.clear()
            self.btn_edit_tags.disabled = True
            self.btn_move.disabled = True
            self.btn_delete.disabled = True
            self.btn_edit_tags.opacity = 0.5
            self.btn_move.opacity = 0.5
            self.btn_delete.opacity = 0.5
            self._update_status_with_selection()

        def on_cancel(instance):
            popup.dismiss()
            _deselect_all_widgets()

        def on_save(instance):
            popup.dismiss()

            # Verzamel nieuwe waarden uit inputs
            def get_text(inp):
                if hasattr(inp, 'text_input'):
                    return inp.text_input.text.strip()
                return inp.text.strip() if hasattr(inp, 'text') else ''

            new_values = {}
            for name, inp in inputs.items():
                new_values[name] = get_text(inp)

            # Parse tags (behoud originele case)
            new_tags = set()
            for line in new_values['tags'].split('\n'):
                tag = line.strip()  # Behoud case
                if tag.startswith('#'):
                    tag = tag[1:].strip()
                if tag:
                    new_tags.add(tag)

            # Bouw metadata object voor opslaan
            new_meta = {
                'cover': new_values['cover'],
                'booktitle': new_values['booktitle'],
                'author': new_values['author'],
                'author_sort': new_values['author_sort'],
                'isbn': new_values['isbn'],
                'rating': new_values['rating'],
                'publisher': new_values['publisher'],
                'publication_date': new_values['publication_date'],
                'language': new_values['language'],
                'pages': new_values['pages'],
                'series': new_values['series'],
                'series_index': new_values['series_index'],
                'translator': new_values['translator'],
                'illustrator': new_values['illustrator'],
                'tags': sorted(new_tags),
                'description': new_values['description'],
                'notes': new_values['notes'],
            }

            # Sla metadata op naar bestand
            try:
                self._save_full_metadata(path, new_meta)

                # Update widget met nieuwe waarden
                if widget:
                    widget.booktitle = new_meta['booktitle']
                    widget.isbn = new_meta['isbn']
                    widget.tags = new_meta['tags']
                    if hasattr(widget, '_draw_document_type_triangle'):
                        widget._draw_document_type_triangle()

                # Update file cache - invalidate zodat volgende load verse data haalt
                # De file is zojuist gewijzigd, dus de cache entry is stale
                self.file_cache.invalidate(path)

                # Volledige refresh zodat grid en tag lijst consistent blijven.
                # Dit is nodig omdat:
                # 1. Bij tag filter: bestand kan uit view verdwijnen als tag verwijderd is
                # 2. Bij subfolder navigatie: bestanden in hoofdfolder moeten ook bijgewerkt
                # 3. Tag lijst scant recursief alle subfolders
                # Zonder refresh moet gebruiker handmatig refreshen wat niet intuïtief is.
                self._refresh()

                self.status_label.text = "Metadata saved"
            except Exception as e:
                print(f"Error saving metadata: {e}")
                import traceback
                traceback.print_exc()
                self.status_label.text = f"Error saving metadata: {str(e)[:50]}"

            _deselect_all_widgets()

        btn_cancel.bind(on_release=on_cancel)
        btn_save.bind(on_release=on_save)
        popup.open()

    def _save_full_metadata(self, path: Path, metadata: dict):
        """Save full metadata to a file.

        Supports:
        - Markdown: YAML frontmatter
        - EPUB: OPF metadata (internal) or sidecar
        - PDF: metadata fields or sidecar
        - MOBI/AZW: Markdown sidecar (always)
        - CBZ/CBR: ComicInfo.xml or sidecar

        When 'metadata_in_sidecar' setting is True, all metadata is stored
        in sidecar files instead of in the book files themselves.

        Args:
            path: Path to the file
            metadata: Dict with all metadata fields
        """
        file_type = path.suffix.lower()
        use_sidecar = self.custom.get('metadata_in_sidecar', False)

        if file_type in ('.md', '.markdown'):
            # Markdown files: always save to the file itself (it IS the metadata)
            self._save_markdown_metadata(path, metadata)
        elif use_sidecar and file_type in ('.epub', '.pdf', '.cbz', '.cbr'):
            # User prefers sidecar: save all metadata to sidecar file
            self._save_sidecar_metadata(path, metadata)
        elif file_type == '.epub':
            self._save_epub_metadata(path, metadata)
        elif file_type == '.pdf':
            self._save_pdf_metadata(path, metadata)
        elif file_type in ('.mobi', '.azw', '.azw3'):
            # MOBI/AZW: always use sidecar (format doesn't support metadata editing)
            self._save_mobi_metadata(path, metadata)
        elif file_type in ('.cbz', '.cbr'):
            self._save_comic_metadata(path, metadata)
        else:
            # Unknown formats: use Markdown sidecar
            self._save_sidecar_metadata(path, metadata)

    def _save_markdown_metadata(self, path: Path, metadata: dict):
        """Sla metadata op in een markdown bestand.

        Gebruikt altijd YAML frontmatter. Als er nog geen frontmatter is,
        wordt deze automatisch toegevoegd aan het begin van het bestand.
        """
        field_names = self.custom.get('field_names', {})

        try:
            content = path.read_text(encoding='utf-8')

            # Altijd YAML frontmatter gebruiken - _update_yaml_frontmatter()
            # voegt automatisch frontmatter toe als die ontbreekt
            content = self._update_yaml_frontmatter(content, metadata, field_names)

            path.write_text(content, encoding='utf-8')
        except Exception as e:
            print(f"Error saving markdown metadata: {e}")
            raise

    def _update_yaml_frontmatter(self, content: str, metadata: dict, field_names: dict) -> str:
        """Update YAML frontmatter met nieuwe metadata.

        Behoudt bestaande velden die niet in metadata zitten.
        Behoudt het originele tag formaat (block-style of inline).
        """
        # Vind einde van frontmatter
        if not content.startswith('---'):
            # Geen frontmatter - voeg toe
            frontmatter_lines = ['---']
            for key, value in metadata.items():
                if value:  # Skip lege waarden
                    field_name = field_names.get(key, key)
                    if key == 'tags' and isinstance(value, list):
                        frontmatter_lines.append(f"{field_name}: [{', '.join(value)}]")
                    elif key in ('description', 'notes') and '\n' in str(value):
                        # Multiline waarden
                        frontmatter_lines.append(f"{field_name}: |")
                        for line in str(value).split('\n'):
                            frontmatter_lines.append(f"  {line}")
                    else:
                        frontmatter_lines.append(f"{field_name}: {value}")
            frontmatter_lines.append('---')
            frontmatter_lines.append('')
            return '\n'.join(frontmatter_lines) + content

        # Vind tweede ---
        second_dash = content.find('---', 3)
        if second_dash == -1:
            return content  # Ongeldige frontmatter

        frontmatter = content[3:second_dash].strip()
        rest = content[second_dash + 3:]

        # Detecteer of tags in block-style zijn (tags:\n  - tag1\n  - tag2)
        tags_field = field_names.get('tags', 'tags')
        tags_is_block_style = bool(re.search(
            rf'^{re.escape(tags_field)}:\s*$\n\s+-',
            frontmatter, re.MULTILINE | re.IGNORECASE
        ))

        # Parse en update frontmatter
        new_lines = []
        updated_fields = set()
        skip_block_items = False  # Flag om block-style tag items over te slaan

        for line in frontmatter.split('\n'):
            # Check of we in block-style tag items zitten die we moeten skippen
            if skip_block_items:
                if re.match(r'^\s+-\s+', line):
                    # Dit is een block-style tag item, skip het
                    continue
                else:
                    # Geen block item meer, stop met skippen
                    skip_block_items = False

            # Check of deze regel een veld is dat we updaten
            updated = False
            for key, value in metadata.items():
                field_name = field_names.get(key, key)
                pattern = rf'^{re.escape(field_name)}:\s*'
                if re.match(pattern, line, re.IGNORECASE):
                    # Update dit veld
                    if value:  # Alleen als er een waarde is
                        if key == 'tags' and isinstance(value, list):
                            if tags_is_block_style:
                                # Behoud block-style formaat
                                new_lines.append(f"{field_name}:")
                                for tag in value:
                                    new_lines.append(f"  - {tag}")
                                # Skip de oude block items
                                skip_block_items = True
                            else:
                                # Inline formaat
                                new_lines.append(f"{field_name}: [{', '.join(value)}]")
                        elif key in ('description', 'notes') and '\n' in str(value):
                            new_lines.append(f"{field_name}: |")
                            for l in str(value).split('\n'):
                                new_lines.append(f"  {l}")
                        else:
                            new_lines.append(f"{field_name}: {value}")
                    updated_fields.add(key)
                    updated = True
                    break
            if not updated:
                new_lines.append(line)

        # Voeg nieuwe velden toe die nog niet bestonden
        for key, value in metadata.items():
            if key not in updated_fields and value:
                field_name = field_names.get(key, key)
                if key == 'tags' and isinstance(value, list):
                    new_lines.append(f"{field_name}: [{', '.join(value)}]")
                elif key in ('description', 'notes') and '\n' in str(value):
                    new_lines.append(f"{field_name}: |")
                    for l in str(value).split('\n'):
                        new_lines.append(f"  {l}")
                else:
                    new_lines.append(f"{field_name}: {value}")

        return '---\n' + '\n'.join(new_lines) + '\n---' + rest

    def _save_epub_metadata(self, path: Path, metadata: dict):
        """Sla metadata op in een EPUB bestand.

        Update OPF metadata binnen de EPUB.
        Gebruikt lxml voor correcte namespace handling (ElementTree verliest namespace prefixes).
        """
        import zipfile
        from lxml import etree

        DC_NS = 'http://purl.org/dc/elements/1.1/'
        OPF_NS = 'http://www.idpf.org/2007/opf'

        # Namespace map voor lxml queries
        nsmap = {
            'dc': DC_NS,
            'opf': OPF_NS,
        }

        try:
            # Lees EPUB en vind OPF
            opf_path = None
            opf_content = None

            with zipfile.ZipFile(path, 'r') as zf:
                # Vind OPF via container.xml
                try:
                    container_xml = zf.read('META-INF/container.xml')
                    container = etree.fromstring(container_xml)
                    rootfile = container.find('.//{urn:oasis:names:tc:opendocument:xmlns:container}rootfile')
                    if rootfile is not None:
                        opf_path = rootfile.get('full-path')
                except Exception:
                    pass

                if not opf_path:
                    opf_files = [n for n in zf.namelist() if n.endswith('.opf')]
                    if opf_files:
                        opf_path = opf_files[0]

                if not opf_path:
                    raise ValueError("No OPF file found in EPUB")

                opf_content = zf.read(opf_path)

            # Parse OPF met lxml (behoudt namespaces correct)
            parser = etree.XMLParser(remove_blank_text=False)
            opf = etree.fromstring(opf_content, parser)

            # Zoek metadata element
            metadata_elem = opf.find('opf:metadata', nsmap)
            if metadata_elem is None:
                metadata_elem = opf.find('{%s}metadata' % OPF_NS)
            if metadata_elem is None:
                metadata_elem = opf.find('metadata')
            if metadata_elem is None:
                raise ValueError("No metadata element in OPF")

            # Update metadata velden
            # Dublin Core elementen voor standaard metadata
            field_mapping = {
                'booktitle': 'dc:title',
                'author': 'dc:creator',
                'publisher': 'dc:publisher',
                'language': 'dc:language',
                'description': 'dc:description',
            }

            # Helper om DC element te vinden (met of zonder namespace)
            def find_dc_elem(tag_name):
                # Probeer met namespace prefix
                elem = metadata_elem.find(f'dc:{tag_name}', nsmap)
                if elem is not None:
                    return elem
                # Probeer met Clark notatie
                elem = metadata_elem.find('{%s}%s' % (DC_NS, tag_name))
                if elem is not None:
                    return elem
                # Probeer zonder namespace
                return metadata_elem.find(tag_name)

            # Update Dublin Core velden
            for key, dc_tag in field_mapping.items():
                if key in metadata and metadata[key]:
                    tag_name = dc_tag.split(':')[1]  # 'dc:title' -> 'title'
                    elem = find_dc_elem(tag_name)

                    # Als niet gevonden, maak nieuw element met juiste namespace
                    if elem is None:
                        elem = etree.SubElement(metadata_elem, '{%s}%s' % (DC_NS, tag_name))

                    elem.text = metadata[key]

            # ISBN apart behandelen - zoek specifiek naar identifier met ISBN scheme
            if 'isbn' in metadata and metadata['isbn']:
                isbn_value = metadata['isbn']
                isbn_elem = None

                # Zoek naar identifier met opf:scheme="ISBN" of id die isbn bevat
                # Check beide namespace varianten voor scheme attribuut
                for identifier in metadata_elem.findall('dc:identifier', nsmap):
                    scheme = identifier.get('{%s}scheme' % OPF_NS, '')
                    if not scheme:
                        scheme = identifier.get('scheme', '')
                    elem_id = identifier.get('id', '').lower()
                    if scheme.upper() == 'ISBN' or 'isbn' in elem_id:
                        isbn_elem = identifier
                        break

                # Als geen ISBN-specifieke identifier gevonden
                if isbn_elem is None:
                    identifiers = metadata_elem.findall('dc:identifier', nsmap)
                    if identifiers:
                        # Gebruik eerste identifier alleen als die geen UUID lijkt
                        first_id = identifiers[0]
                        if first_id.text and 'urn:uuid:' not in first_id.text:
                            isbn_elem = first_id
                        else:
                            # Maak nieuwe identifier voor ISBN
                            isbn_elem = etree.SubElement(metadata_elem, '{%s}identifier' % DC_NS)
                            isbn_elem.set('{%s}scheme' % OPF_NS, 'ISBN')
                    else:
                        isbn_elem = etree.SubElement(metadata_elem, '{%s}identifier' % DC_NS)
                        isbn_elem.set('{%s}scheme' % OPF_NS, 'ISBN')

                isbn_elem.text = isbn_value

            # Tags (dc:subject) - verwijder bestaande en voeg nieuwe toe
            if 'tags' in metadata:
                # Verwijder bestaande subjects
                for subject in metadata_elem.findall('dc:subject', nsmap):
                    metadata_elem.remove(subject)
                # Voeg nieuwe toe
                for tag in metadata['tags']:
                    if tag:
                        subj = etree.SubElement(metadata_elem, '{%s}subject' % DC_NS)
                        subj.text = tag

            # Helper functie om meta element te vinden of maken
            def set_meta(name: str, value: str):
                """Zoek of maak <meta name="name" content="value"/>.

                Zoekt zowel namespaced als non-namespaced meta elementen.
                Calibre-gegenereerde EPUBs gebruiken vaak {OPF_NS}meta elementen,
                terwijl andere tools simpele <meta> elementen gebruiken.
                Zonder beide te doorzoeken ontstaan duplicaten.
                """
                # Zoek in beide varianten: met OPF namespace en zonder namespace
                # Sommige EPUBs (vooral Calibre) gebruiken {OPF_NS}meta, anderen gebruiken <meta>
                all_metas = list(metadata_elem.findall('meta'))
                all_metas.extend(metadata_elem.findall('{%s}meta' % OPF_NS))

                for meta in all_metas:
                    if meta.get('name') == name:
                        if value:
                            meta.set('content', value)
                        else:
                            metadata_elem.remove(meta)
                        return
                if value:
                    new_meta = etree.SubElement(metadata_elem, 'meta')
                    new_meta.set('name', name)
                    new_meta.set('content', value)

            # Series en series_index (Calibre compatibel)
            if 'series' in metadata:
                set_meta('calibre:series', metadata['series'])

            if 'series_index' in metadata:
                set_meta('calibre:series_index', metadata['series_index'])

            # Rating (Calibre gebruikt schaal 0-10 intern, wij 0-5)
            if 'rating' in metadata and metadata['rating']:
                try:
                    rating_val = float(metadata['rating'])
                    # Calibre gebruikt 0-10, wij tonen 0-5
                    calibre_rating = str(int(rating_val * 2))
                    set_meta('calibre:rating', calibre_rating)
                except (ValueError, TypeError):
                    pass  # Ongeldige rating waarde, negeren

            # Notes (custom meta element)
            if 'notes' in metadata:
                set_meta('calibre:user_notes', metadata['notes'])

            # Author sort: opf:file-as attribuut op dc:creator element
            if 'author_sort' in metadata and metadata['author_sort']:
                creator_elem = find_dc_elem('creator')
                if creator_elem is not None:
                    creator_elem.set('{%s}file-as' % OPF_NS, metadata['author_sort'])

            # Publication date: gebruik dc:date voor volledige datum
            if 'publication_date' in metadata and metadata['publication_date']:
                date_elem = find_dc_elem('date')
                if date_elem is None:
                    date_elem = etree.SubElement(metadata_elem, '{%s}date' % DC_NS)
                date_elem.text = metadata['publication_date']

            # Pages: meta element voor aantal pagina's
            # Gebruikt rendition:page-count (EPUB3 standaard) en calibre:pages als backup
            if 'pages' in metadata and metadata['pages']:
                set_meta('rendition:page-count', metadata['pages'])
                set_meta('calibre:pages', metadata['pages'])

            # Helper om role attribuut te lezen (robuust voor verschillende namespace varianten)
            def get_role(elem):
                # Probeer met volledige OPF namespace (Clark notatie)
                role = elem.get(f'{{{OPF_NS}}}role')
                if role:
                    return role.lower()
                # Probeer zonder namespace (sommige EPUBs)
                role = elem.get('role')
                if role:
                    return role.lower()
                # Zoek in alle attributen naar iets dat eindigt op 'role'
                for attr_name, attr_val in elem.attrib.items():
                    if attr_name.endswith('role') or attr_name.endswith('}role'):
                        return attr_val.lower()
                return ''

            # Translator: dc:contributor met opf:role="trl"
            if 'translator' in metadata:
                # Verwijder bestaande translators
                contributors_to_remove = []
                for contrib in metadata_elem.findall('dc:contributor', nsmap):
                    if get_role(contrib) == 'trl':
                        contributors_to_remove.append(contrib)
                for contrib in metadata_elem.findall('contributor'):
                    if get_role(contrib) == 'trl':
                        contributors_to_remove.append(contrib)
                for contrib in contributors_to_remove:
                    metadata_elem.remove(contrib)
                # Voeg nieuwe toe als er een waarde is
                if metadata['translator']:
                    trans_elem = etree.SubElement(metadata_elem, '{%s}contributor' % DC_NS)
                    trans_elem.text = metadata['translator']
                    trans_elem.set('{%s}role' % OPF_NS, 'trl')

            # Illustrator: dc:contributor met opf:role="ill"
            if 'illustrator' in metadata:
                # Verwijder bestaande illustrators
                contributors_to_remove = []
                for contrib in metadata_elem.findall('dc:contributor', nsmap):
                    if get_role(contrib) == 'ill':
                        contributors_to_remove.append(contrib)
                for contrib in metadata_elem.findall('contributor'):
                    if get_role(contrib) == 'ill':
                        contributors_to_remove.append(contrib)
                for contrib in contributors_to_remove:
                    metadata_elem.remove(contrib)
                # Voeg nieuwe toe als er een waarde is
                if metadata['illustrator']:
                    ill_elem = etree.SubElement(metadata_elem, '{%s}contributor' % DC_NS)
                    ill_elem.text = metadata['illustrator']
                    ill_elem.set('{%s}role' % OPF_NS, 'ill')

            # Schrijf terug naar EPUB met lxml (behoudt namespaces correct)
            # Let op: lxml vereist bytes encoding voor xml_declaration=True
            new_opf_content = etree.tostring(opf, encoding='UTF-8', xml_declaration=True).decode('utf-8')

            fd, temp_path = tempfile.mkstemp(suffix='.epub')
            os.close(fd)

            try:
                # Kopieer alle bestanden naar temp
                all_files = []
                with zipfile.ZipFile(path, 'r') as zf_in:
                    for item in zf_in.infolist():
                        if item.filename == opf_path:
                            all_files.append((item, new_opf_content.encode('utf-8'), True))
                        else:
                            data = zf_in.read(item.filename)
                            all_files.append((item, data, False))

                with zipfile.ZipFile(temp_path, 'w') as zf_out:
                    for item, data, is_opf in all_files:
                        if is_opf:
                            zf_out.writestr(item, data, compress_type=zipfile.ZIP_DEFLATED)
                        else:
                            zf_out.writestr(item, data, compress_type=item.compress_type)

                # Vervang origineel
                import gc
                gc.collect()

                import time
                max_retries = 5
                for attempt in range(max_retries):
                    try:
                        os.replace(temp_path, path)
                        break
                    except PermissionError:
                        if attempt < max_retries - 1:
                            time.sleep(0.1)
                            gc.collect()
                        else:
                            import shutil
                            shutil.copy2(temp_path, path)
                            os.unlink(temp_path)

            except Exception as e:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
                raise

        except Exception as e:
            print(f"Error saving EPUB metadata: {e}")
            raise

    def _save_pdf_metadata(self, path: Path, metadata: dict):
        """Sla metadata op in een PDF bestand.

        PDF ondersteunt beperkte native metadata:
        - title, author, subject (tags - Calibre-compatibel), keywords (behouden)

        Tags worden in het subject veld opgeslagen met komma-spatie separator.
        Description past niet in PDF en gaat naar de Markdown sidecar.

        Extra velden (isbn, year, language, series, series_index, rating, notes,
        description, etc.) worden opgeslagen in een Markdown sidecar file.

        Als PDF succesvol wordt opgeslagen, worden tags NIET naar de sidecar geschreven.
        Dit voorkomt duplicatie en zorgt dat de sidecar alleen extra velden bevat.
        """
        pdf_saved = False

        # Probeer native PDF metadata op te slaan
        try:
            try:
                import pymupdf as fitz
            except ImportError:
                import fitz

            doc = fitz.open(str(path))
            current_meta = doc.metadata

            # Native PDF velden
            # Tags worden in 'subject' veld opgeslagen (Calibre-compatibel).
            # Het 'keywords' veld wordt vaak misbruikt voor URLs/generator info,
            # dus we laten dat met rust en gebruiken subject voor tags.
            # Description wordt NIET in PDF opgeslagen (geen geschikt veld) - alleen in sidecar.
            new_meta = {
                'title': metadata.get('booktitle', current_meta.get('title', '')),
                'author': metadata.get('author', current_meta.get('author', '')),
                'subject': ', '.join(metadata.get('tags', [])),
                'keywords': current_meta.get('keywords', ''),  # Behoud origineel
                'creator': current_meta.get('creator', ''),
                'producer': current_meta.get('producer', ''),
                'creationDate': current_meta.get('creationDate', ''),
                'modDate': current_meta.get('modDate', ''),
            }

            doc.set_metadata(new_meta)

            # Save
            try:
                doc.save(str(path), incremental=True, encryption=fitz.PDF_ENCRYPT_KEEP)
                pdf_saved = True
            except Exception:
                import tempfile
                fd, temp_path = tempfile.mkstemp(suffix='.pdf')
                os.close(fd)
                try:
                    doc.save(temp_path, garbage=4, deflate=True)
                    doc.close()
                    import shutil
                    shutil.move(temp_path, path)
                    pdf_saved = True
                except Exception:
                    if os.path.exists(temp_path):
                        os.unlink(temp_path)
                    raise

            doc.close()

        except ImportError:
            print("PyMuPDF not installed - using sidecar for all PDF metadata")
        except Exception as e:
            print(f"Error saving native PDF metadata: {e}")

        # Sidecar ALLEEN voor velden die PDF niet native ondersteunt
        # PDF native: title, author, subject (nu gebruikt voor tags), keywords (behouden)
        # PDF mist: isbn, language, series, series_index, rating, notes, publisher,
        #           author_sort, publication_date, pages, translator, illustrator, description
        # Description gaat naar sidecar omdat subject voor tags wordt gebruikt.
        extra_fields = ['isbn', 'language', 'series', 'series_index', 'rating', 'notes', 'publisher',
                        'author_sort', 'publication_date', 'pages', 'translator', 'illustrator', 'description']

        # Bouw metadata dict met alleen de extra velden (geen duplicaten met PDF)
        sidecar_metadata = {}
        for field in extra_fields:
            if field in metadata and metadata[field]:
                sidecar_metadata[field] = metadata[field]

        # Voor problematische PDFs waar native save faalde: alle native velden ook naar sidecar
        if not pdf_saved:
            native_fields = ['booktitle', 'author', 'description', 'tags']
            for field in native_fields:
                if metadata.get(field):
                    sidecar_metadata[field] = metadata[field]

        # Alleen sidecar aanmaken/updaten als er extra data is
        if sidecar_metadata:
            self._save_sidecar_metadata(path, sidecar_metadata)
        else:
            # Geen extra data - verwijder eventuele bestaande sidecar
            from core.metadata_extractor import get_sidecar_path
            sidecar_path = get_sidecar_path(path)
            if sidecar_path.exists():
                try:
                    sidecar_path.unlink()
                except Exception:
                    pass

    def _save_mobi_metadata(self, path: Path, metadata: dict):
        """Sla metadata op voor MOBI/AZW via Markdown sidecar."""
        self._save_sidecar_metadata(path, metadata)

    def _save_comic_metadata(self, path: Path, metadata: dict):
        """Sla metadata op voor comic bestanden.

        CBZ: ComicInfo.xml
        CBR: Markdown sidecar
        """
        if path.suffix.lower() == '.cbr':
            self._save_sidecar_metadata(path, metadata)
            return

        # CBZ: update ComicInfo.xml
        import zipfile
        import xml.etree.ElementTree as ET

        try:
            comicinfo_content = None
            comicinfo_exists = False

            with zipfile.ZipFile(path, 'r') as zf:
                for name in zf.namelist():
                    if name.lower() == 'comicinfo.xml':
                        comicinfo_content = zf.read(name).decode('utf-8')
                        comicinfo_exists = True
                        break

            if comicinfo_content:
                root = ET.fromstring(comicinfo_content)
            else:
                root = ET.Element('ComicInfo')

            # Update velden
            # ComicInfo.xml ondersteunt deze standaard velden:
            field_mapping = {
                'booktitle': 'Title',
                'author': 'Writer',
                'publisher': 'Publisher',
                'description': 'Summary',
                'notes': 'Notes',
                'series': 'Series',
                'series_index': 'Number',
                'language': 'LanguageISO',
                'pages': 'PageCount',
                # Illustrator wordt opgeslagen als Penciller (meest gebruikte artist role)
                'illustrator': 'Penciller',
                # Translator is geen standaard ComicInfo veld, maar we voegen het toe
                # voor compatibiliteit (sommige readers ondersteunen het)
                'translator': 'Translator',
            }

            for key, xml_field in field_mapping.items():
                if key in metadata and metadata[key]:
                    elem = root.find(xml_field)
                    if elem is None:
                        elem = ET.SubElement(root, xml_field)
                    elem.text = str(metadata[key])
                elif key in metadata and not metadata[key]:
                    # Verwijder element als waarde leeg is
                    elem = root.find(xml_field)
                    if elem is not None:
                        root.remove(elem)

            # Tags
            if 'tags' in metadata:
                tags_elem = root.find('Tags')
                if tags_elem is None:
                    tags_elem = ET.SubElement(root, 'Tags')
                if metadata['tags']:
                    tags_elem.text = ', '.join(metadata['tags'])
                else:
                    root.remove(tags_elem)

            # Rating: ComicInfo gebruikt CommunityRating (schaal 0-5)
            if 'rating' in metadata:
                rating_elem = root.find('CommunityRating')
                if metadata['rating']:
                    if rating_elem is None:
                        rating_elem = ET.SubElement(root, 'CommunityRating')
                    rating_elem.text = str(metadata['rating'])
                elif rating_elem is not None:
                    root.remove(rating_elem)

            # Extra velden die ComicInfo.xml niet ondersteunt worden via sidecar opgeslagen
            # Dit zijn: isbn, author_sort, publication_date
            extra_fields = ['isbn', 'author_sort', 'publication_date']
            sidecar_metadata = {}
            for field in extra_fields:
                if field in metadata and metadata[field]:
                    sidecar_metadata[field] = metadata[field]

            # Sla extra velden op in sidecar als er data is
            if sidecar_metadata:
                from core.metadata_extractor import get_sidecar_path, write_sidecar_metadata
                sidecar_path = get_sidecar_path(path)
                write_sidecar_metadata(sidecar_path, sidecar_metadata)
            else:
                # Verwijder eventuele bestaande sidecar als geen extra velden meer nodig
                from core.metadata_extractor import get_sidecar_path
                sidecar_path = get_sidecar_path(path)
                if sidecar_path.exists():
                    try:
                        sidecar_path.unlink()
                    except Exception:
                        pass

            new_comicinfo = ET.tostring(root, encoding='unicode', xml_declaration=True)

            # Schrijf terug
            import tempfile
            fd, temp_path = tempfile.mkstemp(suffix='.cbz')
            os.close(fd)

            try:
                with zipfile.ZipFile(path, 'r') as zf_in:
                    with zipfile.ZipFile(temp_path, 'w') as zf_out:
                        for item in zf_in.infolist():
                            if item.filename.lower() == 'comicinfo.xml':
                                zf_out.writestr(item, new_comicinfo.encode('utf-8'),
                                               compress_type=zipfile.ZIP_DEFLATED)
                            else:
                                data = zf_in.read(item.filename)
                                zf_out.writestr(item, data, compress_type=item.compress_type)

                        if not comicinfo_exists:
                            zf_out.writestr('ComicInfo.xml', new_comicinfo.encode('utf-8'),
                                           compress_type=zipfile.ZIP_DEFLATED)

                if path.exists():
                    os.unlink(path)
                import shutil
                shutil.move(temp_path, path)

            except Exception as e:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
                raise

        except Exception as e:
            print(f"Error saving comic metadata: {e}")
            raise

    def _save_sidecar_metadata(self, path: Path, metadata: dict):
        """Sla metadata op in een Markdown sidecar file (YAML frontmatter).

        Gebruikt voor formaten die geen native metadata ondersteunen.
        """
        from core.metadata_extractor import get_sidecar_path, write_sidecar_metadata

        sidecar_path = get_sidecar_path(path)
        write_sidecar_metadata(sidecar_path, metadata)

    def _start_async_tag_save(self, widgets_by_path: dict, tags_to_remove: set,
                               tags_to_add: set, selected_widgets: list,
                               deselect_callback):
        """Start async batch processing for saving tags.

        Ondersteunt meerdere tags tegelijk toevoegen of verwijderen.
        Shows progress with time estimate.

        Args:
            widgets_by_path: Dict met path -> list van widgets
            tags_to_remove: Set van tags om te verwijderen (lowercase)
            tags_to_add: Set van tags om toe te voegen (lowercase)
            selected_widgets: Lijst van geselecteerde widgets
            deselect_callback: Callback om widgets te deselecteren na afloop
        """
        import time

        # Cancel any existing tag save batch
        if hasattr(self, '_tag_save_batch_event') and self._tag_save_batch_event:
            self._tag_save_batch_event.cancel()
            self._tag_save_batch_event = None

        # Convert dict to list for batch processing
        self._pending_tag_save_items = list(widgets_by_path.items())
        self._tag_save_batch_index = 0
        self._tag_save_modified_count = 0
        self._tag_save_start_time = time.time()
        self._tag_save_tags_to_remove = tags_to_remove
        self._tag_save_tags_to_add = tags_to_add  # Nu een set ipv enkele string
        self._tag_save_selected_widgets = selected_widgets
        self._tag_save_deselect_callback = deselect_callback

        total = len(self._pending_tag_save_items)
        if total == 0:
            deselect_callback()
            return

        self.status_label.text = f"Saving tags... 0/{total}"
        self._process_tag_save_batch()

    def _process_tag_save_batch(self, dt=None):
        """Process a batch of files for tag saving.

        Shows progress with time estimate.
        Ondersteunt meerdere tags tegelijk toevoegen.
        """
        import time

        items = self._pending_tag_save_items
        if not items:
            return

        tags_to_remove = self._tag_save_tags_to_remove
        tags_to_add = self._tag_save_tags_to_add  # Nu een set van tags
        start_idx = self._tag_save_batch_index
        total = len(items)

        # Process one file at a time (file operations can be slow)
        if start_idx >= total:
            self._finish_tag_save()
            return

        path_str, widgets = items[start_idx]
        path = Path(path_str)

        try:
            # Wijzig tags voor dit bestand
            file_modified = False
            if self._modify_file_tags(path, tags_to_remove, tags_to_add):
                self._tag_save_modified_count += len(widgets)
                file_modified = True

            # Update widget tags in-memory ALLEEN als file succesvol gewijzigd is
            # Dit voorkomt dat de UI een andere staat toont dan het bestand
            if file_modified:
                for widget in widgets:
                    current_tags = list(widget.tags) if widget.tags else []
                    # Verwijder tags die in tags_to_remove zitten (case-sensitive)
                    new_tags = [t for t in current_tags if t not in tags_to_remove]
                    # Voeg alle nieuwe tags toe die er nog niet zijn
                    for tag in tags_to_add:
                        if tag not in new_tags:
                            new_tags.append(tag)
                    widget.tags = new_tags
                    if hasattr(widget, '_draw_document_type_triangle'):
                        widget._draw_document_type_triangle()

                # Update file cache - invalidate zodat volgende load verse data haalt
                self.file_cache.invalidate(path)

        except Exception as e:
            print(f"Error modifying tags for {path}: {e}")

        self._tag_save_batch_index += 1
        current_idx = self._tag_save_batch_index

        # Update status with time estimate
        progress = int((current_idx / total) * 100) if total > 0 else 100
        elapsed = time.time() - self._tag_save_start_time

        if progress > 0 and progress < 100:
            estimated_total = elapsed / (progress / 100)
            remaining = estimated_total - elapsed
            if remaining > 60:
                time_str = f"~{int(remaining / 60)} min remaining"
            else:
                time_str = f"~{int(remaining)} sec remaining"
            self.status_label.text = f"Saving tags... {current_idx}/{total} - {time_str}"
        else:
            self.status_label.text = f"Saving tags... {current_idx}/{total}"

        if current_idx < total:
            # More to process - schedule next file
            self._tag_save_batch_event = Clock.schedule_once(
                self._process_tag_save_batch, 0)
        else:
            self._finish_tag_save()

    def _finish_tag_save(self):
        """Finish tag save operation and update UI.

        Na tag wijziging wordt altijd een volledige refresh gedaan zodat
        grid en tag lijst consistent blijven. De tag lijst scant recursief
        alle subfolders, dus na een wijziging moet het hele scherm herbouwd.
        """
        modified_count = self._tag_save_modified_count

        # Deselecteer alle items VOOR refresh (anders raken we widget referenties kwijt)
        if hasattr(self, '_tag_save_deselect_callback') and self._tag_save_deselect_callback:
            self._tag_save_deselect_callback()

        if modified_count > 0:
            # Volledige refresh voor consistente weergave
            self._refresh()
            self.status_label.text = f"Updated tags for {modified_count} item(s)"
        else:
            self.status_label.text = "No tags were modified"

    def _incremental_tag_filter_update(self):
        """Incrementele update van grid na tag wijziging met actieve tag filter.

        Checkt alleen de gewijzigde widgets of ze nog aan de filter criteria
        voldoen. Items die niet meer matchen (tag verwijderd) worden uit het
        grid verwijderd. Dit is veel sneller dan de hele filter opnieuw draaien.
        """
        tag = self._tag_filter_tag
        if not tag:
            return

        widgets_to_remove = []
        widgets_modified = getattr(self, '_tag_save_selected_widgets', [])

        for widget in widgets_modified:
            # Check of widget nog in grid zit
            if widget.parent != self.grid:
                continue

            # Check of widget nog steeds de gefilterde tag heeft (case-sensitive)
            widget_tags = []
            if hasattr(widget, 'tags') and widget.tags:
                widget_tags = [t.strip() for t in widget.tags if t]

            if tag not in widget_tags:
                # Tag is verwijderd - widget moet uit grid
                widgets_to_remove.append(widget)

        # Verwijder widgets die niet meer matchen
        for widget in widgets_to_remove:
            self.grid.remove_widget(widget)
            self._file_count -= 1

        # Update status met nieuw aantal
        if self._file_count == 0:
            self.status_label.text = f"No books found with tag #{tag}"
        else:
            self.status_label.text = f"{self._file_count} books with #{tag}"

        # Update tag lijst (kan nieuwe tags bevatten of tags verwijderen)
        self._schedule_tag_list_update()

    def _incremental_no_tag_filter_update(self):
        """Incrementele update van grid na tag wijziging met 'No tag' filter actief.

        Checkt alleen de gewijzigde widgets of ze nog geen tags hebben.
        Items die nu wel tags hebben worden uit het grid verwijderd.
        """
        widgets_to_remove = []
        widgets_modified = getattr(self, '_tag_save_selected_widgets', [])

        for widget in widgets_modified:
            # Check of widget nog in grid zit
            if widget.parent != self.grid:
                continue

            # Check of widget nu tags heeft (dan moet hij weg uit No tag filter)
            widget_tags = []
            if hasattr(widget, 'tags') and widget.tags:
                widget_tags = [t for t in widget.tags if t]

            if widget_tags:
                # Widget heeft nu tags - verwijder uit grid
                widgets_to_remove.append(widget)

        # Verwijder widgets die niet meer matchen
        for widget in widgets_to_remove:
            self.grid.remove_widget(widget)
            self._file_count -= 1

        # Update status met nieuw aantal
        if self._file_count == 0:
            self.status_label.text = "No books without tags"
        else:
            self.status_label.text = f"{self._file_count} books without tags"

        # Update tag lijst (de toegevoegde tags moeten verschijnen)
        self._schedule_tag_list_update()

    def _modify_file_tags(self, path: Path, tags_to_remove: set, tags_to_add: set) -> bool:
        """Modify tags in a file.

        Supports adding/removing multiple tags at once.

        Args:
            path: Path to the file
            tags_to_remove: Set of tags to remove (case-sensitive)
            tags_to_add: Set of tags to add (case-sensitive)

        Returns:
            True if file was modified, False otherwise

        Supports:
        - Markdown files with tags: [tag1, tag2] format
        - EPUB files via dc:subject elements in OPF
        - PDF files via subject metadata field (Calibre-compatible, requires PyMuPDF)
        - MOBI/AZW/AZW3 files via Markdown sidecar (MOBI itself unreliable)

        When 'metadata_in_sidecar' setting is True, tags are stored in sidecar
        files instead of in the book files themselves.

        Creates automatic backup in system temp directory for each change.
        """
        from core.metadata_extractor import modify_sidecar_tags

        file_type = path.suffix.lower()
        use_sidecar = self.custom.get('metadata_in_sidecar', False)

        if file_type in ('.md', '.markdown'):
            # Markdown files: always modify the file itself
            return self._modify_markdown_tags(path, tags_to_remove, tags_to_add)
        elif use_sidecar and file_type in ('.epub', '.pdf', '.cbz', '.cbr'):
            # User prefers sidecar: modify tags in sidecar file
            return modify_sidecar_tags(path, tags_to_remove, tags_to_add)
        elif file_type == '.epub':
            return self._modify_epub_tags(path, tags_to_remove, tags_to_add)
        elif file_type == '.pdf':
            return self._modify_pdf_tags(path, tags_to_remove, tags_to_add)
        elif file_type in ('.mobi', '.azw', '.azw3'):
            # MOBI/AZW: always use sidecar (format doesn't support reliable metadata editing)
            return self._modify_mobi_tags(path, tags_to_remove, tags_to_add)
        elif file_type in ('.cbz', '.cbr'):
            return self._modify_comic_tags(path, tags_to_remove, tags_to_add)
        elif file_type == '.opf':
            # OPF files are legacy sidecar files - skip
            return False
        else:
            # For all other file formats (.rtf, .mp3, .txt, etc.):
            # Use Markdown sidecar file for tag storage
            return modify_sidecar_tags(path, tags_to_remove, tags_to_add)

    def _create_temp_backup(self, path: Path) -> Path:
        """Maak een tijdelijke backup van een bestand.

        Backups worden in de systeem temp directory gemaakt, zodat ze niet
        zichtbaar zijn in Libiry. Bij het afsluiten van de app worden alle
        resterende backups automatisch opgeruimd.

        Args:
            path: Path naar het te backuppen bestand

        Returns:
            Path naar de backup file
        """
        # Initialiseer backup tracking lijst als die nog niet bestaat
        if not hasattr(self, '_temp_backups'):
            self._temp_backups = []

        # Gebruik systeem temp directory - onzichtbaar voor Libiry
        backup_dir = Path(tempfile.gettempdir()) / 'Libirybackup'
        backup_dir.mkdir(exist_ok=True)

        # Unieke bestandsnaam om conflicten te voorkomen
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        backup_filename = f"{path.stem}_{timestamp}{path.suffix}"
        backup_path = backup_dir / backup_filename
        shutil.copy2(path, backup_path)

        # Track deze backup voor cleanup bij app exit
        self._temp_backups.append(backup_path)

        return backup_path

    def _remove_temp_backup(self, backup_path: Path):
        """Verwijder een tijdelijke backup na succesvolle wijziging.

        Args:
            backup_path: Path naar de backup file
        """
        try:
            if backup_path.exists():
                backup_path.unlink()
            # Verwijder uit tracking lijst
            if hasattr(self, '_temp_backups') and backup_path in self._temp_backups:
                self._temp_backups.remove(backup_path)
        except Exception as e:
            print(f"Warning: Could not remove backup {backup_path}: {e}")

    def _cleanup_all_backups(self):
        """Verwijder alle resterende tijdelijke backups.

        Wordt aangeroepen bij het afsluiten van de app om te zorgen dat
        er geen backup bestanden achterblijven, ook niet na mislukte acties.
        """
        # Verwijder getrackte backups
        if hasattr(self, '_temp_backups'):
            for backup_path in self._temp_backups[:]:  # Copy lijst om tijdens iteratie te verwijderen
                try:
                    if backup_path.exists():
                        backup_path.unlink()
                except Exception as e:
                    print(f"Warning: Could not remove backup {backup_path}: {e}")
            self._temp_backups.clear()

        # Verwijder ook de backup folder als die leeg is
        backup_dir = Path(tempfile.gettempdir()) / 'Libirybackup'
        if backup_dir.exists():
            try:
                # Verwijder alle resterende bestanden in de backup folder
                for f in backup_dir.iterdir():
                    try:
                        f.unlink()
                    except Exception:
                        pass
                # Probeer de folder te verwijderen als die leeg is
                if not any(backup_dir.iterdir()):
                    backup_dir.rmdir()
            except Exception:
                pass

    def _modify_markdown_tags(self, path: Path, tags_to_remove: set, tags_to_add: set) -> bool:
        """Modify tags in a markdown file.

        Ondersteunt meerdere tags tegelijk toevoegen of verwijderen.

        Ondersteunt drie tag formaten (consistent met metadata_extractor):
        1. YAML inline array: tags: [fiction, sci-fi]
        2. YAML block list: tags:\n  - fiction\n  - sci-fi
        3. Komma-gescheiden: tags: fiction, sci-fi

        Het originele formaat wordt behouden bij wijzigingen.
        """
        # Haal geconfigureerde veldnamen op
        tags_field = 'tags'
        cover_field = 'cover'
        if hasattr(self, 'custom') and 'field_names' in self.custom:
            tags_field = self.custom['field_names'].get('tags', 'tags')
            cover_field = self.custom['field_names'].get('cover', 'cover')

        try:
            content = path.read_text(encoding='utf-8')

            # Wijzig hele bestand
            new_content, was_modified, needs_frontmatter = self._modify_tags_in_section(
                content, tags_field, tags_to_remove, tags_to_add
            )

            if needs_frontmatter and tags_to_add:
                # Bestand heeft geen cover: veld en geen tags: veld
                # Voeg YAML frontmatter toe bovenaan met cover (bestandsnaam) en alle tags
                # Dit maakt het bestand herkenbaar als boek in Libiry
                cover_name = path.stem  # Bestandsnaam zonder extensie
                tags_str = ', '.join(sorted(tags_to_add))
                frontmatter = f"---\ncover: {cover_name}\n{tags_field}: [{tags_str}]\n---\n\n"
                new_content = frontmatter + content
                was_modified = True

            if was_modified:
                path.write_text(new_content, encoding='utf-8')
                return True

        except Exception as e:
            print(f"Error modifying tags in {path}: {e}")
            import traceback
            traceback.print_exc()

        return False

    def _modify_tags_in_section(self, content: str, tags_field: str,
                                 tags_to_remove: set, tags_to_add: set) -> tuple:
        """Wijzig tags binnen een sectie van markdown content.

        Ondersteunt meerdere tags tegelijk toevoegen of verwijderen.

        Args:
            content: De markdown content (of sectie daarvan)
            tags_field: Naam van het tags veld (bijv. "tags")
            tags_to_remove: Set van tags om te verwijderen (lowercase)
            tags_to_add: Set van tags om toe te voegen (lowercase)

        Returns:
            Tuple van (gewijzigde content, bool of er wijzigingen waren, bool of YAML frontmatter nodig is)
            De derde waarde (needs_frontmatter) is True als er geen cover: veld en geen tags
            veld gevonden is, maar wel een tag toegevoegd moet worden. In dat geval moet de
            aanroeper YAML frontmatter toevoegen met cover: en tags:.
        """
        modified = False

        # === Format 1: YAML inline array: tags: [tag1, tag2] ===
        def replace_inline_array(match):
            nonlocal modified
            prefix = match.group(1)  # "tags: " deel
            tags_str = match.group(2)  # inhoud tussen brackets

            # Parse tags (respecteer quotes)
            current_tags = []
            items = re.findall(r'"([^"]+)"|\'([^\']+)\'|([^,\s][^,]*)', tags_str)
            for item in items:
                tag = (item[0] or item[1] or item[2]).strip().strip('"\'')
                if tag:
                    current_tags.append(tag)

            # Pas tags aan: verwijder eerst, voeg dan alle nieuwe toe (case-sensitive)
            new_tags = [t for t in current_tags if t not in tags_to_remove]
            for tag in sorted(tags_to_add):  # Sorteer voor consistente volgorde
                if tag not in new_tags:
                    new_tags.append(tag)

            # Check voor wijzigingen
            if new_tags != current_tags:
                modified = True

            return f"{prefix}[{', '.join(new_tags)}]"

        # Pattern matcht zowel "tags: [...]" als "[tags]: [...]" (flat format)
        # De optionele \[?\]? rond de veldnaam ondersteunt beide formaten
        inline_pattern = rf'(\[?{re.escape(tags_field)}\]?:\s*)\[([^\]]*)\]'
        content = re.sub(inline_pattern, replace_inline_array, content, flags=re.IGNORECASE)

        # === Format 2: YAML block list: tags:\n  - tag1\n  - tag2 ===
        def replace_block_list(match):
            nonlocal modified
            prefix = match.group(1)  # "tags:" deel
            block = match.group(2)   # de list items

            # Parse huidige tags
            current_tags = []
            for line in block.split('\n'):
                line = line.strip()
                if line.startswith('-'):
                    tag = line[1:].strip().strip('"\'')
                    if tag:
                        current_tags.append(tag)

            # Pas tags aan: verwijder eerst, voeg dan alle nieuwe toe (case-sensitive)
            new_tags = [t for t in current_tags if t not in tags_to_remove]
            for tag in sorted(tags_to_add):  # Sorteer voor consistente volgorde
                if tag not in new_tags:
                    new_tags.append(tag)

            # Check voor wijzigingen
            if new_tags != current_tags:
                modified = True

            # Reconstrueer block list met dezelfde indentatie
            indent = "  "  # standaard 2 spaties
            indent_match = re.search(r'\n(\s+)-', block)
            if indent_match:
                indent = indent_match.group(1)

            # Behoud trailing newline als die er was in het origineel
            # Dit voorkomt dat de volgende regel (bijv. comments:) aan de laatste tag plakt
            trailing_newline = '\n' if block.endswith('\n') else ''

            new_block = '\n'.join(f'{indent}- {t}' for t in new_tags)
            return f"{prefix}\n{new_block}{trailing_newline}"

        # Pattern matcht zowel "tags:" als "[tags]:" (flat format) met block list
        block_pattern = rf'(\[?{re.escape(tags_field)}\]?:)\s*$\n((?:\s+-\s+.+\n?)+)'
        content = re.sub(block_pattern, replace_block_list, content, flags=re.MULTILINE | re.IGNORECASE)

        # === Format 3: Komma-gescheiden: tags: tag1, tag2 ===
        def replace_comma_separated(match):
            nonlocal modified
            prefix = match.group(1)  # "tags: " deel
            tags_str = match.group(2)

            # Skip als het met [ begint (dat is format 1 - inline array)
            if tags_str.strip().startswith('['):
                return match.group(0)

            # Skip als het met - begint (dat is format 2 - block list)
            # Dit kan gebeuren als de regex newlines in de prefix matcht
            if tags_str.strip().startswith('-'):
                return match.group(0)

            # Parse huidige tags
            current_tags = [t.strip().strip('"\'') for t in re.split(r'[,;]', tags_str) if t.strip()]

            # Pas tags aan: verwijder eerst, voeg dan alle nieuwe toe (case-sensitive)
            new_tags = [t for t in current_tags if t not in tags_to_remove]
            for tag in sorted(tags_to_add):  # Sorteer voor consistente volgorde
                if tag not in new_tags:
                    new_tags.append(tag)

            # Check voor wijzigingen
            if new_tags != current_tags:
                modified = True

            return f"{prefix}{', '.join(new_tags)}"

        # Pattern matcht zowel "tags: value" als "[tags]: value" (flat format)
        comma_pattern = rf'^(\[?{re.escape(tags_field)}\]?:\s*)(.+?)$'
        content = re.sub(comma_pattern, replace_comma_separated, content, flags=re.MULTILINE | re.IGNORECASE)

        # === Als geen tags veld gevonden en we willen tags toevoegen ===
        # Voeg een nieuw tags veld toe
        if not modified and tags_to_add:
            # Check of er al een tags veld bestaat (in welk formaat dan ook)
            # Matcht zowel "tags:" als "[tags]:" (flat format)
            has_tags_field = re.search(
                rf'^\[?{re.escape(tags_field)}\]?:', content, re.MULTILINE | re.IGNORECASE
            )

            if not has_tags_field:
                # Geen tags veld - voeg er een toe met alle nieuwe tags
                tags_str = ', '.join(sorted(tags_to_add))

                # Bepaal waar we het moeten invoegen:
                # 1. Na YAML frontmatter einde (---)
                # 2. Na laatste metadata veld (cover, booktitle, author, isbn)
                # 3. Aan het begin van het bestand (met nieuwe YAML frontmatter incl. cover)

                # Check voor YAML frontmatter
                yaml_end_match = re.search(r'^---\s*$', content, re.MULTILINE)
                if yaml_end_match and content.startswith('---'):
                    # YAML frontmatter aanwezig - zoek het einde
                    # Zoek de tweede --- (einde van frontmatter)
                    second_dash = content.find('---', 3)
                    if second_dash != -1:
                        # Voeg tags toe net voor het einde van de frontmatter
                        insert_pos = second_dash
                        new_line = f"{tags_field}: [{tags_str}]\n"
                        content = content[:insert_pos] + new_line + content[insert_pos:]
                        modified = True
                else:
                    # Geen YAML frontmatter - zoek naar bestaande metadata velden
                    # Zoek naar cover:, booktitle:, author:, isbn: etc.
                    metadata_patterns = [
                        rf'^\[?{re.escape(tags_field)}\]?:',
                        r'^\[?cover\]?:',
                        r'^\[?booktitle\]?:',
                        r'^\[?author\]?:',
                        r'^\[?isbn\]?:',
                    ]

                    last_metadata_end = 0
                    for pattern in metadata_patterns:
                        for match in re.finditer(pattern, content, re.MULTILINE | re.IGNORECASE):
                            # Vind het einde van deze regel
                            line_end = content.find('\n', match.end())
                            if line_end == -1:
                                line_end = len(content)
                            if line_end > last_metadata_end:
                                last_metadata_end = line_end

                    if last_metadata_end > 0:
                        # Voeg tags toe na het laatste metadata veld
                        # Check of we [tags]: of tags: format moeten gebruiken
                        if re.search(r'^\[cover\]:', content, re.MULTILINE | re.IGNORECASE):
                            # Flat format met brackets
                            new_line = f"\n[{tags_field}]: {tags_str}"
                        else:
                            # YAML-achtig formaat
                            new_line = f"\n{tags_field}: [{tags_str}]"
                        content = content[:last_metadata_end] + new_line + content[last_metadata_end:]
                        modified = True
                    else:
                        # Geen metadata velden gevonden - check of er een cover: veld is
                        # Zo niet, signaleer dat YAML frontmatter nodig is (wordt in
                        # _modify_markdown_tags afgehandeld waar we toegang hebben tot path)
                        has_cover = re.search(r'^\[?cover\]?:', content, re.MULTILINE | re.IGNORECASE)
                        if not has_cover:
                            # Geen cover veld - geef aan dat frontmatter nodig is
                            # Return derde waarde: True = needs_frontmatter
                            return content, modified, True

        return content, modified, False

    def _modify_epub_tags(self, path: Path, tags_to_remove: set, tags_to_add: set) -> bool:
        """Modify tags (dc:subject) in an EPUB file.

        Ondersteunt meerdere tags tegelijk toevoegen of verwijderen.

        PERFORMANCE OPTIMALISATIE (maart 2026):
        Twee-staps aanpak voor maximale snelheid:
        1. SNELLE POGING: ZIP append mode - voeg alleen gewijzigde OPF toe
           Dit is ~50x sneller omdat we niet de hele EPUB herschrijven.
        2. FALLBACK: Als append faalt (file locking), herschrijf de hele EPUB.

        Dit is gebaseerd op het inzicht dat:
        - Append mode werkt voor de meeste bestanden
        - Alleen bij file locking (Windows) is fallback nodig
        - De trage methode is nog steeds betrouwbaar als backup

        Args:
            path: Path naar de EPUB file
            tags_to_remove: Set van tags om te verwijderen (lowercase)
            tags_to_add: Set van tags om toe te voegen (lowercase, lege set = niets toevoegen)

        Returns:
            True als bestand gewijzigd is, False anders
        """
        import zipfile
        import xml.etree.ElementTree as ET

        # Dublin Core namespace voor dc:subject
        DC_NS = 'http://purl.org/dc/elements/1.1/'
        OPF_NS = 'http://www.idpf.org/2007/opf'

        # Registreer namespaces zodat ze behouden blijven bij serialisatie
        # Dit voorkomt dat ElementTree ns0:, ns1: prefixes toevoegt
        ET.register_namespace('dc', DC_NS)
        ET.register_namespace('opf', OPF_NS)
        ET.register_namespace('', OPF_NS)  # default namespace

        try:
            # Check of bestand schrijfbaar is (Windows file locking workaround)
            import stat
            file_stat = os.stat(path)
            if not (file_stat.st_mode & stat.S_IWRITE):
                os.chmod(path, file_stat.st_mode | stat.S_IWRITE)

            # Stap 1: Open EPUB en vind OPF file
            # (Backup is niet nodig: we schrijven eerst naar temp file,
            # origineel wordt pas vervangen bij succes)
            opf_path = None
            opf_content = None

            with zipfile.ZipFile(path, 'r') as zf:
                # Vind OPF via container.xml
                try:
                    container_xml = zf.read('META-INF/container.xml')
                    container = ET.fromstring(container_xml)
                    ns = {'c': 'urn:oasis:names:tc:opendocument:xmlns:container'}
                    rootfile = container.find('.//c:rootfile', ns)
                    if rootfile is None:
                        rootfile = container.find('.//{urn:oasis:names:tc:opendocument:xmlns:container}rootfile')
                    if rootfile is not None:
                        opf_path = rootfile.get('full-path')
                except Exception:
                    pass

                # Fallback: zoek naar .opf file
                if not opf_path:
                    opf_files = [n for n in zf.namelist() if n.endswith('.opf')]
                    if opf_files:
                        opf_path = opf_files[0]

                if not opf_path:
                    print(f"No OPF file found in {path}")
                    return False

                # Lees OPF content
                opf_content = zf.read(opf_path).decode('utf-8')

            # Stap 3: Parse OPF XML
            # Bewaar originele XML declaratie en whitespace zoveel mogelijk
            opf = ET.fromstring(opf_content)

            # Vind metadata element
            metadata = opf.find(f'{{{OPF_NS}}}metadata')
            if metadata is None:
                metadata = opf.find('metadata')
            if metadata is None:
                print(f"No metadata element found in OPF of {path}")
                return False

            # Stap 4: Verzamel huidige tags en pas aan
            current_tags = []
            subjects_to_remove = []

            for subject in metadata.findall(f'{{{DC_NS}}}subject'):
                if subject.text:
                    tag_text = subject.text.strip()
                    if tag_text in tags_to_remove:
                        # Markeer voor verwijdering (case-sensitive)
                        subjects_to_remove.append(subject)
                    else:
                        current_tags.append(tag_text)

            # Verwijder gemarkeerde subjects
            for subject in subjects_to_remove:
                metadata.remove(subject)

            # Voeg alle nieuwe tags toe die er nog niet zijn (case-sensitive)
            tags_added = []
            for tag_to_add in sorted(tags_to_add):  # Sorteer voor consistente volgorde
                if tag_to_add not in current_tags:
                    # Bij eerste dc:subject: zorg dat dc namespace gedeclareerd is
                    # Dit is nodig omdat ElementTree de namespace declaratie verliest
                    # als er geen bestaande dc: elementen zijn
                    if not current_tags and not tags_added:
                        # Zoek een bestaand dc: element om de namespace te behouden
                        # (bijv. dc:title, dc:creator) - als die er is, is dc namespace ok
                        existing_dc = metadata.find(f'{{{DC_NS}}}title')
                        if existing_dc is None:
                            existing_dc = metadata.find(f'{{{DC_NS}}}creator')
                        if existing_dc is None:
                            # Geen bestaande dc: elementen - voeg xmlns:dc toe aan metadata
                            # ElementTree ondersteunt dit niet direct, dus we doen het via attrib
                            # Let op: dit werkt alleen als de namespace nog niet gedeclareerd is
                            metadata.set(f'{{http://www.w3.org/2000/xmlns/}}dc', DC_NS)

                    # Maak nieuw dc:subject element
                    new_subject = ET.SubElement(metadata, f'{{{DC_NS}}}subject')
                    new_subject.text = tag_to_add
                    tags_added.append(tag_to_add)

            # Check of er wijzigingen zijn
            if not subjects_to_remove and not tags_added:
                return False

            # Stap 5: Schrijf gewijzigde OPF terug naar EPUB
            # Serialiseer de XML met correcte encoding
            new_opf_content = ET.tostring(opf, encoding='unicode', xml_declaration=True)

            import tempfile
            # os is al geïmporteerd op module niveau

            # Maak tijdelijk bestand
            fd, temp_path = tempfile.mkstemp(suffix='.epub')
            os.close(fd)

            try:
                # Lees alle bestanden eerst in geheugen om file handles vrij te geven
                # Dit voorkomt file locking problemen op Windows
                all_files = []
                with zipfile.ZipFile(path, 'r') as zf_in:
                    for item in zf_in.infolist():
                        if item.filename == opf_path:
                            # Gebruik gewijzigde OPF content
                            all_files.append((item, new_opf_content.encode('utf-8'), True))
                        else:
                            data = zf_in.read(item.filename)
                            all_files.append((item, data, False))

                # Schrijf naar temp bestand (origineel is nu gesloten)
                # GEEN hercompressie voor snelheid - EPUB kan iets groter worden
                with zipfile.ZipFile(temp_path, 'w') as zf_out:
                    for item, data, is_opf in all_files:
                        if is_opf:
                            # OPF is klein, comprimeer wel voor compatibiliteit
                            zf_out.writestr(item, data, compress_type=zipfile.ZIP_DEFLATED)
                        else:
                            # Behoud originele compressie type voor compatibiliteit
                            zf_out.writestr(item, data, compress_type=item.compress_type)

                # Forceer garbage collection om file handles vrij te geven
                import gc
                gc.collect()

                # Vervang origineel door gewijzigd bestand
                # Windows file locking workaround: retry met kleine delay
                # os.replace() faalt soms op Windows omdat de file handle nog
                # niet volledig vrijgegeven is, zelfs na gc.collect()
                import time
                max_retries = 5
                for attempt in range(max_retries):
                    try:
                        os.replace(temp_path, path)
                        break  # Succes
                    except PermissionError:
                        if attempt < max_retries - 1:
                            time.sleep(0.1)  # Wacht 100ms en probeer opnieuw
                            gc.collect()
                        else:
                            # Laatste poging: probeer shutil.copy + delete
                            try:
                                shutil.copy2(temp_path, path)
                                os.unlink(temp_path)
                            except Exception:
                                raise  # Geef de originele PermissionError door
                return True

            except Exception as e:
                # Bij fout: verwijder temp bestand
                if os.path.exists(temp_path):
                    try:
                        os.unlink(temp_path)
                    except Exception:
                        pass
                raise e

        except Exception as e:
            print(f"Error modifying EPUB tags in {path}: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _modify_pdf_tags(self, path: Path, tags_to_remove: set, tags_to_add: set) -> bool:
        """Modify tags in a PDF file.

        Ondersteunt meerdere tags tegelijk toevoegen of verwijderen.
        Tags worden opgeslagen in het 'subject' veld met komma-spatie separator.

        Probeert ALTIJD eerst de PDF direct te wijzigen. Bij succes worden tags
        uit een eventuele sidecar verwijderd (en de sidecar verwijderd als die leeg is).
        Alleen als PDF schrijven faalt, wordt de Markdown sidecar gebruikt.

        Args:
            path: Path naar de PDF file
            tags_to_remove: Set van tags om te verwijderen
            tags_to_add: Set van tags om toe te voegen

        Returns:
            True als bestand gewijzigd is, False anders
        """
        from core.metadata_extractor import get_sidecar_path, read_sidecar_metadata, write_sidecar_metadata

        # Probeer PyMuPDF te importeren
        try:
            try:
                import pymupdf as fitz
            except ImportError:
                import fitz
        except ImportError:
            print("PyMuPDF (fitz) not installed - cannot modify PDF tags")
            return False

        pdf_saved = False

        try:
            # Open PDF en lees metadata
            doc = fitz.open(str(path))
            metadata = doc.metadata

            # Haal huidige tags uit subject veld (Calibre-compatibel)
            # Tags worden als één string opgeslagen, gescheiden door ', '
            subject_str = metadata.get('subject', '') or ''
            if subject_str:
                current_tags = [t.strip() for t in subject_str.split(', ') if t.strip()]
            else:
                current_tags = []

            # Pas tags aan - verwijder tags (case-sensitive)
            new_tags = [t for t in current_tags if t not in tags_to_remove]
            removed_count = len(current_tags) - len(new_tags)

            # Voeg alle nieuwe tags toe die er nog niet zijn (case-sensitive)
            tags_added = []
            for tag_to_add in sorted(tags_to_add):
                if tag_to_add not in new_tags:
                    new_tags.append(tag_to_add)
                    tags_added.append(tag_to_add)

            # Check of er wijzigingen zijn
            if removed_count == 0 and not tags_added:
                doc.close()
                return False

            # Schrijf nieuwe metadata - tags naar subject veld met komma-spatie separator
            new_subject = ', '.join(new_tags)
            doc.set_metadata({
                'subject': new_subject,
                'title': metadata.get('title', ''),
                'author': metadata.get('author', ''),
                'keywords': metadata.get('keywords', ''),  # Behoud origineel
                'creator': metadata.get('creator', ''),
                'producer': metadata.get('producer', ''),
                'creationDate': metadata.get('creationDate', ''),
                'modDate': metadata.get('modDate', ''),
            })

            # Probeer incremental save
            try:
                doc.save(str(path), incremental=True, encryption=fitz.PDF_ENCRYPT_KEEP)
                pdf_saved = True
            except Exception:
                # Incremental save faalde - probeer full save via temp file
                import tempfile
                import os

                fd, temp_path = tempfile.mkstemp(suffix='.pdf')
                os.close(fd)

                try:
                    doc.save(temp_path, garbage=4, deflate=True)
                    doc.close()
                    shutil.move(temp_path, path)
                    pdf_saved = True
                except Exception as full_error:
                    if os.path.exists(temp_path):
                        os.unlink(temp_path)
                    raise full_error

            doc.close()

        except Exception as e:
            print(f"PDF direct modification failed for {path}: {e}")

        # Als PDF succesvol opgeslagen: verwijder tags uit sidecar
        if pdf_saved:
            sidecar_path = get_sidecar_path(path)
            if sidecar_path.exists():
                # Lees sidecar metadata, verwijder tags, behoud andere velden
                sidecar_meta = read_sidecar_metadata(path)
                if sidecar_meta:
                    # Bouw nieuwe metadata zonder tags
                    remaining_meta = {}
                    for field in ['booktitle', 'author', 'isbn', 'publisher', 'language',
                                  'description', 'series', 'series_index', 'rating', 'notes',
                                  'author_sort', 'publication_date', 'pages', 'translator', 'illustrator']:
                        val = getattr(sidecar_meta, field, None)
                        if val:
                            if field == 'author':
                                # authors is een lijst, author is string
                                remaining_meta[field] = ', '.join(sidecar_meta.authors) if sidecar_meta.authors else ''
                            else:
                                remaining_meta[field] = val

                    # Als er nog andere metadata is, update sidecar zonder tags
                    # Anders verwijder de hele sidecar
                    if any(remaining_meta.values()):
                        write_sidecar_metadata(sidecar_path, remaining_meta)
                    else:
                        try:
                            sidecar_path.unlink()
                        except Exception:
                            pass
            return True

        # PDF schrijven faalde - gebruik sidecar
        print("Using sidecar file for tag storage...")

        # Lees bestaande tags uit PDF (subject veld) of sidecar
        existing_tags = []
        try:
            doc_read = fitz.open(str(path))
            subject_str = doc_read.metadata.get('subject', '') or ''
            if subject_str:
                existing_tags = [t.strip() for t in subject_str.split(', ') if t.strip()]
            doc_read.close()
        except Exception:
            pass

        # Pas tags aan
        new_tags = [t for t in existing_tags if t not in tags_to_remove]
        for tag_to_add in sorted(tags_to_add):
            if tag_to_add not in new_tags:
                new_tags.append(tag_to_add)

        # Schrijf naar sidecar met alle bestaande metadata + nieuwe tags
        sidecar_path = get_sidecar_path(path)
        sidecar_meta = read_sidecar_metadata(path) if sidecar_path.exists() else None

        new_sidecar_data = {}
        if sidecar_meta:
            for field in ['booktitle', 'isbn', 'publisher', 'language', 'description',
                          'series', 'series_index', 'rating', 'notes', 'author_sort',
                          'publication_date', 'pages', 'translator', 'illustrator']:
                val = getattr(sidecar_meta, field, None)
                if val:
                    new_sidecar_data[field] = val
            if sidecar_meta.authors:
                new_sidecar_data['author'] = ', '.join(sidecar_meta.authors)

        new_sidecar_data['tags'] = new_tags if new_tags else ['__tag_in_sidecar__']
        write_sidecar_metadata(sidecar_path, new_sidecar_data)
        return True

    def _modify_mobi_tags(self, path: Path, tags_to_remove: set, tags_to_add: set) -> bool:
        """Modify tags for MOBI/AZW files via Markdown sidecar file.

        Ondersteunt meerdere tags tegelijk toevoegen of verwijderen.

        MOBI/AZW metadata is niet betrouwbaar te wijzigen, dus we gebruiken
        een Markdown sidecar file (zelfde naam, .md extensie) voor tags.
        """
        from core.metadata_extractor import modify_sidecar_tags
        return modify_sidecar_tags(path, tags_to_remove, tags_to_add)

    def _modify_comic_tags(self, path: Path, tags_to_remove: set, tags_to_add: set) -> bool:
        """Modify tags in a CBZ/CBR comic archive.

        Ondersteunt meerdere tags tegelijk toevoegen of verwijderen.

        CBZ: Tags worden opgeslagen in ComicInfo.xml in het archive.
        CBR: Tags worden opgeslagen in Markdown sidecar file (RAR is niet schrijfbaar).

        Args:
            path: Path naar het comic archive
            tags_to_remove: Set van tags om te verwijderen (case-sensitive)
            tags_to_add: Set van tags om toe te voegen (case-sensitive)

        Returns:
            True als bestand gewijzigd is, False anders
        """
        file_type = path.suffix.lower()

        # CBR: gebruik sidecar file (RAR is niet schrijfbaar)
        if file_type == '.cbr':
            from core.metadata_extractor import modify_sidecar_tags
            return modify_sidecar_tags(path, tags_to_remove, tags_to_add)

        # CBZ: schrijf naar ComicInfo.xml in het archive
        import zipfile
        import xml.etree.ElementTree as ET

        try:
            # Open archive en zoek ComicInfo.xml (case-insensitive)
            comicinfo_content = None
            comicinfo_exists = False

            with zipfile.ZipFile(path, 'r') as zf:
                for name in zf.namelist():
                    if name.lower() == 'comicinfo.xml':
                        comicinfo_content = zf.read(name).decode('utf-8')
                        comicinfo_exists = True
                        break

            # Parse of maak ComicInfo.xml
            if comicinfo_content:
                root = ET.fromstring(comicinfo_content)
            else:
                root = ET.Element('ComicInfo')

            # Haal huidige tags
            tags_elem = root.find('Tags')
            current_tags = []
            if tags_elem is not None and tags_elem.text:
                current_tags = [t.strip() for t in tags_elem.text.split(',') if t.strip()]

            # Pas tags aan - verwijder eerst (case-sensitive)
            new_tags = [t for t in current_tags if t not in tags_to_remove]
            removed_count = len(current_tags) - len(new_tags)

            # Voeg alle nieuwe tags toe die er nog niet zijn (case-sensitive)
            tags_added = []
            for tag_to_add in sorted(tags_to_add):  # Sorteer voor consistente volgorde
                if tag_to_add not in new_tags:
                    new_tags.append(tag_to_add)
                    tags_added.append(tag_to_add)

            # Check of er wijzigingen zijn
            if removed_count == 0 and not tags_added:
                return False

            # Update ComicInfo.xml
            if tags_elem is None:
                tags_elem = ET.SubElement(root, 'Tags')
            tags_elem.text = ', '.join(new_tags) if new_tags else ''

            new_comicinfo = ET.tostring(root, encoding='unicode', xml_declaration=True)

            # Schrijf terug naar archive via temp file
            fd, temp_path = tempfile.mkstemp(suffix='.cbz')
            os.close(fd)

            try:
                with zipfile.ZipFile(path, 'r') as zf_in:
                    with zipfile.ZipFile(temp_path, 'w') as zf_out:
                        for item in zf_in.infolist():
                            if item.filename.lower() == 'comicinfo.xml':
                                # Schrijf gewijzigde ComicInfo.xml
                                zf_out.writestr(item, new_comicinfo.encode('utf-8'),
                                               compress_type=zipfile.ZIP_DEFLATED)
                            else:
                                data = zf_in.read(item.filename)
                                zf_out.writestr(item, data, compress_type=item.compress_type)

                        # Voeg ComicInfo.xml toe als die nog niet bestond
                        if not comicinfo_exists:
                            zf_out.writestr('ComicInfo.xml', new_comicinfo.encode('utf-8'),
                                           compress_type=zipfile.ZIP_DEFLATED)

                # Vervang origineel
                if path.exists():
                    os.unlink(path)
                shutil.move(temp_path, path)
                return True

            except Exception as e:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
                raise e

        except Exception as e:
            print(f"Error modifying comic tags in {path}: {e}")
            return False

    def _on_info_click(self, instance):
        """Handle info button click - open https://libiry.org/ in browser."""
        # Open the Libiry website in the user's default browser
        webbrowser.open('https://libiry.org/')

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

            # Text input met witte achtergrond en ronde hoeken
            input_container = self._create_popup_text_input(value, white_background=True, size_hint_x=0.6)
            row.add_widget(input_container)
            form.add_widget(row)
            self._settings_inputs[key] = input_container.text_input

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
        add_section_header('Selected file types')
        types_str = '\n'.join(sorted(self.selected_types)) if self.selected_types else ''
        # Textarea row is 4x normale hoogte
        types_row = self._create_form_row(height_multiplier=4.0)
        types_label = self._create_popup_label('One per line', size_hint_x=0.4, valign='top')
        types_row.add_widget(types_label)

        # Text input met witte achtergrond en ronde hoeken voor types
        types_container = self._create_popup_text_input(types_str, multiline=True, white_background=True, size_hint_x=0.6)
        types_row.add_widget(types_container)
        form.add_widget(types_row)
        self._settings_inputs['selected_types'] = types_container.text_input

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
        add_yn_field('Show tags', 'show_tags', self.custom.get('show_tags', False))
        add_yn_field('Rounded corners', 'rounded_corners', self.custom['rounded_corners'])
        add_yn_field('Only selected file types', 'only_selected_types', self.custom['only_selected_types'])
        add_yn_field('Fuzzy search', 'fuzzy_search', self.custom.get('fuzzy_search', False))
        add_yn_field('Store metadata in sidecar', 'metadata_in_sidecar', self.custom.get('metadata_in_sidecar', False))

        # === FIELD NAME SETTINGS ===
        add_section_header('Field names')
        # Haal field names uit de geneste field_names dict
        field_names = self.custom.get('field_names', {})
        add_field('Cover', 'field_cover', field_names.get('cover', 'cover'))
        add_field('Booktitle', 'field_booktitle', field_names.get('booktitle', 'booktitle'))
        add_field('Author', 'field_author', field_names.get('author', 'author'))
        add_field('ISBN', 'field_isbn', field_names.get('isbn', 'isbn'))
        add_field('Tags', 'field_tags', field_names.get('tags', 'tags'))

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
        lines.append(f"Store metadata in sidecar y/n: {'Y' if inputs['metadata_in_sidecar'].active else 'N'}")
        lines.append(f"Scrollbar width: {inputs['scrollbar_width'].text}")
        lines.append(f"Scrollbar always visible y/n: {'Y' if inputs['scrollbar_always_visible'].active else 'N'}")
        lines.append(f"Show book title y/n: {'Y' if inputs['show_book_title'].active else 'N'}")
        lines.append(f"Show tags y/n: {'Y' if inputs['show_tags'].active else 'N'}")
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
            Clock.schedule_once(lambda dt: self.navigate_to(start_path, add_to_history=False), 0)

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

    def _try_set_windows_icon(self, dt=None):
        """Probeer Windows taskbar icon te zetten, retry tot het lukt (max 20x)."""
        self._icon_set_attempts += 1
        if self._icon_set_attempts > 20:
            print("Failed to set Windows icon after 20 attempts")
            return

        success = self._set_windows_icon(self._icon_path)
        if not success:
            # Probeer opnieuw na 0.1 seconde
            Clock.schedule_once(self._try_set_windows_icon, 0.1)

    def _set_windows_icon(self, icon_path):
        """Set Windows taskbar icon using Windows API. Returns True on success.

        Probeert meerdere methoden om de window handle te verkrijgen:
        1. Via Kivy's SDL window info (meest betrouwbaar)
        2. EnumWindows met process ID matching
        3. FindWindowW met diverse class namen
        """
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

                # Methode 1: Probeer via Kivy SDL window info (meest betrouwbaar)
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

                # Methode 2: EnumWindows met process ID matching
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

                # Methode 3: FindWindowW met diverse class namen (fallback)
                if not hwnd:
                    hwnd = user32.GetActiveWindow()
                if not hwnd:
                    hwnd = user32.GetForegroundWindow()
                if not hwnd:
                    # SDL2 window class namen (kan variëren per SDL versie)
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

    def _on_close_request(self, *args):
        """Handle window close request (X button).

        Sluit de app direct, zonder te wachten op lopende taken.
        Cancel alle scheduled events om blokkering te voorkomen.
        """
        # Cancel alle lopende batch events
        if hasattr(self, '_batch_load_event') and self._batch_load_event:
            self._batch_load_event.cancel()
        if hasattr(self, '_tag_filter_batch_event') and self._tag_filter_batch_event:
            self._tag_filter_batch_event.cancel()
        if hasattr(self, '_no_tag_filter_batch_event') and self._no_tag_filter_batch_event:
            self._no_tag_filter_batch_event.cancel()
        if hasattr(self, '_tag_update_event') and self._tag_update_event:
            self._tag_update_event.cancel()

        # Stop de app direct
        self.stop()
        return True  # Prevent default close handling, we handled it

    def on_stop(self):
        """Handle app stop.

        Ruimt alle tijdelijke backups op bij het afsluiten van de app,
        ook als er acties mislukt waren.
        """
        self._cleanup_all_backups()
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
