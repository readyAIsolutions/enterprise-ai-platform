# Module: `agent_graph`

- Category: Legacy Core · priority 9
- Version: 1.0.0
- Purpose: ENI Agent Graph Module — langgraph-style stateful agent graph orchestration.
- Skill: `eni-module-agent_graph` (ICM stages) in skills_pack/skills/eni-modules/agent_graph/

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
  ``add_edge``, ``run_graph``, ``get_checkpoint``, ``list_runs``.

Version: 1.0.0
Python: 3.11+

## Key API (facade methods)
add_edge, add_node, build_graph, build_state_graph, facade, get_checkpoint, health_check, initialize, list_runs, max_steps, run_graph, set_event_bus, shutdown, state_store

## Tests
```bash
python3 -m pytest modules/agent_graph/tests -q
```

## Import
```python
from enterprise.modules.agent_graph import create_agent_graph_module
m = create_agent_graph_module()
```
