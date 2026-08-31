"""Libiry - A cross-platform ebook library viewer
Supports Windows, Linux, macOS, Android and iOS"""

import sys
import re
import shutil
import os
import tempfile
import webbrowser
from pathlib import Path
from functools import partial
from datetime import datetime

# Try to import send2trash 
# If not available, use permanent deletion as fallback
try:
    from send2trash import send2trash
    HAS_SEND2TRASH = True
except ImportError:
    HAS_SEND2TRASH = False

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

# To show Libiry icon in Windows taskbar: set AppUserModelID
# Do this before the Kivy imports
if sys.platform == 'win32':
    import ctypes
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('libiry.app.1.0')

if sys.platform != 'win32':
    os.environ.setdefault('SDL_VIDEO_X11_WMCLASS', 'Libiry')
    os.environ.setdefault('SDL_VIDEO_WAYLAND_WMCLASS', 'Libiry')

from version import __version__
from kivy.config import Config

# Set window icon before importing other kivy modules
app_path = Path(__file__).parent
icon_path = app_path / "resources" / "icons" / "Libiry.png"
if icon_path.exists():
    # Use forward slashes for Kivy config
    Config.set('kivy', 'window_icon', str(icon_path).replace('\\', '/'))

# Disable multitouch emulation (to prevent red dots appearing in case of mouse interaction)
Config.set('input', 'mouse', 'mouse,multitouch_on_demand')

from kivy.app import App
from kivy.core.window import Window
from kivy.clock import Clock
from kivy.metrics import dp #used everywhere
from kivy.graphics import Color, Rectangle, RoundedRectangle, Triangle, Line
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.relativelayout import RelativeLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.image import Image
from kivy.uix.popup import Popup
from kivy.uix.filechooser import FileChooserListView
from kivy.uix.behaviors import ButtonBehavior #base class of ImageButton and CoverImage
from kivy.properties import StringProperty, ObjectProperty, ListProperty, NumericProperty
from kivy.utils import platform

from threading import Thread

from core.cover_cache import CoverCache
from core.cover_extractor import CoverExtractor
from core.file_opener import open_in_default_app
from core.file_cache import FileCache
from core.metadata_extractor import BookMetadata, get_sidecar_path, modify_markdown_tags, modify_epub_tags, modify_cbz_tags, save_full_metadata
from core.libiry_style import draw_capsule_bar, get_icon_path, get_user_data_dir, get_cache_dir, is_hidden, HoverBehavior, ColoredButton, LocationBox, SearchBox, StyledCheckBox, measure_text_size

class ImageButton(HoverBehavior, ButtonBehavior, Image):
    """A button with an image. Supports hover tooltips via the tooltip_text property"""
    pass

class CoverImage(HoverBehavior, ButtonBehavior, BoxLayout):
    """A clickable book cover or folder icon"""

    source = StringProperty('')
    item_name = StringProperty('')
    item_type = StringProperty('file')
    item_path = StringProperty('')
    file_type = StringProperty('')
    document_type = StringProperty('')
    is_selected = ObjectProperty(False)

    # Metadata properties
    cover = StringProperty('')   
    booktitle = StringProperty('')
    authors = ListProperty([])
    isbn = StringProperty('')
    rating = NumericProperty(0)
    tags = ListProperty([])
    series = StringProperty('')
    series_index = NumericProperty(0)

    def __init__(self, **kwargs):
        # These are Kivy widget instance attributes, not related to BG_COLOR etc
        self.item_path = kwargs.pop('item_path', '')
        self.item_type = kwargs.pop('item_type', 'file')
        self.item_name = kwargs.pop('item_name', '')
        self.file_type = kwargs.pop('file_type', '')
        self.document_type = kwargs.pop('document_type', '')
        self.source = kwargs.pop('source', '')
        self.on_double_tap_callback = kwargs.pop('on_double_tap', None)
        self.on_tap_callback = kwargs.pop('on_tap', None)
        self.on_right_click_callback = kwargs.pop('on_right_click', None)
        self.tile_font_color = kwargs.pop('tile_font_color', (0, 0, 0, 1))
        self.background_color = kwargs.pop('background_color', (0.44, 0.62, 0.62, 1)) 

        # Metadata fields
        self.booktitle = kwargs.pop('booktitle', '')
        self.authors = kwargs.pop('authors', [])
        self.isbn = kwargs.pop('isbn', '')
        self.rating = kwargs.pop('rating', 0)
        self.tags = kwargs.pop('tags', [])
        self.series = kwargs.pop('series', '')
        self.series_index = kwargs.pop('series_index', 0)
        self.cover = kwargs.pop('cover', '')

        super().__init__(**kwargs)
        self.orientation = 'vertical'
        self.size_hint = (None, None)
        self.padding = 0
        self.spacing = 0

        self._last_touch_time = 0
        self._build_ui()

    def _build_ui(self):
        """Build the cover UI"""
        # Use RelativeLayout to allow text overlay on image
        self.img_container = RelativeLayout(size_hint=(1, 1))

        self._has_real_cover = False
        if self.source and Path(self.source).exists():
            # Image fills tile completely, no bezel/margin. Center crop is done for thumbnail creation
            #self.img = Image(source=self.source, size_hint=(1, 1), allow_stretch=True, keep_ratio=False)
            self.img = Image(source=self.source, size_hint=(1, 1), fit_mode='fill')
            self._has_real_cover = True
        else:
            # Use fallback image based on type
            if self.item_type == 'folder':
                fallback = self._get_fallback_image('folder.png')
            else:
                fallback = self._get_fallback_image('book.png')

            if fallback:
                # self.img = Image(source=fallback, size_hint=(1, 1), allow_stretch=True, keep_ratio=False)
                self.img = Image(source=fallback, size_hint=(1, 1), fit_mode='fill')
                
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
                font_size=App.get_running_app().FONT_SIZE*0.8, #dp(11),
                color=self.tile_font_color,
                bold=False,
            )
            self.text_overlay.bind(size=lambda *x: setattr(self.text_overlay, 'text_size', (self.text_overlay.width - dp(10), None)))
            self.img_container.add_widget(self.text_overlay)

        self.add_widget(self.img_container)

        # Title overlay for tiles with covers (default hidden)
        # Can be shown via "Show Title" checkbox (Settings)
        self._title_overlay = None
        self._title_overlay_bg = None
        if self._has_real_cover and self.item_type != 'folder':
            self._create_title_overlay()

        # Selection indicator (shown when selected)
        self.bg_rect = None
        self.bg_color_inst = None
        self.bind(pos=self._update_tile, size=self._update_tile)
        Clock.schedule_once(self._initial_draw, 0.1)

    def _get_fallback_image(self, filename):
        """Get fallback image from customize or resources folder"""
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
        """Create the title overlay label (hidden by default)
        Shows [author] - [booktitle] in white on black when the "Show Title" button is active"""
        # Build the display text: "[author] - [booktitle]"
        if self.authors:
            author_str = ', '.join(self.authors[:2])
            title = self.booktitle if self.booktitle else self.item_name
            display_text = f"{author_str} - {title}"
        else:
            display_text = self.booktitle if self.booktitle else self.item_name

        self._title_overlay = Label(
            text=display_text,
            halign='center',
            valign='middle',
            size_hint=(1, None),
            height=dp(40),
            pos_hint={'center_x': 0.5, 'y': 0},  # At the bottom of the tile
            font_size=App.get_running_app().FONT_SIZE * 0.8,
            color=App.get_running_app().ACCENT_FONT_COLOR,
            bold=False,
            opacity=0,  # Default hidden
        )
        self._title_overlay.bind(
            size=lambda *x: setattr(self._title_overlay, 'text_size', (self._title_overlay.width - dp(6), None))
        )

        # Add background to label
        with self._title_overlay.canvas.before:
            self._title_overlay_color = Color(*App.get_running_app().ACCENT_COLOR[:3], 0) #The [:3] strips the alpha from ACCENT_COLOR so we can set alpha to 0 here (starts hidden). set_title_overlay_visible then sets .a = 0.8 or .a = 0 as it already does
            self._title_overlay_bg = Rectangle(pos=self._title_overlay.pos, size=self._title_overlay.size)

        # Bind to let background move accordingly
        self._title_overlay.bind(pos=self._update_title_overlay_bg, size=self._update_title_overlay_bg)

        self.img_container.add_widget(self._title_overlay)

    def _update_title_overlay_bg(self, *args):
        """Update the background positin/size of the title overlay"""
        if self._title_overlay_bg and self._title_overlay:
            self._title_overlay_bg.pos = self._title_overlay.pos
            self._title_overlay_bg.size = self._title_overlay.size

    def set_title_overlay_visible(self, visible: bool):
        """Show or hide the title overlay
        Only for tiles with real covers - tiles without cover already show the title"""
        if not self._title_overlay:
            return

        if visible:
            self._title_overlay.opacity = 1
            if hasattr(self, '_title_overlay_color'):
                self._title_overlay_color.a = 1 #opacity
        else:
            self._title_overlay.opacity = 0
            if hasattr(self, '_title_overlay_color'):
                self._title_overlay_color.a = 0

    def _draw_document_type_triangle(self):
        """Draws a colored triangle in bottom-right corner based on tags
        Looks at the book's tags:
        - Red triangle when one of the tags is 'summary'
        - Grey triangle when one of the tags is 'analog'
        - Summary prevails in case a book has both tags"""
        if not self.tags:
            return

        # Tags are case sensitive
        tags_stripped = [tag.strip() for tag in self.tags]

        # Determine triangle color based on tags (summary prevails over analog)
        if 'summary' in tags_stripped:
            if self._title_overlay:
                triangle_color = App.get_running_app().ACCENT_FONT_COLOR # White if aubergine title banner is shown
            else:
                triangle_color = App.get_running_app().ACCENT_COLOR # Aubergine for summary
        elif 'analog' in tags_stripped:
            triangle_color = App.get_running_app().BG_COLOR # Teal for analog
        else:
            return  # No triangle for other tags

        # Store triangle info for later updates
        self._triangle_color = triangle_color
        self._has_triangle = True

        # Draw triangle on canvas after so it's on top
        self._update_triangle()

    def _update_triangle(self):
        """Update the triangle position at the very bottom-right corner"""
        if not hasattr(self, '_has_triangle') or not self._has_triangle:
            return

        # Remove old triangle if it exists
        if hasattr(self, '_triangle_instr') and self._triangle_instr:
            self.canvas.after.remove(self._triangle_color_instr)
            self.canvas.after.remove(self._triangle_instr)

        # Triangle at the very bottom-right corner of the tile
        triangle_size = dp(20)

        # Triangle points: bottom-right corner
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
        """Redraw triangle at updated position (bottom-right corner)"""
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
        """Draw document type triangle"""
        self._draw_document_type_triangle()

    def _update_tile(self, *args):
        """Update selection indicator and triangle"""
        # Handle selection indicator
        if self.is_selected: # When tile is selected
            if self.bg_rect is None:
                with self.canvas.after:
                    # Grey overlay over the whole tile 
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
        """Handle touch events"""
        #The collide_point (*touch.pos) check uses scroll-transformed coordinates. Since Kivy's click dispatch already works correctly in this app, this should be fine, but if empty-space deselect never fires, this coordinate transform is the first thing to investigate 
        if self.collide_point(*touch.pos):
            if touch.button == 'right':
                if self.on_right_click_callback:
                    self.on_right_click_callback(self.item_path, self.item_type)
                return True
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
                    if self.on_tap_callback:
                      app = App.get_running_app()
                      #print(f"DEBUG, app._ctrl_held, app._shift_held", app._ctrl_held, app._shift_held) 
                      self.on_tap_callback(self, app._ctrl_held, app._shift_held)

                return True
        return super().on_touch_down(touch)

class RoundedScrollView(ScrollView):
    """ScrollView with rounded scrollbar (capsule shaped) or default rectangular scrollbar
    If rounded=True: draws own capsule shaped scrollbar with RoundedRectangle in custom color. If rounded=False: uses Kivy's default scrollbar but with the custom color
    Scrollbar is ALWAYS clickable/dragable (scroll_type must contain 'bars')
    The always_visible parameter only controls if the bar is visible when there is something to scroll
    Args:
        rounded: bool - True/False
        bar_color_override: tuple - color for the scrollbar
        always_visible: bool - True/False"""

    def __init__(self, rounded=True, bar_color_override=None, always_visible=True, **kwargs):
        # Save bar color - is used in both modes
        self._bar_color_override = bar_color_override or kwargs.get('bar_color', (0.5, 0.5, 0.5, 1))
        self._rounded_bar = rounded
        self._always_visible = always_visible

        if rounded:
            # Hide scrollbar by making it transparent 
            kwargs['bar_color'] = (0, 0, 0, 0)
            kwargs['bar_inactive_color'] = (0, 0, 0, 0)
        else:
            # Use rectangular scrollbar but with custom color
            kwargs['bar_color'] = self._bar_color_override
            if always_visible:
                kwargs['bar_inactive_color'] = self._bar_color_override
            else:
                kwargs['bar_inactive_color'] = (0, 0, 0, 0) #transparent

        super().__init__(**kwargs)

        if rounded:
            # Bindings for scrollbar redraw
            self.bind(scroll_y=self._draw_rounded_bar)
            self.bind(size=self._draw_rounded_bar)
            self.bind(viewport_size=self._draw_rounded_bar)
            Clock.schedule_once(lambda dt: self._draw_rounded_bar(), 0.2)

    def _draw_rounded_bar(self, *args):
        draw_capsule_bar(self, self._bar_color_override, self.bar_width)


    def _draw_rounded_barTMP(self, *args):
        """Draw rounded scrollbar"""
        # Delete old rounded bar graphics
        if hasattr(self, '_rounded_bar_group'):
            try:
                self.canvas.after.remove(self._rounded_bar_group)
            except ValueError:
                pass

        if not self._rounded_bar:
            return

        # Check if scrollbar is needed
        if not hasattr(self, 'viewport_size') or self.viewport_size[1] <= self.height:
            return  # Geen scrollbar nodig

        # Scrollbar dimensions
        # Minimal height is 3x the width (Libiry style)
        bar_width = self.bar_width
        viewport_ratio = self.height / self.viewport_size[1]
        bar_height = max(bar_width * 3, viewport_ratio * self.height)

        # Scrollbar position (right, depends on scroll_y)
        scroll_range = self.height - bar_height
        bar_x = self.right - bar_width - dp(2)
        bar_y = self.y + scroll_range * self.scroll_y

        # Draw rounded scrollbar
        from kivy.graphics import InstructionGroup
        self._rounded_bar_group = InstructionGroup()

        # Color
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

