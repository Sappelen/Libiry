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

# Windows taakbalk icoon fix: stel AppUserModelID in zodat Windows
# het juiste icoon toont in de taakbalk in plaats van het Python icoon
try:
    import ctypes
    # Unieke ID voor Libiry apps - Windows groepeert vensters met dezelfde ID
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('Libiry.Libiry2Go.1')
except (ImportError, AttributeError, OSError):
    pass  # Niet op Windows of ctypes niet beschikbaar

# Voeg Libiry's core folder toe aan path zodat we de extractors kunnen gebruiken
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

try:
    from core.metadata_extractor import MetadataExtractor, BookMetadata
except ImportError:
    # Standalone mode - basic metadata extraction
    MetadataExtractor = None
    BookMetadata = None


# =============================================================================
# Configuration
# =============================================================================


# Default bestandstypes (fallback als selected types.txt niet bestaat)
DEFAULT_EXTENSIONS = {'.epub', '.mobi', '.azw', '.azw3', '.pdf', '.cbr', '.cbz', '.md', '.markdown'}

# Extensies waarvoor metadata extractie mogelijk is
EBOOK_EXTENSIONS = {'.epub', '.mobi', '.azw', '.azw3', '.pdf', '.cbr', '.cbz'}
MARKDOWN_EXTENSIONS = {'.md', '.markdown'}

# Volgorde gebaseerd op Goodreads CSV export voor maximale compatibiliteit
DEFAULT_FIELD_NAMES = {
    'cover': 'cover',              # UI: cover afbeelding
    'booktitle': 'booktitle',      # Goodreads: Title
    'author': 'author',            # Goodreads: Author
    'author_sort': 'author_sort',  # Sorteer naam auteur (opf:file-as)
    'isbn': 'isbn',                # Goodreads: ISBN
    'rating': 'rating',            # Goodreads: My Rating
    'publisher': 'publisher',      # Goodreads: Publisher
    'publication_date': 'publication_date',  # Volledige publicatiedatum
    'language': 'language',        # Taal
    'pages': 'pages',              # Aantal pagina's
    'tags': 'tags',                # Goodreads: Bookshelves
    'series': 'series',            # Serie naam
    'series_index': 'series_index',# Serie volgnummer
    'translator': 'translator',    # Vertaler
    'illustrator': 'illustrator',  # Illustrator
    'description': 'description',  # Goodreads: My Review
    'notes': 'notes',              # Goodreads: Private Notes
    'file_created': 'file_created',    # Libiry2Go: bestand aanmaakdatum
    'file_modified': 'file_modified',  # Libiry2Go: bestand wijzigingsdatum
}


def load_field_names_from_libiry() -> Dict[str, str]:
    """
    Laad veldnamen uit Libiry's customize/customize.txt indien aanwezig.
    Dit zorgt ervoor dat de veldnamen consistent zijn met de gebruiker's Libiry setup.
    """
    field_names = DEFAULT_FIELD_NAMES.copy()

    # Check beide locaties: eerst customize folder, dan resources folder
    for folder in ['customize', 'resources']:
        customize_file = SCRIPT_DIR / folder / 'customize.txt'
        if not customize_file.exists():
            continue

        try:
            content = customize_file.read_text(encoding='utf-8')
            for line in content.split('\n'):
                line = line.strip()
                if line.startswith('Field name '):
                    # Format: "Field name cover: coverimage"
                    parts = line.split(':', 1)
                    if len(parts) == 2:
                        field_part = parts[0].replace('Field name ', '').strip()
                        value = parts[1].strip()
                        if field_part in field_names and value:
                            field_names[field_part] = value
        except Exception as e:
            print(f"Warning: Could not read {customize_file}: {e}")

    return field_names


def load_selected_types_from_libiry() -> set:
    """
    Laad geselecteerde bestandstypes uit Libiry's selected types.txt.
    Zoekt eerst in customize folder, dan in resources folder.
    """
    # Check beide locaties: eerst customize folder, dan resources folder
    for folder in ['customize', 'resources']:
        types_path = SCRIPT_DIR / folder / 'selected types.txt'
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

    return DEFAULT_EXTENSIONS


