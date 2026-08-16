# Server Architecture Reference

## Component Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                        CreedServer Instance                         │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌──────────────┐    ┌──────────────┐    ┌────────────────────┐   │
│  │ WebSocket    │    │ HTTP API     │    │ Background Loops   │   │
│  │ Handler      │    │ Routes       │    │                    │   │
│  │              │    │              │    │  • heartbeat_loop  │   │
│  │ /ws          │    │ /api/tasks   │    │  • timeout_loop    │   │
│  │              │    │ /api/clients │    │  • status_broadcast│   │
│  │ • HELLO/AUTH │    │ /api/artifacts│   │                    │   │
│  │ • TASK_*     │    │ /health      │    │                    │   │
│  │ • ARTIFACT_* │    │              │    │                    │   │
│  │ • HEARTBEAT  │    │              │    │                    │   │
│  │ • DASHBOARD_ │    │              │    │                    │   │
│  └──────┬───────┘    └──────┬───────┘    └────────┬───────────┘   │
│         │                   │                     │               │
│         └───────────────────┼─────────────────────┘               │
│                             ▼                                     │
│                    ┌──────────────────┐                           │
│                    │ Shared State     │                           │
│                    │                  │                           │
│                    │ clients: Dict    │                           │
│                    │ task_queue: Deque│                           │
│                    │ active_tasks     │                           │
│                    │ completed_tasks  │                           │
│                    │ artifacts        │                           │
│                    └──────────────────┘                           │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

## Data Structures

### ConnectedClient
```python
@dataclass
class ConnectedClient:
    client_id: str                    # 8-char UUID prefix
    name: str                         # Human-readable
    ws: WebSocketResponse             # Active connection
    capabilities: ClientCapabilities  # Hardware + providers
    auth_providers: Dict[str, str]    # provider -> api_key
    connected_at: str                 # ISO timestamp
    last_heartbeat: float             # time.time()
    status: str                       # "idle" | "busy" | "offline"
    current_task_id: Optional[str]
    tasks_completed: int
    tasks_failed: int
```

### PendingTask
```python
@dataclass
class PendingTask:
    spec: TaskSpec
    created_at: float
    claimed_by: Optional[str]         # client_id
    assigned_at: Optional[float]
    started_at: Optional[float]
```

## Core Algorithms

### Task Assignment (in `_try_assign_tasks`)
```python
# 1. Find idle authenticated clients
idle_clients = [c for c in clients.values() 
                if c.status == "idle" and c.auth_providers]

# 2. For each queued task, find first eligible client
#    (greedy: first-come task gets first eligible client)
while task_queue:
    task = task_queue.popleft()
    eligible = find_eligible_client(task, idle_clients)
    if eligible:
        assign_task_to_client(task, eligible)
        idle_clients.remove(eligible)
    else:
        remaining.append(task)
```

### Client Timeout Handling (in `_timeout_loop`)
```python
# Every 10s:
now = time.time()
timed_out = [cid for cid, c in clients.items() 
             if now - c.last_heartbeat > 60]

for cid in timed_out:
    # Re-queue their active task (if any)
    if c.current_task_id in active_tasks:
        task = active_tasks.pop(c.current_task_id)
        task.claimed_by = None
        task.assigned_at = None
        task.started_at = None
        task_queue.appendleft(task)
    unregister_client(cid, "heartbeat timeout")
```

## Artifact Storage

```
~/.creed/artifacts/
└── {task_id}/
    ├── file1.py
    ├── subdir/
    │   └── file2.md
    └── file3.json
```

- Stored via `aiofiles` async write
- Verified with SHA256 hash
- Served via HTTP at `/api/artifacts/{task_id}/{path}`

## HTTP API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /health | Liveness probe |
| POST | /api/tasks | Submit new task |
| GET | /api/tasks | List all tasks (queued/active/completed) |
| GET | /api/tasks/{id} | Get task status/result |
| GET | /api/clients | List connected clients |
| GET | /api/artifacts/{task_id} | List artifacts for task |
| GET | /api/artifacts/{task_id}/{path} | Download artifact |

## Security Considerations

1. **API keys never logged** — Only provider names in logs
2. **Keys only in memory** — Never written to disk by server
3. **Keys injected per-task** — Passed via env to client subprocess only
4. **No auth on server endpoints** — Intended for trusted LAN; add reverse proxy for public exposure