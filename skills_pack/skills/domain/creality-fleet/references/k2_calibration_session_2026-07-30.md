# K2 Calibration Session — 2026-07-30

## Summary
Ran full calibration on both K2 Plus printers via Demiurge3D backend. PID phase passed, mesh phase stalled on both printers for different reasons.

## Printer Status
| Printer | ID | IP | Hostname |
|---------|-----|-----|----------|
| P1 | 5 | 192.168.1.67 | K2Plus-E69E |
| P2 | 6 | 192.168.1.65 | K2Plus-E96C |

## Sequence Run
```bash
# PID calibration (both printers, parallel) - PASSED
curl -X POST http://127.0.0.1:8093/api/printer/calibrate \
  -H "Content-Type: application/json" \
  -d '{"step":"pid","armed":true,"printer_ids":[5,6]}'

# Full calibration (both printers, parallel) - TIMEOUT/STALLED
curl -X POST http://127.0.0.1:8093/api/printer/calibrate \
  -H "Content-Type: application/json" \
  -d '{"step":"all","armed":true,"printer_ids":[5,6]}'
```

## Results

### P1 (id:5, .67) — Heater/PID Issue
- **PID phase**: ✅ NOZZLE_PID + BEDPID both OK
- **Mesh phase**: Extruder target 140°C but **could not maintain temp**
  - Dropped from 140°C → 123°C → 108°C → 93°C → 89°C → 54°C over ~15 min
  - Bed cooling 86°C → 50°C (normal)
  - Fully homed (`homed_axes: "xyz"`)
- **Root cause**: PID constants saved but heater cannot hold 140°C — likely:
  - PID soak test passed but real-world mesh temp (140°C) differs from PID tune temp (230°C)
  - Heater cartridge / thermistor issue
  - PID constants need re-tune at mesh temperature

### P2 (id:6, .65) — Key1 Motor Fault
- **PID phase**: ✅ NOZZLE_PID + BEDPID both OK
- **Mesh phase**: Extruder held 140°C steady, bed cooling 80°C → 50°C
- **Failure**: After ~16 min curl timeout (exit 28), recovery attempt triggered:
  - `key60` (Internal error on command:G28) → `key1` (motor_err_detail_data)
  - **Requires hard power cycle** (off at switch, 30-60s, back on)
  - Only Y axis homed (`homed_axes: "y"`), X/Z not homed

## Key Observations

### Mesh Phase Temperature Requirements
| Parameter | Target | Notes |
|-----------|--------|-------|
| Extruder | 140°C | For BED_MESH_CALIBRATE_START_PRINT |
| Bed | 50°C | Cooling from 100°C BEDPID |

### Calibration Timeout Pattern
- Full `step="all"` takes 8-12 min → curl `-m 600` exits 28
- Backend continues running (asyncio.gather) but HTTP response lost
- Server-side result written to `/home/hunter/DemiurgeForge/smart_<pid>.json`
- **Always** use long curl timeout AND read the result file

### P1 Heater Diagnosis Needed
After PID tune at 230°C, mesh runs at 140°C — different thermal regime.
Options:
1. Re-run PID at 140°C target (if supported)
2. Check heater cartridge resistance / thermistor
3. Manual PID override for mesh temp

### P2 Recovery Required
**LO must**: Power cycle P2 (off at switch, 30-60s, on, full boot, verify manual home works)

## Next Steps
```bash
# After P2 power cycle:
curl -X POST http://127.0.0.1:8093/api/printer/select -H "Content-Type: application/json" -d '{"printer_id":5}'
curl -X POST http://127.0.0.1:8093/api/printer/select -H "Content-Type: application/json" -d '{"printer_id":6}'

# Run mesh only (13x13)
curl -X POST http://127.0.0.1:8093/api/printer/calibrate \
  -H "Content-Type: application/json" \
  -d '{"step":"mesh","armed":true,"printer_ids":[5,6]}'
```

## Files
- Smart calibration results: `/home/hunter/DemiurgeForge/smart_5.json`, `smart_6.json`
- Backend: `/home/hunter/Desktop/Projects/Demiurge_3D/Demiurge3D/backend/server.py`
- Manager: `/home/hunter/Desktop/Projects/Demiurge_3D/Demiurge3D/backend/demiurge/printer/manager.py`