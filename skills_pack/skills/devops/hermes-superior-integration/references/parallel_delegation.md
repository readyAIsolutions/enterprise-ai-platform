# Parallel Delegation Engine

This document describes the parallel delegation architecture that makes Hermes superior to Claude Code's sequential delegation.

## Core Concept

Claude Code delegates tasks **sequentially** - one subagent at a time. Hermes runs **multiple subagents in parallel** with dependency resolution, merging results intelligently.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    PARALLEL DELEGATION ENGINE                   │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │  Task A     │  │  Task B     │  │  Task C     │  ← PARALLEL │
│  │ Security    │  │ Performance │  │  Style      │             │
│  │ Review      │  │ Analysis    │  │  Review     │             │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘             │
│         │                │                │                     │
│         └────────────────┼────────────────┘                     │
│                          ▼                                      │
│              ┌─────────────────────┐                             │
│              │   RESULT MERGER     │                             │
│              │  • Conflict resolve │                             │
│              │  • Priority merge   │                             │
│              │  • Summary gen      │                             │
│              └─────────────────────┘                             │
└─────────────────────────────────────────────────────────────────┘
```

## Task Specification

```python
@dataclass
class TaskSpec:
    prompt: str                    # Task description
    agent_type: str = "subagent"   # Agent type to use
    agent_name: str = None         # Specific agent name
    context: Dict = {}             # Shared context
    max_turns: int = 20            # Max conversation turns
    toolsets: List[str] = None     # Allowed tools
    working_dir: str = None        # Isolated working directory
    priority: int = 0              # Higher = more important
    dependencies: List[str] = []   # Task IDs this depends on
```

## Dependency Resolution (DAG)

```python
async def execute_with_dependencies(self, task_ids: List[str]):
    """Execute tasks respecting dependency DAG."""
    completed = set()
    failed = set()
    
    while len(completed) + len(failed) < len(task_ids):
        # Find ready tasks (all dependencies met)
        ready = [tid for tid in task_ids 
                 if tid not in completed and tid not in failed
                 and tid not in self.running
                 and all(dep in completed for dep in self.tasks[tid].dependencies)]
        
        # Start ready tasks up to concurrency limit
        for task_id in ready[:self.max_concurrent - len(self.running)]:
            asyncio.create_task(self._run_task(task_id))
        
        await asyncio.sleep(0.1)
```

## Result Merging Strategies

### 1. Concatenation (Default)
```python
def merge_concat(results: List[TaskResult]) -> str:
    return "\n\n---\n\n".join(r.result for r in results if r.status == "completed")
```

### 2. Priority Merge
```python
def merge_priority(results: List[TaskResult]) -> str:
    # Higher priority results override
    sorted_results = sorted(results, key=lambda r: r.priority, reverse=True)
    merged = {}
    for r in sorted_results:
        if r.status == "completed":
            merged.update(r.result)  # Assuming dict results
    return merged
```

### 3. Conflict Resolution
```python
def merge_with_conflicts(results: List[TaskResult]) -> Dict:
    conflicts = []
    merged = {}
    
    for r in results:
        if r.status != "completed":
            continue
        for key, value in r.result.items():
            if key in merged and merged[key] != value:
                conflicts.append({
                    "key": key,
                    "existing": merged[key],
                    "new": value,
                    "source": r.task_id
                })
            else:
                merged[key] = value
    
    return {"merged": merged, "conflicts": conflicts}
```

## Usage Examples

### Simple Parallel
```python
results = await delegate_parallel([
    "Security audit of auth module",
    "Performance analysis of database",
    "Code style review of frontend",
    "API documentation audit"
], agent_type="code-reviewer", max_concurrent=3)
```

### With Dependencies
```python
tasks = [
    {"id": "fetch", "prompt": "Fetch data from API"},
    {"id": "process", "prompt": "Process the data", "depends_on": ["fetch"]},
    {"id": "report", "prompt": "Generate report", "depends_on": ["process"]}
]
results = await delegate_with_dependencies(tasks)
```

### ENI Swarm Integration
```python
# For massive parallelization (50+ concurrent)
engine = ENISwarmDelegationEngine(
    max_concurrent=50,
    eni_endpoint="http://localhost:8420",
    eni_power=75
)

# Dispatch to ENI swarm
task = await bridge.submit_task(
    "Massive codebase refactoring",
    agent_type="refactoring",
    power_level=75
)
result = await bridge.wait_for_completion(task.id)
```

## Progress Tracking

```python
def get_progress(self) -> Dict:
    return {
        "total": total,
        "completed": completed,
        "failed": failed,
        "running": running,
        "pending": pending,
        "percent": completed / total * 100
    }
```

## Callbacks

```python
engine.on_task_start = lambda task_id, spec: print(f"Starting {task_id}")
engine.on_task_complete = lambda task_id, result: print(f"Done: {task_id}")
engine.on_task_failed = lambda task_id, result: print(f"Failed: {task_id}")
engine.on_progress = lambda progress: print(f"Progress: {progress['percent']:.1f}%")
```

## Why Superior to Claude Code

| Feature | Claude Code | Hermes Parallel Engine |
|---------|-------------|------------------------|
| Concurrency | Sequential | **5+ parallel** |
| Dependencies | Manual | **Auto DAG resolution** |
| ENI Swarm | No | **50+ parallel builders** |
| Result merging | Manual | **Auto-merge strategies** |
| Progress tracking | None | **Real-time callbacks** |
| Failure handling | Stop all | **Isolated failures** |
| Resource limits | None | **Per-agent limits** |