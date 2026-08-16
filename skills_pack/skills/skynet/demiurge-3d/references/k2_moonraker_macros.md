# K2 Plus (Creality) Moonraker Macro Map + Calibration Pitfalls

Durable knowledge for the Demiurge 3D printer-control work on LO's Creality K2
Plus fleet. Captured 2026-07-16 after a live "calibrate failed" incident.

## HARD RULE: never guess Klipper macro names on the K2

The Creality K2 Plus firmware STRIPS the standard Klipper macros and exposes
Creality-named equivalents. Wiring standard Klipper names (G28,
BED_MESH_CALIBRATE, SHAPER_CALIBRATE, AUTO_FLOW_CALIBRATE, AUTO_PA_CALIBRATE,
BELT_MDL_INFO-as-macro) silently fails with "unknown macro" — the HTTP call
returns an error and the frontend shows "failed" with an empty body.

ALWAYS enumerate the live macro/object list before writing any gcode path:

```bash
# both printers in LO's fleet (confirmed 2026-07-16):
#   P1 = http://192.168.1.65:7125   P2 = http://192.168.1.66:7125
curl -s "http://<printer_ip>:7125/printer/objects/list" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); [print(o.replace('gcode_macro ','')) for o in d['result']['objects'] if o.startswith('gcode_macro ')]"
```

Then grep the output for the capability you need (PID/FLOW/PA/BELT/MESH/SHAPER).

## Confirmed K2 Plus macro map (fleet, 2026-07-16)

| Capability | Standard Klipper (DOES NOT EXIST) | K2 Creality name (USE THIS) |
|---|---|---|
| Home | `G28` | `ACCURATE_G28` |
| Bed mesh | `BED_MESH_CALIBRATE` | `BED_MESH_CALIBRATE_START_PRINT` |
| Input shaper | `SHAPER_CALIBRATE` | `AUTOTUNE_SHAPERS` (also `INPUTSHAPER`) |
| Hotend PID | `PID_CALIBRATE HEATER=extruder` | `NOZZLE_PID` (= PID_CALIBRATE HEATER=extruder TARGET=230) |
| Bed PID | `PID_CALIBRATE HEATER=heater_bed` | `BEDPID` (= PID_CALIBRATE HEATER=heater_bed TARGET=100) |
| Flow + PA test print | `AUTO_FLOW_CALIBRATE` / `AUTO_PA_CALIBRATE` | `PRINT_CALIBRATION` (single routine does BOTH) |
| Belt tension | `BELT_MDL_INFO` (gcode, unreliable) | `BELT_TENSION` (macro) + `belt_mdl mdlx` / `belt_mdl mdly` objects |
| Z axis | — | `Z_AXIS_CALIBRATION` |

Note: `belt_mdl mdlx` and `belt_mdl mdly` are REAL Moonraker objects on the K2,
so `read_belt_tension()`'s object path (`query_object("belt_mdl")`) works —
prefer it over firing `BELT_MDL_INFO` gcode.

## PITFALL: never send multi-stage calibration as ONE gcode script

`NOZZLE_PID`, `BEDPID`, and `PRINT_CALIBRATION` each run `SAVE_CONFIG`, which
RESTARTS Klipper. If you join all stages into one newline script
(`"NOZZLE_PID\nBEDPID\n...\nBELT_TENSION"`), the script aborts the instant
Klipper drops — every macro after the restart never runs. Moonraker's 503 retry
(`Klippy Host not connected`) then re-fires the WHOLE script, causing a restart
loop until the 120s transient cap is hit, then it raises -> empty 500 ->
frontend "failed". The server log shows:
`GET /printer/objects/query failed: HTTP 503 Klippy Host not connected`.

FIX (implemented in `demiurge/printer/manager.py`, `command("calibrate",...)`):
fire EACH macro as its OWN `send_gcode` call, in order, and after EVERY step
call `await self.client._wait_for_klippy_ready(timeout=90.0)` so a Klipper
restart is absorbed and the next stage still runs. Collect per-stage results;
one stage failing must NOT abort the rest. The MoonrakerClient already has a
503→wait→retry layer in `run_gcode`, but it only protects a SINGLE macro call,
not a combined script.

## Diagnostic recipe (when "calibrate failed" on a K2)

1. Read the server log tail for `503 Klippy Host not connected` / `SAVE_CONFIG`.
2. Re-enumerate `/printer/objects/list` — confirm the macro names you used
   actually exist (they probably don't; you guessed Klipper names).
3. Fire a SINGLE stage armed (e.g. `{"step":"pid","armed":true}`) to isolate
   which macro is the culprit. Lowest-risk first test = `pid` (heats + PID) or
   `belt` (no heating).
4. Confirm `PRINT_CALIBRATION` (flow/PA) needs the touchscreen "auto cal"
   toggle enabled or it may no-op.

## Where the code lives

- `demiurge/printer/manager.py` — `PrinterManager.command(action="calibrate")`
  builds the ordered step list + inter-step `_wait_for_klippy_ready`.
- `PrinterManager._is_creality()` returns True (fleet is K2-only); the Creality
  branch selects the real macro names; a non-Creality fallback branch keeps
  standard Klipper names for portability.
- `demiurge/printer/moonraker.py` — `run_gcode` has the 503→wait→retry layer;
  `_wait_for_klippy_ready(timeout=...)` polls `/printer/info` until state=ready.
- `demiurge/printer/ui_map.py` documents `NOZZLE_PID`/`NOZZLE_PID_HIGH`/`BEDPID`
  target temps (230 / 320 / 100).
- `demiurge/calibrations/native_auto_calibration.py` has `CREALITY_FLOW_MACRO`
  and `CREALITY_PA_MACRO` — NOTE these (`AUTO_FLOW_CALIBRATE`/`AUTO_PA_CALIBRATE`)
  are WRONG for LO's firmware rev; the real routine is `PRINT_CALIBRATION`.