def format_file_size(size_bytes: int) -> str:
    """Formatteer bestandsgrootte naar leesbare string."""
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
    Eenvoudige metadata extractor voor standalone gebruik.
    Gebruikt Libiry's MetadataExtractor indien beschikbaar.
    """

    def __init__(self, field_names: Dict[str, str]):
        self.field_names = field_names
        self.libiry_extractor = None

        if MetadataExtractor:
            try:
                self.libiry_extractor = MetadataExtractor(field_names)
            except Exception:
                pass

    def extract(self, filepath: Path) -> Dict[str, str]:
        """
        Extract metadata uit een bestand.
        Returns dict met alle boek metadata velden in Goodreads volgorde.
        """
        # Volgorde gebaseerd op Goodreads CSV export
        # Haal file stats op voor size en dates
        file_stat = filepath.stat() if filepath.exists() else None
        file_size = format_file_size(file_stat.st_size) if file_stat else ''
        # File dates in YYYY-MM-DD formaat voor Obsidian dashboard
        file_created = datetime.fromtimestamp(file_stat.st_ctime).strftime('%Y-%m-%d') if file_stat else ''
        file_modified = datetime.fromtimestamp(file_stat.st_mtime).strftime('%Y-%m-%d') if file_stat else ''

        result = {
            'cover': '',                # UI: cover afbeelding
            'booktitle': filepath.stem, # Goodreads: Title
            'author': '',               # Goodreads: Author
            'author_sort': '',          # Sorteer naam auteur
            'isbn': '',                 # Goodreads: ISBN
            'rating': '',               # Goodreads: My Rating
            'publisher': '',            # Goodreads: Publisher
            'publication_date': '',     # Volledige publicatiedatum
            'language': '',             # Taal
            'pages': '',                # Aantal pagina's
            'tags': '',                 # Goodreads: Bookshelves
            'series': '',               # Serie naam
            'series_index': '',         # Serie volgnummer
            'translator': '',           # Vertaler
            'illustrator': '',          # Illustrator
            'description': '',          # Goodreads: My Review
            'notes': '',                # Goodreads: Private Notes
            'size': file_size,
            'type': filepath.suffix.lower().lstrip('.'),
            'path': str(filepath),
            'file_created': file_created,    # Voor Obsidian dashboard
            'file_modified': file_modified,  # Voor Obsidian dashboard
        }

        ext = filepath.suffix.lower()

        try:
            if self.libiry_extractor:
                # Gebruik Libiry's extractor voor rijkere metadata
                if ext in EBOOK_EXTENSIONS or ext in MARKDOWN_EXTENSIONS:
                    meta = self.libiry_extractor.extract(filepath)
                    if meta:
                        # Volgorde: Goodreads CSV export + extra velden
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
            else:
                # Fallback: basis extractie voor EPUB
                if ext == '.epub':
                    result.update(self._extract_epub_basic(filepath))
                elif ext in MARKDOWN_EXTENSIONS:
                    result.update(self._extract_markdown_basic(filepath))
        except Exception as e:
            print(f"Warning: Could not extract metadata from {filepath.name}: {e}")

        return result

    def _extract_epub_basic(self, filepath: Path) -> Dict[str, str]:
        """Basis EPUB metadata extractie zonder externe dependencies."""
        import zipfile
        import xml.etree.ElementTree as ET

        result = {}

        try:
            with zipfile.ZipFile(filepath, 'r') as zf:
                # Zoek OPF bestand
                opf_path = None
                for name in zf.namelist():
                    if name.endswith('.opf'):
                        opf_path = name
                        break

                if not opf_path:
                    # Probeer container.xml
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
                        # Skip UUID waarden
                        if text.lower().startswith('urn:uuid:'):
                            continue
                        if 'isbn' in scheme or 'isbn' in text.lower():
                            isbn = text.strip()
                            # Verwijder eventuele ISBN: prefix
                            for prefix in ['ISBN:', 'ISBN-10:', 'ISBN-13:']:
                                if isbn.upper().startswith(prefix):
                                    isbn = isbn[len(prefix):].strip()
                                    break
                            # Clean als exact 10 of 13 cijfers
                            cleaned = ''.join(c for c in isbn.upper() if c.isdigit() or c == 'X')
                            if len(cleaned) in (10, 13):
                                isbn = cleaned
                            if isbn:
                                result['isbn'] = isbn
                                break

                    # Cover URL (niet altijd beschikbaar in EPUB)
                    # Zoek naar cover meta tag
                    for meta in root.findall('.//opf:meta', dc_ns):
                        if meta.get('name') == 'cover':
                            cover_id = meta.get('content')
                            # Zoek item met dit ID
                            for item in root.findall('.//opf:item', dc_ns):
                                if item.get('id') == cover_id:
                                    result['cover'] = item.get('href', '')
                                    break
        except Exception:
            pass

        return result

    def _extract_markdown_basic(self, filepath: Path) -> Dict[str, str]:
        """Basis markdown metadata extractie."""
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
    Scan een folder recursief en verzamel metadata van alle bestanden.

    Als er meerdere bestanden zijn met dezelfde booktitle+author (bijv. een .epub
    en .md van hetzelfde boek), krijgen ze (1), (2) etc. toegevoegd aan de titel.
    """
    field_names = load_field_names_from_libiry()
    extractor = SimpleMetadataExtractor(field_names)

    books = []
    all_files = []

    # Laad geselecteerde bestandstypes uit Libiry settings
    valid_extensions = load_selected_types_from_libiry()

    for root, dirs, files in os.walk(folder):
        # Skip hidden folders
        dirs[:] = [d for d in dirs if not d.startswith('.')]

        for filename in files:
            if filename.startswith('.'):
                continue
            filepath = Path(root) / filename
            # Alleen bestanden met geselecteerde extensies meenemen
            if filepath.suffix.lower() in valid_extensions:
                all_files.append(filepath)

    total = len(all_files)

    for i, filepath in enumerate(all_files):
        if progress_callback:
            progress_callback(i + 1, total, filepath.name)

        try:
            # Relatief pad voor weergave
            rel_path = filepath.relative_to(folder)
            rel_path_posix = rel_path.as_posix()

            # Extractie metadata
            metadata = extractor.extract(filepath)
            metadata['file'] = rel_path_posix

            books.append(metadata)
        except Exception as e:
            print(f"Error processing {filepath}: {e}")

    # Sorteer op booktitle
    books.sort(key=lambda b: b.get('booktitle', '').lower())

    # Detecteer duplicaten op basis van booktitle+author en voeg (1), (2) toe
    # Dit zorgt ervoor dat bijv. book.epub en book.md beide in de output komen
    title_author_count = {}
    for book in books:
        key = (book.get('booktitle', '').lower(), book.get('author', '').lower())
        title_author_count[key] = title_author_count.get(key, 0) + 1

    # Tweede pass: voeg nummers toe aan duplicaten
    title_author_seen = {}
    for book in books:
        key = (book.get('booktitle', '').lower(), book.get('author', '').lower())
        if title_author_count[key] > 1:
            # Er zijn meerdere boeken met deze titel+author
            seen = title_author_seen.get(key, 0) + 1
            title_author_seen[key] = seen
            # Voeg (1), (2) etc. toe aan de booktitle
            book['booktitle'] = f"{book.get('booktitle', '')} ({seen})"

    return books


