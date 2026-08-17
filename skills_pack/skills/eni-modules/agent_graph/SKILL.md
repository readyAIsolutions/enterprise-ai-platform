---
name: eni-module-agent_graph
description: Operate the ENI Enterprise `agent_graph` module (Legacy Core) — ENI Agent Graph Module — langgraph-style stateful agent graph orchestration. Use when working with agent_graph in the Enterprise Platform.
---

# Module skill: agent_graph

- Category: Legacy Core (priority ?)
- Version: 1.0.0
- Purpose: ENI Agent Graph Module — langgraph-style stateful agent graph orchestration.

## What it does
ENI Agent Graph Module — langgraph-style stateful agent graph orchestration.

A dependency-free (stdlib-only) engine for building and running directed
graphs of stateful agent nodes, with checkpoint persistence for replay and
inspection.

Features:
- ``add_node`` / ``add_edge`` build-time validation (undefined node targets
  raise ``ValueError``).
- ``run`` walks the graph in topological order, honoring conditional edges,
  with START/END markers and cycle/back-edge protection via ``max_steps``.
- :class:`StateCheckpointStore` persists intermediate states keyed by
  ``run_id``.
- :class:`SupervisorGraph` — a coordinator node that routes to worker nodes
  based on a state key.
- :class:`AgentGraphFacade` — public surface: ``build_graph``, ``add_node``,
  ``add_edge``, ``run_graph``, ``get_c

## Key API (facade methods on the @module class)
- add_edge\n- add_node\n- build_graph\n- build_state_graph\n- facade\n- get_checkpoint\n- health_check\n- initialize\n- list_runs\n- max_steps\n- run_graph\n- set_event_bus\n- shutdown\n- state_store

## Use
Import via:
```python
from enterprise.modules.agent_graph import create_agent_graph_module
m = create_agent_graph_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/agent_graph/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.
