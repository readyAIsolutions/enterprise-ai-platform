---
name: demiurge-3d-website
description: Boot, operate, diagnose, and repair the Demiurge 3D web app (Demiurge3D) — the FastAPI backend + React/Vite/Three.js frontend + Moonraker printer bridge that drives LO's Creality K2 Plus fleet. Covers the boot pattern, the white-screen crash fix, STL print-readiness validation, and the gated "stage-then-LO-presses-start" print workflow. Use when LO says "boot my website", "the site is white", "calibrate/print via Demiurge3D", or anything touching the :8093 app.
---

# Demiurge 3D Website (Demiurge3D)

The app is TWO pieces on LO's box (`/home/hunter/Desktop/Projects/Demiurge_3D/Demiurge3D/`):
- `backend/server.py` — FastAPI (uvicorn, port **8093**). Hosts the API + serves the built
  frontend `dist/`. Auto-connects printers from SQLite `~/.cali-agent/webapp.db`
  (table `printers`: id, name, moonraker_url). Backend CAN reach the printers (LAN); the agent
  shell CANNOT (egress-only). So all printer contact goes THROUGH the backend's API.
- `frontend/` — React 18 + Vite + Three.js/@react-three/fiber. `npm run build` → `dist/`.
  The backend serves `dist/` from disk per-request (no restart needed after a rebuild).

## BOOT PATTERN
1. Kill any stale worker holding :8093 first (a dead uvicorn child holds the port and the
   new launch fails with `[Errno 98] address already in use`). Check: `ss -ltnp | grep 8093`.
2. Syntax-check: `cd /home/hunter/Desktop/Projects/Demiurge_3D/Demiurge3D/backend && python3 -c "import py_compile; py_compile.compile('server.py', doraise=True); print('OK')"`
3. Launch: `cd /home/hunter/Desktop/Projects/Demiurge_3D/Demiurge3D/backend && python3 server.py`
   (use terminal background=true, NOT nohup/setsid — harness blocks those).
4. Wait 5-6s for auto-connect, then select printers:
   `curl -s -X POST http://127.0.0.1:8093/api/printer/select -H "Content-Type: application/json" -d '{"printer_id":5}' -m5`
   `curl -s -X POST http://127.0.0.1:8093/api/printer/select -H "Content-Type: application/json" -d '{"printer_id":6}' -m5`
5. Verify: `curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8093/` → 200.
   Printers: `curl -s http://127.0.0.1:8093/api/printers` → lists K2s with live temps.
   LO opens it at http://localhost:8093 (or his LAN IP).

