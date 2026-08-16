# Lazy-import display / optional backend pattern (LUMEN add-only)

## Why
A LUMEN add-only module must import with ZERO `PyQt6` / `PySide6` / `Xlib` in
`sys.modules` (the leash probe asserts this). But some features NEED a real
display at runtime — e.g. global hotkeys grab keys via Xlib `XGrabKey` on the
root window. If you `import Xlib` at module top, the import probe fails and you
violate the leash even though you never opened a display.

## Rule
Put the heavy/display import INSIDE a function (usually `__init__` of the
backend class), and only CONSTRUCT the backend lazily when the user explicitly
opts in (e.g. `HotkeyManager(backend="x11").start()`). Tests and the headless
`--self-test` use a `FakeBackend`, so the display path is never built in CI.

## Skeleton
```python
# lumen/hotkeys.py  (pure stdlib at import time — NO Xlib/PyQt at top)

class FakeBackend:
    """Tests + self-test. fire(combo) simulates a keypress."""
    def supported(self): return True
    def start(self, callback, combos): self._cb, self._combos = callback, list(combos); return True
    def stop(self): pass
    def fire(self, combo):
        if combo in self._combos and self._cb: self._cb(combo)

class NullBackend:
    """Default safe no-op. start() returns False."""
    def supported(self): return False
    def start(self, callback, combos): return False
    def stop(self): pass

class X11Backend:
    """REAL capture. Xlib imported lazily so `import lumen.hotkeys` stays clean."""
    def __init__(self):
        self._ok = False
        try:
            from Xlib import X, display          # type: ignore  (lazy!)
            from Xlib.XK import string_to_keysym  # type: ignore
            self._X = X
            self._display = display.Display()
            self._root = self._display.screen().root
            self._string_to_keysym = string_to_keysym
            self._ok = True
        except Exception:
            self._ok = False           # headless / Wayland / no X -> degrade
    def supported(self): return self._ok
    def start(self, callback, combos):
        if not self._ok: return False
        # ... grab_key per combo (see lumen/hotkeys.py for the full impl) ...
        return True
    def stop(self): pass

def _make_x11_backend():
    """Construct, degrading to NullBackend on ANY failure (never raises)."""
    try:
        return X11Backend()
    except Exception:
        return NullBackend()


class HotkeyManager:
    def __init__(self, bindings=None, bridge=None, backend="null"):
        self._backend_spec = backend          # "null" default = no display touched
        ...
    def _resolve_backend(self):
        if isinstance(self._backend_spec, str):
            name = self._backend_spec.lower()
            if name == "x11": return _make_x11_backend()
            if name == "fake": return FakeBackend()
            return NullBackend()
        return self._backend_spec
    def start(self):
        if self.running: return True
        self._backend = self._resolve_backend()
        if not self._backend.supported():
            return False                       # graceful: no capture
        ok = self._backend.start(self._on_event, [h.combo for h in self.bindings.hotkeys()])
        self.running = bool(ok)
        return self.running
```

## Verification
- Import probe must print `QT/Xlib:False`:
  `QT_QPA_PLATFORM=offscreen DISPLAY= .venv/bin/python -c "import sys, lumen.<mod>; print('QT/Xlib:' + str(any(m.split('.')[0] in ('PyQt6','PySide6','Xlib') for m in sys.modules)))"`
- Tests construct `FakeBackend` (or monkeypatch `_make_x11_backend` to raise and
  assert `start()` returns False) — they NEVER build `X11Backend`.
- mypy on the module needs `--ignore-missing-imports` because Xlib ships no stubs.

## Gotchas
- Reusing a loop variable name then reassigning it to another type will trip
  mypy ("Incompatible types in assignment"). Rename the loop var.
- After editing, `rm -rf .mypy_cache` before re-running mypy — the incremental
  cache can report stale errors.
- Don't compare `format(*parse(raw)) == raw` for identity: canonicalization
  reorders/normalizes (e.g. "Win+R" -> "Super+R"). Round-trip test must RE-PARSE.
