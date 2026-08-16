# K2 Calibration Session — 2026-07-31

## Summary
**FULL CALIBRATION PASSED on BOTH printers** after deploying root-cause fixes.

## Printer Status
| Printer | ID | IP | Hostname | Result |
|---------|-----|-----|----------|--------|
| P1 | 5 | 192.168.1.67 | K2Plus-E69E | ✅ PASSED (after power cycle) |
| P2 | 6 | 192.168.1.65 | K2Plus-E96C | ✅ PASSED |

## Root Cause Fixed
**After PID SAVE_CONFIG restarts, Klipper reports "ready" in ~2s but Y stepper/probe needs 12-15s more.** The previous 5s settle was insufficient.

## Fixes Deployed

### 1. manager.py — Enhanced calibration loop
- **12s settle** after PID macros (NOZZLE_PID, BEDPID) before M17/G28/ACCURATE_G28/mesh/zaxis
- **Mesh retry**: 2 attempts with re-home between (fixes key766)
- **Z-axis retry**: 2 attempts with settle (fixes key22)
- **G28/ACCURATE_G28 retry**: 4 attempts with 3s settle
- Extended settle after M17 (5s) before G28

### 2. cali_smart.py — Smart calibrate orchestrator
- 12s settle after PID before mesh
- Mesh retry (2 attempts) with re-home
- Z-axis retry (2 attempts) with settle
- 3s settle between retries

### 3. server.py — Auto-reconnect endpoint
- `hub.ensure(pid, url)` in calibrate endpoint auto-reconnects after PID restarts
- Survives Klipper SAVE_CONFIG disconnection for multi-printer runs

## Calibration Sequence (all steps passed)
```
NOZZLE_PID → BEDPID → 12s settle → M17 → 5s settle → G28 (retry) → ACCURATE_G28
→ BED_MESH_CALIBRATE_START_PRINT (13×13, retry) → Z_AXIS_CALIBRATION (retry)
→ AUTOTUNE_SHAPERS → PRINT_CALIBRATION → Belt read
```

## Curl Commands (for future runs)
```bash
# P1 full calibration
curl -X POST http://127.0.0.1:8093/api/printer/calibrate \
  -H "Content-Type: application/json" \
  -d '{"step": "all", "armed": true, "printer_ids": [5]}' --max-time 2000

# P2 full calibration  
curl -X POST http://127.0.0.1:8093/api/printer/calibrate \
  -H "Content-Type: application/json" \
  -d '{"step": "all", "armed": true, "printer_ids": [6]}' --max-time 2000
```

## Key Firmware Behaviors Confirmed
- `key60` (Internal error on G28) = latched fault, **only hard power cycle clears**
- `key766` (G28 XYZ FAIL) = Y stepper/probe not ready after PID restart — fixed by 12s settle + retry
- `key22` (No trigger on y) = same root cause — fixed by retry with re-home
- `toolhead.homed_axes` stays `''` even after successful ACCURATE_G28 — never gate on it
- PID autotune triggers SAVE_CONFIG → Klipper restart (503 mid-call) — EXPECTED

## Verification
Both printers completed all 10 calibration steps successfully:
✅ NOZZLE_PID ✅ BEDPID ✅ M17 ✅ G28 ✅ ACCURATE_G28
✅ BED_MESH_CALIBRATE_START_PRINT (13×13) ✅ Z_AXIS_CALIBRATION
✅ AUTOTUNE_SHAPERS ✅ PRINT_CALIBRATION ✅ Belt read