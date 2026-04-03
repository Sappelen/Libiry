#!/usr/bin/env python3
"""
Libiry2Go - Portable book catalog generator

Creates markdown files from your ebook library that you can take on your phone.
Extracts metadata from ebooks and markdown files.
One file per book in Obsidian format (YAML frontmatter).

Uses Libiry's customize.txt for field name configuration, so your field names stay consistent.

Usage:
    python libiry2go.py                          # Opens GUI for folder selection
    python libiry2go.py "C:/Books"               # Scan folder, output next to it
    python libiry2go.py "C:/Books" "C:/Out"      # Scan folder, custom output location
"""

import sys
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, List
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import threading

# Windows taskbar icon fix: set AppUserModelID so Windows
# shows the correct icon in the taskbar instead of the Python icon
try:
    import ctypes
    # Unique ID for Libiry apps - Windows groups windows with the same ID
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('Libiry.Libiry2Go.1')
except (ImportError, AttributeError, OSError):
    pass  # Not on Windows or ctypes not available

# Add Libiry's core folder to path so we can use the extractors
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

try:
    from core.metadata_extractor import (
        MetadataExtractor, BookMetadata,
        get_sidecar_path, read_sidecar_as_dict, consolidate_metadata_to_sidecar,
        find_cover_for_ebook
    )
    from core.libiry_style import load_field_names, load_selected_types
except ImportError:
    # Standalone mode - basic metadata extraction
    MetadataExtractor = None
    BookMetadata = None
    get_sidecar_path = None
    read_sidecar_as_dict = None
    consolidate_metadata_to_sidecar = None
    find_cover_for_ebook = None
    load_field_names = None
    load_selected_types = None


# =============================================================================
# Configuration
# =============================================================================


# Extensions for which metadata extraction is possible
EBOOK_EXTENSIONS = {'.epub', '.mobi', '.azw', '.azw3', '.pdf', '.cbr', '.cbz'}
MARKDOWN_EXTENSIONS = {'.md', '.markdown'}


