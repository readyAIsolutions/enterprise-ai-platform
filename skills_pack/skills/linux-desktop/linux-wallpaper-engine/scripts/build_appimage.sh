#!/usr/bin/env bash
# Build a distributable Lumen AppImage.
#
# Self-contained: creates a clean (non-editable) venv, installs deps, copies
# the *real* lumen package into site-packages (so the image does not depend on
# the source tree), bundles libmpv + the python interpreter, and assembles the
# AppDir with appimagetool. linuxdeploy is intentionally NOT used — it cannot
# locate a venv-bundled PyQt6.
#
# Usage:  bash build_appimage.sh
set -euo pipefail

SRC=/home/hunter/Desktop/apps/lumen
BUILD=/home/hunter/lumen-build
APPDIR="$BUILD/AppDir"
BV=/tmp/lumen-buildvenv
OUT=/home/hunter/Desktop/apps/lumen.AppImage

echo ">> cleaning $BUILD"
rm -rf "$BUILD"
mkdir -p "$APPDIR/usr/bin" "$APPDIR/usr/lib" "$BUILD"

echo ">> [1/7] clean venv + install deps (non-editable lumen)"
python3 -m venv "$BV"
# shellcheck disable=SC1091
source "$BV/bin/activate"
pip install --upgrade pip wheel setuptools >/dev/null
pip install PyQt6 PyQt6-WebEngine python-xlib python-mpv Pillow requests
pip install "$SRC"

PVER=$("$BV/bin/python3" -c 'import sys;print("%d.%d"%sys.version_info[:2])')
PYSRC=$(readlink -f "$BV/bin/python3")
echo "   python $PVER at $PYSRC"

echo ">> [2/7] interpreter + stdlib/site-packages"
cp "$PYSRC" "$APPDIR/usr/bin/python3"
chmod +x "$APPDIR/usr/bin/python3"
cp -rL "$BV/lib/python$PVER" "$APPDIR/usr/lib/python$PVER"

echo ">> [3/7] strip caches / tests / pip"
find "$APPDIR/usr/lib/python$PVER" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
rm -rf "$APPDIR/usr/lib/python$PVER/site-packages/pip" \
       "$APPDIR/usr/lib/python$PVER/site-packages/setuptools" \
       "$APPDIR/usr/lib/python$PVER/site-packages/wheel" \
       "$APPDIR/usr/lib/python$PVER/site-packages/pkg_resources" \
       "$APPDIR/usr/lib/python$PVER/test" 2>/dev/null || true

echo ">> [4/7] bundle libmpv"
if [ -f /usr/lib/x86_64-linux-gnu/libmpv.so.2 ]; then
  cp /usr/lib/x86_64-linux-gnu/libmpv.so.2 "$APPDIR/usr/lib/"
elif [ -f /usr/lib/libmpv.so.2 ]; then
  cp /usr/lib/libmpv.so.2 "$APPDIR/usr/lib/"
else
  echo "!! libmpv.so.2 not found — video wallpapers will not work in the AppImage"
fi

echo ">> [5/7] icon (bundled logo, fall back to PIL orb)"
LOGO="$SRC/lumen/ui/assets/logo.png"
if [ -f "$LOGO" ]; then
  cp "$LOGO" "$APPDIR/lumen.png"
else
  "$BV/bin/python" - "$APPDIR/lumen.png" <<'PY'
from PIL import Image, ImageDraw
import sys
W=256
img=Image.new("RGBA",(W,W),(0,0,0,0))
d=ImageDraw.Draw(img)
d.ellipse([16,16,W-16,W-16],fill=(155,123,255,255))
d.ellipse([W*0.34,W*0.34,W*0.66,W*0.66],fill=(214,196,255,255))
img.save(sys.argv[1])
PY
fi

echo ">> [6/7] .desktop + AppRun"
cp "$SRC/packaging/AppImage/lumen.desktop" "$APPDIR/lumen.desktop"
cat > "$APPDIR/AppRun" <<EOF
#!/bin/bash
set -e
HERE="\$(dirname "\$(readlink -f "\${0}")")"
export LD_LIBRARY_PATH="\${HERE}/usr/lib:\${LD_LIBRARY_PATH}"
export PYTHONPATH="\${HERE}/usr/lib/python$PVER/site-packages"
export QT_QPA_PLATFORM_PLUGIN_PATH="\${HERE}/usr/lib/python$PVER/site-packages/PyQt6/Qt/plugins"
export QTWEBENGINE_DISABLE_SANDBOX=1
exec "\${HERE}/usr/bin/python3" -m lumen "\$@"
EOF
chmod +x "$APPDIR/AppRun"

echo ">> [7/7] appimagetool -> $OUT"
if [ ! -x /tmp/appimagetool ]; then
  echo "   downloading appimagetool (needs network)"
  curl -fsSL https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage -o /tmp/appimagetool
  chmod +x /tmp/appimagetool
fi
rm -f "$OUT"
/tmp/appimagetool "$APPDIR" "$OUT"
echo "BUILD DONE"
ls -la "$OUT"
echo
echo "Verify:  timeout 14 $OUT --minimized   (watch log for 'Applied ... -> DisplayPort-0')"
