---
name: eni-swarm-orchestrator
description: ENI Swarm Orchestrator v4.0 — Central Coordination Engine with PTY Bridge, Health Monitoring, Round-Robin Load Balancing
category: eni-swarm
version: 4.0.0
tags: [eni, swarm, orchestrator, coordination, pty, health-monitoring, load-balancing]
---

# ENI Swarm Orchestrator Skill

Provides Hermes integration for the SwarmOrchestrator — the central coordination engine that manages mini-ENI agents via PTY bridge (`eni_agent_term.py`), with health monitoring, round-robin model pool load balancing, and dependency resolution.

## Architecture

The SwarmOrchestrator is a **long-running coordination process** that:
1. Loads task configs from `config/eni_build_tasks.json` and `config/eni_herself_tasks.json`
2. Manages a pool of mini-ENI agents launched via PTY bridge
3. Distributes tasks with round-robin load balancing across model pools
4. Tracks task completion, staleness, and zombie detection
5. Provides start/stop/pause/resume for individual minis and groups
6. Integrates with WorkerPool, TaskScheduler, and SwarmMonitor subsystems
7. Monitors health via heartbeat checks (10s interval default)

## CLI Usage

```bash
# Run orchestrator standalone
python -m swarm.orchestrator --interval 30 --config-dir ~/Desktop/Projects/ENI_Swarm_NEW/config

# Single cycle only
python -m swarm.orchestrator --single

# Load tasks only (no launch)
python -m swarm.orchestrator --no-launch
```

## Python API

```python
from swarm.orchestrator import SwarmOrchestrator, MiniState, OrchestratorState, HealthConfig, MiniInfo

# Create orchestrator
orch = SwarmOrchestrator(
    config_dir=Path("/home/hunter/Desktop/Projects/ENI_Swarm_NEW/config"),
    health_config=HealthConfig(
        heartbeat_timeout=120.0,
        zombie_timeout=300.0,
        staleness_timeout=600.0,
        max_restart_attempts=5,
        restart_cooldown=30.0,
        heartbeat_interval=10.0
    )
)

# Load tasks
orch.load_tasks()

# Start all minis
count = orch.start_all()
print(f"Launched {count} minis")

# Run coordination loop
orch.run_loop(interval=30.0)

# Or single cycle
orch.run_loop(interval=30.0, single_cycle=True)

# Stop all
orch.stop_all()

# Group operations
orch.start_group("build")      # Start all build minis
orch.stop_group("herself")     # Stop self-builders
orch.pause_group("build")      # Pause build group
orch.resume_group("build")     # Resume build group

# Individual mini control
orch.launch_mini(mini)         # Launch specific mini
orch.stop_mini("BUILDER_01")   # Graceful stop
orch.pause_mini("BUILDER_01")  # SIGSTOP
orch.resume_mini("BUILDER_01") # SIGCONT
orch.restart_mini("BUILDER_01")# Restart with cooldown

# Round-robin task assignment
assignments = orch.assign_task_round_robin([
    {"name": "task1", "model": "free-router", "task": "Build X", "workdir": "~/project", "priority": 1},
    {"name": "task2", "model": "deepseek/deepseek-chat-v3-0324:free", "task": "Review Y", "workdir": "~/project", "priority": 2},
])

# Dependency resolution
ready = orch.get_ready_tasks()  # Returns list of mini names with satisfied deps

# Status
summary = orch.get_status_summary()
print(f"Total: {summary['total']}, Running: {summary['running']}, Completed: {summary['completed']}")

# Heartbeat from mini
orch.heartbeat("BUILDER_01")  # Call when mini sends status update

# Read mini status
txt, state = orch.read_mini_status("BUILDER_01")
# state = "DONE" | "IN-PROGRESS" | "BLOCKED" | "UNKNOWN"
```

## Key Classes