def format_file_size(size_bytes: int) -> str:
    """Format file size to human-readable string."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"


# =============================================================================
# Metadata Extraction
# =============================================================================

class SimpleMetadataExtractor:
    """
    Simple metadata extractor for standalone use.
    Uses Libiry's MetadataExtractor if available.
    """

    def __init__(self, field_names: Dict[str, str]):
        self.field_names = field_names
        self.libiry_extractor = None

        if MetadataExtractor:
            try:
                self.libiry_extractor = MetadataExtractor(field_names)
            except Exception:
                pass

    def _apply_metadata_to_result(self, result: Dict[str, str], meta, filepath: Path) -> None:
        """Apply metadata to result dict. Handles both BookMetadata objects and dicts.

        This helper eliminates code duplication - the same conversion logic is used
        for both native extraction (BookMetadata) and consolidated sidecar data (dict).

        Args:
            result: Dict to update with metadata values
            meta: Either a BookMetadata object or a dict with metadata
            filepath: Path to the file (used for fallback booktitle)
        """
        if isinstance(meta, dict):
            # Dict from consolidate_metadata_to_sidecar()
            result['cover'] = meta.get('cover', '') or ''
            result['booktitle'] = meta.get('booktitle', '') or filepath.stem
            result['author'] = meta.get('author', '') or ''
            result['author_sort'] = meta.get('author_sort', '') or ''
            result['isbn'] = meta.get('isbn', '') or ''
            result['rating'] = str(meta.get('rating', '')) if meta.get('rating') else ''
            result['publisher'] = meta.get('publisher', '') or ''
            result['publication_date'] = meta.get('publication_date', '') or ''
            result['language'] = meta.get('language', '') or ''
            result['pages'] = meta.get('pages', '') or ''
            # Tags may be list or string
            tags = meta.get('tags', [])
            if isinstance(tags, list):
                result['tags'] = ', '.join(tags)
            else:
                result['tags'] = tags or ''
            result['series'] = meta.get('series', '') or ''
            result['series_index'] = str(meta.get('series_index', '')) if meta.get('series_index') else ''
            result['translator'] = meta.get('translator', '') or ''
            result['illustrator'] = meta.get('illustrator', '') or ''
            result['description'] = meta.get('description', '') or ''
            result['notes'] = meta.get('notes', '') or ''
        else:
            # BookMetadata object from Libiry's extractor
            result['cover'] = meta.cover_url or ''
            result['booktitle'] = meta.booktitle or filepath.stem
            result['author'] = ', '.join(meta.authors) if meta.authors else ''
            result['author_sort'] = meta.author_sort or ''
            result['isbn'] = meta.isbn or ''
            result['rating'] = str(meta.rating) if meta.rating else ''
            result['publisher'] = meta.publisher or ''
            result['publication_date'] = meta.publication_date or ''
            result['language'] = meta.language or ''
            result['pages'] = meta.pages or ''
            result['tags'] = ', '.join(meta.tags) if meta.tags else ''
            result['series'] = meta.series or ''
            result['series_index'] = str(meta.series_index) if meta.series_index else ''
            result['translator'] = meta.translator or ''
            result['illustrator'] = meta.illustrator or ''
            result['description'] = meta.description or ''
            result['notes'] = meta.notes or ''

    def extract(self, filepath: Path) -> Dict[str, str]:
        """
        Extract metadata from a file.
        Returns dict with all book metadata fields in Goodreads order.
        """
        # Order based on Goodreads CSV export
        # Get file stats for size and dates
        file_stat = filepath.stat() if filepath.exists() else None
        file_size = format_file_size(file_stat.st_size) if file_stat else ''
        # File dates in YYYY-MM-DD format for Obsidian dashboard
        file_created = datetime.fromtimestamp(file_stat.st_ctime).strftime('%Y-%m-%d') if file_stat else ''
        file_modified = datetime.fromtimestamp(file_stat.st_mtime).strftime('%Y-%m-%d') if file_stat else ''

        result = {
            'cover': '',                # UI: cover afbeelding
            'booktitle': filepath.stem, # Goodreads: Title
            'author': '',               # Goodreads: Author
            'author_sort': '',          # Author sort name
            'isbn': '',                 # Goodreads: ISBN
            'rating': '',               # Goodreads: My Rating
            'publisher': '',            # Goodreads: Publisher
            'publication_date': '',     # Full publication date
            'language': '',             # Language
            'pages': '',                # Page count
            'tags': '',                 # Goodreads: Bookshelves
            'series': '',               # Series name
            'series_index': '',         # Series index
            'translator': '',           # Translator
            'illustrator': '',          # Illustrator
            'description': '',          # Goodreads: My Review
            'notes': '',                # Goodreads: Private Notes
            'size': file_size,
            'type': filepath.suffix.lower().lstrip('.'),
            'path': str(filepath),
            'file_created': file_created,    # For Obsidian dashboard
            'file_modified': file_modified,  # For Obsidian dashboard
        }

        ext = filepath.suffix.lower()

        try:
            if self.libiry_extractor:
                # Check if an MD sidecar exists - use consolidate_metadata_to_sidecar
                # to merge sidecar metadata with native ebook metadata
                if ext in EBOOK_EXTENSIONS:
                    sidecar_used = False
                    if get_sidecar_path and read_sidecar_as_dict and consolidate_metadata_to_sidecar:
                        sidecar_path = get_sidecar_path(filepath)
                        if sidecar_path.exists():
                            # Read existing sidecar as dict and merge with native
                            sidecar_metadata = read_sidecar_as_dict(filepath)
                            if sidecar_metadata:
                                # Use shared consolidation function - merges sidecar with native
                                merged = consolidate_metadata_to_sidecar(
                                    filepath,
                                    source_metadata=sidecar_metadata,
                                    filter_redundant=True
                                )
                                self._apply_metadata_to_result(result, merged, filepath)
                                sidecar_used = True

                    # No sidecar or consolidation not available - use native extraction
                    if not sidecar_used:
                        meta = self.libiry_extractor.extract(filepath)
                        if meta:
                            self._apply_metadata_to_result(result, meta, filepath)
                        # Also check for cover file next to ebook
                        if find_cover_for_ebook:
                            cover_filename = find_cover_for_ebook(filepath)
                            if cover_filename:
                                result['cover'] = cover_filename

                elif ext in MARKDOWN_EXTENSIONS:
                    # Markdown files - use Libiry's extractor
                    meta = self.libiry_extractor.extract(filepath)
                    if meta:
                        self._apply_metadata_to_result(result, meta, filepath)
            else:
                # Fallback: basic extraction for EPUB
                if ext == '.epub':
                    result.update(self._extract_epub_basic(filepath))
                elif ext in MARKDOWN_EXTENSIONS:
                    result.update(self._extract_markdown_basic(filepath))
        except Exception as e:
            print(f"Warning: Could not extract metadata from {filepath.name}: {e}")

        return result

    def _extract_epub_basic(self, filepath: Path) -> Dict[str, str]:
        """Basic EPUB metadata extraction without external dependencies."""
        import zipfile
        import xml.etree.ElementTree as ET

        result = {}

        try:
            with zipfile.ZipFile(filepath, 'r') as zf:
                # Find OPF file
                opf_path = None
                for name in zf.namelist():
                    if name.endswith('.opf'):
                        opf_path = name
                        break

                if not opf_path:
                    # Try container.xml
                    try:
                        container = zf.read('META-INF/container.xml')
                        root = ET.fromstring(container)
                        ns = {'c': 'urn:oasis:names:tc:opendocument:xmlns:container'}
                        rootfile = root.find('.//c:rootfile', ns)
                        if rootfile is not None:
                            opf_path = rootfile.get('full-path')
                    except Exception:
                        pass

                if opf_path:
                    opf_content = zf.read(opf_path)
                    root = ET.fromstring(opf_content)

                    # Dublin Core namespace
                    dc_ns = {'dc': 'http://purl.org/dc/elements/1.1/',
                             'opf': 'http://www.idpf.org/2007/opf'}

                    # Title
                    title_elem = root.find('.//dc:title', dc_ns)
                    if title_elem is not None and title_elem.text:
                        result['booktitle'] = title_elem.text.strip()

                    # Author
                    creator_elem = root.find('.//dc:creator', dc_ns)
                    if creator_elem is not None and creator_elem.text:
                        result['author'] = creator_elem.text.strip()

                    # ISBN (identifier)
                    for identifier in root.findall('.//dc:identifier', dc_ns):
                        text = identifier.text or ''
                        scheme = identifier.get('{http://www.idpf.org/2007/opf}scheme', '').lower()
                        # Skip UUID values
                        if text.lower().startswith('urn:uuid:'):
                            continue
                        if 'isbn' in scheme or 'isbn' in text.lower():
                            isbn = text.strip()
                            # Remove any ISBN: prefix
                            for prefix in ['ISBN:', 'ISBN-10:', 'ISBN-13:']:
                                if isbn.upper().startswith(prefix):
                                    isbn = isbn[len(prefix):].strip()
                                    break
                            # Clean if exactly 10 or 13 digits
                            cleaned = ''.join(c for c in isbn.upper() if c.isdigit() or c == 'X')
                            if len(cleaned) in (10, 13):
                                isbn = cleaned
                            if isbn:
                                result['isbn'] = isbn
                                break

                    # Cover URL (not always available in EPUB)
                    # Look for cover meta tag
                    for meta in root.findall('.//opf:meta', dc_ns):
                        if meta.get('name') == 'cover':
                            cover_id = meta.get('content')
                            # Find item with this ID
                            for item in root.findall('.//opf:item', dc_ns):
                                if item.get('id') == cover_id:
                                    result['cover'] = item.get('href', '')
                                    break
        except Exception:
            pass

        return result

    def _extract_markdown_basic(self, filepath: Path) -> Dict[str, str]:
        """Basic markdown metadata extraction."""
        import re

        result = {}

        try:
            content = filepath.read_text(encoding='utf-8')

            # Check for YAML frontmatter
            yaml_match = re.match(r'^---\s*\n(.*?)\n---', content, re.DOTALL)
            search_content = yaml_match.group(1) if yaml_match else content

            # Extract fields using configured field names
            for field, field_name in self.field_names.items():
                pattern = rf'^{re.escape(field_name)}:\s*(.+?)$'
                match = re.search(pattern, search_content, re.MULTILINE | re.IGNORECASE)
                if match:
                    value = match.group(1).strip().strip('"\'[]!')
                    if field == 'author':
                        result['author'] = value
                    elif field == 'booktitle':
                        result['booktitle'] = value
                    elif field == 'cover':
                        result['cover'] = value
                    elif field == 'isbn':
                        result['isbn'] = value
        except Exception:
            pass

        return result


# =============================================================================
# Catalog Generation
# =============================================================================

def scan_folder(folder: Path, progress_callback=None) -> List[Dict[str, str]]:
    """
    Scan a folder recursively and collect metadata from all files.

    If multiple files have the same booktitle+author (e.g., an .epub and .md
    of the same book), they get (1), (2) etc. appended to the title.
    """
    field_names = load_field_names(SCRIPT_DIR)
    extractor = SimpleMetadataExtractor(field_names)

    books = []
    all_files = []

    # Load selected file types from Libiry settings
    valid_extensions = load_selected_types(SCRIPT_DIR)

    for root, dirs, files in os.walk(folder):
        # Skip hidden folders
        dirs[:] = [d for d in dirs if not d.startswith('.')]

        for filename in files:
            if filename.startswith('.'):
                continue
            filepath = Path(root) / filename
            # Only include files with selected extensions
            if filepath.suffix.lower() in valid_extensions:
                all_files.append(filepath)

    total = len(all_files)

    for i, filepath in enumerate(all_files):
        if progress_callback:
            progress_callback(i + 1, total, filepath.name)

        try:
            # Relative path for display
            rel_path = filepath.relative_to(folder)
            rel_path_posix = rel_path.as_posix()

            # Extract metadata
            metadata = extractor.extract(filepath)
            metadata['file'] = rel_path_posix

            books.append(metadata)
        except Exception as e:
            print(f"Error processing {filepath}: {e}")

    # Sort by booktitle
    books.sort(key=lambda b: b.get('booktitle', '').lower())

    # Detect duplicates based on booktitle+author and add (1), (2) etc.
    # This ensures both book.epub and book.md appear in the output
    title_author_count = {}
    for book in books:
        key = (book.get('booktitle', '').lower(), book.get('author', '').lower())
        title_author_count[key] = title_author_count.get(key, 0) + 1

    # Second pass: add numbers to duplicates
    title_author_seen = {}
    for book in books:
        key = (book.get('booktitle', '').lower(), book.get('author', '').lower())
        if title_author_count[key] > 1:
            # Multiple books with same title+author
            seen = title_author_seen.get(key, 0) + 1
            title_author_seen[key] = seen
            # Append (1), (2) etc. to booktitle
            book['booktitle'] = f"{book.get('booktitle', '')} ({seen})"

    return books


def sanitize_filename(name: str) -> str:
    """Remove invalid characters from filename."""
    return ''.join(c if c not in '<>:"/\\|?*' else '_' for c in name)[:200]


def clean_quotes(value: str) -> str:
    """
    Remove internal double quotes from a string.
    This prevents YAML parsing issues in Obsidian when fields
    are surrounded by quotes and there are also quotes in the value.
    """
    if not value:
        return value
    return value.replace('"', '')


def generate_markdown_files(books: List[Dict[str, str]],
                           output_folder: Path,
                           field_names: Dict[str, str]) -> List[Path]:
    """
    Generate markdown files from the book list.
    One file per book in Obsidian format (YAML frontmatter).

    Args:
        books: List of book metadata dicts
        output_folder: Output folder
        field_names: Field names configuration
    """
    output_folder.mkdir(parents=True, exist_ok=True)
    generated_files = []

    for book in books:
        # Filename: [author] - [booktitle].md
        author = book.get('author', 'Unknown') or 'Unknown'
        title = book.get('booktitle', 'Untitled') or 'Untitled'
        filename = sanitize_filename(f"{author} - {title}.md")
        filepath = output_folder / filename

        # Prevent duplicates by adding a number
        counter = 1
        while filepath.exists():
            filename = sanitize_filename(f"{author} - {title} ({counter}).md")
            filepath = output_folder / filename
            counter += 1

        # YAML frontmatter with Libiry field names
        lines = [
            '---',
            f'{field_names["cover"]}: "{clean_quotes(book.get("cover", ""))}"',
            f'{field_names["booktitle"]}: "{clean_quotes(title)}"',
            f'{field_names["author"]}: "{clean_quotes(author)}"',
            f'{field_names["author_sort"]}: "{clean_quotes(book.get("author_sort", ""))}"',
            f'{field_names["isbn"]}: "{clean_quotes(book.get("isbn", ""))}"',
            f'{field_names["rating"]}: "{clean_quotes(book.get("rating", ""))}"',
            f'{field_names["publisher"]}: "{clean_quotes(book.get("publisher", ""))}"',
            f'{field_names["publication_date"]}: "{clean_quotes(book.get("publication_date", ""))}"',
            f'{field_names["language"]}: "{clean_quotes(book.get("language", ""))}"',
            f'{field_names["pages"]}: "{clean_quotes(book.get("pages", ""))}"',
            f'{field_names["tags"]}: [{clean_quotes(book.get("tags", ""))}]',
            f'{field_names["series"]}: "{clean_quotes(book.get("series", ""))}"',
            f'{field_names["series_index"]}: "{clean_quotes(book.get("series_index", ""))}"',
            f'{field_names["translator"]}: "{clean_quotes(book.get("translator", ""))}"',
            f'{field_names["illustrator"]}: "{clean_quotes(book.get("illustrator", ""))}"',
            f'{field_names["description"]}: "{clean_quotes(book.get("description", ""))}"',
            f'{field_names["notes"]}: "{clean_quotes(book.get("notes", ""))}"',
            f'file: "{clean_quotes(book.get("file", ""))}"',
            f'size: "{clean_quotes(book.get("size", ""))}"',
            f'type: "{clean_quotes(book.get("type", ""))}"',
            f'{field_names["file_created"]}: {book.get("file_created", "")}',
            f'{field_names["file_modified"]}: {book.get("file_modified", "")}',
            f'generated: {datetime.now().isoformat()}',
            f'generator: Libiry2Go',
            '---',
            '',
            f'# {clean_quotes(title)}',
            '',
            ''
        ]

        filepath.write_text('\n'.join(lines), encoding='utf-8')
        generated_files.append(filepath)

    return generated_files


# =============================================================================
# GUI
# =============================================================================

class Libiry2GoApp:
    """GUI for Libiry2Go in Libiry style."""

    def __init__(self):
        # Load Libiry styling from customize.txt
        self._load_style()

        self.root = tk.Tk()
        self.root.title("Libiry2Go")
        self.root.geometry("550x380")
        self.root.resizable(True, True)
        self.root.configure(bg=self.BG_COLOR)

        # Libiry icon in Windows taskbar
        # iconbitmap must be called BEFORE mainloop, and path must be absolute
        icon_path = SCRIPT_DIR / 'resources' / 'icons' / 'Libiry.ico'
        try:
            if icon_path.exists():
                # default="" also sets the icon in the taskbar
                self.root.iconbitmap(default=str(icon_path))
        except tk.TclError:
            pass  # Icon not found or not supported

        # Configure ttk style for Libiry look
        self._configure_style()

        self.input_folder = tk.StringVar()
        self.output_folder = tk.StringVar()

        self._create_widgets()

    def _load_style(self):
        """Load styling from Libiry's customize.txt."""
        try:
            from core.libiry_style import load_libiry_style
            style = load_libiry_style(SCRIPT_DIR)
        except ImportError:
            # Fallback if module not found
            style = {
                'background_color': '#6F9D9F',
                'button_color': '#793F4E',
                'button_font_color': '#FFFFFF',
                'background_font_color': '#000000',
                'search_box_color': '#FFFFFF',
                'font_size': 12,
            }

        self.BG_COLOR = style.get('background_color', '#6F9D9F')
        self.BTN_COLOR = style.get('button_color', '#793F4E')
        self.BTN_FONT_COLOR = style.get('button_font_color', '#FFFFFF')
        self.BG_FONT_COLOR = style.get('background_font_color', '#000000')
        self.ENTRY_BG = style.get('search_box_color', '#FFFFFF')
        self.FONT_SIZE = style.get('font_size', 12)

    def _configure_style(self):
        """Configure ttk styling to use Libiry colors."""
        style = ttk.Style()

        # Frame background
        style.configure('TFrame', background=self.BG_COLOR)

        # Labels with background font color
        style.configure('TLabel', background=self.BG_COLOR, foreground=self.BG_FONT_COLOR,
                       font=('Helvetica', self.FONT_SIZE))
        style.configure('Title.TLabel', background=self.BG_COLOR, foreground=self.BG_FONT_COLOR,
                       font=('Helvetica', self.FONT_SIZE + 6, 'bold'))
        style.configure('Subtitle.TLabel', background=self.BG_COLOR, foreground=self.BG_FONT_COLOR,
                       font=('Helvetica', self.FONT_SIZE))
        # Hint text in same color as background font, but slightly lighter
        style.configure('Hint.TLabel', background=self.BG_COLOR, foreground=self.BG_FONT_COLOR,
                       font=('Helvetica', self.FONT_SIZE - 1))

        # Entry fields
        style.configure('TEntry', fieldbackground=self.ENTRY_BG,
                       font=('Helvetica', self.FONT_SIZE))

        # Spinbox
        style.configure('TSpinbox', fieldbackground=self.ENTRY_BG,
                       font=('Helvetica', self.FONT_SIZE))

    def _create_button(self, parent, text, command):
        """Create a button with Libiry styling (tk.Button for correct colors)."""
        btn = tk.Button(
            parent,
            text=text,
            command=command,
            bg=self.BTN_COLOR,
            fg=self.BTN_FONT_COLOR,
            activebackground=self.BTN_COLOR,
            activeforeground=self.BTN_FONT_COLOR,
            font=('Helvetica', self.FONT_SIZE),
            relief='flat',  # No border
            borderwidth=0,
            padx=15,
            pady=7,
            cursor='hand2'
        )
        return btn

    def _create_entry(self, parent, textvariable, width=40):
        """
        Create an entry field with Libiry styling.
        Same font and height as buttons for consistent look.
        """
        entry = tk.Entry(
            parent,
            textvariable=textvariable,
            width=width,
            font=('Helvetica', self.FONT_SIZE),  # Same font as buttons
            bg=self.ENTRY_BG,
            relief='flat',
            borderwidth=0,
            # Height equal to buttons: buttons have pady=5, entry uses ipady
            # for internal vertical padding to get the same height
        )
        # ipady via pack/grid for consistent height with buttons
        return entry

    def _create_entry_with_button(self, parent, textvariable, button_text, button_command, entry_width=40):
        """
        Create a combined field with entry and button directly adjacent.
        Entry and button have the same height and font for consistent look.

        The button determines the height (font + 2*pady). Entry must get the same height
        via ipady. Buttons have pady=7, so entry gets ipady=7.
        """
        # Frame without padding between entry and button
        frame = ttk.Frame(parent)

        # Entry with same font as button
        # ipady=7 gives same height as button with pady=7
        entry = tk.Entry(
            frame,
            textvariable=textvariable,
            width=entry_width,
            font=('Helvetica', self.FONT_SIZE),
            bg=self.ENTRY_BG,
            relief='flat',
            borderwidth=0,
        )
        entry.pack(side='left', ipady=7, fill='y')

        # Button directly adjacent
        # padx=15 so "Browse..." is fully visible
        # pady=7 for sufficient height
        btn = tk.Button(
            frame,
            text=button_text,
            command=button_command,
            bg=self.BTN_COLOR,
            fg=self.BTN_FONT_COLOR,
            activebackground=self.BTN_COLOR,
            activeforeground=self.BTN_FONT_COLOR,
            font=('Helvetica', self.FONT_SIZE),
            relief='flat',
            borderwidth=0,
            padx=15,
            pady=7,
            cursor='hand2'
        )
        btn.pack(side='left')

        return frame

    def _create_widgets(self):
        # Main frame with padding
        main = ttk.Frame(self.root, padding="20")
        main.grid(row=0, column=0, sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main.columnconfigure(1, weight=1)

        # Title
        title = ttk.Label(main, text="Libiry2Go", style='Title.TLabel')
        title.grid(row=0, column=0, columnspan=3, pady=(0, 5))

        subtitle = ttk.Label(main, text="Create a portable catalog of your book library",
                            style='Subtitle.TLabel')
        subtitle.grid(row=1, column=0, columnspan=3, pady=(0, 20))

        # Input folder - entry and button directly adjacent, same height and font
        # Consistent vertical spacing (pady=8) between all form rows
        ttk.Label(main, text="Library folder:").grid(row=2, column=0, sticky="w", pady=8)
        input_frame = self._create_entry_with_button(
            main, self.input_folder, "...", self._browse_input)
        input_frame.grid(row=2, column=1, columnspan=2, sticky="w", pady=8)

        # Output folder - entry and button directly adjacent, same height and font
        ttk.Label(main, text="Output folder:").grid(row=3, column=0, sticky="w", pady=8)
        output_frame = self._create_entry_with_button(
            main, self.output_folder, "...", self._browse_output)
        output_frame.grid(row=3, column=1, columnspan=2, sticky="w", pady=8)

        # Progress (text instead of bar, like Calibre2Libiry)
        self.progress_label = ttk.Label(main, text="")
        self.progress_label.grid(row=4, column=0, columnspan=3, pady=(20, 5))

        # Generate button
        self.generate_btn = self._create_button(main, "Generate Catalog", self._generate)
        self.generate_btn.grid(row=5, column=0, columnspan=3, pady=20)

        # Status
        self.status_label = ttk.Label(main, text="")
        self.status_label.grid(row=6, column=0, columnspan=3)

    def _browse_input(self):
        folder = filedialog.askdirectory(title="Select your book library folder")
        if folder:
            self.input_folder.set(folder)
            # Auto-fill output if empty (use forward slashes for consistency)
            if not self.output_folder.get():
                self.output_folder.set((Path(folder).parent / "Libiry2Go_Output").as_posix())

    def _browse_output(self):
        folder = filedialog.askdirectory(title="Select output folder")
        if folder:
            self.output_folder.set(folder)

    def _generate(self):
        input_path = self.input_folder.get()
        output_path = self.output_folder.get()

        if not input_path:
            messagebox.showerror("Error", "Please select a library folder")
            return

        if not Path(input_path).exists():
            messagebox.showerror("Error", "Library folder does not exist")
            return

        if not output_path:
            output_path = (Path(input_path).parent / "Libiry2Go_Output").as_posix()
            self.output_folder.set(output_path)

        # Disable button during generation
        self.generate_btn.config(state='disabled')

        # Run in thread to keep UI responsive
        thread = threading.Thread(target=self._generate_thread,
                                  args=(Path(input_path), Path(output_path)))
        thread.daemon = True
        thread.start()

    def _generate_thread(self, input_folder: Path, output_folder: Path):
        try:
            def progress_callback(current, total, filename):
                pct = (current / total) * 100
                self.root.after(0, lambda: self._update_progress(pct, f"Scanning: {filename[:40]}..."))

            # Scan
            self.root.after(0, lambda: self._update_progress(0, "Scanning library..."))
            books = scan_folder(input_folder, progress_callback)

            if not books:
                self.root.after(0, lambda: self._show_result("No files found in the selected folder."))
                return

            # Generate
            self.root.after(0, lambda: self._update_progress(100, "Generating markdown files..."))
            field_names = load_field_names(SCRIPT_DIR)
            files = generate_markdown_files(books, output_folder, field_names)

            # Done
            msg = f"Done! Generated {len(files)} file(s) with {len(books)} books.\n\nOutput: {output_folder}"
            self.root.after(0, lambda: self._show_result(msg, success=True))

        except Exception as e:
            self.root.after(0, lambda: self._show_result(f"Error: {e}"))

    def _update_progress(self, pct: float, text: str):
        # Show percentage and text together (without gray progress bar)
        self.progress_label.config(text=f"[{pct:.0f}%] {text}")

    def _show_result(self, message: str, success: bool = False):
        self.generate_btn.config(state='normal')
        self.progress_label.config(text="")

        if success:
            self.status_label.config(text="Catalog generated successfully!", foreground=self.BG_FONT_COLOR)
            messagebox.showinfo("Success", message)
        else:
            self.status_label.config(text=message, foreground=self.BG_FONT_COLOR)
            if "Error" in message:
                messagebox.showerror("Error", message)

    def run(self):
        self.root.mainloop()


# =============================================================================
# Main
# =============================================================================

def main():
    """
    Main entry point.

    Usage:
        python libiry2go.py                         # Opens GUI
        python libiry2go.py "C:/Books"              # CLI, output next to input
        python libiry2go.py "C:/Books" "C:/Out"     # CLI, custom output
    """
    if len(sys.argv) > 1:
        # CLI mode
        input_folder = Path(sys.argv[1])

        if not input_folder.exists():
            print(f"Error: Folder not found: {input_folder}")
            sys.exit(1)

        if len(sys.argv) > 2:
            output_folder = Path(sys.argv[2])
        else:
            output_folder = input_folder.parent / "Libiry2Go_Output"

        print(f"Libiry2Go - Portable Book Catalog Generator")
        print(f"=" * 50)
        print(f"Input:  {input_folder}")
        print(f"Output: {output_folder}")
        print()

        # Progress callback for CLI
        def progress(current, total, filename):
            pct = (current / total) * 100
            print(f"\r[{pct:5.1f}%] Scanning: {filename[:50]:<50}", end='', flush=True)

        print("Scanning library...")
        books = scan_folder(input_folder, progress)
        print()  # Newline after progress

        if not books:
            print("No files found.")
            sys.exit(0)

        print(f"Found {len(books)} files. Generating markdown...")
        field_names = load_field_names(SCRIPT_DIR)
        files = generate_markdown_files(books, output_folder, field_names)

        print(f"\nDone! Generated {len(files)} file(s):")
        for f in files[:10]:  # Show max 10 files
            print(f"  - {f.name}")
        if len(files) > 10:
            print(f"  ... and {len(files) - 10} more")
    else:
        # GUI mode
        app = Libiry2GoApp()
        app.run()


if __name__ == '__main__':
    main()
