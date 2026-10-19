# Module: `hybrid_kg_retrieval`

- Category: Legacy Core · priority 34
- Version: 1.0.0
- Purpose: hybrid_kg_retrieval — an agentic RAG 2.0 retrieval engine that combines a
- Skill: `eni-module-hybrid_kg_retrieval` (ICM stages) in skills_pack/skills/eni-modules/hybrid_kg_retrieval/

## What it does
hybrid_kg_retrieval — an agentic RAG 2.0 retrieval engine that combines a
vector/semantic index with an in-memory knowledge graph, routing each query to
vector, graph, or BOTH strategies and fusing the results with provenance.

Grounded in ColeMedin's "Introducing RAG 2.0: Agentic RAG + Knowledge Graphs"
(https://www.youtube.com/watch?v=p0FERNkpyHE).

This module is distinct from `agentic_rag` and `knowledge_graph`: its facade is
focused on the HYBRID combination + agentic per-query routing + rank fusion,
computed locally with pure stdlib (no network, no embeddings, no LLM calls).

## Key API (facade methods)
add_entity, add_relation, classify, health_check, index_document, initialize, retrieve, set_event_bus, shutdown

## Tests
```bash
python3 -m pytest modules/hybrid_kg_retrieval/tests -q
```

## Import
```python
from enterprise.modules.hybrid_kg_retrieval import create_hybrid_kg_retrieval_module
m = create_hybrid_kg_retrieval_module()
```
