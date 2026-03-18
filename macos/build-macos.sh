#!/bin/bash
# =============================================================================
# Build script for Libiry macOS .app and .dmg
# =============================================================================
# This script:
# 1. Creates a virtual environment
# 2. Installs dependencies
# 3. Builds the .app bundle with PyInstaller
# 4. Optionally creates a .dmg for distribution
#
# Requirements:
# - macOS 10.15+ (Catalina or newer)
# - Python 3.10 or 3.11
# - Xcode Command Line Tools: xcode-select --install
#
# Usage: ./build-macos.sh [--dmg]
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BUILD_DIR="$PROJECT_ROOT/build-macos"
CREATE_DMG=false

# Check for --dmg flag
if [[ "$1" == "--dmg" ]]; then
    CREATE_DMG=true
fi

echo "========================================"
echo "  Libiry macOS Builder"
echo "========================================"
echo ""
echo "Project root: $PROJECT_ROOT"
echo "Build dir: $BUILD_DIR"
echo "Create DMG: $CREATE_DMG"
echo ""

# Check if running on macOS
if [[ "$OSTYPE" != "darwin"* ]]; then
    echo "ERROR: This script must be run on macOS"
    exit 1
fi

# Check Python version
PYTHON_CMD=""
for cmd in python3.11 python3.10 python3; do
    if command -v $cmd &> /dev/null; then
        version=$($cmd -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
        major=$(echo $version | cut -d. -f1)
        minor=$(echo $version | cut -d. -f2)
        if [ "$major" -eq 3 ] && [ "$minor" -ge 10 ] && [ "$minor" -le 11 ]; then
            PYTHON_CMD=$cmd
            break
        fi
    fi
done

if [ -z "$PYTHON_CMD" ]; then
    echo "ERROR: Python 3.10 or 3.11 is required"
    echo "Install with: brew install python@3.11"
    exit 1
fi

echo "Using Python: $PYTHON_CMD ($($PYTHON_CMD --version))"
echo ""

# Clean previous build
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"

# Create virtual environment
echo ">> Creating virtual environment..."
$PYTHON_CMD -m venv "$BUILD_DIR/venv"
source "$BUILD_DIR/venv/bin/activate"

# Upgrade pip
pip install --upgrade pip

# Install dependencies
echo ""
echo ">> Installing dependencies..."
pip install -r "$PROJECT_ROOT/requirements.txt"
pip install pyinstaller

# Check/create .icns icon
ICNS_FILE="$PROJECT_ROOT/resources/icons/Libiry.icns"
if [ ! -f "$ICNS_FILE" ]; then
    echo ""
    echo ">> Creating macOS icon (.icns)..."
    if [ -f "$PROJECT_ROOT/resources/icons/Libiry.ico" ]; then
        # Create iconset from ICO
        ICONSET="$BUILD_DIR/Libiry.iconset"
        mkdir -p "$ICONSET"

        # Use sips to convert (built into macOS)
        sips -s format png "$PROJECT_ROOT/resources/icons/Libiry.ico" --out "$BUILD_DIR/icon_512.png" 2>/dev/null || true

        if [ -f "$BUILD_DIR/icon_512.png" ]; then
            # Create required sizes
            sips -z 16 16 "$BUILD_DIR/icon_512.png" --out "$ICONSET/icon_16x16.png"
            sips -z 32 32 "$BUILD_DIR/icon_512.png" --out "$ICONSET/icon_16x16@2x.png"
            sips -z 32 32 "$BUILD_DIR/icon_512.png" --out "$ICONSET/icon_32x32.png"
            sips -z 64 64 "$BUILD_DIR/icon_512.png" --out "$ICONSET/icon_32x32@2x.png"
            sips -z 128 128 "$BUILD_DIR/icon_512.png" --out "$ICONSET/icon_128x128.png"
            sips -z 256 256 "$BUILD_DIR/icon_512.png" --out "$ICONSET/icon_128x128@2x.png"
            sips -z 256 256 "$BUILD_DIR/icon_512.png" --out "$ICONSET/icon_256x256.png"
            sips -z 512 512 "$BUILD_DIR/icon_512.png" --out "$ICONSET/icon_256x256@2x.png"
            sips -z 512 512 "$BUILD_DIR/icon_512.png" --out "$ICONSET/icon_512x512.png"
            cp "$BUILD_DIR/icon_512.png" "$ICONSET/icon_512x512@2x.png"

            # Create .icns
            iconutil -c icns "$ICONSET" -o "$ICNS_FILE"
            echo "   Created: $ICNS_FILE"
        else
            echo "   WARNING: Could not convert icon, using default"
        fi
    fi
fi

# Build with PyInstaller
echo ""
echo ">> Building with PyInstaller..."
cd "$PROJECT_ROOT"
pyinstaller macos/libiry.spec \
    --distpath "$BUILD_DIR/dist" \
    --workpath "$BUILD_DIR/work" \
    --noconfirm

# Check if .app was created
APP_PATH="$BUILD_DIR/dist/Libiry.app"
if [ ! -d "$APP_PATH" ]; then
    echo "ERROR: .app bundle was not created"
    exit 1
fi

echo ""
echo ">> .app bundle created: $APP_PATH"

# Create DMG if requested
if [ "$CREATE_DMG" = true ]; then
    echo ""
    echo ">> Creating DMG..."

    DMG_DIR="$BUILD_DIR/dmg"
    mkdir -p "$DMG_DIR"

    # Copy .app to DMG directory
    cp -r "$APP_PATH" "$DMG_DIR/"

    # Create symbolic link to Applications
    ln -s /Applications "$DMG_DIR/Applications"

    # Create DMG
    DMG_PATH="$BUILD_DIR/Libiry.dmg"
    hdiutil create -volname "Libiry" \
        -srcfolder "$DMG_DIR" \
        -ov -format UDZO \
        "$DMG_PATH"

    echo "   Created: $DMG_PATH"
fi

# Done
echo ""
echo "========================================"
echo "  Build complete!"
echo "========================================"
echo ""
echo "App bundle: $APP_PATH"
if [ "$CREATE_DMG" = true ]; then
    echo "DMG file:   $BUILD_DIR/Libiry.dmg"
fi
echo ""
echo "To test:"
echo "  open \"$APP_PATH\""
echo ""
echo "To install:"
echo "  Drag Libiry.app to /Applications"
echo ""
