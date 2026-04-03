"""
Calibre2Libiry - Converteer Calibre metadata.opf naar Libiry Markdown sidecar formaat.

Calibre slaat metadata op in metadata.opf bestanden per boek-folder.
Libiry verwacht metadata in {boekbestand}.md formaat (bijv. book.pdf.md).

Calibre slaat covers op als cover.jpg/cover.png in de boek-folder.
Libiry verwacht covers in {boekbestand}.jpg formaat (bijv. book.pdf.jpg).

Dit script:
1. Leest Calibre's metadata.opf XML bestanden
2. Converteert de metadata naar Libiry's Markdown sidecar formaat (YAML frontmatter)
3. Schrijft het resultaat als book.ext.md
4. Hernoemt cover bestanden naar book.ext.jpg/.png

Gebruik:
    python Calibre2Libiry.py                    # Opens GUI
    python Calibre2Libiry.py [calibre_path]     # CLI mode

Let op:
    - Dit script HERNOEMT cover bestanden (geen kopie)
    - metadata.opf wordt NIET verwijderd (voor backup doeleinden)
    - Maak eerst een backup van je Calibre library als je onzeker bent
"""

import os
import sys
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import threading

# Windows taakbalk icoon fix: stel AppUserModelID in zodat Windows
# het juiste icoon toont in de taakbalk in plaats van het Python icoon
try:
    import ctypes
    # Unieke ID voor Libiry apps - Windows groepeert vensters met dezelfde ID
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('Libiry.Calibre2Libiry.1')
except (ImportError, AttributeError, OSError):
    pass  # Niet op Windows of ctypes niet beschikbaar


# Script directory voor imports
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))


# Ondersteunde ebook extensies (zelfde als Libiry)
EBOOK_EXTENSIONS = {
    '.epub', '.mobi', '.azw', '.azw3', '.pdf',
    '.cbz', '.cbr', '.djvu', '.fb2', '.lit',
    '.pdb', '.rtf', '.txt'
}

# Calibre cover bestandsnamen (zonder extensie)
CALIBRE_COVER_NAMES = {'cover'}

# Ondersteunde cover image extensies
COVER_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}


# =============================================================================
# Core Functions
# =============================================================================

def find_ebook_in_folder(folder: Path) -> Path | None:
    """Vind het ebook bestand in een Calibre boek-folder (returns eerste ebook)."""
    for file in folder.iterdir():
        if file.is_file() and file.suffix.lower() in EBOOK_EXTENSIONS:
            return file
    return None


def count_ebooks_in_folder(folder: Path) -> int:
    """Tel het aantal ebook bestanden in een folder."""
    count = 0
    for file in folder.iterdir():
        if file.is_file() and file.suffix.lower() in EBOOK_EXTENSIONS:
            count += 1
    return count


def find_cover_in_folder(folder: Path) -> Path | None:
    """Vind het cover bestand in een Calibre boek-folder."""
    for file in folder.iterdir():
        if file.is_file():
            name_lower = file.stem.lower()
            ext_lower = file.suffix.lower()
            if name_lower in CALIBRE_COVER_NAMES and ext_lower in COVER_EXTENSIONS:
                return file
    return None


def count_opf_files(library_path: Path) -> int:
    """Tel het aantal metadata.opf bestanden."""
    return len(list(library_path.rglob('metadata.opf')))


def find_standalone_cover_folders(library_path: Path) -> list[Path]:
    """
    Vind folders met precies 1 ebook en 1 cover, maar zonder metadata.opf.
    Deze covers kunnen ook hernoemd worden naar sidecar formaat.
    """
    standalone_folders = []
    processed_folders = set()

    # Verzamel alle folders met metadata.opf (die worden apart verwerkt)
    for opf_path in library_path.rglob('metadata.opf'):
        processed_folders.add(opf_path.parent)

    # Zoek door alle subfolders naar standalone covers
    for folder in library_path.rglob('*'):
        if not folder.is_dir():
            continue
        if folder in processed_folders:
            continue

        # Check: precies 1 ebook en 1 cover in deze folder
        if count_ebooks_in_folder(folder) == 1 and find_cover_in_folder(folder):
            standalone_folders.append(folder)

    return standalone_folders


