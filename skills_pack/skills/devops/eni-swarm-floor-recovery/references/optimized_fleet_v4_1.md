# ENI Swarm v4.1 — Optimized Fleet Architecture

## Overview

50+ builders launched on-demand via `hermes -z` (single-shot), NOT persistent `hermes chat` sessions. 
Zero CPU when idle. Resource-gated, staged launch, OOM-protected.

## Key Files

| File | Purpose |
|------|---------|
| `launchers/eni_launch_50_optimized.sh` | Staged fleet launcher with resource gates |
| `bin/eni_agent_run.py` | Agent runner — monitors FIFO, executes `hermes -z` on-demand |
| `config/eni_build_tasks.json` | 50 builder tasks + HEARTBEAT + PRODUCT_LEAD |
| `config/swarm_config.json` | Power levels, model pool, concurrency settings |
| `dashboard/server.py` | Web dashboard on :8420 |
| `scripts/check_fleet.sh` | Quick fleet health check |

## Fleet Launcher Design

```
Resource gate → Launch 5 builders → Sleep 12s → Repeat (10 stages for 50 builders)
```

Resource gate checks EVERY launch:
- CPU load < 80% (from /proc/loadavg vs nproc)
- Free RAM > 2GB (from /proc/meminfo MemAvailable)
- Concurrent hermes processes < MAX_HERMES (6)

Each builder runs with:
- `nice -n 15 ionice -c 3` (lowest CPU/IO priority)
- OOM score 500 (dies before desktop freeze)
- 2GB RAM cap (via resource.setrlimit)
- HERMES_MAX_RETRIES=3 in env

## Agent Runner Pattern

```python
# Main loop: execute task, listen for more on FIFO
while running:
    run_hermes(task, model, provider)  # single-shot, exits clean
    while running:
        new_task = fifo_listener(fifo)  # non-blocking poll
        if new_task:
            if "MODEL CHANGE" in new_task:
                update active_model  # don't trigger execution
                continue
            task = new_task
            break
```

Single `hermes -z` call per task. Between tasks, the runner sits in a FIFO poll loop consuming zero CPU.

## Duplicate Log Line Fix

The `log()` function must NOT write to the log file directly. The launcher redirects stdout to the log file via `>>`. Double-writing causes every line to appear twice:

```python
def log(name, msg):
    print(f"[{ts}] [{name}] {msg}", flush=True)
    # stdout is redirected to log file by launcher >> redirect
    # Do NOT also open() and write() to the file directly
```

## Known Failure Mode: Large Prompt Parse

Prompts over 60KB with special characters (em-dashes, unicode, backticks) can cause `hermes -z` to parse prompt content as flags → `invalid choice` error. ~2% failure rate on 50 builders. Self-heals on next fleet launcher run (skips already-alive builders, fills gaps).

## Power Levels

| Level | Max Hermes | Nice | Description |
|-------|-----------|------|-------------|
| 25% | 5 | 19 | Light load |
| 50% | 12 | 15 | Moderate |
| 75% | 20 | 10 | Heavy throughput |
| 100% | 35 | 5 | Full fleet power |

Power changes broadcast to all 50 builder FIFOs via `<POWER CHANGE>` message.
