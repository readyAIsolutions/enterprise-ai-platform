# Headless simulator & Qt-free gate for LUMEN ADD-ONLY modules

Condensed, reusable technique for building a CODE-ONLY, leash-safe LUMEN
sub-module that proves behaviour without ever launching the GUI.

## The zero-Qt import gate (MUST pass for any new module)
A new module must be importable in a FRESH interpreter with zero PyQt/PySide
symbols in `sys.modules`. This is the hard leash gate — if your module
transitively imports Qt, a future core wiring could launch a display. Verify
with a SUBPROCESS test, NOT an in-process assertion: LUMEN's offscreen conftest
already has PyQt in `sys.modules` for the whole session, so an in-process
`assert 'PyQt6' not in sys.modules` gives false failures on unrelated modules.

```python
def test_module_imports_without_qt():
    code = (
        "import sys, importlib\n"
        "mod = importlib.import_module('lumen.<module>')\n"
        "qt = [m for m in sys.modules if m.split('.')[0] in "
        "('PyQt6','PyQt5','PySide6','PySide2')]\n"
        "print('QT', qt)\n"
        "print('OK', hasattr(mod, 'simulate'))\n"
    )
    out = subprocess.run([sys.executable, "-c", code],
                         cwd=REPO, capture_output=True, text=True)
    assert out.returncode == 0
    assert "QT []" in out.stdout
```
Run under `QT_QPA_PLATFORM=offscreen DISPLAY=` so even an accidental Qt import
fails loudly instead of grabbing LO's X.

Rule of thumb for imports:
- Import only `lumen.perf` at module TOP (proven Qt-free).
- `lumen.auto_tune` is Qt-free (imports `lumen.perf` only) — safe to import at
  top. It exposes `PerfSnapshot`, `WallpaperLoad`, `TuneAction`, `govern`,
  `apply_plan`, `AutoTuner`, `plan_text`, `self_test`.
- `lumen.recommend` is Qt-free at top (imports `lumen.perf`; it imports
  `lumen.config` ONLY lazily inside `profile_from_config`). Still, lazy-import
  it inside the single function that needs it so the zero-Qt gate is
  bulletproof: `from lumen import recommend` inside `propose_*()`.
- Any sibling that pulls `lumen.config` or Qt at import time MUST be imported
  lazily inside the function that uses it.

## Reuse a 1-shot governor as a virtual-clock simulator
When a sibling already provides a pure decision engine over a single snapshot
(e.g. `auto_tune.govern` / `AutoTuner` / `apply_plan`), build a what-if TIME
simulator WITHOUT touching core:
1. Define `Scenario` + `build_snapshot(scn)` that materialises the assignment
   into the engine's snapshot type. Honour the engine's caps — e.g.
   `max_webgl_surfaces`: only N of the LARGEST screens get a live WebGL surface;
   the rest are forced to image fallbacks (exactly what the live engine does).
2. Loop `ticks`: `actions = AutoTuner(window).feed(snap)` ->
   `snap = apply_plan(snap, actions)` -> normalise any side-effects the apply
   step didn't perform (e.g. `apply_plan` mutates wallpaper *kinds* but leaves
   surface count; set `snap.webgl_surfaces = count of webgl` so your RSS model
   stays honest) -> recompute RSS from YOUR model -> record the step.
3. Optionally inject a "storm" every K ticks (swap the heaviest live surface for
   a heavier asset / raise its resolution) to stress-test the worst case.
4. Emit a verdict + the RSS trajectory. This is the headless proof that a
   MASTER-sanctioned live wiring of the same engine would keep the box safe.

## Coefficient-matching trick (consistent models)
If your absolute RSS model must agree with the engine's relief deltas (so the
two don't diverge), reuse the SAME per-unit coefficients. `auto_tune.apply_plan`
relieves: 350 MB per dropped WebGL surface, 6 MB per fps (FPS_STEP=5 => 30),
200 MB per dpr step (DPR_STEP=0.25 => 50). Mirror those exactly in
`model_rss`. Add a fragment term calibrated from `lumen.perf.gpu_fragment_load`
(`PER_FRAG_MB ~ 1.5e-6` gives a heavy 2560x1080@30,dpr1.5 shader ~= 280 MB).
Calibrate so a default 1-surface config lands ~1500–1600 MB (well under the
2200 ceiling) and a 4-surface overload lands > ceiling so the governor must
pause. Thresholds (RSS_CEILING 2200, RSS_CRIT 2000, RSS_WARN 1700) should
mirror `app.py`'s watchdog so every layer agrees.

## Regression-isolation verification (prove you added zero failures)
Always run the FULL suite, but to prove your module introduced no regressions:
run the failing sibling suites with YOUR OWN test file EXCLUDED (so your module
+ its imports are never loaded, via `--ignore=tests/test_<yours>.py`). If they
still fail identically, they are pre-existing — flag for owners, don't fix
(out of scope). Report the honest count in the STATUS board. Note: the offscreen
conftest leaks a QApplication into `sys.modules` for the whole session, so any
"no Qt in sys.modules" assertion in OTHER test files is a known false-fail
artifact — not your defect.

## Verdict shapes for the stability story
STABLE (no governor action) | DEGRADES_GRACEFULLY (caps/downgrades, never
pause) | DEGRADES_TO_PAUSE (box only saved by pausing everything — risky
config) | REBOOT_RISK (even pause couldn't hold the ceiling — pathological).
Pair the simulator with `lumen.recommend.auto_assign` to propose the proven
AMD-safe fix: drop `max_webgl_surfaces` to 1 + pick the lightest per-screen
mix.
