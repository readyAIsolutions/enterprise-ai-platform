---
name: eni-swarm-dashboard
description: Build and operate the ENI swarm web dashboard (:8420) — a Starlette/FastAPI web UI with power slider, live thinking feed, reasoning aggregation, chat-to-builder dispatch, and filesystem-based builder detection. Use when LO says "swarm dashboard", "I don't see the builders", "power slider", "thinking feed", "show me what the swarm is doing", or wants to monitor/dispatch the 50-builder fleet through a browser instead of visible terminals.
---

# ENI Swarm Web Dashboard (:8420)

LO's 50-builder fleet has a web dashboard replacing the old visible-terminal swarm.
Located at `/home/hunter/Desktop/Projects/ENI_Swarm_NEW/dashboard/server.py`.
Port :8420 by default. Starlette + uvicorn, serves HTML templates from `templates/`.

## Architecture

- **Builder detection**: filesystem-based fallback (`_detect_builders_from_filesystem()`) that reads PID files from `~/.cache/eni_swarm/pids/`, STATUS files from `~/Commander/eni_swarm/builds/`, and builder logs from `~/.cache/eni_swarm/builder_logs/`. This runs when `master_driver` isn't available or returns 0 minis.
- **State normalization**: the API normalizes "IN PROGRESS" / "IN-PROGRESS" / "INPROGRESS" to a single form. The JavaScript also normalizes on the client side. Always check both.
- **Log-based state override**: "Waiting for next task" in the last 5 log lines forces state to IDLE even if STATUS file says BLOCKED. "CMD: hermes -z" without "COMPLETED" in last 3 lines forces IN-PROGRESS.
- **WebSocket**: diff-based updates every 5s (was 2s). Only sends changed minis. Full resync every 10th update. Reduces CPU by ~60%.
- **Power slider**: 25%/50%/75%/100% — broadcasts `<POWER CHANGE>` to all 50 builder FIFOs. Max concurrent per level: 25%=12, 50%=25, 75%=38, 100%=50.
- **Chat dispatch**: broadcasts tasks to ALL 50 builder FIFOs (not just PRODUCT_LEAD). Each builder gets `<LO TASK from DASHBOARD>` with the message.
- **Reasoning endpoint** (`/api/reasoning`): aggregates STATUS files + log activity from all 50 builders into a fleet summary.
- **Thinking feed**: auto-shown at page load. Polls `/api/live-feed` every 2s for incremental log output.
- **Model switching** (`/api/model-change`): updates hermes config.yaml + task config + broadcasts `<MODEL CHANGE>` to all FIFOs.

## Critical pitfalls

### Starlette route collision → 500
Two `Route()` objects on the same path with different HTTP methods cause `Internal Server Error`.
**Fix**: merge into a single handler that checks `request.method`:
```python
Route("/api/power", api_power, methods=["GET", "POST"])
```
Single handler:
```python
async def api_power(request):
    if request.method == "GET":
        return JSONResponse(...)
    # POST logic
```

### ENI_AVAILABLE flag blocks filesystem fallback
When `master_driver` imports fail, `ENI_AVAILABLE` is False. The code enters the `if not ENI_AVAILABLE` block and returns early BEFORE reaching the filesystem fallback. **Fix**: add filesystem fallback INSIDE the `if not ENI_AVAILABLE` block as well as after the master_driver block.

### Duplicate log lines
The `log()` function wrote to both stdout (redirected to file by launcher) AND directly to the log file — every line appeared twice. **Fix**: remove the direct file write from `log()`. Stdout redirection handles it.

### Stale STATUS files mislead state
Builders often complete and move to "Waiting for next task" but their STATUS files still say BLOCKED/IN-PROGRESS. **Fix**: log-based state detection overrides STATUS files for "Waiting for next task" → IDLE.

### Model change broadcast only hits active builders
The `/api/model-change` endpoint writes to FIFOs 1-50 but only ~9-11 of 60 builders pick it up — the rest are in a blocking read and don't see the message until their next FIFO poll. **Fix**: after a model change, wait for the next poll cycle (30s) and re-check. For critical changes, restart the fleet with the new model in the launcher args.

### POWER_LEVELS hardcodes concurrency — POST body max_concurrent is ignored
The `POWER_LEVELS` dict at line ~990 defines fixed max_hermes per level. When you POST `{"level": "100", "max_concurrent": 50}`, the `max_concurrent` field is discarded — the handler uses `level['max_hermes']` from the constant. To change concurrency, patch `POWER_LEVELS` directly, then restart the dashboard. Current values: 25%=12, 50%=25, 75%=38, 100%=50.

