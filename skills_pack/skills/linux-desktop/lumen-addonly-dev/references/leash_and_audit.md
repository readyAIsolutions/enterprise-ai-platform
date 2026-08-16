# LUMEN: auditing an untested add-only module + live-swarm collision detection

Companion to `references/headless_safety_and_mypy.md` (which proves leash
compliance: the `QApplication created by` footer check + `mypy`). This file
adds two things that file does NOT cover: (a) the audit-an-untested-module
workflow (a high-value alternative to building from scratch) with the rpc.py
case study, and (b) live-swarm collision detection when the claimed-module map
drifts mid-session.

## 1. Proving YOUR module (not the conftest) pulls no Qt
`headless_safety_and_mypy.md` covers the footer check + mypy. ADD this one
probe when you must show the MODULE under test is Qt-free (the conftest imports
PyQt6 itself, so grepping `sys.modules` inside the test process is unreliable):
    QT_QPA_PLATFORM=offscreen DISPLAY= .venv/bin/python -c \
      "import sys, lumen.<mod>; print('QT:' + str(any(m.startswith('PyQt') or m.startswith('PySide') for m in sys.modules)))"
Assert the printed line is `QT:False`. (`lumen/__init__.py` is clean, so a
pure-stdlib module will not transitively import Qt.)

## 2. AUDITING a complete-but-untested ADD-ONLY module (high-value move)
Not every good add-only task is "build from scratch". A shipped `lumen/<mod>.py`
that has NO `tests/test_<mod>.py` and a RED built-in self-test is a top gap and
zero-collision (it is already there; you only ADD a test file + a minimal fix).

Steps:
1. Find it: a `lumen/<mod>.py` that exists but has no `tests/test_<mod>.py`
   and no STATUS claim. (Avoid core + already-claimed sibling modules.)
2. Get ground truth: run `python -m lumen.<mod> --self-test`. If it exits 1,
   read the traceback — there is a real latent defect.
3. Fix minimally + harden: patch only the broken logic; add defensive handling
   so the failure class can't recur (e.g. accept both shapes of a returned
   value).
4. Write `tests/test_<mod>.py` as a real pytest suite (real socket / injected
   fakes) locking every route/branch/error code + the degradation path.
5. Run flake8 + mypy + importlint + the leash checks (section 1 + the footer
   check in `headless_safety_and_mypy.md`).

### Case study: lumen/rpc.py
- Symptom: `python -m lumen.rpc --self-test` exited 1 with
  `TypeError: 'dict' object is not callable` on GET /api/status.
- Root cause: the self-test's FakeBridge set `self.status = {...}` as an
  INSTANCE ATTRIBUTE, which SHADOWED the inherited `status()` method; the
  handler called `self.server.bridge.status()` -> `dict()` -> TypeError. The
  SAME shape hits any real bridge that exposes `status` as an attribute (the
  common pattern) — so the live route would 500 too.
- Fix: (a) make FakeBridge override `status(self)` as a method; (b) harden the
  handler with a `_resolve_status(bridge)` helper that calls `bridge.status`
  only if it is callable, otherwise uses the attribute directly. Now BOTH
  shapes work and the route can never 500 on the common bridge.
- Lock: `tests/test_rpc.py` — 17 tests over a real localhost socket:
  health/status (method + attribute shapes), switch/randomize/pause/resume/set
  (200 + dispatch recorded), missing-field 400, unknown 404, NullBridge
  degradation 501, `_supports()`, `free_port()`, `self_test()` shape + pass, CLI
  `--self-test` / `--health-check` exit codes, and the `QT:False` import probe.

## 3. LIVE-SWARM collision avoidance (the map drifts mid-session)
The claimed-module map changes WHILE you work — other minis create files.
- Re-scan `lumen/*.py` and `tests/*.py` right before you commit to a module.
  A candidate that "didn't exist 10 min ago" (e.g. another mini just created
  `library_dedup.py`, or `tests/test_hotkeys.py` shows up mid-build) is now
  OWNED — pick a different gap.
- Use the full-suite failure list as a live "who is building what" signal:
    pytest -q 2>&1 | grep -E "^(FAILED|ERROR)" \
      | sed -E 's#tests/test_([a-z_]+)\.py.*#\1#' | sort | uniq -c
  Any module appearing there is actively being touched — do NOT also edit it,
  and do NOT "fix" its failures (that collides with the active mini and risks
  editing core).
- Your own change must add ZERO failures: confirm NONE of the failing tests are
  in your module (`grep -i <yourmod> /tmp/failures.txt` => empty). Attribute
  the rest to siblings/concurrent swarm and report them; do NOT fix core.
