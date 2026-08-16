# K2 Calibration Lessons — key22/key60/key766 Marathon (2026-07-19)

## TL;DR — the fix
Fire the FULL calibration as ONE stock call:
```python
await m.command("calibrate", step="all", dry_run=...)
```
Then do READ-ONLY verification reads on top (mesh probed_matrix 13×13 check,
input_shaper select+apply, belt spec). NEVER split the steps into separate
`m.command("calibrate", step=...)` calls from different coroutines, and NEVER
fire `NOZZLE_PID\nBEDPID` as a combined string.

## The ~12-run failure loop (what NOT to do)
A "smart calibration layer" (`cali_smart.py`) reinvented the calibration sequence:
1. Fired `ACCURATE_G28` BEFORE pid (wrong order — stock does pid THEN g28).
2. Fired `NOZZLE_PID\nBEDPID` as ONE combined newline string (the manager's
   `single` dict `"pid"` entry) → SAVE_CONFIG restart-loop → `key60: Internal
   error on command:G28` shutdown.
3. Fired mesh as a SEPARATE `m.command("calibrate", step="mesh")` from a different
   coroutine AFTER a separate `step="g28"` → `key766: G28 XYZ FAIL` (the mesh
   macro's internal G28-check failed because the steps weren't in the same loop
   with `_wait_for_klippy_ready` between them).
4. Added `FIRMWARE_RESTART` after PID — wrong theory (blamed "stuck Y-endstop").

Result: PID failed (key60), mesh failed (key766/key22), every run.

## The user correction (LO)
- "there is nothing wrong with my hardware, fix it"
- "just homed the printer from the buttons homed just fine this is CLEARLY you you problem"
→ Hardware was PERFECT. The bug was 100% in the software sequence.

## The resolution (CORRECTED 2026-07-28, ENHANCED 2026-07-31)
1. Split PID into separate `NOZZLE_PID` / `BEDPID` calls with `_wait_connected`
   between (avoids the combined-string key60 shutdown). → PID passed.
2. Added **12s settle after PID restarts** + `M17` + 5s settle + G28 retry(4×)
   BEFORE mesh/zaxis — the **ROOT CAUSE FIX** for key22/key766. Klipper reports
   "ready" ~2s after SAVE_CONFIG restart but Y stepper/probe needs ~12-15s more.
   The manager's `step="all"` loop ONLY waits on `_wait_for_klippy_ready`
   (returns too early), so bare `step="all"` STILL threw key22/key766 intermittently.
3. FINAL manager.py `all_steps` sequence (with fix):
   NOZZLE_PID → BEDPID → **12s settle** → M17 → G28 (retry) → ACCURATE_G28 → BED_MESH_CALIBRATE_START_PRINT →
   Z_AXIS_CALIBRATION → AUTOTUNE_SHAPERS → PRINT_CALIBRATION → BELT_TENSION
   Each with `_wait_for_klippy_ready` after, plus 12s settle after PID, 5s after M17 before G28.
4. Mesh retry: 2 attempts with re-home between (catches key766).
5. Z-axis retry: 2 attempts with settle (catches key22).
6. G28/ACCURATE_G28 retry logic: up to 4 attempts with 3s settle between,
   treats non-timeout errors on homing macros as retryable.
7. **Auto-reconnect via `hub.ensure()`** in server.py calibrate endpoint — handles
   PID restart disconnection so multi-printer calibration survives restarts.
6. G28/ACCURATE_G28 retry logic: up to 4 attempts with 3s settle between,
   treats non-timeout errors on homing macros as retryable.

## Key firmware facts confirmed
- PID autotune (NOZZLE_PID/BEDPID) triggers `SAVE_CONFIG` → Klipper RESTART →
  Moonraker client drops mid-call (503/Disconnected). This is EXPECTED, not failure.
- `BED_MESH_CALIBRATE_START_PRINT` does its OWN internal G28 and needs XYZ already
  homed IN-LOOP. Firing it standalone after a separate g28 from another coroutine
  fails key766.
- `toolhead.homed_axes` is NOT a reliable homed signal on Creality fw — stays `''`
  even after a successful `ACCURATE_G28`. Never gate on it.
- `bed_mesh.probed_matrix` = real 13×13 probe points (use for assertions).
  `bed_mesh.mesh_matrix` = 37×37 interpolated (ignore for probe-count checks).

## Curl timeout
Full calibrate runs 8–12 min > curl `-m 600`. Endpoint writes result server-side
to `/home/hunter/DemiurgeForge/smart_<pid>.json`. Use `-m 900` + read that file.

## What survived (still true)
- 13×13 mesh is a HARD LO mandate (probe_count [13,13], mesh_min [5,5], mesh_max [345,345]).
- `key22: No trigger on y` = bed PROBE signal issue (cable/deploy/auto-cal toggle),
  NOT the Y endstop (g28 would also fail if the switch were broken). But key22 can
  ALSO be a CODE bug (combined-PID restart-loop state) — debug code first.
- `XS300` = hard firmware fault; only a HARD POWER CYCLE from LO clears it. Never
  send remote `firmware_restart` to a faulted K2.
- Blame MY code first, never his hardware.
