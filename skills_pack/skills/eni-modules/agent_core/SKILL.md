---
name: eni-module-agent_core
description: Operate the ENI Enterprise `agent_core` module (Legacy Core) — Claude Code Core — Enterprise Platform Kernel Module v2.0.0 Use when working with agent_core in the Enterprise Platform.
---

# Module skill: agent_core

- Category: Legacy Core (priority ?)
- Version: 2.0.0
- Purpose: Claude Code Core — Enterprise Platform Kernel Module v2.0.0

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
  ├── TaskCoordinator       — DAG scheduli

## Key API (facade methods on the @module class)
- context_manager\n- coordinator\n- engine\n- health_check\n- hooks\n- initialize\n- scheduler\n- services\n- shutdown\n- state

## Use
Import via:
```python
from enterprise.modules.agent_core import create_agent_core_module
m = create_agent_core_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/agent_core/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.
