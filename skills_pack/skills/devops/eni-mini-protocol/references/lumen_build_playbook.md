# LUMEN build playbook (ENI_LUMEN)

Condensed knowledge bank for resuming / full-power-building the LUMEN PyQt6
WebGL wallpaper engine at `/home/hunter/Desktop/apps/lumen`. Pair with the
"CRITICAL pitfall" + "LUMEN-specific notes" subsections in SKILL.md.

## Validated commands (post PASS 5)
- Full headless suite:
  `cd ~/Desktop/apps/lumen && .venv/bin/python -m pytest -q -p no:randomly`
  -> 106 passed, 1 skipped, 4 subtests. (Baseline before PASS 5 was 78.)
- The web-engine test (`tests/test_surfaces.py`) is opt-in via
  `LUMEN_RUN_WEBENGINE_TESTS=1`; it SKIPS cleanly headless because Chromium
  SIGABRTs on `QWebEngineView` construct offscreen — the abort is un-catchable
  by `try/except`, so never assert it as FAIL.
- Headless GUI smoke (verifies Settings wiring without a desktop):
  `QT_QPA_PLATFORM=offscreen .venv/bin/python -c "..."` building
  `MainWindow(MagicMock(engine))`. Assert `engine.max_webgl` flips when the
  spinbox handler runs. (Set config back to `max_webgl_surfaces=1` after — the
  smoke writes to `~/.config/lumen/config.json`.)

## Additive full-power build checklist
1. GUI theme — create `lumen/ui/styles.qss`. The loader already reads it; a
   MISSING file means the app ships with ZERO theming (bare Qt). Use the
   object names already in code: `Sidebar, Nav, Card, Apply, MonitorChip,
   Hero, TopBar, BrandText` (+ `Search, Status, Current, Badge`). See
   `templates/pyqt6_dark_theme.qss` as a starter.
2. Settings — add rows to `browser.SettingsPage.__init__` and wire them as new
   methods. For AMD stability set BOTH `cfg["max_webgl_surfaces"]` AND
   `engine.max_webgl` (guarded `hasattr`), then call `on_change()`.
3. Samples — drop `lumen/samples/<id>/{lumen.json, shader.glsl}`.
   `tests/test_samples.py` validates every manifest + shader `main`/`gl_FragColor`.
   Link real render stills (`store_assets/verify_*.png`) as `preview.png` so
   library cards show thumbnails instead of "no preview".
4. Store art — `image_generate` needs `FAL_KEY` (absent in this env). Use
   `tools/make_store_art.py` (pure PIL, no external dep) to emit
   `capsule.png` (616x353), `header.png` (1920x1080), `library.png` (1280x720).
5. Packaging — AppImage (built+verified), Flatpak (`packaging/flatpak/build.sh`),
   Deb (`packaging/deb/build.sh`). Last two need their build hosts.
6. Docs — `STORE_PAGE.md` (Steam store copy).
7. Tests — lock every new asset with a regression test (`test_styles`,
   `test_samples`).

## Gotchas (root-caused this session)
- `WallpaperEngine.max_webgl` is HARDCODED `=1` in `__init__` and never reads
  config. A Settings control MUST push the value into the live attribute.
- `Wallpaper.folder == root / id` — a test that passes `folder=cache/wid` as the
  model root produces a doubled path `cache/wid/wid`. Pass `cache` as root.
- `build_shader_html` writes `CACHE_DIR/{id}.html` but does NOT set `wp.entry`
  (that's `ShaderWallpaper.__init__`) and does NOT mkdir. Assert the FILE.
- Safe-mode recovery: `python -m lumen --reset-safe`. Settings can expose a
  button that subprocesses this.
- On-disk GPU-sandbox contract (source of truth): `app.py` sets
  `QTWEBENGINE_CHROMIUM_FLAGS` = SwiftShader-only; GPU sandbox LEFT ON; no
  `QTWEBENGINE_DISABLE_SANDBOX`. STATUS_LUMEN.md once said "do NOT remove" that
  var — STALE; trust the disk, not the doc.

## UNVALIDATED (need LO's desktop / build hosts — NOT code defects)
Live AMD multi-monitor boot; Flatpak build; Deb build; real-desktop web-engine
test; AI-generated store art. Scripts + procedural art are in place and runnable
there.
