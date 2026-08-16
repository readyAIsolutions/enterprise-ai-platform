# ENI Swarm v4 Boot — Python-Native Swarm (ENI_Swarm_NEW)

The v4 swarm (`~/Desktop/Projects/ENI_Swarm_NEW`) uses a Python master driver
loop + per-mini PTY bridges instead of xfce4-terminal windows.

## Quick Boot

```bash
# 1. Ensure builds directory exists
mkdir -p ~/Commander/eni_swarm/builds

# 2. Start KB daemon (optional — for MCP/LSP services)
cd ~/Desktop/Projects/ENI_Swarm_NEW
PYTHONPATH="lib:$PYTHONPATH" python3 -m kb.daemon.eni_kb_daemon --daemon &

# 3. Start dashboard on :8420
PYTHONPATH="lib:$PYTHONPATH" python3 -c "
import sys; sys.path.insert(0,'lib')
from dashboard.server import app
import uvicorn
uvicorn.run(app, host='0.0.0.0', port=8420, log_level='warning')
" &

# 4. Launch master driver (N builders from config)
PYTHONPATH="lib:$PYTHONPATH" python3 -m eni.master_driver --interval 120
```

## Architecture

```
Master Driver (master_driver.py)
  ├── Reads config/eni_build_tasks.json (builder roster)
  ├── Spawns eni_agent_term.py per builder (PTY bridge)
  │   └── Launches hermes chat in PTY
  │   └── Reads from /tmp/eni_ctl_<NAME> (FIFO)
  └── Writes MASTER_STATUS.md every cycle

FIFO Protocol:
  /tmp/eni_ctl_<NAME> — master writes, builder reads
  Non-blocking opens (O_WRONLY | O_NONBLOCK)
  Messages forwarded from FIFO into Hermes PTY as if typed

Dashboard (dashboard/server.py, :8420)
  ├── / — HTML with builder grid + swarm chat
  ├── /api/status — JSON swarm state
  ├── /api/chat — POST to route via PRODUCT_LEAD FIFO
  ├── /api/broadcast — POST to all builders
  ├── /api/assign-idle — POST to idle builders
  └── /ws — WebSocket live streaming
```

## Config: Versatile Builders

LO wants generic builders, not project-locked. Use `BUILDER_01..BUILDER_50`:

```json
{
  "name": "BUILDER_01",
  "title": "Versatile Builder 01",
  "workdir": "/home/hunter/Commander/eni_swarm/builds",
  "model": "deepseek/deepseek-v4-pro",
  "provider": "openrouter",
  "task": "Handle ANY task LO assigns. Monitor /tmp/eni_ctl_BUILDER_01. Write STATUS_BUILDER_01.md. Be autonomous.",
  "status_file": "STATUS_BUILDER_01.md"
}
```

## Safe Kill

Shell-based `pkill -f` will kill your own shell — use Python PID targeting:

```python
import os, signal
for d in os.listdir('/proc'):
    if not d.isdigit(): continue
    try:
        cmd = open(f'/proc/{d}/cmdline','rb').read().decode(errors='replace')
        if 'eni_agent_term' in cmd or 'master_driver' in cmd:
            os.kill(int(d), signal.SIGKILL)
    except: pass
```

## Pitfalls

- **Absent FIFO = no work queued (scheduling/cron semantics)**: A poll for
  `/tmp/eni_ctl_BUILDER_N` that comes back "does not exist" means the master
  never assigned a task to that builder — it is NOT an error to fix and NOT a
  job to invent. The master driver only creates FIFOs when it spawns/assigns a
  builder. If a crate/cron agent fires for `eni_ctl_BUILDER_N` and the file is
  missing (only BUILDER_50 + DEMIURGE* exist, or none), record status as
  `IDLE / blocker=none / next=await LO's directive via FIFO creation` and
  return silent/no-op. Only act when the FIFO actually exists AND has content.
  Do not fabricate a task from the builder's own rote `task:` description when
  no directive was written. Re-verify empirically (e.g. `ls /tmp/eni_ctl_*`)
  rather than trusting a status file alone.

- **`parents[N]` bug**: `ROOT = Path(__file__).resolve().parents[3]` was one
  level too high when the file is at `lib/eni/master_driver.py`. Must be
  `parents[2]`. Symptom: config files not found. Same bug in orchestrator.py.
- **FIFO "no reader"**: Normal on first cycle — bridges take 2-3s to open
  their FIFOs after launch. Wait for next cycle.
- **Hermes crash**: Bridges restart Hermes automatically on exit (up to 1000
  restarts). If a mini stays dead, Hermes itself may be failing to start.
- **Swap saturation**: Box has 8GB swap, usually full. Not a blocker —
  `mem_sentinel` script caps memory pressure.
- **Never pkill from interactive shell**: `pkill -f 'master_driver'` kills the
  shell running the command. Use `/proc` scanning in Python.

## TUI Dashboard

```bash
eni-swarm tui  # Requires: pip install rich
```

Shows live table of all builders with state/age/model/PID, system health
panel, coordination log feed, refreshes every 2s.

## Verification

- Dashboard health: `curl http://localhost:8420/api/status`
- Builder count: `pgrep -cf eni_agent_term`
- Hermes count: `pgrep -cf 'hermes chat'`
- MASTER_STATUS: `cat tasks/status/MASTER_STATUS.md`
- State file: `cat ~/.cache/eni_swarm/master_state.json`
