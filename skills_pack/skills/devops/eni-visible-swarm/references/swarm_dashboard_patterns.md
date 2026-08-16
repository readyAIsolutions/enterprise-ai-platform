# ENI Swarm Web Dashboard — Optimization Patterns

## Filesystem Fallback for Builder Detection
When `ENI_AVAILABLE=False` (master_driver module not importable), the dashboard
falls back to filesystem detection via `_detect_builders_from_filesystem()`:

```python
def _detect_builders_from_filesystem():
    pid_dir = Path.home() / ".cache" / "eni_swarm" / "pids"
    log_dir = Path.home() / ".cache" / "eni_swarm" / "builder_logs"
    status_dir = Path("/home/hunter/Commander/eni_swarm/builds")
    task_status_dir = Path("/home/hunter/Desktop/Projects/ENI_Swarm_NEW/tasks/status")
```

This MUST trigger before the early return in the `ENI_AVAILABLE=False` block.
Without it, the dashboard shows 0 builders even when 60 are running.

## State Normalization
STATUS files contain inconsistent state labels. Normalize server-side:
- "IN-PROGRESS", "IN PROGRESS", "INPROGRESS" → "IN-PROGRESS"
- "UNKNOWN" + alive=True → "IDLE"
- "BLOCKED" + "Waiting for next task" in log → "IDLE"

Client-side normalization in `updateBuilderGrid()`:
```javascript
minis = minis.map(m => {
    const s = (m.state || '').toUpperCase().replace(/[ _-]/g, '-');
    if (s === 'IN-PROGRESS' || s === 'INPROGRESS') m.state_norm = 'IN-PROGRESS';
    else if (s === 'DONE') m.state_norm = 'DONE';
    else if (s === 'BLOCKED') m.state_norm = 'BLOCKED';
    else if (s === 'IDLE' || s === 'READY' || s === 'UNKNOWN') m.state_norm = 'IDLE';
    else m.state_norm = 'IDLE';
});
```

## Log-Based State Detection
STATUS files can be stale. Read builder logs for more accurate state:
- "Waiting for next task" in last 5 lines → state = "IDLE"
- "CMD: hermes -z" without "COMPLETED" in last 3 lines → state = "IN-PROGRESS"

## Power Slider — Route Collision Fix
Starlette doesn't support two Route() objects on the same path with different methods.
Merge GET+POST into a single handler:

```python
async def api_power(request: Request) -> JSONResponse:
    if request.method == "GET":
        # return current level
    # POST — set power level
    body = await request.json()
    # ...
```

## Power Levels
```
"25":  max_hermes=5,  nice=19 — 5 concurrent, light load
"50":  max_hermes=12, nice=15 — 12 concurrent, moderate
"75":  max_hermes=20, nice=10 — 20 concurrent, heavy throughput
"100": max_hermes=35, nice=5  — 35 concurrent, full fleet power
```

## Key Pittfalls
1. **KeyError on POWER_LEVELS**: If keys change (e.g. "eco"→"25"), both `_current_power`
   default AND the fallback `POWER_LEVELS.get(_current_power, POWER_LEVELS["75"])`
   must be updated or every `/api/power` call crashes.
2. **Duplicate log lines**: `log()` writes to stdout AND file, but launcher redirects
   stdout to same file via `>>`. Fix: remove direct file write from log(), rely on
   stdout redirect.
3. **ENI_AVAILABLE must trigger filesystem fallback in BOTH paths**: The early return
   when `ENI_AVAILABLE=False` AND the post-master_driver block after the try/except.
4. **Thinking feed must be auto-visible**: `document.getElementById('thinking-feed').style.display = 'block'`
   on DOMContentLoaded. Poll every 2 seconds, not 3.
