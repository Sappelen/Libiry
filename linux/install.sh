#!/bin/bash
# =============================================================================
# Libiry Linux installatie script (voor development/source)
# =============================================================================
# Dit script installeert dependencies om Libiry vanaf broncode te draaien.
# Voor eindgebruikers is de AppImage eenvoudiger.
#
# Gebruik: ./install.sh
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "========================================"
echo "  Libiry Linux Installatie"
echo "========================================"
echo ""

# Check Python
PYTHON_CMD=""
for cmd in python3.11 python3.10 python3; do
    if command -v $cmd &> /dev/null; then
        PYTHON_CMD=$cmd
        break
    fi
done

if [ -z "$PYTHON_CMD" ]; then
    echo "FOUT: Python 3.10+ is vereist"
    echo ""
    echo "Installeer met:"
    echo "  Ubuntu/Debian: sudo apt install python3 python3-venv python3-pip"
    echo "  Fedora:        sudo dnf install python3 python3-pip"
    echo "  Arch:          sudo pacman -S python python-pip"
    exit 1
fi

echo "Python gevonden: $PYTHON_CMD"
echo ""

# Maak venv aan
cd "$PROJECT_ROOT"
if [ ! -d "venv" ]; then
    echo ">> Virtual environment aanmaken..."
    $PYTHON_CMD -m venv venv
fi

# Activeer venv
source venv/bin/activate

# Upgrade pip
echo ">> Pip upgraden..."
pip install --upgrade pip

# Installeer dependencies
echo ""
echo ">> Dependencies installeren..."
pip install -r requirements.txt

echo ""
echo "========================================"
echo "  Installatie voltooid!"
echo "========================================"
echo ""
echo "Libiry starten met: ./run.sh"
echo ""
