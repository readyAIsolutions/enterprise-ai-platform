# Build script `set -u` unbound-variable trap (Lumen 2026-07-12)

## Symptom
A PyQt6/PyQt6-WebEngine AppImage build passes `--version OK` and
`white-screen-safe OK`, writes the artifact, then dies at the OFFSCREEN
import-smoke with:

    build_appimage.sh: line 224: LD_LIBRARY_PATH: unbound variable

The artifact mtime does NOT change (appimagetool writes only at the end, and
the smoke runs after it). So the file looks unchanged and the failure is easy
to misread as "the build didn't run."

## Root cause
The build script runs under `set -euo pipefail`. The import-smoke runs the
extracted artifact's python DIRECTLY (not via AppRun) as a command-prefix
assignment:

    if LD_LIBRARY_PATH="$EXROOT/usr/lib/python$PVER/site-packages/PyQt6/Qt6/lib:${LD_LIBRARY_PATH}" \
       QT_QPA_PLATFORM_PLUGIN_PATH=".../PyQt6/Qt6/plugins" \
       QT_QPA_PLATFORM=offscreen "$EXROOT/usr/bin/python3" -c "import ..." ; then

That `${LD_LIBRARY_PATH}` is expanded by the BUILD script's own shell. Under
`set -u` an unset variable is a fatal error. A clean agent/CI shell often has
no `LD_LIBRARY_PATH` exported, so the build aborts. On an interactive desktop
it may "work" only because that shell happens to have it set — a silent
portability landmine.

## Fix
Use the empty default `${LD_LIBRARY_PATH:-}` in the smoke command-prefix
(REQUIRED under `set -u`):

    if LD_LIBRARY_PATH="$EXROOT/usr/lib/python$PVER/site-packages/PyQt6/Qt6/lib:${LD_LIBRARY_PATH:-}" \
       QT_QPA_PLATFORM_PLUGIN_PATH="$EXROOT/usr/lib/python$PVER/site-packages/PyQt6/Qt6/plugins" \
       QT_QPA_PLATFORM=offscreen "$EXROOT/usr/bin/python3" -c \
        "import lumen, lumen.app, lumen.ui.main_window, lumen.steam.steamworks, lumen.gallery_export; print('IMPORTS OK', lumen.__version__)" 2>/dev/null; then

Defensively, also write the `AppRun` generation line with `:-` (so a future
edit that un-escapes the heredoc var can't reintroduce the trap):

    export LD_LIBRARY_PATH="\${HERE}/usr/lib/python$PVER/site-packages/PyQt6/Qt6/lib:\${HERE}/usr/lib:\${LD_LIBRARY_PATH:-}"

Inside an UNQUOTED `<<EOF` heredoc the leading `\` keeps `$HERE`/`$LD_LIBRARY_PATH`
literal in the written AppRun; AppRun itself only has `set -e`, so the `:-`
there is defensive, not required — but the smoke prefix above IS required.

## Diagnostic that reveals the real error
The smoke hid its own trace with `2>/dev/null`. To see the actual failure,
run the extracted artifact's import with stderr visible:

    OUT=/path/to/app.AppImage
    "$OUT" --appimage-extract >/dev/null 2>&1
    EXROOT="$(pwd)/squashfs-root"
    QT_QPA_PLATFORM=offscreen \
      LD_LIBRARY_PATH="$EXROOT/usr/lib/python3.14/site-packages/PyQt6/Qt6/lib" \
      "$EXROOT/usr/bin/python3" -c "import lumen, lumen.app, lumen.ui.main_window, lumen.steam.steamworks, lumen.gallery_export" 2>&1 | head -40
    rm -rf squashfs-root

The first real error is usually `ImportError: libQt6WebChannel.so.6: cannot open
shared object file` (the Qt6/lib path bug) — NOT the set -u error. Fix the path
first, then the `:-` hardening, then the smoke turns green.
