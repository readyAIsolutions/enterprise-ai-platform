# PyQt6 settings-dialog pattern (DEMIURGE3D / reusable)

Condensed from the DEMIURGE3D_B09 mini-build (`backend/forge/settings_ui.py`,
2026-07-11). LO's standard for desktop GUIs is PyQt6 (same as lumen).

## Paradigm caveat (READ FIRST)
DEMIURGE3D's **primary UI is the React/TS SPA** served by FastAPI `server.py`
(settings already surface via `/api/printer/settings` + `PrinterSetup.tsx`).
A PyQt6 `QDialog` is a **standalone desktop companion** that does NOT plug into
the SPA. Before building "settings dialogs" as PyQt6, confirm with LO whether he
wants a separate desktop window or the settings belong in the React frontend.
The B09 `forge/settings_ui.py` was built ADD-ONLY as a standalone, tested module
but is NOT wired to the SPA.

## Schema-driven shape (so the UI can't drift from the model)
1. `FieldSpec` dataclass: `key, label, dtype, default, group, help, choices,
   min, max, env`. `dtype` in {str, int, float, bool, choice, path, dir}.
2. `SCHEMA: list[FieldSpec]` — the ONLY place a setting is declared. Adding a
   setting = one line here.
3. `Settings` (pure Python, no Qt): typed get/set, `validate_all()`, JSON
   `load`/`save`, env-var overrides, `reset_to_defaults()`, `on_change()`
   listeners. Pull defaults from real modules where they exist (e.g.
   `project.DEFAULT_ROOT`, `scad.openscad_bin()`, `filament_profiles
   .FILAMENT_PROFILES`).
4. `SettingsDialog(QDialog)`: auto-builds itself from `SCHEMA` — one tab per
   `group`, correct widget per `dtype` (QLineEdit+Browse for path/dir,
   QSpinBox/QDoubleSpinBox for int/float with min/max, QCheckBox for bool,
   QComboBox for choice). On Accept: validate -> write back -> autosave
   `settings.json` -> emit `applied`.

## Pitfall 1 — guarded Qt import + Pyright "possibly unbound"
```python
try:
    from PyQt6 import QtCore, QtGui, QtWidgets
    _HAS_QT = True
except Exception:
    _HAS_QT = False
...
if _HAS_QT:
    from PyQt6 import QtCore, QtGui, QtWidgets   # LOCAL re-import (NO # type: ignore!)
    class SettingsDialog(QtWidgets.QDialog): ...
```
Define the dialog class ONLY inside `if _HAS_QT:`, and do a **local** re-import
of Qt inside that block so the static analyzer sees the real types. **Do NOT put
`# type: ignore` on that local re-import** — it suppresses the binding and
re-triggers `reportPossiblyUnboundVariable` on every `QtWidgets.X` reference.

## Pitfall 2 — widget-per-dtype fall-through bug (crashes at runtime)
Never write:
```python
if f.dtype == "int": ...
else:  # float          <-- this ALSO catches str/path/dir!
    w = QDoubleSpinBox(); w.setValue(float(cur))   # cur may be a string -> ValueError
```
Use **early returns** per dtype so nothing falls through:
```python
if f.dtype == "bool":   ...; return
if f.dtype == "choice": ...; return
if f.dtype == "int":    ...; return
if f.dtype == "float":  ...; return
# else: str / path / dir  (QLineEdit)
```
The bug surfaced as `ValueError: could not convert string to float:
'/home/hunter/Desktop/...'` during dialog build — a "dir" field was routed into
the float branch.

## Pitfall 3 — QSpinBox / QDoubleSpinBox clamp silently
`spin.setValue(999)` with `setMaximum(100)` is **clamped to 100** by Qt; the
value never becomes 999, so a dialog-level `validate_all()` rejection for
out-of-range numerics essentially never fires. A pytest that does
`spin.setValue(999); _on_accept(); assert settings unchanged` will FAIL (it
writes 100). **Test the clamp** (`assert spin.value() == 100`) and keep the
model's `validate_all()` as a defensive backstop (covered by pure-Python tests).

## Headless testing (no display)
```python
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6 import QtWidgets
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])  # module-scoped singleton

pytestmark = pytest.mark.skipif(not S._HAS_QT, reason="PyQt6 not installed")
```
Drive widgets programmatically (`dlg._widgets[key].setText(...)` /
`.setValue(...)`), then call the dialog's accept handler directly and assert the
`Settings` object updated and (if autosave on) `settings.json` was written and
reloads. PyQt6 is **already installed** on this host (Qt 6.10.2; `python3`
user-site imports it) — no `pip install` (and PEP 668 blocks it anyway).

