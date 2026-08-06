#!/usr/bin/env python3
"""Align book data - Maintenance tool for Libiry metadata
This script executes 2 tasks:
1. It cleans up redundant sidecars
2. It reports conflicting metadata (sidecar and book info differ)
Use: python Align_book_data.py"""

import sys
from pathlib import Path
from typing import Tuple, List, Dict, Any
from datetime import datetime
import threading

# To show Libiry icon in Windows taskbar: set AppUserModelID
# Do this before the Kivy imports
try:
    import ctypes
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('Libiry.AlignBookData.1')
except (ImportError, AttributeError, OSError):
    pass
from version import __version__
from kivy.config import Config
_icon_path = Path(__file__).parent / "resources" / "icons" / "Libiry.png"
if _icon_path.exists():
    Config.set('kivy', 'window_icon', str(_icon_path).replace('\\', '/'))
    Config.set('input', 'mouse', 'mouse,multitouch_on_demand')

from kivy.metrics import dp
from kivy.uix.label import Label

try:
    from core.metadata_extractor import MetadataExtractor, get_sidecar_path
    from core.libiry_style import normalize_language_code, is_undefined_language, authors_equivalent, is_os_hidden
except ImportError:
    # MetadataExtractor = None: If the import fails, the app should not proceed, but it should give an error message
    load_selected_types = None

# =============================================================================
# Constants
# =============================================================================

# Script directory for imports
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

NATIVE_METADATA_FORMATS = {'.epub', '.cbz'}

# =============================================================================
# Helpers
# =============================================================================

def is_sidecar_redundant(sidecar_meta, ebook_path: Path) -> bool:
    """Check if a sidecar can safely be deleted
    A sidecar is redundant if every field either:
    - Is empty/None in both sidecar and native, OR
    - Has the same value in sidecar and native (truly redundant)
    A sidecar must be kept if any field:
    - Has a value in sidecar but not in native (sidecar adds info), OR
    - Is empty in sidecar but not empty in native (sidecar suppresses native), OR
    - Differs from native (sidecar overrides native)
    from core.metadata_extractor import MetadataExtractor"""

    #print(f"DEBUG sidecar_meta('{sidecar_meta}')")
    if sidecar_meta is None:
        return True

    try:
        extractor = MetadataExtractor()
        #Read "pure" book metadata, so without the sidecars
        native_meta = extractor.extract(ebook_path, False)
        #print(f"DEBUG native_meta('{native_meta}')")
    except Exception as e:
        # Cannot determine native metadata - keep sidecar to be safe
        print(f"DEBUG extract failed: {e}")
        return False

    # Compare all fields: sidecar is redundant only if every field
    # is either both empty or identical to native

    # Simple string fields
    string_fields = [
        ('booktitle', 'booktitle'),
        ('author_sort', 'author_sort'),
        ('isbn', 'isbn'),
        ('publisher', 'publisher'),
        ('language', 'language'),
        ('publication_date', 'publication_date'),
        ('pages', 'pages'),
        ('series', 'series'),
        ('translator', 'translator'),
        ('illustrator', 'illustrator'),
        ('description', 'description'),
        ('notes', 'notes'),
    ]

    for sidecar_field, native_field in string_fields:
        sidecar_val = (getattr(sidecar_meta, sidecar_field, None) or '').strip()
        native_val = (getattr(native_meta, native_field, None) or '').strip()

        if sidecar_val != native_val:
            # Different: sidecar either adds, overrides, or suppresses - keep it
            return False

    # Authors
    sidecar_authors = sorted(sidecar_meta.authors or [])
    native_authors = sorted(native_meta.authors or [])
    if sidecar_authors != native_authors:
        return False

    # Rating
    sidecar_rating = sidecar_meta.rating
    native_rating = native_meta.rating
    if sidecar_rating != native_rating:
        return False

    # Series index
    sidecar_si = sidecar_meta.series_index
    native_si = native_meta.series_index
    if sidecar_si != native_si:
        return False

    # Tags - filter placeholder before comparing
    sidecar_tags = sorted(
        t for t in (sidecar_meta.tags or [])
        if t and t != '__tag_in_sidecar__'
    )
    native_tags = sorted(native_meta.tags or [])
    if sidecar_tags != native_tags:
        return False

    # Every field is identical to native - sidecar is truly redundant
    return True

def normalize_for_comparison(value: Any) -> str:
    """Normalize a value before comparing
    Convert to lowercase string, trimmed"""
    if value is None:
        return ''
    if isinstance(value, list):
        return ', '.join(sorted(str(v).strip().lower() for v in value if v))
    return str(value).strip().lower()

