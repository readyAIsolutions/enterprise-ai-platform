---
name: distributed-multiplayer-build-system
description: Build and operate a distributed multi-user AI build coordination system where each user brings their own hardware + API keys, connecting to a central server for task distribution, result aggregation, and real-time dashboard visualization.
triggers:
  - User wants to scale build throughput horizontally by adding more machines
  - Need to coordinate multiple users each with their own API credentials
  - Building a "swarm" where participants are independent agents, not persistent processes
  - Requirement for real-time visibility into distributed build status
---

# Distributed Multiplayer Build System

## Architecture Overview

```
┌─────────────────┐     WebSocket      ┌──────────────────┐     HTTP API      ┌─────────────────┐
│   Builder A     │ ◀────────────────▶ │  Coordination    │ ◀───────────────▶ │   Dashboard     │
│  (GPU, keys)    │   Protocol v1      │    Server        │   Proxy + WS      │   (Web UI)      │
└─────────────────┘                    │  :8765           │                   │  :8766          │
                                       └────────┬─────────┘                   └─────────────────┘
                                                │
                    ┌───────────────────────────┼───────────────────────────┐
                    ▼                           ▼                           ▼
             ┌─────────────┐            ┌─────────────┐            ┌─────────────┐
             │  Builder B  │            │  Builder C  │            │  Builder N  │
             │ (CPU, keys) │            │ (GPU, keys) │            │  (keys)     │
             └─────────────┘            └─────────────┘            └─────────────┘
```

**Core principle**: Each builder brings their own hardware + API keys. Server only coordinates — zero central compute cost. Linear throughput scaling: N builders = N× tokens/day.

## Protocol Design (creed_protocol.py)

### Message Types
- `HELLO` / `WELCOME` — Client announces capabilities, server assigns ID
- `AUTH` — Client sends API keys (provider → key mapping)
- `TASK_AVAILABLE` / `TASK_CLAIM` / `TASK_ASSIGNED` — Pull-based assignment with eligibility matching
- `TASK_PROGRESS` / `TASK_COMPLETE` / `TASK_FAILED` — Execution lifecycle
- `ARTIFACT_UPLOAD` — Base64-encoded file uploads with SHA256
- `FILE_SYNC_PUSH` / `FILE_SYNC_PULL` / `FILE_SYNC_LIST` / `FILE_SYNC_ACK` — Remote file sync
- `HEARTBEAT` — Bidirectional liveness (15s interval, 60s timeout)
- `DASHBOARD_SUBSCRIBE` / `DASHBOARD_UPDATE` — Real-time UI feed

### Eligibility Matching
Tasks declare `required_providers`, `required_tags`, and optionally `target_client_id`. Server matches against client's `auth_providers`, `capabilities.tags`, and `client_id`:
```python
# Client eligible if:
(not task.target_client_id or client.client_id == task.target_client_id) and \
all(p in client.auth_providers for p in task.required_providers) and \
all(t in client.capabilities.tags for t in task.required_tags)
```
**Explicit targeting**: When `target_client_id` is set, only that specific client is eligible (priority boosted +1000). Use for "build on this specific machine" workflows.

## Server Implementation (creed_server/server.py)

### Key Components
- **Task Queue**: `deque[PendingTask]` — FIFO with priority support
- **Active Tasks**: `dict[task_id, PendingTask]` — In-flight with assignment metadata
- **Client Registry**: `dict[client_id, ConnectedClient]` — Capabilities, auth, status
- **Artifact Store**: `dict[task_id, List[Artifact]]` — Metadata + filesystem persistence

### Critical Pitfalls & Fixes

