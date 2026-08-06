#!/bin/bash
# =============================================================================
# Build script for macOS - makes Libiry.app and .dmg installer
# =============================================================================
# This script:
# 1. Installs build dependencies
# 2. Converts icon to .icns format
# 3. Builds the .app bundle with PyInstaller
# 4. Creates a .dmg disk image for distribution
#
# Requirements:
# - macOS 10.15+ (Catalina or newer)
# - Python 3.10+ (via Homebrew recommended)
# - Xcode Command Line Tools: xcode-select --install
#
# Use: ./build_macos.sh (from the Libiry folder)
# =============================================================================

set -e  # Stops at first error

echo ""
echo "========================================"
echo "  Libiry macOS Build Script"
echo "========================================"
echo ""

# Check if we are in the correct folder
if [ ! -f "main.py" ]; then
    echo "ERROR: main.py not found. Run this script from the Libiry folder."
    exit 1
fi

# Check Python version
PYTHON_VERSION=$(python3 --version 2>&1 | cut -d' ' -f2 | cut -d'.' -f1,2)
echo "Python version: $PYTHON_VERSION"

# Make dist folder
mkdir -p dist/installer

# Activate venv if it exists
if [ -d "venv" ]; then
    echo "Activating virtual environment..."
    source venv/bin/activate
else
    echo "Creating virtual environment..."
    python3 -m venv venv
    source venv/bin/activate
fi

# Install build tools
echo ""
echo "[1/5] Installing build dependencies..."
pip install --upgrade pip
pip install --upgrade pyinstaller

# Install app dependencies
echo ""
echo "[2/5] Installing app dependencies..."
pip install -r requirements.txt

# Convert icon to .icns format (macOS native icon format)
echo ""
echo "[3/5] Converting icon to macOS format..."

ICON_SRC="resources/icons/Libiry.ico"
ICON_DST="resources/icons/Libiry.icns"

if [ -f "$ICON_SRC" ] && [ ! -f "$ICON_DST" ]; then
    # Maak iconset folder met alle benodigde resoluties
    ICONSET="resources/icons/Libiry.iconset"
    mkdir -p "$ICONSET"

    # Use sips (macOS native tool) to extract and resize PNG
    # Convert to PNG first
    sips -s format png "$ICON_SRC" --out "$ICONSET/icon_512x512.png" 2>/dev/null || true

    # If sips doesn't work (ico format), try with Python/PIL
    if [ ! -f "$ICONSET/icon_512x512.png" ]; then
        python3 << 'PYTHON_SCRIPT'
from PIL import Image
import os

ico_path = "resources/icons/Libiry.ico"
iconset_path = "resources/icons/Libiry.iconset"
os.makedirs(iconset_path, exist_ok=True)

# Open ico and get biggest resolution
img = Image.open(ico_path)
img = img.convert('RGBA')

# Generate all sizes needed for macOS
sizes = [16, 32, 64, 128, 256, 512, 1024]
for size in sizes:
    resized = img.resize((size, size), Image.Resampling.LANCZOS)
    if size == 1024:
        resized.save(f"{iconset_path}/icon_512x512@2x.png")
    elif size >= 32:
        resized.save(f"{iconset_path}/icon_{size}x{size}.png")
        if size <= 512:
            # @2x versie
            resized_2x = img.resize((size*2, size*2), Image.Resampling.LANCZOS)
            resized.save(f"{iconset_path}/icon_{size//2}x{size//2}@2x.png")
    else:
        resized.save(f"{iconset_path}/icon_{size}x{size}.png")

print("Icon sizes generated successfully")
PYTHON_SCRIPT
    fi

    # Convert iconset to icns
    if [ -d "$ICONSET" ]; then
        iconutil -c icns "$ICONSET" -o "$ICON_DST" 2>/dev/null || echo "Warning: iconutil failed, continuing without custom icon"
        rm -rf "$ICONSET"
    fi
fi

# Build with PyInstaller
echo ""
echo "[4/5] Building .app bundle with PyInstaller..."
echo "This may take several minutes..."
pyinstaller --clean --noconfirm linux/libiry.spec

if [ ! -d "dist/Libiry.app" ]; then
    echo ""
    echo "ERROR: Libiry.app not found in dist/"
    exit 1
fi

echo ""
echo ".app bundle created successfully!"

# Maak DMG disk image
echo ""
echo "[5/5] Creating DMG installer..."

DMG_NAME="Libiry-Installer.dmg"
DMG_PATH="dist/installer/$DMG_NAME"

# Delete old DMG if there is one
rm -f "$DMG_PATH"

# Make temp folder 
DMG_TEMP="dist/dmg_temp"
rm -rf "$DMG_TEMP"
mkdir -p "$DMG_TEMP"

# Copy the app
cp -R "dist/Libiry.app" "$DMG_TEMP/"

# Make a symbolic link to Applications (standard macOS installer pattern)
ln -s /Applications "$DMG_TEMP/Applications"

# Make the DMG
# hdiutil is the macOS native tool for disk images
hdiutil create -volname "Libiry" \
    -srcfolder "$DMG_TEMP" \
    -ov -format UDZO \
    "$DMG_PATH"

# Cleanup
rm -rf "$DMG_TEMP"

echo ""
echo "========================================"
echo "  BUILD COMPLETE!"
echo "========================================"
echo ""
echo "DMG Installer: $DMG_PATH"
echo "App Bundle:    dist/Libiry.app"
echo ""
echo "To install: Open the DMG and drag Libiry to Applications"
echo ""