def cover_needs_renaming(folder: Path, ebook: Path = None) -> bool:
    """Check of een cover in de folder hernoemd moet worden.

    Returns False als:
    - Er geen cover is
    - De cover al de juiste sidecar naam heeft (ebook.ext.jpg)
    """
    cover = find_cover_in_folder(folder)
    if not cover:
        return False

    if ebook is None:
        ebook = find_ebook_in_folder(folder)
    if ebook is None:
        return False

    # Check of cover al de juiste naam heeft
    expected_name = ebook.name + cover.suffix.lower()
    if cover.name.lower() == expected_name.lower():
        return False  # Al correct

    # Check of target al bestaat
    target_path = folder / expected_name
    if target_path.exists():
        return False  # Target bestaat al

    return True


def count_files_to_convert(library_path: Path) -> tuple[int, int]:
    """Tel het aantal OPF en cover bestanden om te converteren.

    Telt alleen covers die daadwerkelijk hernoemd moeten worden,
    niet covers die al de juiste naamgeving hebben.
    """
    from core.metadata_extractor import get_sidecar_path

    opf_count = 0
    cover_count = 0

    # Folders met metadata.opf (Calibre style)
    for opf_path in library_path.rglob('metadata.opf'):
        folder = opf_path.parent
        ebook = find_ebook_in_folder(folder)

        # Tel OPF alleen als er nog geen sidecar is
        if ebook:
            sidecar_path = get_sidecar_path(ebook)
            if not sidecar_path.exists():
                opf_count += 1

            # Tel cover alleen als het hernoemd moet worden
            if cover_needs_renaming(folder, ebook):
                cover_count += 1
        else:
            # Geen ebook, skip
            pass

    # Standalone covers (1 ebook + 1 cover, geen opf)
    standalone_folders = find_standalone_cover_folders(library_path)
    for folder in standalone_folders:
        ebook = find_ebook_in_folder(folder)
        if cover_needs_renaming(folder, ebook):
            cover_count += 1

    return opf_count, cover_count


