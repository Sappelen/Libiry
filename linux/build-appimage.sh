#!/bin/bash
# =============================================================================
# Build script voor Libiry Linux AppImage
# =============================================================================
# Dit script:
# 1. Installeert dependencies in een venv
# 2. Bouwt de app met PyInstaller
# 3. Maakt er een AppImage van
#
# Vereisten:
# - Python 3.10+ (Kivy ondersteunt 3.12 nog niet volledig op Linux)
# - appimagetool (wordt automatisch gedownload indien nodig)
#
# Gebruik: ./build-appimage.sh
# =============================================================================

set -e  # Stop bij errors

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BUILD_DIR="$PROJECT_ROOT/build-linux"
APPDIR="$BUILD_DIR/Libiry.AppDir"

echo "========================================"
echo "  Libiry AppImage Builder"
echo "========================================"
echo ""
echo "Project root: $PROJECT_ROOT"
echo "Build dir: $BUILD_DIR"
echo ""

# Cleanup vorige build
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"

# Check Python versie
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
    echo "FOUT: Python 3.10 of 3.11 is vereist (Kivy Linux support)"
    echo "Installeer met: sudo apt install python3.11 python3.11-venv"
    exit 1
fi

echo "Gebruik Python: $PYTHON_CMD ($($PYTHON_CMD --version))"
echo ""

# Maak virtual environment
echo ">> Virtual environment aanmaken..."
$PYTHON_CMD -m venv "$BUILD_DIR/venv"
source "$BUILD_DIR/venv/bin/activate"

# Upgrade pip
pip install --upgrade pip

# Installeer dependencies
echo ""
echo ">> Dependencies installeren..."
pip install -r "$PROJECT_ROOT/requirements.txt"
pip install pyinstaller

# Bouw met PyInstaller
echo ""
echo ">> PyInstaller build..."
cd "$PROJECT_ROOT"
pyinstaller linux/libiry.spec --distpath "$BUILD_DIR/dist" --workpath "$BUILD_DIR/work"

# Maak AppDir structuur
echo ""
echo ">> AppDir structuur maken..."
mkdir -p "$APPDIR/usr/bin"
mkdir -p "$APPDIR/usr/share/applications"
mkdir -p "$APPDIR/usr/share/icons/hicolor/256x256/apps"

# Kopieer PyInstaller output naar AppDir
cp -r "$BUILD_DIR/dist/Libiry/"* "$APPDIR/usr/bin/"

# Kopieer desktop file
cp "$SCRIPT_DIR/Libiry.desktop" "$APPDIR/"
cp "$SCRIPT_DIR/Libiry.desktop" "$APPDIR/usr/share/applications/"

# Kopieer icon (converteer ICO naar PNG indien nodig)
if command -v convert &> /dev/null; then
    convert "$PROJECT_ROOT/resources/icons/Libiry.ico[0]" -resize 256x256 "$APPDIR/libiry.png"
else
    # Fallback: gebruik book.png als icon
    cp "$PROJECT_ROOT/resources/book.png" "$APPDIR/libiry.png"
fi
cp "$APPDIR/libiry.png" "$APPDIR/usr/share/icons/hicolor/256x256/apps/"

# Maak AppRun script
cat > "$APPDIR/AppRun" << 'EOF'
#!/bin/bash
SELF=$(readlink -f "$0")
HERE=${SELF%/*}
export PATH="${HERE}/usr/bin:${PATH}"
export LD_LIBRARY_PATH="${HERE}/usr/bin:${LD_LIBRARY_PATH}"
exec "${HERE}/usr/bin/Libiry" "$@"
EOF
chmod +x "$APPDIR/AppRun"

# Download appimagetool indien nodig
APPIMAGETOOL="$BUILD_DIR/appimagetool"
if [ ! -f "$APPIMAGETOOL" ]; then
    echo ""
    echo ">> appimagetool downloaden..."
    wget -q "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage" -O "$APPIMAGETOOL"
    chmod +x "$APPIMAGETOOL"
fi

# Bouw AppImage
echo ""
echo ">> AppImage bouwen..."
cd "$BUILD_DIR"
ARCH=x86_64 "$APPIMAGETOOL" "$APPDIR" "Libiry-x86_64.AppImage"

# Klaar
echo ""
echo "========================================"
echo "  Build voltooid!"
echo "========================================"
echo ""
echo "AppImage: $BUILD_DIR/Libiry-x86_64.AppImage"
echo ""
echo "Testen:"
echo "  chmod +x Libiry-x86_64.AppImage"
echo "  ./Libiry-x86_64.AppImage"
echo ""
