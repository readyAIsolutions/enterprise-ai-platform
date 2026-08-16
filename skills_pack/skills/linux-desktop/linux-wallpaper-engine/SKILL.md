---
name: linux-wallpaper-engine
description: Build and ship Linux wallpaper / desktop-overlay applications (animated wallpapers rendered behind the file manager) with PyQt6, X11 desktop-layer windows, libmpv video, WebGL/GLSL shaders, and Steam/AppImage/Flatpak packaging. Use when LO asks for a wallpaper engine, a desktop overlay, or a "Lumen"-style sellable Linux desktop product.
triggers:
  - "wallpaper engine for linux"
  - "animated wallpaper"
  - "desktop overlay behind icons"
  - "sellable linux desktop app"
  - building Lumen / extending the wallpaper project
---

# Linux Wallpaper / Desktop-Overlay Engine

## When to use
LO wants a wallpaper engine or any app that renders content *behind* the desktop
file manager across one or more monitors — web/WebGL, video, image, and GLSL
shader wallpapers — ideally shippable on Steam. A full reference implementation
lives at `/home/hunter/Desktop/apps/lumen` (LO's apps folder; app name "Lumen",
Python + PyQt6, run via `.venv/bin/python -m lumen`).

## Architecture (proven, from Lumen)
- `WallpaperWindow(QWidget)`: frameless, fills one `QScreen.geometry()`. Flag
  choice is the whole ballgame for icon safety — see Critical X11 technique.
  Do NOT use `Qt.Tool` (forces `_NET_WM_WINDOW_TYPE_UTILITY`, stacks above
  desktop). Non-interactive wallpapers use `X11BypassWindowManagerHint`
  (unmanaged, root-bottom) so the WM keeps them BELOW `nemo-desktop` (icons
  stay visible) and below the managed GUI; re-assert with `engine.lower_all()`
  after the GUI shows. Interactive web wallpapers that need mouse events use
  managed `WindowStaysOnBottomHint` instead (they sit above icons only while
  active). The "white screen" is NOT stacking — it is the QWebEngineView white
  default page background (see Pitfalls).
- One window per screen, owned by a `WallpaperEngine` (QObject) that handles
  monitor hot-plug (`app.screenAdded/Removed`), pause-on-fullscreen/battery
  policies, and re-applies saved per-screen assignments from a JSON config.
- Wallpaper kinds map to surface classes:
  - **web** → `QWebEngineView` (Chromium). Enable
    `QWebEngineSettings.WebAttribute.WebGLEnabled` and
    `Accelerated2dCanvasEnabled`. Local files via `QUrl.fromLocalFile`.
  - **video** → libmpv via `python-mpv`: `MPV(wid=str(winId()), vo="gpu",
    loop_file="inf", keepaspect=False, osc=False)`.
  - **image** → `QLabel` + `QPixmap` with stretch / fill / fit / center / tile.
  - **shader** → wrap the GLSL fragment shader in a minimal WebGL page and run
    it through the web surface (see Pitfalls — do NOT use a native GL renderer).
    Uniforms: `vec3 iResolution (w,h,1)`, `float iTime`.
    Implement the wrapper as `build_shader_html(glsl)` (module-level in
 `shader.py`) so the `ShaderWallpaper` window AND the library preview widget
 share one HTML generator — never build it inline in two places.
 - **Dedicated WebGL engine module (additive, ENI-mini pattern)** → build a
 *separate* `lumen/wallpaper/webgl_engine.py` (NOT an edit to `shader.py`)
 for the superset feature set: full `iResolution/iTime/iMouse/iFrame/iDate/
 iAudio/iDpr` uniforms, DPR-aware canvas with an AMD-safe cap (1.5x),
 `webglcontextlost`→reload recovery, dark no-WebGL fallback (never Chromium
 white), audio-reactive `iAudio` via WebAudio `AnalyserNode`, FPS throttle
 honoring `config.fps_limit`, an offline GLSL validator, and a GPU
 fragment-load estimator that feeds `max_webgl`. Full technique + the
 first-frame throttle-consistency pitfall + the Chromium-surface test gate +
 the add-only routing pattern + Shadertoy-style user uniforms + the dead-code
 `__lumenSetUniform`/`set_uniform` no-op pitfall: `references/webgl-engine-module.md`. Hard
 rules: write the portable page as `webgl.html` (NOT `shader.html`) so the
 two engines coexist; keep any pure-Python mirror byte-for-byte consistent
 with the JS loop on first-frame; gate `QWebEngineView`-constructing tests
 behind `LUMEN_RUN_WEBENGINE_TESTS=1`; ship a drop-in `WebGLShaderWallpaper`
 mirroring `ShaderWallpaper` so the engine.py routing swap is one non-
 destructive line; OANDA token is N/A to a graphics engine — say so.
- GUI: PyQt6 with a glassy QSS theme, a FlowLayout card grid, monitor chips as
  drag-drop targets, and a live preview widget.
- Steam: a `steamworkspy` wrapper with a dev fallback to the local library so
  the Store tab works even without Steam running. Robust init tries the canonical
  `steamworks` SDK first, then `steamworkspy`, then degrades to dev mode
  (see Pitfalls — the pip `steamworkspy` is broken).

