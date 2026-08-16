# K2 Plus Firmware — Calibration & Belt-Tension Knowledge Bank

Distilled from a live debugging session on LO's Creality K2 Plus fleet
(printers at 192.168.1.65 / 192.168.1.66, Moonraker on port 7125, Demiurge
backend on 8093). These are PRINTER-FIRMWARE facts (durable), NOT environment
quirks.

## 1. Real macro names (NOT standard Klipper)

The K2 Plus firmware strips/replaces standard Klipper macros. If a calibrate
route "does nothing" or errors, it's almost always because it fired a Klipper
name the K2 doesn't expose. Confirmed present via `/printer/objects/list`:

| Function | K2 macro (USE THIS) | Standard Klipper (DOES NOT EXIST) |
|---|---|---|
| Home | `ACCURATE_G28` | `G28` |
| Bed mesh | `BED_MESH_CALIBRATE_START_PRINT` | `BED_MESH_CALIBRATE` |
| Input shaper | `AUTOTUNE_SHAPERS` (also `INPUTSHAPER`, `TUNOFFINPUTSHAPERS`) | `SHAPER_CALIBRATE` |
| Hotend+bed PID | `NOZZLE_PID` + `BEDPID` (`NOZZLE_PID_HIGH` for 320C) | `PID_CALIBRATE HEATER=...` |
| Flow + PA test print | `PRINT_CALIBRATION` | `AUTO_FLOW_CALIBRATE` / `AUTO_PA_CALIBRATE` |
| Z-axis | `Z_AXIS_CALIBRATION` | — |
| Belt tension | read `belt_mdl` objects (see §2); `BELT_TENSION` macro EXISTS but HANGS | `BELT_MDL_INFO` gcode |

Other real macros seen: `Z_OFFSET_CALIBRATION` (via `CALIBRATE_CUT_POS`),
`BED_MANUAL_CAL_START/END`, `PROBE_CALIBRATION`, `PRINT_PREPARE_CLEAR`.

## 2. Belt tension — read the OBJECT, never a macro

The K2 exposes two Moonraker objects:
- `belt_mdl mdlx` -> `{"tension": <float>}`
- `belt_mdl mdly` -> `{"tension": <float>}`

Live example: P5 X=129.21 Y=140.65; P6 X=121.61 Y=140.20 (both calibrated).

CORRECT read (manager.py `read_belt_tension`):
```
ox = await self.query_object("belt_mdl mdlx")
oy = await self.query_object("belt_mdl mdly")
x_n = float(ox["tension"]) if isinstance(ox, dict) and "tension" in ox else None
```
Do NOT query `"belt_mdl"` (no such object) and dig `mdlx`/`x` — wrong shape,
returns null.

FORBIDDEN: `BELT_MDL_INFO MDL_NAME=mdlx` gcode and the `BELT_TENSION` macro.
Both HANG the `/printer/gcode/script` endpoint (never return; the client
times out at 15s). Firing them blocks the server coroutine and can wedge the
printer. Calibrate `belt` step must READ the object, not fire a macro.

Calibration sentinel: tension <= 1.0 or >= 4294967295 (0xFFFFFFFF) = uncalibrated
sensor (CA2714 OTA-wipe).

## 3. The "calibrate fails" root causes (live case study)

Symptom: `POST /api/printer/calibrate` returns empty / frontend "failed".

CAUSE A — 503 abort: the whole sequence was ONE newline-joined gcode script.
`NOZZLE_PID`/`BEDPID`/`PRINT_CALIBRATION` run SAVE_CONFIG -> Klipper restarts ->
the single script aborts the remaining macros; Moonraker's 503 retry re-fires
the whole thing (restart loop) until the 120s transient cap -> raise -> empty 500.
Server log shows: `GET /printer/objects/query failed: HTTP 503 Klippy Host not connected`.

FIX A: fire each macro as its OWN `send_gcode` call, in order, with
`await self.client._wait_for_klippy_ready(timeout=90.0)` between steps. Collect
per-stage results; one stage failing must NOT abort the rest.

CAUSE B — macro HANG: `NOZZLE_PID`/`PRINT_CALIBRATION`/etc. over the blocking
gcode endpoint either reject (`HTTP 400 key1 "Internal error during ready
callback: No active exception to reraise"`) or hang entirely (verified by
hitting Moonraker DIRECTLY: `POST /printer/gcode/script?script=BELT_TENSION`
returns nothing in 30s). These macros need async fire-then-poll, not blocking
await. Blasting them repeatedly put P5 into `shutdown` state.

FIX B (partial / pending): belt step reads object (safe). PID/flow/pa/shaper
still need an async design: fire macro with short timeout (treat 504/timeout as
"accepted, running"), then poll printer state / relevant object until done.
NOT yet implemented — do not fire those macros blocking-wait in the meantime.

## 4. Recovery

Klipper `shutdown` / wedged -> `POST /api/printer/{id}/restart` calls
`client.firmware_restart()` (FIRMWARE_RESTART + wait-ready). Confirmed brings
P5(shutdown) and P6(wedged) back to `ready`.

Check printer state directly:
```
curl http://<ip>:7125/printer/info      # result.state: ready | shutdown | ...
curl http://<ip>:7125/server/info       # klippy_connected / klippy_state
```

## 5. Debug recipe (reuse every time)

1. Enumerate REAL names: `curl http://<ip>:7125/printer/objects/list` -> grep
   macros + objects. Stop guessing from other modules.
2. Isolate server vs firmware: `curl -X POST http://<ip>:7125/printer/gcode/script?script=<MACRO>`
   with a short `-m 30`. Empty response = firmware hangs the endpoint.
3. Read belt live: `curl "http://<ip>:7125/printer/objects/query?belt_mdl%20mdlx&belt_mdl%20mdly"`.
4. Restart server with `terminal(background=true)` (never nohup); health-check
   `/api/printers` (HTTP 200) before declaring it up.

## 6. Server-pattern notes (Demiurge backend)

- Backend: `demiurge/printer/manager.py` (`PrinterManager.command` dispatches
  `calibrate`/`home`/`mesh`/`flow`/`pid`/`belt`). `read_belt_tension()` lives
  here. `_is_creality()` returns True for LO's fleet (selects K2 macro names).
- Client: `demiurge/printer/moonraker.py` — `send_gcode`->`run_gcode` has
  built-in 503/504 retry + `_wait_for_klippy_ready()`. `firmware_restart()`
  exists. httpx client: max_connections=6 (not a single-conn deadlock).
- Route: `server.py` `POST /api/printer/calibrate` (step=all|g28|g29|mesh|
  zaxis|shaper|pid|flow|pa|belt, armed=bool, dry_run default), `GET/POST
  /api/printer/{id}/belt-tension`, `POST /api/printer/{id}/restart`.