def read_calibre_opf(opf_path: Path) -> dict:
    """Lees metadata uit een Calibre metadata.opf bestand.

    Gebruikt centrale helpers uit metadata_extractor om dubbele code te voorkomen.

    Returns:
        Dict met metadata velden
    """
    import xml.etree.ElementTree as ET
    import re

    # Importeer centrale helpers - geen dubbele code!
    from core.metadata_extractor import (
        find_dc_text, find_opf_metadata_element, DC_NS, OPF_NS
    )
    from core.libiry_style import convert_calibre_rating

    metadata = {}

    try:
        tree = ET.parse(opf_path)
        root = tree.getroot()

        # Gebruik centrale helper voor metadata element
        metadata_elem = find_opf_metadata_element(root, OPF_NS)

        # Basis velden - gebruik centrale find_dc_text helper
        title = find_dc_text(metadata_elem, 'title', DC_NS)
        if title:
            metadata['booktitle'] = title

        # Authors (kan meerdere dc:creator zijn)
        authors = []
        for creator in metadata_elem.findall(f'{{{DC_NS}}}creator'):
            if creator.text:
                authors.append(creator.text.strip())
                # Author sort uit opf:file-as attribuut
                file_as = creator.get(f'{{{OPF_NS}}}file-as') or creator.get('opf:file-as')
                if file_as and 'author_sort' not in metadata:
                    metadata['author_sort'] = file_as.strip()
        if not authors:
            for creator in metadata_elem.findall('creator'):
                if creator.text:
                    authors.append(creator.text.strip())
        if authors:
            metadata['author'] = ', '.join(authors)

        # ISBN - first look for <dc:identifier opf:scheme="ISBN">, then fallback to first identifier
        isbn_found = False
        first_identifier = None

        # Search all dc:identifier elements
        for identifier_elem in metadata_elem.findall(f'{{{DC_NS}}}identifier'):
            if not identifier_elem.text:
                continue
            ident_text = identifier_elem.text.strip()

            # Skip UUID values
            if ident_text.lower().startswith('urn:uuid:'):
                continue

            # Check for opf:scheme="ISBN" attribute (preferred)
            scheme = identifier_elem.get(f'{{{OPF_NS}}}scheme') or identifier_elem.get('opf:scheme') or ''
            if scheme.upper() == 'ISBN':
                # Clean ISBN value
                isbn_match = re.search(r'(\d{10}|\d{13})', ident_text)
                if isbn_match:
                    metadata['isbn'] = isbn_match.group(1)
                else:
                    metadata['isbn'] = ident_text
                isbn_found = True
                break

            # Store first non-UUID identifier as fallback
            if first_identifier is None:
                first_identifier = ident_text

        # Fallback: use first identifier if no ISBN scheme found
        if not isbn_found and first_identifier:
            isbn_match = re.search(r'(\d{10}|\d{13})', first_identifier)
            if isbn_match:
                metadata['isbn'] = isbn_match.group(1)
            else:
                # Only use if it looks like an ISBN (not random calibre ID)
                if len(first_identifier) >= 10 or first_identifier.isdigit():
                    metadata['isbn'] = first_identifier

        metadata['publisher'] = find_dc_text(metadata_elem, 'publisher', DC_NS) or ''
        metadata['language'] = find_dc_text(metadata_elem, 'language', DC_NS) or ''
        metadata['description'] = find_dc_text(metadata_elem, 'description', DC_NS) or ''

        # Tags uit dc:subject
        tags = []
        for subject in metadata_elem.findall(f'{{{DC_NS}}}subject'):
            if subject.text:
                tags.append(subject.text.strip())
        if not tags:
            for subject in metadata_elem.findall('subject'):
                if subject.text:
                    tags.append(subject.text.strip())
        if tags:
            metadata['tags'] = tags

        # Meta elementen (series, rating, etc.)
        meta_elements = list(metadata_elem.findall(f'{{{OPF_NS}}}meta'))
        meta_elements.extend(metadata_elem.findall('meta'))

        for m in meta_elements:
            name = m.get('name', '')
            content = m.get('content', '')

            if name == 'calibre:series' and content:
                metadata['series'] = content
            elif name == 'calibre:series_index' and content:
                try:
                    metadata['series_index'] = float(content)
                except (ValueError, TypeError):
                    pass
            elif name == 'calibre:rating' and content:
                # Gebruik centrale rating conversie (met kwart-sterren)
                rating = convert_calibre_rating(content)
                if rating is not None:
                    metadata['rating'] = rating
            elif name == 'calibre:user_notes' and content:
                metadata['notes'] = content
            elif name == 'calibre:year' and content:
                metadata['year'] = content
            elif name in ('rendition:page-count', 'calibre:pages') and content:
                metadata['pages'] = content
            elif name == 'calibre:author_sort' and content:
                if 'author_sort' not in metadata:
                    metadata['author_sort'] = content

        # Year uit dc:date als nog niet gevonden
        if 'year' not in metadata:
            date_text = find_dc_text('date')
            if date_text:
                year_match = re.match(r'^(\d{4})', date_text)
                if year_match:
                    metadata['year'] = year_match.group(1)
                # Volledige datum opslaan
                metadata['publication_date'] = date_text

        # Translator en Illustrator uit dc:contributor
        for contributor in metadata_elem.findall(f'{{{DC_NS}}}contributor'):
            if contributor.text:
                name_text = contributor.text.strip()
                role = contributor.get(f'{{{OPF_NS}}}role') or contributor.get('opf:role') or ''
                role = role.lower()
                if role == 'trl' and 'translator' not in metadata:
                    metadata['translator'] = name_text
                elif role == 'ill' and 'illustrator' not in metadata:
                    metadata['illustrator'] = name_text

    except Exception as e:
        print(f"Error reading Calibre OPF {opf_path}: {e}")

    return metadata


