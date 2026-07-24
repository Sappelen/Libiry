#!/usr/bin/env python3
"""Libiry2Go - Portable book catalog generator
Creates markdown files with ebook library metadata that you can take on your phone or use in an app like Obsidian
Extracts metadata from ebooks and markdown files
One file per book in Obsidian format (YAML frontmatter)
Uses your own field name configuration (maintained in Libiry's customize settings)
Use: python libiry2go.py"""

import os
from pathlib import Path
from datetime import datetime
from typing import Dict, List
import threading

# To show Libiry icon in Windows taskbar: set AppUserModelID
# Do this before the Kivy imports
try:
    import ctypes
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('Libiry.Libiry2Go.1')
except (ImportError, AttributeError, OSError):
    pass

from version import __version__    
from kivy.config import Config
_icon_path = Path(__file__).parent / "resources" / "icons" / "Libiry.ico"
if _icon_path.exists():
    Config.set('kivy', 'window_icon', str(_icon_path).replace('\\', '/'))
    Config.set('input', 'mouse', 'mouse,multitouch_on_demand')

from kivy.properties import StringProperty   

try:
    from core.metadata_extractor import modify_markdown_metadata
    from core.libiry_style import is_hidden
except ImportError:
    pass

# =============================================================================
# Helpers
# =============================================================================

