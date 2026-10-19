---
name: eni-module-hybrid_kg_retrieval
description: Operate the ENI Enterprise `hybrid_kg_retrieval` module (Legacy Core) — hybrid_kg_retrieval — an agentic RAG 2.0 retrieval engine that combines a Use when working with hybrid_kg_retrieval in the Enterprise Platform.
---

# Module skill: hybrid_kg_retrieval

- Category: Legacy Core (priority ?)
- Version: 1.0.0
- Purpose: hybrid_kg_retrieval — an agentic RAG 2.0 retrieval engine that combines a

## What it does
hybrid_kg_retrieval — an agentic RAG 2.0 retrieval engine that combines a
vector/semantic index with an in-memory knowledge graph, routing each query to
vector, graph, or BOTH strategies and fusing the results with provenance.

Grounded in ColeMedin's "Introducing RAG 2.0: Agentic RAG + Knowledge Graphs"
(https://www.youtube.com/watch?v=p0FERNkpyHE).

This module is distinct from `agentic_rag` and `knowledge_graph`: its facade is
focused on the HYBRID combination + agentic per-query routing + rank fusion,
computed locally with pure stdlib (no network, no embeddings, no LLM calls).

## Key API (facade methods on the @module class)
- add_entity\n- add_relation\n- classify\n- health_check\n- index_document\n- initialize\n- retrieve\n- set_event_bus\n- shutdown

## Use
Import via:
```python
from enterprise.modules.hybrid_kg_retrieval import create_hybrid_kg_retrieval_module
m = create_hybrid_kg_retrieval_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/hybrid_kg_retrieval/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.
