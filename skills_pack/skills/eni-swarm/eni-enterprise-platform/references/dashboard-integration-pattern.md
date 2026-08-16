# Dashboard Integration Pattern

Complete recipe for building/re-building the enterprise dashboard.

## Architecture

```
enterprise/dashboard/
├── server.py           # Starlette app on :8421
├── run_validation.py   # Standalone subprocess script
├── templates/
│   └── dashboard.html  # Jinja2 template (dark theme)
├── static/
│   └── style.css       # Dark terminal CSS
└── tests/
    ├── __init__.py
    └── test_dashboard.py
```

## server.py Recipe

1. **Use Starlette, not FastAPI** — lighter weight, fewer deps
2. **Use `jinja2.Environment` directly** — NOT `Jinja2Templates` (Python 3.14 bug)
3. **Subprocess validation** — call `run_validation.py` via `subprocess.run()`, never import enterprise modules directly
4. **WiFi from `iw` command** — `subprocess.run(["iw", "dev", "wlp4s0", "link"])` instead of WiFiReader class
5. **Turbocharger from HTTP** — `urllib.request.urlopen("http://localhost:8922/health")`
6. **5-second cache** for validation results
7. **Routes**: `/`, `/api/score`, `/api/modules`, `/api/swarm`, `/api/events`, `/api/health`
8. **`__main__` block** with `uvicorn.run(app, host="0.0.0.0", port=8421)`

## run_validation.py Recipe

Standalone script that prints validation JSON to stdout:
```python
import json, sys
sys.path.insert(0, "/home/hunter/Desktop/Enterprise Builder")
import asyncio
from enterprise.modules.enterprise_validation.validation_engine import run_full_validation

async def main():
    r = await run_full_validation()
    print(json.dumps({...}))

asyncio.run(main())
```

Called from server.py as:
```python
subprocess.run([sys.executable, VALIDATION_SCRIPT], capture_output=True, 
               text=True, timeout=30, cwd="/home/hunter/Desktop/Enterprise Builder")
```

## Common Failures

| Symptom | Cause | Fix |
|---------|-------|-----|
| `ModuleNotFoundError: No module named 'enterprise.modules'` | Missing `enterprise/modules/__init__.py` | `touch enterprise/modules/__init__.py` |
| `asyncio.run() cannot be called from a running event loop` | `asyncio.run()` in handler | Use subprocess, or make everything async/await |
| `RuntimeWarning: coroutine was never awaited` | Called async function without await | Use `await` or subprocess |
| `TypeError: cannot use 'tuple' as a dict key` | Jinja2Templates bug | Use `jinja2.Environment` directly |
| Routes 200 but score shows "Offline" | Import path issues in uvicorn context | Switch to subprocess pattern |
| Dashboard shows old routes (openapi.json, docs, agents) | Old server.py bytecode cached | Delete `__pycache__/`, verify file contents |
| Copied dashboard files went to nested `dashboard/dashboard/` | `cp -r src dst` when dst exists | `cp src/server.py dst/server.py` (file-level, not dir-level) |

## Testing

Use `starlette.testclient.TestClient`:
```python
from starlette.testclient import TestClient
client = TestClient(app)
client.get("/api/score")  # JSON with final_score
client.get("/api/swarm")  # signal_dbm, concurrency, turbocharger
client.get("/api/modules")  # dict of module scores
```

Tests must tolerate offline validation engine (score_final = "—") since TestClient may not have the right import path.

## Startup

```bash
cd "/home/hunter/Desktop/Enterprise Builder"
python3 enterprise/dashboard/server.py
# → http://0.0.0.0:8421
# → "DASHBOARD: http://0.0.0.0:8421  |  157.0 Singularity"
```

## Port Conflict

```bash
fuser -k 8421/tcp
```
