# Creed Multiplayer Protocol Reference

## Message Schema (JSON over binary WebSocket frames)

### HELLO → WELCOME
```json
// Client → Server
{
  "type": "hello",
  "client_name": "demiurge-linux-hunter",
  "capabilities": {
    "max_concurrent_tasks": 1,
    "models": ["free-router", "nvidia/nemotron-3-ultra-550b-a55b:free"],
    "providers": ["openrouter", "zhipu", "sambanova", ...],
    "gpu": true,
    "gpu_name": "NVIDIA GeForce RTX 3060 Ti",
    "cpu_cores": 24,
    "ram_gb": 30.2,
    "python_version": "3.14.4",
    "hermes_version": "Hermes Agent v0.15.2",
    "tags": ["cuda", "api-keys", "ollama", "cpu-24", "gpu"]
  },
  "protocol_version": 1
}

// Server → Client
{
  "type": "welcome",
  "client_id": "3b294282",
  "server_config": {
    "server_version": "1.0",
    "protocol_version": 1,
    "heartbeat_interval": 15,
    "artifact_dir": "/home/user/.creed/artifacts"
  }
}
```

### AUTH → AUTH_OK / AUTH_FAIL
```json
// Client → Server
{
  "type": "auth",
  "providers": {
    "openrouter": "sk-or-v1-...",
    "zhipu": "...",
    "sambanova": "..."
  }
}

// Server → Client
{ "type": "auth_ok" }
// or
{ "type": "auth_fail", "reason": "invalid key format" }
```

### TASK_AVAILABLE
```json
// Server → Client (broadcast to eligible idle clients)
{
  "type": "task_available",
  "task": {
    "task_id": "build-123",
    "name": "trading-bot-backtest",
    "description": "Run walk-forward validation on EURUSD",
    "workdir": "~/Projects/DEMIURGE",
    "prompt": "Build complete walk-forward engine...",
    "model": "free-router",
    "provider": "free-router",
    "required_providers": ["openrouter"],
    "required_tags": ["gpu"],
    "priority": 0,
    "timeout_seconds": 600,
    "artifacts_expected": ["*.py", "*.md", "*.json", "*.log"],
    "metadata": {}
  }
}
```

### TASK_CLAIM → TASK_ASSIGNED / TASK_REJECTED
```json
// Client → Server
{ "type": "task_claim", "task_id": "build-123", "client_id": "3b294282" }

// Server → Client (if eligible)
{
  "type": "task_assigned",
  "task": { ...task spec with _client_api_keys injected... },
  "client_id": "3b294282"
}

// Server → Client (if not eligible or already claimed)
{ "type": "task_rejected", "task_id": "build-123", "reason": "Already claimed" }
```

### TASK_PROGRESS
```json
// Client → Server (periodic during execution)
{
  "type": "task_progress",
  "task_id": "build-123",
  "client_id": "3b294282",
  "progress": 0.45,
  "message": "Running fold 3/12...",
  "timestamp": "2026-07-25T19:45:12.345Z"
}
```

### TASK_COMPLETE
```json
// Client → Server
{
  "type": "task_complete",
  "result": {
    "task_id": "build-123",
    "client_id": "3b294282",
    "success": true,
    "exit_code": 0,
    "stdout": "...full output...",
    "stderr": "",
    "artifacts": [
      {"path": "STATUS_WALKFORWARD.md", "size": 4096, "hash": "a1b2c3d4", "mtime": 1690123456.789}
    ],
    "duration_seconds": 45.2,
    "error": ""
  }
}
```

### TASK_FAILED
```json
// Client → Server
{
  "type": "task_failed",
  "task_id": "build-123",
  "client_id": "3b294282",
  "error": "Hermes exited with code 1: API key exhausted"
}
```

### ARTIFACT_UPLOAD
```json
// Client → Server (after TASK_COMPLETE)
{
  "type": "artifact_upload",
  "task_id": "build-123",
  "client_id": "3b294282",
  "artifacts": [
    {
      "path": "STATUS_WALKFORWARD.md",
      "size": 4096,
      "hash": "a1b2c3d4",
      "mtime": 1690123456.789,
      "content": "base64-encoded-file-content"
    }
  ]
}
```

