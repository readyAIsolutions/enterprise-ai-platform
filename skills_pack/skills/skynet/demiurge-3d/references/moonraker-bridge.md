# Moonraker read-only state/job REST bridge — endpoint + field map

Condensed knowledge bank for `backend/demiurge/printer/moonraker_bridge.py` (read-only
STATE + JOBS) and `moonraker_fleet.py` (multi-printer aggregator). Built 2026-07-11 by
DEMIURGE3D_B01 in the parallel 12-mini build. Deliberately DISJOINT from `moonraker.py`
(the motion-capable client) — this bridge never issues gcode.

## Port rule (CRITICAL, same as the rest of the project)
Target `:7125` (real Moonraker) for ALL status/job queries. `:4408` is the Creality nginx
proxy — 10s cap → 504 on `/printer/objects/query`, flips `connected=False` every poll.
CAMERAS are the ONLY exception (`:4408/webcam/`, `:4408/webcam2/`; `:7125` 404s them).
Full recipe in `references/printer-connect-and-dashboard.md`.

## Endpoints used by MoonrakerBridge
| Path | Method | Purpose | Result field(s) |
|---|---|---|---|
| `/printer/info` | GET | klippy state + firmware | `state`, `software_version` |
| `/server/info` | GET | moonraker version | `plugins.moonraker.version` |
| `/printer/objects/query` | GET | live status (`params` = `object:attr,attr`) | `status.{extruder,heater_bed,print_stats,toolhead,virtual_sdcard,display_status}` |
| `/server/job_queue/jobs` | GET | queue state + queued jobs | `queue_state`, `queued_jobs[]` |
| `/server/job_queue/job` | POST | add job | `added_jobs[]` |
| `/server/job_queue/job` | DELETE | remove job (`json {"job_ids":[..]}`) | `removed_jobs[]` |
| `/server/job_queue/start` | POST | start queued/next job | — |
| `/server/job_queue/clear` | POST | clear/pause/reset (`json {"clear":bool}`) | — |
| `/printer/print/pause` `resume` `cancel` | POST | current-print control | — |
| `/server/files/metadata` | GET | file ETA/filament/size (`params filename`) | `size,estimated_time,filament_total,layer_height,object_height` |
| `/server/files/list` | GET | gcode file list (`params root=gcodes`) | `files[]` |

## `objects/query` field shapes (passed as `params`)
```
extruder:        temperature,target,pressure_advance
heater_bed:      temperature,target
print_stats:     state,filename,progress,print_duration,total_duration,filament_used,message
toolhead:        position,homed_axes
virtual_sdcard:  progress,is_active
display_status:  progress,message
```
Progress precedence in `snapshot()`: `print_stats.progress`, else `virtual_sdcard.progress`.

## Dry-run kill-switch
Global `CALI_DRY_RUN=1|true|yes|on` (or per-instance `MoonrakerBridge(..., dry_run=True)`)
makes every MUTATING op (`add_job/remove_job/start_job/clear_queue/pause_print/...`)
return `{"status":"dry_run","skipped":True,...}` with NO network call. Read-only queries
are unaffected. Test: assert no mutating path was hit when dry-run is set.

## Per-printer fault isolation (fleet)
`MoonrakerFleet.snapshot_all()` wraps each `bridge.snapshot()` in try/except inside an
`asyncio.gather`; a failing printer becomes `FleetSnapshot.members[name]=None` +
`errors[name]`, the others stay populated. One dead K2 Plus can never wedge the dashboard.
`FleetSnapshot` exposes `.printing / .ready / .down / .count`. `is_alive_all()` degrades
gracefully to `False` per member.

## Test harness (zero-network, no respx/pytest-asyncio)
Inject a `MockMoonraker` implementing the `httpx.AsyncClient` subset:
```python
async def request(self, method, path, params=None, json=None, data=None, files=None):
    ...
    return MockResponse(status_code, json_data)   # has .json(), .text, .is_success, .reason_phrase
```
Serve realistic K2 Plus JSON per path; inject transient 503s on `/printer/info` to exercise
the bounded-retry path (retries 502/503 + "klippy host not connected"). Runs the FULL module
with zero network/printer. See `tests/test_moonraker_bridge.py` + `tests/test_moonraker_fleet.py`
(47 passing as of 2026-07-11 — 24 bridge + 23 fleet; grew from 37 when the `probe_connection`
UI seam and the `fleet_from_config`/`fleet_from_endpoints` integration seam were added).