def format_file_size(size_bytes: int) -> str:
    """Format file size to human-readable string"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"

# =============================================================================
# Catalog Generation
# =============================================================================

def sanitize_filename(name: str) -> str:
    """Remove invalid characters from filename"""
    return ''.join(c if c not in '<>:"/\\|?*' else '_' for c in name)[:200]

def generate_markdown_files(books: List[Dict[str, str]],
                            output_folder: Path,
                            field_names: Dict[str, str]) -> List[Path]:
    """Generates markdown files from the book list"""
    output_folder.mkdir(parents=True, exist_ok=True)
    generated_files = []

    for book in books:
        author = book.get('author', 'Unknown') or 'Unknown'
        title  = book.get('booktitle', 'Untitled') or 'Untitled'
        filename = sanitize_filename(f"{author} - {title}.md")
        filepath = output_folder / filename

        # Prevent duplicates by adding a number
        counter = 1
        while filepath.exists():
            filename = sanitize_filename(f"{author} - {title} ({counter}).md")
            filepath = output_folder / filename
            counter += 1

        # Write body first; modify_markdown_metadata prepends YAML frontmatter to it
        filepath.write_text(f'\n# {title}\n\n', encoding='utf-8')
        # tags is already a list (from _scan_folder Step 3 above)
        # Compared to the Libiry app there are 3 extra fields: path, size and type. They have no entry in field_names, so field_names.get(key, key) returns the key itself, which works
        modify_markdown_metadata(None, filepath, book, field_names)
        generated_files.append(filepath)

    return generated_files

# =============================================================================
# GUI
# =============================================================================

from core.libiry_style import LibiryKivyApp

class Libiry2GoApp(LibiryKivyApp):
    """GUI for Libiry2Go"""
    
    current_path = StringProperty('')
    
    def __init__(self, **kwargs):
        # super().__init__(**kwargs) calls LibiryKivyApp.__init__:
        #   1. App.__init__(**kwargs)  — Kivy property system ready
        #   2. _load_style()           — colors loaded from customize.txt
        super().__init__(**kwargs)
        # Configure window title, size and background color
        # Must happen after _load_style() (BG_COLOR needed) and before run()
        self._setup_kivy_app('Libiry2Go', 550, 280)

    def _create_widgets(self):
        layout = self._layout
        self.title = f'Libiry2Go {__version__}'
        self._create_label(layout, "Libiry2Go", style='title')
        self._create_label(layout, "Create a portable catalog of your book library", style='subtitle')

        # Select input folder
        self._add_location_field(layout, 'Input folder', 'input_folder', self.custom.get('location', ''))
        self._load_last_folder()
        
        # Select output folder
        self._add_location_field(layout, 'Output folder', 'output_folder', '')

        # Dry-run checkbox row: [Label text] [CheckBox widget] 

        cb_row = self._create_popup_row()

        # 40% resize for correct alignment from label with "Input folder:" and "Output folder:"
        cb_row.add_widget(self._create_popup_label(
            "Preview only (dry run - no changes)", size_hint_x=0.4))

        # Progress, action button, status
        self.progress_label = self._create_label(layout, "", style='normal')

        self.generate_btn = self._create_button(layout, 'Generate Catalog', self._generate)
  
        self.status_label   = self._create_label(layout, "", style='normal')
        
    def _on_navigate(self, path: Path, add_to_history: bool = False):  
        # Base class sets self._current_folder before calling this
        #
        # When the user selects a folder via the path bar in Libiry2GoApp, the chain is:
        #  "Choose folder" button
        #    → _show_folder_chooser()
        #      → navigate_to(path)           ← LibiryKivyApp's version
        #        → self._current_folder = path
        #        → self._on_navigate(path)   ← resolves to Libiry2GoApp._on_navigate
        #          → sets output_entry.text suggestion
        
        output_input = self._settings_inputs['output_folder']
        if not output_input.text:
            # Auto-suggest output folder only when field is still empty
            output_input.text = str(path.parent / "Libiry2Go_Output")

    def _generate(self): 
        input_text = self._settings_inputs['input_folder'].text.strip()
        if not input_text:
            self._show_error("Please select a library folder")
            return
        input_path = Path(input_text)
        if not input_path.exists():
            self._show_error("Library folder does not exist")
            return  
            
        output_input = self._settings_inputs['output_folder']
        output_path = output_input.text.strip()
        if not output_path:
            output_path = str(self._current_folder.parent / "Libiry2Go_Output")
            output_input.text = output_path    

        self.generate_btn.disabled = True

        thread = threading.Thread(
            target=self._generate_thread,
            args=(input_path, Path(output_path)),
        )
        thread.daemon = True
        thread.start()
 
    def _scan_folder(self, folder: Path, progress_callback=None) -> List[Dict[str, str]]:
        """Scan a folder recursively and collect metadata from all files
        If multiple files have the same booktitle+author (e.g., an .epub and .md of the same book), they get (1), (2) etc. appended to the title"""
        books = []
        all_files = []

        for root, dirs, files in os.walk(folder):
            # Skip hidden folders
            dirs[:] = [d for d in dirs if not is_hidden(Path(root) / d, self.selected_types)]
            for filename in files:
                filepath = Path(root) / filename
                if is_hidden(filepath, self.selected_types):
                    continue
                    
                all_files.append(filepath)

        total = len(all_files)

        for i, filepath in enumerate(all_files):
            if progress_callback:
                progress_callback(i + 1, total, filepath.name)
                
            try:
                file_stat = filepath.stat() if filepath.exists() else None
            except OSError as e:
                print(f"Error accessing {filepath}: {e}")
                continue

            # Extract metadata
            meta = self.extractor.extract(filepath)
            metadata = {
                'cover': meta.cover or '',
                'booktitle': meta.booktitle or filepath.stem,
                'author': ', '.join(meta.authors) if meta.authors else '',
                'author_sort': meta.author_sort or '',
                'isbn': meta.isbn or '',
                'rating': str(meta.rating) if meta.rating is not None else '',
                'publisher': meta.publisher or '',
                'publication_date': meta.publication_date or '',
                'language': meta.language or '',
                'pages': meta.pages or '',
                'tags': sorted(meta.tags) if meta.tags else [],
                'series': meta.series or '',
                'series_index': str(meta.series_index) if meta.series_index is not None else '',
                'translator': meta.translator or '',
                'illustrator': meta.illustrator or '',
                'description': meta.description or '',
                'notes': meta.notes or '',
                'size': format_file_size(file_stat.st_size) if file_stat else '',
                'type': filepath.suffix.lower().lstrip('.'), # Get the e-book extension
                'path': str(filepath),
                'book_created': datetime.fromtimestamp(file_stat.st_ctime).strftime('%Y-%m-%d') if file_stat else '',
                'book_modified': datetime.fromtimestamp(file_stat.st_mtime).strftime('%Y-%m-%d') if file_stat else '',
            }
            
            books.append(metadata)
            
        # Sort by booktitle
        books.sort(key=lambda b: b.get('booktitle', '').lower())

        title_author_count = {}
        for book in books:
            key = (book.get('booktitle', '').lower(), book.get('author', '').lower())
            title_author_count[key] = title_author_count.get(key, 0) + 1

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
 
    def _generate_thread(self, input_folder: Path, output_folder: Path):
        from kivy.clock import Clock

        def progress_callback(current, total, filename):
            pct = (current / total) * 100
            Clock.schedule_once(
                lambda dt: self._update_progress(
                    pct, f"Scanning: {filename[:40]}..."), 0)

        Clock.schedule_once(
            lambda dt: self._update_progress(0, "Scanning library..."), 0)
        books = self._scan_folder(input_folder, progress_callback)

        if not books:
            Clock.schedule_once(
                lambda dt: self._show_result(
                    "No files found in the selected folder."), 0)
            return

        Clock.schedule_once(
            lambda dt: self._update_progress(
                100, "Generating markdown files..."), 0)
        files = generate_markdown_files(books, output_folder, self.field_names)

        msg = (f"Done! Generated {len(files)} file(s) with {len(books)} books."
               f"\n\nOutput: {output_folder}")
        Clock.schedule_once(lambda dt: self._show_result(msg, success=True), 0)

    def _update_progress(self, pct: float, text: str):
        # Show percentage and text together
        # Override: this method is always called from Clock callbacks, so direct assignment is safe here. The base class version wraps in Clock.schedule_once, which would be redundant in this case
        self.progress_label.text = f"[{pct:.0f}%] {text}"

    def _show_result(self, message: str, success: bool = False):
        self.generate_btn.disabled = False
        self.progress_label.text   = ""
        if success:
            self.status_label.text  = "Catalog generated successfully!"
            self.status_label.color = self.BG_FONT_COLOR
            self._show_info("Success", message)
        else:
            self.status_label.text  = message
            self.status_label.color = self.BG_FONT_COLOR
            if "Error" in message:
                self._show_error(message)
                
# =============================================================================
# Main
# =============================================================================

def main():
    """Main entry point
    In case of startup issues the app is automatically started again
    """
    try:
        Libiry2GoApp().run()
    except Exception as e:
        print(f"Startup error: {e}")
        print("Restarting...")
        # Try to start again
        try:
            Libiry2GoApp().run()
        except Exception as e2:
            print(f"Failed to restart: {e2}")
            raise

if __name__ == '__main__':
    main()