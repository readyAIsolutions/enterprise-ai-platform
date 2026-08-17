# Module: `autonomous_agent_runtime`

- Category: Legacy Core · priority 15
- Version: 1.0.0
- Purpose: ENI Autonomous Agent Runtime Module -- Multi-provider LLM abstraction.
- Skill: `eni-module-autonomous_agent_runtime` (ICM stages) in skills_pack/skills/eni-modules/autonomous_agent_runtime/

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

Version: 1.0.0
Python: 3.11+

## Key API (facade methods)
cost_summary, facade, fallback_status, get_provider, health_check, health_check_all, initialize, list_providers, register_providers_from_config, reset_circuit, set_event_bus, shutdown

## Tests
```bash
python3 -m pytest modules/autonomous_agent_runtime/tests -q
```

## Import
```python
from enterprise.modules.autonomous_agent_runtime import create_autonomous_agent_runtime_module
m = create_autonomous_agent_runtime_module()
```
