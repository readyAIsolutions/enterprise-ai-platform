#!/usr/bin/env bash
# FUSE-free, display-free verification of a Lumen AppImage.
#
# Extracts the image (no FUSE mount needed) and proves the bundle is complete
# + importable by running:
#   1. AppRun --version          (prints "Lumen X.Y.Z")
#   2. AppRun --reset-safe       (exercises the bundled BootGuard)
#   3. a bundled-python import check across every heavy submodule
#
# This needs NEITHER FUSE NOR an X display, so it is the cheapest GREEN proof
# on a headless build box or when LO's DISPLAY is busy. It is deterministic —
# unlike the offscreen `--screenshot` smoke it does not SIGSEGV on teardown.
#
# Usage: bash verify_appimage_headless.sh [path/to/lumen.AppImage]
set -euo pipefail

APPIMAGE="${1:-/home/hunter/Desktop/apps/lumen.AppImage}"
[ -x "$APPIMAGE" ] || { echo "MISSING: $APPIMAGE"; exit 2; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
cd "$WORK"

echo ">> extracting $APPIMAGE (no FUSE needed)"
"$APPIMAGE" --appimage-extract >/dev/null 2>&1
ROOT="$WORK/squashfs-root"
[ -d "$ROOT" ] || { echo "EXTRACT FAILED"; exit 3; }

PY="$ROOT/usr/bin/python3"
SP="$ROOT/usr/lib/python3.14/site-packages"
LIB="$ROOT/usr/lib"
[ -x "$PY" ] || { echo "BUNDLED PYTHON MISSING"; exit 4; }

echo ">> (1) AppRun --version"
"$ROOT/AppRun" --version | head -1

echo ">> (2) AppRun --reset-safe (exercises bundled BootGuard)"
"$ROOT/AppRun" --reset-safe | head -1

echo ">> (3) bundled import check (all heavy submodules)"
if PYTHONPATH="$SP" LD_LIBRARY_PATH="$LIB" "$PY" -c \
    "import lumen, lumen.app, lumen.wallpaper.engine, lumen.ui.main_window, lumen.steam.steamworks, lumen.gallery_export; print('IMPORTS OK', lumen.__version__)"; then
  echo "ALL HEADLESS CHECKS PASSED"
else
  echo "IMPORT CHECK FAILED"
  exit 5
fi
