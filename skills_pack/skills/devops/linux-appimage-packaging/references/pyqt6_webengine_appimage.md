# PyQt6 / PyQt6-WebEngine AppImage native-lib path fix

Reference recipe for the `libQt6WebChannel.so.6` ImportError that red-lighted the
LUMEN AppImage build (2026-07-12). Symptom, root cause, fix, and the offscreen
import-smoke that proves the bundle actually imports.

## Symptom
The AppImage builds and `--version` is fine, but a headless import of the whole
shipped tree fails:

```
Traceback (most recent call last):
  ...
    from PyQt6.QtWebEngineWidgets import QWebEngineView
ImportError: libQt6WebChannel.so.6: cannot open shared object file: No such file or directory
```

`--version` passes because it exits before any `QApplication`/WebEngine import.
The failure only shows when you import `lumen.app` / `lumen.ui.main_window` /
`lumen.steam.steamworks` / `lumen.gallery_export` (anything that pulls
`PyQt6.QtWebEngineWidgets`).

## Root cause
The PyQt6 Python modules live in `site-packages/PyQt6/`, but their native
`.so` companions (libQt6WebChannel.so.6, libQt6WebEngineCore.so.6,
libQt6Quick.so.6, libQt6Qml.so.6, libQt6WebChannelQuick.so.6, ...) live in
`site-packages/PyQt6/Qt6/lib/`. Modern PyQt6 wheels use the **`Qt6/`** directory;
the legacy `PyQt6/Qt/` path no longer exists. If `AppRun` only exports
`LD_LIBRARY_PATH="$HERE/usr/lib"` and
`QT_QPA_PLATFORM_PLUGIN_PATH=.../PyQt6/Qt/plugins`, the loader finds the Python
modules but cannot resolve their native libs (and the plugin path is wrong too).
In a dev venv the import works because the wheel's RPATH resolves `Qt6/lib`
relative to the module; that RPATH is not honored the same way once the tree is
relocated into the AppImage's `usr/lib/python$PVER/site-packages`.

## Fix (AppRun generator)
Point both env vars at the real `Qt6` locations. Required when you SPLIT
site-packages into `usr/lib/python$PVER/site-packages` (the split-layout build).
The whole-`.venv` B4 approach does NOT need this because Qt resolves under
`.venv` automatically.

```bash
# in AppRun, after HERE is known and PVER computed:
export LD_LIBRARY_PATH="$HERE/usr/lib/python$PVER/site-packages/PyQt6/Qt6/lib:$HERE/usr/lib:${LD_LIBRARY_PATH:-}"
export PYTHONPATH="$HERE/usr/lib/python$PVER/site-packages"
export QT_QPA_PLATFORM_PLUGIN_PATH="$HERE/usr/lib/python$PVER/site-packages/PyQt6/Qt6/plugins"
exec "$HERE/usr/bin/python3" -m lumen "$@"
```

Verify the dirs actually exist in your wheel before trusting the path:
```bash
find site-packages/PyQt6 -maxdepth 2 -type d -name lib      # expect .../PyQt6/Qt6/lib
find site-packages/PyQt6 -maxdepth 2 -type d -name plugins  # expect .../PyQt6/Qt6/plugins
```
If your wheel is old enough to still use `PyQt6/Qt/` (not `Qt6/`), use that path
instead — check, don't assume.

## Fix (offscreen import-smoke against the artifact)
The build's self-verify extracts the AppImage and runs the artifact python
DIRECTLY (not via AppRun), so AppRun's env is absent. Export the same vars inline
or the smoke fails identically:

```bash
SMOKE_DIR="$(mktemp -d)"
( cd "$SMOKE_DIR" && "$OUT" --appimage-extract >/dev/null 2>&1 )
EXROOT="$SMOKE_DIR/squashfs-root"
if [ -x "$EXROOT/usr/bin/python3" ]; then
  if LD_LIBRARY_PATH="$EXROOT/usr/lib/python$PVER/site-packages/PyQt6/Qt6/lib:${LD_LIBRARY_PATH}" \
     QT_QPA_PLATFORM_PLUGIN_PATH="$EXROOT/usr/lib/python$PVER/site-packages/PyQt6/Qt6/plugins" \
     QT_QPA_PLATFORM=offscreen \
     "$EXROOT/usr/bin/python3" -c \
       "import lumen, lumen.app, lumen.ui.main_window, lumen.steam.steamworks, lumen.gallery_export; print('IMPORTS OK', lumen.__version__)" 2>&1; then
    echo "import smoke OK"
  fi
fi
rm -rf "$SMOKE_DIR"
```

Drop `2>/dev/null` from the python invocation during diagnosis — it hides the
exact ImportError (that's how the bad path surfaced here).

## After the lib-path fix
More transitive libs may surface on first real launch (libGL/libEGL from the host
for WebEngine GPU init, libnss3/libnspr for WebEngine network). Those are HOST
system libs and are expected to be present on the target desktop; they are NOT
part of the bundle. The offscreen smoke does not exercise GPU/net, so a passing
smoke proves the bundle's Python+Qt native deps are complete even if a real
launch later needs host GL/nss.
