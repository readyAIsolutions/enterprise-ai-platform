---
name: eni-module-swarm_bridge
description: Operate the ENI Enterprise `swarm_bridge` module (Legacy Core) — ENI Swarm Enterprise Module v5.0.0 Use when working with swarm_bridge in the Enterprise Platform.
---

# Module skill: swarm_bridge

- Category: Legacy Core (priority ?)
- Version: 5.0.0
- Purpose: ENI Swarm Enterprise Module v5.0.0

## What it does
ENI Swarm Enterprise Module v5.0.0
===================================
Enterprise Platform Kernel module for the ENI Swarm — the 50-builder
on-demand AI agent fleet coordinated by Master Driver v5.0.

Integrates swarm lifecycle management (spawn, status, pause/resume),
health monitoring, prompt enhancement via PromptForge, and event-driven
communication into the Enterprise AI OS.

Architecture:
  ENISwarmModule (Module)
  ├── SwarmBridge      — lifecycle, status, task management
  ├── SwarmHealthCheck  — continuous health monitoring & metrics
  └── PromptForgeBridge — wraps PromptForge for enterprise prompt enhancement

Events emitted:
  - swarm.builder.started     — a builder began executing a task
  - swarm.builder.completed   — a builder finished successfully
  - swarm.builder.failed   

## Key API (facade methods on the @module class)
(module-level API)

## Use
Import via:
```python
from enterprise.modules.swarm_bridge import create_swarm_bridge_module
m = create_swarm_bridge_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/swarm_bridge/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.
