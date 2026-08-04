#!/bin/bash
# Libiry Cache Cleaner - Linux/macOS
# Removes the Libiry cache folder

CACHE_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/Libiry"

if [ -d "$CACHE_DIR" ]; then
    echo "Clearing Libiry cache: $CACHE_DIR"
    rm -rf "$CACHE_DIR"
    echo "Cache cleared."
else
    echo "No cache found at $CACHE_DIR"
fi
