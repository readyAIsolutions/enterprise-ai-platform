#!/usr/bin/env bash
# Capture Steam store assets on your X11 desktop.
#
# What it does:
#   1. Launches Lumen and auto-captures the Library, Workshop, and Settings
#      tabs as PNGs (via `lumen --screenshot`).
#   2. Records a ~30s trailer of the live wallpaper on the primary monitor
#      using ffmpeg x11grab (so buyers see the wallpaper actually moving).
#
# Requirements: Lumen installed + runnable (`lumen` on PATH or use the venv:
#   ~/Desktop/apps/lumen/.venv/bin/python -m lumen), ffmpeg, xrandr.
#
# Usage:  bash capture_assets.sh [OUT_DIR]
set -euo pipefail

OUT="${1:-store_assets}"
LUMEN_BIN="${LUMEN_BIN:-lumen}"

mkdir -p "$OUT"

echo ">> [1/2] GUI screenshots (lumen --screenshot)"
"$LUMEN_BIN" --screenshot "$OUT"
ls -1 "$OUT"/*.png 2>/dev/null || echo "   (no PNGs — is Lumen runnable on this display?)"

echo ">> [2/2] 30s live-wallpaper trailer (ffmpeg x11grab)"
# Find the primary monitor offset/size via xrandr.
PRIMARY=$(xrandr --current | awk '/ connected/{p=0} /\*/*/{print}' | head -1)
# Fallback: parse the line containing 'primary'
LINE=$(xrandr --current | grep -m1 primary || xrandr --current | grep -m1 connected)
GEO=$(echo "$LINE" | grep -oE '[0-9]+x[0-9]+\+[0-9]+\+[0-9]+' | head -1)
W=${GEO%%x*}; rest=${GEO#*x}; H=${rest%%+*}; off=${GEO#*+}; OX=${off%%+*}; OY=${off#*+}
echo "   primary geometry: ${W}x${H} @ +${OX},+${OY}"
ffmpeg -y -loglevel error -f x11grab -r 30 \
  -s "${W}x${H}" -i ":0.0+${OX},${OY}" -t 30 \
  -c:v libx264 -pix_fmt yuv420p -crf 18 "$OUT/trailer.mp4"
echo "   wrote $OUT/trailer.mp4"

echo "DONE. Upload to Steamworks:"
echo "  - 01_library.png, 02_store.png, 03_settings.png, 04_wallpaper.png"
echo "  - trailer.mp4"