## Critical X11 technique — icon-safe bottom stacking (read this!)
The naive approach (tag `_NET_WM_WINDOW_TYPE_DESKTOP` + `_NET_WM_STATE_BELOW`,
delivered as a `ClientMessage`) is NOT enough under XFWM4 and WILL bury desktop
icons. WHY: Qt appends `_NET_WM_WINDOW_TYPE_NORMAL` to every window's type list
(probe shows `[DESKTOP, _KDE_NET_WM_WINDOW_TYPE_OVERRIDE, NORMAL]`), so XFWM4
reads the multi-type as NORMAL and stacks the wallpaper ABOVE `nemo-desktop`.
Do NOT use `Qt.Tool` (UTILITY type, also stacks above). The reliable
bottom-of-stack under XFWM4 that ALSO preserves desktop icons is:
- **Non-interactive wallpapers** (web/video/image/shader): use
  `Qt.WindowType.X11BypassWindowManagerHint` (unmanaged, root-bottom) so the
  WM leaves the wallpaper BELOW `nemo-desktop` (icons stay visible) and below
  the managed GUI. This is the correct fix — the earlier "white screen" was
  NOT stacking: it was the QWebEngineView white default page background
  flashing (fixed by painting the view + page background black in web.py) plus
  a blank workshop web wallpaper as the default assignment (now a bundled
  colourful sample). Keep `WA_TransparentForMouseEvents` so clicks pass through.
- **Interactive web wallpapers** (need mouse events): keep managed with
  `WindowStaysOnBottomHint` (no bypass). Accept it sits above icons only while
  that interactive wallpaper is active.
Full working code + Xlib probe + gsettings backdrop recipe:
`references/x11-wallpaper-bottom-stacking.md`.