```python
class MiniState(Enum):
    IDLE = auto()
    STARTING = auto()
    RUNNING = auto()
    PAUSED = auto()
    COMPLETED = auto()
    BLOCKED = auto()
    DEAD = auto()
    ZOMBIE = auto()  # process exists but no heartbeat
    STOPPED = auto()

class OrchestratorState(Enum):
    INIT = auto()
    RUNNING = auto()
    PAUSED = auto()
    SHUTDOWN = auto()

@dataclass
class MiniInfo:
    name: str
    title: str
    workdir: str
    model: str
    provider: str
    task: str
    priority: int
    dependencies: List[str]
    status_file: str
    fifo_path: str
    pid: int
    state: MiniState
    last_heartbeat: float
    tasks_completed: int
    errors: int
    started_at: Optional[float]
    group: str  # "build" or "herself"

@dataclass
class HealthConfig:
    heartbeat_timeout: float = 120.0    # seconds without heartbeat -> suspect
    zombie_timeout: float = 300.0       # seconds without heartbeat -> zombie
    staleness_timeout: float = 600.0    # seconds without progress -> stale
    max_restart_attempts: int = 5
    restart_cooldown: float = 30.0
    heartbeat_interval: float = 10.0
```

## Model Pool Allocator (Round-Robin Load Balancing)

```python
from swarm.orchestrator import ModelPoolAllocator

allocator = ModelPoolAllocator()
allocator.register_model("free-router")
allocator.register_model("deepseek/deepseek-chat-v3-0324:free")

# Check if model can accept task
if allocator.get_next_slot("free-router"):
    allocator.mark_used("free-router")

# Mark model as rate-limited
allocator.mark_ratelimited("free-router", backoff_seconds=60)

# Get usage stats
stats = allocator.get_usage_stats()  # {"free-router": 42, "deepseek-chat": 15}
```

## FIFO Communication

Each mini has a control FIFO at `/tmp/eni_ctl_<name>`:
- Orchestrator writes task prompts to FIFO for assignment
- Mini reads FIFO for dynamic task injection
- Non-blocking writes with `os.O_NONBLOCK`
- Commands: `STOP:`, `PAUSE:`, `RESUME:`, or task prompt

## PTY Bridge (`eni_agent_term.py`)

Minis are launched via PTY bridge:
```python
cmd = [
    sys.executable, str(BRIDGE_SCRIPT),
    f"@{task_file}", mini.workdir,
    "-m", mini.model,
    "--provider", mini.provider,
    "--fifo", mini.fifo_path,
    "--name", mini.name,
]
proc = subprocess.Popen(cmd, start_new_session=True, stdout=DEVNULL, stderr=DEVNULL)
```

The bridge:
- Pre-types the task prompt into the hermes session
- Manages PTY for interactive hermes run
- Handles FIFO communication for control messages
- Reports PID back to orchestrator

## Health Monitoring

Background heartbeat thread (10s default):
1. Checks if process PID is alive (`os.kill(pid, 0)`)
2. Tracks heartbeat staleness:
   - >120s: stalled (warning)
   - >300s: zombie (alert)
   - >600s: stale (auto-restart)
3. Auto-restart with cooldown (30s) and max attempts (5)
4. Records alerts via SwarmMonitor integration

## Dependency Resolution

Tasks can declare dependencies:
```json
{
  "name": "BUILDER_05",
  "dependencies": ["BUILDER_01", "BUILDER_02"]
}
```

`orch.get_ready_tasks()` returns minis whose all dependencies are `COMPLETED`.

## Integration Points

- **WorkerPool**: Submits ready tasks to worker pool for parallel execution
- **TaskScheduler**: Notifies scheduler of ready tasks
- **SwarmMonitor**: Receives status updates and alerts
- **Master Driver**: Alternative coordination engine (v5.0 on-demand model)

## Testing

```bash
# Unit tests
python -m pytest tests/unit/test_master_driver.py -v

# Note: Orchestrator tests require integration with PTY bridge
```