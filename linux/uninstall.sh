#!/usr/bin/env bash
# Libiry uninstaller

INSTALL_DIR="/opt/Libiry"
BIN_LINK="/usr/local/bin/libiry"
DESKTOP_FILE="$HOME/.local/share/applications/Libiry.desktop"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/Libiry"
CACHE_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/Libiry"

echo "==============================="
echo "  Libiry Uninstall"
echo "==============================="
echo

read -rp "Remove Libiry? This cannot be undone! (y/N) " confirm
if [[ "$confirm" != [yY] ]]; then
    echo "Cancelled."
    exit 0
fi

# App files
[ -d "$INSTALL_DIR" ] && sudo rm -rf "$INSTALL_DIR" && echo "Removed $INSTALL_DIR"

# Command-line launcher
[ -L "$BIN_LINK" ] && sudo rm "$BIN_LINK" && echo "Removed $BIN_LINK"

# Desktop entry
if [ -f "$DESKTOP_FILE" ]; then
    rm "$DESKTOP_FILE"
    update-desktop-database "$(dirname "$DESKTOP_FILE")" 2>/dev/null || true
    echo "Removed desktop entry"
fi

# Icon
[ -f /usr/share/pixmaps/libiry.png ] && sudo rm /usr/share/pixmaps/libiry.png

echo
read -rp "Also remove your settings and customizations for Libiry in $CONFIG_DIR? (y/N) " rc
[[ "$rc" == [yY] ]] && rm -rf "$CONFIG_DIR" && echo "Removed settings"

read -rp "Also remove Libiry's cover cache in $CACHE_DIR? (y/N) " rca
[[ "$rca" == [yY] ]] && rm -rf "$CACHE_DIR" && echo "Removed cache"

echo
echo "Libiry has been uninstalled."
echo