#!/bin/bash
# =============================================================================
# Libiry Linux run script (voor development/source)
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

# Activeer venv en start app
if [ -d "venv" ]; then
    source venv/bin/activate
    python main.py "$@"
else
    echo "Venv niet gevonden. Voer eerst uit: ./linux/install.sh"
    exit 1
fi
