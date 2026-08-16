# K2 Plus Calibration — Persistent Shutdown Fix (key22 / key60 / key766)

## Symptom
Running calibration on a Creality K2 Plus via the Demiurge3D backend
(`/api/printer/calibrate` or `smart_calibrate`) fails with:
- `key60: Internal error on command:G28`  (G28 throws internal error)
- `key22: No trigger on y after full movement` (Y probe won't trigger)
- `key766: PR_ERR_CODE_NEED_RESET_XYZ: G28 XYZ FAIL, Need to Retry G28`

zaxis / shaper / belt READS may still pass; only G28-dependent macros fail.
Intermittent — sometimes passes, sometimes fails.

## Root cause (NOT hardware)
Klipper enters a **persistent SHUTDOWN/fault state after SAVE_CONFIG restarts**
(PID autotune, `PRINT_CALIBRATION`). After restart it reports `state:"ready"`
via `/printer/info`, but ANY `G28` throws key60 internally. The shutdown
PERSISTS between runs — so the next calibration's first `G28` (inside
`NOZZLE_PID`) fails immediately. The physical touchscreen "Auto-Calibrate"
works only because a power-cycle clears the shutdown; the user's button-press
home also works for the same reason.

`FIRMWARE_RESTART` is the software equivalent of a power-cycle: it re-inits the
MCU and clears the stuck shutdown WITHOUT losing saved PID/config.

## Proven fix (code, not hardware)
In any calibration orchestrator, send `FIRMWARE_RESTART`:
1. **At the very START** (before PID) — clears any pre-existing shutdown so
   the first G28 inside `NOZZLE_PID` doesn't fail.
2. **After PID** (which does its own SAVE_CONFIG restart) — clears the
   shutdown before mesh/zaxis G28 calls.

Then `M17` (enable steppers) + settle ~5s + `G28` with retry-until-homed
before any mesh/zaxis macro.

Command schema for raw gcode via the backend API:
  POST /api/printer/command
  {"printer_id":5,"action":"gcode","script":"FIRMWARE_RESTART","armed":true}
  (NOT `gcode:` + `armed:` alone — the route requires `action` + `script`.)

## Why earlier attempts failed (anti-patterns)
- Firing `NOZZLE_PID\nBEDPID` as ONE combined newline string → SAVE_CONFIG
  restart-loop → key60. FIX: fire them as SEPARATE calls.
- Relying on `_wait_for_klippy_ready` alone → returns on `state:"ready"`
  (~2s) but steppers/probe not yet online → key22. FIX: M17 + settle + retry G28.
- Using stock `step="all"` one-shot → still hits key766 because the shutdown
  pre-exists and isn't cleared. FIX: explicit FIRMWARE_RESTART first.
- Letting it hang on 503 `Klippy Host not connected` for 900s → Klipper crashed,
  not just restarting. Always have a hard overall timeout.

## Verified result
After FIRMWARE_RESTART (start + post-PID) + M17 + settle + G28-retry:
G28 returns `{"ok":true,"result":{"result":"ok"}}`, mesh produces a 13×13
probed_matrix, PID overshoot 0.0%. The printer hardware was never at fault.
