#!/bin/bash
# Verify wallpaper engine and desktop icons are working correctly

set -e

BUILD_DIR="$HOME/Dev/linux-wallpaperengine/build"
DESKTOP_SCRIPT="$BUILD_DIR/desktop-icons.py"
ENGINE_BIN="$BUILD_DIR/output/linux-wallpaperengine"

# Check engine binary exists
if [ ! -f "$ENGINE_BIN" ]; then
    echo "ERROR: Wallpaper engine binary not found at $ENGINE_BIN"
    exit 1
fi

# Check desktop script syntax
if ! python3 -m py_compile "$DESKTOP_SCRIPT" 2>/dev/null; then
    echo "ERROR: desktop-icons.py has syntax errors"
    exit 1
fi

# Check running processes
if ! pgrep -f "desktop-icons.py" > /dev/null; then
    echo "WARNING: desktop-icons.py not running"
fi

if ! pgrep -f "linux-wallpaperengine" > /dev/null; then
    echo "WARNING: linux-wallpaperengine not running"
fi

echo "Wallpaper system check passed"