class LibiryGrid(GridLayout):
    def on_touch_down(self, touch):
        result = super().on_touch_down(touch)
        if not result and self.collide_point(*touch.pos):
            App.get_running_app()._deselect_all()
            return True
        return result

from core.libiry_style import LibiryKivyApp

class LibiryApp(LibiryKivyApp):
    """Main Libiry application"""

    current_path = StringProperty('')
    status_text = StringProperty('Select a folder to browse')

    CACHE_DIR = get_cache_dir()
    
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
        self._ctrl_held = False #Because Window.modifiers is a known unreliable source on Windows — it's populated through keyboard events but not guaranteed to be current during a mouse touch event
        self._shift_held = False #Ditto
        self._selection_anchor = None #init reference to the last tile clicked without Shift
        self._hidden_widgets = []  
        self._search_text = ''
        self._search_root = None  
        self._app_path = Path(__file__).parent

        # Initialize core components
        self.cache = CoverCache(self.CACHE_DIR)
        # Do NOT empty cache at startup - this slows up the startup and makes caching useless
        # Pass configured field names to extractors
        field_names = self.custom.get('field_names', {}) 
        self.coverextractor = CoverExtractor(field_names=field_names)

        # Persistent file metadata cache
        self.file_cache = FileCache(self.CACHE_DIR)

    def build(self):
        """Builds the main UI"""
        self.title = f'Libiry {__version__}'
        Window.bind(on_keyboard=self._on_keyboard)
        Window.bind(on_key_down=self._on_modifier_key_down)
        Window.bind(on_key_up=self._on_modifier_key_up)
        # X knop closes app immediately, and doesn't wait for running tasks
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

        # Main layout with background color - spacing equals margin_x for consistent distance X
        self.root = BoxLayout(orientation='vertical', spacing=self.margin_x, padding=[self.margin_x, self.margin_x, self.margin_x, self.margin_x])
        with self.root.canvas.before:
            Color(*self.BG_COLOR)
            self.root_bg = Rectangle(pos=self.root.pos, size=self.root.size)
        self.root.bind(pos=self._update_root_bg, size=self._update_root_bg)

        # Toolbar
        toolbar = self._build_toolbar()
        self.root.add_widget(toolbar)

        # Path bar
        path_bar = self._build_path_bar()
        self.root.add_widget(path_bar)

        # Grid area with scrollbar in button color
        # Scrollbar styling: width and visibility from customize settings
        # RoundedScrollView draws a capsule shaped scrollbar if self.ROUNDED is true
        self.scroll_view = RoundedScrollView(
            rounded=self.ROUNDED,
            bar_color_override=self.ACCENT_COLOR, #button color
            do_scroll_x=False,
            bar_width=self.SCROLLBAR_WIDTH,
            # Always 'bars' in scroll_type so scrollbar is clickable/dragable
            scroll_type=['bars', 'content'],
            # Scrollbar visibility: always_visible determines if bar visible or fade-out
            always_visible=self.SCROLLBAR_ALWAYS_VISIBLE,
        )
        self.grid = LibiryGrid(
            cols=4,
            spacing=dp(10),
            padding=[0, 0, 0, 0],  # No extra padding, main layout already has margin_x
            size_hint_y=None,
        )
        self.grid.bind(minimum_height=self.grid.setter('height'))
        self.scroll_view.add_widget(self.grid)
        self.root.add_widget(self.scroll_view)

        # Tag list block - conditional based on show_tags setting
        # Shows all tags of visible books, clickable for filtering
        if self.custom.get('show_tags', False):
            # Line height: FONT_SIZE + line spacing factor (1.5 is standard Kivy)
            self._tag_line_height = self.FONT_SIZE * 1.5
            # Scrollable tag bar — height capped at TAG_LINES lines
            self.tag_scroll = RoundedScrollView(
                rounded=self.ROUNDED,
                bar_color_override=self.ACCENT_COLOR,
                do_scroll_x=False,
                bar_width=self.SCROLLBAR_WIDTH,
                scroll_type=['bars', 'content'],
                always_visible=self.SCROLLBAR_ALWAYS_VISIBLE,
                size_hint=(1, None),
                height=0,  # Starts empty, grows with content via _on_tag_label_size
            )
            self.tag_list_label = Label(
                text='',
                size_hint=(1, None),
                height=0,
                halign='left',
                valign='top',
                color=self.BG_FONT_COLOR,
                font_size=self.FONT_SIZE,
                markup=True,
            )
            # Width binding drives text wrapping (unchanged logic, now reads label.width, which equals tag_scroll.width because do_scroll_x=False + size_hint_x=1)
            self.tag_list_label.bind(
                width=lambda inst, w: setattr(inst, 'text_size', (w, None))
            )
            # Height binding: grow label, cap scrollview
            self.tag_list_label.bind(texture_size=self._on_tag_label_size)
            self.tag_list_label.bind(on_ref_press=self._on_tag_ref_press)
            self.tag_scroll.add_widget(self.tag_list_label)
            self.root.add_widget(self.tag_scroll)
        else: # Tags hidden via setting
            self.tag_scroll = None
            self.tag_list_label = None

        # Status bar with Move/Delete buttons
        status_bar = BoxLayout(size_hint_y=None, height=self.UI_BAR_HEIGHT, spacing=dp(5))

        self.status_label = Label(
            text=self.status_text,
            size_hint=(1, 1),
            halign='left',
            valign='middle',
            color=self.BG_FONT_COLOR,
            font_size=self.FONT_SIZE,
            padding=[0, 0],
        )
        self.status_label.bind(size=lambda *x: setattr(self.status_label, 'text_size', self.status_label.size))
        status_bar.add_widget(self.status_label)

        accent_color = self.ACCENT_COLOR
        # Button width scales with font size - all buttons same width
        btn_width = self.FONT_SIZE * 9

        self._show_titles_active = self.custom.get('show_book_title', False)

        # Edit Tags button
        self.btn_edit_tags = ColoredButton(
            text='Edit',
            size_hint_x=None,
            width=btn_width,
            bg_color=self.ACCENT_COLOR,
            rounded=self.ROUNDED,
            color=self.ACCENT_FONT_COLOR,
            font_size= self.FONT_SIZE,
            disabled=True,
        )
        self.btn_edit_tags.bind(on_release=lambda x: self._show_edit_tags_popup())

        self.btn_edit_tags.tooltip_text = 'Edit'
        status_bar.add_widget(self.btn_edit_tags)

        self.btn_move = ColoredButton(
            text='Move',
            size_hint_x=None,
            width=btn_width,
            bg_color=self.ACCENT_COLOR,
            rounded=self.ROUNDED,
            color=self.ACCENT_FONT_COLOR,
            font_size=self.FONT_SIZE,
            disabled=True,
        )
        self.btn_move.bind(on_release=lambda x: self._move_selected())
        self.btn_move.tooltip_text = 'Move'
        status_bar.add_widget(self.btn_move)

        self.btn_delete = ColoredButton(
            text='Delete',
            size_hint_x=None,
            width=btn_width,
            bg_color=self.ACCENT_COLOR,
            rounded=self.ROUNDED,
            color=self.ACCENT_FONT_COLOR,
            font_size=self.FONT_SIZE,
            disabled=True,
        )
        self.btn_delete.bind(on_release=lambda x: self._delete_selected())
        self.btn_delete.tooltip_text = 'Delete'
        status_bar.add_widget(self.btn_delete)

        self.root.add_widget(status_bar)

        self._load_last_folder()
        Window.bind(on_resize=self._on_window_resize)
        Clock.schedule_once(lambda dt: self._update_grid_cols(), 0.1)

        return self.root

    def _update_root_bg(self, *args):
        """Update root background rectangle"""
        self.root_bg.pos = self.root.pos
        self.root_bg.size = self.root.size

    def _build_toolbar(self):
        # Icon spacing: dp(12) standard, dp(8) around information icon (narrower image)
        icon_spacing = dp(12)
        icon_spacing_info = dp(8)  # Smaller spacing before/after information icon
        toolbar = BoxLayout(size_hint_y=None, height=self.UI_BAR_HEIGHT, spacing=0)
        accent_color = self.ACCENT_COLOR
        icon_size = self.UI_BAR_HEIGHT # Icons scale with bar height
        icon_size_small = icon_size * 0.8  # 80% size for all icons except twins

        # Helper function for spacer
        def add_spacer(width=icon_spacing):
            toolbar.add_widget(BoxLayout(size_hint_x=None, width=width))

        # Helper functie for icon with bottom alignment (for 80% icons)
        # Container is icon_size width, icon itself is icon_size_small
        def create_icon_container(icon_btn, small=True):
            """Wrap icon in container for bottom-alignment when using smaller icons"""
            if not small:
                return icon_btn
            # Container with full icon_size, icon aligned at the bottom
            container = RelativeLayout(size_hint=(None, None), size=(icon_size, icon_size))
            icon_btn.pos_hint = {'center_x': 0.5, 'y': 0}  # Bottom-aligned
            container.add_widget(icon_btn)
            return container

        # Back button - goes to parent directory (80% size)
        back_icon = get_icon_path(self._app_path, 'back.png')
        if back_icon:
            self.btn_back = ImageButton(source=back_icon, size_hint=(None, None), size=(icon_size_small, icon_size_small))
            self.btn_back.tooltip_text = 'One folder up'
            toolbar.add_widget(create_icon_container(self.btn_back))
        else:
            self.btn_back = Button(text='<', size_hint_x=None, width=icon_size, background_color=self.ACCENT_COLOR, font_size=self.FONT_SIZE)
            toolbar.add_widget(self.btn_back)
        self.btn_back.bind(on_release=lambda x: self.go_up())
        self.btn_back.opacity = 0  # Hidden until parent exists

        add_spacer()

        # Refresh button (80% size)
        refresh_icon = get_icon_path(self._app_path, 'refresh.png')
        if refresh_icon:
            btn_refresh = ImageButton(source=refresh_icon, size_hint=(None, None), size=(icon_size_small, icon_size_small))
            btn_refresh.tooltip_text = 'Refresh'
            toolbar.add_widget(create_icon_container(btn_refresh))
        else:
            btn_refresh = Button(text='Refresh', size_hint_x=None, width=icon_size * 2, background_color=self.ACCENT_COLOR, font_size=self.FONT_SIZE)
            toolbar.add_widget(btn_refresh)
        btn_refresh.bind(on_release=lambda x: self._refresh())

        add_spacer()

        # Search box with magnifying glass icon
        self.search_box = SearchBox(
            app_path=self._app_path,
            bg_color=self.ACCENT_FONT_COLOR,
            fg_color=self.ACCENT_COLOR,
            rounded=self.ROUNDED,
            font_size=self.FONT_SIZE,
            on_text_change=self._on_search_changed,
            size_hint=(1, 1),
        )
        self.search_box.tooltip_text = 'Search. Type .epub to display all epubs. Turn fuzzy search on in Settings'
        toolbar.add_widget(self.search_box)

        add_spacer(icon_spacing_info)  # Kleinere spacing voor information icon

        # === TOOLBAR BUTTONS (sequence: information, gear, bento/plus, twins) ===

        # 1. Information button (80% size)
        info_icon = get_icon_path(self._app_path, 'information.png')
        if not info_icon:
            info_icon = get_icon_path(self._app_path, 'information.ico')
        if info_icon:
            self.btn_info = ImageButton(source=info_icon, size_hint=(None, None), size=(icon_size_small, icon_size_small))
            self.btn_info.tooltip_text = 'About Libiry'
            toolbar.add_widget(create_icon_container(self.btn_info))
        else:
            self.btn_info = Button(text='i', size_hint_x=None, width=icon_size, background_color=self.ACCENT_COLOR, font_size=self.FONT_SIZE)
            toolbar.add_widget(self.btn_info)
        self.btn_info.bind(on_release=self._on_info_click)

        add_spacer(icon_spacing_info)  # Small spacing after information icon

        # 2. Settings/gear button (80% size)
        gear_icon = get_icon_path(self._app_path, 'gear.png')
        if gear_icon:
            self.btn_gear = ImageButton(source=gear_icon, size_hint=(None, None), size=(icon_size_small, icon_size_small))
            self.btn_gear.tooltip_text = 'Settings'
            toolbar.add_widget(create_icon_container(self.btn_gear))
        else:
            self.btn_gear = Button(text='⚙', size_hint_x=None, width=icon_size, background_color=self.ACCENT_COLOR, font_size=self.FONT_SIZE)
            toolbar.add_widget(self.btn_gear)
        self.btn_gear.bind(on_release=self._on_gear_click)

        add_spacer()

        # 3. Support button (80% size) - opens support website
        support_icon = get_icon_path(self._app_path, 'support.png')
        if support_icon:
            self.btn_support = ImageButton(source=support_icon, size_hint=(None, None), size=(icon_size_small, icon_size_small))
            self.btn_support.tooltip_text = 'Support'
            toolbar.add_widget(create_icon_container(self.btn_support))
        else:
            self.btn_support = Button(text='?', size_hint_x=None, width=icon_size, background_color=self.ACCENT_COLOR, font_size=self.FONT_SIZE)
            toolbar.add_widget(self.btn_support)
        self.btn_support.bind(on_release=lambda x: webbrowser.open('https://libiry.org/Contributing'))

        add_spacer()

        # 5. Bento button (80% size)
        plus_icon = get_icon_path(self._app_path, 'plus.png')
        if plus_icon:
            self.btn_bento = ImageButton(source=plus_icon, size_hint=(None, None), size=(icon_size_small, icon_size_small))
            self.btn_bento.tooltip_text = 'Libiry apps'
            toolbar.add_widget(create_icon_container(self.btn_bento))
        else:
            self.btn_bento = Button(text='+', size_hint_x=None, width=icon_size, background_color=self.ACCENT_COLOR, font_size=self.FONT_SIZE)
            toolbar.add_widget(self.btn_bento)
        self.btn_bento.bind(on_release=lambda x: self._show_libiry_apps_popup())

        add_spacer()

        # 6. Twins filter button (rightmost) - 100% size
        # Note that the icon does not display properly on Linux!
        # Because 5 thin lines in a 542×659 illustration don't survive aggressive downscaling on Linux's OpenGL driver
        twins_icon = get_icon_path(self._app_path, 'twins.png')       
        if twins_icon:
            self.btn_twins = ImageButton(source=twins_icon, size_hint=(None, None), size=(icon_size, icon_size))
            self.btn_twins.tooltip_text = 'Find duplicates'
        else:
            self.btn_twins = Button(text='2x', size_hint_x=None, width=icon_size, background_color=self.ACCENT_COLOR, font_size=self.FONT_SIZE)
        self.btn_twins.bind(on_release=lambda x: self._toggle_twins_filter())
        self._twins_filter_active = False
        self._twins_filter_root = None  # Root folder for relative path calculation
        # Tag filter state - for filtering on a specific tag via double click in tag list
        self._tag_filter_active = False
        self._tag_filter_tag = None  # The active tag that is being filtered on
        self._tag_filter_root = None  # Root folder for relative path calculation
        self._tag_list_lookup = []  # Lookup table for tag indices in the tag list
        toolbar.add_widget(self.btn_twins)

        return toolbar

    def _on_navigate(self, path: Path, add_to_history: bool = False):
        # Base class sets self._current_folder before calling this
        
        if add_to_history and self._current_folder and self._current_folder != path:
            self._history = self._history[:self._history_index + 1]
            self._history.append(self._current_folder)
            self._history_index = len(self._history) - 1

        self.current_path = str(path)
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

    def _load_folder(self, folder_path: Path):
        """Load folder contents into grid. Handles missing/deleted folders gracefully
        At double click on folder a possible running load action is stopped immediately by increasing _load_version and cancelling scheduled events"""
        if hasattr(self, '_batch_load_event') and self._batch_load_event:
            self._batch_load_event.cancel()
            self._batch_load_event = None

        # Cancel running tag scan and filter batches to keep UI responsive
        self._cancel_tag_filter_batches()
        HoverBehavior._destroy_active_tooltip()
        self.grid.clear_widgets()
        self._items = []
        self._selected_items.clear()
        self._hidden_widgets = []  # Reset hidden widgets of search filter
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

        for item in items:
            try:
                # Skip files/folders that need to be hidden (Unix: starts with '.', Windows: hidden attribute, sidecars)
                #print(f"main.py line 1168")
                if is_hidden(item, self.selected_types):
                    continue

                if item.is_dir():
                    folders.append(item)
                    folder_count += 1
                elif item.is_file():
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
            # Save reference to scheduled event so it can be cancelled in case of a double click on another folder (see _load_folder)
            self._batch_load_event = Clock.schedule_once(self._load_items_batch, 0)
        else:
            # Singular/plural: "1 folder" vs "2 folders", "1 file" vs "2 files"
            folder_word = "folder" if self._folder_count == 1 else "folders"
            file_word = "file" if self._file_count == 1 else "files"
            self.status_text = f"{self._folder_count} {folder_word}, {self._file_count} {file_word}"
            self.status_label.text = self.status_text
            self._pending_items = None
            self._batch_load_event = None  # Load ready, no pending event anymore
            # If there are no files (only folders), update tag list immediately
            # Otherwise update will be triggered by _update_cover_and_metadata() after metadata load
            if self._file_count == 0:
                self._schedule_tag_list_update(force=True)

    def _add_folder_widget(self, path: Path):
        """Add a folder widget to the grid"""
        # No item count - this was a big performance bottleneck, because every folder was scanned at the same time
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
            on_right_click=self._on_item_right_click,
            tile_font_color=self.TILE_FONT_COLOR,
            background_color=self.BG_COLOR,
        )
        widget.tooltip_text = name
        self.grid.add_widget(widget)

    def _get_document_type(self, filepath: Path) -> str:
        """Strips the sidecar extension and reads the remaining suffix. Returns 'pdf' for 'book.pdf.md' and 'book.pdf.markdown', '' for standalone 'book.md' or non-sidecar 'book.pdf'"""
        if filepath.suffix.lower() not in ('.md', '.markdown'):
            return ''
        suffixes = filepath.suffixes          # ['pdf', '.md'] for book.pdf.md
        if len(suffixes) < 2:
            return ''
        return suffixes[-2].lstrip('.')       # 'pdf'

    def _add_file_widget(self, path: Path, known_tags: list = None):
        """Add a file widget to the grid
        Args:
            path: Path to the file
            known_tags: List with tags that are already known (before tag filter)"""

        file_type =path.suffix.lower()
        
        document_type = self._get_document_type(path)

        # Use file_cache for fast metadata lookup
        cached = self.file_cache.get_or_extract(path, self.extractor)

        # Read tags from cache if available
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
            on_right_click=self._on_item_right_click,
            tile_font_color=self.TILE_FONT_COLOR,
            background_color=self.BG_COLOR,
            tags=known_tags if known_tags else [],
        )
        self.grid.add_widget(widget)

        Thread(target=self._load_cover_async, args=(path, widget), daemon=True).start()

    def _load_cover_async(self, path: Path, widget: CoverImage):
        """Load cover and metadata in background thread. Handles missing files gracefully"""
        try:
            # Check if file still exists before trying to load
            if not path.exists():
                return
            # Use file_cache for metadata (incl. tags) - this is more consistent
            # and prevents loss of tags with files without YAML frontmatter
            cached = self.file_cache.get_or_extract(path, self.extractor)
            if cached:
                # Converts cached file metadata to BookMetadata
                metadata = BookMetadata(
                    cover=cached.cover,
                    booktitle=cached.booktitle,
                    authors=cached.authors,
                    author_sort=cached.author_sort,
                    isbn=cached.isbn,
                    rating=cached.rating,
                    publisher=cached.publisher,
                    publication_date=cached.publication_date,
                    pages=cached.pages,
                    language=cached.language,
                    tags=cached.tags,
                    series=cached.series,
                    series_index=cached.series_index,
                    translator=cached.translator,
                    illustrator=cached.illustrator,
                    description=cached.description,
                    notes=cached.notes,
                )
            else:
                # Fallback to direct extraction
                metadata = self.extractor.extract(path)

            # Get cover thumbnail
            thumb_path = self.cache.get_cover(path, self.coverextractor)
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
        """Update widget with loaded cover and metadata"""
        # Update metadata on widget
        widget.cover = metadata.cover if metadata.cover else ''
        widget.booktitle = metadata.booktitle
        widget.authors = metadata.authors
        widget.isbn = metadata.isbn
        widget.rating = metadata.rating if metadata.rating else 0
        widget.tags = metadata.tags
        widget.series = metadata.series
        widget.series_index = metadata.series_index if metadata.series_index else 0

        # Determine display title (booktitle if different from filename, otherwise filename)
        display_title = metadata.booktitle if metadata.booktitle and metadata.booktitle != widget.item_name else widget.item_name
        author_str = ', '.join(metadata.authors[:2]) if metadata.authors else ''
        description = metadata.description
        
        if has_real_cover and Path(thumb_path).exists():
            # Clear the image container and add new cover
            widget.img_container.clear_widgets()
            #widget.img = Image(source=thumb_path, size_hint=(1, 1), allow_stretch=True, keep_ratio=False)
            widget.img = Image(source=thumb_path, size_hint=(1, 1), fit_mode='fill')
            widget.img_container.add_widget(widget.img)
            widget._has_real_cover = True
            # Remove text overlay reference since container was cleared
            if hasattr(widget, 'text_overlay'):
                widget.text_overlay = None

            # Create title overlay for tiles with covers
            widget._create_title_overlay()
            # Apply current show titles state
            if self._show_titles_active:
                widget.set_title_overlay_visible(True)
        else:
            # No real cover - update text overlay with "[author] - [booktitle]"
            if hasattr(widget, 'text_overlay') and widget.text_overlay:
                if author_str and display_title:
                    overlay_text = f"{author_str} - {display_title}"
                elif display_title:
                    overlay_text = display_title
                elif author_str:
                    overlay_text = author_str
                else:
                    overlay_text = widget.item_name
                widget.text_overlay.text = overlay_text
        
        widget.tooltip_text = "\n".join(part for part in (display_title, author_str, description) if part)
        
        # If tile is already hovered when metadata arrives, show tooltip now
        if getattr(widget, '_is_hovering', False) and not HoverBehavior._active_tooltip:
            widget._show_tooltip()

        # Redraw tag triangle now that tags are available and title overlay is determined
        # (summary = aubergine, analog = teal)
        widget._draw_document_type_triangle()
 
        # Schedule tag list update with debouncing
        # Every time metadata comes in, reset the timer
        # The tag list will only be updated 0.3s afther the LAST metadata load
        self._schedule_tag_list_update()

    def _schedule_tag_list_update(self, force: bool = False):
        """Schedule tag list update with debouncing.
        Cancels eventual previous scheduled update, so the tag list
        will only be updated after the last metadata load (+ 0.3s delay)
        This prevents unneccesary updates during the load
        Args:
            force: If True, schedule always. If False, skip if a
                   background tag scan is already running (prevents covers that
                   come in from resetting the running scan)"""
        # Skip if a tag scan is already running and it is not a force update
        # The running scan will find the tags itself, so we do not need to start again
        if not force and hasattr(self, '_tag_scan_active') and self._tag_scan_active:
            return

        if hasattr(self, '_tag_update_event') and self._tag_update_event:
            self._tag_update_event.cancel()
        self._tag_update_event = Clock.schedule_once(
            lambda dt: self._update_tag_list(), 0.3
        )

    def _on_item_tap(self, widget, ctrl_held=False, shift_held=False):
        """Handle item tap - toggle selection
        If a tag filter is busy searching, it is stopped immediately
        when the UI responds to the selection"""
        # Stop running tag filter batches immediately at user interaction
        self._cancel_tag_filter_batches()

        if shift_held and self._selection_anchor is not None:
            self._select_range(self._selection_anchor, widget)

        elif ctrl_held:
            widget.is_selected = not widget.is_selected
            if widget.is_selected:
                self._selected_items.add(widget.item_path)
                self._selection_anchor = widget
            else:
                self._selected_items.discard(widget.item_path)
            widget._update_tile()

        else:
            for child in self.grid.children:
                if hasattr(child, 'is_selected') and child.is_selected:
                    child.is_selected = False
                    child._update_tile()
            self._selected_items.clear()
            widget.is_selected = True
            self._selected_items.add(widget.item_path)
            widget._update_tile()
            self._selection_anchor = widget

        self._refresh_selection_ui()

    def _refresh_selection_ui(self):
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

    def _deselect_all(self):
        for child in self.grid.children:
            if hasattr(child, 'is_selected') and child.is_selected:
                child.is_selected = False
                child._update_tile()
        self._selected_items.clear()
        self._selection_anchor = None
        self._refresh_selection_ui()

    def _select_range(self, anchor, target):
        tiles = list(reversed(self.grid.children))
        if anchor not in tiles or target not in tiles:
            return
        start = min(tiles.index(anchor), tiles.index(target))
        end   = max(tiles.index(anchor), tiles.index(target))
        self._selected_items.clear()
        for i, tile in enumerate(tiles):
            if start <= i <= end:
                tile.is_selected = True
                self._selected_items.add(tile.item_path)
            else:
                tile.is_selected = False
            tile._update_tile()

    def _update_status_with_selection(self):
        """Update status label to include selection count if items are selected
        If the twins filter is active and exactly 1 item is selected, show also the relative path from the twins filter root folder"""
        selected_count = len(self._selected_items)
        if selected_count > 0:
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

            # If exactly 1 item is selected, show extension + size + folder name + tags
            # ALWAYS, not just with twins filter (per user request)
            if selected_count == 1:
                selected_path = Path(list(self._selected_items)[0])
                # Show extension and file size for files (not for folders)
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

                    # Find tags of selected item (format: #tag1, #tag2)
                    tags_text = ""
                    for child in self.grid.children:
                        if hasattr(child, 'item_path') and child.item_path == str(selected_path):
                            # Check if this really is the selected widget
                            if hasattr(child, 'is_selected') and child.is_selected:
                                if hasattr(child, 'tags') and child.tags:
                                    tags_text = "  " + ", ".join(f"#{tag}" for tag in child.tags)
                                break

                    # For twins filter of search: show relative path from root
                    # Otherwise (normal folder view): only show parent folder name
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
                        # Search modus: show relatief path from search root
                        try:
                            rel_path = selected_path.parent.relative_to(self._search_root)
                            if rel_path != Path('.'):
                                base_text += f"  |  {ext_text} {size_text} {rel_path}{tags_text}"
                            else:
                                base_text += f"  |  {ext_text} {size_text} (root){tags_text}"
                        except ValueError:
                            base_text += f"  |  {ext_text} {size_text} {selected_path.parent.name}{tags_text}"
                    else:
                        # Normal modus: show parent folder name only
                        base_text += f"  |  {ext_text} {size_text} {selected_path.parent.name}{tags_text}"

            self.status_label.text = base_text
        else:
            # Singular/plural: "1 folder" vs "2 folders", "1 file" vs "2 files"
            folder_word = "folder" if self._folder_count == 1 else "folders"
            file_word = "file" if self._file_count == 1 else "files"
            self.status_label.text = f"{self._folder_count} {folder_word}, {self._file_count} {file_word}"

    def _on_tag_label_size(self, instance, texture_size):
        h = texture_size[1] if instance.text else 0
        instance.height = h
        # Cap the scrollview to TAG_LINES lines; shows scrollbar when exceeded
        self.tag_scroll.height = min(h, self.TAG_LINES * self._tag_line_height)

    def _update_tag_list(self):
        """Update the tag list at the bottom of the screen
        Recursively scans all files in the current folder via the file_cache
        This way the same data is used for display AND for filtering
        The UI stays responsive - scan runs in background thread
        Skip if tag list is hidden"""

        if self.tag_list_label is None:
            return

        # Skip if no folder loaded
        if not self._current_folder:
            return

        self._start_background_tag_scan()

    def _start_background_tag_scan(self):
        """Start a background thread to collect all tags recursively
        The scan runs in a separate thread to keep the UI responsive
        The current scan gets cancelled after user input (via _tag_scan_version check)
        Uses the file_cache. New files are extracted and saved in cache via file_cache.get_or_extract()"""
        
        from threading import Thread

        # Cancel running scan
        self._tag_scan_version = getattr(self, '_tag_scan_version', 0) + 1
        current_version = self._tag_scan_version
        scan_folder = self._current_folder

        # Prevent cover loads from resetting the scan
        self._tag_scan_active = True

        # Show "All books", then "Scanning..."
        # Tags are incrementally added during the scan (alfabetically sorted)
        # "No tag" is only shown if there are books without tags
        if self.tag_list_label:
            self.tag_list_label.text = '[ref=__all_books__][u]All books[/u][/ref], Scanning tags...'

        def _scan_tags_thread():
            """Background thread that collects tags"""
            import time

            # Set instead of Counter - we sort alfabetically, count not needed
            found_tags = set()
            no_tag_count = 0  # Number of books without tags
            MAX_TAGS = 99
            MAX_FILES = 5000  # Limit to save memory
            TIMEOUT_SECONDS = 30
            UPDATE_INTERVAL = 0.3  # Seconds between UI updates
            start_time = time.time()
            last_update_time = start_time
            truncated = False
            files_scanned = 0
            tags_changed_since_update = False

            def schedule_ui_update(is_final=False):
                """Schedule a UI update on the main thread"""
                nonlocal last_update_time, tags_changed_since_update
                if self._tag_scan_version != current_version:
                    return
                # Make copy for thread safety
                tags_copy = set(found_tags)
                no_tag_copy = no_tag_count
                truncated_copy = truncated
                Clock.schedule_once(
                    lambda dt: self._display_tag_list(
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
                    # Check if scan is cancelled (user clicked or navigated to other folder)
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
                        # Use file_cache - retrieve from cache or extract and cached
                        cached = self.file_cache.get_or_extract(filepath, self.extractor)

                        if cached and cached.tags:
                            for tag in cached.tags:
                                if tag:
                                    tag_stripped = tag.strip()
                                    if tag_stripped not in found_tags:
                                        found_tags.add(tag_stripped)
                                        tags_changed_since_update = True
                        else:
                            # File without tags
                            no_tag_count += 1

                    except Exception:
                        no_tag_count += 1  # Count error as "no tag"

                    # Periodical UI update (only if there are new tags)
                    if tags_changed_since_update and time.time() - last_update_time >= UPDATE_INTERVAL:
                        schedule_ui_update(is_final=False)

            except Exception as e:
                print(f"Error in tag scan: {e}")

            # Final UI update (only if scan has not been cancelled)
            if self._tag_scan_version == current_version:
                schedule_ui_update(is_final=True)

        # Start background thread
        Thread(target=_scan_tags_thread, daemon=True).start()

    def _display_tag_list(self, tags: set, truncated: bool, no_tag_count: int = 0, is_final: bool = False):
        """Show the collected tags in the tag list, sorted alfabetically
        Is called incrementally during the scan for fast feedback
        Args:
            tags: Set met gevonden tags
            truncated: True if not all tags are loaded (timeout/max)
            no_tag_count: Number of books without tags
            is_final: True if this is the final update (scan complete)"""
        # Mark scan as ready if this is the final update
        if is_final:
            self._tag_scan_active = False

        if self.tag_list_label is None:
            return

        # Format: clickable tags
        self._tag_list_lookup = []
        tag_strings = []

        def _ref(display_text, logical_value):
            idx = len(self._tag_list_lookup)
            self._tag_list_lookup.append(logical_value)
            return f"[ref={idx}][u]{display_text}[/u][/ref]"

        tag_strings.append(_ref('All books', '__all_books__'))
        if no_tag_count > 0:
            tag_strings.append(_ref('No tag', '__no_tag__'))

        for tag in sorted(tags, key=lambda x: x.lower()):
            display = tag.replace('&', '&amp;').replace('[', '&bl;'). replace(']', '&br;')
            tag_strings.append(_ref(f'#{display}', tag))

        if truncated:
            tag_strings.append("[ref=0][u]...[/u][/ref]")
        elif not is_final:
            tag_strings.append("Scanning...")

        self.tag_list_label.text = ", ".join(tag_strings)


    def _display_tag_listTMP(self, tags: set, truncated: bool, no_tag_count: int = 0, is_final: bool = False):
        """Show the collected tags in the tag list, sorted alfabetically
        Is called incrementally during the scan for fast feedback
        Args:
            tags: Set met gevonden tags
            truncated: True if not all tags are loaded (timeout/max)
            no_tag_count: Number of books without tags
            is_final: True if this is the final update (scan complete)"""
        # Mark scan as ready if this is the final update
        if is_final:
            self._tag_scan_active = False

        if self.tag_list_label is None:
            return

        # Format: clickable tags
        tag_strings = ["[ref=__all_books__][u]All books[/u][/ref]"]

        # Add "No tag" if there are books without tags
        if no_tag_count > 0:
            tag_strings.append("[ref=__no_tag__][u]No tag[/u][/ref]")

        # Sort alfabetically (case-insensitive)
        sorted_tags = sorted(tags, key=lambda x: x.lower())

        tag_strings.extend([f"[ref={tag}][u]#{tag}[/u][/ref]" for tag in sorted_tags])

        # Show clearly that the scan results are incomplete
        if truncated:
            tag_strings.append("[ref=__all_books__][u]...[/u][/ref]")
        elif not is_final:
            tag_strings.append("Scanning...")

        self.tag_list_label.text = ", ".join(tag_strings)

    def _cancel_tag_filter_batches(self):
        """Cancel any pending tag filter/scan batch processing
        Is called in case of user interaction (select, buttons) to let the UI
        react immediately instead of waiting until the filter/scan is ready"""
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
        """Handle click on a tag in the tag list
        The ref_value is the tag name (without #). Filter on books with that tag
        Special value "__all_books__" resets the tag filter or performs a refresh
        Special value "__no_tag__" filters on books without tags"""
        try:
            ref = self._tag_list_lookup[int(ref_value)]
        except (ValueError, IndexError, AttributeError):
            ref = ref_value.strip()
        if not ref:
            return

        # Cancel any pending tag filter batches
        self._cancel_tag_filter_batches()

        # "All books" is a special action: reset tag filter or refresh
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
                # No tag filter active: do the same as the refresh button
                self._refresh()
            return

        # "No tag" filter: show books without tags
        if ref == '__no_tag__':
            self._no_tag_filter_active = True
            self._tag_filter_active = False
            self._tag_filter_tag = None
            self._tag_filter_root = self._current_folder
            self._apply_no_tag_filter()
            return

        # Filter on this tag
        tag = ref
        self._no_tag_filter_active = False
        self._tag_filter_tag = tag
        self._tag_filter_active = True
        self._tag_filter_root = self._current_folder
        self._apply_tag_filter()

    def _apply_tag_filter(self):
        """Filter books with the active tag (recursive, from cache)
        Uses file_cache for instant lookup - no disk I/O needed
        Cache is filled by background tag scan and grid build"""
        if not self._tag_filter_tag:
            return

        tag = self._tag_filter_tag

        # Collect files with the tag from file_cache
        # Filter on current folder and subfolders
        current_folder = self._tag_filter_root or self._current_folder
        matching_files = []

        # Collect all files (recursive, max 10 layers deep)
        all_files = []
        self._collect_files_recursive(current_folder, all_files)

        for filepath in all_files:
            # Use get_or_extract for consistency with tag scan
            cached = self.file_cache.get_or_extract(filepath, self.extractor)
            if cached and cached.tags:
                # Strip for consistent comparison
                cached_tags_stripped = [t.strip() for t in cached.tags if t]
                if tag in cached_tags_stripped:
                    matching_files.append(filepath)

        # Sort alfabetically
        matching_files.sort(key=lambda p: p.name.lower())

        # Clear grid and show results
        HoverBehavior._destroy_active_tooltip()
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

        # Add results in batches for big numbers
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
                # Retrieve tags from cache for widget
                cached = self.file_cache.get(filepath)
                cached_tags = cached.tags if cached else []
                self._add_file_widget(filepath, known_tags=cached_tags)
                self._file_count += 1
            except Exception:
                pass

        self._tag_results_index = end_idx

        # Update status
        self.status_label.text = f"{self._file_count} books with #{self._tag_filter_tag}"

        if end_idx < len(files):
            # More to process
            Clock.schedule_once(self._add_tag_results_batch, 0)
        else:
            # Ready
            self._pending_tag_results = None

    def _apply_no_tag_filter(self):
        """Filter to show books WITHOUT tags (recursively, from cache)"""
        # Find files without tags in cache
        current_folder = self._tag_filter_root or self._current_folder
        matching_files = []

        all_files = []
        self._collect_files_recursive(current_folder, all_files)

        for filepath in all_files:
            # Use get_or_extract for consistency
            cached = self.file_cache.get_or_extract(filepath, self.extractor)
            if cached:
                # Check if this file has no tags
                # Filter out empty strings for a correct check
                real_tags = [t.strip() for t in cached.tags if t and t.strip()]
                if not real_tags:
                    matching_files.append(filepath)
            else:
                # Extraction failed, count as "no tags"
                matching_files.append(filepath)

        # Sort alfabetically
        matching_files.sort(key=lambda p: p.name.lower())

        # Clear grid and show results
        HoverBehavior._destroy_active_tooltip()
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

        # Add results to grid in batches
        self._pending_no_tag_results = matching_files
        self._no_tag_results_index = 0
        self._add_no_tag_results_batch()

    def _add_no_tag_results_batch(self, dt=None):
        """Add no-tag filter results to grid in batches"""
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

    def _on_item_double_tap(self, path_str: str, item_type: str):
        """Handle item double tap"""
        # Stop running tag scan/filters for direct UI response
        self._cancel_tag_filter_batches()

        path = Path(path_str)
        if item_type == 'folder':
            self.navigate_to(path, add_to_history=True)

        else:
            
            # Remove the grey veil if there was a preceding single-click
            for child in self.grid.children:
                if hasattr(child, 'is_selected') and child.is_selected:
                    child.is_selected = False
                    child._update_tile()
                self._selected_items.clear()
                self._refresh_selection_ui()
              
            # Show a non-blocking toast popup confirming the action.
            # Popup with auto_dismiss=True closes when the user clicks anywhere outside it
            # Clock.schedule_once auto-closes it after 3 s
            toast_content = Label(
                text=f'Opening in default reading app',
                halign='center',
                valign='middle',
            )
            toast_content.bind(size=lambda inst, _: setattr(inst, 'text_size', inst.size))

            self._open_toast = Popup(
                title=path.stem,           # book title in the popup title bar
                content=toast_content,
                size_hint=(None, None),
                size=(dp(320), dp(110)),
                auto_dismiss=True,         # clicking anywhere outside closes it
            )
            self._open_toast.open()
            # Auto-close after 3 s regardless of user input
            self._open_toast_event = Clock.schedule_once(
                lambda dt: self._open_toast.dismiss(), 3
            )

            if not open_in_default_app(path):
                # Cancel the "opening" toast, show error instead
                self._open_toast_event.cancel()
                self._open_toast.dismiss()
                self._show_error(f"Could not open: {path.name}")

    def _on_item_right_click(self, path_str: str, item_type: str):
        """Open the folder of the item in the file explorer (Windows/Mac/Linux)"""
        import subprocess
        path = Path(path_str)

        # For a file: open folder AND select file
        # For a folder: open folder
        if sys.platform == 'win32':
            if item_type == 'file':
                subprocess.Popen(['explorer', '/select,', str(path)])
            else:
                subprocess.Popen(['explorer', str(path)])
        elif sys.platform == 'darwin':  # macOS
            if item_type == 'file':
                subprocess.Popen(['open', '-R', str(path)])
            else:
                subprocess.Popen(['open', str(path)])
        else:  # Linux
            folder = path.parent if item_type == 'file' else path
            subprocess.Popen(['xdg-open', str(folder)])

    def _get_sidecar_files(self, path: Path) -> list:
        """Find sidecar files (metadata and cover) for a book
        Sidecar files follow the pattern:
        - book.pdf.md for metadata (Markdown with YAML frontmatter)
        - book.pdf.jpg/.png/.jpeg/.gif/.webp for cover
        Returns list of Path objects for existing sidecar files"""
        if not path.is_file():
            return []

        sidecars = []

        # Metadata sidecar: book.pdf.md
        md_path = path.parent / (path.name + '.md')
        if md_path.exists():
            sidecars.append(md_path)

        # cover sidecar: book.pdf.jpg, book.pdf.png, etc.
        COVER_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.gif', '.webp']
        for ext in COVER_EXTENSIONS:
            cover_path = path.parent / (path.name + ext)
            if cover_path.exists():
                sidecars.append(cover_path)
                break  # Slechts één cover per boek

        return sidecars

    def _move_selected(self):
        """Move selected items to another folder"""
        # Stop lopende tag filter batches onmiddellijk bij user interactie
        self._cancel_tag_filter_batches()

        if not self._selected_items:
            return

        selected_paths = [Path(p) for p in self._selected_items]

        # Collect selected widgets for deselect after cancel/move
        selected_widgets = []
        for child in self.grid.children:
            if hasattr(child, 'item_path') and child.item_path in self._selected_items:
                if hasattr(child, 'is_selected') and child.is_selected:
                    selected_widgets.append(child)

        # Show folder chooser
        content = BoxLayout(orientation='vertical')
        
        start_path = str(self._current_folder) if self._current_folder else str(Path.home())
        filechooser = FileChooserListView(path=start_path, dirselect=True, filters=[''])
        # Use modular helper for consistent FileChooser styling
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
            """Deselect all widgets - consistent with Edit Tags behavior"""
            for widget in selected_widgets:
                if hasattr(widget, 'is_selected'):
                    widget.is_selected = False
                    if hasattr(widget, '_update_tile'):
                        widget._update_tile()
            self._selected_items.clear()
            self.btn_edit_tags.disabled = True
            self.btn_move.disabled = True
            self.btn_delete.disabled = True
            self.btn_edit_tags.opacity = 0.5
            self.btn_move.opacity = 0.5
            self.btn_delete.opacity = 0.5
            self._update_status_with_selection()

        def on_move(instance): #Same name as in venv
            if not filechooser.selection:
                return
            dest = Path(filechooser.selection[0])
            if not dest.is_dir():
                return
            popup.dismiss()

            moved = 0
            skipped = 0  # Files already in target folder
            sidecars_moved = 0
            errors = []  # Real errors (not "already exists")
            moved_paths = set()  # Keep track of the paths that have actually been moved
            for path in selected_paths:
                try:
                    new_path = dest / path.name
                    if new_path.exists():
                        # File is already in target folder - skip (no error)
                        skipped += 1
                        continue

                    # Move sidecar files first (metadata en cover)
                    for sidecar in self._get_sidecar_files(path):
                        sidecar_dest = dest / sidecar.name
                        if not sidecar_dest.exists():
                            try:
                                shutil.move(str(sidecar), str(sidecar_dest))
                                sidecars_moved += 1
                            except Exception as e:
                                # Sidecar error not fataal, log is
                                errors.append(f"{sidecar.name}: {e}")

                    # Move the book itself
                    shutil.move(str(path), str(new_path))
                    moved += 1
                    moved_paths.add(str(path))  # Remember succesful move

                    # Update file cache: move entry to new path
                    self.file_cache.update_path(path, new_path)
                except Exception as e:
                    errors.append(f"{path.name}: {e}")

            # If twins filter, tag filter or search is active: remove only moved widgets
            if self._twins_filter_active or self._search_root or self._tag_filter_active or getattr(self, '_no_tag_filter_active', False):
                widgets_to_remove = []
                for child in self.grid.children:
                    # Only remove if actually moved (not skipped or error)
                    if hasattr(child, 'item_path') and child.item_path in moved_paths:
                        widgets_to_remove.append(child)
                for widget in widgets_to_remove:
                    self.grid.remove_widget(widget)
                # Deselect remaining widgets (skipped/error items)
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

            # Only show error popup if there are real errors, not if there are only skipped files
            if errors:
                self._show_error(f"Moved {moved} items.\n\nErrors:\n" + "\n".join(errors[:5]))

        def on_cancel(instance):
            popup.dismiss()
            _deselect_all()

        btn_cancel.bind(on_release=on_cancel)
        btn_move.bind(on_release=on_move)
        popup.open()

    def _delete_selected(self):
        """Delete selected items after confirmation"""
        # Stop lopende tag filter batches onmiddellijk bij user interactie
        self._cancel_tag_filter_batches()

        if not self._selected_items:
            return

        selected_paths = [Path(p) for p in self._selected_items]
        count = len(selected_paths)

        # Gather selected widgets for deselection after cancel/delete
        selected_widgets = []
        for child in self.grid.children:
            if hasattr(child, 'item_path') and child.item_path in self._selected_items:
                if hasattr(child, 'is_selected') and child.is_selected:
                    selected_widgets.append(child)

        # Check if there are folders with files in them
        # (counts all files, regardless of if they will be hidden in the grid)
        folders_with_files = 0
        for path in selected_paths:
            if path.is_dir():
                try:
                    # Check if folder not empty (any() stops with first hit)
                    if any(path.iterdir()):
                        folders_with_files += 1
                except (PermissionError, OSError):
                    pass

        # Determine warning text and if action is dangerous
        # Red button only for: folders with files in them, or permanent deletion (not for moving to trashcan)
        is_dangerous = False
        if folders_with_files == 1:
            warning_text = "Beware! This action will delete the files in this folder too!"
            is_dangerous = True
        elif folders_with_files > 1:
            warning_text = "Beware! This action will delete the files in these folders too!"
            is_dangerous = True
        elif HAS_SEND2TRASH:
            warning_text = f"Move {count} item(s) to trash?"
            is_dangerous = False  # Simpele trashcan operation, not dangerous
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
                    # Remove sidecar files first(metadata en cover)
                    for sidecar in self._get_sidecar_files(path):
                        try:
                            if HAS_SEND2TRASH:
                                send2trash(str(sidecar))
                            else:
                                sidecar.unlink()
                            sidecars_deleted += 1
                        except Exception as e:
                            # Sidecar error not fatal, but log is
                            errors.append(f"{sidecar.name}: {e}")

                    # Remove the book itself
                    if HAS_SEND2TRASH:
                        # Use send2trash for cross-platform bin support
                        send2trash(str(path))
                    else:
                        # Fallback: permanent removal
                        if path.is_file():
                            path.unlink()
                        elif path.is_dir():
                            shutil.rmtree(path)
                    deleted += 1

                    # Remove from file cache
                    self.file_cache.invalidate(path)

                except Exception as e:
                    errors.append(f"{path.name}: {e}")

            # If twins filter or search active: delete only the widgets from the grid without loading the entire folder again (prevents recalculation/reset)
            if self._twins_filter_active or self._search_root:
                widgets_to_remove = []
                for child in self.grid.children:
                    if hasattr(child, 'item_path') and child.item_path in self._selected_items:
                        widgets_to_remove.append(child)
                for widget in widgets_to_remove:
                    self.grid.remove_widget(widget)
                self._selected_items.clear()
                # Update status with number of remaining items
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
            """Deselect all widgets - consistent with Edit Tags behavior"""
            for widget in selected_widgets:
                if hasattr(widget, 'is_selected'):
                    widget.is_selected = False
                    if hasattr(widget, '_update_tile'):
                        widget._update_tile()
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
        """Handle search text change - triggers recursive search with debouncing
        Debouncing: wait 400ms after user stops typing before search starts. This prevents every keystroke from starting a heavy recursive search"""
        self._search_text = value.lower().strip()

        # Cancel planned search if there is one
        if hasattr(self, '_search_event') and self._search_event:
            self._search_event.cancel()
            self._search_event = None

        if not self._search_text:
            # Recover normal folder view
            self._clear_search()
        else:
            # Schedule search after 400ms debounce delay
            self._search_event = Clock.schedule_once(
                lambda dt: self._start_async_search(), 0.4
            )

    def _search_match(self, pattern: str, text: str) -> bool:
        """Check if pattern matches text, depending on fuzzy_search setting
        If fuzzy_search=False: only exact substring match (case insensitive)
        If fuzzy_search=True: also fuzzy match (all chars appear in sequence)"""
        pattern = pattern.lower()
        text = text.lower()

        # Alway try the exact substring match first
        if pattern in text:
            return True

        # Only fuzzy match if setting is on
        if self.custom.get('fuzzy_search', False):
            pattern_idx = 0
            for char in text:
                if pattern_idx < len(pattern) and char == pattern[pattern_idx]:
                    pattern_idx += 1
            return pattern_idx == len(pattern)

        return False

    def _start_async_search(self):
        """Start asynchrone search - collects files first, then batch processing
        SPECIAL: If the search term is a file type from selected_types.txt (like ".epub"), all files of that type are shown"""
        import time

        if not self._current_folder or not self._search_text:
            return

        # Save search root so we can go back to normal view
        if not self._search_root:
            self._search_root = self._current_folder

        # Cancel any running scheduled batches
        if hasattr(self, '_search_batch_event') and self._search_batch_event:
            self._search_batch_event.cancel()
            self._search_batch_event = None
        if hasattr(self, '_search_results_event') and self._search_results_event:
            self._search_results_event.cancel()
            self._search_results_event = None

        # Increment search version to cancel old searches
        self._search_version = getattr(self, '_search_version', 0) + 1
        current_version = self._search_version

        # Check if search term is a file type (f.e. ".epub", "epub", ".pdf")
        search_term = self._search_text
        if not search_term.startswith('.'):
            search_term_with_dot = '.' + search_term
        else:
            search_term_with_dot = search_term

        # Check if it is a file type from selected_types.txt
        is_file_type_search = search_term_with_dot.lower() in self.selected_types

        if is_file_type_search:
            self.status_label.text = f"Finding all {search_term_with_dot} files..."
        else:
            self.status_label.text = f"Searching for '{self._search_text}'..."

        # Clear grid 
        HoverBehavior._destroy_active_tooltip()
        self.grid.clear_widgets()
        self._selected_items.clear()
        self._hidden_widgets = []

        # Collect all files recursively (this is fast, only file system)
        all_files = []
        self._collect_files_recursive(self._current_folder, all_files, max_depth=10)

        # For file type search: filter directly on extension, no metadata matching needed
        if is_file_type_search:
            matching_files = [f for f in all_files if f.suffix.lower() == search_term_with_dot.lower()]
            self._search_matches = matching_files
            self._pending_search_files = []  # Geen batch processing nodig
            self._search_batch_index = 0
            self._current_search_version = current_version
            # Toon direct resultaten
            self._show_search_results(expected_version=current_version)
            return

        # Start batch processing for metadata matching
        self._pending_search_files = all_files
        self._search_matches = []
        self._search_batch_index = 0
        self._current_search_version = current_version
        # Track start time for progress estimation
        self._search_start_time = time.time()
        # Give expected_version so the batch chain follows this version
        self._process_search_batch(expected_version=current_version)

    def _process_search_batch(self, dt=None, expected_version=None):
        """Process a batch of files for search matching
        Processes 50 files per batch to keep the UI responsive
        Checks search_version to stop when a new search has been stared
        Parameters:
            dt: delta time van Clock scheduler (not used but required by Kivy)
            expected_version: the search version for which this batch has been started. If this does not match _search_version, a new search has been started and therefore we stop"""
        # Stop if search is cancelled or a new search has been started
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

        # Process this batch
        for i in range(start_idx, end_idx):
            file_path = files[i]
            # Filename check first (quick)
            if self._search_match(self._search_text, file_path.name):
                self._search_matches.append(file_path)
            # Only metadata check if filename does not match (slow)
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
            # More to process - schedule next batch
            # Save event so it can be cancelled in case of a new user command
            # Use partial to record expected_version on the schedule-moment
            self._search_batch_event = Clock.schedule_once(
                partial(self._process_search_batch, expected_version=expected_version), 0)
        else:
            # Ready - show results
            self._show_search_results(expected_version)

    def _show_search_results(self, expected_version=None):
        """Show search results after batch processing
        Parameter expected_version: the search version for these results Is passed on to _add_search_results_batch"""
        if expected_version is None:
            expected_version = getattr(self, '_current_search_version', None)
        if expected_version is None:
            return
        if expected_version != self._search_version:
            return  # Cancelled - newer user input exists

        matching_files = self._search_matches

        # Sort alfabetically on name
        matching_files.sort(key=lambda p: p.name.lower())

        # IMPORTANT: Clear grid before showing results
        HoverBehavior._destroy_active_tooltip()
        self.grid.clear_widgets()
        self._selected_items.clear()

        # Add widgets in batches for large results
        self._pending_search_results = matching_files
        self._search_results_index = 0
        # Pass on expected_version so the batch knows
        self._add_search_results_batch(expected_version=expected_version)

    def _add_search_results_batch(self, dt=None, expected_version=None):
        """Add search results to grid in batches
        Parameters:
            dt: delta time of Clock scheduler (not used but required by Kivy)
            expected_version: the search version of this batch. If this is not the same as _search_version, we stop"""
        if expected_version is None:
            expected_version = getattr(self, '_current_search_version', None)
        if expected_version is None:
            return
        if expected_version != self._search_version:
            return  # Cancelled - a new user command has been given 

        BATCH_SIZE = 20
        files = self._pending_search_results
        start_idx = self._search_results_index
        end_idx = min(start_idx + BATCH_SIZE, len(files))

        for i in range(start_idx, end_idx):
            self._add_file_widget(files[i])

        self._search_results_index = end_idx

        if end_idx < len(files):
            # Save event so that it can be cancelled in case of a new user command
            # Use partial to record expected_version on the schedule-moment
            self._search_results_event = Clock.schedule_once(
                partial(self._add_search_results_batch, expected_version=expected_version), 0)
        else:
            # Ready
            self._folder_count = 0
            self._file_count = len(files)
            self.status_label.text = f"Found {len(files)} files matching '{self._search_text}'"

    def _file_matches_search_metadata(self, file_path: Path) -> bool:
        """Check if file metadata matches the search term (NOT file name)
        This is the slow version, only called if file name does not match
        Uses file_cache for quick lookup if available
        If fuzzy_search=True: searches booktitle, author, isbn, cover
        If fuzzy_search=False: searches ONLY booktitle and author (exacte substring match)"""
        is_fuzzy = self.custom.get('fuzzy_search', False)

        try:
            # Use file_cache for fast lookup
            cached = self.file_cache.get_or_extract(file_path, self.extractor)

            if cached:
                if cached.booktitle and self._search_match(self._search_text, cached.booktitle):
                    return True
                for author in cached.authors:
                    if self._search_match(self._search_text, author):
                        return True
                # ISBN and cover only for fuzzy search
                if is_fuzzy:
                    if cached.isbn and self._search_match(self._search_text, cached.isbn):
                        return True
                    if cached.cover and self._search_match(self._search_text, cached.cover):
                        return True

        except Exception:
            # Corrupt file, permission error, etc.: skip
            pass

        return False

    def _clear_search(self):
        """Delete search results and recover normal folder view"""
        # Cancel a running search if it exists
        if hasattr(self, '_search_event') and self._search_event:
            self._search_event.cancel()
            self._search_event = None
        # Increment version to stop batch processing
        self._search_version = getattr(self, '_search_version', 0) + 1

        self._search_root = None
        self._hidden_widgets = []
        if self._current_folder:
            self._load_folder(self._current_folder)

    def _normalize_title(self, title: str) -> str:
        """Normalize title for duplicate comparison (Calibre-style)
        - Lowercase
        - Remove common prefixes: A, An, The, De, Het, Een
        - Remove punctuation
        - Collapse whitespace"""
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
        """Normalize author name for duplicate comparison (Calibre-style)
        - Lowercase
        - Remove jr, sr, phd, md, etc.
        - Remove punctuation
        - Simplify to lastname + first initial(s)"""
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
        """Get list of normalized author names from widget"""
        if hasattr(widget, 'authors') and widget.authors:
            return [self._normalize_author(a) for a in widget.authors if a]
        return []

    def _titles_match(self, title1: str, title2: str) -> bool:
        """Check if two titles are similar enough to be duplicates"""
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
        """Check if author lists have any matching authors"""
        if not authors1 or not authors2:
            return False

        norm1 = set(self._normalize_author(a) for a in authors1 if a)
        norm2 = set(self._normalize_author(a) for a in authors2 if a)

        # Any overlapping author is a match
        return bool(norm1 & norm2)

    def _toggle_twins_filter(self):
        """Toggle filter to show duplicate books (by ISBN or by title+author)"""
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
        """Show only duplicate books using Calibre-style logic
        IMPORTANT: Recursively searches ALL subfolders from current location
        Duplicates are found based on:
        1. Identical ISBN
        2. Similar title AND similar author (fuzzy matching)
        Results are grouped per duplicate set so that related books are next to eachother
        Uses an background thread for the heavy operations to keep the UI responsive. Clock.schedule_once is used to get the UI-updates back on the main thread"""
        self.status_label.text = "Scanning all subfolders for duplicates..."

        # Save root folder for relative path calculation
        self._twins_filter_root = self._current_folder

        # Start background thread for the heavy operations
        def background_scan():
            from concurrent.futures import ThreadPoolExecutor, as_completed

            # DEBUG mode: only if twins_debug.txt already exists in the folder
            # (user can create this file to get debug output)
            debug_file = self._current_folder / "twins_debug.txt"
            debug_mode = debug_file.exists()
            debug_lines = [] if debug_mode else None

            if debug_mode:
                debug_lines.append(f"=== TWINS FILTER DEBUG ===")
                debug_lines.append(f"Root folder: {self._current_folder}")
                debug_lines.append("")
                debug_lines.append("=== FILE COLLECTION ===")

            # Step 1: Collect all files from all subfolders recursively
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

            # Step 2: Get metadata with parallell processing (much faster!)
            # Use ThreadPoolExecutor for I/O-bound metadata extraction
            def extract_metadata(filepath):
                """Extract metadata for one file"""
                try:
                    # Use file_cache for fast lookup
                    cached = self.file_cache.get_or_extract(filepath, self.extractor)

                    if cached:
                        return [{
                            'path': filepath,
                            'isbn': cached.isbn or '',
                            'booktitle': cached.booktitle or filepath.stem,
                            'authors': cached.authors or [],
                        }]

                    # Fallback: direct extraction
                    meta = self.extractor.extract(filepath)
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
            # Use max 8 threads for metadata extraction
            max_workers = min(8, num_files)
            processed = 0

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {executor.submit(extract_metadata, fp): fp for fp in all_files}

                for future in as_completed(futures):
                    metadata_list = future.result()
                    file_metadata.extend(metadata_list)
                    processed += 1

                    # Update status every 100 files
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

            # Step 3: Find duplicates and group them by set
            # duplicate_sets is a list of lists - every sublist contains metadata of files that are duplicates of eachother
            duplicate_sets = []
            processed_items = set()

            def get_item_key(meta):
                """Generate unique key for a metadata entry"""
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
            # IMPORTANT: We build groups for ALL files (also those that are already in ISBN sets) so that a file with ISBN can also be matched with a file without ISBN
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
                    # Check how many items are not processed yet
                    unprocessed = [f for f in files if get_item_key(f) not in processed_items]
                    already_processed = [f for f in files if get_item_key(f) in processed_items]

                    if len(unprocessed) > 0 and len(already_processed) > 0:
                        # Some items are not matched yet but DO have the same title/author as items in an ISBN set
                        # ONLY add the unprocessed items, to prevent duplication
                        if debug_mode:
                            debug_lines.append(f"    -> CROSS-MATCH: adding {len(unprocessed)} new items (matched with {len(already_processed)} from ISBN sets)")
                        duplicate_sets.append(unprocessed)
                        for f in unprocessed:
                            processed_items.add(get_item_key(f))
                    elif len(unprocessed) > 1:
                        # Multiple new items with the same title/author
                        if debug_mode:
                            debug_lines.append(f"    -> DUPLICATE SET FOUND!")
                        duplicate_sets.append(unprocessed)
                        for f in unprocessed:
                            processed_items.add(get_item_key(f))
            if debug_mode:
                debug_lines.append("")

            # Fuzzy title matching - add to existing sets or make new ones
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
            Clock.schedule_once(lambda dt: self._show_duplicates_result(duplicate_sets))

        Thread(target=background_scan, daemon=True).start()

    def _show_duplicates_result(self, duplicate_sets: list):
        """Show the found duplicates in the grid, grouped per set
        duplicate_sets is a list of lists - each sublist contains metadata
        of files that are duplicates of eachother
        This function is called from Clock.schedule_once to make sure that
        UI updates happen on the main thread"""
        if not duplicate_sets:
            self.status_label.text = "No duplicates found in any subfolders"
            return

        # Empty grid and fill with duplicates per set
        HoverBehavior._destroy_active_tooltip()
        self.grid.clear_widgets()
        self._selected_items.clear()

        w, h = self.ZOOM_LEVELS[self._zoom_level]
        total_files = 0

        # Track which items have already been displayed to prevent duplicates
        shown_items = set()

        # Run through every duplicate set and add files
        # This way duplicates are always next to eachother
        for dup_set in duplicate_sets:
            # Sort within the set on folder path so that similar folders are close to eachother
            sorted_set = sorted(dup_set, key=lambda m: str(m['path'].parent))

            for meta in sorted_set:
                filepath = meta['path']

                # Skip if this item has been shown already
                if filepath in shown_items:
                    continue
                shown_items.add(filepath)

                file_type = filepath.suffix.lower()
                document_type = self._get_document_type(filepath)

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
                    on_right_click=self._on_item_right_click,
                    tile_font_color=self.TILE_FONT_COLOR,
                    background_color=self.BG_COLOR,
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
        """Collect all files from folder and subfolders, 10 layers deep"""
        if max_depth <= 0:
            if debug_lines is not None:
                debug_lines.append(f"  MAX DEPTH REACHED at {folder}")
            return

        try:
            if debug_lines is not None:
                debug_lines.append(f"  Scanning: {folder} (depth remaining: {max_depth})")

            for item in folder.iterdir():
                # Skip hidden files/folders (Unix: '.', Windows: hidden attribuut)
                #print(f"main.py line 3071")
                if is_hidden(item, self.selected_types):
                    if debug_lines is not None:
                        debug_lines.append(f"    SKIPPED (hidden): {item.name}")
                    continue

                if item.is_file():                   
                    # Filter op toegestane bestandstypes
                    if item.suffix.lower() not in self.selected_types:
                        if debug_lines is not None:
                            debug_lines.append(f"    SKIPPED (type filter): {item.name}")
                        continue
                    # Skip sidecar .md files: "book.pdf.md" if "book.pdf" exists
                    if item.suffix.lower() == '.md':
                        parent_path = item.parent / item.stem
                        if parent_path.is_file():
                            if debug_lines is not None:
                                debug_lines.append(f"    SKIPPED (sidecar): {item.name}")
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
        """Clear the twins filter and restore normal folder view
        Because the recursive twins filter replaces the entire grid content with only duplicate files from all subfolders, we must recover the normal view by reloading the current folder"""
        self._twins_filter_root = None
        if self._current_folder:
            self._load_folder(self._current_folder)

    def go_up(self):
        """Navigate to parent folder"""
        if self._current_folder and self._current_folder.parent != self._current_folder:
            self.navigate_to(self._current_folder.parent, add_to_history=True)
      
    def _update_nav_buttons(self): 
        """Update navigation button visibility"""
        # Back button: visible if parent folder exists
        has_parent = (
            self._current_folder is not None and
            self._current_folder.parent != self._current_folder
        )
        self.btn_back.opacity = 1 if has_parent else 0
        self.btn_back.disabled = not has_parent

    def _refresh(self):
        """Refresh current view (folder, twins, tag filter, or search)"""
        if self._twins_filter_active:
            # Twins filter active: execute twins filter again
            self._apply_twins_filter()
        elif self._tag_filter_active:
            # Tag filter active: execute tag filter again
            self._apply_tag_filter()
        elif self._search_root and self._search_text:
            # Search active: execute search again
            self._start_async_search()
        elif self._current_folder:
            # Normal folder view
            self._load_folder(self._current_folder)

    def _zoom_in(self):
        """Zoom in (larger covers)"""
        if self._zoom_level < len(self.ZOOM_LEVELS) - 1:
            self._zoom_level += 1
            self._update_grid_cols()
            self._refresh()

    def _zoom_out(self):
        """Zoom out (smaller covers)"""
        if self._zoom_level > 0:
            self._zoom_level -= 1
            self._update_grid_cols()
            self._refresh()

    def _open_bookspinescanner(self):
        """Open BookSpineScanner website in default browser"""
        import webbrowser
        webbrowser.open('https://sappelen.github.io/BookSpineScanner/')

    def _show_libiry_apps_popup(self):
        """Show popup with Libiry companion apps
        This is the "bento" menu popup, similar to Google Apps in Gmail f.e.
        - BookSpineScanner: opens website in browser
        - Calibre2Libiry: starts local tool (.bat on Windows, .py on Mac/Linux)
        - Libiry2Go: starts local tool (.bat on Windows, .py on Mac/Linux)"""
        content = BoxLayout(orientation='vertical', spacing=dp(10), padding=dp(15))

        # App buttons
        # 1. BookSpineScanner: Web App, show on all platforms
        btn_row_bss = self._create_popup_button_row()
        btn_bss = self._create_popup_button('BookSpineScanner')
        btn_row_bss.add_widget(btn_bss)
        content.add_widget(btn_row_bss)

        if platform != 'android':
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

            # 4. Align book data
            btn_row_abd = self._create_popup_button_row()
            btn_abd = self._create_popup_button('Align book data')
            btn_row_abd.add_widget(btn_abd)
            content.add_widget(btn_row_abd)

        # Spacer
        content.add_widget(BoxLayout(size_hint_y=1))

        # Cancel button
        btn_row_cancel = self._create_popup_button_row()
        btn_cancel = self._create_popup_button('Cancel')
        btn_row_cancel.add_widget(btn_cancel)
        content.add_widget(btn_row_cancel)

        # Create popup
        popup = self._create_popup('Libiry apps', content, size_hint=(0.4, 0.5))

        def on_bss(instance):
            popup.dismiss()
            self._open_bookspinescanner()

        def on_c2l(instance):
            popup.dismiss()
            self._start_companion_tool('Calibre2Libiry')

        def on_l2g(instance):
            popup.dismiss()
            self._start_companion_tool('Libiry2Go')

        def on_abd(instance):
            popup.dismiss()
            self._start_companion_tool('Align_book_data')

        btn_bss.bind(on_release=on_bss)
        if platform != 'android':
            btn_c2l.bind(on_release=on_c2l)
            btn_l2g.bind(on_release=on_l2g)
            btn_abd.bind(on_release=on_abd)
        btn_cancel.bind(on_release=lambda x: popup.dismiss())

        popup.open()

    def _start_companion_tool(self, tool_name: str):
        """Start a Libiry companion tool
        On Windows the .bat file is started, on Mac/Linux the .py file
        The tools share settings with Libiry via customize/customize.txt
        Args: tool_name (f.e. 'Calibre2Libiry' or 'Libiry2Go')"""
        import subprocess
        import sys

        # Determine the path to the tool
        app_dir = self._app_path

        if sys.platform == 'win32':
            # Windows: use .bat file
            tool_path = app_dir / f'{tool_name}.bat'
            if tool_path.exists():
                try:
                    # Start in own console frame, independently. Suppress DOS screen
                    #subprocess.Popen(
                    #    ['cmd', '/c', 'start', '', str(tool_path)],
                    #    cwd=str(app_dir),
                    #    shell=True
                    #)
                    subprocess.Popen(
                        ['cmd', '/c', str(tool_path)],
                        cwd=str(app_dir),
                        creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW
                    )
                    self.status_label.text = f"Started {tool_name}"
                except Exception as e:
                    self._show_error(f"Could not start {tool_name}: {e}")
            else:
                self._show_error(f"{tool_name}.bat not found")
        else:
            # Mac/Linux: use .py file with Python
            tool_path = app_dir / f'{tool_name.lower()}.py'
            # Try also with original casing
            if not tool_path.exists():
                tool_path = app_dir / f'{tool_name}.py'
            if tool_path.exists():
                try:
                    # Start Python script in background
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
        """Update grid columns based on window size and zoom level"""
        w, h = self.ZOOM_LEVELS[self._zoom_level]
        available_width = Window.width - dp(40)
        cols = max(1, int(available_width / (w + dp(20))))
        self.grid.cols = cols

    def _on_window_resize(self, window, width, height):
        """Handle window resize"""
        self._update_grid_cols()

    def _on_keyboard(self, window, key, scancode, codepoint, modifier):
        """Handle keyboard shortcuts
        On Windows codepoint can be None with Ctrl+letter combinations,
        that's why we use key codes as fallback
        Key codes: a=97, -=45, ==61, +=43"""
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
                self._select_all_tiles()
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
        if key == 27 and not modifier: #Escape key in _on_keyboard
            self._deselect_all()
            return True   
        if key == 273 and 'alt' not in modifier and 'ctrl' not in modifier: #Up arrow scroll
            step = (self.ZOOM_LEVELS[self._zoom_level][1] + dp(20) + dp(10)) / max(1, self.grid.height)
            self.scroll_view.scroll_y = min(1.0, self.scroll_view.scroll_y + step)
            return True
        if key == 274 and 'alt' not in modifier and 'ctrl' not in modifier: #Down arrow scroll
            step = (self.ZOOM_LEVELS[self._zoom_level][1] + dp(20) + dp(10)) / max(1, self.grid.height)
            self.scroll_view.scroll_y = max(0.0, self.scroll_view.scroll_y - step)
            return True
            
        return False

    def _on_modifier_key_down(self, window, key, scancode, codepoint, modifier):
        '''303 = right shift, 304 = left shift, 305 = left ctrl, 306 = right ctrl'''
        if key in (303, 304):
            self._shift_held = True
        if key in (305, 306):
            self._ctrl_held = True

    def _on_modifier_key_up(self, window, key, scancode):
        if key in (303, 304):
            self._shift_held = False
        if key in (305, 306):
            self._ctrl_held = False

    def _select_all_tiles(self):
        """Select all tiles in the grid"""
        if not hasattr(self, 'grid') or self.grid is None:
            return
        if not self.grid.children:
            return
        try:
            tiles = [c for c in self.grid.children if hasattr(c, 'is_selected')]
            if not tiles:
                return
            all_selected = all(t.is_selected for t in tiles)
            widgets_to_update = []
            for tile in tiles:
                if not tile.is_selected:
                    tile.is_selected = True
                    self._selected_items.add(tile.item_path)
                    widgets_to_update.append(tile)
            for tile in widgets_to_update:
                tile._update_tile()
            self._refresh_selection_ui()
        except Exception as e:
            print(f"Error in _select_all_tiles: {e}")
            import traceback
            traceback.print_exc()
              
    def _show_edit_tags_popup(self):
        """Show popup for editing metadata on selected items
        For 1 item: full metadata editor with all fields
        For multiple items: only tags editor (bulk editing)
        Supported fields (for 1 item):
        - cover, booktitle, author, isbn, rating, publisher, publication_date, language
        - series, series_index, tags, description, notes
        Tags are shown in a multiline text box (one tag per line),
        just like "file types" in the Settings popup"""
        # Stop running tag filter batches immediately at user interaction
        self._cancel_tag_filter_batches()

        if not self._selected_items:
            return

        # Save selected_paths for use in on_save callback
        selected_paths = [Path(p) for p in self._selected_items]

        # Collect widgets
        selected_widgets = []
        for child in self.grid.children:
            if hasattr(child, 'item_path') and child.item_path in self._selected_items:
                if hasattr(child, 'is_selected') and child.is_selected:
                    selected_widgets.append(child)

        item_count = len(selected_widgets) if selected_widgets else len(selected_paths)

        # For 1 item: show full metadata editor
        # For multiple items: show only tags editor
        if item_count == 1:
            self._show_full_metadata_editor(selected_widgets, selected_paths)
        else:
            self._show_tags_only_editor(selected_widgets, selected_paths)

    def _show_tags_only_editor(self, selected_widgets, selected_paths):
        """Show only tags editor for bulk editing of multiple items"""
        # Collect tags per WIDGET
        all_tags_per_item = []
        for widget in selected_widgets:
            widget_tags = set()
            if hasattr(widget, 'tags') and widget.tags:
                for tag in widget.tags:
                    if tag:
                        widget_tags.add(tag.strip())
            all_tags_per_item.append(widget_tags)

        # Fallback: if no widgets found, use paths
        if not all_tags_per_item:
            for path in selected_paths:
                file_tags = set()
                try:
                    meta = self.extractor.extract(path)
                    if meta and meta.tags:
                        for tag in meta.tags:
                            if tag:
                                file_tags.add(tag.strip())
                except Exception:
                    pass
                all_tags_per_item.append(file_tags)

        # Find common tags (intersection of all sets)
        if all_tags_per_item:
            common_tags = all_tags_per_item[0].copy()
            for item_tags in all_tags_per_item[1:]:
                common_tags &= item_tags
        else:
            common_tags = set()

        # Sort tags alphabetically
        common_tags_sorted = sorted(common_tags)
        original_tags = set(common_tags_sorted)
        tags_str = '\n'.join(common_tags_sorted)

        # Build popup content
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
                    if hasattr(widget, '_update_tile'):
                        widget._update_tile()
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
                tag = line.strip()  # Keep original case
                if tag.startswith('#'):
                    tag = tag[1:].strip()
                if tag:
                    new_tags.add(tag)

            # Tags are case-sensitive: direct comparison
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
        """Show full metadata editor for a single item
        Fields: cover, booktitle, author, author_sort, isbn, rating, publisher, publication_date, language, pages, series, series_index, translator, illustrator, tags, description, notes"""
        # Retrieve metadata from the selected item
        widget = selected_widgets[0] if selected_widgets else None
        path = selected_paths[0]

        # Read current metadata from cache (more consistent than direct extraction)
        # This prevents the loss of metadata by inconsistent extraction
        try:
            cached = self.file_cache.get_or_extract(path, self.extractor)
            if cached:
                # Convert cached file metadata to BookMetadata-like object
                meta = BookMetadata(
                    booktitle=cached.booktitle,
                    authors=cached.authors,
                    author_sort=cached.author_sort,
                    isbn=cached.isbn,
                    rating=cached.rating,
                    publisher=cached.publisher,
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
                    cover=cached.cover,
                )
            else:
                # Fallback to direct extraction
                meta = self.extractor.extract(path) #Same call as inside the get_or_extract routine
        except Exception as e:
            print(f"Error reading metadata: {e}")
            meta = None

        # Get configured field names
        field_names = self.custom.get('field_names', {})

        #print(f"DEBUG widget.booktitle: '{getattr(widget, 'booktitle', 'NO ATTR')}'")
        #print(f"DEBUG meta.booktitle: '{meta.booktitle if meta else 'NO META'}'")

        # Standard values
        current = {
            'cover': meta.cover if meta else '',
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

        # Save original tags for comparison (keep case)
        original_tags = set(t.strip() for t in (meta.tags if meta else []) if t)

        # Build scrollable popup content
        # Head container
        main_content = BoxLayout(orientation='vertical', padding=dp(10), spacing=dp(5))

        # Scrollable form area with customizeable scrollbar
        scroll = RoundedScrollView(
            size_hint=(1, 1),
            do_scroll_x=False,
            bar_width=self.SCROLLBAR_WIDTH,
            rounded=self.ROUNDED,
            bar_color_override=self.ACCENT_COLOR, # Aubergine
            scroll_type=['bars', 'content'],  # Needed for touch interaction
            always_visible=self.SCROLLBAR_ALWAYS_VISIBLE,
        )
        form = BoxLayout(orientation='vertical', size_hint_y=None, spacing=dp(8), padding=[0, 0, dp(10), 0])
        form.bind(minimum_height=form.setter('height'))

        # Dictionary to keep track of input widgets
        inputs = {}

        # Helper for form rows (label + input)
        def add_field(name, label_text, value, multiline=False, height_mult=1.0):
            row = BoxLayout(orientation='horizontal', size_hint_y=None, height=dp(100 * height_mult) if multiline else self.UI_BAR_HEIGHT)
            row.spacing = dp(10)

            # Label (30% width)
            lbl = self._create_popup_label(label_text, size_hint_x=0.3, halign='right')
            lbl.valign = 'top' if multiline else 'middle'
            row.add_widget(lbl)

            # Input (70% width)
            inp = self._create_popup_text_input(
                value, multiline=multiline, white_background=True, size_hint_x=0.7
            )
            row.add_widget(inp)
            inputs[name] = inp

            form.add_widget(row)

        # Add all fields
        # Section: Basic information
        add_field('cover', field_names.get('cover', 'cover') + ':', current['cover'])
        add_field('booktitle', field_names.get('booktitle', 'booktitle') + ':', current['booktitle'])
        add_field('author', field_names.get('author', 'author') + ':', current['author'])
        add_field('isbn', field_names.get('isbn', 'isbn') + ':', current['isbn'])

        # Section: Publication info
        add_field('publisher', field_names.get('publisher', 'publisher') + ':', current['publisher'])
        add_field('language', field_names.get('language', 'language') + ':', current['language'])

        # Section: Series info
        add_field('series', field_names.get('series', 'series') + ':', current['series'])
        add_field('series_index', field_names.get('series_index', 'series index') + ':', current['series_index'])

        # Sectien: Rating
        add_field('rating', field_names.get('rating', 'rating') + ' (0-5):', current['rating'])

        # Section: Tags (multiline)
        add_field('tags', field_names.get('tags', 'tags') + ':', current['tags'], multiline=True, height_mult=1.2)

        # Section: Extra fields
        add_field('author_sort', field_names.get('author_sort', 'author sort') + ':', current['author_sort'])
        add_field('publication_date', field_names.get('publication_date', 'publication date') + ':', current['publication_date'])
        add_field('pages', field_names.get('pages', 'pages') + ':', current['pages'])
        add_field('translator', field_names.get('translator', 'translator') + ':', current['translator'])
        add_field('illustrator', field_names.get('illustrator', 'illustrator') + ':', current['illustrator'])

        # Section: Description (multiline)
        add_field('description', field_names.get('description', 'description') + ':', current['description'], multiline=True, height_mult=1.5)

        # Section: Notities (multiline)
        add_field('notes', field_names.get('notes', 'notes') + ':', current['notes'], multiline=True, height_mult=1.2)

        scroll.add_widget(form)
        main_content.add_widget(scroll)

        # Buttons at the bottom
        btn_layout = self._create_popup_button_row()
        btn_cancel = self._create_popup_button('Cancel')
        btn_save = self._create_popup_button('Save')
        btn_layout.add_widget(btn_cancel)
        btn_layout.add_widget(btn_save)
        main_content.add_widget(btn_layout)

        # Popup with bigger size for all fields
        # 0.8 wide x 0.95 high for less scrolling
        popup = self._create_popup('Edit Metadata', main_content, size_hint=(0.8, 0.95))

        def _deselect_all_widgets():
            for w in selected_widgets:
                if hasattr(w, 'is_selected'):
                    w.is_selected = False
                    if hasattr(w, '_update_tile'):
                        w._update_tile()
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

            # Collect new values from user input
            def get_text(inp):
                if hasattr(inp, 'text_input'):
                    return inp.text_input.text.strip()
                return inp.text.strip() if hasattr(inp, 'text') else ''

            new_values = {}
            for name, inp in inputs.items():
                new_values[name] = get_text(inp)

            # Parse tags (keep original case)
            new_tags = set()
            for line in new_values['tags'].split('\n'):
                tag = line.strip()  # Keep case
                if tag.startswith('#'):
                    tag = tag[1:].strip()
                if tag:
                    new_tags.add(tag)

            # Build metadata object to save
            new_meta = {
                'cover': new_values['cover'],
                'booktitle': new_values['booktitle'],
                'author': new_values['author'],
                'author sort': new_values['author sort'],
                'isbn': new_values['isbn'],
                'rating': new_values['rating'],
                'publisher': new_values['publisher'],
                'publication date': new_values['publication date'],
                'language': new_values['language'],
                'pages': new_values['pages'],
                'series': new_values['series'],
                'series index': new_values['series index'],
                'translator': new_values['translator'],
                'illustrator': new_values['illustrator'],
                'tags': sorted(new_tags),
                'description': new_values['description'],
                'notes': new_values['notes'],
            }
            
            #print(f"DEBUG field_names: {field_names}")
            #print(f"DEBUG field_names.get('booktitle'): {field_names.get('booktitle', 'booktitle')}")
           
            try:
                use_sidecar = self.custom.get('metadata_in_sidecar', False)
                save_full_metadata(path, new_meta, use_sidecar=use_sidecar, field_names=field_names)

                # Update widget with new values
                if widget:
                    widget.booktitle = new_meta['booktitle']
                    widget.isbn = new_meta['isbn']
                    widget.tags = new_meta['tags']
                    if hasattr(widget, '_draw_document_type_triangle'):
                        widget._draw_document_type_triangle()

                # Update file cache - invalidate so the next load retrieves fresh data
                # The file has just been changed, so the cache entry is stale
                self.file_cache.invalidate(path)

                # Full refresh so that grid and tag list stay consistent. Because:
                # 1. In case of tag filter: file can disappear from view if tag has been removed
                # 2. In case of subfolder navigation: files in main folder must also be updated
                # 3. Tag list scans all subfolders recursively
                # Without refresh the user would have to refresh manually, which isn't intuitive
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

    def _start_async_tag_save(self, widgets_by_path: dict, tags_to_remove: set, tags_to_add: set, selected_widgets: list, deselect_callback):
        """Start async batch processing for saving tags
        Supports the addition or deletion of multiple tags
        Shows progress with time estimate
        Args:
            widgets_by_path: Dict with path -> list of widgets
            tags_to_remove: Set of tags to remove
            tags_to_add: Set of tags to add
            selected_widgets: List of selected widgets
            deselect_callback: Callback to deselect widgets afterwards"""
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
        """Process a batch of files for tag saving. Shows progress with time estimate. Supports batch addition of tags"""
        import time

        items = self._pending_tag_save_items
        if not items:
            return

        tags_to_remove = self._tag_save_tags_to_remove
        tags_to_add = self._tag_save_tags_to_add  
        start_idx = self._tag_save_batch_index
        total = len(items)

        # Process one file at a time (file operations can be slow)
        if start_idx >= total:
            self._finish_tag_save()
            return

        path_str, widgets = items[start_idx]
        path = Path(path_str)

        try:
            # Modify tags for this file
            file_modified = False
            if self._modify_file_tags(path, tags_to_remove, tags_to_add):
                self._tag_save_modified_count += len(widgets)
                file_modified = True

            # Update widget tags in memory ONLY if the file has been edited succesfully
            # This prevents the UI to show a different state than the file
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

                # Update file cache - invalidate so that the next load retrieves fresh data
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
        After a tag change a full refresh is done so that
        grid and tag list remain consistent. The tag list scans recursively all subfolders, so after a change the whole screen needs to be rebuilt"""
        modified_count = self._tag_save_modified_count

        # Deselect all items BEFORE refresh (otherwise we lose widget references)
        if hasattr(self, '_tag_save_deselect_callback') and self._tag_save_deselect_callback:
            self._tag_save_deselect_callback()

        if modified_count > 0:
            # Full refresh for consistent display
            self._refresh()
            self.status_label.text = f"Updated tags for {modified_count} item(s)"
        else:
            self.status_label.text = "No tags were modified"

    def _modify_file_tags(self, path: Path, tags_to_remove: set, tags_to_add: set) -> bool:
        """Modify tags in a file. Supports adding/removing multiple tags at once
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
        When 'metadata_in_sidecar' setting is True, tags are stored in sidecar files instead of in the book files themselves.
        Creates automatic backup in system temp directory for each change"""

        file_type = path.suffix.lower()
        field_names = self.custom.get('field_names', {}) 
        use_sidecar = self.custom.get('metadata_in_sidecar', False)

        if file_type in ('.md', '.markdown'): # Markdown files: modify the file itself
            return modify_markdown_tags(path, path, tags_to_remove, tags_to_add, field_names)
        elif use_sidecar: # User prefers sidecar: modify tags in sidecar file
            return modify_markdown_tags(path, get_sidecar_path(path), tags_to_remove, tags_to_add, field_names)
        elif file_type == '.epub':
            return modify_epub_tags(path, tags_to_remove, tags_to_add)
        elif file_type == '.cbz':
            return modify_cbz_tags(path, tags_to_remove, tags_to_add)
        elif file_type == '.opf':
            # OPF files are legacy sidecar files - skip
            return False
        else:
            # For all other file formats (.cbr, .mobi, .pdf, .rtf, .mp3, .txt, etc.): Use Markdown sidecar file for tag storage
            return modify_markdown_tags(path, get_sidecar_path(path), tags_to_remove, tags_to_add, field_names)

    def _cleanup_all_backups(self):
        """Delete all remaining temporary backups
        Is called at app closing to ensure that no
        backup files remain, not even after failed actions"""
        # Delete tracked backups
        if hasattr(self, '_temp_backups'):
            for backup_path in self._temp_backups[:]:  # Copy list to remove during iteration
                try:
                    if backup_path.exists():
                        backup_path.unlink()
                except Exception as e:
                    print(f"Warning: Could not remove backup {backup_path}: {e}")
            self._temp_backups.clear()

        # If the backup folder is empty, remove the folder too
        backup_dir = Path(tempfile.gettempdir()) / 'Libirybackup'
        if backup_dir.exists():
            try:
                # Remove all remaining files in the backup folder
                for f in backup_dir.iterdir():
                    try:
                        f.unlink()
                    except Exception:
                        pass
                # Try to delete the folder if it is empty
                if not any(backup_dir.iterdir()):
                    backup_dir.rmdir()
            except Exception:
                pass

    def _on_info_click(self, instance):
        """Handle info button click - open https://libiry.org/ in browser"""
        # Open the Libiry website in the user's default browser
        webbrowser.open('https://libiry.org/')

    def _on_gear_click(self, instance):
        """Handle gear button click - show settings"""
        self._show_settings()

    def _show_settings(self):
        """Show settings popup for editing customize.txt and selected types.txt"""
        ####from kivy.uix.textinput import TextInput

        # Main content layout
        content_layout = BoxLayout(orientation='vertical', padding=dp(10), spacing=dp(10))
        with content_layout.canvas.before:
            Color(*self.BG_COLOR)
            self._settings_bg = Rectangle(pos=content_layout.pos, size=content_layout.size)
        content_layout.bind(
            pos=lambda *x: setattr(self._settings_bg, 'pos', content_layout.pos),
            size=lambda *x: setattr(self._settings_bg, 'size', content_layout.size)
        )

        # Scrollable form
        # Scrollbar styling: width and visibility from customize settings
        scroll = RoundedScrollView(
            rounded=self.ROUNDED,
            bar_color_override=self.ACCENT_COLOR,
            size_hint=(1, 1),
            bar_width=self.SCROLLBAR_WIDTH,
            scroll_type=['bars', 'content'],
            always_visible=self.SCROLLBAR_ALWAYS_VISIBLE,
        )
        form = BoxLayout(orientation='vertical', size_hint_y=None, spacing=dp(8), padding=dp(5))
        form.bind(minimum_height=form.setter('height'))

        # Store references to input fields for saving
        self._settings_inputs = {}

        def add_field(label_text, key, value, is_color=False):
            """Add a labeled input field to the form with rounded background"""
            row = self._create_popup_row()
            label = self._create_popup_label(label_text, size_hint_x=0.4)
            row.add_widget(label)

            # Text input box
            input_container = self._create_popup_text_input(value, white_background=True, size_hint_x=0.6)
            row.add_widget(input_container)
            form.add_widget(row)
            self._settings_inputs[key] = input_container.text_input

        def add_section_header(text):
            """Add a section header, left-aligned"""
            header = self._create_popup_label(text, bold=True)
            header.size_hint_y = None
            header.height = self.UI_BAR_HEIGHT
            form.add_widget(header)

        # === FILE TYPES === (bovenaan voor snelle toegang)
        add_section_header('File types')
        types_str = '\n'.join(sorted(self.selected_types)) if self.selected_types else ''
        # Textarea row is 4x normal height
        types_row = self._create_popup_row(height_multiplier=4.0)
        types_label = self._create_popup_label('One per line', size_hint_x=0.4, valign='top')
        types_row.add_widget(types_label)

        # Text input with white background and rounded corners for types
        types_container = self._create_popup_text_input(types_str, multiline=True, white_background=True, size_hint_x=0.6)
        types_row.add_widget(types_container)
        form.add_widget(types_row)
        self._settings_inputs['selected_types'] = types_container.text_input

        # === APPEARANCE SETTINGS ===
        add_section_header('Customize appearance')
        #self._add_location_field(form, 'Start location', 'location', self.custom.get('location', ''))
        add_field('Screen color', 'background_color_hex', self._color_to_hex(self.custom['background_color'])) # because field background_color is known in the venv modules
        add_field('Font color', 'background_font_color_hex', self._color_to_hex(self.custom['background_font_color']))
        add_field('Accent color', 'accent_color_hex', self._color_to_hex(self.custom['accent_color']))
        add_field('Accent font color', 'accent_font_color_hex', self._color_to_hex(self.custom['accent_font_color']))
        add_field('Tile font color', 'tile_font_color_hex', self._color_to_hex(self.custom['tile_font_color']))
        add_field('Font size', 'font_size', str(self.custom['font_size']))
        add_field('Scrollbar width', 'scrollbar_width', str(self.custom['scrollbar_width']))
        add_field('Tag bar lines', 'tag_lines', str(self.custom['tag_lines']))
        self._add_yn_field(form, 'Scrollbar always visible', 'scrollbar_always_visible', self.custom['scrollbar_always_visible'])
        self._add_yn_field(form, 'Show book title', 'show_book_title', self.custom['show_book_title'])
        self._add_yn_field(form, 'Show tags', 'show_tags', self.custom['show_tags'])
        self._add_yn_field(form, 'Rounded corners', 'rounded_corners', self.custom['rounded_corners'])
        self._add_yn_field(form, 'Fuzzy search', 'fuzzy_search', self.custom['fuzzy_search'])
        self._add_yn_field(form, 'Store book data in sidecar', 'metadata_in_sidecar', self.custom['metadata_in_sidecar'])
        self._create_label(form, "", style='subtitle')
        # === FIELD NAME SETTINGS ===
        add_section_header('Custom field names')
        self._create_label(form, "Match your existing markdown field names", style='subtitle')
        # Retrieve field names from the nested field_names dict
        field_names = self.custom.get('field_names', {})
        add_field('Cover', 'field_cover', field_names.get('cover', 'cover'))
        add_field('Booktitle', 'field_booktitle', field_names.get('booktitle', 'booktitle'))
        add_field('Author', 'field_author', field_names.get('author', 'author'))
        add_field('Author sort', 'field_author_sort', field_names.get('author_sort', 'author sort'))
        add_field('ISBN', 'field_isbn', field_names.get('isbn', 'isbn'))
        add_field('Rating', 'field_rating', field_names.get('rating', 'rating'))
        add_field('Publisher', 'field_publisher', field_names.get('publisher', 'publisher'))
        add_field('Publication date', 'field_publication_date', field_names.get('publication_date', 'publication date'))
        add_field('Pages', 'field_pages', field_names.get('pages', 'pages'))
        add_field('Language', 'field_language', field_names.get('language', 'language'))
        add_field('Tags', 'field_tags', field_names.get('tags', 'tags'))
        add_field('Series', 'field_series', field_names.get('series', 'series'))
        add_field('Series index', 'field_series_index', field_names.get('series_index', 'series index'))
        add_field('Translator', 'field_translator', field_names.get('translator', 'translator'))
        add_field('Illustrator', 'field_illustrator', field_names.get('illustrator', 'illustrator'))
        add_field('Description', 'field_description', field_names.get('description', 'description'))
        add_field('Notes', 'field_notes', field_names.get('notes', 'notes'))
        # Retrieve field names from the nested field_names dict
        add_field('Book creation date (system)', 'field_book_created', field_names.get('book_created', 'book created'))
        add_field('Book modification date (system)', 'field_book_modified', field_names.get('book_modified', 'book modified'))

        scroll.add_widget(form)
        content_layout.add_widget(scroll)

        # Button row with helpers for consistent styling
        btn_row = self._create_popup_button_row()
        btn_cancel = self._create_popup_button('Cancel')
        btn_save = self._create_popup_button('Save')

        btn_row.add_widget(btn_cancel)
        btn_row.add_widget(btn_save)
        content_layout.add_widget(btn_row)

        popup = self._create_popup('Settings', content_layout, size_hint=(0.85, 0.9))

        def on_save(instance):
            self._save_settings()
            # Show warning message. Settings popup stays open so the user can proceed if they wish to
            info_label = self._create_popup_label(
                'Your changes will become effective after restart',
                halign='center',
                valign='middle',
            )
            info_popup = self._create_popup('Settings saved', info_label, size_hint=(0.6, 0.3))
            # Background color for the popup content
            with info_popup.content.canvas.before:
                Color(*self.BG_COLOR)
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
        """Convert RGBA tuple to hex string or named color
        If the color corresponds with a known color name, show that name so that end users know that they can also enter color names"""
        if isinstance(color, str):
            return color

        # Known colors: tuple -> name mapping
        # Compare with a small tolerance for floating point
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

        # Check if color (/w tolerance) corresponds with a known color
        r, g, b = round(color[0], 2), round(color[1], 2), round(color[2], 2)
        for known_rgb, name in named_colors.items():
            if (abs(r - known_rgb[0]) < 0.05 and
                abs(g - known_rgb[1]) < 0.05 and
                abs(b - known_rgb[2]) < 0.05):
                return name

        # No known color, use hex
        r_int, g_int, b_int = int(color[0] * 255), int(color[1] * 255), int(color[2] * 255)
        return f'#{r_int:02X}{g_int:02X}{b_int:02X}'

    def _save_settings(self):
        """Save settings to customize.txt and selected types.txt"""

        inputs = self._settings_inputs

        # Build customize.txt content
        lines = []
        lines.append(f"Location: self.custom.get('location', '')") #Location is no longer maintained in the settings screen, but the Location line may not be removed from customize.txt, so keep doing this here
        lines.append(f"Background color: {inputs['background_color_hex'].text}")
        lines.append(f"Background font color: {inputs['background_font_color_hex'].text}")
        lines.append(f"Accent color: {inputs['accent_color_hex'].text}")
        lines.append(f"Accent font color: {inputs['accent_font_color_hex'].text}")
        lines.append(f"Tile font color: {inputs['tile_font_color_hex'].text}")
        lines.append(f"Rounded corners: {'Y' if inputs['rounded_corners'].active else 'N'}")
        lines.append(f"Fuzzy search: {'Y' if inputs['fuzzy_search'].active else 'N'}")
        lines.append(f"Metadata in sidecar: {'Y' if inputs['metadata_in_sidecar'].active else 'N'}")
        lines.append(f"Scrollbar width: {inputs['scrollbar_width'].text}")
        lines.append(f"Scrollbar always visible: {'Y' if inputs['scrollbar_always_visible'].active else 'N'}")
        lines.append(f"Show book title: {'Y' if inputs['show_book_title'].active else 'N'}")
        lines.append(f"Show tags: {'Y' if inputs['show_tags'].active else 'N'}")
        lines.append(f"Tag lines: {inputs['tag_lines'].text}")
        lines.append(f"Font size: {inputs['font_size'].text}")
        lines.append("")
        lines.append("# Configurable field names (sequence based on Goodreads CSV export)")
        lines.append(f"Field name cover: {inputs['field_cover'].text}")
        lines.append(f"Field name booktitle: {inputs['field_booktitle'].text}")
        lines.append(f"Field name author: {inputs['field_author'].text}")     
        lines.append(f"Field name author_sort: {inputs['field_author_sort'].text}")
        lines.append(f"Field name isbn: {inputs['field_isbn'].text}")
        lines.append(f"Field name rating: {inputs['field_rating'].text}")
        lines.append(f"Field name publisher: {inputs['field_publisher'].text}")
        lines.append(f"Field name publication_date: {inputs['field_publication_date'].text}")
        lines.append(f"Field name pages: {inputs['field_pages'].text}")
        lines.append(f"Field name language: {inputs['field_language'].text}")
        lines.append(f"Field name tags: {inputs['field_tags'].text}")
        lines.append(f"Field name series: {inputs['field_series'].text}")
        lines.append(f"Field name series_index: {inputs['field_series_index'].text}")
        lines.append(f"Field name translator: {inputs['field_translator'].text}")
        lines.append(f"Field name illustrator: {inputs['field_illustrator'].text}")
        lines.append(f"Field name description: {inputs['field_description'].text}")
        lines.append(f"Field name notes: {inputs['field_notes'].text}")
        
        lines.append("")
        lines.append("# Configurable field names for field that are filled automatically")
        lines.append(f"Field name book_created: {inputs['field_book_created'].text}")
        lines.append(f"Field name book_modified: {inputs['field_book_modified'].text}")

        # Write customize.txt
        customize_path = get_user_data_dir() / 'customize' / 'customize.txt'
        try:
            customize_path.parent.mkdir(parents=True, exist_ok=True)
            customize_path.write_text('\n'.join(lines), encoding='utf-8')
        except Exception as e:
            self._show_error(f"Could not save customize.txt: {e}")
            return

        # Clear file cache when metadata_in_sidecar changes
        # Because, when Save to sidecar is set to No and the sidecar is manually removed, the original metadata should reappear, and no sidecar-originating metadata be read from cache
        if inputs['metadata_in_sidecar'].active != self.custom.get('metadata_in_sidecar', False):
            self.file_cache.clear()

        # Write selected types.txt
        types_path = get_user_data_dir() / 'customize' / 'selected types.txt'
        types_text = inputs['selected_types'].text.strip()
        types_lines = [t.strip() for t in types_text.split('\n') if t.strip()]
        try:
            types_path.write_text('\n'.join(types_lines) + '\n', encoding='utf-8')
        except Exception as e:
            self._show_error(f"Could not save selected types.txt: {e}")
            return

        # Settings only become active after restart, so no reload needed (reload during runtime can cause crashes by format mismatches)
        
    def _save_session_state(self):
        """Save zoom level to settings.json and current folder to customize.txt
        Note: This is APART from _save_settings() that saves customize.txt completely and also saves and selected types.txt"""
        try:
            get_user_data_dir().mkdir(parents=True, exist_ok=True)
            self.store.put('zoom_level', value=self._zoom_level)
        except Exception as e:
            print(f"Error saving session state: {e}")
            
        #print(f"DEBUG self._current_folder('{self._current_folder}')")
        if self._current_folder:
            # Write the current folder to the 'Location:' line in customize/customize.txt
            # Read the file, update or insert the Location line, write it back
            self.custom['location'] = str(self._current_folder)
            customize_path = get_user_data_dir() / 'customize' / 'customize.txt'
            try:
                customize_path.parent.mkdir(parents=True, exist_ok=True)
                if customize_path.exists():
                    lines = customize_path.read_text(encoding='utf-8').splitlines()
                    for i, line in enumerate(lines):
                        if line.strip().lower().startswith('location:'):
                            lines[i] = f'Location: {self._current_folder}'
                            break
                    else:
                        lines.insert(0, f'Location: {self._current_folder}')
                    customize_path.write_text('\n'.join(lines), encoding='utf-8')
                else:
                    customize_path.write_text(f'Location: {self._current_folder}\n', encoding='utf-8')
            except Exception as e:
                print(f"Error saving location: {e}")

    def _on_close_request(self, *args):
        """Handle window close request (X button)
        Close the app immediately without waiting on running tasks
        Cancel all scheduled events to prevent blocking"""
        # Cancel all running batch events
        if hasattr(self, '_batch_load_event') and self._batch_load_event:
            self._batch_load_event.cancel()
        if hasattr(self, '_tag_filter_batch_event') and self._tag_filter_batch_event:
            self._tag_filter_batch_event.cancel()
        if hasattr(self, '_no_tag_filter_batch_event') and self._no_tag_filter_batch_event:
            self._no_tag_filter_batch_event.cancel()
        if hasattr(self, '_tag_update_event') and self._tag_update_event:
            self._tag_update_event.cancel()

        # Stop the app immediately
        self.stop()
        return True  # Prevent default close handling, we handled it

    def on_stop(self):
        """Handle app stop. Cleans up all temporary backups when closing the app, even if some actions failed"""
        self._cleanup_all_backups()
        self._save_session_state()
        self.file_cache.close()

def clear_cache():
    """Clear the entire Libiry cache folder
    Gets called in case of startup issues to remove corrupt cache"""
    cache_dir = get_cache_dir()
    if cache_dir.exists():
        try:
            shutil.rmtree(cache_dir)
            print(f"Cache cleared: {cache_dir}")
        except Exception as e:
            print(f"Error clearing cache: {e}")

def main():
    """Main entry point
    In case of startup issues the cache is automatically cleared and the app is automatically started again"""
    try:
        LibiryApp().run()
    except Exception as e:
        print(f"Startup error: {e}")
        print("Clearing cache and restarting...")
        clear_cache()
        # Try to start again after clearing the cache
        try:
            LibiryApp().run()
        except Exception as e2:
            print(f"Failed to restart after cache clear: {e2}")
            raise

if __name__ == '__main__':
    main()