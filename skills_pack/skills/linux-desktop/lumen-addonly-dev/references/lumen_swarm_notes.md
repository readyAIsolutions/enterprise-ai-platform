# LUMEN swarm add-only — reference notes

## Claimed sub-modules SNAPSHOT (2026-07-11, workspace-4 pass)
Re-check live before picking — the swarm map drifts. Read every `STATUS_*.md`
in the repo root; do NOT claim something already owned. As of this pass:

| Builder | Module | Notes |
|---------|--------|-------|
| B01 | `lumen/wallpaper/webgl_engine.py` | dedicated WebGL engine + user uniforms |
| B05 | `lumen/samples_pack.py` | sample wallpapers + preview PNGs + dist pack |
| B09 | `lumen/safe_mode.py` | boot safe-mode lifecycle over BootGuard |
| ENI63 | `lumen/ui/browser.py` (SettingsPage) | settings panel hardened/polished |
| ENI9 | white-screen fix | edited `webgl_engine.py`/`web.py` child-view flag (code-only, unrun) |
| ENI_LUMEN | `tests/test_engine.py` | engine regression suite (core logic) |
| LM13 | `lumen/slideshow.py` | slideshow/randomizer SCHEDULING engine (this pass) |

Unclaimed-but-referenced gaps seen this pass: slideshow *logic* (config had
`slideshow_*` keys, no consumer), time-of-day scheduling, engine `set_slideshow`
/ `randomize_now` hooks (core edit — leave to master).

Good add-only targets: pure, headless-testable logic layers that existing
config/UI points at but does not exist. Avoid anything that must import PyQt /
QWebEngine / grab X.

## Pitfall #1 — half-open interval overlap (abutting windows)

Bug: a `_overlaps(a0,a1,b0,b1)` that tested "is endpoint of B inside A" using
`lo <= x < hi` falsely flagged adjacent windows `06:00-12:00` and `12:00-18:00`
as overlapping, because `a1 == b0 == 12:00` satisfies `12 <= 12 < 18`.

WRONG (endpoint-in-range):
```python
def contains(lo, hi, x):
    if lo < hi:
        return lo <= x < hi
    return x >= lo or x < hi
return contains(a0,a1,b0) or contains(a0,a1,b1) or contains(b0,b1,a0) or contains(b0,b1,a1)
```

RIGHT (minute-intersection; shared boundary ABUTS, does not overlap):
```python
@staticmethod
def _minutes_of(start, end):
    if start < end:
        return range(start, end)
    return list(range(start, 1440)) + list(range(0, end))   # wraps midnight

def _overlaps(self, a0, a1, b0, b1):
    bwin = _Window(b0, b1, None)
    for m in self._minutes_of(a0, a1):
        if self._in_window(bwin, m):     # half-open: start<=m<end (or wrap)
            return True
    return False
```
General rule: two half-open intervals [a0,a1) and [b0,b1) overlap iff they share
ANY interior point; boundaries are not shared. Iterate the (bounded, <=1440)
minute set for correctness.

## Pitfall #2 — testing a CLI `--self-test` exit code

Bug: a test that monkeypatched `mod.self_test` to force FAIL, then ran
`subprocess.run([sys.executable, "-m", "lumen.<mod>", "--self-test"])` and
asserted `returncode == 1`. It got `0` — the child interpreter does NOT inherit
the parent's monkeypatch.

WRONG (subprocess can't see the patch):
```python
mod.self_test = lambda: (False, "forced")
proc = subprocess.run([sys.executable, "-m", "lumen.<mod>", "--self-test"], ...)
assert proc.returncode == 1   # FAILS: child runs the real self_test -> 0
```

RIGHT (call `_main` IN-PROCESS — it looks up the module global at call time, so
the patch applies):
```python
real = mod.self_test
mod.self_test = lambda: (False, "forced")
try:
    self.assertEqual(mod._main(["--self-test"]), 1)
finally:
    mod.self_test = real
```
Keep the real subprocess test too (it proves the entry point wiring), but drive
the failure branch in-process.

## Determinism recipe
- Every scheduler method takes `now: Optional[float] = None`; the live path
  defaults to `time.monotonic()`, tests pass explicit values.
- RNG seeded: `random.Random(seed)`; expose `seed` in the constructor so a
  "random" sequence is reproducible and testable.
- Never call `time.time()`/`time.monotonic()` inside the test-exercised path.
