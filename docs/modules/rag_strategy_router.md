# Module: `rag_strategy_router`

- Category: Legacy Core · priority 60
- Version: 1.0.0
- Purpose: ``rag_strategy_router`` — intent-based VECTOR / GRAPH / HYBRID RAG router.
- Skill: `eni-module-rag_strategy_router` (ICM stages) in skills_pack/skills/eni-modules/rag_strategy_router/

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
``agentic_rag`` / ``knowledge_graph`` / ``rag`` / ``hybrid_kg_retrieval``
modules. Retrievers are injected by the caller.

Export surface:
  * Strategy                 — VECTOR / GRAPH / HYBRID enum.
  * RouteDecision            — strategy + confidence + matched_signals + rationale.
  * Signal                   — a single transcript-grounded routing signal.
  * QueryClassifier          — deterministic intent scorer.
  * StrategyRouter           — route / route_batch / dispatch + retriever registry.
  * RagStrategyRouterModule  — the ENI platform Module wrapper.
  * create_rag_strategy_router_module(config) — factory used by the platform.

## Key API (facade methods)
dispatch, health_check, initialize, register_retriever, route, route_batch, set_event_bus, shutdown, strategies

## Tests
```bash
python3 -m pytest modules/rag_strategy_router/tests -q
```

## Import
```python
from enterprise.modules.rag_strategy_router import create_rag_strategy_router_module
m = create_rag_strategy_router_module()
```
