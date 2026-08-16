# K2 Plus Fleet — Durable Hardware Facts (LO's printers)

Captured 2026-07-16 while fixing camera labels, belt tension, and calibration
on LO's two K2 Plus units. These are STABLE facts about the hardware/firmware,
not transient bugs.

## Printers (from webapp.db)
- P1 = id 5, `http://192.168.1.65:7125`
- P2 = id 6, `http://192.168.1.66:7125`
- Bed = 350³ mm (usable ~342 in splitter math).
- Moonraker on :7125, nozzle cam :8081, chamber cam :4408.

## Camera URLs (CONFIRMED LIVE by LO in browser)
- NOZZLE  -> `http://{host}:8081/snapshot`  (single JPEG, always works)
- CHAMBER -> `http://{host}:4408/webcam/?action=stream`  (works; see MJPEG false-positive pitfall below)

DO NOT use `:4408/webcam2/` — that endpoint is DEAD on K2 firmware.
Older code that labeled `:8081/snapshot` as "chamber" and `:4408/webcam2/`
as "nozzle" had them SWAPPED. Correct mapping is nozzle=8081, chamber=4408.

## Belt tension — the K2 does NOT have a `belt_tension` Moonraker object
The K2 exposes belt tension via the **belt_mdl strain sensors**, read with the
`BELT_MDL_INFO` gcode macro:
- `BELT_MDL_INFO MDL_NAME=mdlx`  -> X tension
- `BELT_MDL_INFO MDL_NAME=mdly`  -> Y tension
Output format varies by firmware; parse defensively (N=, hex 0x..., plain number).
The CA2714 firmware OTA-wipe sentinel is `0xFFFFFFFF` (sensor not calibrated
via touchscreen key714 yet). Treat N<=1.0 or N>=0xFFFFFFFF-1 as uncalibrated.
- Persist: `BELT_MDL_SET MDL_NAME=mdlx ...` + `SAVE_CONFIG`.
- NEVER run BELT_MDL_SET on uncalibrated sensors (CA2714 bug can trigger
  dangerous auto-tensioning).

The macro `BELT_TENSION_CALIBRATE` does NOT exist on K2 firmware — firing it
errors. Use `BELT_MDL_INFO` reads instead.

## Calibration sequencing
The CalibrationWizard fires g28 -> g29 -> shaper -> belt. The K2 reports
`print_stats.state == "printing"` while a macro/motion is active and `"ready"`
when idle. MUST wait for idle between steps or the printer chokes mid-move
("moved a bit then stopped"). Frontend `waitForIdle()` polls
`/api/printer/{id}/status` until ready.

## MJPEG false-positive pitfall (frontend CameraStream.tsx)
The K2 chamber URL contains `action=stream`, which a naive check reads as
"live MJPEG push" and sets `<img src>` ONCE -> frozen/stale frame. The K2's
`action=stream` does NOT push a continuous in-browser MJPEG; treat it as a
pollable snapshot (cache-bust with `?t=Date.now()` every ~1s), same as the
nozzle. Only `mixed-replace`/`/mjpeg` URLs are true browser-push MJPEG.

## Agent sandbox cannot reach 192.168.x.x
The agent shell has NO LAN egress — curl/ping/nc to the printers return empty.
All printer reachability MUST go through the server process (which runs on
LO's box) or LO's browser. Don't waste cycles probing printers from the agent.

## DEBUGGING PATTERN: live server serves OLD code after edits
If you edit `server.py`/`manager.py` and the running uvicorn still serves OLD
responses (bare `[]` when you added a `_debug` dict, or a route that no longer
exists), the running worker is STALE, not your file:
1. `ss -ltnp | grep ':8093'` -> holder PID. `pkill -9 -f uvicorn` may kill your
   OWN shell group (exit -9) or miss a `--reload` child worker (a python3
   worker NOT named "uvicorn"). Kill the specific PID from `ss`.
2. Confirm `8093 FREE`, THEN relaunch. `--reload` does NOT guarantee the
   endpoint reflects edits if a stale worker is already bound.
3. A silent 15s `send_gcode` timeout (raw: `"...timed out after 15.0s"`) = the
   printer was busy or the macro format is wrong, NOT a code bug.
4. `ModuleNotFoundError: No module named 'anthropic'` at request time (not
   startup) = an endpoint lazily imported a heavy module
   (`demiurge.calibrations.belt_tension` pulls `vision.analyzer` -> `anthropic`)
   not installed in the venv. Inline the tiny pure function you need instead of
   importing the whole module.
5. When the live endpoint returns `[]` but a standalone `hub.ensure`+method
   script returns correct data, the gap is process-state, not logic. Reproduce
   the EXACT server call path in a standalone script (import server as srv,
   call the manager method) to isolate — the standalone will usually work,
   proving the fix logic is right and only the live reload is the issue.
