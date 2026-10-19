---
name: eni-module-rag_strategy_router
description: Operate the ENI Enterprise `rag_strategy_router` module (Legacy Core) — ``rag_strategy_router`` — intent-based VECTOR / GRAPH / HYBRID RAG router. Use when working with rag_strategy_router in the Enterprise Platform.
---

# Module skill: rag_strategy_router

- Category: Legacy Core (priority ?)
- Version: 1.0.0
- Purpose: ``rag_strategy_router`` — intent-based VECTOR / GRAPH / HYBRID RAG router.

## What it does
``rag_strategy_router`` — intent-based VECTOR / GRAPH / HYBRID RAG router.

Grounded entirely in the real pulled transcript ``ColeMedin/p0FERNkpyHE.md``
("Introducing RAG 2.0: Agentic RAG + Knowledge Graphs (FREE Template)"). The
talk shows an agent that can "pick and choose how it explores the knowledge":
a **vector database** lookup for single-entity / broad-semantic fact questions
("what are the AI initiatives for Google"), a **knowledge-graph** traversal for
relational / multi-entity questions ("how are OpenAI and Microsoft related"),
or **both** when the query carries both intents / explicitly asks to "use both
search types".

This module is a ROUTER / DISPATCHER that classifies query intent and selects a
strategy — it is NOT itself a retriever and does not depend on the existing
``ag

## Key API (facade methods on the @module class)
- dispatch\n- health_check\n- initialize\n- register_retriever\n- route\n- route_batch\n- set_event_bus\n- shutdown\n- strategies

## Use
Import via:
```python
from enterprise.modules.rag_strategy_router import create_rag_strategy_router_module
m = create_rag_strategy_router_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/rag_strategy_router/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.
