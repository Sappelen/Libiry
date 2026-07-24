"""Open files in default system application"""

from pathlib import Path
import os
import sys
import subprocess

def open_in_default_app(filepath: Path) -> bool:
    """Opens a file in the system's default application
    Args: filepath: Path to the file to open
    Returns True if successful, False otherwise"""
    if not filepath.exists():
        return False

    try:
        if sys.platform == 'win32':
            # Open book with Windows default app
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
    """Get MIME type for a file based on extension"""
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