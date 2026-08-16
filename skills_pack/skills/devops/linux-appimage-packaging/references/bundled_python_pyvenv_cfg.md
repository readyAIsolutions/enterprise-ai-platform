# Bundled interpreter NEEDS pyvenv.cfg (PyQt6/Python AppImage, split layout)

## Symptom
Build completes, `--version` prints, a `web.py`/source grep passes, but the
offscreen **import smoke** fails with either:

```
ModuleNotFoundError: No module named 'PyQt6.QtWebChannel'
```

...or a traceback that imports YOUR package from a SOURCE path instead of the
bundle:

```
File "/home/hunter/Desktop/apps/<app>/<app>/app.py", line 41, in <module>
    from <app>.wallpaper.engine import WallpaperEngine
```

even though `PyQt6/QtWebChannel.abi3.so` IS present in the extracted
artifact's `site-packages`, and `import <app>` from the venv passes.

## Root cause
The split-layout recipe copies only the python BINARY:

```bash
cp "$(readlink -f $VENV/bin/python3)" AppDir/usr/bin/python3
chmod +x AppDir/usr/bin/python3
```

No `pyvenv.cfg` is written beside it. Without the venv marker file, CPython
resolves `sys.prefix` to its *compiled-in* (HOST) prefix and uses the HOST
`site-packages`. So:

- `import <app>` finds the host's **editable** install -> the SOURCE tree
  (traceback shows the source path, not the bundled copy).
- `PyQt6.QtWebChannel` is resolved from the HOST PyQt6, which may be incomplete
  or missing. The bundled PyQt6 is COMPLETE but never consulted.

`--version` passes because argparse's version action imports almost nothing; the
grep passes because the source file is correct; only a real `import` of the full
shipped tree exposes the host fallback.

## Fix
Write a correct `pyvenv.cfg` next to the bundled binary (in the build script,
right after copying the binary):

```bash
cat > "$APPDIR/usr/bin/pyvenv.cfg" <<EOF
home = /usr/bin
include-system-site-packages = false
version = $PVER
EOF
```

`home` is the base-python bin (conventional; not used for stdlib location).
`include-system-site-packages = false` is the critical line — it stops the
interpreter from appending the HOST site-packages. With the marker present,
`sys.prefix` = `$APPDIR/usr` and `site-packages` = the BUNDLED one, so
`import <app>` and `PyQt6.QtWebChannel` both resolve from the shipped copy.

## Diagnostic — always surface the real error
The smoke must NOT use `2>/dev/null`:

```bash
LD_LIBRARY_PATH="$EXROOT/usr/lib/python$PVER/site-packages/PyQt6/Qt6/lib:${LD_LIBRARY_PATH:-}" \
QT_QPA_PLATFORM_PLUGIN_PATH="$EXROOT/usr/lib/python$PVER/site-packages/PyQt6/Qt6/plugins" \
QT_QPA_PLATFORM=offscreen \
"$EXROOT/usr/bin/python3" -c "import <app>, <app>.app, <app>.ui.main_window; print('IMPORTS OK')" 2>&1 | head -40
```

Reading the error:
- **SOURCE-tree path in the traceback** => host fallback (pyvenv.cfg missing).
- `libQt6WebChannel.so.6: cannot open shared object file` => Qt6 lib path not on
  `LD_LIBRARY_PATH` (see `references/pyqt6_webengine_appimage.md`).
- `LD_LIBRARY_PATH: unbound variable` => `set -u` + bare `${LD_LIBRARY_PATH}` in
  the smoke (see `references/build_script_setu_unbound_var.md`).

## Note on `--appimage-extract` path
`appimage-extract` writes `squashfs-root` RELATIVE to the CWD where it runs. If
you `cd` into a temp dir first, reference the AppImage by ABSOLUTE path:

```bash
EX=$(mktemp -d); ( cd "$EX" && /abs/path/to/app.AppImage --appimage-extract >/dev/null 2>&1 ); EXR="$EX/squashfs-root"
```

A relative `./app.AppImage` after `cd` fails silently (file not found) and leaves
no `squashfs-root` — which looks like "asset missing" but is actually a failed
extraction. Verify the dir exists before asserting on its contents.

## Applies to
Split-layout bundles (binary + `usr/lib/python$PVER`), NOT the whole-`.venv` (B4)
approach where `AppRun` points at `.venv/bin/python` and the venv's own
`pyvenv.cfg` ships inside `.venv`.
