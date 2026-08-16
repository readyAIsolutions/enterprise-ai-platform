# K2 Calibration Fixes — 2026-07-31 Session
## Root Cause: Extended Settle Needed After PID Restarts

**Previous fix (2026-07-28)** inserted `M17` + 5s settle + G28 retry(4×) before mesh/zaxis.
**This session proved 5s is INSUFFICIENT** — Y stepper/probe needs **10-15s after PID SAVE_CONFIG restarts**.

### What Happened
- NOZZLE_PID + BEDPID both passed (each triggers SAVE_CONFIG + Klipper restart)
- After PID restarts, Klipper reports "ready" in ~2s (`_wait_for_klippy_ready` returns)
- But Y stepper + bed probe need ~10-15s MORE to enable
- Mesh (BED_MESH_CALIBRATE_START_PRINT) fired too early → `key766: G28 XYZ FAIL`
- Z_AXIS_CALIBRATION fired too early → `key22: No trigger on y`

### Enhanced Fix Applied (manager.py + cali_smart.py)

**manager.py** - Enhanced calibration loop:
```python
# Extended settle after PID macros complete
if macro in ("M17", "G28", "ACCURATE_G28", "BED_MESH_CALIBRATE_START_PRINT", "Z_AXIS_CALIBRATION") 
   and prev_macro in ("NOZZLE_PID", "BEDPID"):
    await asyncio.sleep(12.0)  # 12s settle for Y stepper/probe after PID restarts

# Retry logic for mesh (key766) and zaxis (key22)
mesh_retries = 2 if macro == "BED_MESH_CALIBRATE_START_PRINT" else 1
zaxis_retries = 2 if macro == "Z_AXIS_CALIBRATION" else 1

# On retry: re-home with ACCURATE_G28 before re-firing mesh/zaxis
if macro in ("BED_MESH_CALIBRATE_START_PRINT", "Z_AXIS_CALIBRATION") and attempt < max_r - 1:
    await m.command("calibrate", step="g28", dry_run=dry_run)
    await asyncio.sleep(2.0)
```

**cali_smart.py** - Smart calibrate orchestrator:
- 12s settle after PID before mesh
- Mesh retry (2 attempts) with re-home between
- Z-axis retry (2 attempts) with settle
- Reuses manager's retry logic

### Printer States This Session
| Printer | IP | State | Issue |
|---------|-----|-------|-------|
| P1 | 192.168.1.67 | **key60 fault** | Latched after calibration; requires hard power cycle |
| P2 | 192.168.1.65 | **Offline** | Powered off; needs power-on |

### Verification Commands
```bash
# After P1 power cycle, run full calibration:
curl -X POST http://127.0.0.1:8093/api/printer/calibrate \
  -H "Content-Type: application/json" \
  -d '{"step": "all", "armed": true, "printer_ids": [5]}' --max-time 2000

# Read server-side result (curl may timeout but backend continues):
cat /home/hunter/DemiurgeForge/smart_5.json
```

### Key Lessons Reinforced
1. **NEVER rely on `_wait_for_klippy_ready` alone** — it returns ~2s after restart, Y stepper/probe needs 10-15s more
2. **Key60 = latched internal fault** → ONLY hard power cycle clears (off 30-60s)
3. **Key22/Key766 = code sequence bug, NOT hardware** — LO confirmed "there is nothing wrong with my hardware"
4. **Debug YOUR code sequence FIRST** before assuming HW issues
5. **Mesh phase runs at 140°C extruder** (different from PID tune at 230°C) — PID soak at 230°C doesn't guarantee 140°C stability