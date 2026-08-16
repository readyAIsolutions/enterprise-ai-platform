# Library integrity / repair ADD-ONLY module (LUMEN)

Pattern distilled from `lumen/library_repair.py` (LM01, 2026-07-11). Use it
to build the next library-hygiene module. The family already has
`library_backup` (save) / `library_dedup` (prune) / `library_repair`
(correct); a 4th is `library_audit` (read-only classify:
HEALTHY/BROKEN/UNRENDERABLE/EMPTY/ORPHAN — see the AUDIT VARIANT section
below); others could be `library_organize` (smart collections) or
`library_share` (portable pack export).

## Shape
- Pure stdlib at module TOP. No Qt/X11 import at top level.
- Public API: `scan(root) -> IntegrityReport` (read-only walk),
  `build_repair_plan(report, protect_ids=None, stat_store=None) ->
  List[RepairAction]`, `repair(plan, root, *, dry_run=True) ->
  RepairResult`, and `self_test() -> Tuple[bool, str]`.
- Findings carry `severity` (error = unloadable / warning = degraded) and
  `repairable` + `repair_kind`. The plan only includes repairable findings.
- `repair` DEFAULTS to `dry_run=True` — it never mutates unless the caller
  passes `dry_run=False`.

## Safety invariants (leash + data)
- Every write target is `is_relative_to(root)`-checked; an escape attempt is
  recorded as an ERROR and never executed.
- Repairs that overwrite a manifest first back it up to
  `<name>.lumen.json.bak`.
- Favorites are never auto-repaired: accept `protect_ids` AND a duck-typed
  `stat_store` with a `favorite_ids()` method; union them into the protect
  set. No hard dependency on `library_stats`.
- No core/sibling file edited (strictly ADD-ONLY).

## GOTCHAS (the three that burned a cycle)
1. `from lumen.wallpaper.model import Wallpaper` at TOP LEVEL pulls PyQt6 +
   QtWebEngine + Xlib — the `lumen.wallpaper` package `__init__` imports
   the engine. That fails the leash subprocess probe. Lazy-import the model
   INSIDE the renderability helper only.
2. When building `Wallpaper(root, meta)` for an `is_renderable()` check,
   pass the REAL scan root and force `meta["id"] = folder.name`, or paths
   resolve against `LIBRARY_DIR` and you get FALSE `non_renderable` findings
   on temp dirs.
3. mypy: `manifest_path = lumen or project` stays `Path | None` even after
   an earlier `continue` on the all-None branch. Add an explicit
   `if manifest_path is None: continue` to narrow the type.

## Verification (4 gates + leash)
```bash
.venv/bin/python -m pytest tests/test_<mod>.py -q
.venv/bin/python -m flake8 lumen/<mod>.py tests/test_<mod>.py
.venv/bin/python -m mypy --follow-imports=skip lumen/<mod>.py
.venv/bin/python -m importlint check lumen/<mod>.py tests/test_<mod>.py
# Qt-freeness (FRESH subprocess, NOT in-process):
QT_QPA_PLATFORM=offscreen DISPLAY= .venv/bin/python -c \
  "import sys, lumen.<mod>; bad=any(m.split('.')[0] in ('PyQt6','PySide6','Xlib') for m in sys.modules); print('QT/XLIB:'+str(bad))"
# expect: QT/XLIB:False
```

## Headless demo (never opens the app)
```bash
.venv/bin/python -m lumen.library_repair --scan <dir> --json   # read-only
.venv/bin/python -m lumen.library_repair --repair <dir>         # dry-run
.venv/bin/python -m lumen.library_repair --repair <dir> --apply # real
```

## AUDIT (read-only classifier) VARIANT — and the UNRENDERABLE divergence
`lumen/library_audit.py` (LM10, 2026-07-11) is the read-only 4th member of the
family: it CLASSIFIES every library entry instead of repairing it. The taxonomy
that proved useful (reuse it):

  HEALTHY      lint clean AND Wallpaper.is_renderable() is True
  BROKEN       manifest present but any lint ERROR (schema/disk/MEDIA_MISSING)
  UNRENDERABLE lint CLEAN but engine.is_renderable() is False   <-- the catch
  EMPTY        a directory with no lumen.json / project.json
  ORPHAN       a loose file sitting directly in the library root

Precedence when classifying a folder:
  EMPTY (only a NO_MANIFEST error) > BROKEN (any lint error) >
  UNRENDERABLE (lint clean but not renderable) > HEALTHY.

THE divergence that makes the audit worth building (manifest_lint ALONE MISSES
it): an `image` wallpaper whose declared `preview` is MISSING but the folder
contains ANOTHER image file. `manifest_lint._lint_disk` for `image` only ERRORS
when NO image file exists anywhere in the folder — so it PASSES. But
`Wallpaper.is_renderable()` for the `image` kind returns `preview_path is not
None`, and `preview_path` resolves the DECLARED `preview` (missing) -> False.
Result: lint PASS, engine BLANK. The audit flags UNRENDERABLE. Reproduce in a
test with `lumen.json {"kind":"image","preview":"missing.png"}` plus a sibling
`fallback.jpg` in the same folder — expect UNRENDERABLE, NOT BROKEN.

PURE-STDLIB renderability fallback (keeps the module headless even at RUNTIME
on a Qt-less host): lazily `try: from lumen.wallpaper.model import Wallpaper`;
if that raises (PyQt absent), fall back to a local
`_heuristic_renderable(meta, folder)` that mirrors `Wallpaper.is_renderable()`
with only `pathlib` — check `entry.startswith("http")`,
`(folder/entry).exists()`, `folder.rglob("index.html")`,
`(folder/preview).exists()`, and image/video extensions via `folder.iterdir()`.
This keeps the module Qt-free at import AND at runtime when PyQt is missing.

REUSE (read-only, compose — do NOT reimplement): `from lumen.manifest_lint
import lint_folder` (import it LAZILY too — manifest_lint itself imports the
model at its top, so importing it at YOUR top would re-pull Qt) and
`Wallpaper.is_renderable()` (authoritative). A naive audit that only wraps
`manifest_lint.lint_library()` adds nothing; the value is the
renderability cross-check + EMPTY/ORPHAN detection.
