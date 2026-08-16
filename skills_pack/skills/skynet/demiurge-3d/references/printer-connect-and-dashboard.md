# Printer connect & dashboard visibility (Demiurge 3D)

## Symptom
User saved printers (`K2 Plus P1`/`K2 Plus P2` at 192.168.1.65/66) but the Dashboard connection
badge stays "Disconnected" even though the printers are online and answer Moonraker on `:7125`.

## THE #1 GOTCHA: `:4408` is the nginx proxy, `:7125` is real Moonraker
- `:4408` = Creality **nginx proxy** with a **10s cap** → returns **504** on `/printer/objects/query`.
- `:7125` = the **real Moonraker** (no cap, full status API).
- `moonraker.py` says it outright: *"nginx (port 4408) has its own 10s cap, so backend calls
  should use port 7125 directly to avoid 504 Gateway Timeout."*
- `PrinterManager.get_status()` calls `_refresh_status()` on **every** poll; `_refresh_status()`
  catches any query exception and sets `connected = False`. So a connect that *looks* successful
  (liveness `/printer/info` passes even on :4408) still flips the badge to **"Disconnected"** the
  moment a status poll hits the 504. **Target `:7125` always; never `:4408`.**

## Fix path (verified this session)
1. **Clean fix — correct the saved URLs (preferred).** The DB column is `moonraker_url`
   (NOT `url`). DB writes are behind the approval gate, but the user CAN explicitly approve
   (said "yes please" this session) — when approved, run:
   ```sql
   UPDATE printers SET moonraker_url=REPLACE(moonraker_url,':4408',':7125')
     WHERE moonraker_url LIKE '%:4408%';
   ```
   After this both rows are `http://192.168.1.65:7125` / `http://192.168.1.66:7125`.
2. **Auto-connect MUST prefer `:7125` and NOT fall back to `:4408`.** The old `[7125, 4408]`
   fallback reconnects to the broken proxy and reintroduces the 504 flicker. Use
   `ports = [parsed.port] if parsed.port else [7125]` (no 4408).
3. **Dashboard**: reads `connected` from the singleton `PrinterManager`. It is empty until
   something calls `pm.connect()`. Add `POST /api/printer/select {printer_id}` → look up
   `moonraker_url` → `pm.connect(url)` so the UI can switch between P1/P2. The singleton holds
   ONE active printer; the Dashboard header has a Switch dropdown. `pm.connect` is read-only
   liveness (queries `/printer/info`) — sends NO gcode.

## Auto-connect recipe (server.py)
```python
import sqlite3 as _sq
from urllib.parse import urlparse
from demiurge.printer.manager import get_printer_manager
import demiurge.webapp.db as _wdb

async def _auto_connect_first_printer() -> None:
    pm = get_printer_manager()
    if pm.client is not None:
        return
    with _sq.connect(str(_wdb.DEFAULT_DB_PATH)) as c:
        rows = c.execute(
            "SELECT id, moonraker_url FROM printers "
            "WHERE moonraker_url IS NOT NULL AND moonraker_url <> ''"
        ).fetchall()
    for pid, url in rows:
        parsed = urlparse(url if "://" in url else f"http://{url}")
        host = parsed.hostname or ""
        ports = [parsed.port] if parsed.port else [7125]   # PREFER 7125; NEVER fall back to 4408
        for port in ports:
            try:
                res = await pm.connect(f"http://{host}:{port}")
                if res.get("connected"):
                    print(f"[startup] Auto-connected to printer {pid} at http://{host}:{port}")
                    return
            except Exception:
                continue

# inside @app.on_event("startup"):
asyncio.create_task(_auto_connect_first_printer())
```

## Verifying a fix WITHOUT probing the API (curl is blocked)
The background `process` tool's `log`/`wait` frequently returns **empty** for the long-lived
uvicorn server (output capture is unreliable in this env) — you will NOT see
`[startup] Auto-connected ...` through `process(action='log')`, even with `python -u`.
Reliable path:
1. Start uvicorn redirecting to a file:
   `.../python -u -m uvicorn server:app --host 127.0.0.1 --port 8911 > /tmp/demiurge_server.log 2>&1`
   (run as `background=true`).
2. `read_file('/tmp/demiurge_server.log')` (or `cat`) → confirm:
   `[startup] Auto-connected to printer 5 at http://192.168.1.65:7125`
   `WebSocket /api/printer/ws [accepted] — connection open`
3. Non-intrusive TCP readiness check (NOT an API call — safe when curl is blocked):
   `python -c "import socket;s=socket.socket();print(s.connect_ex(('127.0.0.1',8911)))"` → `0` = listening.

## Frontend
Add a printer switcher to the Dashboard header: list `printers` from `GET /api/account`, show each
with a live status badge, call `POST /api/printer/select` on click. `usePrinterStore` persists
`printerUrl` in localStorage (defaults to `http://localhost:7125`).

## MoonrakerClient note
`demiurge/printer/moonraker.py` uses **httpx** (not aiohttp), so the IPv6-localhost failure mode
seen with aiohttp does NOT apply to real `192.168.x` printer IPs. Reachability checks use
`connect()` / `get_printer_info()` — never gcode.