def compare_metadata(native_meta, sidecar_meta) -> Dict[str, Tuple[str, str]]:
    """Compare native metadata to sidecar metadata
    Returns Dict with field name -> (native_value, sidecar_value)"""
    conflicts = {}
    # Fields to compare
    fields = [
        ('booktitle', 'booktitle'),
        ('authors', 'authors'),
        ('isbn', 'isbn'),
        ('publisher', 'publisher'),
        ('language', 'language'),
        ('publication_date', 'publication_date'),
        ('series', 'series'),
        ('series_index', 'series_index'),
        ('tags', 'tags'),
        ('description', 'description'),
    ]

    for native_field, sidecar_field in fields:
        native_val = getattr(native_meta, native_field, None) if native_meta else None
        sidecar_val = getattr(sidecar_meta, sidecar_field, None) if sidecar_meta else None

        # Normalize for comparison
        # Language field gets special treatment (ISO 639-1 vs 639-2, UNDefined handling)
        if native_field == 'language':
            # Skip conflict if native is UND (undefined) - sidecar value is better
            if native_val and is_undefined_language(native_val):
                continue
            native_norm = normalize_language_code(native_val) if native_val else ''
            sidecar_norm = normalize_language_code(sidecar_val) if sidecar_val else ''
        elif native_field == 'authors':
            # Skip conflict if authors are equivalent (e.g., "First Last" vs "Last, First")
            if native_val and sidecar_val and authors_equivalent(native_val, sidecar_val):
                continue
            native_norm = normalize_for_comparison(native_val)
            sidecar_norm = normalize_for_comparison(sidecar_val)
        else:
            native_norm = normalize_for_comparison(native_val)
            sidecar_norm = normalize_for_comparison(sidecar_val)

        # Only report if both have a value AND they differ
        # Note: UND (undefined) is NOT considered equivalent to any real language
        if native_norm and sidecar_norm and native_norm != sidecar_norm:
            # Original values for report (not normalised)
            native_display = native_val if not isinstance(native_val, list) else ', '.join(str(v) for v in native_val)
            sidecar_display = sidecar_val if not isinstance(sidecar_val, list) else ', '.join(str(v) for v in sidecar_val)
            conflicts[native_field] = (str(native_display), str(sidecar_display))

    return conflicts

# =============================================================================
# Report generation
# =============================================================================

def generate_report(folder_path: Path,
                    redundant_sidecars: Tuple[int, int, List[Path]],
                    conflicts: List[Dict], dry_run: bool) -> str:
    """Generate a text report of all findings
    Returns Report as string"""
    lines = []
    lines.append("=" * 70)
    lines.append("LIBIRY BOOK METADATA ALIGNMENT REPORT")
    if dry_run:
       lines.append(f"PREVIEW MODE")
    lines.append(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"Folder: {folder_path}")
    lines.append("=" * 70)
    lines.append("")

    # Section 1: Redundant sidecars
    found, removed, removed_paths = redundant_sidecars
    lines.append("-" * 70)
    lines.append("1. REDUNDANT SIDECARS")
    lines.append("-" * 70)
    lines.append(f"Sidecars found: {found}")
    if dry_run:
        lines.append(f"Redundant sidecars found: {removed}")
    else:
        lines.append(f"Redundant sidecars removed: {removed}")
    if removed_paths:
        lines.append("")
        if dry_run:
            lines.append(f"Redundant files:")
        else:
            lines.append("Removed files:")
        for p in removed_paths:
            lines.append(f"  - {p.relative_to(folder_path)}")
    lines.append("")

    # Section 2: Conflicts
    lines.append("-" * 70)
    lines.append("2. METADATA CONFLICTS")
    lines.append("-" * 70)
    lines.append(f"Files with conflicts: {len(conflicts)}")
    if conflicts:
        lines.append("")
        for item in conflicts:
            lines.append(f"File: {item['path'].relative_to(folder_path)}")
            for field, (native, sidecar) in item['conflicts'].items():
                lines.append(f"  {field}:")
                lines.append(f"    Native:  {native[:80]}{'...' if len(native) > 80 else ''}")
                lines.append(f"    Sidecar: {sidecar[:80]}{'...' if len(sidecar) > 80 else ''}")
            lines.append("")
    lines.append("")

    # Summary
    lines.append("=" * 70)
    lines.append("SUMMARY")
    lines.append("=" * 70)
    if dry_run:
        lines.append(f"  Redundant sidecars found: {removed}")
    else:
        lines.append(f"  Redundant sidecars removed: {removed}")
    lines.append(f"  Metadata conflicts found: {len(conflicts)}")
    lines.append("")

    if conflicts:
        lines.append("ACTION REQUIRED: Review the metadata conflicts and decide which")
        lines.append("                 value is correct (native or sidecar).")

    return '\n'.join(lines)

