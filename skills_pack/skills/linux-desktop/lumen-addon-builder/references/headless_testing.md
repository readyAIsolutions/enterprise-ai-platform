# Headless testing for LUMEN add-on modules

## Run recipe (from repo root /home/hunter/Desktop/apps/lumen)
The project venv is `.venv` (symlink to python3). Do NOT run `python -m lumen`.

```
cd ~/Desktop/apps/lumen
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_<module>.py -v
.venv/bin/python -m flake8 lumen/<module>.py tests/test_<module>.py
.venv/bin/python -m mypy lumen/<module>.py
QT_QPA_PLATFORM=offscreen .venv/bin/python -c "import lumen.<module>"
```

All four must be green:
- pytest: 0 failed
- flake8: exit 0, 0 issues
- mypy: "Success: no issues found in 1 source file"
- import-smoke: prints OK, no display touched

Other LUMEN tests also set `QT_QPA_PLATFORM=offscreen` and `os.environ.pop("DISPLAY")`
at import time (see tests/test_settings.py). Match that convention in any test
that might import a Qt-using module transitively.

## Gotchas that bit a real build
1. `__version__` is in `lumen/__init__.py`, NOT `lumen.config`.
   `from lumen.config import __version__` -> ImportError. Use
   `from lumen import __version__`.
2. mypy + tempfile: `fd, tmp = tempfile.mkstemp(...)` infers `tmp: str`.
   `tmp = Path(tmp)` then errors with "incompatible types (Path vs str)".
   Fix: `tmp_fd, tmp_name = tempfile.mkstemp(...); os.close(tmp_fd);
   tmp = Path(tmp_name)`.
3. Library walks must skip scratch dirs `cache` and `_import_tmp` (LUMEN
   writes temp imports there). Otherwise backups/tests capture junk.
4. Keep every filesystem path a function PARAMETER (default to the real
   LIBRARY_DIR/CONF_FILE) so tests inject `tmp_path` and never touch the live
   `~/.local/share/lumen`.

## Already-claimed LUMEN modules (avoid collision — read headers of each
## STATUS_*.md before claiming; this map is a snapshot, re-verify per session)
- safety.py + app.py + engine.py  -> reboot fix / boot guard / WebGL cap /
  RSS watchdog (WS4 master, STATUS_LUMEN.md PASS 1-4)
- steam/steamworks.py + gallery_export.py -> Workshop + gallery export
  (STATUS_LUMEN PASS 2)
- ui/browser.py (SettingsPage) -> settings panel hardening (ENI63)
- wallpaper/webgl_engine.py + wallpaper/web.py -> white-screen child-view fix
  (ENI9)
- importers/wallpaper_engine.py -> Wallpaper Engine .pkg import (established,
  in README + importers/__init__.py — treat as claimed)
- engine regression suite tests/test_engine.py (ENI_LUMEN PASS 3)
- config.py validation/schema (core — never touch)

## Safest claim: a NEW file
Create `lumen/<new>.py` (e.g. `lumen/library_backup.py`) that did not exist.
This guarantees add-only and zero sibling conflict. Worked example this
session: `lumen/library_backup.py` + `tests/test_library_backup.py`
(15 tests, pure stdlib, no Qt) — all four gates green.
