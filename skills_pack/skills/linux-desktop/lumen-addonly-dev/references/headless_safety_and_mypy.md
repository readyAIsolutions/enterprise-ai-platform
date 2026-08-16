# LUMEN add-only — headless safety, mypy, gap strategy (LM16 pass learnings)

## Pitfall #3 — conftest's offscreen QApplication makes in-process "no Qt" checks LIE

The LUMEN repo's `tests/conftest.py` force-sets `QT_QPA_PLATFORM=offscreen` and
strips `DISPLAY`, AND it constructs a `QApplication` at session start (so the
offscreen UI tests can run). That means during ANY pytest run, `PyQt6` IS already
in `sys.modules` for the whole session.

Bug: a test like `test_module_imports_without_qt` that does
`assert not any(m.startswith("PyQt") for m in sys.modules)` FAILS — not because
your module imported Qt, but because conftest already loaded it. This is a
TEST-ISOLATION artifact, not your defect (seen live:
`test_profiles.py::test_module_imports_without_qt` fails this way every run).

RIGHT — prove Qt-freeness of YOUR module in a FRESH interpreter that never sees
the conftest QApplication:
```python
def test_module_imports_without_qt():
    script = (
        "import sys; import lumen.<mod>; "
        "q=[m for m in sys.modules if m.startswith('PyQt') "
        "or m.startswith('PySide')]; "
        "print('QT', q)"
    )
    out = subprocess.run([sys.executable, "-c", script],
                         capture_output=True, text=True, cwd=".")
    assert out.returncode == 0
    assert "QT []" in out.stdout
```
Also verify the IMPORT CHAIN is pure: `lumen/__init__.py` is pure (no Qt), and
your module should import ONLY stdlib + `from lumen import perf` (perf.py is
stdlib-only — no PyQt). Reusing `lumen.perf.gpu_fragment_load` is the sanctioned
way to stay Qt-free AND keep weight math identical to the live engine.

## Pitfall #4 — mypy fails on SIBLING type errors, not yours

`from lumen import perf` (or any sibling) drags that sibling into mypy's descent.
If the sibling has a pre-existing annotation gap (live example:
`lumen/perf.py:489` — `FrameStatsCollector._buf` needs a type annotation), a bare
`mypy lumen/<yourmod>.py` reports THAT error and looks like YOUR failure.

RIGHT — bill your own file clean without masking real sibling issues:
```bash
.venv/bin/python -m mypy lumen/<yourmod>.py \
    --ignore-missing-imports --follow-imports=silent
# -> Success: no issues found in 1 source file
```
`--follow-imports=silent` stops mypy from type-checking imported siblings; it
still checks YOUR file fully. Flag the sibling error to its owner — do NOT patch
a file you don't own (ADD-ONLY).

## Domain context — LUMEN's three-tier AMD-stability architecture

When picking a gap, understand the existing layers so you build the MISSING one
instead of re-implementing a sibling:

1. **STATIC fit** — `lumen/recommend.py` (LM10): given screen geometry + caps,
   answers "which wallpapers fit the GPU budget?" Greedy, never blank (falls back
   to lightest). Pure; reuses `perf.gpu_fragment_load`.
2. **REACTIVE drop** — `app.py` + `safety.py` + `engine.drop_all_to_safe()`:
   boot-guard disables wallpapers after a crash; a 3 s watchdog calls
   `drop_all_to_safe()` once process RSS passes **2.2 GB**. Only fires AFTER the
   box is in danger.
3. **PROACTIVE governor** — `lumen/auto_tune.py` (LM16): watches live RSS /
   delivered-FPS / drop-rate / WebGL-surface count and steps quality DOWN *before*
   the 2.2 GB line (cap FPS, cap DPR, swap heavy shader -> image fallback, drop a
   WebGL surface, pause). Pure decision engine; applying is a MASTER-sanctioned
   core push.

Other shipped pure layers: `scheduler.py` (time-of-day/weekday/power),
`slideshow.py` (rotation scheduling), `library_backup.py`, `rpc.py` (localhost
HTTP control), `doctor.py`, `manifest_lint.py`, `library_stats.py`,
`wallpaper_index.py`, `profiles.py`, `presets.py`, `gallery_export.py`,
`samples_pack.py`. Grep the repo + read every STATUS_*.md before claiming.

## Gap strategy — target the MISSING LAYER of the #1 product risk

Don't just grep for "config key with no consumer." Read the MASTER
`STATUS_LUMEN.md` first: it names the headline product risk (for LUMEN it is
"Lumen reboots LO's AMD box"). Then ask: which layer of the defence for THAT risk
is ABSENT? In LM16's pass the static recommender and reactive watchdog existed,
but nothing watched live signals proactively — that missing layer
(`auto_tune`) was the highest-value unclaimed target. This "find the missing
layer of the documented #1 risk" move beats random gap-grepping.

## Reusable design patterns (ADD-ONLY, headless)

- **Decision vs effect-simulation separation**: a governor/action module should
  expose `govern(snapshot) -> List[Action]` (pure decision) AND
  `apply_plan(snapshot, actions) -> Snapshot` (pure arithmetic simulation of the
  result, NO engine/X). Tests prove idempotency
  `govern(apply(govern(x))) == []` and the CLI can dry-run "if we did this, RSS
  would drop to X" — both fully headless.
- **Hysteresis wrapper for noisy signals**: wrap the pure decision in a stateful
  `AutoTuner(window=N)` that only acts after `N` consecutive warn/starve samples,
  but acts IMMEDIATELY on a critical reading. Prevents a one-off spike from
  degrading the user's chosen wallpaper. Reset clears history.
- **CLI surface**: `--self-test` (exit 0/1 liveness probe), `--demo` (print a
  canned plan), `--plan` (read a JSON snapshot from `--snapshot FILE` or stdin
  and print actions + modelled relief). All headless, never touch X/WebGL/config.
