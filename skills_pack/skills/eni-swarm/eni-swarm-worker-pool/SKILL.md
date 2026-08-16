---
name: eni-swarm-worker-pool
description: ENI Swarm Worker Pool — Concurrent Worker Process Manager with Auto-Scaling, Work Stealing, Death Detection
category: eni-swarm
version: 1.0.0
tags: [eni, swarm, worker-pool, multiprocessing, auto-scaling, work-stealing, concurrent]
---

# ENI Swarm Worker Pool Skill

Provides Hermes integration for the WorkerPool — a multiprocessing-based concurrent worker manager with auto-scaling, work stealing, death detection, and per-worker metrics.

## Architecture

The WorkerPool manages **N concurrent worker processes** (not threads) using `multiprocessing.Process`:
- Each worker pulls tasks from a shared `multiprocessing.Queue`
- Auto-scales between `min_workers` and `max_workers` based on queue depth
- Work stealing is implicit via shared queue (all workers pull from same queue)
- Death detection via heartbeat timeout (30s default)
- Automatic restart with max attempts limit
- Per-worker metrics tracking (tasks completed, errors, uptime, work time)

## CLI Usage

```bash
# Run standalone test
python -m swarm.worker_pool --min-workers 2 --max-workers 4 --tasks 10 --runtime 5
```

## Python API

```python
from swarm.worker_pool import WorkerPool, TaskType, PoolState, WorkerState

# Create pool
pool = WorkerPool(
    min_workers=2,
    max_workers=8,
    task_types=[
        TaskType.GENERIC,
        TaskType.BUILD,
        TaskType.COMPRESS,
        TaskType.VERIFY,
        TaskType.SYNC,
        TaskType.EVOLVE,
        TaskType.EXPORT,
    ],
    scale_up_threshold=5,      # Queue depth to trigger scale-up
    scale_down_threshold=3,    # Idle workers to trigger scale-down
    scale_check_interval=5.0,  # Seconds between scale checks
    heartbeat_timeout=30.0,    # Seconds without heartbeat -> dead
    max_restart_attempts=3,    # Max consecutive restarts per worker
)

# Start pool
pool.start()

# Submit single task
task = {
    "name": "compress_batch_1",
    "type": TaskType.COMPRESS,
    "task": "Compress this data...",
    "workdir": "/home/hunter/project",
}
pool.submit_task(task)

# Submit batch
tasks = [
    {"name": f"build_{i}", "type": TaskType.BUILD, "task": f"Build component {i}", "verify_cmd": "make test", "workdir": "~/project"}
    for i in range(10)
]
count = pool.submit_batch(tasks)
print(f"Queued {count} tasks")

# Check queue depth
depth = pool.queue_depth()

# Get metrics
metrics = pool.get_metrics()
print(f"Workers: {metrics.total_workers} (idle={metrics.idle_workers}, busy={metrics.busy_workers})")
print(f"Completed: {metrics.total_tasks_completed}, Failed: {metrics.total_tasks_failed}")
print(f"Avg task time: {metrics.avg_task_time:.3f}s")
print(f"Scale events: {metrics.scale_events}")
for w in metrics.workers:
    print(f"  Worker {w['worker_id']}: {w['state']} completed={w['tasks_completed']} failed={w['tasks_failed']} pid={w['pid']}")

# Register result callback
def on_result(result):
    print(f"Task {result['task_name']} {'succeeded' if result['success'] else 'failed'} in {result['elapsed']:.2f}s")

pool.on_result(on_result)

# Enable/disable work stealing
pool.enable_stearing(True)

# Stop pool (drain=True waits for queue to empty)
pool.stop(drain=True)
```

## Task Types

```python
class TaskType:
    BUILD = "build"        # Build tasks with optional verify_cmd
    COMPRESS = "compress"  # Compression pipeline tasks
    VERIFY = "verify"      # Verification with verify_cmd
    SYNC = "sync"          # Sync operations
    EVOLVE = "evolve"      # Evolution generations
    EXPORT = "export"      # Export/artifact generation
    GENERIC = "generic"    # Default fallback
```

