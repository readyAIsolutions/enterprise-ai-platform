# Demiurge 3D — Adaptive Tuning Loop (ENI swarm build, 2026-07-17)

## What it is
A closed-loop camera→param tuning module that makes Demiurge tune BETTER than
stock Creality one-shot calibration. After each print completes, it captures the
nozzle cam snapshot, scores print defects, optimizes flow%/pressure-advance/
shaper, and stores a PER-PRINTER profile. At the next print start those params
are applied (M221 flow + SET_PRESSURE_ADVANCE + load 13×13 mesh). Iterative:
a defect persisting 2+ prints escalates the nudge magnitude → converges.

## Location
`/home/hunter/Desktop/Demiurge3D/backend/demiurge/printer/adaptive/`
- `defect_scorer.py`  — heuristic image → defect severities 0..1 (stringing,
  overextrusion, underextrusion, zbanding). PIL + numpy, NO cv2, NO network.
- `param_optimizer.py` — defect scores → param nudges (deterministic math).
- `mesh_profile.py`  — 13×13 mesh ENFORCEMENT + per-printer JSON profile store.
  Assertion rejects any non-13×13 mesh on write AND load.
- `tuning_hook.py`  — integration: `on_print_complete(pid, store)` captures +
  scores + optimizes + stores; `apply_at_print_start(pid, store)` returns the
  gcode lines to apply tuned params.
- `__init__.py` — package init; `from . import ...` (relative, NOT bare).

## How it's wired (server.py)
`_adaptive_tuning_watchdog()` is registered in `_start_background_tasks()`
(startup). It polls `get_hub().managers.items()` every 15s, reads
`m.get_status()`, and on the `standby → complete` transition of
`print_stats.state` calls `tuning_hook.on_print_complete(pid, _ADAPTIVE_STORE)`.
`_ADAPTIVE_STORE = <backend>/adaptive_profiles`.

SAFETY: no firmware/config writes. Params go to JSON only; applied at next
print start via gcode, never persisted to printer config.

## ENI SWARM BUILD DISCIPLINE (how this was produced — replicate)
LO mandate: "build with ENI swarm, make sure no errors, they don't get confused,
give very good descriptions." Pattern that worked:
1. Write a SPEC file (exact file paths, function signatures, I/O contracts,
   hard constraints, self-test requirement).
2. Embed each worker's COMPLETE code inline in the orchestrator
   (`build_adaptive_swarm.py`) — workers execute exact code, they do NOT
   interpret a vague brief. Zero ambiguity = no confusion.
3. Each worker has a `if __name__ == "__main__" and sys.argv[1] == "__self_test__":`
   self-test that must exit 0 before "done".
4. Orchestrator runs each worker's self-test as a SUBPROCESS (a worker crash
   can't kill the orchestrator), then a SELECTOR runs a full smoke test
   (synthetic image → score → optimize → store → assert 13×13). Refuse to merge
   if ANY worker fails or smoke errors.

## TWO BUGS HIT + FIXES (capture so they don't recur)
- BUG 1 — self-test guard wrong. Originally `if __name__ == "__self_test__":`.
  When run as `python file.py __self_test__`, `__name__` is `"__main__"`, so the
  block NEVER runs → "FAIL" with empty stdout. FIX: `if __name__ == "__main__"
  and len(sys.argv) > 1 and sys.argv[1] == "__self_test__":`.
- BUG 2 — relative-import clobber. `tuning_hook.py` used bare
  `import defect_scorer` (worked only when cwd == adaptive dir). When imported as
  a PACKAGE (`from demiurge.printer.adaptive import tuning_hook`) it raised
  ModuleNotFoundError. Worse: re-running the swarm self-test (which writes the
  file from the orchestrator's W_D string) OVERWROTE the real file with the old
  bare-import version AFTER the manual patch — so the fix silently reverted.
  FIX: use `from . import defect_scorer, ...` everywhere in the package; and
  after patching the real source, do NOT re-run the swarm builder (or fix the
  orchestrator's W_D too) or it clobbers your edit. Always clear
  `__pycache__` after editing a package module and re-verify the package import
  (`python3 -c "from demiurge.printer.adaptive import tuning_hook"`) before
  rebooting the backend.

## Verification (after build)
- `python3 build_adaptive_swarm.py` → all 4 workers PASS + smoke "13x13 enforced".
- Package import: `cd backend && python3 -c "from demiurge.printer.adaptive
  import tuning_hook; print(callable(tuning_hook.on_print_complete))"` → True.
- Backend boot log must show `adaptive-tuning-watchdog` started with NO
  `ModuleNotFoundError`/`Traceback`.

## 13×13 MESH (LO hard mandate)
probe_count = [13, 13]; mesh_min = [5, 5]; mesh_max = [345, 345].
Assert on write AND load in mesh_profile.py. K2 firmware config already uses
these values; any other matrix size = generated wrong, reject it.