# =============================================================================
# GUI
# =============================================================================

from core.libiry_style import LibiryKivyApp

class AlignBookDataApp(LibiryKivyApp):
    """GUI for Align Book Data"""

    def __init__(self, **kwargs):
        # super().__init__(**kwargs) calls LibiryKivyApp.__init__:
        #   1. App.__init__(**kwargs)  — Kivy property system ready
        #   2. _load_style()           — colors loaded from customize.txt
        super().__init__(**kwargs)
        # Configure window title, size and background color
        # Must happen after _load_style() (BG_COLOR needed) and before run()
        self._setup_kivy_app('Check metadata', 550, 400) #width resp. height
        
    def _create_widgets(self):
        layout = self._layout
        
        # Title and description
        self.title = f'Align book data {__version__}'
        self._create_label(layout, "Align book data", style='title')
        self._create_label(layout, "Check and consolidate metadata, clean sidecars and detect conflicts", style='subtitle')

        # Select input folder
        self._add_location_field(layout, 'Folder to scan', 'input_folder',
                                   self.custom.get('location', ''))
        self._add_yn_field(layout, 'Preview only (dry run - no changes)',
                             'dry_run', True) #Dry run default ON
        self._load_last_folder()

        # Tool description (multi-line, left-aligned, auto-wrapping)
        info_text = ("This tool will:\n"
                     "  1. Remove redundant sidecar files\n"
                     "  2. Report metadata conflicts (sidecar vs native)\n"
                     "  3. Generate a full report")
        info_desc = Label(
            text=info_text,
            color=self.BG_FONT_COLOR,
            font_size=self.FONT_SIZE,
            halign='left', valign='top',
            size_hint_y=None, height=dp(80),
        )
        # Text_size must track widget width for wrapping to work in Kivy
        info_desc.bind(
            width=lambda w, v: setattr(w, 'text_size', (v, None)))
        layout.add_widget(info_desc)

        # Run button
        self.execute_btn = self._create_button(layout, 'Run', self._execute)
          
        # Folder info, progress, status
        self.info_label     = self._create_label(layout, "", style='normal')
        self.progress_label = self._create_label(layout, "", style='normal')
        self.status_label   = self._create_label(layout, "", style='normal')
           
    # -- Folder browse --------------------------------------------------

    def _validate(self):
        path = self._settings_inputs['input_folder'].text.strip()
        if not path:
            self._show_error("Please select a folder")
            return None
        folder_path = Path(path)
        if not folder_path.exists():
            self._show_error("Folder does not exist")
            return None
        return folder_path

    def _execute(self):
        folder_path = self._validate()
        if not folder_path:
            return
        dry_run = self._settings_inputs['dry_run'].active
        if not dry_run:
            # Disable immediately; re-enable in on_no if cancelled
            self.execute_btn.disabled = True
            self._show_confirm(
                message=("This will:\n"
                         "- Remove redundant sidecar files\n"
                         "- Generate a report file\n\n"
                         "Continue?"),
                on_yes=lambda: self._start_execute(folder_path, dry_run),
                on_no=lambda: setattr(self.execute_btn, 'disabled', False),
            )
        else:
            self.execute_btn.disabled = True
            self._start_execute(folder_path, dry_run)

    def _start_execute(self, folder_path: Path, dry_run: bool):
        thread = threading.Thread(
            target=self._execute_thread, args=(folder_path, dry_run))
        thread.daemon = True
        thread.start()

    def _cleanup_redundant_sidecars(self, folder_path: Path, dry_run: bool = False, verbose: bool = True) -> Tuple[int, int, List[Path]]:
        """Args:
            folder_path: Folder to scan (recursive)
            dry_run: If True, just report without deleting
            verbose: Show progress
        Returns tuple of (found, deleted, list of deleted paths)"""
        from core.metadata_extractor import get_sidecar_path

        found = 0
        removed = 0
        removed_paths = []
 
        # Look for all .md sidecar files. Note that this logic is much more precise than the logic in libiry_style.py/is_hidden
        for md_file in list(folder_path.rglob('*.md')):

            # Check if this file is hidden or in a hidden folder
            rel_parts = md_file.relative_to(folder_path).parts
            if any(is_os_hidden(folder_path.joinpath(*rel_parts[:i + 1]))
                   for i in range(len(rel_parts))):
                continue

            # Check if this is a sidecar (name ends on .ext.md)
            # F.e.: book.pdf.md, book.epub.md
            stem = md_file.stem  # book.pdf
            if '.' not in stem:
                continue  # No sidecar, just a markdown file

            # Check if parent file exists
            parent_file = md_file.parent / stem
            if not parent_file.exists():
                continue  # Orphan sidecar - or ALSO just a markdown file... skip it 

            found += 1

            # Read sidecar metadata
            sidecar_meta = self.extractor.read_markdown_metadata(md_file)
            if is_sidecar_redundant(sidecar_meta, parent_file):
                if verbose:
                    print(f"  Empty sidecar: {md_file.relative_to(folder_path)}")

                if not dry_run:
                    try:
                        md_file.unlink()
                        removed += 1
                        removed_paths.append(md_file)
                    except Exception as e:
                        print(f"    Error deleting: {e}")
                else:
                    removed += 1
                    removed_paths.append(md_file)

        return found, removed, removed_paths

    def _find_metadata_conflicts(self,folder_path: Path, verbose: bool = True) -> List[Dict]:
        """Find files where sidecar and native metadata conflict
        Args:
            folder_path: folder to scan (recursive)
            verbose: show progress
        Returns list of dicts with conflicting information"""
        
        conflicts_list = []

        # Scan all files with native metadata support
        for ext in NATIVE_METADATA_FORMATS:
            pattern = f'**/*{ext}'
            for file_path in folder_path.glob(pattern):

                rel_parts = file_path.relative_to(folder_path).parts
                if any(is_os_hidden(folder_path.joinpath(*rel_parts[:i + 1]))
                       for i in range(len(rel_parts))):
                    continue

                # Check if a sidecar exists
                sidecar_path = get_sidecar_path(file_path)
                if not sidecar_path.exists():
                    continue

                if verbose:
                    print(f"  Checking: {file_path.name}...", end=' ')

                try:
                    # Read native metadata (without sidecar fallback)
                    native_meta = self.extractor.extract(file_path, False)

                    # Read sidecar metadata
                    sidecar_meta = self.extractor.read_markdown_metadata(sidecar_path)
                    
                    # Compare
                    conflicts = compare_metadata(native_meta, sidecar_meta)

                    if conflicts:
                        if verbose:
                            print(f"CONFLICT ({len(conflicts)} velden)")
                        conflicts_list.append({
                            'path': file_path,
                            'conflicts': conflicts
                        })
                    else:
                        if verbose:
                            print("OK")

                except Exception as e:
                    if verbose:
                        print(f"ERROR: {e}")

        return conflicts_list

    def _execute_thread(self, folder_path: Path, dry_run: bool):
        from kivy.clock import Clock

        def upd(text):
            Clock.schedule_once(
                lambda dt: setattr(self.progress_label, 'text', text), 0)

        upd("Task 1/2: Clean up redundant sidecars...")
        redundant_results = self._cleanup_redundant_sidecars(
            folder_path, dry_run, verbose=False)
        upd(f"Task 1/2: {redundant_results[1]} redundant sidecars found")

        upd("Task 2/2: Detect metadata conflicts...")
        conflicts = self._find_metadata_conflicts(folder_path, verbose=False)
        upd(f"Task 2/2: {len(conflicts)} conflicts found")

        upd("Creating report...")
        report = generate_report(folder_path, redundant_results, conflicts, dry_run)

        report_path = (folder_path /
                           f"metadata_report_"
                           f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
        try:
            report_path.write_text(report, encoding='utf-8')
            report_saved = str(report_path)
        except Exception:
            report_saved = None

        Clock.schedule_once(
            lambda dt: self._show_results(
                redundant_results, conflicts, report_saved, dry_run), 0)

    def _show_results(self, redundant_results, conflicts,
                      report_path, dry_run):
        self.execute_btn.disabled    = False
        self.progress_label.text = ""

        found, removed, _ = redundant_results
        mode = "Preview" if dry_run else "Complete"

        msg  = f"{mode}!\n\n"
        msg += (f"Redundant sidecars: {removed} of {found} "
                f"{'would be ' if dry_run else ''}removed\n")
        msg += f"Metadata conflicts: {len(conflicts)} found\n"
        if report_path:
            msg += f"\nReport saved to:\n{report_path}"

        self.status_label.text  = f"{mode}!"
        self.status_label.color = self.BG_FONT_COLOR
        self._show_info("Results", msg)

# =============================================================================
# Main
# =============================================================================

def main():
    """Main entry point
    In case of startup issues the app is automatically started again"""
    try:
        AlignBookDataApp().run()
    except Exception as e:
        print(f"Startup error: {e}")
        print("Restarting...")
        # Try to start again
        try:
            AlignBookDataApp().run()
        except Exception as e2:
            print(f"Failed to restart: {e2}")
            raise

if __name__ == '__main__':
    main()