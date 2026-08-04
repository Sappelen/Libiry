#!/usr/bin/env bash
# Libiry installer for Debian/Ubuntu-based Linux systems
set -e

INSTALL_DIR="/opt/Libiry"
REPO_URL="https://github.com/Sappelen/Libiry.git"
BIN_LINK="/usr/local/bin/libiry"
DESKTOP_DIR="$HOME/.local/share/applications"

echo "==============================="
echo "  Libiry Installation"
echo "==============================="
echo

# Check Python 3
if ! command -v python3 &>/dev/null; then
    echo "ERROR: Python 3 is not installed. Please install Python 3.11 or 3.12."
    exit 1
fi
echo "Found $(python3 --version)"

# System dependencies
echo
echo "[1/5] Installing system dependencies..."
sudo apt-get install -y \
    python3-dev python3-venv git \
    libsdl2-dev libsdl2-image-dev libsdl2-mixer-dev libsdl2-ttf-dev \
    unrar

# Clone or update
echo
echo "[2/5] Downloading Libiry..."
if [ -d "$INSTALL_DIR/.git" ]; then
    echo "Existing installation found — updating..."
    git -C "$INSTALL_DIR" pull origin master
else
    sudo git clone "$REPO_URL" "$INSTALL_DIR"
    sudo chown -R "$USER:$USER" "$INSTALL_DIR"
fi

# Python environment
echo
echo "[3/5] Setting up Python environment..."
cd "$INSTALL_DIR"
python3 -m venv venv
venv/bin/pip install --upgrade pip --quiet
venv/bin/pip install -r requirements.txt --quiet

# Command-line launcher
echo
echo "[4/5] Installing command-line launcher..."
sudo ln -sf "$INSTALL_DIR/Libiry.sh" "$BIN_LINK"
# Desktop entry + icon
echo
echo "[5/5] Installing desktop entry..."
mkdir -p "$DESKTOP_DIR"
sed "s|Exec=Libiry|Exec=$INSTALL_DIR/Libiry.sh|" \
    "$INSTALL_DIR/linux/Libiry.desktop" \
    > "$DESKTOP_DIR/Libiry.desktop"
if [ -f "$INSTALL_DIR/resources/icons/Libiry.png" ]; then
    sudo cp "$INSTALL_DIR/resources/icons/Libiry.png" /usr/share/pixmaps/libiry.png
    mkdir -p "$HOME/.local/share/icons/hicolor/256x256/apps"
    cp "$INSTALL_DIR/resources/icons/Libiry.png" "$HOME/.local/share/icons/hicolor/256x256/apps/libiry.png"
fi

update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true

echo
echo "==============================="
echo "  Installation complete!"
echo "==============================="
echo
echo "Launch from terminal:  libiry"
echo "Or find Libiry in your applications menu."
echo