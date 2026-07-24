#!/usr/bin/env bash
# libiry2go.sh — Launch Libiry2Go (macOS / Linux).
# No arguments : GUI mode   — detached from terminal (nohup + &).
# --debug      : Debug mode — foreground, console stays open.
# Other args   : CLI mode   — forwarded to libiry2go.py, foreground.
cd "$(dirname "$0")"
PYTHON="venv/bin/python"
[ -f "$PYTHON" ] || PYTHON="python3"
if [ $# -eq 0 ]; then
    nohup "$PYTHON" launcher.py libiry2go > /dev/null 2>&1 &
else
    "$PYTHON" launcher.py libiry2go "$@"
fi
