"""Open files in default system application."""

from pathlib import Path
import os
import sys
import subprocess


def _find_calibre_viewer() -> str:
    """Find Calibre E-book Viewer executable on Windows."""
    if sys.platform != 'win32':
        return ''

    # Common Calibre installation paths
    possible_paths = [
        Path(os.environ.get('PROGRAMFILES', '')) / 'Calibre2' / 'ebook-viewer.exe',
        Path(os.environ.get('PROGRAMFILES(X86)', '')) / 'Calibre2' / 'ebook-viewer.exe',
        Path(os.environ.get('LOCALAPPDATA', '')) / 'Calibre2' / 'ebook-viewer.exe',
        Path.home() / 'AppData' / 'Local' / 'Calibre2' / 'ebook-viewer.exe',
    ]

    for path in possible_paths:
        if path.exists():
            return str(path)

    return ''


def _is_obsidian_default_for_md() -> bool:
    """Check if Obsidian is the default app for .md files via Windows registry."""
    if sys.platform != 'win32':
        return False

    try:
        import winreg

        # Check user choice first
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                               r'Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts\.md\UserChoice') as key:
                prog_id = winreg.QueryValueEx(key, 'ProgId')[0]
                if 'obsidian' in prog_id.lower():
                    return True
        except (FileNotFoundError, OSError):
            pass

        # Check class registration
        try:
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r'.md') as key:
                prog_id = winreg.QueryValueEx(key, '')[0]
                if 'obsidian' in prog_id.lower():
                    return True
        except (FileNotFoundError, OSError):
            pass

    except Exception:
        pass

    return False


def _get_epub_open_command() -> tuple:
    """Get the shell open command for .epub files from Windows registry.

    Returns:
        Tuple of (executable_path, full_command_template) or ('', '') if not found.
    """
    if sys.platform != 'win32':
        return ('', '')

    try:
        import winreg

        # Get the ProgId for .epub
        prog_id = None

        # Check user choice first
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                               r'Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts\.epub\UserChoice') as key:
                prog_id = winreg.QueryValueEx(key, 'ProgId')[0]
        except (FileNotFoundError, OSError):
            pass

        # Fallback to class registration
        if not prog_id:
            try:
                with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r'.epub') as key:
                    prog_id = winreg.QueryValueEx(key, '')[0]
            except (FileNotFoundError, OSError):
                pass

        if not prog_id:
            return ('', '')

        # Get the shell open command for this ProgId
        try:
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT,
                               rf'{prog_id}\shell\open\command') as key:
                command = winreg.QueryValueEx(key, '')[0]
                if command:
                    # Extract executable path
                    if command.startswith('"'):
                        end_quote = command.find('"', 1)
                        if end_quote > 0:
                            exe_path = command[1:end_quote]
                            return (exe_path, command)
                    else:
                        parts = command.split()
                        if parts:
                            return (parts[0], command)
        except (FileNotFoundError, OSError):
            pass

    except Exception:
        pass

    return ('', '')


def _is_calibre_default_for_extension(extension: str) -> bool:
    """Check if Calibre (main app, not viewer) is the default for a file extension."""
    if sys.platform != 'win32':
        return False

    try:
        import winreg
        ext = extension.lower() if extension.startswith('.') else f'.{extension.lower()}'

        # Check user choice
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                               rf'Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts\{ext}\UserChoice') as key:
                prog_id = winreg.QueryValueEx(key, 'ProgId')[0]
                # Check for Calibre main app (not ebook-viewer)
                if 'calibre' in prog_id.lower() and 'viewer' not in prog_id.lower():
                    return True
        except (FileNotFoundError, OSError):
            pass

        # Check class registration
        try:
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, ext) as key:
                prog_id = winreg.QueryValueEx(key, '')[0]
                if 'calibre' in prog_id.lower() and 'viewer' not in prog_id.lower():
                    return True
        except (FileNotFoundError, OSError):
            pass

    except Exception:
        pass

    return False


