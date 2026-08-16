# K2 Plus — confirmed hardware/firmware facts (LO's fleet, 2026-07-16)

Durable, session-independent facts about the Creality K2 Plus (Moonraker/Klipper
fork) that the Demiurge backend integrates with. Use these when wiring camera
discovery, belt tension, or any calibration that assumes "generic Klipper."

## Camera URLs (CONFIRMED by LO in browser)
- NOZZLE cam  -> `http://{host}:8081/snapshot`   (single JPEG, works)
- CHAMBER cam -> `http://{host}:4408/webcam/?action=stream`  (MJPEG, works)
- DEAD path: `:4408/webcam2/` returns nothing. Do NOT use `webcam2`.
- `:8080/webcam/...` also tried, not confirmed live.
- Both URLs are per-printer: P1 host=192.168.1.65, P2 host=192.168.1.66.

## Belt tension (NOT a generic Klipper object)
- K2 has NO `belt_tension` Moonraker printer object. Querying it returns None ->
  dashboards that read `query_object("belt_tension")` show 0/0 ("borked").
- Real read: gcode macro `BELT_MDL_INFO MDL_NAME=mdlx` and `...=mdly`.
  Output format VARIES by firmware — LO must paste the actual console line to
  parse it. The strain gauge returns `0xFFFFFFFF` (4294967295) when the sensor
  has not been calibrated via the touchscreen `key714` cal (CA2714 firmware OTA
  wipe sentinel).
- REAL save: `BELT_MDL_SET MDL_NAME=mdlx CH_MIN=-140 CH_MAX=140 IDL_ADC=1800
  FULL_ADC=4096` then `SAVE_CONFIG`. NEVER run BELT_MDL_SET on uncalibrated
  sensors — can trigger dangerous auto-tensioning.
- K2 has NO `BELT_TENSION_CALIBRATE` macro (that's SonicPad/Marlin). Firing it
  errors. Use the BELT_MDL_INFO read instead for "calibrate -> belt".

## Working pitfall pattern (this session)
- Old code gated cams on a live probe -> when the probe blipped at startup the
  WHOLE cam list returned `[]` (outage). Fix: register both cams
  unconditionally from confirmed URLs; probe only upgrades stream->snapshot
  fallback, never drops a cam.
- React `<Camera>` must key on a unique `id` (e.g. `nozzle:...` / `chamber:...`),
  NOT `cam.kind` — two cams sharing a kind collapsed to one/zero tiles.
- `demiurge.calibrations.belt_tension` imports `vision.analyzer` -> `anthropic`,
  which is NOT installed in the venv. Importing that module at request time
  raises `ModuleNotFoundError: No module named 'anthropic'` and 500s the
  endpoint. Inline the regex parser instead of importing the heavy module.
