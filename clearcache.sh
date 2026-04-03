#!/bin/bash
# Libiry Cache Cleaner - Linux/macOS
# Verwijdert de Libiry cache folder (~/.libiry/cache)

CACHE_DIR="$HOME/.libiry/cache"

if [ -d "$CACHE_DIR" ]; then
    echo "Clearing Libiry cache: $CACHE_DIR"
    rm -rf "$CACHE_DIR"
    echo "Cache cleared."
else
    echo "No cache found at $CACHE_DIR"
fi
