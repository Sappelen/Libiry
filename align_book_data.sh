#!/usr/bin/env bash
# align_book_data.sh — Launch the metadata tool (macOS / Linux)
# No arguments : GUI mode   — detached from terminal (nohup + &)
# --debug      : Debug mode — foreground, console stays open
# Other args   : CLI mode   — forwarded to the script, foreground
cd "$(dirname "$0")"
PYTHON="venv/bin/python"
[ -f "$PYTHON" ] || PYTHON="python3"
if [ $# -eq 0 ]; then
    nohup "$PYTHON" launcher.py align_book_data > /dev/null 2>&1 &
else
    "$PYTHON" launcher.py align_book_data "$@"
fi
