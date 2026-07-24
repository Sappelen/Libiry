#!/usr/bin/env bash
# calibre2libiry.sh — Launch Calibre2Libiry (macOS / Linux).
# No arguments : GUI mode   — detached from terminal (nohup + &).
# --debug      : Debug mode — foreground, console stays open.
# Other args   : CLI mode   — forwarded to Calibre2Libiry.py, foreground.
cd "$(dirname "$0")"
PYTHON="venv/bin/python"
[ -f "$PYTHON" ] || PYTHON="python3"
if [ $# -eq 0 ]; then
    nohup "$PYTHON" launcher.py calibre2libiry > /dev/null 2>&1 &
else
    "$PYTHON" launcher.py calibre2libiry "$@"
fi
