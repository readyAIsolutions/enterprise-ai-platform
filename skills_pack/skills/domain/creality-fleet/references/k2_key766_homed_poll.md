# K2 key766 (PR_ERR_CODE_NEED_RESET_XYZ) — root cause + G28-retry fix

`key766: PR_ERR_CODE_NEED_RESET_XYZ: G28 XYZ FAIL, Need to Retry G28!!`
with `X_nohome:True Y_nohome:True Z_nohome:True`.

## Root cause chain (why it recurs)
1. `NOZZLE_PID` / `BEDPID` autotune triggers `SAVE_CONFIG` → **Klipper RESTARTS**.
2. A Klipper restart WIPES homing state (all axes become "nohome").
3. **CRITICAL (2026-07-19 confirmed):** Klipper reports `state=="ready"` ~2s after restart
   (`_wait_for_klippy_ready` returns), but the **Y stepper driver + bed probe need ~5s MORE**
   to enable/initialize. Any G28-dependent macro fired in that window hits key766/key22.
4. If the next macro (`BED_MESH_CALIBRATE_START_PRINT`) fires IMMEDIATELY after
   G28 — before the Y stepper/probe is online — the firmware sees un-homed axes and
   rejects with key766.

## The real fix: M17 + settle + G28 retry(4×), NOT homed_axes poll
`toolhead.homed_axes` is **NOT reliable on Creality fw** — stays `''` even after a
successful `ACCURATE_G28` (verified 2026-07-19). Polling it gives FALSE NEGATIVE.

Pattern (implemented in `demiurge/printer/manager.py` calibrate dispatch + `cali_smart.py`):
- After PID restarts: fire `M17` (enable steppers) → `asyncio.sleep(5.0)` settle →
  `G28` WITH RETRY (up to 4×, 2s settle between) until homed.
- Treat a successful `G28`/`ACCURATE_G28` send (no exception / macro ok:true) as
  homed proof; do NOT gate on `homed_axes`.
- The G28 retry re-inits the probe if it was stuck.

## General rule for ANY K2 gcode sequence
After a macro that may SAVE_CONFIG (PID especially), or after any restart:
Insert `M17` + 5s settle + `G28` retry(4×) before the next home-dependent step.
Never trust `_wait_for_klippy_ready` alone — it returns too early.
Never gate on `homed_axes` — it's unreliable on this firmware.
