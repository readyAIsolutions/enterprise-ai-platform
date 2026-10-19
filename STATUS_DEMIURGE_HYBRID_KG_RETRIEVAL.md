# STATUS — hybrid_kg_retrieval (DEMIURGE enterprise boost)

## What I understood (from the ColeMedin RAG 2.0 transcript)
The transcript "Introducing RAG 2.0: Agentic RAG + Knowledge Graphs" teaches
combining TWO knowledge-retrieval strategies for an AI agent and letting the
agent choose per query:

- **Vector / semantic RAG** — chunk documents, retrieve by semantic similarity;
  best for broad "find relevant passages" lookups (he uses Postgres + pgvector).
- **Knowledge-graph retrieval** — entities + typed relationships; best for
  multi-hop / relational questions ("how does X relate to Y", "what depends on Z").

**RAG 2.0 = an agentic retriever** that has tools for BOTH semantic search and
graph traversal and decides, per query, whether to use vector, graph, or both,
then fuses the results.

This module implements that HYBRID architecture + routing + fusion **locally and
deterministically** — no network, no real embeddings, no LLM calls. It is
intentionally distinct from the existing `agentic_rag` and `knowledge_graph`
modules (not imported, not touched): the facade here is focused on the hybrid
combination + agentic routing + rank fusion.

## Module API
`modules/hybrid_kg_retrieval/`

### core.py (pure stdlib)
- `tokenize(text)` — lowercase alphanumeric tokenizer.
- `VectorIndex` — deterministic "vector" stand-in: TF bag-of-words vectors with
  **cosine similarity** (Counter + math). `add_document(doc_id, text)`,
  `search(query, top_k)` → ranked `(doc_id, score)`.
- `KnowledgeGraph` — real in-memory typed directed graph. `add_entity`,
  `add_relation`, `neighbors(id, rel=None)`, `query_relations(entity)`,
  `multi_hop(start, max_hops, rel=None)` (BFS distances), `find_path(start, end)`.
- `HybridRetriever` — the agentic router + fusion engine.
  - `classify(query)` → `'vector' | 'graph' | 'hybrid'` via deterministic
    heuristics: relational cue words (`RELATIONAL_CUES`: "related to",
    "depends on", "how does", "connected", "path between", …) route to graph;
    plain lookups to vector; mixed/entity-naming-broad queries to hybrid.
  - `retrieve(query, top_k)` → `{query, strategy, results}` where results are
    `RetrievalResult(ref, source, score, detail)`; hybrid uses **Reciprocal
    Rank Fusion (RRF)** across vector + graph lists, each result tagged with
    `source` provenance ('vector' | 'graph').

### __init__.py (platform facade)
- Unconditional `from enterprise.platform_kernel import Event, HealthStatus, Module, module`.
- `__version__ = "1.0.0"`.
- `@module(name="hybrid_kg_retrieval", version="1.0.0", config_defaults={"default_top_k": 5, "max_hops": 2})`.
- `HybridKgRetrievalModule(Module)`: async `initialize` (HEALTHY/UNHEALTHY+raise),
  async `health_check`, async `shutdown` (STOPPING), `set_event_bus`, guarded
  `_publish`. Facade methods: `index_document`, `add_entity`, `add_relation`,
  `classify`, `retrieve` — each emitting events when a bus is attached.
- `create_hybrid_kg_retrieval_module(config=None)` factory + full `__all__`.

## Verification (real output)
1. `python3 -m pytest modules/hybrid_kg_retrieval/tests -q`
   → **14 passed in 0.05s** (PASS=14, FAIL=0).
2. Registration:
   `... print('hybrid_kg_retrieval' in _MODULE_REGISTRY)` → **True**.

## Files created
- `modules/hybrid_kg_retrieval/__init__.py`
- `modules/hybrid_kg_retrieval/core.py`
- `modules/hybrid_kg_retrieval/tests/__init__.py`
- `modules/hybrid_kg_retrieval/tests/test_hybrid_kg_retrieval.py`
- `STATUS_DEMIURGE_HYBRID_KG_RETRIEVAL.md`

## Issues
- `pytest` is not installed in the active `hermes` venv (`python3 -m pytest`
  reports "No module named pytest"); the repo's pytest lives at
  `/home/hunter/.local/bin/pytest`, which was used and passed all 14 tests.
  No code issue — environment note only.
- No changes to `config.yaml`, `platform_kernel.py`, `agentic_rag`,
  `knowledge_graph`, or any other module.

Branch: `upgrade/demiurge-enterprise-boost`.