## Read-only connection probe (`probe_connection`)
`probe_connection(ip, *, api_key="", timeout=8.0, dry_run=None, client=None)` is the
READ-ONLY "Test connection" seam a settings UI button should call — NOT a second ad-hoc
HTTP client. It issues ONLY GET `/printer/info` + `/server/info` (never gcode/motion) and
returns `{"online", "klippy_state", "moonraker_version", "error", "dry_run"}`.

**Error-surfacing technique (reusable):** `MoonrakerBridge.is_alive()` *swallows* the
underlying reason (returns `False` on any HTTP/connection error). To give the UI a real
reason string, `probe_connection` calls `await bridge._request("GET", "/printer/info")`
directly inside the same module and catches `MoonrakerBridgeError` — surfacing
`"HTTP 404 Error: ..."` / connection-refused text instead of a bare red dot. Use this
pattern whenever you need WHY a printer is down, not just whether.

Honors `CALI_DRY_RUN` / `dry_run=True` → returns `{"online": False, "dry_run": True}` with
zero network calls. B09's settings "Test connection" button should `from demiurge.printer
.moonraker_bridge import probe_connection` and call it (GET-only, never send_gcode).

## Integration seam: `fleet_from_config` / `fleet_from_endpoints`
`MoonrakerFleet` is printer-agnostic, but the dual-K2 orchestrator/dashboard should NOT
hand-spin ad-hoc `MoonrakerBridge` instances. The single seam to use instead:
- `PrinterEndpoint(name, ip, api_key="")` — schema-agnostic endpoint spec.
- `fleet_from_endpoints([...], *, dry_run=None, **bridge_kw)` — builds the fleet from a
  list of `PrinterEndpoint` / dict / attribute-object specs; raises `MoonrakerFleetError`
  on any entry missing `name` or `ip`. `**bridge_kw` (e.g. `client=MockMoonraker()`) is
  forwarded to every bridge — use it in tests.
- `fleet_from_config(settings, *, key="printers", dry_run=None, **bridge_kw)` — builds the
  fleet from a `settings` object, schema-agnostically: a mapping `settings[key]` (list of
  endpoints, OR a `name -> ip` dict, OR `name -> endpoint` dict) or an object attribute
  `settings.<key>`. Each entry is normalized by `_normalize_endpoint` so it works unchanged
  with B09's `PrinterConfig`, plain dicts, or `PrinterEndpoint`. Missing/empty → empty (but
  valid) fleet, never raises.

Usage: `fleet = fleet_from_config(app_settings); snap = await fleet.snapshot_all()` — one
concurrent call snapshots the whole bench with per-printer fault isolation. Flag B11 (and
any dual-printer orchestrator) to swap its two bridges for this.

## Pitfalls
- Reuse the injectable `client=` kwarg; do NOT monkeypatch httpx internals in tests.
- `probe_connection` surfaces the error *reason*; if you only need a boolean, `is_alive()`
  is fine, but a UI "why offline" panel needs the direct `_request` + catch pattern above.
- Test gotcha: reassigning `mock.request = _boom` (to inject a 404/503 on one path) trips a
  Pyright `reportAttributeAccessIssue` false-positive (the method signature narrows) — it
  runs fine under `pytest`, so ignore the LSP squiggle; keep the pattern consistent with the
  rest of `test_moonraker_bridge.py`.
- `get_klippy_state()` swallows errors → `KlippyState.DISCONNECTED` (never crash the
  dashboard); methods that must surface faults (e.g. `get_jobs`) raise `MoonrakerBridgeError`
  after the bounded retry budget is exhausted.
- `add_job` returns a `QueuedJob` on success but a `{"status":"dry_run",...}` dict on
  dry-run — callers must handle both shapes.
- `clear_queue(mode)` only accepts `clear|pause|reset`; bad mode raises `ValueError` BEFORE
  any network call.
- `eta_remaining` is a naive linear model (`total_duration/progress - total_duration`);
  UNVALIDATED vs Moonraker's own ETA on a live print.