### BUILD Task
```python
{
    "name": "build_component",
    "type": TaskType.BUILD,
    "task": "Build the component",
    "workdir": "/project",
    "verify_cmd": "make test",  # Optional: runs subprocess for verification
    "timeout": 60,              # Optional: subprocess timeout
}
```

### COMPRESS Task
```python
{
    "name": "compress_data",
    "type": TaskType.COMPRESS,
    "task": "Data to compress",  # Used as payload
    # Or uses test data if empty
}
```

### VERIFY Task
```python
{
    "name": "verify_build",
    "type": TaskType.VERIFY,
    "verify_cmd": "python -m pytest tests/ -x",
    "workdir": "/project",
    "timeout": 30,
}
```

### GENERIC Task
```python
{
    "name": "custom_task",
    "type": TaskType.GENERIC,
    "task": "Arbitrary task body",
    "import_check": "import mymodule",  # Optional: runs as subprocess
    "timeout": 10,
}
```

## Worker Process Internals

Each worker runs `_worker_main()` in a separate process:
1. Signals alive via `metrics_queue` heartbeat
2. Pulls tasks from `task_queue` with 1s timeout
3. Executes `_execute_task()` based on task type
4. Pushes result to `result_queue`
5. Sends heartbeat after each task
6. Exits on `control_event` (poison pill or drain)

### Heartbeat Message
```python
{
    "type": "heartbeat",
    "worker_id": 1,
    "pid": 12345,
    "state": "idle" | "busy",
    "task": "task_name",  # when busy
    "timestamp": 1234567890.123,
    "completed": 5,       # on exit
    "failed": 1,
    "work_time": 123.45,
}
```

## Auto-Scaling Logic

### Scale Up
Triggered when `queue_depth() > scale_up_threshold` AND `total_workers < max_workers`:
1. Spawns new worker with next task_type in rotation
2. Increments `scale_events`
3. Logs: `Scale UP: spawned worker N (total=X, queue=Y)`

### Scale Down
Triggered when `idle_workers > scale_down_threshold` AND `total_workers > min_workers`:
1. Kills most recently idle worker (LIFO)
2. Increments `scale_events`
3. Logs: `Scale DOWN: killed worker N (total=X, idle=Y)`

## Death Detection & Restart

Monitor loop (every `scale_check_interval`):
1. Checks `process.is_alive()` for each worker
2. If dead: `_restart_worker()` if attempts < `max_restart_attempts`
3. Checks heartbeat timeout: if `now - last_heartbeat > heartbeat_timeout`, kill + restart

### Restart Logic
```python
def _restart_worker(self, worker_id):
    attempts = self._restart_attempts.get(worker_id, 0)
    if attempts >= self.max_restart_attempts:
        return False
    self._restart_attempts[worker_id] = attempts + 1
    old_type = old_handle.task_type
    self._kill_worker(worker_id)
    new_handle = self._spawn_worker(worker_id, old_type)
    new_handle.metrics.restarts = attempts + 1
    return True
```

## Metrics

```python
@dataclass
class WorkerMetrics:
    worker_id: int
    tasks_completed: int
    tasks_failed: int
    total_work_time: float
    last_task_start: float
    last_task_end: float
    started_at: float
    restarts: int
    state: WorkerState
    current_task: Optional[str]
    pid: int

@dataclass
class PoolMetrics:
    total_workers: int
    idle_workers: int
    busy_workers: int
    dead_workers: int
    total_tasks_completed: int
    total_tasks_failed: int
    queued_tasks: int
    avg_task_time: float
    uptime_seconds: float
    scale_events: int
    workers: List[Dict]  # WorkerMetrics.to_dict()
```

## Integration Points

- **SwarmOrchestrator**: Feeds ready tasks via `worker_pool.submit_task()`
- **Master Driver**: Alternative to on-demand `hermes run` model
- **Monitoring**: `get_metrics()` for dashboard/telemetry
- **Callbacks**: `on_result(callback)` for real-time result processing

## Testing

```bash
# Standalone test
python -m swarm.worker_pool --min-workers 2 --max-workers 4 --tasks 20 --runtime 10

# Unit tests (if any)
python -m pytest tests/ -k "worker_pool" -v
```