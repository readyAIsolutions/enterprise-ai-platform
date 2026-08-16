# Lumen ship-readiness audit (real DISPLAY, read-only)

Reusable recipe for the recurring "is Lumen shippable?" question, run on LO's
rig (DISPLAY=:0.0 is live; 4 monitors, DisplayPort-0 primary). It verifies
build / AppImage / GUI / scaling / store-copy / asset pipeline WITHOUT editing
any Lumen source (bridge/report only). Re-verify a PRIOR audit's claims with
fresh commands rather than trusting the old doc — source can drift, and prior
bridge docs have shipped wrong paths.

## Verify command set
```bash
cd ~/Desktop/apps/lumen
# 1. source compiles
.venv/bin/python -m compileall -q lumen && echo COMPILE_OK
# 2. 15/15 modules import offscreen (no import/syntax blockers)
QT_QPA_PLATFORM=offscreen .venv/bin/python - <<'PY'
import importlib
mods=["lumen.app","lumen.ui.main_window","lumen.wallpaper.engine",
"lumen.steam.steamworks","lumen.importers.wallpaper_engine",
"lumen.utils.scaling","lumen.wallpaper.image","lumen.wallpaper.shader",
"lumen.wallpaper.web","lumen.wallpaper.video","lumen.ui.browser",
"lumen.ui.creator","lumen.ui.tray","lumen.utils.monitors","lumen.gallery_export"]
ok=sum(importlib.import_module(m) or 1 for m in mods)
print(f"IMPORTED {ok}/{len(mods)}")
PY
# 3. deps import (NOTE: PyQt6 has NO __version__ attr — don't test it)
.venv/bin/python -c "import PyQt6,PyQt6.QtWebEngineWidgets,mpv,PIL,requests;print('deps ok')"
ls -l /usr/lib/x86_64-linux-gnu/libmpv.so.2
# 4. AppImage artifact (sibling of source, NOT inside lumen/)
ls -l /home/hunter/Desktop/apps/lumen.AppImage
head -c3 /home/hunter/Desktop/apps/lumen.AppImage | xxd   # expect 7f45 4c
# 5. runtime smoke (repaints primary monitor wallpaper briefly)
timeout 14 /home/hunter/Desktop/apps/lumen.AppImage --minimized
#    watch log for:  "Applied <name> -> DisplayPort-0"
# 6. source-drift check: empty output => tree unchanged since the build
find lumen packaging scripts -type f -newermt "YYYY-MM-DD HH:MM" -print
# 7. real App ID blocker
cat steam_appid.txt          # 480 = placeholder
grep -n "APP_ID" lumen/steam/steamworks.py
```

## Asset pipeline reality (verified, not just claimed)
- `lumen/app.py` `main()` routes `--screenshot` -> `export_screenshots(OUTDIR)`
  and `--minimized` -> `run(minimized=...)`. Both real.
- `export_screenshots()` opens every tab and writes, into OUTDIR:
  `01_library.png` (`browser.show_library`), `02_store.png`
  (`browser.show_store`), `03_settings.png` (`browser.show_settings`),
  `04_wallpaper.png` (`QApplication.primaryScreen().grabWindow(0)`).
  All three tab methods exist in `browser.py` (show_library/store/settings)
  and are bound on `MainWindow` — capture will not AttributeError.
- `scripts/capture_assets.sh` does `[1] lumen --screenshot OUT` then
  `[2] ffmpeg x11grab` of the primary monitor geometry (parsed from xrandr)
  for ~30s -> `trailer.mp4`. Works from the AppImage too:
  `LUMEN_BIN=/home/hunter/Desktop/apps/lumen.AppImage bash scripts/capture_assets.sh ./store_assets`
- NOT executed by audits (disruptive: pops GUI, repaints wallpaper, 30s grab).
  LO runs it on his own session.

## Pitfalls / corrections discovered during audits
- **`--screenshot` bypasses the single-instance PID lock.** `export_screenshots()`
  instantiates a fresh `WallpaperEngine` + `MainWindow` WITHOUT calling
  `_single_instance()`. Running capture while the main Lumen GUI is open spawns
  a SECOND set of wallpaper surfaces stacked over `nemo-desktop` (icons hidden
  mid-run). Always quit Lumen first, or run on a clean session.
- **Image sample preview is `wallpaper.png`, NOT `preview.png`.** `gen_assets.py`
  `set_previews()` maps `image -> wallpaper.png`; shader/web/video use
  `preview.png`. All four are present. Don't raise a false "missing
  image/preview.png" alarm.
- **AppImage path is a SIBLING:** `/home/hunter/Desktop/apps/lumen.AppImage`
  (in `~/Desktop/apps/`), NOT `~/Desktop/apps/lumen/lumen.AppImage`. Watch
  script/CI paths.
- **`monitors.primary_name()` returns `""` under the offscreen QPA** (no real
  screens). Under the live X11 app it resolves to `DisplayPort-0` (proven by the
  runtime log). Don't probe it without a live `QApplication` + real display.
- **`PyQt6.__version__` does not exist** — use `PyQt6.QtCore.PYQT_VERSION_STR`.
  Test imports, not the attribute.
- Scaling override for web/shader/video is STORED but only physically
  transformed for IMAGE wallpapers (full-window by design). Store copy wording
  should say "scaling for images and video frames", not claim shader fit/center.

## Standalone blockers to shipping (need LO action, not audit)
- Real Steam App ID (replace `480` in `steam_appid.txt` + `steamworks.py APP_ID`).
- `git init` before ship (Lumen has no VCS).
- Store asset capture (Step 3) + Steamworks page paste (Step 4).