| Issue | Symptom | Fix |
|-------|---------|-----|
| WS handler returns `None` | `AttributeError: 'NoneType' object has no attribute 'prepare'` | Wrap `ws.prepare()` in try/except, always `return ws` |
| `json_response` fails on dataclass | `TypeError: Object of type ClientInfo is not JSON serializable` | Use `asdict(client.to_info())` for all dataclass returns |
| Proxy session closes between requests | `Session is closed` on `/api/*` calls | Lazy-create session in `proxy_api()`: `if not self.session or self.session.closed: self.session = ClientSession()` |
| CORS errors on catch-all route | `ValueError: <DynamicResource /api/{path}> already has '*' handler` | Add routes BEFORE CORS setup, skip CORS for proxy routes: `if "/api/" not in str(route.resource): cors.add(route)` |

### Background Loops
```python
# Heartbeat: ping all clients every 15s
# Timeout: mark clients dead after 60s silence, re-queue their tasks
# Status broadcast: push full state to dashboards every 5s
```

### File Sync Protocol (Remote Build Workflow)
New in v1.1: Clients can exchange files through the server without direct P2P connections.

**Message Types**:
- `FILE_SYNC_PUSH` — Source → Server → Target: send files to target's `WORKDIR`
- `FILE_SYNC_PULL` — Source → Server → Target: request files from target
- `FILE_SYNC_LIST` — Source → Server → Target: list files on target
- `FILE_SYNC_ACK` — Target → Server → Source: result with file metadata/hash

**HTTP Endpoints** (for CLI):
- `POST /api/files/push` — Push local files to remote client
- `POST /api/files/pull` — Pull files from remote client
- `POST /api/files/list` — List files on remote client

**CLI Usage** (via unified `creed.py`):
```bash
creed push-files --target-client <id> ./src ./include --dest-dir project/
creed pull-files --target-client <id> --patterns "*.so,*.a" --src-dir build/
creed list-files --target-client <id> --dir-path project/
```

**Shared Workdir Helper** (optional): For large repos, auto-mount SSHFS/NFS to same path on all machines:
```bash
creed shared-workdir setup --remote user@build:/shared --local ~/creed_shared
creed shared-workdir mount
```

## Client Implementation (creed_client/client.py)

### Capability Detection
Auto-detects on startup:
- CPU cores (`os.cpu_count()`)
- RAM GB (`psutil.virtual_memory()`)
- GPU: `nvidia-smi` (CUDA) or `rocminfo` (ROCm)
- Local LLMs: `ollama`, `llama.cpp` presence
- Hermes version: `hermes --version`

### API Key Loading Priority
1. Environment variables (`OPENROUTER_API_KEY`, `ZHIPU_API_KEY`, etc.)
2. `~/.hermes/config.yaml` provider `api_key` fields
3. `~/.creed/api_keys.json` (local override)

### Execution Flow
1. Receive `TASK_ASSIGNED` with injected `_client_api_keys` in metadata
2. Build prompt + protocol reminder
3. Spawn `hermes -z` subprocess with keys in env
4. Stream stdout → progress updates every 10 lines
5. On completion: collect artifacts matching `artifacts_expected` patterns
6. Upload artifact metadata + base64 content via `ARTIFACT_UPLOAD`

### File Sync Methods (Client → Client via Server)
Client exposes public methods for remote file operations:
```python
await client.push_files(target_client_id, local_paths, dest_dir="")  # Upload to target
await client.pull_files(target_client_id, file_patterns, src_dir="")  # Download from target
await client.list_files(target_client_id, dir_path="", patterns=["*"])  # List on target
```
Files are base64-encoded with Blake2b hashes for integrity verification. Server forwards via `FILE_SYNC_*` messages — no direct client-to-client connection needed.

## Dashboard Implementation (creed_dashboard/server.py)

### Proxy Pattern
- Single-page app served at `/`
- `/ws` — Dashboard subscribes to server's `DASHBOARD_UPDATE`
- `/api/{path:.*}` — Proxies to coordination server, lazy session creation
- CORS only on non-proxy routes

