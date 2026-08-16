---
name: eni-swarm-master-driver
description: ENI Swarm Master Driver v5.0 — On-Demand Coordination CLI and Python API
category: eni-swarm
version: 5.0.0
tags: [eni, swarm, master-driver, coordination, hermes, cli]
---

# ENI Swarm Master Driver Skill

Provides Hermes integration for the ENI Swarm Master Driver — the on-demand coordination engine that manages 50+ builder minis via `hermes run` subprocesses.

## References

- `references/builder-provisioning-diagnostics.md` — verify a builder slot is actually
  provisioned before processing a `eni_ctl_BUILDER_<N>` dispatch (FIFO = named pipe;
  check watcher process + STATUS file + task roster; distinguish active vs stale floor state).

## Architecture

The Master Driver is a **single coordination process** that:
1. Reads task rosters from `config/eni_build_tasks.json` and `config/eni_herself_tasks.json`
2. Tracks 60 logical builder slots (50 BUILDERS + HEARTBEAT + PRODUCT_LEAD + 8 ENI_SELF)
3. Spawns `hermes run --yolo` ON-DEMAND — no persistent agent processes
4. Limits concurrency (default 6 workers) via `ThreadPoolExecutor`
5. Reads STATUS files, routes replies via FIFO (`/tmp/eni_ctl_<name>`)
6. Writes `MASTER_STATUS.md` + builder logs for dashboard
7. Self-heals: detects stalled minis, respawns on crash
8. Watches `~/.hermes/config.yaml` for model/provider changes at runtime

**Key difference from v4**: Minis are NOT persistent `hermes chat` processes. They are logical slots. When work is assigned, the master spawns `hermes run` for that mini, waits for completion, then the mini goes idle. Zero CPU when nothing is building.

## CLI Usage

```bash
# Start swarm for a project
eni-swarm start --project DEMIURGE --workers 6

# Stop all workers
eni-swarm stop

# Show full status
eni-swarm status

# Real-time heartbeat monitor
eni-swarm heartbeat

# Launch visible terminals
eni-swarm launch

# Config management
eni-swarm config show
eni-swarm config edit

# Task roster management
eni-swarm task list
eni-swarm task add --name TASK_NAME --title "Title" --workdir ~/path --model free-router --task "prompt"

# View logs
eni-swarm logs --follow
eni-swarm logs --mini BUILDER_01

# Web dashboard
eni-swarm dashboard

# KB daemon
eni-swarm daemon start|stop|restart|status

# Peer sync
eni-swarm sync once|daemon|peers|status

# Compression pipeline
eni-swarm compress <FILE>

# Glyph management
eni-swarm glyph list|allocate|expand|compress|stats|init

# Compression evolution
eni-swarm evolve --generations 50

# Skill forge
eni-swarm skill-forge --workers 4

# TUI dashboard
eni-swarm tui

# Model auto-fallback
eni-swarm model list|resolve|fail|success|add|reset

# Snapshots
eni-swarm snapshot create|list|restore|delete|prune|auto

# Cross-project patterns + token economics
eni-swarm discover pattern|token list|stats|summary|per-mini|reset|add
```

## Python API

```python
from eni.master_driver import main_loop, load_tasks, MiniSlot, MasterState, execute_mini_task, craft_reply

# Load all tasks
tasks = load_tasks()  # Returns List[MiniSlot]

# Run main coordination loop (blocking)
main_loop(interval=30, max_workers=6)

# Execute a single mini task programmatically
mini = MiniSlot(
    name="BUILDER_01",
    title="ENI Builder 01",
    workdir="/home/hunter/Desktop/Projects/ENI_Swarm_NEW",
    model="free-router",
    provider="free-router",
    task="Build something amazing..."
)
success = execute_mini_task(mini, "Build the thing")

# Read swarm state
state = MasterState.load()
print(f"Cycle: {state.cycle}, Minis: {len(state.minis)}")

# Craft a reply for a mini
reply = craft_reply(mini, status_text, parsed_state)
```

## Configuration Files

