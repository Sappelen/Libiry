#!/bin/bash
# =============================================================================
# Libiry macOS run script (for development/source)
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

# Activate venv and start app
if [ -d "venv" ]; then
    source venv/bin/activate
    python main.py "$@"
else
    echo "Venv not found. Run first: ./macos/install.sh"
    exit 1
fi
