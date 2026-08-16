# Creality K2 Plus — Real Firmware Macro Names (vs Stock Klipper)

Source of truth: enumerated LIVE from LO's fleet via Moonraker
`GET /printer/objects/list` on 2026-07-16 (printers 5 = 192.168.1.65,
6 = 192.168.1.66, port 7125). The K2 firmware STRIPS most stock Klipper
macros. Any code that fires standard Klipper gcode names will silently fail
("unknown macro") on the K2.

## Confirmed PRESENT on K2 firmware
- `ACCURATE_G28`            — homing (NOT `G28`)
- `BED_MESH_CALIBRATE_START_PRINT` — full bed mesh cal (NOT `BED_MESH_CALIBRATE`)
- `AUTOTUNE_SHAPERS`        — input shaper tune (NOT `SHAPER_CALIBRATE`)
- `INPUTSHAPER`             — shaper query/toggle
- `NOZZLE_PID`              — hotend PID @230C (PID_CALIBRATE HEATER=extruder TARGET=230)
- `BEDPID`                  — bed PID @100C   (PID_CALIBRATE HEATER=heater_bed TARGET=100)
- `NOZZLE_PID_HIGH`         — hotend PID @320C
- `PRINT_CALIBRATION`       — the "small test print" that tunes BOTH flow ratio
                              AND pressure advance. This is the K2's flow/PA routine.
                              (NOT `AUTO_FLOW_CALIBRATE` / `AUTO_PA_CALIBRATE` — those
                              names exist in `demiurge/calibrations/native_auto_calibration.py`
                              but are WRONG for this firmware rev.)
- `BELT_TENSION`            — belt tension read/cal macro (belt_mdl strain sensors)
- `Z_AXIS_CALIBRATION`      — Z-axis calibration
- `CALIBRATE_CUT_POS`, `PRINT_PREPARED`, `PRINT_PREPARE_CLEAR`, `BED_MANUAL_CAL*`
  also present
- Objects: `bed_mesh`, `belt_mdl mdlx`, `belt_mdl mdly` (read_belt_tension() reads these)

## Confirmed MISSING on K2 firmware (do NOT use)
- `G28` (use `ACCURATE_G28`)
- `BED_MESH_CALIBRATE` (use `BED_MESH_CALIBRATE_START_PRINT`)
- `SHAPER_CALIBRATE` (use `AUTOTUNE_SHAPERS`)
- `AUTO_FLOW_CALIBRATE` (use `PRINT_CALIBRATION`)
- `AUTO_PA_CALIBRATE` (use `PRINT_CALIBRATION`)
- `BELT_MDL_INFO` as a macro (gcode handler — may still parse; prefer `BELT_TENSION`)

## Debugging pattern (how this was found)
When "live calibrate doesn't work" with no obvious error:
1. Query the live printer: `curl -s http://<ip>:7125/printer/objects/list`
2. Filter macros: `| python3 -c "import sys,json; d=json.load(sys.stdin); print([o.replace('gcode_macro ','') for o in d['result']['objects'] if o.startswith('gcode_macro ')])"`
3. Diff the names your code fires against what ACTUALLY exists.
4. The mismatch = the bug. Rewrite dispatch to use the firmware's real names.

## Where the fix lives
- `demiurge/printer/manager.py` `PrinterManager.command()` — `calibrate`/`home`/`mesh`
  actions now branch on `_is_creality()` (returns True for LO's fleet) and emit the
  K2-native names above. Non-Creality fallback branch keeps stock Klipper names.
- `step="all"` full sequence (Creality):
  NOZZLE_PID, BEDPID, ACCURATE_G28, BED_MESH_CALIBRATE_START_PRINT,
  Z_AXIS_CALIBRATION, AUTOTUNE_SHAPERS, PRINT_CALIBRATION, BELT_TENSION
- Standalone steps: pid, flow, pa (→PRINT_CALIBRATION), belt (→BELT_TENSION),
  mesh/g29 (→BED_MESH_CALIBRATE_START_PRINT), shaper (→AUTOTUNE_SHAPERS),
  g28 (→ACCURATE_G28), zaxis (→Z_AXIS_CALIBRATION).

## Caveats
- `PRINT_CALIBRATION` may require the touchscreen "auto cal" toggle ON or it no-ops.
- `BED_MESH_CALIBRATE_START_PRINT` — verify it runs a FULL mesh, not just pre-print.
- Macro names can differ across K2 firmware revisions (CA2714+ confirmed here).
  Always re-enumerate on a new printer before assuming names.