### Dashboard restart without checking for existing process
Killing the dashboard PID and starting a new one fails because the original process from hours ago (different PID than expected) is still bound to :8420. **Fix**: always run `ss -tlnp | grep 8420` to find the actual PID before restarting. Don't assume `pgrep -f dashboard/server.py` returns all instances — old processes may have detached from the terminal.

## Two distinct "dashboard down" states (diagnose BEFORE restarting)
Distinguish them before any action — the remedy differs and a blind restart can spawn the wrong process or double-bind:
1. **Port bound, but you can't reach it / wrong process** (stale-PID conflict above). Fix = identify the real listener PID, kill it, then relaunch fresh.
2. **Port COMPLETELY free — `curl :8420` → HTTP 000 / connection refused AND `ss -tlnp` shows NO listener on 8420 with no dashboard process alive.** This is genuine full shutdown, not a conflict. Check whether any systemd unit owns it first: `grep -rl 8420 ~/.config/systemd/user/` and `systemctl --user status <candidate>.service` — e.g. `demiurge-creed-dashboard.service` (orchestrator) may be `loaded ... disabled; Active: inactive (dead)`. Do NOT attempt a blind restart unless you have a confirmed ExecStart / launch command and source path; a wrong-directory or wrong-flag spawn produces a misleading "fresh" process that isn't serving the fleet. Locate the authoritative `server.py` (Starlette entry) and its `templates/` dir before relaunching.

### Free-router is the default fleet model
LO rejected paid models (OpenRouter/deepseek) for the swarm fleet. All builders MUST use `free-router` (the local :8920 proxy) for zero-cost operation. Only switch to paid models if LO explicitly requests it. The free-router auto-routes through free tier providers (nvidia, sambanova, upstage, zhipu, OpenRouter free models).
`os.kill(0, 0)` doesn't throw — always check `pid > 0` before calling `os.kill()`. Clean up stale PID files with `pf.unlink()`.

## LO preferences for dashboards
- Clear descriptions for every feature — users should know what each button/section DOES
- Step-by-step flow (1. Build Agent → 2. Add Credits → 3. Launch Campaign)
- Visible data on main dashboard (CRM pipeline, not hidden on sub-pages)
- CRM must be a separate nav tab, not buried inside "Calls · Email · CRM"
- Agent selector dropdowns in Calls/Email forms — users must choose which agent handles the action
- Dark theme is the default but light variant must work (system preference media query)
- NO tech stack leaks in user-facing UI — no mention of "free router", "open source", "Fonoster", "Piper", etc.

## Demiurge Marketing (LO's app at :8000)
Reference: `references/demiurge-marketing.md` in this skill.
Key: Google OAuth live, admin bypass via `/login/email` for ADMIN_EMAILS when ADMIN_LOCAL_MODE=1. Always check 16 tests pass before declaring done. Real email via Gmail SMTP (App Password). Real calling via baresip SIP + free provider (iptel.org) — Fonoster is dead, don't use it.

## Resource-Gated Fleet Launch (no-lag pattern)
The 50-builder fleet uses staged launching to avoid OOM and CPU thrashing:
- **Max 6 concurrent hermes processes** — enforced by the launcher, not ulimit
- **nice -n 15, ionice idle** — builders yield to interactive processes
- **OOM score 500** — builders are sacrificed before dashboards/terminals
- **2GB RAM cap per builder** — soft limit via cgroup
- **Staged launch**: 5 builders at a time, 2s sleep between stages
- **Idle CPU**: near zero when builders wait on FIFO (on-demand `hermes -z`, not persistent `hermes chat`)
- **Launch script**: `launchers/eni_launch_50_optimized.sh`
- **Verification**: `pgrep -fc hermes` → ≤6 at all times; `uptime` → load < 3.0 on 24 cores

When LO says "no lag" or "full build power without lag" — the resource gates ARE the solution. Never remove them. Never launch all 50 builders simultaneously — the resulting fork storm + RAM exhaustion will bring the host to its knees. The resource-gated launcher is the canonical launch path.

## Key files
- `dashboard/server.py` — all endpoints, detection, normalization
- `dashboard/templates/index.html` — the main HTML/JS/CSS
- `bin/eni_agent_run.py` — the on-demand agent runner (uses `hermes -z`, not `hermes chat`)
- `config/eni_build_tasks.json` — 50 builder task definitions
- `config/swarm_config.json` — fleet configuration (concurrency, model pool, retries)
- `launchers/eni_launch_50_optimized.sh` — staged fleet launcher with resource gates