### UI Tabs
- **Overview** — Cluster stats (idle/busy/queued/active/done/failed)
- **Clients** — Cards per builder: hardware, providers, tags, current task
- **Tasks** — Three columns: Queued / Active (with progress bars) / Completed
- **Artifacts** — Grouped by task, downloadable
- **Submit** — Full task spec form (name, prompt, workdir, model, provider, required_providers, required_tags, timeout, artifact patterns)
- **Activity** — Live log feed

## Launch & Operations

### Single-Machine Dev Stack
```bash
cd ~/Desktop/Projects/Demiurge_Creed
./launch_all.sh  # Starts server → dashboard → local client
```

### Multi-Machine Deployment
```bash
# Server machine (runs server + dashboard)
./launch_server.sh && ./launch_dashboard.sh

# Each builder machine
export CREED_SERVER_URL=ws://server-ip:8765/ws
export OPENROUTER_API_KEY=***
export ZHIPU_API_KEY=***
# ... other keys
cd creed_client && python3 client.py
```

### Task Submission
```bash
# CLI
python3 -m creed_client.submit_task --name my-build --prompt "Build X" --workdir ~/proj --required-providers openrouter

# Or via Dashboard UI at http://server:8766 (Submit tab)

# File Sync (new in v1.1)
creed push-files --target-client <id> ./src ./include --dest-dir project/
creed pull-files --target-client <id> --patterns "*.so,*.a" --src-dir build/
creed list-files --target-client <id> --dir-path project/
creed shared-workdir setup --remote user@build:/shared --local ~/creed_shared
creed shared-workdir mount
```

## Scaling Characteristics

| Builders | OpenRouter Keys | Tier 1 Daily Tokens | Tier 1+2 Daily Tokens |
|----------|-----------------|---------------------|----------------------|
| 1        | 2               | ~4.0B               | ~7B                  |
| 5        | 10              | ~20B                | ~35B                 |
| 10       | 20              | ~40B                | ~70B                 |

Each builder's keys are isolated — no shared credential risk. Server never logs keys.

## Common Pitfalls (v1.1+)

| Issue | Symptom | Fix |
|-------|---------|-----|
| **ENI executor AttributeError** | `ENITaskExecutor` used `active_tasks` but client code expected `running_tasks` | Use `running_tasks` consistently; add `@property active_tasks` for compatibility |
| **ClientProfile missing field** | New `artifact_quality_score` field accessed before initialization | Add `artifact_quality_score: float = 0.0` default in dataclass |
| **Stale bytecode after changes** | Python caches `__pycache__` after ENI bridge edits | Clear `__pycache__` dirs before restart: `find . -name "__pycache__" -exec rm -rf {} +` |
| **Task never picked up** | Target client disconnected before assignment | Server re-queues on heartbeat timeout (60s); client must stay connected |
| **FILE_SYNC_ACK timeout** | Client didn't respond to push/pull/list request | Check target client connected; increase wait timeout; verify WS not blocked |
| `hermes` not found | `HERMES_BIN` wrong or not in PATH | Set `CREED_HERMES_BIN` or ensure `hermes` in PATH |
| API key not working | Key loaded but not passed to subprocess | Check `provider_to_env()` mapping includes provider |
| Artifact upload fails | File too large for WS frame | Increase `max_message_size` or chunk large files |
| Task timeout | Default 600s too short | Set `timeout_seconds` in task spec |
| GPU not detected | `nvidia-smi` not in PATH | Install nvidia-utils or add to PATH |
| Hermes exits immediately | Missing `--yolo` flag or auth | Ensure `--yolo` passed and keys in env |

## References
- `references/protocol.md` — Full message schemas and state machines
- `references/server-architecture.md` — Component diagram and data flows
- `references/client-execution.md` — Hermes subprocess management details
- `references/dashboard-proxy.md` — Proxy pattern and CORS configuration
- `templates/launch_scripts.sh` — Template launch scripts for server/client/dashboard
- `templates/task_spec.json` — Example task submission payloads