## Cross-builder probe wiring (async sibling bridge, read-only, non-blocking)
When a dialog action must touch the printer/network, REUSE a sibling builder's
existing client — do NOT open a second HTTP client. DEMIURGE3D_B09's "Test
connection" button (Settings → Printer) delegates to B01's
`MoonrakerBridge.is_alive()` / `get_klippy_state()` (a read-only `GET
/printer/info`) via a module-level `probe_moonraker_connection(url, key,
timeout, client=None)` helper in `forge/settings_ui.py`. Rules that emerged
(2026-07-11, B09↔B01 wiring task):

- **Single-client discipline.** `MoonrakerBridge` (`backend/demiurge/printer/
  moonraker_bridge.py`) is the app's ONE read-only printer-state client. The
  dialog's probe calls it; it never builds its own `urllib`/`httpx` for the same
  job. If the bridge can't be imported (minimal install / no httpx), fall back to
  a pure-stdlib `urllib` probe — but ONLY as a fallback, never the primary path.
- **Lazy import.** Import the sibling bridge inside a tiny `_import_bridge()`
  helper wrapped in try/except, so the pure-Python core (and headless
  `selfcheck()`) stays importable with no httpx and no sibling on sys.path.
- **Read-only by construction.** Only `is_alive()` / `get_klippy_state()` /
  `close()` are called. To PROVE this in a test, give the fake bridge a
  `send_gcode()` that raises `AssertionError` and assert it was never called —
  that guarantees the dialog can never move the printer (AGENTS.md safety policy
  / `CALI_DRY_RUN`). This is the binding safety evidence for any printer-touching
  UI control.
- **Async bridge from a sync slot → worker thread + signal.** `MoonrakerBridge`
  is async (`httpx.AsyncClient`); a PyQt slot is sync on the GUI thread. Do NOT
  `asyncio.run()` on the GUI thread (it freezes the dialog for the whole timeout).
  Instead:
  ```python
  class SettingsDialog(QtWidgets.QDialog):
      moonraker_result = QtCore.pyqtSignal(dict)   # result dict, NOT the bridge

      def __init__(self, ...):
          self.moonraker_result.connect(self._on_moonraker_result)

      def _test_moonraker(self):
          url = self._widgets["moonraker_url"].text().strip()
          # ... read key/timeout from widgets ...
          self._moonraker_status.setText("Testing…")
          def _worker():
              res = probe_moonraker_connection(url, key, timeout)  # asyncio.run() HERE, off-GUI
              self.moonraker_result.emit(res)
          threading.Thread(target=_worker, daemon=True).start()

      def _on_moonraker_result(self, res):   # runs on GUI thread
          ok = res.get("ok")
          self._moonraker_status.setText(("OK — " if ok else "FAIL — ") + res.get("message",""))
          self._moonraker_status.setStyleSheet("color:#2e7d32;" if ok else "color:#c62828;")
  ```
  The worker calls `asyncio.run(...)` (fresh loop per call — fine, Qt's event loop
  isn't asyncio). The result dict crosses back via the signal, so the label is
  only ever touched on the GUI thread.
- **Pyright false-positive.** `self.moonraker_result.connect(
  self._on_moonraker_result)` inside `__init__` can draw Pyright
  `reportAttributeAccessIssue: "_on_moonraker_result is unknown"`. It's a FALSE
  positive (methods exist at class-creation time, before `__init__` runs). Ignore
  it — it does not fail at runtime or under pytest.
- **Test without a printer.** `probe_moonraker_connection` takes an injectable
  `client=` (passed straight to `MoonrakerBridge(client=...)`). For the
  read-only / unreachable / fallback paths, monkeypatch the real `MoonrakerBridge`
  in `demiurge.printer.moonraker_bridge` (or monkeypatch `settings_ui._import_bridge`
  to raise) — zero network, zero hardware, deterministic. For the dialog's
  threaded path, monkeypatch `S.probe_moonraker_connection` to return a canned
  dict, then pump `QtCore.QCoreApplication.processEvents()` in a loop to let the
  signal arrive before asserting the label text.

## Targeted git commit in the parallel swarm
Each ENI mini commits ONLY its own files. After building/testing:
`git add <your module> <your test> STATUS_DEMIURGE3D_B<NN>.md && git commit` —
do NOT `git add -A`. Sibling builders (B01's `moonraker_bridge.py`, etc.) own
their own files; co-mingling their uncommitted work into your commit breaks the
per-builder revertibility the AGENTS.md checkpoint rule relies on. Verify via
`git status --short` that only your files are staged before committing.
