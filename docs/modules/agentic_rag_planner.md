# Module: `agentic_rag_planner`

- Category: Legacy Core · priority 14
- Version: 1.0.0
- Purpose: Agentic RAG retrieval-strategy planner module.
- Skill: `eni-module-agentic_rag_planner` (ICM stages) in skills_pack/skills/eni-modules/agentic_rag_planner/

## What it does
Agentic RAG retrieval-strategy planner module.

Grounded in Cole Medin's "Introducing RAG 2.0: Agentic RAG + Knowledge Graphs"
(YouTube p0FERNkpyHE). The agent is given BOTH a vector/semantic-search tool and
a knowledge-graph tool and "picks and chooses how it explores the knowledge".
This module is the PLANNER/ROUTER: given a query it decides which retrieval
tool(s) to use (vector vs graph vs hybrid) and in what order, and emits a
structured plan. It plans over abstract tool interfaces; it does not itself
implement a vector DB or a graph DB.

## Key API (facade methods)
health_check, initialize, plan, plan_multi, set_event_bus, shutdown

## Tests
```bash
python3 -m pytest modules/agentic_rag_planner/tests -q
```

## Import
```python
from enterprise.modules.agentic_rag_planner import create_agentic_rag_planner_module
m = create_agentic_rag_planner_module()
```
