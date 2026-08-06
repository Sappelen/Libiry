#!/bin/bash
# =============================================================================
# Build script for Linux - makes AppImage
# =============================================================================
# This script:

# 1. Installs build dependencies
# 2. Builds the executable with PyInstaller
# 3. Creates an AppImage for universal Linux distribution
#

# Why AppImage:
# - Works on all Linux distributions (Ubuntu, Fedora, Arch, etc.)
# - No root privileges required for installation
# - One file, download and run
# - Alternative: .deb/.rpm are distro-specific
#

# Requirements:
# - Ubuntu 20.04+ or similar
# - Python 3.10+
# - appimagetool (downloaded automatically)
#
# Usage: ./build_linux.sh (from the Library folder)
# =============================================================================

set -e  # Stops at first error

echo ""
echo "========================================"
echo "  Libiry Linux Build Script"
echo "========================================"
echo ""

# Check if we are in the correct folder
if [ ! -f "main.py" ]; then
    echo "ERROR: main.py not found. Run this script from the Libiry folder."
    exit 1
fi

# Detect architecture
ARCH=$(uname -m)
echo "Architecture: $ARCH"

# Make dist folder
mkdir -p dist/installer

# Install system dependencies (Debian/Ubuntu)
echo ""
echo "[1/6] Checking system dependencies..."

if command -v apt-get &> /dev/null; then
    echo "Debian/Ubuntu detected, installing dependencies..."
    sudo apt-get update
    sudo apt-get install -y \
        python3-pip \
        python3-venv \
        libgl1-mesa-dev \
        libgles2-mesa-dev \
        libsdl2-dev \
        libsdl2-image-dev \
        libsdl2-mixer-dev \
        libsdl2-ttf-dev \
        libmtdev-dev \
        libffi-dev \
        fuse \
        wget
elif command -v dnf &> /dev/null; then
    echo "Fedora/RHEL detected, installing dependencies..."
    sudo dnf install -y \
        python3-pip \
        python3-virtualenv \
        mesa-libGL-devel \
        SDL2-devel \
        SDL2_image-devel \
        SDL2_mixer-devel \
        SDL2_ttf-devel \
        fuse \
        wget
elif command -v pacman &> /dev/null; then
    echo "Arch Linux detected, installing dependencies..."
    sudo pacman -S --noconfirm \
        python-pip \
        python-virtualenv \
        mesa \
        sdl2 \
        sdl2_image \
        sdl2_mixer \
        sdl2_ttf \
        fuse2 \
        wget
fi

# Activate or make venv
if [ -d "venv" ]; then
    echo "Activating virtual environment..."
    source venv/bin/activate
else
    echo "Creating virtual environment..."
    python3 -m venv venv
    source venv/bin/activate
fi

# Install Python build tools
echo ""
echo "[2/6] Installing build dependencies..."
pip install --upgrade pip
pip install --upgrade pyinstaller

# Install app dependencies
echo ""
echo "[3/6] Installing app dependencies..."
pip install -r requirements.txt

# Download appimagetool if it doesn't exist
echo ""
echo "[4/6] Setting up AppImage tools..."

APPIMAGETOOL="appimagetool-${ARCH}.AppImage"
if [ ! -f "$APPIMAGETOOL" ]; then
    echo "Downloading appimagetool..."
    wget -q "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-${ARCH}.AppImage" -O "$APPIMAGETOOL"
    chmod +x "$APPIMAGETOOL"
fi

# Build with PyInstaller
echo ""
echo "[5/6] Building executable with PyInstaller..."
echo "This may take several minutes..."

# Linux uses the same spec as macOS
pyinstaller --clean --noconfirm linux/libiry.spec 

if [ ! -d "dist/Libiry" ]; then
    echo ""
    echo "ERROR: dist/Libiry folder not found"
    exit 1
fi

echo ""
echo "PyInstaller build successful!"

# Make AppImage
echo ""
echo "[6/6] Creating AppImage..."

APPDIR="dist/Libiry.AppDir"
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin"
mkdir -p "$APPDIR/usr/share/icons/hicolor/256x256/apps"
mkdir -p "$APPDIR/usr/share/applications"

# Kopy PyInstaller output
cp -R dist/Libiry/* "$APPDIR/usr/bin/"

# Make desktop entry
cat > "$APPDIR/libiry.desktop" << 'DESKTOP'
[Desktop Entry]
Type=Application
Name=Libiry
Comment=E-book library manager
Exec=Libiry
Icon=libiry
Categories=Office;Viewer;
Terminal=false
DESKTOP

# Kopy to usr/share/applications too
cp "$APPDIR/libiry.desktop" "$APPDIR/usr/share/applications/"

# Convert and copy icon
# Try with PIL first, then with ImageMagick
if [ -f "resources/icons/Libiry.ico" ]; then
    python3 << 'PYTHON_SCRIPT' || true
from PIL import Image
img = Image.open("resources/icons/Libiry.ico")
img = img.convert('RGBA')
img = img.resize((256, 256), Image.Resampling.LANCZOS)
img.save("dist/Libiry.AppDir/libiry.png")
img.save("dist/Libiry.AppDir/usr/share/icons/hicolor/256x256/apps/libiry.png")
PYTHON_SCRIPT
fi

# Fallback: if icon conversion failed, make a placeholder
if [ ! -f "$APPDIR/libiry.png" ]; then
    echo "Warning: Could not convert icon, using placeholder"
    # Maak een simpele placeholder icon met ImageMagick als beschikbaar
    if command -v convert &> /dev/null; then
        convert -size 256x256 xc:#7F4050 -fill white -gravity center \
            -pointsize 72 -annotate 0 "L" "$APPDIR/libiry.png"
        cp "$APPDIR/libiry.png" "$APPDIR/usr/share/icons/hicolor/256x256/apps/libiry.png"
    fi
fi

# Make AppRun script (entry point for AppImage)
cat > "$APPDIR/AppRun" << 'APPRUN'
#!/bin/bash
# AppImage entry point
SELF=$(readlink -f "$0")
HERE=${SELF%/*}
export PATH="${HERE}/usr/bin:${PATH}"
export LD_LIBRARY_PATH="${HERE}/usr/lib:${LD_LIBRARY_PATH}"
exec "${HERE}/usr/bin/Libiry" "$@"
APPRUN
chmod +x "$APPDIR/AppRun"

# Build the AppImage
APPIMAGE_NAME="Libiry-${ARCH}.AppImage"
FUSE_AVAILABLE=1

# Check if FUSE is available (neccesary for appimagetool)
if ! fusermount -V &> /dev/null; then
    echo "Note: FUSE not available, using --appimage-extract-and-run"
    FUSE_AVAILABLE=0
fi

if [ $FUSE_AVAILABLE -eq 1 ]; then
    ./"$APPIMAGETOOL" "$APPDIR" "dist/installer/$APPIMAGE_NAME"
else
    ./"$APPIMAGETOOL" --appimage-extract-and-run "$APPDIR" "dist/installer/$APPIMAGE_NAME"
fi

# Cleanup
rm -rf "$APPDIR"

echo ""
echo "========================================"
echo "  BUILD COMPLETE!"
echo "========================================"
echo ""
echo "AppImage: dist/installer/$APPIMAGE_NAME"
echo ""
echo "To run: chmod +x dist/installer/$APPIMAGE_NAME && ./dist/installer/$APPIMAGE_NAME"
echo "To install: Move the AppImage to ~/Applications or /opt"
echo ""
