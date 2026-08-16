# Demiurge3D — Forge Adaptive Tuning + Frontend Crash Fixes (2026-07-17)

Reference for two ENI-built pieces this session: (1) the closed-loop camera→param
adaptive tuning module, and (2) the frontend null-crash / white-screen fix.

## 1. Adaptive Tuning Loop (closed loop: print → camera sees error → next print better)

Built with the ENI swarm as 4 workers under
`/home/hunter/Desktop/Demiurge3D/backend/demiurge/printer/adaptive/`:
- `defect_scorer.py` — heuristic camera analysis (stringing, over/under-extrusion,
  z-banding) via PIL + numpy. LOCAL-ONLY (no external model, no network — zero error risk).
- `param_optimizer.py` — maps defect scores → flow% / pressure-advance / shaper nudges;
  deterministic; escalates nudge magnitude if a defect persists 2+ prints (converges).
- `mesh_profile.py` — **13×13 mesh HARD-ENFORCED** (probe_count 13,13; mesh_min 5,5;
  mesh_max 345,345). Assertion rejects non-13×13 on BOTH store + load. Profiles are
  per-printer JSON on disk — NO firmware/config writes.
- `tuning_hook.py` — integration: on print-complete it grabs the nozzle-cam snapshot
  (`http://{host}:8081/snapshot`), scores defects, optimizes, stores the profile;
  at next print start it applies `M221` (flow) + `SET_PRESSURE_ADVANCE` + loads the 13×13 mesh.

Wired into backend startup via `adaptive-tuning-watchdog` (registered in
`_start_background_tasks` in server.py). It polls `get_hub().managers.items()`,
detects the `print_stats.state == "complete"` transition, and fires
`tuning_hook.on_print_complete(printer_id, store_dir)`. Iterates → tunes the NEXT print.

Camera URLs (confirmed): NOZZLE `http://{host}:8081/snapshot`, CHAMBER `http://{host}:4408/webcam/?action=stream`.

### Razor-spec swarm note (this build)
Workers got EXACT specs: file path, function signatures, I/O contract, hard
constraints (13×13, no firmware writes, no external net), and a self-test each
must pass. Selector ran ONE smoke test (synthetic snapshot → score → optimize →
store → assert 13×13) and only merged on ZERO errors. Pitfalls hit + fixed:
- Self-test guard must be `if __name__=="__main__" and sys.argv[1]=="__self_test__":`
  (NOT `__name__=="__self_test__"` — that never fires when run directly).
- Use `from . import` (relative) inside the package, never bare `import`. The
  orchestrator's embedded worker string is the source of truth — if you patch the
  real file, patch the embedded string too, or the self-test re-clobbers your fix.
- Clear `__pycache__` before the final `from demiurge.printer.adaptive import tuning_hook` test.

## 2. Smart Calibration Layer (non-printing steps, beats stock one-shot)

`demiurge/printer/cali_smart.py` + `POST /api/printer/calibrate_smart` (see
creality-fleet skill → SMART CALIBRATION LAYER). Verifies + selects instead of
fire-and-forget: PID soak-test+retry, 13×13 mesh span-check+re-mesh, shaper
optimal-type select + runtime apply, belt spec-band check. No firmware writes
unless armed + runtime-only.

## 3. Frontend NULL-CRASH + WHITE-SCREEN FIX

Symptom: dashboard threw `Cannot read properties of null (reading 'toFixed')`
during calibration/idle (temps/bedTarget/extruderTarget/belt values are `null`
when the printer isn't actively heating). Earlier the same app white-screened
because there was NO ErrorBoundary — any render throw blanked the SPA.

Fixes applied:
- Added `frontend/src/ErrorBoundary.tsx` and wrapped `<App/>` in `main.tsx` — now a
  thrown render shows a panel (with the cause) instead of a white screen.
- Null-guarded every `.toFixed` call across the dashboard:
  - `LiveTelemetry.tsx`: `(temps.bedTarget ?? 0).toFixed(0)`, `(temps.extruderTarget ?? 0)`,
    `(belt.x ?? 0).toFixed(1)`, `(belt.y ?? 0).toFixed(1)`.
  - `App.tsx`: same bed/extruder target guards.
  - `PrinterPanel.tsx`: same bed/extruder target guards.
  - `BeltTensionDial.tsx`: `value != null ? value.toFixed(1) : 'Uncalibrated'`.
  - `BedMeshHeatmap.tsx`: `(min ?? 0).toFixed(3)` etc.
  RULE: any live printer field that can be null during idle/calibration MUST use
  `?? 0` (or `?? '—'`) before `.toFixed()`. The 2D heatmap and BedMesh3D are already
  guarded (return early on empty/irregular matrix) — the crash was the LIVE
  telemetry numbers, not the mesh.
- Rebuild: `cd frontend && npm run build` → new bundle served from backend :8093.

Verify after any frontend change: `curl -s localhost:8093/ | grep index-` shows the
new bundle hash; reload the app — no white screen, no toFixed crash during idle.

## 4. Backend wiring pattern (add a background task without patching internals)
- Background tasks register in `_start_background_tasks` (an `@app.on_event("startup")`
  function in server.py). Add `asyncio.create_task(_my_watchdog())` there.
- Iterate printers via `get_hub().managers.items()` (NOT `hub.items()` — that's a
  different API; the LSP/lint error `hub.items` means use `.managers`).
- Read live status: `m.get_status()`; read printer objects: `m.query_object("bed_mesh")`.
- Capture: trigger a watchdog on a print-complete transition by polling
  `print_stats.state` each loop iteration (don't patch the print-done handler).
- After editing server.py: `python3 -m py_compile server.py` (catches syntax), then
  reboot backend (kill :8093 by PID via `ss -ltnp`, relaunch `python3 server.py`).
  `pkill -f server.py` will signal your OWN shell too (exit -15) — that's harmless;
  just confirm `ss -ltnp | grep 8093` is free before relaunching.