def convert_calibre_library(library_path: Path, dry_run: bool = False,
                            progress_callback=None) -> dict:
    """Convert all metadata.opf and cover files in a Calibre library.

    OPF files are NOT renamed but converted to Markdown sidecar.
    Cover files are renamed to sidecar format.

    Uses consolidate_metadata_to_sidecar() to merge OPF metadata with native
    ebook metadata, filtering out redundant values.

    Returns:
        Dict with results:
        - md_success, md_skip: sidecar counts
        - cover_success, cover_skip: cover counts
        - errors: list of error messages
        - created_sidecars: list of created sidecar paths
        - renamed_covers: list of (old_path, new_path) tuples
    """
    from core.metadata_extractor import (
        get_sidecar_path, write_sidecar_metadata, consolidate_metadata_to_sidecar
    )

    results = {
        'md_success': 0,
        'md_skip': 0,
        'cover_success': 0,
        'cover_skip': 0,
        'errors': [],
        'created_sidecars': [],
        'renamed_covers': [],
    }

    # Verzamel alle te verwerken items
    opf_files = list(library_path.rglob('metadata.opf'))
    standalone_folders = find_standalone_cover_folders(library_path)
    total = len(opf_files) + len(standalone_folders)

    if total == 0:
        return results

    # === FASE 1: Folders met metadata.opf (Calibre style) ===
    for i, opf_path in enumerate(opf_files):
        if progress_callback:
            progress_callback(i + 1, total, opf_path.parent.name)

        folder = opf_path.parent
        ebook = find_ebook_in_folder(folder)

        if ebook is None:
            # No ebook in folder - skip without error message
            results['md_skip'] += 1
            continue

        # === STEP 1: Rename cover FIRST ===
        # Must happen before sidecar creation so consolidate_metadata_to_sidecar
        # can find the correctly named cover file (e.g., book.pdf.jpg)
        cover = find_cover_in_folder(folder)
        if cover:
            new_cover_name = ebook.name + cover.suffix.lower()
            new_cover_path = folder / new_cover_name

            # Check if cover already correct or target exists
            if cover.name.lower() == new_cover_name.lower():
                # Already correct - don't count as skip
                pass
            elif new_cover_path.exists():
                results['cover_skip'] += 1
            elif not dry_run:
                try:
                    old_path = cover
                    cover.rename(new_cover_path)
                    results['cover_success'] += 1
                    results['renamed_covers'].append((old_path, new_cover_path))
                except Exception as e:
                    results['errors'].append(f"Cover error: {e}")
            else:
                results['cover_success'] += 1
                results['renamed_covers'].append((cover, new_cover_path))

        # === STEP 2: Convert OPF to Markdown sidecar ===
        # Now consolidate_metadata_to_sidecar will find the renamed cover
        sidecar_path = get_sidecar_path(ebook)

        if sidecar_path.exists():
            results['md_skip'] += 1
        elif not dry_run:
            try:
                # Read metadata from Calibre OPF
                opf_metadata = read_calibre_opf(opf_path)

                if opf_metadata:
                    # Use shared function to merge OPF with native ebook metadata
                    # Native overrides OPF, redundant values are filtered out
                    # Also detects cover file and sets cover field
                    final_metadata = consolidate_metadata_to_sidecar(
                        ebook, source_metadata=opf_metadata, filter_redundant=True
                    )

                    # Write to Markdown sidecar
                    write_sidecar_metadata(sidecar_path, final_metadata)
                    results['md_success'] += 1
                    results['created_sidecars'].append(sidecar_path)
                else:
                    results['md_skip'] += 1
            except Exception as e:
                results['errors'].append(f"Sidecar error {opf_path.name}: {e}")
        else:
            # Dry run - count as success
            opf_metadata = read_calibre_opf(opf_path)
            if opf_metadata:
                results['md_success'] += 1
                results['created_sidecars'].append(sidecar_path)
            else:
                results['md_skip'] += 1

    # === FASE 2: Standalone covers (1 ebook + 1 cover, geen opf) ===
    for i, folder in enumerate(standalone_folders):
        if progress_callback:
            progress_callback(len(opf_files) + i + 1, total, folder.name)

        ebook = find_ebook_in_folder(folder)
        cover = find_cover_in_folder(folder)

        if ebook and cover:
            new_cover_name = ebook.name + cover.suffix.lower()
            new_cover_path = folder / new_cover_name

            # Check of cover al correct is of target bestaat
            if cover.name.lower() == new_cover_name.lower():
                # Al correct - niet tellen
                pass
            elif new_cover_path.exists():
                results['cover_skip'] += 1
            elif not dry_run:
                try:
                    old_path = cover
                    cover.rename(new_cover_path)
                    results['cover_success'] += 1
                    results['renamed_covers'].append((old_path, new_cover_path))
                except Exception as e:
                    results['errors'].append(f"Cover error: {e}")
            else:
                results['cover_success'] += 1
                results['renamed_covers'].append((cover, new_cover_path))

    return results