def open_in_default_app(filepath: Path) -> bool:
    """
    Open a file in the system's default application.

    Args:
        filepath: Path to the file to open

    Returns:
        True if successful, False otherwise
    """
    if not filepath.exists():
        return False

    try:
        if sys.platform == 'win32':
            suffix = filepath.suffix.lower()
            viewer = _find_calibre_viewer()

            # For any file where Calibre (main app) is default, use Calibre Viewer instead
            if viewer and _is_calibre_default_for_extension(suffix):
                subprocess.Popen([viewer, str(filepath)])
                return True

            # For .md files where Obsidian is default, use the default epub app instead
            if suffix in ('.md', '.markdown'):
                if _is_obsidian_default_for_md():
                    # Get the default epub app command
                    exe_path, command_template = _get_epub_open_command()
                    if exe_path and Path(exe_path).exists():
                        if '%1' in command_template:
                            cmd = command_template.replace('"%1"', f'"{filepath}"').replace('%1', f'"{filepath}"')
                            subprocess.Popen(cmd, shell=True)
                        else:
                            subprocess.Popen([exe_path, str(filepath)])
                        return True
                    # Fallback: try Calibre viewer
                    if viewer:
                        subprocess.Popen([viewer, str(filepath)])
                        return True

            # Fall back to Windows default
            os.startfile(str(filepath))
        elif sys.platform == 'darwin':
            # macOS
            subprocess.run(['open', str(filepath)], check=True)
        elif hasattr(sys, 'getandroidapilevel'):
            # Android - use Intent
            try:
                from android import mActivity
                from jnius import autoclass, cast

                Intent = autoclass('android.content.Intent')
                Uri = autoclass('android.net.Uri')
                File = autoclass('java.io.File')

                file = File(str(filepath))
                uri = Uri.fromFile(file)

                intent = Intent(Intent.ACTION_VIEW)
                intent.setDataAndType(uri, _get_mime_type(filepath))
                intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)

                mActivity.startActivity(intent)
                return True
            except Exception as e:
                print(f"Android open error: {e}")
                return False
        else:
            # Linux and others
            subprocess.run(['xdg-open', str(filepath)], check=True)
        return True
    except Exception as e:
        print(f"Failed to open {filepath}: {e}")
        return False


def _get_mime_type(filepath: Path) -> str:
    """Get MIME type for a file based on extension."""
    mime_types = {
        '.pdf': 'application/pdf',
        '.epub': 'application/epub+zip',
        '.mobi': 'application/x-mobipocket-ebook',
        '.azw': 'application/vnd.amazon.ebook',
        '.azw3': 'application/vnd.amazon.ebook',
        '.cbz': 'application/vnd.comicbook+zip',
        '.cbr': 'application/vnd.comicbook-rar',
        '.md': 'text/markdown',
    }
    return mime_types.get(filepath.suffix.lower(), 'application/octet-stream')


def open_folder_in_explorer(folder_path: Path) -> bool:
    """
    Open a folder in the system's file explorer.

    Args:
        folder_path: Path to the folder to open

    Returns:
        True if successful, False otherwise
    """
    if not folder_path.exists():
        return False

    try:
        if sys.platform == 'win32':
            os.startfile(str(folder_path))
        elif sys.platform == 'darwin':
            subprocess.run(['open', str(folder_path)], check=True)
        elif hasattr(sys, 'getandroidapilevel'):
            # Android - limited file browser support
            return False
        else:
            subprocess.run(['xdg-open', str(folder_path)], check=True)
        return True
    except Exception as e:
        print(f"Failed to open folder {folder_path}: {e}")
        return False


def show_in_explorer(filepath: Path) -> bool:
    """
    Show a file in the system's file explorer (select the file).

    Args:
        filepath: Path to the file to show

    Returns:
        True if successful, False otherwise
    """
    if not filepath.exists():
        return False

    try:
        if sys.platform == 'win32':
            subprocess.run(['explorer', '/select,', str(filepath)], check=True)
        elif sys.platform == 'darwin':
            subprocess.run(['open', '-R', str(filepath)], check=True)
        elif hasattr(sys, 'getandroidapilevel'):
            # Android - not supported
            return False
        else:
            # Linux - just open the containing folder
            subprocess.run(['xdg-open', str(filepath.parent)], check=True)
        return True
    except Exception as e:
        print(f"Failed to show {filepath} in explorer: {e}")
        return False
