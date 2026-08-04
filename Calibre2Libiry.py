"""Calibre2Libiry - Convert Calibre metadata.opf to Libiry Markdown sidecar format

Calibre saves metadata in metadata.opf files per book-folder
Libiry expects metadata in {bookfile}.md format (f.e. book.pdf.md)
Calibre saves covers as cover.jpg/cover.png in the book folder
Libiry expects covers in {bookfile}.jpg format (f.e. book.pdf.jpg)

This script:
1. Reads Calibre's metadata.opf XML files
2. Converts the metadata to Libiry's Markdown sidecar format (YAML frontmatter)
3. Writes the result as book.ext.md
4. Renames cover files to book.ext.jpg/.png

Use: python Calibre2Libiry.py                    

Beware:
    - This script RENAMES cover files (no copy)
    - metadata.opf metadata is copied into a markdown file and then  metadata.opf is deleted
    - Make a backup of your Calibre library first, just to be sure"""

import sys
from pathlib import Path
import threading

# Windows taskbar icon fix: set AppUserModelID so that Windows shows the correct icon in the taskbar instead of the Python icon

# To show Libiry icon in Windows taskbar: set AppUserModelID
# Do this before the Kivy imports
try:
    import ctypes
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('Libiry.Calibre2Libiry.1')
except (ImportError, AttributeError, OSError):
    pass
  
from version import __version__  
from kivy.config import Config
_icon_path = Path(__file__).parent / "resources" / "icons" / "Libiry.png"
if _icon_path.exists():
    Config.set('kivy', 'window_icon', str(_icon_path).replace('\\', '/'))
    Config.set('input', 'mouse', 'mouse,multitouch_on_demand')

from core.metadata_extractor import MetadataExtractor, get_sidecar_path, save_full_metadata

# =============================================================================
# Constants
# =============================================================================

# Script directory for imports
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

# Supported Calibre ebook extensions
EBOOK_EXTENSIONS = {
    '.epub', '.mobi', '.azw', '.azw3', '.pdf',
    '.cbz', '.cbr', '.djvu', '.fb2', '.lit',
    '.pdb', '.rtf', '.txt'
}

# Supported cover image extensions
COVER_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}

# =============================================================================
# Core Functions
# =============================================================================

def find_ebook_in_folder(folder_path: Path) -> Path | None:
    """Find the ebook file in a Calibre book folder (returns first ebook)"""
    for file in folder_path.iterdir():
        if file.is_file() and file.suffix.lower() in EBOOK_EXTENSIONS:
            return file
    return None

def count_ebooks_in_folder(folder_path: Path) -> int:
    """Count the number of ebook files in a folder"""
    count = 0
    for file in folder_path.iterdir():
        if file.is_file() and file.suffix.lower() in EBOOK_EXTENSIONS:
            count += 1
    return count

def find_cover_in_folder(folder_path: Path) -> Path | None:
    """Find the cover file in a Calibre book folder"""
    for file in folder_path.iterdir():
        if file.is_file():
            name_lower = file.stem.lower()
            ext_lower = file.suffix.lower()
            if name_lower == 'cover' and ext_lower in COVER_EXTENSIONS:
                return file
    return None

def count_opf_files(folder_path: Path) -> int:
    """Count the number of metadata.opf files"""
    return len(list(folder_path.rglob('metadata.opf')))

def find_standalone_cover_folders(folder_path: Path) -> list[Path]:
    """Find folders with exactly 1 ebook and 1 cover, but without metadata.opf
    These covers can also be renamed to the Libiry naming convention"""
    
    standalone_folders = []
    processed_folders = set()

    # Gather all folders with metadata.opf (they are processed separately)
    for opf_path in folder_path.rglob('metadata.opf'):
        processed_folders.add(opf_path.parent)

    # Search through all subfolders for standalone covers
    for folder in folder_path.rglob('*'):
        if not folder.is_dir():
            continue
        if folder in processed_folders:
            continue

        # Check: exactly 1 ebook and 1 cover in this folder
        if count_ebooks_in_folder(folder) == 1 and find_cover_in_folder(folder):
            standalone_folders.append(folder)

    return standalone_folders

def cover_needs_renaming(folder_path: Path, ebook: Path = None) -> bool:
    """Check if a cover in the folder needs renaming
    Returns False if:
    - There is no cover
    - The cover already has the proper name (ebook.ext.jpg)"""
    cover = find_cover_in_folder(folder_path)
    if not cover:
        return False

    if ebook is None:
        ebook = find_ebook_in_folder(folder_path)
    if ebook is None:
        return False

    # Check if cover already has the proper name
    expected_name = ebook.name + cover.suffix.lower()
    if cover.name.lower() == expected_name.lower():
        return False  # Already correct

    # Check if target exists already
    target_path = folder_path / expected_name
    if target_path.exists():
        return False  # Target already exists

    return True

