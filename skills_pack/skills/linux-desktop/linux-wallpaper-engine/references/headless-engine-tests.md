# Headless engine-logic regression tests (Lumen)

The wallpaper engine's reboot-prevention logic is the most important and most
fragile part of Lumen on LO's AMD RX 5700 XT multi-monitor box:

- **safe-mode skip** — when `BootGuard` tripped, `apply()` paints nothing.
- **single live WebGL/Chromium context cap** — `max_webgl_surfaces` (default 1)
  refuses a 2nd live GL surface. This is the "4-context hammer" guard that
  stops Lumen from hanging amdgpu and rebooting the machine.
- **`drop_all_to_safe()` watchdog backstop** — tears every surface down + locks
  safe mode so Lumen can NEVER take the host down.
- **stale-assignment pruning** — `apply_config_assignments()` drops assignments
  whose screen/wallpaper no longer exists (so it never paints a blank white page).

None of this is exercised by `py_compile` or import-only smoke, and the live GUI
path needs a real X display. But the logic CAN be unit-tested headlessly by
stubbing the three things that touch hardware. The REAL `apply()` /
`apply_config_assignments()` / `drop_all_to_safe()` run unchanged — only the
surface materialisation is faked, so the test actually locks the invariants.

## What to fake

1. **The window factory** — `WallpaperEngine._make_window(screen, wp)` returns a
   real `ShaderWallpaper`/`WebWallpaper`/`VideoWallpaper`/`ImageWallpaper`, each
   of which constructs a QWebEngineView / mpv / etc. Replace it (class level)
   with a lightweight `FakeWin` that records lifecycle calls and never touches
   Chromium/X:
   ```python
   monkeypatch.setattr(
       WallpaperEngine, "_make_window",
       staticmethod(lambda screen, wp: FakeWin()),
   )
   ```
   GOTCHA: patch as a `staticmethod`. A plain function as a *class attribute*
   would be bound (self injected) when called as `self._make_window(...)`; a
   `staticmethod` stored as an *instance* attribute would be returned un-called.
   `monkeypatch.setattr(WallpaperEngine, "_make_window", staticmethod(...))` is
   the correct form.

2. **Monitor probes** — `lumen.utils.monitors.screen_by_name(name)` would call
   `QApplication.screens()`. Patch it to return a `MagicMock` whose `.name()` /
   `.geometry()` return deterministic values (one screen per call).

3. **X11 probes** — `lumen.utils.x11.session_is_wayland()` (return `False`) and
   `lumen.utils.x11.set_wallpaper_window(...)` (return `False`). The engine calls
   these inside `apply` / `show_on_desktop`; stub them so no X connection is
   attempted (headless boxes have no `$DISPLAY`).

4. **Config** — `engine.cfg` is a real `Config` that writes
   `~/.config/lumen/config.json`. `monkeypatch.setattr(eng, "cfg", FakeConfig())`
   with an in-memory `data` dict + `assignment`/`set_assignment`/`clear_assignment`
   helpers. Prevents test pollution of LO's real config.

## Harness shape

- `tests/_qt.py::get_qapp()` spins an **offscreen** `QApplication` and imports the
  WebEngine modules *before* the app object exists (required by PyQt6 — importing
  `QtWebEngineWidgets` after a `QCoreApplication` raises). Use an `autouse` fixture
  calling `get_qapp()` so every test has a QApplication; `WallpaperEngine.__init__`
  creates `QTimer`s which need one.
- `_make_engine(monkeypatch, safe_mode, max_webgl)` builds a fully-hermetic engine
  and applies all four stubs. Reuse it in every test.
- `scan_library` is bound into the `lumen.wallpaper.engine` namespace at import
  time, so patch `engine_mod.scan_library` (the engine *module* attr), NOT
  `lumen.wallpaper.model.scan_library`.

## Invariants to lock (one test each)

- safe_mode True → `apply()` paints nothing (`windows` + `_webgl_screens` empty).
- `max_webgl == 1` → 1st WebGL surface allowed, 2nd **refused**.
- raised cap (2) → allows 2, refuses the 3rd.
- non-WebGL (image) surface does NOT consume the GL cap (a shader can still claim
  the single slot).
- `apply_config_assignments`: renderable assignment applied; missing wallpaper
  dropped AND assignment cleared; safe_mode skips all.
- `drop_all_to_safe()`: tears down all windows, sets `safe_mode`, clears
  `_webgl_screens`.

Starter template: `templates/test_engine_headless.py`.
Run: `cd ~/Desktop/apps/lumen && .venv/bin/python -m pytest tests/test_engine.py -v`
