# K2 Plus Smart Calibration — cali_smart.py (ENI build, 2026-07-17)

Module: `backend/demiurge/printer/cali_smart.py`
Endpoint: `POST /api/printer/calibrate_smart` {printer_id, armed, apply_shaper}
Wired into `server.py` startup watchdog? No — invoked on demand. Adaptive tuning
loop (camera→param) is a SEPARATE module: `demiurge/printer/adaptive/` (watcher
registered in `_start_background_tasks`).

## What it does (better than stock one-shot)
- PID: fire NOZZLE_PID+BEDPID, READ BACK constants, SOAK-TEST (heat to 230, sample
  12s, measure overshoot%). Re-fire if overshoot > 3%. Stock just fires-and-forgets.
- mesh: fire BED_MESH_CALIBRATE_START_PRINT, read back PROBED matrix, compute span.
  13×13 ENFORCED (MESH_SPEC). Re-home+re-mesh once if span > 0.4mm.
- shaper: fire AUTOTUNE_SHAPERS, read suggested freq/type from input_shaper, SELECT
  optimal (ei for >=55Hz, mzv for >=35Hz, zv below), apply at runtime via
  SET_INPUT_SHAPER (no SAVE_CONFIG restart).
- belt: read belt_mdl tension, compare to Creality K2 spec band (target 135N ±25).

## CRITICAL K2 FIRMWARE QUIRKS (cost ~10 failed runs to learn)

### 1. key766 = PR_ERR_CODE_NEED_RESET_XYZ (G28 XYZ FAIL)
Mesh macro rejects with `key766` if printer isn't homed. The printer LOSES its
home after ANY Klipper restart (SAVE_CONFIG, PID autotune, firmware_restart).
FIX: never chain mesh onto an un-homed printer. Home first, and treat a
successful G28 *send* as the homed proof (see quirk #3).

### 2. PID autotune triggers SAVE_CONFIG → Klipper RESTART (HTTP 503 mid-call)
`NOZZLE_PID`/`BEDPID` end with SAVE_CONFIG, which restarts Klipper. The
Moonraker client throws `503 Klippy Disconnected` DURING the call. This is
EXPECTED, not a failure. FIX: in verify_pid, catch "Disconnected"/"503"/"Klippy"
exceptions, set fired=True + restart_detected=True, then `_wait_connected()`
(poll get_status until reachable again, ~180s) before reading back constants.

### 3. toolhead.homed_axes is NOT populated by K2 firmware
After a successful ACCURATE_G28, `status.toolhead.homed_axes` stays `''` (empty)
even though the printer IS homed (G28 returns ok:true). Polling it as a "homed
gate" gives a FALSE NEGATIVE and blocks mesh forever. FIX: `_home_and_confirm`
returns True if the G28 `_send` succeeded (no exception). The unreliable
`homed_axes` poll is kept only as a soft fallback. VERIFIED: `calibrate
step=g28 armed` returns ok:true but homed_axes still '' 6s later.

### 4. bed_mesh object field names
- `probed_matrix` = the ACTUAL 13×13 probe points (use THIS for probe_count + span).
- `mesh_matrix` = the 37×37 INTERPOLATED grid (NOT the probe count — do not
  compare its dims to 13×13 or you'll false-flag a violation).
- `probe_count` field is None in the object; derive from probed_matrix dims.

### 5. curl timeout loses the result
Full sequence (PID restart + mesh + shaker) exceeds 600s. curl `-m600` aborts
with exit 28, leaving the result file empty. FIX: endpoint writes result to
`/home/hunter/DemiurgeForge/smart_<pid>.json` server-side (json.dump, default=str)
so a slow curl never loses it. Also: `all_ok` must iterate ONLY the step dicts
(pid/mesh/shaper/belt), NOT meta keys (_homed bool, _warn str) or it crashes
with `AttributeError: 'bool' object has no attribute 'get'`.

## Send-gcode timeout
`_send()` MUST pass `timeout=` to `m.client.send_gcode()` (default client timeout
is 15s — PID/shaker need minutes). PID=600, mesh=300, shaper=300, G28=120,
SET_INPUT_SHAPER=30.

## Standing rule (LO)
HOME before EVERY calibration step. One printer, one step, verify. NO
firmware_restart (caused XS300 system error — only LO hard power cycle fixes).
Job-dispatch gate is READ-ONLY; LO presses print start.
