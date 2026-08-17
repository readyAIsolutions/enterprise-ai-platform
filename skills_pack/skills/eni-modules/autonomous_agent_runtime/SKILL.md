---
name: eni-module-autonomous_agent_runtime
description: Operate the ENI Enterprise `autonomous_agent_runtime` module (Legacy Core) — ENI Autonomous Agent Runtime Module -- Multi-provider LLM abstraction. Use when working with autonomous_agent_runtime in the Enterprise Platform.
---

# Module skill: autonomous_agent_runtime

- Category: Legacy Core (priority ?)
- Version: 1.0.0
- Purpose: ENI Autonomous Agent Runtime Module -- Multi-provider LLM abstraction.

## What it does
ENI Autonomous Agent Runtime Module -- Multi-provider LLM abstraction.

A first-class Platform Kernel module that wraps the ``provider_abstraction``
subsystem: a multi-provider LLM abstraction (provider registry with health
checks), session-aware cost tracking, circuit-breaking fallback orchestration,
and SSE streaming normalization.

The module auto-registers with the Platform Kernel when this package is
imported (via the ``@module`` decorator), implementing the standard lifecycle
(``initialize`` / ``health_check`` / ``shutdown``), the event-bus wiring
contract (``set_event_bus``), and exposing a public
``AutonomousAgentRuntimeFacade`` with ``register_providers_from_config`` /
``list_providers`` / ``get_provider`` / ``cost_summary`` /
``fallback_status`` / ``health_check_all``.

Version: 

## Key API (facade methods on the @module class)
- cost_summary\n- facade\n- fallback_status\n- get_provider\n- health_check\n- health_check_all\n- initialize\n- list_providers\n- register_providers_from_config\n- reset_circuit\n- set_event_bus\n- shutdown

## Use
Import via:
```python
from enterprise.modules.autonomous_agent_runtime import create_autonomous_agent_runtime_module
m = create_autonomous_agent_runtime_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/autonomous_agent_runtime/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.
