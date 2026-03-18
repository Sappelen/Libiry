#!/bin/bash
# =============================================================================
# Build script voor macOS - maakt Libiry.app en .dmg installer
# =============================================================================
# Dit script:
# 1. Installeert build dependencies
# 2. Converteert icon naar .icns format
# 3. Bouwt de .app bundle met PyInstaller
# 4. Maakt een .dmg disk image voor distributie
#
# Vereisten:
# - macOS 10.15+ (Catalina of nieuwer)
# - Python 3.10+ (via Homebrew aanbevolen)
# - Xcode Command Line Tools: xcode-select --install
#
# Gebruik: ./build_macos.sh (vanuit de Libiry folder)
# =============================================================================

set -e  # Stop bij eerste error

echo ""
echo "========================================"
echo "  Libiry macOS Build Script"
echo "========================================"
echo ""

# Controleer of we in de juiste folder zijn
if [ ! -f "main.py" ]; then
    echo "ERROR: main.py niet gevonden. Run dit script vanuit de Libiry folder."
    exit 1
fi

# Controleer Python versie
PYTHON_VERSION=$(python3 --version 2>&1 | cut -d' ' -f2 | cut -d'.' -f1,2)
echo "Python version: $PYTHON_VERSION"

# Maak dist folder
mkdir -p dist/installer

# Activeer venv als die bestaat
if [ -d "venv" ]; then
    echo "Activating virtual environment..."
    source venv/bin/activate
else
    echo "Creating virtual environment..."
    python3 -m venv venv
    source venv/bin/activate
fi

# Installeer build tools
echo ""
echo "[1/5] Installing build dependencies..."
pip install --upgrade pip
pip install --upgrade pyinstaller

# Installeer app dependencies
echo ""
echo "[2/5] Installing app dependencies..."
pip install -r requirements.txt

# Converteer icon naar .icns format (macOS native icon formaat)
echo ""
echo "[3/5] Converting icon to macOS format..."

ICON_SRC="resources/icons/Libiry.ico"
ICON_DST="resources/icons/Libiry.icns"

if [ -f "$ICON_SRC" ] && [ ! -f "$ICON_DST" ]; then
    # Maak iconset folder met alle benodigde resoluties
    ICONSET="resources/icons/Libiry.iconset"
    mkdir -p "$ICONSET"

    # Gebruik sips (macOS native tool) om PNG te extraheren en te resizen
    # Eerst converteren naar PNG
    sips -s format png "$ICON_SRC" --out "$ICONSET/icon_512x512.png" 2>/dev/null || true

    # Als sips niet werkt (ico formaat), probeer met Python/PIL
    if [ ! -f "$ICONSET/icon_512x512.png" ]; then
        python3 << 'PYTHON_SCRIPT'
from PIL import Image
import os

ico_path = "resources/icons/Libiry.ico"
iconset_path = "resources/icons/Libiry.iconset"
os.makedirs(iconset_path, exist_ok=True)

# Open ico en pak grootste resolutie
img = Image.open(ico_path)
img = img.convert('RGBA')

# Genereer alle benodigde groottes voor macOS
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

    # Converteer iconset naar icns
    if [ -d "$ICONSET" ]; then
        iconutil -c icns "$ICONSET" -o "$ICON_DST" 2>/dev/null || echo "Warning: iconutil failed, continuing without custom icon"
        rm -rf "$ICONSET"
    fi
fi

# Bouw met PyInstaller
echo ""
echo "[4/5] Building .app bundle with PyInstaller..."
echo "This may take several minutes..."

pyinstaller --clean --noconfirm libiry_macos.spec

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

# Verwijder oude DMG als die bestaat
rm -f "$DMG_PATH"

# Maak een tijdelijke folder voor de DMG inhoud
DMG_TEMP="dist/dmg_temp"
rm -rf "$DMG_TEMP"
mkdir -p "$DMG_TEMP"

# Kopieer de app
cp -R "dist/Libiry.app" "$DMG_TEMP/"

# Maak een symbolic link naar Applications (standaard macOS installer patroon)
ln -s /Applications "$DMG_TEMP/Applications"

# Maak de DMG
# hdiutil is de macOS native tool voor disk images
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
