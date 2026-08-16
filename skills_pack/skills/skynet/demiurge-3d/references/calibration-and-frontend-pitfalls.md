# Demiurge3D — Calibration, Adaptive Tuning & Frontend Pitfalls (2026-07-17 session)

Durable learnings from a full-session build. Apply these on any Demiurge3D
calibration or frontend fix.

## 1. K2 calibration CADENCE (LO hard rule, established 2026-07-17)
- **HOME (ACCURATE_G28) before EVERY step.** Never chain a calibration step
  onto an un-homed/faulted printer. One printer, one step, verify, then next.
- **NO `firmware_restart`.** Sending it on a faulted printer caused `XS300
  SYSTEM ERROR`. Recovery = LO hard power-cycle the printer, NOT remote restart.
- Run one printer at a time. Multi-printer loops are fine only if each still
  homes before its own steps.
- The backend `calibrate` endpoint defaults to dry-run unless `armed:true` AND
  `CALI_DRY_RUN` is unset. The `calibrate_smart` endpoint mirrors this.

## 2. bed_mesh object: probed_matrix vs mesh_matrix (CRITICAL gotcha)
A K2 `BED_MESH_CALIBRATE_START_PRINT` with `probe_count 13,13` produces:
- `probed_matrix`  → the REAL 13×13 measured probe points. USE THIS for
  probe-count checks and deviation-span math.
- `mesh_matrix`    → a 37×37 INTERPOLATED grid (normal Klipper bicubic). Do
  NOT compare its dimensions to 13×13 — that false-flags a violation.
- `bed_mesh` object has NO `probe_count` field (returns null). Derive probe
  count from `len(probed_matrix[0])` × `len(probed_matrix)`.
- Enforce 13×13 on the PROBED points; the 37×37 interp grid is expected.

## 3. belt_mdl read (K2 Plus)
- Live tension sources: `belt_mdl mdlx` and `belt_mdl mdly`, each returning
  `{"tension": <float>}`. This is THE correct source (confirmed P5 X=129 Y=140,
  P6 X=142).
- Sentinel `0xFFFFFFFF` (4294967295) = uncalibrated sensor → map to `calibrated:false`.
- Do NOT fire `BELT_MDL_INFO` / `BELT_TENSION` macros — they HANG the Moonraker
  gcode/script endpoint on this firmware (never returns, times out).

## 4. Smart calibration layer (`demiurge/printer/cali_smart.py`)
Better than stock one-shot macros — verifies + iterates:
- `verify_pid`: fire NOZZLE_PID+BEDPID, read back constants, SOAK-TEST (heat to
  target, sample 12s, measure overshoot %), re-fire if overshoot > 3%.
- `verify_mesh`: fire 13×13, read `probed_matrix`, span-check (re-mesh if
  span > 0.4mm after re-home), enforce 13×13 on probed points.
- `select_shaper`: fire AUTOTUNE_SHAPERS, read `input_shaper` suggested
  freq+type, SELECT optimal (freq≥55→ei, ≥35→mzv, else zv), apply at runtime
  via `SET_INPUT_SHAPER` (NO SAVE_CONFIG — avoids restart).
- `check_belt`: read belt_mdl, compare to spec band (target 135N ±25).
- Endpoint: `POST /api/printer/calibrate_smart` {printer_id, armed, apply_shaper}.
- Smart layer HOMES FIRST (embeds the cadence rule above).

## 5. Adaptive tuning loop (closed-loop camera→param)
`demiurge/printer/adaptive/` package (ENI swarm build):
- defect_scorer (heuristic PIL+numpy: stringing/over/under-extrusion/zbanding),
  param_optimizer (defect→flow%/PA/shaper nudges, escalates on repeat),
  mesh_profile (13×13 HARD-ENFORCED, per-printer JSON, NO firmware writes),
  tuning_hook (grabs nozzle-cam snapshot :8081/snapshot on print-complete,
  scores, optimizes, stores profile; applies M221+SET_PRESSURE_ADVANCE+13×13
  mesh at next print start).
- Wired via `_adaptive_tuning_watchdog` in server.py `_start_background_tasks`,
  iterating `hub.managers.items()`, firing `on_print_complete` on
  print_stats.state == "complete".

## 6. Frontend null-crash (white/error screen)
- Symptom: `Cannot read properties of null (reading 'toFixed')` in
  react-three bundle. Cause: live telemetry `temps.bedTarget` /
  `temps.extruderTarget` / `belt.x` / `belt.y` are null during calibration/idle.
- FIX: null-guard every `.toFixed` call. Pattern: `(temps.bedTarget ?? 0).toFixed(0)`.
  Files patched: LiveTelemetry.tsx, App.tsx, PrinterPanel.tsx,
  BeltTensionDial.tsx (use `value != null ?`), BedMeshHeatmap.tsx.
- Always ADD an ErrorBoundary (frontend/src/ErrorBoundary.tsx) wrapping <App/>
  in main.tsx so any future throw shows a panel, not a white screen.
- Rebuild: `cd frontend && npm run build` (new bundle hash each build; backend
  serves dist/ live, no backend restart needed for frontend changes).

## 7. Server.py patch pitfall
- When inserting a new route via patch, the old `@app.post("/api/printer/flow")`
  decorator line can get consumed, leaving a bare `async def printer_flow`.
  After any route insertion, grep for duplicate `async def printer_flow` and
  re-add the decorator. Compile-check: `python3 -m py_compile server.py`.
