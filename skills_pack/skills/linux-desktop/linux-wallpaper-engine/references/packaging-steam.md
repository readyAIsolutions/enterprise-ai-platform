# Packaging & Shipping a Linux Wallpaper App (Steam-ready)

## Dependencies
- PyQt6 + PyQt6-WebEngine (web/WebGL surfaces)
- python-xlib (X11 desktop-layer; optional on Wayland)
- python-mpv + system `libmpv2` (video wallpapers)
- Pillow, requests
- For Workshop publishing: `steamworkspy` (dev build works without it)

## AppImage (manual venv-bundle + appimagetool — PROVEN, do not use linuxdeploy)
linuxdeploy-qt cannot locate PyQt6 installed inside a venv, so the manual method
is the reliable path. Full reusable builder: `scripts/build_appimage.sh`.

Steps:
1. Build a throwaway clean venv, `pip install PyQt6-WebEngine python-mpv
   steamworkspy Pillow requests python-xlib`, then `pip install .`
   (**non-editable** — `pip install -e .` leaves a source redirect that breaks
   the image once the source moves).
2. Assemble `AppDir/`:
   - `usr/bin/python3` ← copy of `/usr/bin/python3.14`
   - `usr/lib/python3.14` ← `cp -rL $BV/lib/python3.14` (dereferences the venv
     symlink, copying stdlib + real site-packages)
   - `usr/lib/libmpv.so.2` ← copy from `/usr/lib/x86_64-linux-gnu/`
   - `AppRun`, `<app>.desktop`, `<app>.png`
3. `AppRun` sets `LD_LIBRARY_PATH` (libmpv), `PYTHONPATH`,
   `QT_QPA_PLATFORM_PLUGIN_PATH`, `QTWEBENGINE_DISABLE_SANDBOX=1`, then execs
   `python3 -m lumen`.
4. `appimagetool AppDir out.AppImage` (download `appimagetool-x86_64.AppImage`
   from AppImageKit/continuous; libfuse required at runtime to mount).
5. Verify: `timeout 14 out.AppImage --minimized` — log should show
   `Applied <name> -> DisplayPort-0`.

Note: `python3.14` is NOT linked to `libpython`, so libpython need not be
bundled. Strip `__pycache__`, pip/setuptools, `test/` to shrink (~234 MB
squashed for Lumen).

## Flatpak
Manifest on `org.kde.Platform` 6.6 + `org.freedesktop.Sdk.Extension.python311`.
Install deps into `/app`, set `PYTHONPATH`, `command: lumen`.
finish-args need `--socket=x11`, `--socket=pulseaudio`, `--device=all`,
`--filesystem=home`, `--share=network`.

## Steam
1. Create a Steam "Software" app; note its App ID.
2. Put the id in `steam_appid.txt` (placeholder `480`) and in `APP_ID` in the
   steamworks wrapper.
3. Use `steamworkspy`: `load_steamworks()` → `STEAMWORKS(app_id)`.
   - `Workshop().enumerate_subscribed_items()` → list
   - `Workshop().create_item(...)` → publish
   - `Workshop().subscribe(item_id)` → download
4. Launch option `lumen --minimized` so wallpapers render on boot while the
   window stays hidden.
5. Store assets: GUI screenshots + a 30s wallpaper trailer. Lead with the GUI.

## Niche note
Wallpaper Engine has no first-party Linux client — a polished Linux-native
engine owns that market. Price as a one-time DRM-free purchase.
