"""
Calibre2Libiry - Converteer Calibre metadata.opf en cover bestanden naar Libiry formaat.

Calibre slaat metadata op in metadata.opf bestanden per boek-folder.
Libiry verwacht metadata in {boekbestand}.opf formaat (bijv. book.pdf.opf).

Calibre slaat covers op als cover.jpg/cover.png in de boek-folder.
Libiry verwacht covers in {boekbestand}.jpg formaat (bijv. book.pdf.jpg).

Dit script hernoemt alle metadata.opf en cover bestanden in een Calibre library naar
het Libiry formaat, zodat je bestaande tags, metadata en covers kunt gebruiken in Libiry.

Gebruik:
    python Calibre2Libiry.py                    # Opens GUI
    python Calibre2Libiry.py [calibre_path]     # CLI mode

Let op:
    - Dit script HERNOEMT bestanden (geen kopie)
    - Maak eerst een backup van je Calibre library als je onzeker bent
    - Na hernoemen werkt Calibre's metadata.opf en cover niet meer (Calibre ziet ze niet)
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


def count_files_to_convert(library_path: Path) -> tuple[int, int]:
    """Tel het aantal OPF en cover bestanden om te converteren."""
    opf_count = 0
    cover_count = 0

    # Folders met metadata.opf (Calibre style)
    for opf_path in library_path.rglob('metadata.opf'):
        opf_count += 1
        folder = opf_path.parent
        if find_cover_in_folder(folder):
            cover_count += 1

    # Standalone covers (1 ebook + 1 cover, geen opf)
    standalone_folders = find_standalone_cover_folders(library_path)
    cover_count += len(standalone_folders)

    return opf_count, cover_count


def convert_calibre_library(library_path: Path, dry_run: bool = False,
                            progress_callback=None) -> tuple[int, int, int, int, list[str]]:
    """Converteer alle metadata.opf en cover bestanden in een Calibre library."""
    opf_success = 0
    opf_skip = 0
    cover_success = 0
    cover_skip = 0
    errors = []

    # Verzamel alle te verwerken items
    opf_files = list(library_path.rglob('metadata.opf'))
    standalone_folders = find_standalone_cover_folders(library_path)
    total = len(opf_files) + len(standalone_folders)

    # === FASE 1: Folders met metadata.opf (Calibre style) ===
    for i, opf_path in enumerate(opf_files):
        if progress_callback:
            progress_callback(i + 1, total, opf_path.parent.name)

        folder = opf_path.parent
        ebook = find_ebook_in_folder(folder)

        if ebook is None:
            # Geen ebook in folder - gewoon overslaan zonder foutmelding
            opf_skip += 1
            continue

        # === OPF hernoemen ===
        new_opf_name = ebook.name + '.opf'
        new_opf_path = folder / new_opf_name

        if new_opf_path.exists():
            opf_skip += 1
        elif not dry_run:
            try:
                opf_path.rename(new_opf_path)
                opf_success += 1
            except Exception as e:
                errors.append(f"OPF fout: {e}")
        else:
            opf_success += 1

        # === Cover hernoemen ===
        cover = find_cover_in_folder(folder)
        if cover:
            new_cover_name = ebook.name + cover.suffix.lower()
            new_cover_path = folder / new_cover_name

            if new_cover_path.exists():
                cover_skip += 1
            elif not dry_run:
                try:
                    cover.rename(new_cover_path)
                    cover_success += 1
                except Exception as e:
                    errors.append(f"Cover fout: {e}")
            else:
                cover_success += 1

    # === FASE 2: Standalone covers (1 ebook + 1 cover, geen opf) ===
    for i, folder in enumerate(standalone_folders):
        if progress_callback:
            progress_callback(len(opf_files) + i + 1, total, folder.name)

        ebook = find_ebook_in_folder(folder)
        cover = find_cover_in_folder(folder)

        if ebook and cover:
            new_cover_name = ebook.name + cover.suffix.lower()
            new_cover_path = folder / new_cover_name

            if new_cover_path.exists():
                cover_skip += 1
            elif not dry_run:
                try:
                    cover.rename(new_cover_path)
                    cover_success += 1
                except Exception as e:
                    errors.append(f"Cover fout: {e}")
            else:
                cover_success += 1

    return opf_success, opf_skip, cover_success, cover_skip, errors


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

        subtitle = ttk.Label(main, text="Convert Calibre metadata & covers to Libiry format",
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
            text="Warning: This permanently renames files. Calibre will no longer find them.",
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

        self.preview_btn = self._create_button(btn_frame, "Preview", self._preview)
        self.preview_btn.pack(side='left', padx=5)

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

    def _preview(self):
        library_path = self._validate()
        if not library_path:
            return

        self.preview_btn.config(state='disabled')
        self.convert_btn.config(state='disabled')

        thread = threading.Thread(target=self._preview_thread, args=(library_path,))
        thread.daemon = True
        thread.start()

    def _preview_thread(self, library_path: Path):
        def progress(current, total, name):
            pct = (current / total) * 100
            self.root.after(0, lambda: self._update_progress(pct, f"Scanning: {name[:30]}..."))

        opf_ok, opf_skip, cover_ok, cover_skip, errors = convert_calibre_library(
            library_path, dry_run=True, progress_callback=progress)

        msg = f"Preview: {opf_ok} OPF + {cover_ok} covers would be renamed"
        if opf_skip + cover_skip > 0:
            msg += f"\nSkipped: {opf_skip} OPF + {cover_skip} covers (already exist)"

        self.root.after(0, lambda: self._show_result(msg, preview=True))

    def _convert(self):
        library_path = self._validate()
        if not library_path:
            return

        # Confirm
        if not messagebox.askyesno("Confirm",
            "This will permanently rename files.\n\n"
            "Calibre will no longer find metadata.opf and cover files.\n\n"
            "Continue?"):
            return

        self.preview_btn.config(state='disabled')
        self.convert_btn.config(state='disabled')

        thread = threading.Thread(target=self._convert_thread, args=(library_path,))
        thread.daemon = True
        thread.start()

    def _convert_thread(self, library_path: Path):
        def progress(current, total, name):
            pct = (current / total) * 100
            self.root.after(0, lambda: self._update_progress(pct, f"Converting: {name[:30]}..."))

        opf_ok, opf_skip, cover_ok, cover_skip, errors = convert_calibre_library(
            library_path, dry_run=False, progress_callback=progress)

        msg = f"Done! Renamed {opf_ok} OPF files and {cover_ok} covers."
        if errors:
            msg += f"\n\n{len(errors)} errors occurred."

        self.root.after(0, lambda: self._show_result(msg, success=True))

    def _update_progress(self, pct: float, text: str):
        # Toon percentage en tekst samen
        self.progress_label.config(text=f"[{pct:.0f}%] {text}")

    def _show_result(self, message: str, success: bool = False, preview: bool = False):
        self.preview_btn.config(state='normal')
        self.convert_btn.config(state='normal')
        self.progress_label.config(text="")

        if success:
            self.status_label.config(text="Conversion complete!", foreground=self.BG_FONT_COLOR)
            messagebox.showinfo("Success", message)
        elif preview:
            self.status_label.config(text=message, foreground=self.BG_FONT_COLOR)
        else:
            self.status_label.config(text=message, foreground=self.BG_FONT_COLOR)

    def run(self):
        self.root.mainloop()


# =============================================================================
# CLI Mode (backwards compatibility)
# =============================================================================

def cli_main(library_path: Path):
    """Command-line interface."""
    print("=" * 60)
    print("  Calibre2Libiry - Metadata & Cover Converter")
    print("=" * 60)
    print()

    if not library_path.exists():
        print(f"Error: Path does not exist: {library_path}")
        sys.exit(1)

    opf_count, cover_count = count_files_to_convert(library_path)
    total = opf_count + cover_count
    if total == 0:
        print("No metadata.opf files or standalone covers found.")
        sys.exit(0)

    print(f"Found: {total} files to convert ({opf_count} metadata + {cover_count} covers)")
    print()

    # Preview
    print("Preview:")
    print("-" * 40)

    def progress(current, total, name):
        pct = (current / total) * 100
        print(f"\r[{pct:5.1f}%] {name[:40]:<40}", end='', flush=True)

    opf_ok, opf_skip, cover_ok, cover_skip, errors = convert_calibre_library(
        library_path, dry_run=True, progress_callback=progress)
    print()
    print("-" * 40)
    print(f"Would rename: {opf_ok} OPF, {cover_ok} covers")
    if opf_skip + cover_skip > 0:
        print(f"Would skip: {opf_skip} OPF, {cover_skip} covers")
    print()

    confirm = input("Continue with rename? (y/n): ").strip().lower()
    if confirm not in ('y', 'yes', 'j', 'ja'):
        print("Cancelled.")
        sys.exit(0)

    print()
    print("Converting...")
    opf_ok, opf_skip, cover_ok, cover_skip, errors = convert_calibre_library(
        library_path, dry_run=False, progress_callback=progress)
    print()
    print("=" * 60)
    print(f"Done! {opf_ok} OPF + {cover_ok} covers renamed.")
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
