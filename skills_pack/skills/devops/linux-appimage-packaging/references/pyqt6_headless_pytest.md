# PyQt6 headless pytest — modal-dialog hang fix + slow-box wide-suite run

## The problem (Lumen 2026-07-12)
A full `pytest` of a PyQt6 app froze at 0% CPU and never completed. Root cause:
a product code path (SettingsPage._reset_all) called `QMessageBox.question(...)`
to confirm a destructive action. Under `QT_QPA_PLATFORM=offscreen` no native
dialog is ever dismissed, so the call blocks forever and the whole suite hangs.

This is a HARNESS problem, not a product bug. The dialog is correct UX for a
real user. Do NOT remove or guard the product call to make tests pass — fix the
test harness instead (below).

## The fix — conftest autouse fixture (stub modals when offscreen)
Add to `tests/conftest.py`:

```python
import os
import pytest
from PyQt6 import QtWidgets
from PyQt6.QtWidgets import QMessageBox, QDialog, QFileDialog

@pytest.fixture(autouse=True)
def _headless_dialog_guard():
    """Auto-confirm native modal dialogs under offscreen Qt so pytest can't hang."""
    if os.environ.get("QT_QPA_PLATFORM") != "offscreen":
        yield
        return
    _orig_q = QMessageBox.question
    _orig_exec = QDialog.exec
    _orig_get = QFileDialog.getOpenFileName

    def _fake_question(*a, **k):
        return QMessageBox.StandardButton.Yes
    QMessageBox.question = staticmethod(_fake_question)
    QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
    QMessageBox.critical = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
    QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
    QDialog.exec = lambda self, *a, **k: 0   # exec() returns int in PyQt6
    QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: ("/tmp/fake", ""))
    QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: ("/tmp/fake", ""))
    try:
        yield
    finally:
        QMessageBox.question = staticmethod(_orig_q)
        QDialog.exec = _orig_exec
        QFileDialog.getOpenFileName = staticmethod(_orig_get)
```

Notes:
- `QDialog.exec` (not `exec_`) — see the rename gotcha below.
- Restore originals in `finally` so an interactive (non-offscreen) run still shows real dialogs.
- Stub ONLY under `offscreen`; a real GUI test (if you ever run one) keeps native dialogs.
- If any product test asserts on dialog *content* (rare), narrow the stub or use a
  `monkeypatch` fixture scoped to that one test instead of the global autouse.

## PyQt6 rename gotcha (test code)
PyQt6 RENAMED the old `exec_` / `show_` Qt4/Qt5 methods to `exec` / `show`
(dropping the trailing underscore). Test/helper code that calls `dialog.exec_()`
raises `AttributeError: 'QDialog' object has no attribute 'exec_'`. Use `exec()`.
(Modern product code already uses `exec`; legacy test helpers may not — the
Lumen conftest hit exactly this and had to drop an `exec_` line.)

## Running a WIDE / SLOW suite on the slow box
PyQt6 suites import heavy (sklearn / pandas / PyQt6) — ~5 s/test. A full run can
exceed any foreground timeout and may not survive a context-compaction boundary.
Pattern that worked (Lumen 1028 tests ~27 s; stockbot suite is wider/slower):
- Run with `QT_QPA_PLATFORM=offscreen` (no display needed).
- Run in BACKGROUND with a long timeout — never foreground-block:
  `terminal(background=true, notify_on_complete=true, timeout=900, command="...")`.
- Use `-rfE --tb=line` so the summary lists EVERY failure name even if the run is
  killed at the timeout — you get the diagnosis, not just a `124` exit.
- Capture to a log: `... -rfE --tb=line > /tmp/<app>_test.log 2>&1`.
- A 500 s-capped run may only reach ~66% — that's fine; the `-rfE` summary still
  names the failing tests so you can triage core vs env-dependent failures.

## Quality bar (LO's standing rule for build/verify tasks)
"100% working, bug free, world-class" means: FIX the real bug behind a failing
test, do NOT relax/delete the test to make it green. Distinction:
- **Real product/logic bug** (e.g. `needs_migration` ignoring engine drop-steps,
  `self_test` false-positive under a Qt-loaded harness, missing pyproject asset
  globs) → fix the SOURCE.
- **Harness artifact** (modal blocks headless, `exec_` rename, import-mode
  `isinstance` mismatch) → fix the HARNESS, keep the test.
- **Network / OANDA / timing-dependent tests** that fail without creds/network →
  document as env-limited, not a product defect; do not gut core logic to please
  the suite. (Reuse sourced `.env` creds where available, but never call sudo/apt.)