- `config/eni_build_tasks.json` — 50 builder tasks with full ENI persona prompts (3.7MB)
- `config/eni_herself_tasks.json` — 8 self-builder tasks for swarm maintenance
- `config/swarm_config.json` — Global swarm configuration (concurrency, models, paths, rate limits)
- `references/wifi-friendly-swarm-config.md` — WiFi-friendly concurrency settings for MT7921e/Filogic 330 hardware (prevents WiFi drops under load)

## Key Data Classes

```python
@dataclass
class MiniSlot:
    name: str                    # e.g., "BUILDER_01"
    title: str                   # e.g., "ENI Builder 01"
    workdir: str                 # Working directory
    model: str                   # Model ID (e.g., "free-router")
    provider: str                # Provider (e.g., "free-router")
    task: str                    # Full prompt text
    status_file: str             # STATUS_BUILDER_01.md
    last_mtime: float            # Last status file mtime
    cycles_since_reply: int      # Cycles without status update
    pending_task: Optional[str]  # Task injected via FIFO
    active: bool                 # Currently executing hermes run
    task_count: int              # Completed tasks

@dataclass
class MasterState:
    minis: Dict[str, dict]       # Per-mini persisted state
    cycle: int                   # Current coordination cycle
    updated: str                 # ISO timestamp
    model: str                   # Current model
    provider: str                # Current provider
```

## Live Context Injection

Each mini receives project-specific context via `LIVE_CONTEXT` dict:
- `DEMIURGE_OANDA` — OANDA credentials location
- `DEMIURGE_MTF` — Multi-timeframe structure rules
- `DEMIURGE_NEWS` — News source quality warning
- `DEMIURGE_FEATURES` — Feature override flags
- `DEMIURGE_GATE` — Gate threshold guidance
- `DEMIURGE_AUTOML` — Auto-learn directive
- `DEMIURGE_RISK` — Risk management rules
- `LUMEN` — Steam-store polish directive
- `DEMIURGE-3D` — 3D app advancement

## Status Protocol

Every builder writes `STATUS_<name>.md` with:
```
[DONE|IN-PROGRESS|BLOCKED] <one line>
verified=<...>
blocker=<...>
next=<...>
```

Master reads this to coordinate — builders **must** keep it current.

## FIFO Communication

Control FIFOs at `/tmp/eni_ctl_<mini_name>`:
- Master writes new task prompts to mini's FIFO
- Mini reads FIFO for dynamic task injection
- Non-blocking writes, 0.1s select timeout

## Model/Provider Hot-Reload

Background thread watches `~/.hermes/config.yaml` every 5s:
- Parses `model.default` and `model.provider`
- Updates `CURRENT_MODEL` / `CURRENT_PROVIDER` atomically with lock
- All subsequent `hermes run` calls use new model immediately

## Integration Points

- **Dashboard**: Reads `MASTER_STATUS.md` + `master_state.json` + builder logs
- **PromptForge**: `enhance_for_builder(mini_name, task, model)` enhances prompts with web search, KB, YouTube, LSP
- **Discovery**: PatternBroadcaster + TokenTracker for cross-project intelligence
- **Sync**: KB sync daemon for multi-node state synchronization
- **Compression**: Wenyan → PAQ8 → PXPipe → Glyphs pipeline

## Error Handling

- `hermes run` timeout: 600s (configurable)
- Process cleanup on timeout/kill
- Stale PID file detection and cleanup
- Config YAML parse errors ignored gracefully
- FIFO creation with fallback on permission errors

## Pitfalls

- **WiFi saturation on MT7921e/Filogic 330** — Default concurrency (6 workers, 120 API calls/min) overwhelms MediaTek MT7921e firmware when running on WiFi. Causes periodic deauths, firmware resets, and complete WiFi dropout. Fix: apply WiFi-friendly config (see `references/wifi-friendly-swarm-config.md`) AND system-level fixes (lock to 5 GHz BSSID, disable Bluetooth, disable IPv6, disable PCIe ASPM). On wired ethernet or Intel/Realtek WiFi, defaults are fine.

## Testing

```bash
# Run unit tests
python -m pytest tests/unit/test_master_driver.py -v

# Run integration tests
python -m pytest tests/integration/ -v

# All tests
python -m pytest tests/ -v
```