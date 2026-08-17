---
name: eni-module-a2a
description: Operate the ENI Enterprise `a2a` module (Legacy Core) — ENI A2A Module -- Agent-to-Agent protocol (Google A2A style). Use when working with a2a in the Enterprise Platform.
---

# Module skill: a2a

- Category: Legacy Core (priority ?)
- Version: 1.0.0
- Purpose: ENI A2A Module -- Agent-to-Agent protocol (Google A2A style).

## What it does
ENI A2A Module -- Agent-to-Agent protocol (Google A2A style).

A stdlib-only implementation of agent-to-agent messaging and task
orchestration. Agents advertise themselves with an ``AgentCard`` (resolved to
an ``AgentKey``), exchange structured ``Message`` envelopes, and coordinate
work through ``Task`` objects in an in-memory ``TaskManager`` that enforces
valid life-cycle transitions, idempotency keys and bounded retries.

The module is a registered Platform Kernel module implementing the standard
lifecycle (``initialize`` / ``health_check`` / ``shutdown``) and the event-bus
wiring contract (``set_event_bus``). A public ``A2AFacade`` exposes
``register_agent_card`` / ``list_agents`` / ``create_task`` / ``get_task`` /
``send_message`` / ``handoff``.

Version: 1.0.0
Python: 3.11+

## Key API (facade methods on the @module class)
- create_task\n- facade\n- get_task\n- handoff\n- health_check\n- initialize\n- list_agents\n- max_tasks\n- persists\n- register_agent_card\n- router\n- send_message\n- set_event_bus\n- shutdown\n- store\n- transition\n- transport

## Use
Import via:
```python
from enterprise.modules.a2a import create_a2a_module
m = create_a2a_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/a2a/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.
