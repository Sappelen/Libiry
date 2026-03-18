#!/bin/bash
# =============================================================================
# Build script voor Libiry Android APK
# =============================================================================
# Dit script bouwt de Android APK met Buildozer.
#
# Vereisten:
# - Linux systeem (of WSL2 op Windows)
# - Python 3.8-3.11
# - ~10GB vrije schijfruimte (voor Android SDK/NDK)
#
# Eerste keer duurt lang (SDK/NDK download), daarna veel sneller.
#
# Gebruik: ./build-android.sh [debug|release]
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

BUILD_TYPE="${1:-debug}"

echo "========================================"
echo "  Libiry Android Builder"
echo "========================================"
echo ""
echo "Build type: $BUILD_TYPE"
echo ""

# Check of we op Linux zitten
if [[ "$OSTYPE" != "linux-gnu"* ]]; then
    echo "FOUT: Buildozer werkt alleen op Linux (of WSL2)"
    echo ""
    echo "Op Windows: gebruik WSL2 (Windows Subsystem for Linux)"
    echo "  1. Installeer WSL2: wsl --install"
    echo "  2. Open Ubuntu terminal"
    echo "  3. Navigeer naar dit project"
    echo "  4. Voer dit script uit"
    exit 1
fi

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "FOUT: Python3 is niet geinstalleerd"
    exit 1
fi

# Installeer system dependencies (Ubuntu/Debian)
echo ">> System dependencies checken..."
DEPS="git zip unzip openjdk-17-jdk autoconf libtool pkg-config zlib1g-dev libncurses5-dev libncursesw5-dev libtinfo5 cmake libffi-dev libssl-dev"
MISSING=""
for dep in $DEPS; do
    if ! dpkg -s "$dep" &> /dev/null 2>&1; then
        MISSING="$MISSING $dep"
    fi
done

if [ -n "$MISSING" ]; then
    echo "Ontbrekende packages:$MISSING"
    echo ""
    echo "Installeer met:"
    echo "  sudo apt update"
    echo "  sudo apt install$MISSING"
    exit 1
fi

# Check/installeer Buildozer
if ! command -v buildozer &> /dev/null; then
    echo ">> Buildozer installeren..."
    pip3 install --user buildozer cython
fi

# Check Android icons
if [ ! -f "../resources/icons/libiry_android.png" ]; then
    echo ""
    echo "WAARSCHUWING: Android icon ontbreekt"
    echo "Maak resources/icons/libiry_android.png (512x512 PNG)"
    echo "Buildozer zal doorgaan met default icon..."
    echo ""
fi

# Build
echo ""
echo ">> Buildozer $BUILD_TYPE build starten..."
echo "   (Eerste keer duurt 15-30 minuten voor SDK/NDK download)"
echo ""

buildozer android $BUILD_TYPE

# Output
echo ""
echo "========================================"
echo "  Build voltooid!"
echo "========================================"
echo ""
echo "APK locatie: $(ls -t bin/*.apk 2>/dev/null | head -1)"
echo ""
echo "Installeren op device (met USB debugging aan):"
echo "  adb install -r bin/*.apk"
echo ""
