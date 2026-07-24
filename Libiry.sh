#!/usr/bin/env bash
# run.sh — Launch the main Libiry application (macOS / Linux).
# No arguments : GUI mode   — detached from terminal (nohup + &).
# --debug      : Debug mode — foreground, console stays open.
cd "$(dirname "$0")"
PYTHON="venv/bin/python"
[ -f "$PYTHON" ] || PYTHON="python3"
if [ $# -eq 0 ]; then
    nohup "$PYTHON" launcher.py main > /dev/null 2>&1 &
else
    "$PYTHON" launcher.py main "$@"
fi
