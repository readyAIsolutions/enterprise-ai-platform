# Read-only Moonraker boot-smoke + route-scan (Creality K2 Plus)

Verified 2026-07-11 (D3D06) against the two live K2 Plus units. Use this when
building any ADD-ONLY, GET-only verification module for the fleet.

## The two read-only verification targets
- `http://192.168.1.65:7125` (K2Plus-E69E)
- `http://192.168.1.66:7125` (K2Plus-E96C)

`:7125` is the real Moonraker port (NOT `:4408`, the nginx proxy that 504s
status queries — see the main skill's `:4408` vs `:7125` gotcha). A GET-only
smoke against these is SAFE: it never starts a print or sends gcode.

## Client construction — MUST set base_url for relative paths
`httpx.AsyncClient()` with no `base_url` CANNOT resolve a relative path like
`/printer/info` → raises `httpx.UnsupportedProtocol`. If your probes call
`client.get("/printer/info", ...)` (relative), build the client with
`base_url=target_url.rstrip("/")`. If you call with full URLs instead, base_url
is unnecessary. Either way, the live run is the only place this is caught (see
the fake-client pitfall below).

```python
def _build_default_client(target_url: str, timeout: float) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=target_url.rstrip("/"),
        timeout=httpx.Timeout(timeout, connect=min(3.0, max(1.0, timeout * 0.4))),
        follow_redirects=False,
        verify=False,  # both targets are plain http:// -> harmless
    )
```

## Read-only route allowlist (GET only)
Safe to probe (no motion, no print, no upload):
`/api/version`, `/printer/info`, `/server/info`, `/machine/system/info`,
`/printer/objects/list`, `/printer/objects/query` (params
`extruder=&heater_bed=&print_stats=`), `/server/files/list` (params `root=gcodes`),
`/server/config`, `/server/database/list`.

NEVER include mutating routes in a scan: `/printer/gcode/script`,
`/printer/print/start`, `/printer/print/pause|resume|cancel`,
`/printer/emergency_stop`, `/server/files/upload`. Assert in a test that only
`GET` (never POST/DELETE) is issued.

## Creality K2 Plus firmware quirks (BOTH printers online, verified)
- `/machine/system/info` → **404**. Expected on this firmware build. It is an
  *informational capability gap*, NOT a printer fault — do NOT let it flip a
  healthy printer to DEGRADED. Record it as `system_info_available=degraded`
  but EXCLUDE it from the health-gating set.
- `/api/version` → 200 but a **bare dict** (`{"version":..., "app":"moonraker"}`),
  NO `result` envelope.
- `/server/files/list` → `result` is a **LIST** of file dicts, not a dict.
- `/printer/info`, `/server/info`, `/printer/objects/list`,
  `/printer/objects/query`, `/server/config`, `/server/database/list` → normal
  `{"result": {...}}` envelope.

## Robust route classifier
```python
def classify(status_code: int, body) -> ProbeStatus:
    if status_code == 200 and isinstance(body, dict):
        return OK            # 200 + JSON = endpoint present & responsive,
                             # regardless of result-envelope shape
    if status_code == 404:  return FAIL      # absent (not an error)
    if status_code in (401, 403): return DEGRADED  # present but auth-gated
    if 500 <= status_code < 600: return DEGRADED
    return DEGRADED
```
`has_result` is informational: `isinstance(body, dict) and "result" in body`
(true for both dict- and list-valued `result`).

## Health gating (do NOT penalize optional-endpoint 404s)
Gate `overall` ONLY on genuine health signals:
`reachable, klipper_ready, moonraker_link, firmware_present` (key off
`software_version` from `/printer/info`, NOT `/machine/system/info`),
`temps_sane` (plausible envelope e.g. -10..400 °C), `print_state_known`.
A 404 on `/machine/system/info` is informational and must stay out of the gate.

## PITFALL — a fake HTTP client masks real construction bugs
When you hand-roll a fake `httpx.AsyncClient` (the recommended no-dep test
pattern), it almost always ignores the request *path/args*. So a bug in how you
BUILD the real client never fires in unit tests. This session `fleet_smoke.py`
built `httpx.AsyncClient()` with no `base_url` then called
`client.get("/printer/info")` — all 14 unit tests passed, but the live run
threw `httpx.UnsupportedProtocol`. **After unit tests go green, ALSO run a real
read-only smoke against the actual endpoint** before declaring the module done.

## Live smoke command (gold-standard verification for a read-only module)
```bash
cd /home/hunter/Desktop/demiurge-3d/backend
../.venv/bin/python -m demiurge.printer.fleet_smoke --live --timeout 6 --json
```
GET-only, safe. Verified result this session: both printers `healthy`
(Klipper `ready`; E69E mid-print at 244.9 °C/paused, E96C cool/complete),
route-scan **8 present / 1 absent** per printer (only `/machine/system/info`
absent). If the printers are powered off, you'll see `overall=offline` with the
real error string — also valid evidence.

## Swarm collision note
Search CONCEPT variants (`smoke`/`boot`/`probe`/`scan`/`health`/`verify`/`status`),
not just your chosen filename, before building — a sibling's `fleet_boot_smoke.py`
already implemented this exact slice under a different name. If a sibling owns the
concept, flag the collision in STATUS for MASTER dedupe and build a DISTINCT
value-add rather than a second implementation.
