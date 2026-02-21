"""Grid widget for displaying folders and files using Kivy RecycleView."""

from kivy.uix.recycleview import RecycleView
from kivy.uix.recycleview.views import RecycleDataViewBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.behaviors import ButtonBehavior
from kivy.properties import StringProperty, BooleanProperty, ObjectProperty, NumericProperty
from kivy.clock import Clock
from kivy.core.image import Image as CoreImage
from kivy.graphics.texture import Texture
from pathlib import Path
from threading import Thread
from PIL import Image as PILImage
import io


class GridItem(RecycleDataViewBehavior, ButtonBehavior, BoxLayout):
    """Individual grid item (folder or book cover)."""

    index = NumericProperty(0)
    item_path = StringProperty('')
    item_type = StringProperty('file')
    thumb_path = StringProperty('')
    item_name = StringProperty('')
    is_selected = BooleanProperty(False)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'vertical'
        self.size_hint = (None, None)
        self.padding = 5
        self.spacing = 2

    def refresh_view_attrs(self, rv, index, data):
        """Update view with new data."""
        self.index = index
        self.item_path = data.get('path', '')
        self.item_type = data.get('type', 'file')
        self.thumb_path = data.get('thumb', '')
        self.item_name = data.get('name', '')
        self.is_selected = data.get('selected', False)
        return super().refresh_view_attrs(rv, index, data)

    def on_touch_down(self, touch):
        """Handle touch/click."""
        if self.collide_point(*touch.pos):
            if touch.is_double_tap:
                self.parent.parent.on_item_double_tap(self.index)
                return True
            else:
                self.parent.parent.on_item_tap(self.index)
                return True
        return super().on_touch_down(touch)

    def apply_selection(self, rv, index, is_selected):
        """Apply selection state."""
        self.is_selected = is_selected


class BookGrid(RecycleView):
    """Grid view for displaying book covers and folders."""

    # Callbacks
    on_folder_open = ObjectProperty(None)
    on_book_open = ObjectProperty(None)

    # Zoom levels (width, height)
    ZOOM_LEVELS = [
        (100, 150),
        (150, 225),
        (200, 300),
        (250, 375),
    ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._zoom_level = 1
        self._items_data = []
        self._selected_indices = set()
        self._cache = None
        self._extractor = None
        self._current_folder = None

        # Configure layout
        self.viewclass = 'GridItemWidget'
        from kivy.uix.recycleview.layout import RecycleGridLayout
        from kivy.uix.recyclegridlayout import RecycleGridLayout

        self.layout_manager = RecycleGridLayout()
        self.layout_manager.default_size_hint = (None, None)
        self.layout_manager.spacing = 10
        self.layout_manager.padding = 10
        self._update_grid_size()

    def _update_grid_size(self):
        """Update grid cell sizes based on zoom level."""
        w, h = self.ZOOM_LEVELS[self._zoom_level]
        if hasattr(self, 'layout_manager'):
            self.layout_manager.default_size = (w + 20, h + 40)
            self.layout_manager.cols = max(1, int((self.width - 20) / (w + 30))) if self.width > 0 else 3

    def on_size(self, *args):
        """Handle resize to adjust columns."""
        self._update_grid_size()

    def set_cache_and_extractor(self, cache, extractor):
        """Set the cover cache and extractor."""
        self._cache = cache
        self._extractor = extractor

    def load_folder(self, folder_path: Path):
        """Load and display folder contents."""
        self._current_folder = folder_path
        self._items_data = []
        self._selected_indices.clear()

        if not folder_path.exists():
            self.data = []
            return

        try:
            items = sorted(folder_path.iterdir(), key=lambda x: x.name.lower())
        except PermissionError:
            self.data = []
            return

        folders = []
        files = []

        for item in items:
            if item.name.startswith('.'):
                continue

            if item.is_dir():
                try:
                    count = sum(1 for f in item.iterdir() if not f.name.startswith('.'))
                except PermissionError:
                    count = 0
                folders.append({
                    'path': str(item),
                    'type': 'folder',
                    'name': item.name,
                    'count': count,
                    'thumb': '',
                    'selected': False,
                })
            elif item.suffix.lower() in {'.epub', '.mobi', '.azw', '.azw3', '.pdf', '.cbz', '.cbr', '.md'}:
                files.append({
                    'path': str(item),
                    'type': 'file',
                    'name': item.stem,
                    'thumb': '',
                    'selected': False,
                })

        self._items_data = folders + files
        self.data = self._items_data

        # Load covers in background
        if self._cache and self._extractor:
            Thread(target=self._load_covers_async, daemon=True).start()

    def _load_covers_async(self):
        """Load covers in background thread."""
        for i, item in enumerate(self._items_data):
            if item['type'] == 'file' and not item['thumb']:
                try:
                    filepath = Path(item['path'])
                    thumb_path = self._cache.get_cover(filepath, self._extractor)
                    # Schedule UI update on main thread
                    Clock.schedule_once(lambda dt, idx=i, tp=str(thumb_path): self._update_thumb(idx, tp), 0)
                except Exception as e:
                    print(f"Error loading cover: {e}")

    def _update_thumb(self, index, thumb_path):
        """Update thumbnail in UI (must be called from main thread)."""
        if index < len(self._items_data):
            self._items_data[index]['thumb'] = thumb_path
            self.refresh_from_data()

    def on_item_tap(self, index):
        """Handle single tap - toggle selection."""
        if index < len(self._items_data):
            if index in self._selected_indices:
                self._selected_indices.discard(index)
                self._items_data[index]['selected'] = False
            else:
                self._selected_indices.add(index)
                self._items_data[index]['selected'] = True
            self.refresh_from_data()

    def on_item_double_tap(self, index):
        """Handle double tap - open item."""
        if index < len(self._items_data):
            item = self._items_data[index]
            path = Path(item['path'])
            if item['type'] == 'folder':
                if self.on_folder_open:
                    self.on_folder_open(path)
            else:
                if self.on_book_open:
                    self.on_book_open(path)

    def zoom_in(self) -> bool:
        """Increase icon size."""
        if self._zoom_level < len(self.ZOOM_LEVELS) - 1:
            self._zoom_level += 1
            self._update_grid_size()
            self.refresh_from_data()
            return True
        return False

    def zoom_out(self) -> bool:
        """Decrease icon size."""
        if self._zoom_level > 0:
            self._zoom_level -= 1
            self._update_grid_size()
            self.refresh_from_data()
            return True
        return False

    def get_zoom_level(self) -> int:
        """Get current zoom level."""
        return self._zoom_level

    def filter_items(self, search_text: str) -> int:
        """Filter items by search text."""
        if not search_text:
            self.data = self._items_data
            return len(self._items_data)

        search_lower = search_text.lower()
        filtered = [
            item for item in self._items_data
            if search_lower in item['name'].lower()
        ]
        self.data = filtered
        return len(filtered)

    def get_selected_paths(self):
        """Get list of selected item paths."""
        return [
            Path(self._items_data[i]['path'])
            for i in self._selected_indices
            if i < len(self._items_data)
        ]

    def clear_selection(self):
        """Clear all selections."""
        for i in self._selected_indices:
            if i < len(self._items_data):
                self._items_data[i]['selected'] = False
        self._selected_indices.clear()
        self.refresh_from_data()
