# Module: `agent_core`

- Category: Legacy Core · priority 8
- Version: 2.0.0
- Purpose: Claude Code Core — Enterprise Platform Kernel Module v2.0.0
- Skill: `eni-module-agent_core` (ICM stages) in skills_pack/skills/eni-modules/agent_core/

## What it does
Claude Code Core — Enterprise Platform Kernel Module v2.0.0
============================================================

Re-implementation of Anthropic's Claude Code QueryEngine, Coordinator,
Task system, State management, Context manager, Hooks engine, and
Services as native Python async classes that plug into the ENI
Enterprise Platform Kernel.

100x better than the TypeScript original:
  - Model-agnostic (Anthropic, OpenAI, Google, local models)
  - Async-native with asyncio
  - Parallel-by-default with DAG scheduling
  - Self-healing with automatic retry and circuit breaking
  - Metric-emitting with Prometheus-compatible counters

Architecture:
  ClaudeCodeModule (Module)
  ├── SuperiorQueryEngine   — multi-model routing, streaming, tool loop
  ├── TaskCoordinator       — DAG scheduling, retry, timeout, parallel dispatch
  ├── TaskScheduler         — background tasks, swarm integration
  ├── SmartContext          — embeddings-based relevance, multi-tier compression
  ├── HooksEngine           — 25+ lifecycle hooks, sync+async, plugin system
  ├── StateManager          — distributed state with CRDT
  └── ServiceRegistry       — ModelService, ToolService, MemoryService, AuthService

Version: 2.0.0
Python: 3.10+

## Key API (facade methods)
context_manager, coordinator, engine, health_check, hooks, initialize, scheduler, services, shutdown, state

## Tests
```bash
python3 -m pytest modules/agent_core/tests -q
```

## Import
```python
from enterprise.modules.agent_core import create_agent_core_module
m = create_agent_core_module()
```
