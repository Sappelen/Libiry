#!/bin/bash
# =============================================================================
# Maak Android icons vanuit de bestaande Libiry.ico
# =============================================================================
# Vereist: ImageMagick (convert command)
#   Ubuntu/Debian: sudo apt install imagemagick
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
ICONS_DIR="$PROJECT_ROOT/resources/icons"

echo "Android icons maken..."

# Check ImageMagick
if ! command -v convert &> /dev/null; then
    echo "FOUT: ImageMagick is niet geinstalleerd"
    echo "Installeer met: sudo apt install imagemagick"
    exit 1
fi

# App icon (512x512)
echo ">> libiry_android.png (512x512)..."
convert "$ICONS_DIR/Libiry.ico[0]" -resize 512x512 -background none -gravity center -extent 512x512 "$ICONS_DIR/libiry_android.png"

# Presplash (1080x1920 met centered logo)
echo ">> libiry_presplash.png (1080x1920)..."
convert -size 1080x1920 xc:white \
    \( "$ICONS_DIR/Libiry.ico[0]" -resize 256x256 \) \
    -gravity center -composite \
    "$ICONS_DIR/libiry_presplash.png"

echo ""
echo "Klaar! Icons aangemaakt in: $ICONS_DIR"
ls -la "$ICONS_DIR"/libiry_*.png
