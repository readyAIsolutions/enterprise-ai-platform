# K2 Plus Firmware Macro Map (Creality OS / Klipper + Moonraker)

Verified live on LO's fleet (2026-07-16) via `GET /printer/objects/list` on
both printers (192.168.1.65, 192.168.1.66). 143 objects, 94 gcode_macros each.

## THE GOLDEN RULE
The K2 firmware does NOT expose standard Klipper macro names. If you write
`G28`, `BED_MESH_CALIBRATE`, `SHAPER_CALIBRATE`, `AUTO_FLOW_CALIBRATE`,
`AUTO_PA_CALIBRATE`, or `BELT_MDL_INFO` (as a macro) into any gcode sent to the
K2, it will silently error with "Unknown macro" and the calibrate/home/mesh
action will do nothing. Always use the Creality-native names below.

## Macro name translation (standard Klipper -> K2 Creality)
| Standard Klipper      | K2 Creality name                  | Notes |
|-----------------------|-----------------------------------|-------|
| G28                   | ACCURATE_G28                      | real homing routine |
| BED_MESH_CALIBRATE    | BED_MESH_CALIBRATE_START_PRINT    | full mesh-cal routine |
| SHAPER_CALIBRATE      | AUTOTUNE_SHAPERS                  | input shaper auto-tune |
| (input shaper toggle) | INPUTSHAPER / TUNOFFINPUTSHAPER   | enable/disable |
| PID_CALIBRATE HEATER=extruder | NOZZLE_PID                  | = PID_CALIBRATE @230C |
| PID_CALIBRATE HEATER=heater_bed | BEDPID                     | = PID_CALIBRATE @100C |
| AUTO_FLOW_CALIBRATE   | PRINT_CALIBRATION                 | K2's single flow+PA test-print |
| AUTO_PA_CALIBRATE     | PRINT_CALIBRATION                 | same macro does BOTH flow & PA |
| (belt read)           | BELT_TENSION                      | belt_mdl strain sensor routine |
| (z calibration)       | Z_AXIS_CALIBRATION                | present, untested |

## Confirmed PRESENT on the fleet (relevant subset)
ACCURATE_G28, AUTOTUNE_SHAPERS, BEDPID, BED_MANUAL_CAL(_START/_END),
BED_MESH_CALIBRATE_START_PRINT, BELT_TENSION, CALIBRATE_CUT_POS, INPUTSHAPER,
NOZZLE_PID, NOZZLE_PID_HIGH, PRINT_CALIBRATION, PRINT_PREPARED,
PRINT_PREPARE_CLEAR, TUNOFFINPUTSHAPER, Z_AXIS_CALIBRATION.
Also OBJECTS (not macros): `bed_mesh`, `belt_mdl mdlx`, `belt_mdl mdly`.

## Confirmed ABSENT (do NOT use)
G28, G29, BED_MESH_CALIBRATE, SHAPER_CALIBRATE, AUTO_FLOW_CALIBRATE,
AUTO_PA_CALIBRATE. (BELT_MDL_INFO as a macro is absent; the belt_mdl OBJECTS
exist and are read by `read_belt_tension()`.)

## Canonical full calibration script (K2, confirmed names + ROOT-CAUSE FIX)

The stock `step="all"` (NOZZLE_PID → BEDPID → ACCURATE_G28 → BED_MESH_CALIBRATE_START_PRINT → Z_AXIS_CALIBRATION → AUTOTUNE_SHAPERS → PRINT_CALIBRATION → BELT_TENSION) **still fails key22/key766 intermittently** because `_wait_for_klippy_ready` returns ~2s after PID's SAVE_CONFIG restart, but the Y stepper/probe needs ~5s more to enable.

**FIXED sequence (manager.py `all_steps`):**
```
NOZZLE_PID
BEDPID
M17                    # enable steppers
G28 (retry 4×)         # wait for Y stepper/probe to come online
ACCURATE_G28           # homing
BED_MESH_CALIBRATE_START_PRINT
Z_AXIS_CALIBRATION
AUTOTUNE_SHAPERS
PRINT_CALIBRATION
BELT_TENSION
```
With `_wait_for_klippy_ready` after each, plus 5s `asyncio.sleep` after M17 before G28.
The G28 retry (4 attempts, 2s settle each) is the key — it re-inits the probe if stuck.

## Live re-verification recipe (read-only, no hardware)
```
for ip in 192.168.1.65 192.168.1.66; do
  curl -s -m15 "http://$ip:7125/printer/objects/list" | python3 -c "
import sys,json
d=json.load(sys.stdin)
macros=[o.replace('gcode_macro ','') for o in d['result']['objects'] if o.startswith('gcode_macro ')]
for want in ['G28','BED_MESH_CALIBRATE','SHAPER_CALIBRATE','ACCURATE_G28','BED_MESH_CALIBRATE_START_PRINT','AUTOTUNE_SHAPERS','NOZZLE_PID','BEDPID','PRINT_CALIBRATION','BELT_TENSION','AUTO_FLOW_CALIBRATE','AUTO_PA_CALIBRATE']:
    print(('FOUND   ' if want in macros else 'MISSING ')+want)
"
done
```

## Notes / open questions
- `PRINT_CALIBRATION` (flow+PA test print) may require the touchscreen "auto
  cal" toggle enabled or it no-ops — confirm in UI before relying on it.
- `BELT_TENSION` macro vs `belt_mdl` object: `read_belt_tension()` consumes the
  object path; the macro is the calibration trigger. Both exist.
- `BED_MESH_CALIBRATE_START_PRINT` — verify it runs a FULL mesh, not just the
  pre-print portion, on a real armed run.