def count_files_to_execute(folder_path: Path) -> tuple[int, int]:
    """Count the number of OPF and cover files to convert
    Counts only the covers that still need to be renamed"""
    
    opf_count = 0
    cover_count = 0

    # Folders with metadata.opf (Calibre style)
    for opf_path in folder_path.rglob('metadata.opf'):
        folder = opf_path.parent
        ebook = find_ebook_in_folder(folder)

        # Count OPF only if there is no markdown sidecar yet
        if ebook:
            sidecar_path = get_sidecar_path(ebook)
            if not sidecar_path.exists():
                opf_count += 1

            # Count cover only when it needs to be renamed
            if cover_needs_renaming(folder, ebook):
                cover_count += 1
        else:
            # No ebook: skip
            pass

    # Standalone covers (1 ebook + 1 cover, no opf)
    standalone_folders = find_standalone_cover_folders(folder_path)
    for folder in standalone_folders:
        ebook = find_ebook_in_folder(folder)
        if cover_needs_renaming(folder, ebook):
            cover_count += 1

    return opf_count, cover_count

def generate_conversion_report(folder_path: Path, results: dict, dry_run: bool = False) -> str:
    """Args:
        folder_path: The converted library folder
        results: Dict with results of _convert_calibre_library()
        dry_run: Indicates whether this was a preview
    Returns Report as string"""
    from datetime import datetime

    lines = []
    lines.append("=" * 70)
    lines.append("CALIBRE2LIBIRY CONVERSION REPORT")
    lines.append(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"Library: {folder_path}")
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
                rel_path = path.relative_to(folder_path)
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
                old_rel = old_path.relative_to(folder_path)
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

from core.libiry_style import LibiryKivyApp

