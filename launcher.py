#!/usr/bin/env python3
"""launcher.py — Cross-platform entry point for all Libiry apps
Called by the platform-specific wrapper scripts (bat / sh)

Usage: python launcher.py <app_name> [--debug] [extra args...]

app_name values:
    main            -> main.py
    libiry2go       -> libiry2go.py
    calibre2libiry  -> Calibre2Libiry.py
    align_book_data -> Align_book_data.py

Flags:
    --debug   Keep stderr on the console and show full tracebacks.
              Without this flag, stderr is redirected to <app>.log so that
              Kivy startup messages do not cause console flicker on Windows.

Extra args (after app_name and --debug) are forwarded to the app as
sys.argv[1:], which enables CLI modes in the satellite apps.

Design notes
------------
Why runpy.run_path instead of importlib.import_module?
    The satellite scripts are designed to run as top-level __main__ scripts,
    not as importable packages. runpy.run_path sets __name__ = '__main__'
    inside the module, so each app's `if __name__ == '__main__':` guard fires
    correctly without any changes to the app files

Why os.execv for venv bootstrap?
    os.execv replaces the current process rather than spawning a subprocess.
    This avoids an extra Python process sitting around after launch and ensures
    the app sees a clean process environment with the correct sys.executable.
    os.execv is available on all platforms Python supports (including Windows)

Why redirect stderr to a log file?
    In GUI mode on Windows, pythonw.exe suppresses the console window, but
    Kivy still writes verbose startup messages to stderr. If stderr is not
    redirected, these messages are silently lost. Writing them to a .log file
    next to launcher.py means the user can inspect them when something goes
    wrong, without ever seeing a console window during normal use"""

import os
import sys
import runpy
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Absolute path of the libiry project folder (where launcher.py lives).
_ROOT = Path(__file__).parent.resolve()

# Map lowercase app identifiers to the actual Python filenames (without .py).
_APPS: dict[str, str] = {
    'main':                           'main',
    'libiry2go':                      'libiry2go',
    'calibre2libiry':                 'Calibre2Libiry',
    'align_book_data':                'Align_book_data',
}

# ---------------------------------------------------------------------------
# Venv bootstrap
# ---------------------------------------------------------------------------

def _in_venv() -> bool:
    """Return True if the active interpreter is inside a virtualenv"""
    return (
        hasattr(sys, 'real_prefix')
        or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix)
    )

def _bootstrap_venv() -> None:
    """If not running inside the project venv, re-exec this script with the venv Python. This makes `python launcher.py ...` work even when the caller forgot to activate the venv — the bat/sh wrappers call the venv Python directly, so this path is normally only hit on direct terminal use"""
    if _in_venv():
        return

    venv_py = (
        _ROOT / 'venv' / 'Scripts' / 'python.exe'
        if sys.platform == 'win32'
        else _ROOT / 'venv' / 'bin' / 'python'
    )

    if not venv_py.exists():
        # Print to stderr then exit; we cannot import anything useful yet.
        sys.exit(
            f"ERROR: Virtual environment not found.\n"
            f"Expected: {venv_py}\n\n"
            f"Create it with:\n"
            f"  python -m venv venv\n"
            f"  venv\\Scripts\\pip install kivy plyer   (Windows)\n"
            f"  venv/bin/pip install kivy plyer        (macOS / Linux)"
        )

    # Replace this process image with the venv Python running the same script.
    # Does not return on success.
    os.execv(str(venv_py), [str(venv_py)] + sys.argv)

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def _parse_args() -> tuple[str, bool, list[str]]:
    """Parse sys.argv[1:] and return (app_name, debug, extra_args)
    --debug may appear at any position in the argument list"""
    args = list(sys.argv[1:])
    debug = '--debug' in args
    if debug:
        args.remove('--debug')
    app_name = args[0].lower() if args else ''
    extra_args = args[1:]
    return app_name, debug, extra_args


# ---------------------------------------------------------------------------
# Stderr logging
# ---------------------------------------------------------------------------

def _redirect_stderr_to_log(app_name: str) -> None:
    """In non-debug (GUI) mode redirect stderr to <app_name>.log in the project root. This prevents Kivy startup noise from causing a console window to appear on Windows and gives the user a file to inspect when errors occur"""
    log_path = _ROOT / f'{app_name}.log'
    try:
        # line-buffered so partial messages are flushed on crash
        sys.stderr = open(log_path, 'w', encoding='utf-8', buffering=1)
    except OSError:
        pass  # cannot open log — leave stderr unchanged, not fatal

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    # Step 1: Ensure we are running inside the project venv
    _bootstrap_venv()

    # Step 2: Add project root to sys.path so that satellite apps can resolve `from core.libiry_style import ...` regardless of where launcher.py is invoked from
    if str(_ROOT) not in sys.path:
        sys.path.insert(0, str(_ROOT))

    # Step 3: Parse launcher arguments
    app_name, debug, extra_args = _parse_args()

    if not app_name:
        print(
            f"Usage: python launcher.py <app> [--debug] [args...]\n"
            f"Apps:  {', '.join(_APPS)}",
            file=sys.stderr,
        )
        sys.exit(1)

    if app_name not in _APPS:
        print(
            f"Unknown app '{app_name}'.\n"
            f"Known apps: {', '.join(_APPS)}",
            file=sys.stderr,
        )
        sys.exit(1)

    # Step 4: In non-debug mode, capture stderr in a log file
    if not debug:
        _redirect_stderr_to_log(app_name)

    # Step 5: Set sys.argv so the app module sees its own filename as argv[0] and any CLI arguments as argv[1:]
    module_file = _ROOT / f'{_APPS[app_name]}.py'
    sys.argv = [str(module_file)] + extra_args

    # Step 6: Run the app. runpy.run_path executes the file in a fresh namespace with __name__ == '__main__', which triggers the app's `if __name__ == '__main__':` guard without importing it as a module
    runpy.run_path(str(module_file), run_name='__main__')

if __name__ == '__main__':
    main()