def sanitize_filename(name: str) -> str:
    """Verwijder ongeldige karakters uit bestandsnaam."""
    return ''.join(c if c not in '<>:"/\\|?*' else '_' for c in name)[:200]


def clean_quotes(value: str) -> str:
    """
    Verwijder interne dubbele quotes uit een string.
    Dit voorkomt YAML parsing problemen in Obsidian wanneer velden
    worden omgeven door quotes en er ook quotes in de waarde staan.
    """
    if not value:
        return value
    return value.replace('"', '')


def generate_markdown_files(books: List[Dict[str, str]],
                           output_folder: Path,
                           field_names: Dict[str, str]) -> List[Path]:
    """
    Genereer markdown bestanden van de boekenlijst.
    Één bestand per boek in Obsidian format (YAML frontmatter).

    Args:
        books: Lijst met book metadata dicts
        output_folder: Output folder
        field_names: Veldnamen configuratie
    """
    output_folder.mkdir(parents=True, exist_ok=True)
    generated_files = []

    for book in books:
        # Filename: [author] - [booktitle].md
        author = book.get('author', 'Unknown') or 'Unknown'
        title = book.get('booktitle', 'Untitled') or 'Untitled'
        filename = sanitize_filename(f"{author} - {title}.md")
        filepath = output_folder / filename

        # Voorkom duplicaten door nummer toe te voegen
        counter = 1
        while filepath.exists():
            filename = sanitize_filename(f"{author} - {title} ({counter}).md")
            filepath = output_folder / filename
            counter += 1

        # YAML frontmatter met Libiry veldnamen
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
    """GUI voor Libiry2Go in Libiry stijl."""

    def __init__(self):
        # Laad Libiry styling uit customize.txt
        self._load_style()

        self.root = tk.Tk()
        self.root.title("Libiry2Go")
        self.root.geometry("550x380")
        self.root.resizable(True, True)
        self.root.configure(bg=self.BG_COLOR)

        # Libiry icoon in Windows taakbalk
        # iconbitmap moet VOOR mainloop aangeroepen worden, en pad moet absoluut zijn
        icon_path = SCRIPT_DIR / 'resources' / 'icons' / 'Libiry.ico'
        try:
            if icon_path.exists():
                # default="" zet ook het icoon in de taakbalk
                self.root.iconbitmap(default=str(icon_path))
        except tk.TclError:
            pass  # Icoon niet gevonden of niet ondersteund

        # Configureer ttk style voor Libiry look
        self._configure_style()

        self.input_folder = tk.StringVar()
        self.output_folder = tk.StringVar()

        self._create_widgets()

    def _load_style(self):
        """Laad styling uit Libiry's customize.txt."""
        try:
            from core.libiry_style import load_libiry_style
            style = load_libiry_style(SCRIPT_DIR)
        except ImportError:
            # Fallback als module niet gevonden
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
        """Configureer ttk styling om Libiry kleuren te gebruiken."""
        style = ttk.Style()

        # Frame achtergrond
        style.configure('TFrame', background=self.BG_COLOR)

        # Labels met achtergrond font kleur
        style.configure('TLabel', background=self.BG_COLOR, foreground=self.BG_FONT_COLOR,
                       font=('Helvetica', self.FONT_SIZE))
        style.configure('Title.TLabel', background=self.BG_COLOR, foreground=self.BG_FONT_COLOR,
                       font=('Helvetica', self.FONT_SIZE + 6, 'bold'))
        style.configure('Subtitle.TLabel', background=self.BG_COLOR, foreground=self.BG_FONT_COLOR,
                       font=('Helvetica', self.FONT_SIZE))
        # Hint tekst in zelfde kleur als achtergrond font, maar iets lichter
        style.configure('Hint.TLabel', background=self.BG_COLOR, foreground=self.BG_FONT_COLOR,
                       font=('Helvetica', self.FONT_SIZE - 1))

        # Entry velden
        style.configure('TEntry', fieldbackground=self.ENTRY_BG,
                       font=('Helvetica', self.FONT_SIZE))

        # Spinbox
        style.configure('TSpinbox', fieldbackground=self.ENTRY_BG,
                       font=('Helvetica', self.FONT_SIZE))

    def _create_button(self, parent, text, command):
        """Maak een button met Libiry styling (tk.Button voor correcte kleuren)."""
        btn = tk.Button(
            parent,
            text=text,
            command=command,
            bg=self.BTN_COLOR,
            fg=self.BTN_FONT_COLOR,
            activebackground=self.BTN_COLOR,
            activeforeground=self.BTN_FONT_COLOR,
            font=('Helvetica', self.FONT_SIZE),
            relief='flat',  # Geen border
            borderwidth=0,
            padx=15,
            pady=7,
            cursor='hand2'
        )
        return btn

    def _create_entry(self, parent, textvariable, width=40):
        """
        Maak een entry veld met Libiry styling.
        Zelfde font en hoogte als buttons voor consistente look.
        """
        entry = tk.Entry(
            parent,
            textvariable=textvariable,
            width=width,
            font=('Helvetica', self.FONT_SIZE),  # Zelfde font als buttons
            bg=self.ENTRY_BG,
            relief='flat',
            borderwidth=0,
            # Hoogte gelijk aan buttons: buttons hebben pady=5, entry gebruikt ipady
            # voor interne verticale padding om dezelfde hoogte te krijgen
        )
        # ipady via pack/grid voor consistente hoogte met buttons
        return entry

    def _create_entry_with_button(self, parent, textvariable, button_text, button_command, entry_width=40):
        """
        Maak een gecombineerd veld met entry en button direct tegen elkaar aan.
        Entry en button hebben dezelfde hoogte en font voor consistente look.

        De button bepaalt de hoogte (font + 2*pady). Entry moet dezelfde hoogte krijgen
        via ipady. Buttons hebben pady=7, dus entry krijgt ipady=7.
        """
        # Frame zonder padding tussen entry en button
        frame = ttk.Frame(parent)

        # Entry met zelfde font als button
        # ipady=7 zorgt voor zelfde hoogte als button met pady=7
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

        # Button direct aansluitend
        # padx=15 zodat "Browse..." volledig zichtbaar is
        # pady=7 voor voldoende hoogte
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

        # Input folder - entry en button direct tegen elkaar aan, zelfde hoogte en font
        # Consistente verticale spacing (pady=8) tussen alle form rows
        ttk.Label(main, text="Library folder:").grid(row=2, column=0, sticky="w", pady=8)
        input_frame = self._create_entry_with_button(
            main, self.input_folder, "...", self._browse_input)
        input_frame.grid(row=2, column=1, columnspan=2, sticky="w", pady=8)

        # Output folder - entry en button direct tegen elkaar aan, zelfde hoogte en font
        ttk.Label(main, text="Output folder:").grid(row=3, column=0, sticky="w", pady=8)
        output_frame = self._create_entry_with_button(
            main, self.output_folder, "...", self._browse_output)
        output_frame.grid(row=3, column=1, columnspan=2, sticky="w", pady=8)

        # Progress (tekst ipv balk, zoals Calibre2Libiry)
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
            # Auto-fill output if empty
            if not self.output_folder.get():
                self.output_folder.set(str(Path(folder).parent / "Libiry2Go_Output"))

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
            output_path = str(Path(input_path).parent / "Libiry2Go_Output")
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
            field_names = load_field_names_from_libiry()
            files = generate_markdown_files(books, output_folder, field_names)

            # Done
            msg = f"Done! Generated {len(files)} file(s) with {len(books)} books.\n\nOutput: {output_folder}"
            self.root.after(0, lambda: self._show_result(msg, success=True))

        except Exception as e:
            self.root.after(0, lambda: self._show_result(f"Error: {e}"))

    def _update_progress(self, pct: float, text: str):
        # Toon percentage en tekst samen (zonder grijze progress bar)
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

        # Progress callback voor CLI
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
        field_names = load_field_names_from_libiry()
        files = generate_markdown_files(books, output_folder, field_names)

        print(f"\nDone! Generated {len(files)} file(s):")
        for f in files[:10]:  # Toon max 10 files
            print(f"  - {f.name}")
        if len(files) > 10:
            print(f"  ... and {len(files) - 10} more")
    else:
        # GUI mode
        app = Libiry2GoApp()
        app.run()


if __name__ == '__main__':
    main()
