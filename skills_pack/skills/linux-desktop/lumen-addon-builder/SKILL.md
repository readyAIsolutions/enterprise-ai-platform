---
name: lumen-addon-builder
description: >-
  Build ADD-ONLY sub-modules for LUMEN (PyQt6 WebGL Linux wallpaper engine) as
  an autonomous swarm mini (LMxx/ENIxx). Covers the hard CODE-ONLY leash (never
  launch the GUI / grab X/WebGL), unclaimed-module selection, headless-only
  testing (QT_QPA_PLATFORM=offscreen + pytest/flake8/mypy), and the mandatory
  STATUS_<ID>.md format. Use when extending LUMEN without touching core.
---

# lumen-addon-builder

Build ADD-ONLY sub-modules for LUMEN (PyQt6 WebGL wallpaper engine) as an
autonomous swarm mini (LMxx / ENIxx). Hard leash: the app is NEVER launched.
Headless tests only.

## WHEN TO USE
- A task says "swarm builder", "mini-ENI", "add-only sub-module for LUMEN", or
  asks to extend LUMEN without touching core.
- You are one of several parallel builders on `/home/hunter/Desktop/apps/lumen`
  and must claim an unclaimed module and leave a `STATUS_<ID>.md`.

## THE LEASH (SAFETY CRITICAL — never violate)
LUMEN has crashed LO's AMD RX 5700 XT multi-monitor box by grabbing the X
display / WebGL context. Therefore, CODE-ONLY:
- NEVER run `python -m lumen`.
- NEVER open the GUI / PyQt app, never let it grab the X display or a
  WebGL/GPU context (it has rebooted the box before).
- ALLOWED: edit/fix/harden modules, `pytest`, `flake8`, `mypy`, import-smoke
  (under `QT_QPA_PLATFORM=offscreen`).
- The app stays CLOSED for the whole session.

## ORIENT (first 2 minutes)
1. Read `STATUS_LUMEN.md` (master board): conventions, claimed modules, the
   standing STATUS shape (PASS/FAIL board with REAL numbers, `what adds R /
   what to drop`, UNVALIDATED).
2. `search_files` the repo for `STATUS_*.md`, read each header to see what
   sibling minis already own. Do NOT claim a module a sibling touched.
3. List `lumen/**/*.py` to see existing modules.
A current claimed-map lives in `references/headless_testing.md`.

## PICK A MODULE (prefer a NEW file)
- Strongest add-only move: create a brand-new `lumen/<new>.py` that did not
  exist. Zero collision risk, clearly add-only, no sibling conflict.
- If you must extend an EXISTING non-core module (e.g. `doctor.py`,
  `autostart.py`, `utils/wayland.py`), confirm it is NOT in a sibling's
  claimed set first.
- NEVER touch core: `config.py`, `engine.py`, `app.py`, `lumen/__main__.py`,
  `ui/main_window.py`, `wallpaper/webgl_engine.py`, `wallpaper/web.py`.
- Extending `__main__.py` for a CLI is FORBIDDEN under add-only even though
  it's "just the entry point" — leave CLI wiring to a sibling.
- Read-only imports from `lumen.config` are fine (constants like
  `LIBRARY_DIR`, `CONF_FILE`, `DATA_DIR`).

## BUILD (headless by construction)
- Pure-stdlib modules (zipfile/hashlib/json/pathlib) need NO Qt and are fully
  headless-testable — preferred.
- Any function that touches the filesystem must accept its paths as PARAMETERS
  so tests can inject `tmp_path` and never touch LO's real
  `~/.local/share/lumen`.
- Keep logic hermetic: no network, no display.

## QT-FREE IMPORT DISCIPLINE (the zero-Qt gate)
The single most important leash gate for a new module: it must be importable in
a FRESH interpreter with ZERO PyQt/PySide in `sys.modules` (a future core
wiring must never be able to launch the display through your module). Verify it
with a SUBPROCESS test, NOT an in-process assertion — LUMEN's offscreen conftest
already has PyQt in `sys.modules`, so an in-process `assert 'PyQt6' not in
sys.modules` is a false-fail on unrelated modules. Full recipe + snippet:
`references/headless_simulator.md`. Import rule of thumb: import only
`lumen.perf` at top (Qt-free); `lumen.auto_tune` is Qt-free and safe to import
at top; `lumen.recommend` pulls `lumen.config` but only lazily inside
`profile_from_config`, so import it lazily inside the one function that needs
it. Anything that imports `lumen.config` or Qt at import time MUST be a lazy
function-local import.

