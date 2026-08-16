# Adaptive-Tuning Swarm Build (Demiurge3D)

Captured 2026-07-17. How the ENI adaptive-tuning loop was built as a self-
healing swarm + wired into the Demiurge3D backend. Reusable pattern for any
"build N parallel workers that must produce verified, zero-error code."

## Architecture
- `build_adaptive_swarm.py` = orchestrator. Contains the EXACT source of every
  worker file embedded as a triple-quoted string (`W_D = '''...'''`). It writes
  them to `demiurge/printer/adaptive/` and runs each worker's self-test.
- Workers (4): `defect_scorer.py`, `param_optimizer.py`, `mesh_profile.py`
  (13x13 enforced), `tuning_hook.py`.
- The hook is wired into `server.py` as a background watchdog
  (`adaptive_tuning_watchdog`) that polls `hub.managers`, detects
  `print_stats.state` "complete" transition, fires `tuning_hook.on_print_complete`.
  ADD-only — no firmware writes.

## LESSON 1 — embed EXACT worker code, never "go figure it out"
The orchestrator must carry the full, final source of each worker inline. A
worker that says "TODO: implement" or relies on the LLM to fill gaps will fail
the self-test and LO will see errors. Write the complete, lint-clean module in
the string. This is what "no errors, very good instructions" means.

## LESSON 2 — self-test guard pattern
Each worker file ends with:
```python
if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "__self_test__":
        # run real assertions on the actual logic
        ...
        print("SELF_TEST_PASS")
```
The orchestrator runs `python3 <worker>.py __self_test__` and greps for
`SELF_TEST_PASS`. If missing → fail the build, do not ship.

## LESSON 3 — swarm self-test CLOBBERS the real file (import trap)
The `__self_test__` block in a worker that uses package-relative imports
(`from . import defect_scorer`) CANNOT run standalone (no package context) and
may rewrite the file with BARE imports (`import defect_scorer`) to make the
self-test pass. Result: the shipped file has broken relative imports →
`ModuleNotFoundError: No module named 'defect_scorer'` when imported as a package.
FIX (do BOTH):
  1. In the REAL worker file, ALWAYS use `from . import x` (relative). Never
     let the self-test rewrite it to bare.
  2. After the swarm writes files, `rm -rf demiurge/printer/adaptive/__pycache__`
     and re-run an import test from the backend dir:
     `python3 -c "import sys; sys.path.insert(0,'.'); from demiurge.printer.adaptive import tuning_hook; print('PKG IMPORT OK')"`
  3. If the orchestrator's `W_D` string itself had bare imports, patch it too so
     the NEXT swarm run writes correct code.

## LESSON 4 — heuristic v1, model-swap later
The defect scorer is a pure PIL+numpy heuristic (no external model) so the loop
runs with ZERO error risk and zero external deps. Structure `defect_scorer.score()`
so swapping in a vision model later is a single function change. Don't over-engineer
v1 with a model that can fail.

## LESSON 5 — watchdog wiring pitfalls
- `hub.managers.items()` is the correct API (NOT `hub.items()`).
- The watchdog must be REGISTERED in `_start_background_tasks` or it never runs.
- Use `enabled_toolsets`/background terminal for the watchdog; confirm it's live
  via a health endpoint or log line, not by assuming.
