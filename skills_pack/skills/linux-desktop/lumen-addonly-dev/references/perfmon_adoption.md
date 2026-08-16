# Adopting `lumen/perfmon.py` — the live telemetry bridge (consume-but-never-produce gap)

## Why it was the highest-value gap
The master's stability stack had four tested layers but a MISSING LINK:
- `recommend` — static fit (what the GPU can hold)
- `auto_tune` — proactive governor (`govern(snap) -> List[TuneAction]`)
- `stability_report` — what-if simulation
- `watchdog` / safety — reactive guard

`auto_tune.govern()` and `stability_report.simulate()` BOTH consume a
`PerfSnapshot`, but NOTHING in the repo produced one from the live box, and
`perfmon.py` had ZERO tests. A type that is **REFERENCED by siblings but never
CONSTRUCTED/TESTED** is the richest audit target: it is pure ADD (a test file +
a minimal in-module fix), needs zero core edits, and it completes an
end-to-end chain. When resuming and your assigned module is already DONE
(STATUS `[state: DONE]`), this "missing link" scan is the fastest way to the
next highest-value ADD-ONLY task.

## The bug that shipped (and how it hid)
`perfmon.py` declared dataclasses with BOTH a public field and a public method
of the same name (e.g. `max_webgl_surfaces: int = 1` AND
`def max_webgl_surfaces(self)`). In a dataclass the method OVERWRITES the
field's default slot, so `__init__` stored the FUNCTION as the attribute:
- `ProcSource.max_webgl_surfaces()` raised
  `"missing 1 required positional argument: 'self'"` (hard crash), and
- `SyntheticSource`'s protocol methods SILENTLY returned bound methods
  (callables) instead of values, corrupting every `PerfSnapshot`.

There were no tests, so the corruption was invisible until `--self-test`
probed it. Fix (in-module, leash-safe): private `_`-backed fields; protocol
methods `return self._field`; `SyntheticSource` keeps its public kwargs via a
custom `__init__` so call sites are unchanged. See the dedicated dataclass
collision pitfall in SKILL.md.

## Headless testability of the live source
`AutoTuner` needs a REAL `PerfSnapshot`. Achieve this headlessly with a
`SyntheticSource` test double implementing the same `DataSource` protocol as
`StatusListener` (the intended live source). `StatusListener` is the only part
that needs LO's real desktop; everything else is pure + `SyntheticSource`-driven.
This lets `tests/test_perfmon.py` lock: source construction, snapshot building,
the `AutoTuner` hysteresis window, `recommend`/`auto_tune` integration against a
produced snapshot, and graceful degradation when `StatusListener` is
unavailable.

## Regression proof (leash + no sibling breakage)
- Import probe (FRESH subprocess — never in-process, the conftest already has
  PyQt in `sys.modules`):
  ```python
  python -c "import sys; import lumen.perfmon; print('QT', [m for m in sys.modules if m.startswith(('PyQt6','PySide6','Xlib'))])"
  ```
  -> `QT []` (zero Qt; app never opened).
- Full suite: `pytest -q` -> count passes; for any pre-existing failure,
  `grep -c perfmon tests/test_<failing>.py` == 0 => 0 LM0x regressions.
- Gates: pytest (30 passed) + flake8 clean + mypy clean (with
  `--follow-imports=silent` to bill only `perfmon.py`) + importlint clean.

## Leash-safe FIX shape (no core edit)
- `lumen/perfmon.py` (harden orphan: private fields, guarded `assert` on
  `Optional[PerfSnapshot]` before attribute access) + `tests/test_perfmon.py`
  (add). That is the entire diff. Proven core + all siblings untouched.
