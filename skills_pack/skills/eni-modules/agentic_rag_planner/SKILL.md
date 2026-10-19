---
name: eni-module-agentic_rag_planner
description: Operate the ENI Enterprise `agentic_rag_planner` module (Legacy Core) — Agentic RAG retrieval-strategy planner module. Use when working with agentic_rag_planner in the Enterprise Platform.
---

# Module skill: agentic_rag_planner

- Category: Legacy Core (priority ?)
- Version: 1.0.0
- Purpose: Agentic RAG retrieval-strategy planner module.

## What it does
Agentic RAG retrieval-strategy planner module.

Grounded in Cole Medin's "Introducing RAG 2.0: Agentic RAG + Knowledge Graphs"
(YouTube p0FERNkpyHE). The agent is given BOTH a vector/semantic-search tool and
a knowledge-graph tool and "picks and chooses how it explores the knowledge".
This module is the PLANNER/ROUTER: given a query it decides which retrieval
tool(s) to use (vector vs graph vs hybrid) and in what order, and emits a
structured plan. It plans over abstract tool interfaces; it does not itself
implement a vector DB or a graph DB.

## Key API (facade methods on the @module class)
- health_check\n- initialize\n- plan\n- plan_multi\n- set_event_bus\n- shutdown

## Use
Import via:
```python
from enterprise.modules.agentic_rag_planner import create_agentic_rag_planner_module
m = create_agentic_rag_planner_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/agentic_rag_planner/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.