def generate_conversion_report(library_path: Path, results: dict, dry_run: bool = False) -> str:
    """Genereer een tekstrapport van de conversie.

    Args:
        library_path: De geconverteerde library folder
        results: Dict met resultaten van convert_calibre_library()
        dry_run: Of dit een preview was

    Returns:
        Rapport als string
    """
    from datetime import datetime

    lines = []
    lines.append("=" * 70)
    lines.append("CALIBRE2LIBIRY CONVERSION REPORT")
    lines.append(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"Library: {library_path}")
    if dry_run:
        lines.append("Mode: PREVIEW (no changes made)")
    lines.append("=" * 70)
    lines.append("")

    # Summary
    lines.append("-" * 70)
    lines.append("SUMMARY")
    lines.append("-" * 70)
    lines.append(f"Sidecars created: {results['md_success']}")
    lines.append(f"Sidecars skipped (already exist): {results['md_skip']}")
    lines.append(f"Covers renamed: {results['cover_success']}")
    lines.append(f"Covers skipped (already exist): {results['cover_skip']}")
    if results['errors']:
        lines.append(f"Errors: {len(results['errors'])}")
    lines.append("")

    # Created sidecars
    if results['created_sidecars']:
        lines.append("-" * 70)
        lines.append("CREATED SIDECARS")
        lines.append("-" * 70)
        for path in results['created_sidecars']:
            try:
                rel_path = path.relative_to(library_path)
            except ValueError:
                rel_path = path
            lines.append(f"  {rel_path}")
        lines.append("")

    # Renamed covers
    if results['renamed_covers']:
        lines.append("-" * 70)
        lines.append("RENAMED COVERS")
        lines.append("-" * 70)
        for old_path, new_path in results['renamed_covers']:
            try:
                old_rel = old_path.relative_to(library_path)
                new_name = new_path.name
            except ValueError:
                old_rel = old_path
                new_name = new_path.name
            lines.append(f"  {old_rel} -> {new_name}")
        lines.append("")

    # Errors
    if results['errors']:
        lines.append("-" * 70)
        lines.append("ERRORS")
        lines.append("-" * 70)
        for error in results['errors']:
            lines.append(f"  {error}")
        lines.append("")

    lines.append("=" * 70)
    lines.append("END OF REPORT")
    lines.append("=" * 70)

    return '\n'.join(lines)


# =============================================================================
# GUI
# =============================================================================