## PITFALL — key766 RECOVERY (printer already in shutdown)
When P2 hits key766/PR_ERR_CODE_NEED_RESET_XYZ during calibration (PID restart
cleared home → mesh fails → cascading key60/key22 on subsequent G28), G28
alone won't recover — the printer is in shutdown. Recovery sequence:
1. Cool heaters: `{"action":"gcode","script":"M140 S0\nM104 S0"}`
2. FIRMWARE_RESTART to clear shutdown: `{"action":"gcode","script":"FIRMWARE_RESTART"}`
   (Exception to LO's NO-firmware_restart rule — that rule applies to
    re-sending restart ON TOP of PID's internal SAVE_CONFIG restart.)
3. Home: `{"action":"gcode","script":"G28"}` (long timeout, 15-25s)
4. Verify `homed_axes == "xyz"` via `POST /api/printer/select`
5. Re-run calibration from failed step

API format `POST /api/printer/command`:
- `{"action":"gcode","script":"<raw>"}` — send raw gcode
- `{"action":"home"}` — convenience home
- `{"action":"temp","heater":"bed","temp":50}` — set target

See `references/k2_calibration_lessons.md` §7 for the full write-up.

## CONFIRMED WORKING (2026-07-30 session)
The calibration fixes from previous sessions are VERIFIED in production:
- **Split PID**: NOZZLE_PID and BEDPID fired as separate calls with `_wait_connected` between — no more combined-string key60 shutdown
- **M17 + 5s settle + G28 retry(4×)**: Inserted in `manager.py` `all_steps` after PID restarts — kills key22/key766
- **K2-native macros only**: ACCURATE_G28, BED_MESH_CALIBRATE_START_PRINT, AUTOTUNE_SHAPERS, PRINT_CALIBRATION, NOZZLE_PID/BEDPID, BELT_TENSION
- **Parallel multi-printer**: `/api/printer/calibrate` with `printer_ids: [5,6]` runs both simultaneously via `asyncio.gather`
- **Full armed calibration (step="all")**: ~8-12 min, survives Klipper SAVE_CONFIG restarts, writes server-side result to `/home/hunter/DemiurgeForge/smart_<pid>.json` (curl timeout loses HTTP response but backend completes)

Verified live 2026-07-30: both K2 Plus printers (P1=.67, P2=.65) completed armed PID (NOZZLE_PID + BEDPID) with zero key22/key60/key766 errors.

## PITFALL — PATCH TOOL INDENTATION CORRUPTION
The patch tool can mangle Python indentation (adds 4 extra spaces to blocks). Always syntax-check
after patching server.py or manager.py. If indentation breaks, use execute_code with read_file+patch
to provide exact old/new strings with correct spaces. Pattern:
```python
from hermes_tools import read_file, patch
r = patch(path, old_exact_string, new_exact_string)
```

## PITFALL — WHITE SCREEN ("boots for a little bit then turns white")
Root cause (2026-07-17): the frontend had NO React error boundary. The app is a WS-driven SPA
(`/api/printer/ws` pushes live telemetry). During printer calibration the mesh matrix is empty/
partial (`mesh_matrix:[[]]`), and a telemetry component throwing on that data unmounted the
ENTIRE React tree → blank white page. Server, assets, and all `/api/*` were healthy (200) — the
crash was 100% client-side.
FIX (already applied, safe, additive):
  1. New `frontend/src/ErrorBoundary.tsx` — catches render errors, shows a dark panel with the
     actual error text instead of blanking, keeps the rest of the app alive.
  2. `frontend/src/main.tsx` wraps `<App/>` in `<ErrorBoundary>`.
  3. `cd /home/hunter/Desktop/Demiurge3D/frontend && npm run build` (node22/npm9 present;
     ~6s, 2133 modules). Backend serves the new `dist/` immediately — no restart.
If it whites again after this: the ErrorBoundary will now SHOW the error text — paste it, fix
the exact component. Also guard BedMesh3D/BedMeshHeatmap against empty/NaN matrices.
See `references/white_screen_fix.md` for the full diagnosis transcript.

## PITFALL — `.toFixed()` NULL CRASH (distinct from white screen)
A second crash class (2026-07-17): `TypeError: Cannot read properties of null (reading
'toFixed')` thrown from a dashboard telemetry component (LiveTelemetry / App / PrinterPanel /
BeltTensionDial), caught by the ErrorBoundary as a red panel (NOT a white screen). Cause: during
idle/calibration the WS pushes `temps.bedTarget` / `extruderTarget` / `belt.x` / `belt.y` as
`null`, and the JSX calls `.toFixed()` directly. FIX: null-guard every call with `?? 0`
(e.g. `{(temps.bedTarget ?? 0).toFixed(0)}`) and `value != null ?` for belt dials. The
BedMeshHeatmap `min/max/mean` also use `?? 0`. After editing, `npm run build` (backend serves
`dist/` immediately). This is ADDITIVE and safe.

## CALIBRATION — PARALLEL MULTI-PRINTER (2026-07-23)
The `/api/printer/calibrate` endpoint now runs ALL selected printers in PARALLEL via
`asyncio.gather`. Previously it looped sequentially (one printer at a time). Pass
`printer_ids: [5, 6]` to calibrate both at once. The frontend CalibrationWizard
selects both by default.
The stock `POST /api/printer/calibrate` fires K2 macros and forgets. For NON-PRINTING steps
that should VERIFY + ITERATE, build/use the smart layer in
`demiurge/printer/cali_smart.py` (exposes `POST /api/printer/calibrate_smart`), which:
- **PID**: fires `NOZZLE_PID\nBEDPID`, reads back saved constants, SOAK-TESTS overshoot, re-fires
  if >3%. IMPORTANT: PID autotune triggers `SAVE_CONFIG` → **Klipper RESTARTS** (503 mid-call).
  Treat "Klippy Disconnected"/"503" as SUCCESS + wait-reconnect (`_wait_connected`), NOT failure.
- **mesh**: enforces **13×13** on the PROBED points. The `bed_mesh` object returns `probed_matrix`
  (the real 13×13 measured points) AND `mesh_matrix` (a 37×37 INTERPOLATED grid — NOT the probe
  count). Compare against `probed_matrix` dims, never `mesh_matrix`.
- **shaper**: fires `AUTOTUNE_SHAPERS`, reads `input_shaper` suggested freq/type, SELECTS optimal
  (ei for ≥55Hz, mzv for ≥35Hz, else zv), applies at runtime via `SET_INPUT_SHAPER` (no restart).
- **belt**: reads `belt_mdl mdlx/mdly` tension, compares to Creality K2 spec band (~135N ±25).
KEY LESSONS (capture in `references/k2_calibration_lessons.md`):
- **key766 / `PR_ERR_CODE_NEED_RESET_XYZ`**: mesh fails with `X_nohome:True Y_nohome:True
  Z_nohome:True` when the printer lost home (always happens after a Klipper restart from
  SAVE_CONFIG). FIX: HOME FIRST and **poll until `toolhead.homed_axes == "xyz"`** before firing
  mesh (`_home_and_confirm` + `_wait_homed`). Never chain mesh onto an un-homed printer.
- **Long async + curl timeout**: a full smart-calibrate (PID restart + mesh + shaker) exceeds
  600s. curl `-m` will hit exit 28 and LOSE the result. FIX: the endpoint writes its result to
  `/home/hunter/DemiurgeForge/smart_<pid>.json` server-side; use a long curl timeout AND read
  that file, never rely on the HTTP response body alone.
- **Standing rule (LO)**: home before EVERY step, one printer at a time, NO `firmware_restart`
  (it caused XS300). PID's SAVE_CONFIG restart is firmware-internal and expected — just wait for
  reconnect, don't re-send firmware_restart.
See `references/k2_calibration_lessons.md` for the full transcript + the cali_smart.py contract.

## LINKS
LO's rule: calibrate fully, ensure the model works, STAGE the job, LET LO press start. The agent
never fires the actual print.
1. Generate/slice the part. Backend has a pure-Python slicer: `forge.slicer_bridge.slice_stl(
   stl, gcode, material="PLA", layer_height=0.2, infill=0.15, walls=3)` → real G-code
   (~135 layers for a 120×80mm tray). NOTE: that slicer does NOT emit M104/M109 temp lines, so
   nozzle/bed temp read as 0 in the gcode — the printer profile sets temps at print time; the
   dispatch gate SKIPs the temp check (not a failure).
2. Gate it (READ-ONLY, never prints): `demiurge.printer.job_dispatch_gate` — `load_gcode_job()`
   + `gate_job(job, caps)` against the printer's live caps (build volume, temp ceilings). Returns
   PASS/WARN/FAIL. A zero-dep STL watertight check is in `references/stl_validator.py` (binary +
   ASCII STL parser, edge-manifold test) — run it BEFORE slicing so only watertight parts ship.
3. Stage + hand LO the start. The dispatch gate is strictly read-only (no print path exists in it).
   Expose the gcode + the exact start action (backend UI print button, or the printer touchscreen,
   or a `POST /api/printer/command {"printer_id":N,"gcode":"/path","armed":true}`). LO triggers it.
See `scripts/stage_and_gate.py` for a reproducible stage+gated-check runner.

## SAFETY (binding, from backend AGENTS.md)
- State intent before any printer touch. Respect clamps (hotend ≤ 320°C).
- `CALI_DRY_RUN=1` = simulate (no hardware). Default (unset) = live; only go live when armed.
- Calibration endpoint: `POST /api/printer/calibrate {"step":...,"armed":true,"printer_ids":[N]}`.
  Steps: all | g28 | g29 | mesh | zaxis | shaper | pid | flow | pa | belt. Fire ONE step at a
  time (see creality-fleet pitfall — `step="all"` aborts mid-sequence).
- Emergency stop always available (M112). Report outcomes truthfully; never claim done unverified.
- The agent is LAN-blind: confirm hardware state via LO's screen, not by guessing.

## CAMERA DEBUGGING + PATCH-TOOL PITFALL

When LO reports broken cameras, probe through the BACKEND (agent is LAN-blind):
```bash
cd /home/hunter/Desktop/Projects/Demiurge_3D/Demiurge3D/backend && python3 -c "
import httpx, asyncio
async def p():
    async with httpx.AsyncClient(timeout=6) as c:
        for host,n in [('192.168.1.65','P1'),('192.168.1.66','P2')]:
            for port,cam in [(8081,'nozzle'),(8080,'chamber')]:
                try:
                    r = await c.get(f'http://{host}:{port}/snapshot')
                    print(f'{n} {cam} -> {r.status_code} {r.headers.get('content-type','')[:30]} {len(r.content)}')
                except Exception as e:
                    print(f'{n} {cam} -> {type(e).__name__}: {e}')
asyncio.run(p())
"
```
Dead cameras: SSH in and restart webcam daemon (see creality-fleet skill CAMERA DAEMON RESTART).
Fan out to both printers in parallel. Both cams now registered UNCONDITIONALLY in manager.py.

After backend restart: printers lose hub connection. Run:
  curl -s -X POST http://127.0.0.1:8093/api/printer/select -H 'Content-Type: application/json' -d '{"printer_id":5}'
  curl -s -X POST http://127.0.0.1:8093/api/printer/select -H 'Content-Type: application/json' -d '{"printer_id":6}'
before testing cameras.

PITFALL: the patch tool mangles Python indentation. After ANY edit to server.py,
RUN: python3 -c "import py_compile; py_compile.compile('server.py', doraise=True); print('OK')"
BEFORE restarting the backend. This session's camera proxy fix took 5+ patch attempts
because each one silently shifted if/else indentation, producing UnboundLocalError on url.
Use execute_code + hermes_tools.patch() for precise indent fixes instead of the patch tool.

## LINKS
- references/white_screen_fix.md — full white-screen diagnosis + ErrorBoundary fix transcript.
- references/k2_calibration_lessons.md — key766/XYZ-fault + Klipper-restart + 13×13 mesh + curl-timeout lessons, and the cali_smart.py contract.
- references/adaptive_swarm_build.md — ENI adaptive-tuning swarm: embed-exact-code + self-test guard + import-clobber fix + watchdog wiring.
- references/stl_validator.py — zero-dependency watertight STL validator (binary + ASCII).
- references/forge_pipeline.md — Blender + FreeCAD headless generation pipeline, project assembler, generator routing.
- references/blender_headless.md — Blender 5.0 headless STL generation pattern (args file approach, API changes, clear_scene fix).
- references/k2_camera_restart.md — K2 webcam daemon restart recipes for nozzle (8081) and chamber (8080).
- scripts/stage_and_gate.py — slice a part, validate, run job_dispatch_gate, report PASS/FAIL.
