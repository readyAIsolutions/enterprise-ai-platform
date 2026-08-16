# ENI Executor Fix Reference

## Problem
`ENITaskExecutor` in `creed_client/eni_bridge.py` used `active_tasks` dictionary, but the client code in `creed_client/client.py:_run_task()` expected `running_tasks` (matching `TaskExecutor`).

```python
# client.py:_run_task() - EXPECTED
executor.running_tasks[task_id] = asyncio.current_task()

# eni_bridge.py - HAD
self.active_tasks: Dict[str, asyncio.Task] = {}
```

**Error**: `AttributeError: 'ENITaskExecutor' object has no attribute 'running_tasks'`

## Solution
1. Renamed `active_tasks` → `running_tasks` in `ENITaskExecutor.__init__()`
2. Added compatibility property for any code using `active_tasks`:
```python
@property
def active_tasks(self):
    return self.running_tasks
```

## Files Changed
- `creed_client/eni_bridge.py`: Lines 372-378

## Verification
```bash
# Clear cache first (Python caches imports)
find . -name "__pycache__" -exec rm -rf {} +

# Start server + client
python3 -m creed_server.server
python3 -m creed_client.client

# Submit task targeting ENI client
creed submit --name "test" --prompt "..." --target-client <client-id>
```

## Related
- `references/protocol.md` — Message types for task assignment
- `references/client-execution.md` — TaskExecutor vs ENITaskExecutor