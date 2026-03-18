#!/bin/bash
# =============================================================================
# Build script voor Linux - maakt AppImage
# =============================================================================
# Dit script:
# 1. Installeert build dependencies
# 2. Bouwt de executable met PyInstaller
# 3. Maakt een AppImage voor universele Linux distributie
#
# Waarom AppImage:
# - Werkt op alle Linux distributies (Ubuntu, Fedora, Arch, etc.)
# - Geen root rechten nodig voor installatie
# - Eén bestand, download en run
# - Alternatief: .deb/.rpm zijn distro-specifiek
#
# Vereisten:
# - Ubuntu 20.04+ of vergelijkbaar
# - Python 3.10+
# - appimagetool (wordt automatisch gedownload)
#
# Gebruik: ./build_linux.sh (vanuit de Libiry folder)
# =============================================================================

set -e  # Stop bij eerste error

echo ""
echo "========================================"
echo "  Libiry Linux Build Script"
echo "========================================"
echo ""

# Controleer of we in de juiste folder zijn
if [ ! -f "main.py" ]; then
    echo "ERROR: main.py niet gevonden. Run dit script vanuit de Libiry folder."
    exit 1
fi

# Detecteer architectuur
ARCH=$(uname -m)
echo "Architecture: $ARCH"

# Maak dist folder
mkdir -p dist/installer

# Installeer system dependencies (Debian/Ubuntu)
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

# Activeer of maak venv
if [ -d "venv" ]; then
    echo "Activating virtual environment..."
    source venv/bin/activate
else
    echo "Creating virtual environment..."
    python3 -m venv venv
    source venv/bin/activate
fi

# Installeer Python build tools
echo ""
echo "[2/6] Installing build dependencies..."
pip install --upgrade pip
pip install --upgrade pyinstaller

# Installeer app dependencies
echo ""
echo "[3/6] Installing app dependencies..."
pip install -r requirements.txt

# Download appimagetool als die niet bestaat
echo ""
echo "[4/6] Setting up AppImage tools..."

APPIMAGETOOL="appimagetool-${ARCH}.AppImage"
if [ ! -f "$APPIMAGETOOL" ]; then
    echo "Downloading appimagetool..."
    wget -q "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-${ARCH}.AppImage" -O "$APPIMAGETOOL"
    chmod +x "$APPIMAGETOOL"
fi

# Bouw met PyInstaller
echo ""
echo "[5/6] Building executable with PyInstaller..."
echo "This may take several minutes..."

# Linux gebruikt dezelfde spec als macOS (zonder Windows-specifieke deps)
pyinstaller --clean --noconfirm libiry_macos.spec

if [ ! -d "dist/Libiry" ]; then
    echo ""
    echo "ERROR: dist/Libiry folder not found"
    exit 1
fi

echo ""
echo "PyInstaller build successful!"

# Maak AppImage
echo ""
echo "[6/6] Creating AppImage..."

APPDIR="dist/Libiry.AppDir"
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin"
mkdir -p "$APPDIR/usr/share/icons/hicolor/256x256/apps"
mkdir -p "$APPDIR/usr/share/applications"

# Kopieer PyInstaller output
cp -R dist/Libiry/* "$APPDIR/usr/bin/"

# Maak desktop entry
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

# Kopieer ook naar usr/share/applications
cp "$APPDIR/libiry.desktop" "$APPDIR/usr/share/applications/"

# Converteer en kopieer icon
# Probeer eerst met PIL, dan met ImageMagick
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

# Fallback: als icon conversie niet lukte, maak een placeholder
if [ ! -f "$APPDIR/libiry.png" ]; then
    echo "Warning: Could not convert icon, using placeholder"
    # Maak een simpele placeholder icon met ImageMagick als beschikbaar
    if command -v convert &> /dev/null; then
        convert -size 256x256 xc:#7F4050 -fill white -gravity center \
            -pointsize 72 -annotate 0 "L" "$APPDIR/libiry.png"
        cp "$APPDIR/libiry.png" "$APPDIR/usr/share/icons/hicolor/256x256/apps/libiry.png"
    fi
fi

# Maak AppRun script (entry point voor AppImage)
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

# Bouw de AppImage
APPIMAGE_NAME="Libiry-${ARCH}.AppImage"
FUSE_AVAILABLE=1

# Check of FUSE beschikbaar is (nodig voor appimagetool)
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
