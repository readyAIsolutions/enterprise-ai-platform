# ENI Swarm Web Dashboard Patterns

## Architecture
- Starlette/Uvicorn on port 8420 at `/home/hunter/Desktop/Projects/ENI_Swarm_NEW/dashboard/server.py`
- HTML template at `dashboard/templates/index.html`
- Builders at `/home/hunter/Desktop/Projects/ENI_Swarm_NEW/bin/eni_agent_run.py`
- Fleet launcher: `launchers/eni_launch_50_optimized.sh`

## Key patterns

### Filesystem fallback for builder detection
When `master_driver` isn't tracking builders (ENI_AVAILABLE=False), detect from:
- PID files: `/home/hunter/.cache/eni_swarm/pids/<NAME>.pid`
- STATUS files: `/home/hunter/Commander/eni_swarm/builds/STATUS_<NAME>.md`
- Builder logs: `/home/hunter/.cache/eni_swarm/builder_logs/<NAME>.log`
- Log-based state override: "Waiting for next task" → IDLE, "CMD: hermes -z" → IN-PROGRESS

### Starlette Route collision (CRITICAL PITFALL)
Two Route objects on the same path with different HTTP methods cause 500 errors.
MUST merge into single handler checking `request.method`:
```python
async def api_power(request):
    if request.method == "GET": return ...
    # POST logic
Route("/api/power", api_power, methods=["GET", "POST"])
```

### State normalization
API normalizes: "IN PROGRESS"/"INPROGRESS" → "IN-PROGRESS", "UNKNOWN"+alive → "IDLE"
JS normalizes: `(state||'').toUpperCase().replace(/[ _-]/g, '-')` then maps to norm states

### Power slider
4 levels matching percentages: 25/50/75/100 → max_hermes 5/12/20/35
Broadcasts `<POWER CHANGE>` to all 50 builder FIFOs

### Chat dispatch
When LO sends a chat message, route to PRODUCT_LEAD AND broadcast directly to ALL 50 builder FIFOs:
```python
for i in range(1, 51):
    fifo = f"/tmp/eni_ctl_BUILDER_{i:02d}"
    msg = f"<LO TASK from DASHBOARD>\nTASK: {message}\n..."
    os.write(fd, msg.encode())
```

### Model change propagation
1. Update hermes config.yaml
2. Update swarm task config (for new builders)
3. Broadcast `<MODEL CHANGE>` to all 50 builder FIFOs
Running builders detect it in their FIFO listener loop and switch models

### Reasoning endpoint
`/api/reasoning` aggregates STATUS files from all 50 builders, extracts next=/blocker=, builds combined summary with active work and blockers

### Arrow key chat history
JS chatHistory array + keydown handler for ArrowUp/ArrowDown on chat input

### Thinking feed auto-visible
Set `display:block` on DOMContentLoaded, poll at 2s interval

## Optimized fleet launcher
Resource-gated launch: max 6 concurrent hermes, nice 15, ionice idle, OOM score 500
Staged: 5 builders per 12s delay
Config at `/home/hunter/Desktop/Projects/ENI_Swarm_NEW/config/swarm_config.json`

## pkill self-kill avoidance
NEVER use `pkill -f 'pattern'` inline in terminal commands — the pattern matches the shell command itself.
Always write kill patterns in a script file.
