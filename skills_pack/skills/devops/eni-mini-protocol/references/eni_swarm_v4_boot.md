# ENI Swarm v4 Python Boot — Canonical Procedure

The new ENI Swarm v4.0 (`~/Desktop/Projects/ENI_Swarm_NEW`) is a Python-native
coordination system replacing the old xfce4-terminal `fleet_deploy_ws.sh` floor. It
launches 27 minis via a single `eni.master_driver` process that manages PTY-bridged
Hermes sessions through named FIFOs — no X11 terminals, no wmctrl, no geometry math.

## Architecture

```
eni.master_driver (main loop, 120s cycle)
  └─ eni_agent_term.py × 27  (PTY bridges, one per mini)
       └─ hermes chat × 27    (one Hermes session per mini)
            └─ STATUS_<NAME>.md written to per-project workdirs
```

The master driver reads `config/eni_build_tasks.json` + `config/eni_herself_tasks.json`,
launches minis via subprocess, monitors their STATUS files, sends contextual guidance
through `/tmp/eni_ctl_<NAME>` FIFOs, and self-heals dead processes.

## Verified Boot Sequence

```bash
cd ~/Desktop/Projects/ENI_Swarm_NEW

# 1. Verify paths resolve correctly
python3 -c "
import sys; sys.path.insert(0, 'lib')
from eni.master_driver import ROOT, CONFIG_DIR, TASKS_BUILD, TASKS_HERSELF
print(f'ROOT: {ROOT}')
print(f'TASKS_BUILD exists: {TASKS_BUILD.exists()}')
print(f'TASKS_HERSELF exists: {TASKS_HERSELF.exists()}')
"

# 2. Create a pre-boot snapshot
python3 -c "
import sys; sys.path.insert(0, 'lib')
from eni.snapshot import SnapshotManager
sid = SnapshotManager().create('pre-boot')
print(f'Snapshot: {sid}')
"

# 3. Start KB daemon (HTTP health on :8765, SQLite DB init)
python3 -c "
import sys, subprocess; sys.path.insert(0, 'lib')
from kb.daemon.eni_kb_daemon import init_databases
init_databases()
subprocess.Popen(
    [sys.executable, '-m', 'kb.daemon.eni_kb_daemon', '--daemon'],
    start_new_session=True,
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
)
print('Daemon launched')
"

# 4. Launch master driver (background, 120s interval)
PYTHONPATH="lib:$PYTHONPATH" python3 -m eni.master_driver --interval 120 \
  2>&1 | tee /tmp/eni_master_boot.log &

# 5. Verify (after ~30s for bridges to start Hermes)
sleep 30
python3 -c "
import json, sys
state = json.loads(open(
    '/home/hunter/.cache/eni_swarm/master_state.json'
).read())
minis = state.get('minis', {})
alive = sum(1 for m in minis.values() if m.get('alive'))
print(f'Minis: {len(minis)} total, {alive} alive')
"

# 6. Monitor with TUI
eni-swarm tui
```

## CRITICAL PITFALL — `Path(__file__).resolve().parents[N]` miscount

Both `lib/eni/master_driver.py` and `lib/swarm/orchestrator.py` compute ROOT via:

```python
ROOT = Path(__file__).resolve().parents[2]  # .../ENI_Swarm_NEW
```

The ORIGINAL code used `parents[3]`, which resolved to `/home/hunter/Desktop/Projects`
(one level too high). This caused "config file not found" at boot — the master loaded
0 minis because it couldn't find `config/eni_build_tasks.json`.

**The file lives at:** `ENI_Swarm_NEW/lib/eni/master_driver.py`
- parents[0] = `lib/eni/`
- parents[1] = `lib/`
- parents[2] = `ENI_Swarm_NEW/`  ← CORRECT
- parents[3] = `Projects/`        ← WRONG (original bug)

**Verify after ANY file move or module restructure:**
```python
python3 -c "
import sys; sys.path.insert(0, 'lib')
from eni.master_driver import ROOT, CONFIG_DIR
assert (CONFIG_DIR / 'eni_build_tasks.json').exists(), 'MISCOUNTED parents[N]'
print(f'OK: {ROOT}')
"
```

This bug also affects `lib/swarm/orchestrator.py` (same pattern). When adding new modules
under `lib/`, always verify that `parents[N]` points to the project root, not above it.

## Diagnostics

| Symptom | Check |
|---------|-------|
| "Loaded 0 minis" | `parents[N]` miscount — verify ROOT |
| All minis "FIFO no reader" | Bridges still starting (2s delay + Hermes init) — wait 30s |
| Mini dead, no restart | Master only heals each cycle (120s default) |
| Daemon health fail | Check `curl http://127.0.0.1:8765/health` |
| Token rate limit spam | Lower `api_max_retries` (see memory: cap at 3-6) |
| Hermes chat crash | Check `pgrep -fc "hermes chat"` — bridges auto-restart |

## Kill / Stop

```bash
# Kill master driver (sends SIGTERM to all minis)
kill $(cat ~/.cache/eni_swarm/master_driver.pid)

# Or pkill (be careful of self-kill — use in a script file)
pkill -f "eni.master_driver"
pkill -f "eni_agent_term.py"
pkill -f "eni_kb_daemon"
```
