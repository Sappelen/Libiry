#!/bin/bash
# =============================================================================
# Libiry macOS installation script (for development/source)
# =============================================================================
# This script installs dependencies to run Libiry from source.
# For end users, the .app or .dmg is easier.
#
# Usage: ./install.sh
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "========================================"
echo "  Libiry macOS Installation"
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
    echo "ERROR: Python 3.10+ is required"
    echo ""
    echo "Install with:"
    echo "  brew install python@3.11"
    exit 1
fi

echo "Python found: $PYTHON_CMD"
echo ""

# Create venv
cd "$PROJECT_ROOT"
if [ ! -d "venv" ]; then
    echo ">> Creating virtual environment..."
    $PYTHON_CMD -m venv venv
fi

# Activate venv
source venv/bin/activate

# Upgrade pip
echo ">> Upgrading pip..."
pip install --upgrade pip

# Install dependencies
echo ""
echo ">> Installing dependencies..."
pip install -r requirements.txt

echo ""
echo "========================================"
echo "  Installation complete!"
echo "========================================"
echo ""
echo "Run Libiry with: ./macos/run.sh"
echo ""