### FILE_SYNC_PUSH
```json
// Source Client → Server → Target Client
{
  "type": "file_sync_push",
  "source_client_id": "abc12345",
  "target_client_id": "def67890",
  "files": [
    {
      "path": "src/main.cpp",
      "content_b64": "base64-encoded-content",
      "size": 1024,
      "hash": "a1b2c3d4",
      "mtime": 1690123456.789
    }
  ],
  "dest_dir": "project/",
  "timestamp": "2026-07-26T19:45:12.345Z"
}
```

### FILE_SYNC_PULL
```json
// Source Client → Server → Target Client
{
  "type": "file_sync_pull",
  "source_client_id": "abc12345",
  "target_client_id": "def67890",
  "file_patterns": ["*.so", "*.a"],
  "src_dir": "build/",
  "timestamp": "2026-07-26T19:45:12.345Z"
}
```

### FILE_SYNC_LIST
```json
// Source Client → Server → Target Client
{
  "type": "file_sync_list",
  "target_client_id": "def67890",
  "dir_path": "project/",
  "patterns": ["*"],
  "timestamp": "2026-07-26T19:45:12.345Z"
}
```

### FILE_SYNC_ACK
```json
// Target Client → Server → Source Client
{
  "type": "file_sync_ack",
  "success": true,
  "message": "Received 5 files from abc12345",
  "files": [
    {"path": "src/main.cpp", "size": 1024, "hash": "a1b2c3d4"}
  ],
  "error": "",
  "timestamp": "2026-07-26T19:45:12.345Z"
}
```

### HEARTBEAT (bidirectional)
```json
// Both directions every 15s
{
  "type": "heartbeat",
  "client_id": "3b294282",
  "status": "idle",
  "current_task": null,
  "timestamp": "2026-07-25T19:45:12.345Z"
}
```

### DASHBOARD_SUBSCRIBE / DASHBOARD_UPDATE
```json
// Dashboard → Server
{ "type": "dashboard_subscribe" }

// Server → Dashboard (full state on subscribe, then incremental)
{
  "type": "dashboard_update",
  "payload": {
    "clients": [...],
    "active_tasks": [...],
    "queued_tasks": [...],
    "completed_tasks": [...],
    "artifacts": [...],
    "timestamp": "2026-07-25T19:45:12.345Z"
  }
}
```

## Eligibility Matching Algorithm

```python
def is_eligible(client: ConnectedClient, task: TaskSpec) -> bool:
    # Must have all required providers authenticated
    if task.required_providers:
        if not all(p in client.auth_providers for p in task.required_providers):
            return False
    
    # Must have all required capability tags
    if task.required_tags:
        if not all(t in client.capabilities.tags for t in task.required_tags):
            return False
    
    # Provider compatibility: task.provider must be in client.auth_providers
    # Exception: free-router routes through OpenRouter
    if task.provider not in client.auth_providers:
        if "free-router" not in client.auth_providers:
            return False
    
    # Explicit client targeting (v1.1+)
    if task.target_client_id and client.client_id != task.target_client_id:
        return False
    
    return True
```

**Explicit targeting**: When `target_client_id` is set, only that specific client is eligible (priority boosted +1000). Use for "build on this specific machine" workflows.

## State Machines

### Client States
```
DISCONNECTED → CONNECTING → AUTHENTICATED → IDLE ↔ BUSY → AUTHENTICATED
                                      ↑              ↓
                                      └──────────────┘ (task complete/fail)
```

### Task States
```
QUEUED → ASSIGNED → RUNNING → COMPLETED
                ↘ FAILED → (retry once) → QUEUED
```

## Error Handling

- **Client disconnect during task**: Task re-queued with incremented `_retry_count` (max 1 retry)
- **Heartbeat timeout (60s)**: Client marked dead, tasks re-queued
- **Artifact upload failure**: Logged, task still marked complete
- **Hermes execution timeout**: Configurable per-task (default 600s), kills subprocess