# K2 Plus Calibration Lessons (Demiurge3D / creality-fleet)

Captured 2026-07-17 during the ENI smart-calibration build. These are durable,
repeatable techniques for the Creality K2 Plus fleet driven via the Demiurge3D
backend (`:8093`, LAN-reachable; agent shell is LAN-blind).

## 1. key766 / PR_ERR_CODE_NEED_RESET_XYZ
Exact firmware message:
```
{'code': 'key766', 'msg': 'Shutdown due to PR_ERR_CODE_NEED_RESET_XYZ:
G28 XYZ FAIL,Need to Retry G28!!', 'values': ['X_nohome:True Y_nohome:True Z_nohome:True']}
```
Fired by `BED_MESH_CALIBRATE_START_PRINT` when the printer is not homed.
**Why it happens**: any Klipper restart (e.g. PID `SAVE_CONFIG`) wipes homing.
If you fire mesh right after a restart without re-homing, you get key766.
**Fix**: HOME FIRST, then POLL `toolhead.homed_axes` until it equals `"xyz"`
before firing mesh. Helper pattern:
```python
async def _wait_homed(m, timeout=120) -> bool:
    import time as _t
    deadline = _t.monotonic() + timeout
    while _t.monotonic() < deadline:
        st = await m.get_status()
        ha = st.get("status", {}).get("toolhead", {}).get("homed_axes", "")
        if isinstance(ha, str) and set("xyz").issubset(set(ha.lower())):
            return True
        await asyncio.sleep(2)
    return False
```
Never chain mesh onto an un-homed printer — it is the #1 calibration fault.

## 2. PID autotune -> Klipper restart (503 is NOT failure)
`NOZZLE_PID\nBEDPID` triggers `SAVE_CONFIG`, which RESTARTS Klipper. The
Moonraker client drops mid-call -> `HTTP 503 Klippy Disconnected`. This is
EXPECTED. Treat "Disconnected"/"503"/"Klippy" exceptions as "PID ran, now
restarting" and wait for reconnect:
```python
async def _wait_connected(m, timeout=180) -> bool:
    import time as _t
    deadline = _t.monotonic() + timeout
    while _t.monotonic() < deadline:
        try:
            st = await m.get_status()
            if st and st.get("status"):
                return True
        except Exception:
            pass
        await asyncio.sleep(3)
    return False
```
Do NOT re-send `firmware_restart` — that caused XS300 earlier. The PID restart
is firmware-internal; just wait-reconnect and continue.

## 3. 13x13 mesh — probed_matrix vs mesh_matrix
`bed_mesh` object returns BOTH:
- `probed_matrix`: the REAL 13x13 measured points (what you enforce against).
- `mesh_matrix`: a 37x37 INTERPOLATED grid (Klipper interpolation — NOT the
  probe count). Reading `mesh_matrix` dims and comparing to 13x13 gives a
  FALSE violation (`expected [13,13], got [37,37]`).
**Correct read**: `pc = [len(probed[0]), len(probed)]`; enforce `pc == [13,13]`;
compute span (max-min) from `probed_matrix`. A healthy span is <= 0.4mm.

## 4. Long async + curl timeout loses the result
A full smart-calibrate (PID restart + reconnect wait + 13x13 mesh probe +
AUTOTUNE_SHAPERS) runs 8-12 min — past curl's `-m 600`. curl exits 28 and the
HTTP response (with the JSON result) is lost even though the backend task
finished. **Fix**: have the endpoint write its result server-side:
```python
with open(f"/home/hunter/DemiurgeForge/smart_{pid}.json", "w") as _f:
    json.dump(payload, _f, indent=2, default=str)
```
Then read `/home/hunter/DemiurgeForge/smart_<pid>.json` — never rely on the
curl stdout alone. Use a long curl timeout AND the file as the source of truth.

## 5. cali_smart.py contract (smart_calibrate)
`demiurge/printer/cali_smart.py` -> `POST /api/printer/calibrate_smart`
`{"printer_id":N,"armed":true,"apply_shaper":true}`.
Returns `{printer_id, dry_run, all_ok, results:{pid,mesh,shaper,belt}}`.
Guards per step so ONE failure doesn't kill the orchestrator (each `_send` is
try/except; mesh skips with a clear error if not homed). Home-first + wait-
homed + wait-connected are baked in. 13x13 mesh enforced. Shaper applies at
runtime (no SAVE_CONFIG). No firmware/config writes unless armed + runtime-only.

## 6. Standing rule (LO)
Home before EVERY step. One printer at a time. NO `firmware_restart` AFTER a
PID SAVE_CONFIG restart (XS300). PID SAVE_CONFIG restart is expected — wait-
reconnect, don't re-send restart on top of it.
Agent is LAN-blind: confirm hardware state via LO's screen or the backend API,
never guess.

## 7. key766 RECOVERY (printer already in shutdown)
When the printer is ALREADY in key766 shutdown (cascading from a missed re-home
after PID restart), G28 alone fails with key60 ("Internal error on command:G28").
The shutdown state must be cleared first. Recovery sequence:

1. **Cool heaters** (they may still be at PID targets): `{"action":"gcode","script":"M140 S0\\nM104 S0"}`
2. **FIRMWARE_RESTART** to clear the shutdown: `{"action":"gcode","script":"FIRMWARE_RESTART"}`
   — This is the EXCEPTION to the NO-firmware_restart rule. A printer in
     key766 shutdown NEEDS a restart to recover. The rule exists to prevent
     re-sending restart ON TOP of PID's internal SAVE_CONFIG restart (XS300).
3. **Home (G28)**: `{"action":"gcode","script":"G28"}` — expect a long timeout
   (G28 on K2 takes 15-25s, curl may exit 28; check toolhead.homed_axes after).
4. Verify `homed_axes == "xyz"` via `POST /api/printer/select`
5. **Re-run calibration** from the failed step onward

The backend API endpoint is `POST /api/printer/command` with body:
- `{"action":"gcode","script":"<raw gcode>"}` — single or multi-line gcode
- `{"action":"home"}` — convenience home
- `{"action":"temp","heater":"bed","temp":0}` — set temperature target

This sequence recovered P2 (2026-07-23): key766 → bed 72.7°C overshoot →
cooldown → FIRMWARE_RESTART → G28 → homed_axes restored to "xyz".