- Relative imports inside `demiurge/printer/adaptive/` MUST be `from . import X`
  (package context). Bare `import X` only works when run as a script from cwd —
  it FAILS when imported as a package (ModuleNotFoundError at startup). The
  swarm self-test recreated files with bare imports and clobbered the fix;
  always patch the real file + clear `__pycache__`.

## 8. CRITICAL — `send_gcode` DEFAULT TIMEOUT (15s) SILENTLY KILLS LONG MACROS
Symptom (2026-07-17, first ARMED smart-calibrate run): the endpoint returned
`{"error":"GcodeTimeoutError: gcode 'NOZZLE_PID\nBEDPID' timed out after 15.0s"}`
and the whole orchestrator aborted before mesh/shaper/belt ran. The custom
`_send()` helper defaulted `timeout=600` BUT never PASSED it through to
`m.client.send_gcode(gcode, dry_run=dry_run)` — so the client used its own
hardcoded 15s default. PID tune + bed mesh + shaker autotune all take MINUTES.
FIX: `_send` must call `m.client.send_gcode(gcode, dry_run=dry_run, timeout=timeout)`.
Pass explicit long timeouts per macro:
  - PID (NOZZLE_PID\nBEDPID): timeout=600
  - mesh (BED_MESH_CALIBRATE_START_PRINT): timeout=300
  - shaper (AUTOTUNE_SHAPERS): timeout=300
  - ACCURATE_G28: timeout=60
  - SET_INPUT_SHAPER (runtime apply): timeout=30
  - M104 soak heat: no timeout needed (it's a set, not a blocking macro)
ALSO: wrap each `_send()` macro call in try/except inside the verify function so
ONE step timing out reports per-step (out["error"]=...) and the orchestrator
CONTINUES to the next step — never let a macro exception bubble up and kill the
whole calibration. The stock `command()` dispatch in manager.py already uses
`("NOZZLE_PID", 600)` tuples for exactly this reason; match it.

## 9. OPERATIONAL NOTE — `pkill -f "server.py"` self-signals the agent shell
Running `pkill -f "server.py"` from the agent terminal kills the backend AND
returns exit code -15 (SIGTERM) to the agent's OWN shell, so the command "fails"
even though it worked. This is harmless but confusing. Pattern that works:
run the kill, let it return -15, then run the port-check (`ss -ltnp | grep 8093`)
as a SEPARATE command to confirm the port is free before relaunching. Do NOT
treat the -15 as an error.

## 10. ADAPTIVE TUNING — confirm wiring before claiming "done"
After building `demiurge/printer/adaptive/` and wiring `_adaptive_tuning_watchdog`
into server.py `_start_background_tasks`, VERIFY the package imports as a PACKAGE
(`from demiurge.printer.adaptive import tuning_hook`) — NOT just that the swarm
self-test passed (the self-test runs files as scripts with cwd=package dir, which
hides the relative-import bug). The first backend boot after wiring showed
`ModuleNotFoundError: No module named 'defect_scorer'` because the swarm
self-test had recreated tuning_hook.py with a bare `import defect_scorer` (script
context) which fails under package import. Fix: use `from . import ...` in the
real file + clear `__pycache__`, then re-verify the package import before reboot.

## 11. KEY766 ROOT CAUSE + POLL-UNTIL-HOMED FIX (the recurring XYZ fault)
`key766: PR_ERR_CODE_NEED_RESET_XYZ: G28 XYZ FAIL, Need to Retry G28!!`
with `X_nohome:True Y_nohome:True Z_nohome:True` is the SINGLE most common
calibration failure on this fleet. Root cause chain:
  1. `NOZZLE_PID`/`BEDPID` autotune triggers `SAVE_CONFIG` → **Klipper RESTARTS**.
  2. A Klipper restart WIPES homing state (all axes become "nohome").
  3. If the next macro (`BED_MESH_CALIBRATE_START_PRINT`) fires immediately
     after — before home re-confirms — the firmware sees un-homed axes and
     rejects with key766. Fire-and-forget `ACCURATE_G28` then immediate `mesh`
     hits this EVERY time, because G28 takes seconds and mesh is sent too fast.
THE FIX (non-obvious): **never chain mesh onto a fresh G28 — POLL until the
printer reports XYZ homed, THEN fire mesh.** Implemented as:
  - `_wait_homed(m, timeout=120)`: polls `toolhead.homed_axes` via
    `m.get_status()` every 2s; returns True only when the string contains
    "x","y","z" (case-insensitive).
  - `_home_and_confirm(m, dry_run)`: sends `ACCURATE_G28`, then awaits
    `_wait_homed` before returning.
  - `smart_calibrate` calls `_home_and_confirm` FIRST (home + confirm before
    any step). `verify_mesh` ALSO re-confirms homed before firing mesh
    (defense-in-depth: if not homed, it skips with a clear error instead of
    hitting key766).
GENERAL RULE for ANY K2 gcode sequence: after a macro that may SAVE_CONFIG
(PID especially), or after any restart, HOME and POLL-CONFIRM before the next
home-dependent step. "Fire G28" is necessary but NOT sufficient — you must
verify `homed_axes == "xyz"` before trusting it.