## REUSE EXISTING MACHINERY (don't reimplement the engine)
LUMEN already ships pure, Qt-free decision engines you can drive headlessly:
- `lumen.auto_tune` — `govern(snap)` returns reversible `TuneAction`s for one
  snapshot; `AutoTuner(window)` adds hysteresis; `apply_plan(snap, actions)`
  returns a simulated post-action snapshot. These are the EXACT machinery a
  MASTER-sanctioned live wiring would run, so you can build a what-if TIME
  simulator by looping them on a virtual clock (feed -> apply_plan ->
  normalise -> recompute RSS -> record). See `references/headless_simulator.md`.
- `lumen.recommend` — `auto_assign(wallpapers, profile)` bin-packs one wallpaper
  per screen under the GPU fragment budget; reuse it to PROPOSE a safe
  assignment when your simulator flags a risky config.
- `lumen.perf.gpu_fragment_load(w,h,fps,dpr)` — the single source of truth for
  "how heavy is this"; reuse it (don't recompute) so your numbers match the
  live engine, `recommend`, and `auto_tune`.

## TEST
Create `tests/test_<module>.py` next to it. Pattern proven in-suite:
- `import lumen.<module>` directly (do NOT go through `python -m lumen`).
- Drive every function against `tmp_path` fixtures (a fake library/config
  copied in).
- Cover the safety properties: atomic write, checksum verify,
  rollback-on-failure, merge-vs-force, prune, reject-oversized-input.
- Run (the venv is at `.venv`, python3 symlink; run from repo root):
  ```
  cd ~/Desktop/apps/lumen
  QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_<module>.py -v
  .venv/bin/python -m flake8 lumen/<module>.py tests/test_<module>.py
  .venv/bin/python -m mypy lumen/<module>.py
  QT_QPA_PLATFORM=offscreen .venv/bin/python -c "import lumen.<module>"
  ```
  All four must be green: pytest 0 fail, flake8 exit 0, mypy "no issues
  found", import OK.

## STATUS FILE (required deliverable)
Write `/home/hunter/Desktop/apps/lumen/STATUS_<YOURID>.md` from
`templates/STATUS_LMxx.md`. Mandatory shape:
- **Line 1: `[state: DONE|IN-PROGRESS|BLOCKED]`**
- A PASS/FAIL board with REAL numbers (test counts, exit codes, byte sizes)
  as evidence — never vague.
- A `what adds R / what to drop` list.
- An `UNVALIDATED` section for anything that needs LO's real desktop (e.g.
  live CLI wiring).

## PITFALLS (learned the hard way)
- `__version__` lives in the `lumen` package `__init__.py`, NOT
  `lumen.config`. `from lumen.config import __version__` raises
  `ImportError`. Use `from lumen import __version__`.
- `mypy`: `fd, tmp = tempfile.mkstemp(...)` types `tmp` as `str`;
  reassigning `tmp = Path(tmp)` is an "incompatible types" error. Unpack into
  `tmp_fd, tmp_name = tempfile.mkstemp(...)` then `tmp = Path(tmp_name)`.
- LUMEN's offscreen test harness sets `QT_QPA_PLATFORM=offscreen` and pops
  `DISPLAY`; always run pytest with that env so a test never reaches LO's
  real X.
- **Regression-isolation**: to prove you introduced ZERO new failures, run the
  failing sibling suites with YOUR test file EXCLUDED
  (`--ignore=tests/test_<yours>.py`) so your module is never imported. If they
  still fail identically, they are pre-existing — flag for owners, don't fix.
  (The offscreen conftest's leaked QApplication makes any "no Qt in
  sys.modules" assertion in OTHER test files a known false-fail, not your bug.)
- **Coefficient-matching**: when your absolute RSS/model must agree with an
  existing module's relief math, reuse its exact per-unit coefficients (e.g.
  `auto_tune.apply_plan` relieves 350 MB/surface, 6 MB/fps, 200 MB/dpr). See
  `references/headless_simulator.md`.
- When globbing/walking the library, skip scratch dirs `cache` and
  `_import_tmp`.
- Don't wire a CLI into `__main__.py` to "finish" a feature — that breaks
  add-only. Document the intended CLI in the STATUS file instead and leave it
  for a sibling.

## REFERENCES
- `references/headless_testing.md` — exact recipe, the `__version__`/mkstemp
  gotchas, and a worked map of already-claimed LUMEN modules.
- `references/headless_simulator.md` — the zero-Qt fresh-interpreter gate, the
  reuse-a-governor-as-a-virtual-clock simulator pattern, coefficient-matching,
  and regression-isolation verification.
- `templates/STATUS_LMxx.md` — starter STATUS file with the required line-1
  marker and board skeleton.
