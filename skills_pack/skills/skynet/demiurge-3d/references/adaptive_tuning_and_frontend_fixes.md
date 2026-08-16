# Demiurge3D — Adaptive Tuning Loop + Frontend White-Screen Fix

Condensed from the 2026-07-17 build session. Class-level, not session-specific.

## 1. Frontend "boots then white screen" — root cause + fix
- Symptom: `:8093` loads, paints, then fully white. Server, `/assets/*.js`
  (all 200), and `/api/*` boot endpoints all answer — so it is a CLIENT-SIDE
  React runtime crash, NOT server.
- Root cause: NO top-level error boundary anywhere (`grep -rniE
  'ErrorBoundary|componentDidCatch|getDerivedStateFromError'` = ZERO). Any
  thrown render in a child (live-telemetry component choking on a partial
  WebSocket frame during calibration) unmounts the ENTIRE tree → blank.
- Fix (safe, additive):
  1. `frontend/src/ErrorBoundary.tsx` — class component; catches render errors,
     shows a dark fallback panel WITH the error text, keeps the rest alive.
  2. Wrap `<App/>` in `<ErrorBoundary>` in `frontend/src/main.tsx`.
  3. `cd frontend && npm run build` (node22/npm9 present, ~6s, 2133 modules).
     Backend serves `dist/` from disk per-request → NO restart needed; verify
     root HTML references the new `index-*.js` hash and it returns 200.
- This STOPS the white-out. To fix the underlying throw, read the panel's error
  text and harden the component (guard empty/malformed telemetry, e.g.
  `bed_mesh.mesh_matrix` of `[[]]` mid-calibration).

## 2. Adaptive closed-loop tuning loop (camera → better next print)
LO's vision: tune BETTER than stock Creality one-shot. Built as
`backend/demiurge/printer/adaptive/` (orchestrator:
`~/DemiurgeForge/build_adaptive_swarm.py`):
- `defect_scorer.py` — heuristic, PIL+numpy ONLY (no cv2/torch, local-only):
  scores stringing / overextrusion / underextrusion / zbanding from a snapshot.
- `param_optimizer.py` — deterministic: defect scores → flow% (M221),
  pressure_advance (SET_PRESSURE_ADVANCE), shaper_freq; escalates if a defect
  persists across prints.
- `mesh_profile.py` — per-printer JSON tuning store; **13×13 mesh HARD-ENFORCED
  on write AND load** (assert `probe_count==[13,13]`); NO firmware/config writes
  (reversible). 13×13 mandate: see creality-fleet skill.
- `tuning_hook.py` — `on_print_complete()` grabs nozzle-cam snapshot
  (`:8081/snapshot`), scores, optimizes, stores; `apply_at_print_start()` returns
  M221/PA/mesh-load gcode to inject at next print start. Iterative convergence.
- STATUS 2026-07-17: modules + self-test + smoke (13×13 enforced, zero errors)
  PASS. NOT yet registered into `server.py`'s print-complete event — that
  integration call is the remaining step to fire on real prints.
- Build discipline used: ENI swarm with EXACT embedded worker code +
  `argv[1]=="__self_test__"` guard + refuse-merge-on-any-error. See
  eni-swarm-content-gen skill for that pattern.

## 3. Forge generator foundation (separate from live floor)
`~/DemiurgeForge/` holds the mechanism+tolerance library (`forge_core.py`),
zero-dependency STL validator (`validator.py`, reads ASCII+binary STL, checks
watertight edge-manifold), two multi-part sale prints (ModDock desk system,
AquaSprite planter — all 8 parts watertight-validated), and a forever ENI-swarm
catalog builder (`swarm_forge.py --forever`). OpenSCAD IS installed
(`/usr/bin/openscad`); no slicer/Moonraker in sandbox, so slice+print happens on
LO's box (backend has pure-python slicer + Moonraker). Keep this work OUT of the
live Demiurge3D floor dir to avoid stale-worker collisions.
