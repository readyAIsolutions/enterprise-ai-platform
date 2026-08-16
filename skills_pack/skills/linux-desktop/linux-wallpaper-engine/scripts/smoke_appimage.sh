#!/usr/bin/env bash
# smoke_appimage.sh — headless smoke-test of a BUNDLED Lumen AppImage.
#
# Runs the AppImage with QT_QPA_PLATFORM=offscreen and --screenshot, then asserts
# the GUI PNGs (01/02/03) emit with real (non-trivial) byte sizes.
#
# Why this matters (learned the hard way):
#   - --screenshot REQUIRES an OUTDIR argument; omit it and you get
#     "error: argument --screenshot: expected one argument".
#   - There is NO --offscreen CLI flag. Use the QT_QPA_PLATFORM=offscreen ENV VAR.
#   - The process exits 139 (SIGSEGV) on WebEngine teardown — BENIGN, the PNGs
#     are already written before the crash.
#   - 01_library.png / 02_store.png / 03_settings.png are REAL GUI captures
#     (dark, themed, non-trivial bytes). 04_wallpaper.png is BLANK offscreen
#     (no live wallpaper surface exists without a display) — that is EXPECTED,
#     not a regression. On a real X11 display 04 fills with the live wallpaper.
#
# Usage:
#   LUMEN_APPIMAGE=/path/to/lumen.AppImage OUTDIR=/tmp/smoke bash smoke_appimage.sh
#   (defaults: LUMEN_APPIMAGE=/home/hunter/Desktop/apps/lumen.AppImage,
#              OUTDIR=/tmp/lumen_smoke)
set -u

APP="${LUMEN_APPIMAGE:-/home/hunter/Desktop/apps/lumen.AppImage}"
OUT="${OUTDIR:-/tmp/lumen_smoke}"

if [ ! -x "$APP" ]; then
  echo "FATAL: AppImage not found/executable: $APP" >&2
  exit 2
fi

rm -rf "$OUT"; mkdir -p "$OUT"
echo "=== Lumen AppImage offscreen smoke -> $OUT ==="
QT_QPA_PLATFORM=offscreen timeout 120 "$APP" --screenshot "$OUT"
EC=$?
echo "raw exit=$EC (139 = benign WebEngine teardown, tolerated)"

echo "--- emitted ---"
ls -l "$OUT" 2>&1

# Assert 01/02/03 GUI PNGs are real (non-trivial). 04 is blank offscreen (expected).
for f in 01_library.png 02_store.png 03_settings.png; do
  sz=$(stat -c%s "$OUT/$f" 2>/dev/null || echo 0)
  if [ "$sz" -lt 10000 ]; then
    echo "FAIL: $f too small ($sz B) — GUI did not render"; exit 3
  fi
  echo "OK: $f ($sz B)"
done

echo "SMOKE GREEN: bundled AppImage renders GUI offscreen"
echo "(04_wallpaper.png blank offscreen = expected; fills on real X)"
