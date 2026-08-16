# Dashboard Power Slider & Reasoning System

## Power Slider (Percentage-Based)

Uses a single merged route handler to avoid Starlette route collision:

```python
POWER_LEVELS = {
    "25":  {"max_hermes": 5,  "nice": 19, "label": "25%"},
    "50":  {"max_hermes": 12, "nice": 15, "label": "50%"},
    "75":  {"max_hermes": 20, "nice": 10, "label": "75%"},
    "100": {"max_hermes": 35, "nice": 5,  "label": "100%"},
}

# SINGLE handler for both GET and POST
async def api_power(request):
    if request.method == "GET":
        return JSONResponse({...})
    # POST: broadcast power change to all builder FIFOs
    for i in range(1, 51):
        write_to_fifo(f"/tmp/eni_ctl_BUILDER_{i:02d}", power_msg)

# Route: methods=["GET", "POST"] — NOT two separate Route objects
Route("/api/power", api_power, methods=["GET", "POST"])
```

**Critical pitfall**: Two route objects on the same path (GET + POST) cause 500 errors. Merge into one handler.

## Swarm Reasoning Endpoint (`/api/reasoning`)

Aggregates reasoning from ALL 50 builders by reading STATUS files + log files:

```python
# Reads STATUS_BUILDER_XX.md for state, next=, blocker=
# Reads builder_logs for last_action (completed/executing/waiting)
# Builds combined summary: "Fleet: 12 reporting | 8 in-progress | 39 idle | 1 blocked"
# Returns per-builder insights with state, next, blocker, last_action
```

## Chat Broadcast Pattern

When a chat message is sent, it broadcasts to TWO targets simultaneously:

1. **PRODUCT_LEAD** — coordinator gets the message for analysis/planning
2. **ALL 50 builders** — each builder receives the task directly via FIFO

Earlier versions only sent to PRODUCT_LEAD, which couldn't forward (single-shot `hermes -z` can't dispatch to other FIFOs). Now every builder starts working independently.

## Model Change Broadcasting

`/api/model-change` updates three layers:
1. Hermes `config.yaml` (persistent default)
2. Swarm task config `eni_build_tasks.json` (for new builders)
3. All 50 builder FIFOs + HEARTBEAT + PRODUCT_LEAD

Builders detect `<MODEL CHANGE>` in their FIFO listener loop and update `active_model` dict without triggering execution. Next `hermes -z` call uses the new model.

## Dashboard Filesystem Fallback

When `ENI_AVAILABLE` is False (master_driver imports fail) or master returns 0 minis, the dashboard MUST fall back to filesystem detection:

```python
_detect_builders_from_filesystem()
# Discovers builders from:
# - ~/.cache/eni_swarm/pids/*.pid
# - ~/Commander/eni_swarm/builds/STATUS_BUILDER_*.md
# - ~/Desktop/Projects/ENI_Swarm_NEW/tasks/status/STATUS_BUILDER_*.md
# - ~/.cache/eni_swarm/builder_logs/*.log
```

Must exist in BOTH the `ENI_AVAILABLE=False` path AND the `total_minis==0` path.

## State Normalization

Builders report inconsistent state strings. Fix at TWO levels:

**Server-side** (`_detect_builders_from_filesystem()`):
```python
if state in ("IN PROGRESS", "INPROGRESS"): state = "IN-PROGRESS"
elif state == "UNKNOWN" and alive: state = "IDLE"
```

**Client-side** (`updateBuilderGrid()` in index.html):
```javascript
const s = (m.state || '').toUpperCase().replace(/[ _-]/g, '-');
if (s === 'IN-PROGRESS' || s === 'INPROGRESS') m.state_norm = 'IN-PROGRESS';
// ... normalize all variants
```

## Log-Based State Override

STATUS files go stale while logs show correct state. Override from logs:
```python
# If "Waiting for next task" in last 5 log lines → IDLE (even if STATUS says BLOCKED)
# If "CMD: hermes -z" without "COMPLETED" in last 3 lines → IN-PROGRESS
```

This catches the common case where a builder was BLOCKED, ran `hermes -z` successfully, and is now waiting — but the STATUS file still shows the old BLOCKED state.

## Thinking Feed Auto-Visible

The thinking feed in the dashboard should be auto-expanded on page load:
```javascript
setInterval(fetchThinkingFeed, 2000);  // 2-second poll
document.addEventListener('DOMContentLoaded', function() {
    setTimeout(function() {
        document.getElementById('thinking-feed').style.display = 'block';
    }, 500);
});
```
