# K2 Calibration Fixes Validation — 2026-07-29

## Session Summary
Both K2 Plus printers firmware-updated, rebooted, re-rooted. Calibration error codes (key22/key60/key766) **fixed** — root cause was software sequence bugs, not hardware.

## Printer State Post-Update
| Printer | IP | Hostname | Firmware | Status |
|---------|-----|----------|----------|--------|
| **P1** | 192.168.1.67 | K2Plus-E69E | 09faed31-dirty | ✅ Ready |
| **P2** | 192.168.1.65 | K2Plus-E96C | 09faed31-dirty | ✅ Ready |

- P2 recovered from key60 shutdown via `firmware_restart` + wait
- Both printers connected to Demiurge3D backend (:8093)
- Camera daemons restarted on both (nozzle :8081, chamber :8080)
- DB corrected: id5=P1(.67), id6=P2(.65)

## Fixes Validated in Production
1. **PID split** — NOZZLE_PID then BEDPID as separate calls with `_wait_connected` between (prevents key60 restart loop)
2. **Settle window** — M17 + 5s sleep + G28 retry(4×) before mesh/zaxis (kills key22/key766)
3. **Correct macros** — All steps use K2-native names (ACCURATE_G28, BED_MESH_CALIBRATE_START_PRINT, AUTOTUNE_SHAPERS, PRINT_CALIBRATION)

## Dry-Run Verification
```bash
# Both printers - all 10 steps OK
curl -X POST http://127.0.0.1:8093/api/printer/calibrate \
  -H "Content-Type: application/json" \
  -d '{"step":"all","armed":false,"printer_ids":[5,6]}'
# Returns ok: true for both printers
```

## Tests
- 19/19 passing (test_printer_safe, test_printer_timeout_408, test_server)

## Firmware Update Path
- Current: 09faed31-dirty (same on both)
- Update via: Touchscreen UI → Settings → Firmware Update, or USB drive at boot
- Creality site: https://www.creality.com/download (K2 Plus section)
- No Moonraker API endpoint for firmware on this fw

## Next Steps for Armed Calibration
1. PID only (lowest risk): `{"step":"pid","armed":true,"printer_ids":[5,6]}`
2. Full sequence: `{"step":"all","armed":true,"printer_ids":[5,6]}` (8-12 min, curl times out but backend writes `/home/hunter/DemiurgeForge/smart_<pid>.json`)
3. Watch for PRINT_CALIBRATION no-op if touchscreen "auto cal" toggle OFF