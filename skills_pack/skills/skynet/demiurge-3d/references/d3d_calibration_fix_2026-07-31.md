# Demiurge 3D — K2 Calibration Fix (2026-07-31)

## Summary
Fixed calibration failures on both Creality K2 Plus printers (P1 .67, P2 .65) by addressing the root cause: **Klipper reports "ready" ~2s after PID SAVE_CONFIG restart but Y stepper/probe needs 12-15s more**.

## Files Modified
- `backend/demiurge/printer/manager.py` — calibration loop with 12s settle + retry logic
- `backend/demiurge/printer/cali_smart.py` — smart calibrate orchestrator with retries
- `backend/server.py` — calibrate endpoint with auto-reconnect via `hub.ensure()`

## Fixes

### 1. Extended Settle After PID Restarts (manager.py:430)
```python
# After PID macros complete, before M17/G28/ACCURATE_G28/mesh/zaxis
if macro in ("M17", "G28", "ACCURATE_G28", "BED_MESH_CALIBRATE_START_PRINT", "Z_AXIS_CALIBRATION") and prev_macro in ("NOZZLE_PID", "BEDPID"):
    await asyncio.sleep(12.0)  # Y stepper/probe enable delay
```

### 2. Mesh Retry with Re-home (manager.py:455)
```python
mesh_retries = 2 if macro == "BED_MESH_CALIBRATE_START_PRINT" else 1
# On retry failure: re-home then retry
await self.client.send_gcode("ACCURATE_G28", timeout=GC_HOME_TIMEOUT, dry_run=dry_run)
await asyncio.sleep(2.0)
```

### 3. Z-axis Retry (manager.py:457)
```python
zaxis_retries = 2 if macro == "Z_AXIS_CALIBRATION" else 1
```

### 4. G28/ACCURATE_G28 Retry (manager.py:436)
```python
g28_retries = 4 if macro in ("G28", "ACCURATE_G28") else 1
# 3s settle between retries
```

### 5. Smart Calibrate Retries (cali_smart.py)
- 12s settle after PID before mesh
- Mesh: 2 retries with re-home
- Z-axis: 2 retries with settle
- 3s between retries

### 6. Auto-Reconnect Endpoint (server.py:1934)
```python
for pid in printer_ids:
    with _sq.connect(str(_wdb.DEFAULT_DB_PATH)) as c:
        row = c.execute("SELECT moonraker_url FROM printers WHERE id = ?", (pid,)).fetchone()
    if row:
        m = await hub.ensure(pid, row[0])  # Reconnects after PID restart
        targets.append(pid)
```

## Calibration Sequence (All Steps Pass)
```
NOZZLE_PID → BEDPID → 12s settle → M17 → 5s settle → G28 (retry×4) → ACCURATE_G28
→ BED_MESH_CALIBRATE_START_PRINT (13×13, retry×2) → Z_AXIS_CALIBRATION (retry×2)
→ AUTOTUNE_SHAPERS → PRINT_CALIBRATION → Belt read
```

## Error Codes Fixed
| Code | Meaning | Fix |
|------|---------|-----|
| key766 | G28 XYZ FAIL (mesh) | 12s settle + mesh retry with re-home |
| key22 | No trigger on y (zaxis) | 12s settle + zaxis retry with re-home |
| key60 | Internal error on G28 | Hard power cycle only (firmware interlock) |

## Verification Commands
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

## Result
✅ Both printers: 10/10 calibration steps passed
- NOZZLE_PID, BEDPID, M17, G28, ACCURATE_G28
- BED_MESH_CALIBRATE_START_PRINT (13×13), Z_AXIS_CALIBRATION
- AUTOTUNE_SHAPERS, PRINT_CALIBRATION, Belt read