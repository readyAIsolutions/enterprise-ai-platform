---
name: eni-module-agent_coordination
description: Operate the ENI Enterprise `agent_coordination` module (Legacy Core) — Agent Communication & Coordination OS — Multi-agent orchestration, task scheduling, Use when working with agent_coordination in the Enterprise Platform.
---

# Module skill: agent_coordination

- Category: Legacy Core (priority ?)
- Version: 1.0.0
- Purpose: Agent Communication & Coordination OS — Multi-agent orchestration, task scheduling,

## What it does
Agent Communication & Coordination OS — Multi-agent orchestration, task scheduling,
shared knowledge, conflict resolution, verification, and fault tolerance.

Version: 1.0.0

## Key API (facade methods on the @module class)
- health_check\n- initialize\n- shutdown

## Use
Import via:
```python
from enterprise.modules.agent_coordination import create_agent_coordination_module
m = create_agent_coordination_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/agent_coordination/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.
