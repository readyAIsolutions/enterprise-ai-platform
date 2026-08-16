# Lumen — Project State (as of build session)

Location: `/home/hunter/Desktop/apps/lumen` (LO's apps folder). Run with:
`cd /home/hunter/Desktop/apps/lumen && .venv/bin/python -m lumen`

## Runtime / environment
- Python is **PEP-668 externally-managed** → a venv is required. No sudo, no
  `pip install --user`.
- venv at `.venv` bundles PyQt6 + PyQt6-WebEngine 6.11.0 + python-mpv
  (`python3 -m venv .venv && .venv/bin/pip install -e .`).
- System PyQt6 is 6.10.2 (WebEngine missing) — the venv's 6.11.0 is what runs.
- ffmpeg 8.0.1 and libmpv are present on the box.
- DISPLAY=:0.0 (X11). Live launch works.

## Live launch test (proof it runs)
`timeout 12 .venv/bin/python -m lumen` → EXIT 124 (ran full 12s, no crash),
log line `Applied Nebula Drift -> DisplayPort-0`. Confirms GUI + engine render
on the real primary monitor.

## Wallpaper kinds (all four wired + seeded)
- web / WebGL (Chromium WebEngine) — rock solid
- shader (GLSL wrapped in WebGL via `build_shader_html()`) — stable path
- image (stretch / fill / fit / center / tile)
- video (libmpv) — works

Library ships 4 samples: Aurora Borealis [shader], Nebula Drift [web],
Aurora Gradient [image], Living Gradient [video].

## Steam reality (IMPORTANT)
`steamworkspy` 0.0.2 on PyPI is a **broken empty placeholder** (circular
imports, empty top-level `__init__`). Lumen tries the real `steamworks` SDK,
then `steamworkspy`, then degrades to dev mode (Store shows local library).
Real publishing needs: (1) a working Steamworks Python SDK, (2) a real App ID in
`steam_appid.txt` (currently the 480 placeholder) + `APP_ID` in `steamworks.py`,
(3) Steam installed so `import_workshop_sources` auto-pulls WE content.

LO's actual wallpaper collection is **NOT on this Linux box** (no Steam install;
the `linux-wallpaperengine` in ~/Dev is a C++ dev build, not a stash). Use the
Library Import Folder / Import .pkg buttons, or install Steam, to surface his
wallpapers.

## Pending features (from LO's "1 2 3")
- (1) wallpaper randomizer / slideshow timer — NOT done
- (2) preview-on-hover in library grid — NOT done
- (3) Wayland support — DONE (image via freedesktop Wallpaper portal;
  video/web/shader fullscreen stay-on-bottom fallback)

## Packaging ready
`packaging/AppImage/build.sh` (linuxdeploy),
`packaging/flatpak/io.lumen.Wallpaper.yml` (KDE Platform 6.6),
`packaging/steam/README.md`, `STORE_PAGE.md` (store copy).
Launch option for Steam: `lumen --minimized`.
