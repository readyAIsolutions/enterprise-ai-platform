# K2 Plus Printer Facts (LO's fleet — P1 id=5 @192.168.1.65:7125, P2 id=6 @192.168.1.66:7125)

Condensed domain knowledge learned the hard way. The agent sandbox CANNOT
reach these addresses (see run-and-drives.md "NO LAN egress"); verify only via
the running server's endpoints or a script run on the box.

## Camera URLs
- **NOZZLE** -> `http://{host}:8081/snapshot`  — WORKS on both K2s. Single JPEG.
  Register unconditionally; never let a flaky probe hide it.
- **CHAMBER** -> `http://{host}:4408/webcam/?action=stream` (and `/?action=snapshot`)
  — DEAD on LO's fleet (confirmed 2026-07-16). Do NOT show a chamber tile;
  probe once and skip if it doesn't answer 200+image. If a working chamber URL
  ever appears, discovery picks it up on reconnect.
- In the UI, treat BOTH K2 feeds as poll-with-cache-buster (`:8081/snapshot`
  already needs it; `?action=stream` is NOT a true browser-push MJPEG and
  freezes on frame 1 if treated as static). Use `?t=Date.now()` every ~1s.

## Belt tension (strain-gauge sensors)
- K2 has NO `belt_tension` Moonraker object. Querying it returns nothing -> UI
  shows 0/0 ("borked"). The real data is via gcode macros on `belt_mdl`:
  - Read X: `BELT_MDL_INFO MDL_NAME=mdlx`
  - Read Y: `BELT_MDL_INFO MDL_NAME=mdly`
  - Output is console text (NOT JSON). Parse for an `N=` / tension value;
    `0xFFFFFFFF` = uncalibrated sensor (CA2714 firmware OTA-wipe sentinel).
- There is NO `BELT_TENSION_CALIBRATE` macro. "Calibrate -> belt" should READ,
  not fire a missing macro.
- Save: `BELT_MDL_SET MDL_NAME=mdlx CH_MIN=-140 CH_MAX=140 IDL_ADC=1800
  FULL_ADC=4096` + `SAVE_CONFIG`. ONLY when sensors are calibrated (never on
  0xFFFFFFFF — CA2714 bug can trigger dangerous auto-tensioning). Default
  dry-run; arm explicitly.
- The `belt_tension.py` module imports `anthropic` (heavy chain: vision ->
  orchestrator -> llm_client). Do NOT `from demiurge.calibrations.belt_tension
  import ...` in a hot path — inline a tiny regex parser instead to avoid the
  missing-dep ImportError in the venv.

## Calibration
- K2 calibration must be ONE ordered gcode script so the firmware waits between
  steps. Firing g28->g29->shaper as separate rapid calls makes the printer
  "move once then stop" (next macro chokes mid-home):
  `G28\nBED_MESH_CALIBRATE\nSHAPER_CALIBRATE`
- `BED_MESH_CALIBRATE` and `SHAPER_CALIBRATE` DO exist on K2.
- Flow rate = `M221 S<percent>` (extruder multiplier).
- Auto PID: `PID_CALIBRATE HEATER=extruder [TARGET=t]` and
  `PID_CALIBRATE HEATER=heater_bed [TARGET=t]`. Give it a long timeout
  (~600s) — PID tune runs for minutes.

## Backend route map (Demiurge3D)
- `GET  /api/printer/{id}/cameras` -> list of CameraInfo (nozzle unconditional,
  chamber only if alive). Self-heals: re-runs discover if empty.
- `GET  /api/printer/{id}/belt-tension` -> read via BELT_MDL_INFO.
- `POST /api/printer/{id}/belt-tension` (body `{"armed":true}`) -> save.
- `POST /api/printer/calibrate` (body `{"step":"all"|"g28"|..., "armed":true,
  "printer_ids":[...]}`) -> dry-run unless armed.
- `POST /api/printer/flow` (body `{"percent":105,"armed":true,"printer_ids":[...]}`)
- `POST /api/printer/pid` (body `{"heater":"extruder","temp":220,"armed":true,...}`)
- `GET  /api/printer/{id}/status` -> `{"connected", "ip", "status":{...}}`.
  `status.print_stats.state` in {ready, printing, paused, complete}. Calibration
  shows "printing"/"ready" (NOT a distinct "calibrating" state) — don't poll
  for "calibrating".
- Multi-printer uses `get_hub()` (module singleton `_hub`); `hub.ensure(pid,url)`
  connects + discovers; `hub.get(pid)` retrieves. Both P1/P2 auto-connect at
  startup via `_auto_connect_all_printers()`.
- Default `dry_run` = `(not armed) or _dry_run()`; a global `CALI_DRY_RUN`
  kill-switch forces dry-run even when armed.
