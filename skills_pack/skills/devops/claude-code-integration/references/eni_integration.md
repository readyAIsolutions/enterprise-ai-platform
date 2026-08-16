# ENI Swarm Integration

This documents how Hermes bridges to the ENI (Eternal Neural Intelligence) Swarm for massive parallelization beyond what any single agent can achieve.

## What is ENI Swarm?

ENI (Eternal Neural Intelligence) Swarm is a self-organizing fleet of 60+ specialized AI builders that can work on different parts of a problem simultaneously. It's like having 50+ specialized developers working on your codebase simultaneously.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        HERMES AGENT                                  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                 │
│  │  TUI/Chat   │  │  Agent Loop │  │  Delegation │                 │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘                 │
└─────────┼────────────────┼────────────────┼────────────────────────┘
          │                │                │
          ▼                ▼                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      ENI SWARM BRIDGE                                │
│  • HTTP API client                                                   │
│  • Task dispatch & monitoring                                        │
│  • FIFO thinking stream integration                                  │
│  • Power level management (12/25/38/50/75/100%)                     │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        ENI SWARM (localhost:8420)                   │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌────────────┐  │
│  │  BUILDER 1   │ │  BUILDER 2   │ │  BUILDER N   │ │ HEARTBEAT  │  │
│  │  (Security)  │ │  (Perf)      │ │  (Style)     │ │  Monitor   │  │
│  └──────────────┘ └──────────────┘ └──────────────┘ └────────────┘  │
│         50+ specialized builders working in parallel                 │
└─────────────────────────────────────────────────────────────────────┘
```

## Power Levels

| Level | Builders | Use Case |
|-------|----------|----------|
| 25%   | 12       | Quick tasks, code review |
| 50%   | 25       | Standard development |
| 75%   | 38       | Large refactoring |
| 100%  | 50       | Massive parallelization |

## Integration Points

### 1. Task Submission

```python
from hermes_superior_integration.scripts.eni_bridge import ENIBridge

bridge = ENIBridge(eni_endpoint="http://localhost:8420")

# Submit task
task = await bridge.submit_task(
    prompt="Analyze entire codebase for security vulnerabilities",
    agent_type="security-auditor",
    power_level=75,
    context={"repo": "my-project", "focus": "auth"}
)

# Wait for completion with thinking stream
result = await bridge.wait_for_completion(task.id)
print(result.result)
```

### 2. Parallel Dispatch

```python
# Dispatch multiple tasks to ENI
prompts = [
    "Security audit of authentication module",
    "database layer", 
    "API endpoints",
    "frontend components"
]

results = await eni_parallel_dispatch(
    [f"Security audit of {p}" for p in prompts],
    power=50,
    agent_type="security-auditor"
)
```

### 3. Thinking Stream (Real-time)

```python
async def on_thinking(task_id: str, thought: str):
    print(f"[{task_id}] 💭 {thought}")

bridge.on_thinking = on_thinking

task = await bridge.submit_task("Complex refactoring", power=50)
result = await bridge.wait_for_completion(task.id)
# Real-time thinking streamed via callback
```

## FIFO Thinking Integration

ENI swarm exposes thinking via FIFO pipes:

```python
from hermes_superior_integration.scripts.eni_bridge import ENIFIFOReader

fifo = ENIFIFOReader("/tmp/eni_fifo")

# Open FIFO for task
await fifo.open_fifo(task_id)

# Stream thinking
async def handle_thinking(task_id, thought):
    print(f"[{task_id}] 💭 {thought}")

asyncio.create_task(fifo.read_thinking(task_id, handle_thinking))
```

## Power Level Management

```python
# Check available levels
levels = await bridge.get_power_levels()
# Returns: {12: 12, 25: 25, 38: 38, 50: 50}

# Set default
await bridge.set_power_level(75)  # Valid: 12, 25, 38, 50

# Override per task
task = await bridge.submit_task(
    "Massive refactoring",
    power_level=100  # Use all 50 builders
)
```

## Builder Pool Monitoring

```python
builders = await bridge.refresh_builders()
for b in builders:
    print(f"{b.name}: {b.status} (load: {b.load:.1%})")
# Output:
# builder_sec_01: running (load: 0.8)
# builder_perf_02: idle (load: 0.0)
# builder_style_03: running (load: 0.3)
```

## Task Types for ENI

| Agent Type | Best For | Power Level |
|------------|----------|-------------|
| `security-auditor` | Vulnerability scanning | 50-75 |
| `performance-analyzer` | Bottleneck detection | 50 |
| `code-reviewer` | Style & correctness | 25-50 |
| `refactoring` | Large-scale changes | 75-100 |
| `test-generator` | Test coverage | 50 |
| `documentation` | API docs, guides | 25 |
| `builder` | General purpose | 50 |

## Configuration

```yaml
eni_swarm:
  endpoint: "http://localhost:8420"
  default_power: 50
  auto_start: true
  fifo_dir: "/tmp/eni_fifo"
  timeout: 300
  max_retries: 3
  
  power_levels:
    quick: 25
    standard: 50
    heavy: 75
    maximum: 100
```

## Deployment

```bash
# Start ENI swarm (60 builders)
eni-swarm-start --power 100

# Or with Docker
docker run -d -p 8420:8420 \
  -v /tmp/eni:/tmp/eni \
  nousresearch/eni-swarm:latest --power 100

# Check status
curl http://localhost:8420/api/builders | jq
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Connection refused | Check `eni-swarm-start` running |
| Task timeout | Increase timeout, check builder health |
| No builders available | Reduce power level or wait |
| FIFO not found | Check `/tmp/eni_fifo/` permissions |
| Thinking stream empty | Verify FIFO reader running |

## Advanced: Custom Agent Types

```python
# Register custom agent type with ENI
custom_agent = {
    "name": "my-specialist",
    "description": "Expert in GraphQL optimization",
    "system_prompt": "You are a GraphQL expert...",
    "toolsets": ["read", "search", "bash", "write"],
    "max_turns": 30
}

# Register via ENI API
await bridge.session.post(
    f"{bridge.eni_endpoint}/api/agents",
    json=custom_agent
)
```

## Why Superior to Claude Code

| Capability | Claude Code | Hermes + ENI |
|------------|-------------|--------------|
| Parallel builders | 1 | **50+** |
| Specialized agents | Manual | **Auto-assigned** |
| Real-time thinking | No | **FIFO stream** |
| Power scaling | Fixed | **25-100%** |
| Builder monitoring | No | **Real-time** |
| Cost | $20/mo | **Free (local)** |