class Calibre2LibiryApp:
    """GUI voor Calibre2Libiry in Libiry stijl."""

    def __init__(self):
        # Laad Libiry styling uit customize.txt
        self._load_style()

        self.root = tk.Tk()
        self.root.title("Calibre2Libiry")
        self.root.geometry("550x350")
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

        self.library_folder = tk.StringVar()

        self._create_widgets()

    def _load_style(self):
        """Laad styling uit Libiry's customize.txt."""
        try:
            from core.libiry_style import load_libiry_style
            style = load_libiry_style(SCRIPT_DIR)
        except ImportError:
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

        style.configure('TFrame', background=self.BG_COLOR)
        style.configure('TLabel', background=self.BG_COLOR, foreground=self.BG_FONT_COLOR,
                       font=('Helvetica', self.FONT_SIZE))
        style.configure('Title.TLabel', background=self.BG_COLOR, foreground=self.BG_FONT_COLOR,
                       font=('Helvetica', self.FONT_SIZE + 6, 'bold'))
        style.configure('Subtitle.TLabel', background=self.BG_COLOR, foreground=self.BG_FONT_COLOR,
                       font=('Helvetica', self.FONT_SIZE))
        # Warning in zelfde kleur als achtergrond font (geen slecht leesbare kleuren)
        style.configure('Warning.TLabel', background=self.BG_COLOR, foreground=self.BG_FONT_COLOR,
                       font=('Helvetica', self.FONT_SIZE - 1))

        style.configure('TEntry', fieldbackground=self.ENTRY_BG,
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
            relief='flat',
            borderwidth=0,
            padx=15,
            pady=7,
            cursor='hand2'
        )
        return btn

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
        main = ttk.Frame(self.root, padding="20")
        main.grid(row=0, column=0, sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main.columnconfigure(1, weight=1)

        # Title
        title = ttk.Label(main, text="Calibre2Libiry", style='Title.TLabel')
        title.grid(row=0, column=0, columnspan=3, pady=(0, 5))

        subtitle = ttk.Label(main, text="Convert Calibre metadata files to Libiry metadata files",
                            style='Subtitle.TLabel')
        subtitle.grid(row=1, column=0, columnspan=3, pady=(0, 20))

        # Library folder - entry en button direct tegen elkaar aan, zelfde hoogte en font
        # Consistente verticale spacing (pady=8) op form row
        ttk.Label(main, text="Calibre library:").grid(row=2, column=0, sticky="w", pady=8)
        library_frame = self._create_entry_with_button(
            main, self.library_folder, "...", self._browse)
        library_frame.grid(row=2, column=1, columnspan=2, sticky="w", pady=8)

        # Warning
        warning = ttk.Label(main,
            text="Note: covers are renamed, OPF files are converted to MD files but not deleted.",
            style='Warning.TLabel')
        warning.grid(row=3, column=0, columnspan=3, pady=(15, 5))

        # Info label
        self.info_label = ttk.Label(main, text="")
        self.info_label.grid(row=4, column=0, columnspan=3, pady=5)

        # Progress (tekst ipv balk)
        self.progress_label = ttk.Label(main, text="")
        self.progress_label.grid(row=5, column=0, columnspan=3, pady=(15, 5))

        # Buttons
        btn_frame = ttk.Frame(main)
        btn_frame.grid(row=7, column=0, columnspan=3, pady=20)

        self.convert_btn = self._create_button(btn_frame, "Convert", self._convert)
        self.convert_btn.pack(side='left', padx=5)

        # Status
        self.status_label = ttk.Label(main, text="")
        self.status_label.grid(row=8, column=0, columnspan=3)

    def _browse(self):
        folder = filedialog.askdirectory(title="Select your Calibre library folder")
        if folder:
            self.library_folder.set(folder)
            # Count files to convert
            opf_count, cover_count = count_files_to_convert(Path(folder))
            total = opf_count + cover_count
            self.info_label.config(
                text=f"Found {total} files to convert ({opf_count} metadata + {cover_count} covers)",
                foreground=self.BG_FONT_COLOR)

    def _validate(self) -> Path | None:
        path = self.library_folder.get()
        if not path:
            messagebox.showerror("Error", "Please select a folder")
            return None

        library_path = Path(path)
        if not library_path.exists():
            messagebox.showerror("Error", "Folder does not exist")
            return None

        # Check voor OPF files of standalone covers
        opf_count, cover_count = count_files_to_convert(library_path)
        if opf_count + cover_count == 0:
            messagebox.showerror("Error", "No metadata.opf files or standalone covers found.")
            return None

        return library_path

    def _convert(self):
        library_path = self._validate()
        if not library_path:
            return

        # Confirm
        if not messagebox.askyesno("Confirm",
            "This will:\n"
            "- Create Markdown sidecar files (.md) from Calibre metadata\n"
            "- Rename cover files to sidecar format\n\n"
            "Original metadata.opf files will be preserved.\n\n"
            "Continue?"):
            return

        self.convert_btn.config(state='disabled')
        self._library_path = library_path  # Store for use in thread

        thread = threading.Thread(target=self._convert_thread, args=(library_path,))
        thread.daemon = True
        thread.start()

    def _convert_thread(self, library_path: Path):
        from datetime import datetime

        def progress(current, total, name):
            pct = (current / total) * 100
            self.root.after(0, lambda: self._update_progress(pct, f"Converting: {name[:30]}..."))

        results = convert_calibre_library(
            library_path, dry_run=False, progress_callback=progress)

        # Generate and save report
        report = generate_conversion_report(library_path, results, dry_run=False)
        report_path = library_path / f"calibre2libiry_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        try:
            report_path.write_text(report, encoding='utf-8')
            report_saved = str(report_path)
        except Exception:
            report_saved = None

        self.root.after(0, lambda: self._show_result(results, report_saved))

    def _update_progress(self, pct: float, text: str):
        # Toon percentage en tekst samen
        self.progress_label.config(text=f"[{pct:.0f}%] {text}")

    def _show_result(self, results: dict, report_path: str = None):
        self.convert_btn.config(state='normal')
        self.progress_label.config(text="DONE")

        md_ok = results['md_success']
        cover_ok = results['cover_success']
        errors = results['errors']

        msg = f"Conversion complete!\n\n"
        msg += f"Created {md_ok} sidecars\n"
        msg += f"Renamed {cover_ok} covers\n"

        if errors:
            msg += f"\n{len(errors)} errors occurred."

        if report_path:
            msg += f"\n\nReport saved to:\n{report_path}"

        self.status_label.config(text="DONE - Conversion complete!", foreground=self.BG_FONT_COLOR)
        messagebox.showinfo("Complete", msg)

    def run(self):
        self.root.mainloop()


# =============================================================================
# CLI Mode (backwards compatibility)
# =============================================================================

def cli_main(library_path: Path):
    """Command-line interface."""
    from datetime import datetime

    print("=" * 60)
    print("  Calibre2Libiry - Metadata Converter")
    print("=" * 60)
    print()

    if not library_path.exists():
        print(f"Error: Path does not exist: {library_path}")
        sys.exit(1)

    opf_count, cover_count = count_files_to_convert(library_path)
    total = opf_count + cover_count
    if total == 0:
        print("No files to convert (all sidecars/covers already exist or no OPF files found).")
        sys.exit(0)

    print(f"Found: {total} files to convert ({opf_count} metadata + {cover_count} covers)")
    print()

    # Preview
    print("Preview:")
    print("-" * 40)

    def progress(current, total, name):
        pct = (current / total) * 100
        print(f"\r[{pct:5.1f}%] {name[:40]:<40}", end='', flush=True)

    results = convert_calibre_library(library_path, dry_run=True, progress_callback=progress)
    print()
    print("-" * 40)
    print(f"Would create: {results['md_success']} sidecars, rename {results['cover_success']} covers")
    if results['md_skip'] + results['cover_skip'] > 0:
        print(f"Would skip: {results['md_skip']} sidecars, {results['cover_skip']} covers")
    print()

    confirm = input("Continue with conversion? (y/n): ").strip().lower()
    if confirm not in ('y', 'yes', 'j', 'ja'):
        print("Cancelled.")
        sys.exit(0)

    print()
    print("Converting...")
    results = convert_calibre_library(library_path, dry_run=False, progress_callback=progress)
    print()

    # Generate and save report
    report = generate_conversion_report(library_path, results, dry_run=False)
    report_path = library_path / f"calibre2libiry_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    try:
        report_path.write_text(report, encoding='utf-8')
        print(f"Report saved: {report_path}")
    except Exception as e:
        print(f"Could not save report: {e}")

    print()
    print("=" * 60)
    print(f"DONE! {results['md_success']} sidecars created, {results['cover_success']} covers renamed.")
    print("=" * 60)


# =============================================================================
# Main
# =============================================================================

def main():
    if len(sys.argv) > 1:
        # CLI mode
        cli_main(Path(sys.argv[1]))
    else:
        # GUI mode
        app = Calibre2LibiryApp()
        app.run()


if __name__ == '__main__':
    main()