## Pitfalls (learned the hard way)
- **QWebEngineView flashes pure WHITE before the wallpaper paints — THIS is
  the white-screen bug, NOT window stacking.** A `QWebEngineView` (and its
  `QWebEnginePage`) renders an opaque WHITE background until the page/HTML
  loads, so on boot you see blinding white even when the app is fine. Fix in
  `web.py` (and the shader surface): `view.setStyleSheet("background:black;")`,
  `view.setAutoFillBackground(True)`, `view.page().setBackgroundColor(
  QColor(0,0,0))`, and set the page `<body>` background to `#000` in
  `build_shader_html`. Combined with a bundled COLORFUL default wallpaper (not
  a possibly-blank Steam Workshop web wallpaper), the first paint is always
  dark+colorful. A white-blank default assignment (e.g. Workshop "Adventure
  Cat") is a SECOND white-screen cause — default first-run to a bundled sample
  like "Nebula Drift" (see First-run auto-apply).
- **Desktop ICONS HIDDEN = Lumen stacked ABOVE nemo-desktop (not a white screen).** `_NET_WM_STATE_BELOW` plus `X.Below` (configure stack_mode) is not strong enough under XFWM4 — the override-redirect (`X11BypassWindowManagerHint`) surface maps on top of `nemo-desktop` and buries the icons. The reliable fix in `lumen/utils/x11.py` `_apply_desktop_props` is `d.lower_window(win)` (XLowerWindow), which takes the window to the absolute bottom of the X root, below the managed desktop layer. Re-assert repeatedly (window.py `show_on_desktop` QTimer at 60/250/700/1500/3000/5000/8000 ms) because Chromium creates its render surface after load and would clobber the hint. Also call `x11.ensure_desktop_bg_transparent()` at startup so nemo's backdrop is a transparent PNG (a solid nemo wallpaper otherwise hides Lumen). Verify on the real display: `xwininfo -root -tree` must list the Lumen `has no name` override-redirect windows BELOW the `nemo-desktop` windows, and a grab of the primary must show colorful Lumen content (high stddev) through nemo — that proves transparency and icon visibility.
- **Multiple Lumen instances stack duplicate surfaces over the icons.** A second launch (double-clicking the `.desktop` button) or leftover test processes spawn another set of full-screen wallpaper windows that pile above nemo and hide icons. Add a PID-lock single-instance guard (`_single_instance()` in app.py) that refuses a second launch while one is alive; clean the lock via `atexit`. Kill strays with `pkill -f '.venv/bin/python -m lumen'` — match the venv PATH, never bare `python -m lumen` (that matches the wrapper shell and kills the diagnostic itself).
 - **`--screenshot` capture bypasses the single-instance lock and double-stacks wallpapers.** `export_screenshots()` in `app.py` instantiates a fresh `WallpaperEngine` + `MainWindow` WITHOUT calling `_single_instance()`, so running `capture_assets.sh` (or `lumen --screenshot`) while the main Lumen GUI is open spawns a second set of full-screen wallpaper surfaces that pile above `nemo-desktop` and hide icons. Quit Lumen first (or run before launching it). It calls `engine.shutdown()` at the end, but mid-run you'll see duplicate wallpapers. Verify capture on a clean X11 session.

- **Stale config keys warn/crash on launch — prune invalid assignments
  defensively.** LO's real `lumen.json` once carried a rotten key
  `"screen": "wp_..."` (left from an old run) that made `engine.apply` spam
  `Screen screen not found` every boot. In `apply_config_assignments`/load,
  DROP assignments whose `screen` isn't a live `QScreen.name()` and whose
  `wallpaper` id isn't in the library; on first-run-empty, auto-apply a bundled
  colourful sample to the primary monitor (see First-run auto-apply).
- **Call the set-wallpaper helper AFTER `show()`** — the window must be mapped
  first or EWMH operations silently no-op.
- **Non-interactive wallpapers**: set `WA_TransparentForMouseEvents` so clicks
  pass through to the file manager and desktop icons stay usable and visible.
  Only drop this for "interactive" web wallpapers (then use
  `_NET_WM_STATE_BELOW` removal instead).
- **Wayland**: true desktop-layer needs a compositor wallpaper protocol, which
  isn't broadly exposed. Implemented best-effort: for **images** use the
  freedesktop `org.freedesktop.portal.Wallpaper` (SetWallpaperWithURI) for a
  REAL wallpaper; for video/web/shader fall back to a fullscreen
  stay-on-bottom window. Detect `XDG_SESSION_TYPE==wayland` and branch. Target
  X11 (KDE/GNOME/XFCE) as the solid, full-feature path.
- **PEP 668 externally-managed Python**: LO's box blocks `pip install --user`
  and the system PyQt6 is 6.10.2 (WebEngine missing). Use a project venv:
  `python3 -m venv .venv && .venv/bin/pip install -e .` (bundles PyQt6 +
  WebEngine 6.11.0, python-mpv). Launch via `.venv/bin/python -m lumen`. No sudo
  available — do not attempt system pip or apt.
- **Steamworks SDK is genuinely broken in pip**: `steamworkspy` 0.0.2 on PyPI is
  an empty placeholder (circular imports in its own packaging, empty top-level
  `__init__`). Do NOT rely on it. Robust init: `try: import steamworks` (real
  SDK) `except ImportError: import steamworkspy as steamworks`, and if even that
  fails, run Store in dev mode (local library) with a clear log line. Real
  publishing needs the real SDK + a real App ID in `steam_appid.txt` (currently
  the 480 placeholder) + `APP_ID` in `steamworks.py`.
- **mpv embedding**: pass `wid=str(int(self.winId()))` and create the
  `python-mpv` player only after the window is shown.
- **Shaders**: always wrap GLSL in WebGL. Native scene/GL renderers crash on
  shader wallpapers — WebGL-in-Chromium is the stable path.
- **`python-xlib` import** must be wrapped in try/except so dev builds on
  Wayland / headless don't hard-fail at import time.
- **Per-screen id sanitization**: when importing a folder as a wallpaper,
  sanitize the id (`re.sub(r"[^A-Za-z0-9_.-]", "_", ...)`) — folder names with
  spaces become broken ids otherwise.
- **Hermetic asset-generation tests — never assert repo asset state.** A
  generator you also RUN in-place (e.g. `render_all_previews` against the
  live `lumen/samples` to ship the fix) mutates the repo, so a test that
  asserts "this sample has no preview" / "this is a flat 1-color block"
  GREENS once then REDS forever after the deliverable run (the asset no
  longer matches the assumption). Tests must build their own fixtures
  (unlink the preview to simulate missing; write a known flat PNG to simulate
  a placeholder), then assert the generator's behavior. Applies to ANY
  in-place generator (store-art, gallery contact sheet, pack builder).
  Recipe in `references/sample-previews.md`.
- **UI controls must drive the engine, not just config**: the Settings volume
  slider originally wrote to a dead config key and the wallpaper never changed.
  Wire every GUI control to the live `WallpaperEngine` method (e.g.
  `engine.set_volume(v)`) AND persist via `cfg.set(...)` — control → engine
  first, config second.
- **Shader HTML belongs in a shared module function**: expose
  `build_shader_html(glsl)` at module level in `shader.py` and have BOTH the
  `ShaderWallpaper` window and the preview widget call it. The preview must NOT
  instantiate a hidden wallpaper window just to build the HTML string —
  that wastes a QWebEngineView and can race with the live window.
- **First-run auto-apply**: if the saved-assignments map is empty on launch,
  auto-apply the first scanned library item to the primary monitor so the user
  immediately *sees* the app work. Empty-on-boot feels broken even when code
  is correct.
- **Seed samples per-folder, never early-return**: the original `seed_samples()`
  returned as soon as the library was non-empty, so new sample types never
  appeared. Iterate each sample folder, read its `lumen.json` id, and copy
  individually only if the destination is missing.
- **Generate self-demonstrating media samples with ffmpeg**: `ffmpeg -f lavfi
  -i gradients=...` for a PNG, `ffmpeg -f lavfi -i life=...` for an MP4 loop —
  so the library visibly shows web/shader/image/video out of the box (LO's real
  WE collection is usually NOT on the Linux box). Add Import Folder / Import
  .pkg buttons + `import_we_project` (reads real WE `project.json`) +
  `import_workshop_sources` auto-scan of Steam workshop dirs on launch.
- **Creator wizard + system tray**: ship a "Create" flow that turns a URL /
  local HTML / image / video / GLSL into a library wallpaper, and a tray icon
  (generate the icon in code, no binary asset) with Show / Pause / Resume /
  Quit so the app survives minimized as a real desktop daemon.
- **Hot-plug signal name**: the Qt `QScreen` geometry-change signal is
  `geometryChanged`, NOT `screenGeometryChanged` (that name does not exist and
  raises at connect time). Use `screen.geometryChanged.connect(...)`.
- **PyQt6 is stricter than PyQt5 — three silent breakers caught only by a
  real boot (not by `py_compile`)**:
  - `QAction` moved to `PyQt6.QtGui` (it is NOT in `PyQt6.QtWidgets`). Import
    it from `QtGui`.
  - `QSpacerItem` is NOT auto-imported with `QtWidgets` — add it explicitly to
    the `from PyQt6.QtWidgets import (...)` list or you get
    `NameError: name 'QSpacerItem' is not defined` at build time.
  - `QLayout.addWidget(x)` REJECTS a `QLayout` in PyQt6 (PyQt5 silently
    coerced). Use `addLayout(x)` for nested layouts; `addWidget()` only for
    `QWidget`. Mixing them up raises `TypeError: addWidget(...): argument 1
    has unexpected type 'QHBoxLayout'`.
- **Build order: create reusable popovers/drawers BEFORE the card grid that
  connects to them.** If a page wires `card.hover_requested.connect(
  self.hover.show_for)` but `self.hover` is instantiated *after*
  `_refresh_cards()`, you get `AttributeError: 'LibraryPage' object has no
  attribute 'hover'`. Construct `HoverPreview`/`DetailDrawer` (and any shared
  preview widget) first, then refresh the cards.
- **`X11BypassWindowManagerHint` (unmanaged) is CORRECT for non-interactive
  wallpapers on LO's XFWM4/nemo box — VERIFIED on his real DISPLAY=:0.0.** The
  older claim that it "renders ABOVE the GUI" was wrong for this compositor.
  Under XFWM4 an unmanaged fullscreen wallpaper sits BELOW the managed GUI and
  BELOW `nemo-desktop`, so the dark Lumen window stays visible AND desktop
  icons are preserved (this is the config that shipped). Use bypass for
  web/video/image/shader. Tradeoff: on SOME other compositors (kwin, mutter) an
  unmanaged wallpaper CAN race above managed windows, so a multi-DE build
  should re-assert bottom post-show and fall back to managed
  `WindowStaysOnBottomHint` only for interactive web walls (which need mouse
  events and accept sitting above icons while active). The REAL "Lumen is just
  a white screen" bug is NOT stacking at all — it is the QWebEngineView
  painting a pure WHITE page before the wallpaper loads (next pitfall). Always
  re-assert bottom with `engine.lower_all()` AFTER `window.show()` so a freshly
  raised GUI can never be left under the wallpaper.
- **AppImage: never package an editable install**: `pip install -e .` leaves a
  source redirect (egg-link / `__editable__` finder) so the image depends on the
  source dir existing — it breaks the moment the source moves. Build a throwaway
  clean venv and `pip install .` (non-editable) so `lumen` is a real copied
  package inside `site-packages`.
- **AppImage: data files must live inside the package**: reference bundled
  assets (samples, qss) via `Path(__file__).resolve().parent / "samples"`,
  NEVER `parent.parent` (that only resolves in editable dev mode). Declare them
  in `[tool.setuptools.package-data]` so `pip install .` bundles them.
- **AppImage: bundle libmpv + set Qt env**: copy `libmpv.so.2` into
  `AppDir/usr/lib` and prepend to `LD_LIBRARY_PATH`; set
  `QTWEBENGINE_DISABLE_SANDBOX=1` and `QT_QPA_PLATFORM_PLUGIN_PATH` in AppRun.
  `python3.14` is NOT dynamically linked to `libpython`, so you do NOT need to
  bundle libpython.
- **AppImage: `QTWEBENGINE_DISABLE_SANDBOX=1` is REQUIRED — do NOT remove it.** Chromium can't initialise its sandbox inside an AppImage/container without the setuid helper, so QWebEngine fails to launch (white screen / crash) if you drop it. It is NOT a GPU-sandbox regression: the real AMD-reboot cause was the `--ignore-gpu-blocklist` / `--disable-gpu-sandbox` *flags* forcing HARDWARE WebGL, now gone. With software WebGL (SwiftShader) the disabled Chromium sandbox never reaches the amdgpu driver. A review/status that flags it as "contradicting GPU sandbox" is usually a STALE claim — verify the actual on-disk export (it lives in `lumen/app.py` `os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX","1")` + `build_appimage.sh`; there may be NO `packaging/AppImage/AppRun` file at all).
- **Multi-monitor AMD reboot prevention (ship-blocking on LO's RX5700XT 4-monitor rig).** ROOT CAUSE: every shader/web wallpaper instantiates its OWN `QWebEngineView` → its own Chromium GPU process + its own WebGL context, ONE PER MONITOR. With hardware-forced WebGL flags on AMD `amdgpu`, 4 simultaneous HW WebGL surfaces hang the driver and the box hard-reboots on launch. This is the bug that nuked LO's PC on every Lumen boot. The 3-layer fix that actually works (shipped in `~/Desktop/apps/lumen`):
  1. **Never force hardware accel.** In `app.py` replace `--ignore-gpu-blocklist --enable-webgl --disable-gpu-sandbox` with SwiftShader (software) flags:
     `--enable-unsafe-swiftshader --enable-webgl --disable-gpu-compositing --disable-features=Vulkan,UseChromeOSDirectVideoDecoder --disable-dev-shm-usage`. The disabled Chromium sandbox + SwiftShader never reaches `amdgpu`.
  2. **Boot guard (`lumen/safety.py`):** track consecutive boot crashes in `~/.config/lumen/boot_guard.json`; 2 in a row → SAFE MODE (tray only, NO wallpapers) persisted until `python -m lumen --reset-safe`. Mark launch at start, mark clean exit on `atexit`/a CRASH_WINDOW timer so a clean shutdown resets the streak. Safe mode must also trip if any window dies without a clean-exit mark.
  3. **GL-context cap + RSS watchdog (`wallpaper/engine.py`):** `max_webgl_surfaces` (default 1) enforced in `apply()` — skip applying (and skip `apply_config_assignments`) while in safe mode; `drop_all_to_safe()` tears down every live GL surface. A 3s `QTimer` samples `process_tree_rss()` of the WHOLE process tree and calls `drop_all_to_safe()` if it exceeds ~2.2 GB, killing wallpapers BEFORE an OOM/reboot.
  VERIFY on LO's REAL `DISPLAY=:0.0` (headless can't exercise the GUI render path): launch `python -m lumen --minimized`, confirm no reboot and that `boot_guard.json` reads `safe_mode=false, crashes=0`. Rebuilding the AppImage (`bash build_appimage.sh`) is REQUIRED to bake the fix into the shipped artifact — source-only fixes do not stop the crash.
  `AppRun` / `build_appimage.sh` sets `QT_QPA_PLATFORM_PLUGIN_PATH` to
  `.../site-packages/PyQt6/Qt/plugins` it is WRONG — the bundled Qt plugins dir
  is `PyQt6/Qt6/plugins` (note the `6`). It works on a box that also has system
  Qt plugins (silent fallback), but breaks on machines lacking them. Grep-check:
  `grep -n 'Qt/plugins' AppRun build_appimage.sh` — there must be NO match
  without the `6`. Fix before wide release. (Lumen's `build_appimage.sh:81` had
  exactly this typo; it only worked because LO's rig has system Qt plugins.)
- **AppImage: working build recipe**: download `appimagetool-x86_64.AppImage`
  from AppImageKit/continuous (FUSE/libfuse required to mount at runtime).
  Assemble `AppDir/{usr/bin/python3 (cp of /usr/bin/python3.14),
  usr/lib/python3.14 (cp -rL venv/lib/python3.14 — dereferences the symlink),
  usr/lib/libmpv.so.2, AppRun, <app>.desktop, <app>.png}` then
  `appimagetool AppDir out.AppImage`. Reusable script:
  `scripts/build_appimage.sh`. Verify with
  `timeout 14 out.AppImage --minimized` and watch the log for
  `Applied <name> -> DisplayPort-0`.
- **AppImage: `QTWEBENGINE_DISABLE_SANDBOX=1` is REQUIRED — do NOT remove it.** Chromium can't initialise its sandbox inside an AppImage/container without the setuid helper, so QWebEngine fails to launch (white screen / crash) if you drop it. It is NOT a GPU-sandbox regression: the real AMD-reboot cause was the `--ignore-gpu-blocklist` / `--disable-gpu-sandbox` *flags* forcing HARDWARE WebGL, now gone. With software WebGL (SwiftShader) the disabled Chromium sandbox never reaches the amdgpu driver. A review/status that flags it as "contradicting GPU sandbox" is usually a STALE claim — verify the actual on-disk export (it lives in `lumen/app.py` `os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX","1")` + `build_appimage.sh`; there may be NO `packaging/AppImage/AppRun` file at all).
- **AppImage: the venv `lib/pythonX.Y` has NO stdlib — the bundle is host-Python-bound.** `cp -rL venv/lib/python3.14` only copies `site-packages`: a fresh venv's `lib/python3.14` directory contains ONLY `site-packages`, never `os.py`/the stdlib. The bundled `python3` therefore resolves its stdlib from the HOST's matching `/usr/lib/python3.14` at runtime. Consequence: the artifact runs only on hosts with the SAME Python minor version (fine for LO's python3.14 rig; NOT portable to a python3.12 box). For true portability, copy the real stdlib in (`cp -rL /usr/lib/python3.14 AppDir/usr/lib/python3.14`) and exclude `site-packages` from the auto-copied venv dir, OR accept the constraint and pin the Python version in the release notes. Do NOT assume the AppImage is fully self-contained just because the python binary is bundled.

- **Steam Workshop import must scan the SNAP Steam path**: LO's Steam is a
  *snap* install, so the workshop collection is NOT at `~/.steam` or
  `~/.local/share/Steam`. Scan
  `/home/hunter/snap/steam/common/.local/share/Steam/steamapps/workshop/content/431960/`
  plus the classic roots as fallbacks. Import **by symlink** (not copy) into
  `~/.local/share/lumen/wallpapers/wp_<id>` so it mirrors the live subscription
  and never duplicates gigabytes. Parsing: read WE `project.json` (type field:
  `scene`/`web`/`video`/`image`) AND Lumen's `lumen.json`; `scene` (3D Unity)
  cannot render natively so map to `KIND_SCENE` and play its bundled
  `preview.gif`/`preview.mp4` (every WE wallpaper ships one — assert all
  resolve). Set `original_type` on the model so the UI can badge
  "SCENE · preview" and tag `source_path` so the card shows "Wallpaper Engine".
- **XFCE/Nemo icon safety — the `_NET_WM_WINDOW_TYPE_DESKTOP` trick is NOT
  sufficient**: the old note claimed a DESKTOP-typed + `_NET_WM_STATE_BELOW`
  window is "forced to the bottom of the stack." That is FALSE under XFWM4 —
  Qt appends `_NET_WM_WINDOW_TYPE_NORMAL`, so the WM reads it as NORMAL and
  stacks the wallpaper ABOVE `nemo-desktop` (icons vanish). The only reliable
  bottom-of-stack is `X11BypassWindowManagerHint` + `XLowerWindow` (see
  references/x11-wallpaper-bottom-stacking.md). You STILL must set Nemo's
  backdrop transparent (`gsettings set org.nemo.desktop picture-uri
  "file://<transparent.png>"`) so the wallpaper shows through behind the icons;
  do that at startup via `ensure_desktop_bg_transparent()`.
- **XFCE desktop icons may be owned by `nemo-desktop`, not `xfdesktop`**:
  setting `xfce4-desktop` backdrop transparent is harmless but does NOT reveal
  the wallpaper if Nemo draws the desktop. Instead set Nemo's backdrop
  transparent: `gsettings set org.cinnamon.desktop.background picture-uri
  "file://<transparent.png>"`. Lumen's window is already
  `_NET_WM_WINDOW_TYPE_DESKTOP` + `_NET_WM_STATE_BELOW` + forced to the bottom
  of the stack, so with Nemo transparent the live wallpaper shows *behind* the
  icons. Detect which desktop manager owns the root via
  `xwininfo -root -children` (look for `nemo-desktop` windows).
- **GUI must be forced onto the primary monitor in multi-monitor rigs**: by
  default Qt may open the window on a non-primary screen (LO saw it on the
  left monitor while the wallpaper was on the middle primary). After
  `window.show()`, call a `_place_on_primary()` that moves it to
  `QApplication.primaryScreen().geometry()` centered, then `raise_()` +
  `activateWindow()`. Verify with `xwininfo -id <wid>` — absolute x must fall
  inside the primary monitor's range (LO's DisplayPort-0 is at `+1920+0`, 2560
  wide → 1920–4480; a GUI at `+2610+160` is correctly on primary).
- **`linux-wallpaperengine` (the real WE Linux port) is an icon-killer AND the
  scene-3D path**: the dev build at
  `/home/hunter/Dev/linux-wallpaperengine/build/output/linux-wallpaperengine`
  takes the wallpaper folder as a POSITIONAL arg with flags
  `--screen-root <monitor> --bg <id> --scaling <mode> --assets-dir`. Its
  `--screen-root` mode throws fullscreen windows that bury desktop icons — if
  Lumen coexists with it, kill it (`pkill -f linux-wallpaperengine` / scan
  `/proc`; the binary name exceeds 15 chars so `pkill -x` by exact name fails)
  before trusting icon safety. To offer TRUE 3D for `scene` wallpapers, wire a
  one-click "Render 3D via Wallpaper Engine" button that shells out to this
  binary — but it WILL overlay icons, so gate it behind an explicit user action
  (never auto-run) to honor LO's no-icon rule. Detail in
  `references/wp-engine-import.md`.

## LUMEN swarm add-only build (LMxx builders) — THE LEASH
When building Lumen as a swarm/ENI-mini (LMxx, workspace N), the mandate is
**CODE-ONLY**: NEVER open the GUI, NEVER let code grab the X display or a
WebGL/GPU context — the full app has hard-rebooted LO's AMD RX5700XT 4-monitor
rig, so the GUI path is OFF-LIMITS during build. This is the INVERSE of the
live "verify on DISPLAY=:0.0" rule below: swarm builders prove correctness
HEADLESS and hand the runtime check to LO. Allowed: edit/fix/harden, pytest,
flake8, mypy, import-smoke ONLY. Prove leash-safety with an import-smoke that
asserts NO `PyQt6` symbol is in `sys.modules` after importing your module; if
a module needs a Qt API, import it lazily INSIDE the function that uses it.
Lazy-import pattern + the full verification stack + the `STATUS_LMxx.md`
convention (line 1 `[state: DONE|IN-PROGRESS|BLOCKED]`, PASS/FAIL board with
real numbers, what adds R / what to drop, UNVALIDATED):
`references/lumen-swarm-leash.md`.

## Packaging / shipping (Steam-ready)
See `references/packaging-steam.md`. TL;DR: AppImage built by bundling a
clean venv + `appimagetool` (NOT linuxdeploy — it can't find venv-bundled
PyQt6; use `scripts/build_appimage.sh`), Flatpak on `org.kde.Platform`, Steam
via `steamworkspy` +
ready). Linux
has no first-party Wallpaper Engine client → own that niche.
- **Store assets**: `scripts/capture_assets.sh` launches Lumen with
  `lumen --screenshot <dir>` to grab Library/Workshop/Settings/wallpaper PNGs,
  then records a ~30s live-wallpaper trailer via ffmpeg x11grab. The
  `--screenshot` CLI flag lives in `app.py` (`export_screenshots()`) and
  instantiates the GUI + grabs widgets. It runs on a real X11 display, AND it
  also runs HEADLESS via `QT_QPA_PLATFORM=offscreen` (GUI PNGs 01/02/03 render
  real; 04_wallpaper is blank offscreen by design) — see Verification §4 and
  `scripts/smoke_appimage.sh`.
  CAVEAT: `export_screenshots()` does NOT call the `_single_instance()` PID
  lock, so capturing while the main Lumen GUI is open spawns a SECOND set of
  wallpaper surfaces stacked over `nemo-desktop` (icons hidden mid-run). Quit
  Lumen first. Sample previews: shader/web/video use `preview.png`; the image
  sample previews via `wallpaper.png` (don't look for `image/preview.png`).
  Full read-only ship-audit recipe + source-drift check:
  `references/lumen-ship-audit.md`.

## Sample previews & pack (lumen/samples_pack.py)
ADD-ONLY module (ENI mini B05) for headless procedural sample-thumbnail
generation + a shippable samples pack. Pure PIL, no GPU/X needed. Full
API, the flat-vs-genuine detection heuristic, and the hermetic-asset-test
trap: `references/sample-previews.md`. TL;DR: `render_preview()` makes a
branded deterministic still per sample; `render_all_previews()` regenerates
ONLY flat (≤16-color) / missing previews and PRESERVES genuine
multi-color renders; `build_pack()` emits `samples_pack.tar.gz` +
`samples_manifest.json`. Run `python -m lumen.samples_pack --root
lumen/samples --out dist` to fix/refresh all previews and build the pack.
Do NOT pass `--overwrite` in the normal build (it would clobber the few
genuine renders).

## Verification in a headless sandbox
You often build this on a machine without PyQt6 installed and no X11 display
(e.g. a CLI sandbox). Full GUI runtime testing is impossible there, so verify
in two cheap layers before declaring done:
1. **`python3 -m py_compile lumen/*.py lumen/*/*.py`** — catches every syntax
   error across all modules in one shot. Non-negotiable gate.
2. **Pure-logic smoke test**: load only the non-GUI modules via `importlib`
   (config, model, x11 guarded by try/except) and assert real behavior —
   `get_config()` round-trips, `install_from_folder` sanitizes ids
   (`My Cool Wallpaper` → `My_Cool_Wallpaper`), the assignment map saves.
   Keep the test self-cleaning (delete what it created) so it never leaves
   artifacts in `~/.local/share/lumen`.
- **Headless engine-logic unit tests (lock the reboot-fix invariants without Chromium/X).** Stub `WallpaperEngine._make_window` (return a `FakeWin` that records lifecycle and never builds a QWebEngineView), `lumen.utils.monitors.screen_by_name`, `lumen.utils.x11.{session_is_wayland,set_wallpaper_window}`, and `engine.cfg` (in-memory `FakeConfig`), then run the REAL `apply()` / `apply_config_assignments()` / `drop_all_to_safe()`. This is the only check that proves safe-mode skip, the single-WebGL-context cap, and the watchdog backstop. Use `tests/_qt.py::get_qapp()` (offscreen QApplication; imports WebEngine before the app object) via an autouse fixture. Starter: `templates/test_engine_headless.py`; recipe + gotchas: `references/headless-engine-tests.md`.
Do NOT burn time trying to `pip install PyQt6` in a headless box — it needs
system Qt libs + a display. But if the box HAS `DISPLAY` set (LO's rig runs
X11), you CAN launch live: `cd /home/hunter/Desktop/apps/lumen && timeout 12
.venv/bin/python -m lumen` and watch the log for `Applied <name> ->
DisplayPort-0`. Otherwise hand the runtime check to LO on his real X11 desktop
(`pip install PyQt6 PyQt6-WebEngine python-mpv`, `apt install libmpv2`).
- **When LO's real DISPLAY is reachable, TEST THERE, not in xvfb** — that is
  what actually found the white-screen root cause. Launch the app live on
  `DISPLAY=:0.0`, then grab his PRIMARY monitor (ffmpeg x11grab to a PNG) and
  measure pixel stats with PIL: assert GUI regions are dark (sidebar ~
  (24,19,44)), the wallpaper region has high colour variance (stddev > 40),
  and near-white pixels are < ~1%. This separates a real white-screen
  (QWebEngineView white bg) from a stacking bug (icons hidden) from a fine
  GUI (dark grab). Reusable recipe: `references/white-screen-webengine-fix.md`.
3. **xvfb real-boot (headless box but apt + system Qt available)**: install a
   virtual display and actually launch the full app to catch widget-construction
   bugs that `py_compile` + import-only tests cannot:
   `sudo apt-get install -y xvfb` then
   `timeout 20 xvfb-run -a .venv/bin/python -m lumen --minimized`.
   An `exit=124` (the timeout killing a still-alive process) means it booted
   healthy — read the log for `Applied <name>` and `Slideshow started`. A traceback
   instead means a real bug (e.g. the three PyQt6 issues above, or a missing
   attribute). This is the only check that instantiates the entire GUI + engine,
   so run it whenever the box can install `PyQt6` system libs. Chromium logs a
   Chromium logs a benign `ContextResult::kTransientFailure` GPU warning under xvfb — ignore it.
   - **Headless AppImage smoke (no X needed)** — verify the *bundled* AppImage
   renders its GUI without any display:
   `QT_QPA_PLATFORM=offscreen timeout 120 /home/hunter/Desktop/apps/lumen.AppImage --screenshot /tmp/smoke`
   Gotchas (caught the hard way): `--screenshot` REQUIRES an OUTDIR argument
   (omit it → `error: argument --screenshot: expected one argument`); there is
   NO `--offscreen` CLI flag (use the `QT_QPA_PLATFORM=offscreen` env var); the
   process exits **139 (SIGSEGV) on WebEngine teardown — BENIGN**, the PNGs are
   already written; `01_library.png`/`02_store.png`/`03_settings.png` are REAL
   GUI captures, but `04_wallpaper.png` is BLANK offscreen (no live wallpaper
   surface without a display) — expected, NOT a regression (on real X11 it
   fills). Reusable script: `scripts/smoke_appimage.sh` (asserts 01/02/03 are
 non-trivial and tolerates exit 139). This is the cheapest GREEN proof when
 LO's display is busy or you're in a headless box.
 - **OUTDIR is created as a DIRECTORY, not a file prefix.** Pass
   `/tmp/smoke` and the four PNGs land at `/tmp/smoke/01_library.png`,
   `/tmp/smoke/02_store.png`, `/tmp/smoke/03_settings.png`,
   `/tmp/smoke/04_wallpaper.png` — they do NOT land as `/tmp/smoke_01_library.png`.
   Probing `ls /tmp/smoke_*.png` finds nothing and wastes a cycle; look for a
   freshly-created `<OUTDIR>/` directory instead. (`scripts/smoke_appimage.sh`
   already accounts for this layout.)
 - **FUSE-free headless verify via `--appimage-extract` (best for CI / sandbox).** The runtime needs FUSE to *mount*, but `--appimage-extract` needs NONE — it unpacks to `squashfs-root/`. Then `squashfs-root/AppRun --version` (prints `Lumen 1.0.0`), `squashfs-root/AppRun --reset-safe` (exercises the bundled BootGuard), and a bundled-python import check across every heavy submodule prove the bundle is complete + importable WITHOUT a display:
   `PYTHONPATH=squashfs-root/usr/lib/python3.14/site-packages LD_LIBRARY_PATH=squashfs-root/usr/lib squashfs-root/usr/bin/python3 -c "import lumen, lumen.app, lumen.wallpaper.engine, lumen.ui.main_window, lumen.steam.steamworks, lumen.gallery_export; print('IMPORTS OK', lumen.__version__)"`. This is deterministic (no SIGSEGV to tolerate, unlike the offscreen `--screenshot` smoke) and is the cheapest GREEN proof when the build box is headless or LO's display is busy. Reusable: `scripts/verify_appimage_headless.sh`.
 - **Depot upload is blocked until a REAL App ID + STEAM_USER exist.** The
   shipkit's `NEXT_BUILD.sh` exits **10** (`!! BLOCKER(10): app_build.vdf
   AppID is still the placeholder 480`) while `steam_appid.txt` / `steamworks.py`
   `APP_ID` / `app_build.vdf` still carry the placeholder `480` (and no
   publisher `STEAM_USER` is supplied). The placeholder `480` is Valve's sample
   App ID and is NOT shippable — LO must supply a real App ID + publisher login;
   the agent cannot auto-supply these. Store-asset capture (`capture_headless.sh`
   / `trailer_capture.sh`) is also disruptive on LO's live X (pops GUI + records
   screen) so it waits for his session. Recurring ship-state + the exact ENI-mini
   re-verify command set live in `references/lumen-ship-blockers.md`.
- **White/blank screen triage**: if LO reports an all-white window that still
  boots without a traceback, it is almost always an *overlaying* fullscreen
  surface (the wallpaper/desktop window) painting on top of the GUI — NOT the
  GUI itself. Prove it by grabbing the GUI under xvfb with a stub engine (no
  wallpaper windows) and measuring pixel brightness with PIL: a dark,
  structured grab means the GUI is fine and the bug is window stacking. See
  `references/debug-white-screen.md` + `scripts/diag_gui.py`.

## Working style for LO on big builds
When LO says "full power" / "demiurge" / "use everything", execute autonomously:
build the ENTIRE thing (every module, GUI, packaging, samples) without
step-by-step confirmation or "should I continue?" checks. See memory note on
LO's full-power directive.

## Project state
Current Lumen build status, venv/launch commands, pending features, and the
broken-`steamworkspy` reality: `references/lumen-project-state.md`.
