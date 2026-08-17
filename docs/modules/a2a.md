# Module: `a2a`

- Category: Legacy Core · priority 5
- Version: 1.0.0
- Purpose: ENI A2A Module -- Agent-to-Agent protocol (Google A2A style).
- Skill: `eni-module-a2a` (ICM stages) in skills_pack/skills/eni-modules/a2a/

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

## Key API (facade methods)
create_task, facade, get_task, handoff, health_check, initialize, list_agents, max_tasks, persists, register_agent_card, router, send_message, set_event_bus, shutdown, store, transition, transport

## Tests
```bash
python3 -m pytest modules/a2a/tests -q
```

## Import
```python
from enterprise.modules.a2a import create_a2a_module
m = create_a2a_module()
```