class Calibre2LibiryApp(LibiryKivyApp):
    """GUI for Calibre2Libiry in Libiry style"""

    def __init__(self, **kwargs):
        # super().__init__(**kwargs) calls LibiryKivyApp.__init__:
        #   1. App.__init__(**kwargs)  — Kivy property system ready
        #   2. _load_style()           — colors loaded from customize.txt
        super().__init__(**kwargs)
        # Configure window title, size and background color
        # Must happen after _load_style() (BG_COLOR needed) and before run()
        self._setup_kivy_app('Calibre2Libiry', 550, 350) #width resp. height

    def _create_widgets(self):
        layout = self._layout

        # Title and description
        self.title = f'Calibre2Libiry {__version__}'
        self._create_label(layout, "Calibre2Libiry", style='title')
        self._create_label(layout,
                           "Convert Calibre metadata files to Libiry metadata files",
                           style='subtitle')

        # Select folder
        self._add_location_field(layout, 'Library folder', 'input_folder',                          self.custom.get('location', ''))
        self._add_yn_field(layout, 'Preview only (dry run - no changes)',
                             'dry_run', True) #Dry run default ON
        self._load_last_folder()

        # Warning (smaller font)
        self._create_label(
            layout,
            "Note: covers are renamed and OPF files are converted into MD files",
            style='warning',
        )

        # Info, progress, action button, status
        self.info_label     = self._create_label(layout, "", style='normal')
        self.progress_label = self._create_label(layout, "", style='normal')
        self.execute_btn    = self._create_button(layout, "Convert", self._execute)
        self.status_label   = self._create_label(layout, "", style='normal')

    def _validate(self) -> Path | None:
        path = self._settings_inputs['input_folder'].text.strip()
        if not path:
            self._show_error("Please select a folder")
            return None
        folder_path = Path(path)
        if not folder_path.exists():
            self._show_error("Folder does not exist")
            return None
        opf_count, cover_count = count_files_to_execute(folder_path)
        if opf_count + cover_count == 0:
            self._show_info('Information',
                "No metadata.opf files or standalone covers were found in this folder")
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
                     "- Convert Calibre .opf into Libiry .md sidecar files\n"
                     "- Rename cover files to the Libiry naming convention\n\n"
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

    def _convert_calibre_library(self, folder_path: Path, dry_run: bool = False, progress_callback=None) -> dict:
        """Converts all metadata.opf and cover files in a Calibre library
        OPF files are converted to Markdown files
        Cover files are renamed to Libiry naming convention
        Uses save_full_metadata to merge OPF metadata with native ebook metadata, filtering out redundant values
        Returns:
            Dict with results:
            - md_success, md_skip: sidecar counts
            - cover_success, cover_skip: cover counts
            - errors: list of error messages
            - created_sidecars: list of created sidecar paths
            - renamed_covers: list of (old_path, new_path) tuples"""

        results = {
            'md_success': 0,
            'md_skip': 0,
            'cover_success': 0,
            'cover_skip': 0,
            'errors': [],
            'created_sidecars': [],
            'renamed_covers': [],
        }

        # Gather all items that need to be processed
        opf_files = list(folder_path.rglob('metadata.opf'))
        standalone_folders = find_standalone_cover_folders(folder_path)
        total = len(opf_files) + len(standalone_folders)

        if total == 0:
            return results

        # === PHASE 1: Folders with metadata.opf (Calibre metadata) ===
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
            # Must happen before sidecar creation so save_full_metadata can find the correctly named cover file (e.g. book.pdf.jpg)
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

            # === STEP 2: Write all metadata into a markdown sidecar ===
            # The renamed cover will be found now
            sidecar_path = get_sidecar_path(ebook)

            if sidecar_path.exists():
                results['md_skip'] += 1
            elif not dry_run:
                try:
                    # Gather the metadata from all data sources, including the Calibre OPF
                    meta = self.extractor.extract(ebook)
                    if meta:
                        # Write to Markdown sidecar
                        metadata = {
                            'cover': meta.cover if meta else '',
                            'booktitle': meta.booktitle if meta else '',
                            'author': ', '.join(meta.authors) if meta and meta.authors else '',
                            'author_sort': meta.author_sort if meta else '',
                            'isbn': meta.isbn if meta else '',
                            'rating': str(meta.rating) if meta and meta.rating is not None else '',
                            'publisher': meta.publisher if meta else '',
                            'publication_date': meta.publication_date if meta else '',
                            'language': meta.language if meta else '',
                            'pages': meta.pages if meta else '',
                            'series': meta.series if meta else '',
                            'series_index': str(meta.series_index) if meta and meta.series_index is not None else '',
                            'translator': meta.translator if meta else '',
                            'illustrator': meta.illustrator if meta else '',
                            'tags': sorted(meta.tags) if meta and meta.tags else [],
                            'description': meta.description if meta else '',
                            'notes': meta.notes if meta else '',
                        }

                        use_sidecar = 'Y'
                        save_full_metadata(ebook, metadata, use_sidecar=use_sidecar)
                        results['md_success'] += 1
                        results['created_sidecars'].append(sidecar_path)
                    else:
                        results['md_skip'] += 1
                except Exception as e:
                    results['errors'].append(f"Sidecar error {opf_path.name}: {e}")
            else:
                # Dry run - count as success
                results['md_success'] += 1
                results['created_sidecars'].append(sidecar_path)

        # === PHASE 2: Standalone covers (1 ebook + 1 cover, no opf) ===
        for i, folder in enumerate(standalone_folders):
            if progress_callback:
                progress_callback(len(opf_files) + i + 1, total, folder.name)

            ebook = find_ebook_in_folder(folder)
            cover = find_cover_in_folder(folder)

            if ebook and cover:
                new_cover_name = ebook.name + cover.suffix.lower()
                new_cover_path = folder / new_cover_name

                # Check if cover is already correct and if target exists
                if cover.name.lower() == new_cover_name.lower():
                    # Already correct - do not count
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

    def _execute_thread(self, folder_path: Path, dry_run: bool):
        from datetime import datetime
        from kivy.clock import Clock

        def progress(current, total, name):
            pct = (current / total) * 100
            Clock.schedule_once(
                lambda dt: self._update_progress(
                    pct, f"Converting: {name[:30]}..."), 0)

        results = self._convert_calibre_library(
            folder_path, dry_run=dry_run, progress_callback=progress)
        report = generate_conversion_report(folder_path, results, dry_run=dry_run)
        report_path = (folder_path /
                       f"calibre2libiry_report_"
                       f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
        try:
            report_path.write_text(report, encoding='utf-8')
            report_saved = str(report_path)
        except Exception:
            report_saved = None

        Clock.schedule_once(
            lambda dt: self._show_results(results, report_saved, dry_run), 0)

    def _update_progress(self, pct: float, text: str):
        # Show percentage and text together
        # Override: this method is always called from Clock callbacks, so direct assignment is safe here. The base class version wraps in Clock.schedule_once, which would be redundant in this case
        self.progress_label.text = f"[{pct:.0f}%] {text}"

    def _show_results(self, results: dict, report_path, dry_run):
        self.execute_btn.disabled = False
        self.progress_label.text  = "DONE"

        md_ok    = results['md_success']
        cover_ok = results['cover_success']
        errors   = results['errors']

        if dry_run:
            msg  = "Preview complete — no changes made.\n\n"
            msg += f"Would create {md_ok} sidecars\n"
            msg += f"Would rename {cover_ok} covers\n"
        else:
            msg  = "Conversion complete!\n\n"
            msg += f"Created {md_ok} sidecars\n"
            msg += f"Renamed {cover_ok} covers\n"
        if errors:
            msg += f"\n{len(errors)} errors — see report for details."
        if report_path:
            msg += f"\n\nReport saved to:\n{report_path}"
            
        self.status_label.text = "DONE - Preview complete!" if dry_run else "DONE - Conversion complete!"
        self.status_label.color = self.BG_FONT_COLOR
        self._show_info("Complete", msg)       

# =============================================================================
# Main
# =============================================================================

def main():
    """Main entry point
    In case of startup issues the app is automatically started again"""
    try:
        Calibre2LibiryApp().run()
    except Exception as e:
        print(f"Startup error: {e}")
        print("Restarting...")
        # Try to start again
        try:
            Calibre2LibiryApp().run()
        except Exception as e2:
            print(f"Failed to restart: {e2}")
            raise

if __name__ == '__main__':
    main()