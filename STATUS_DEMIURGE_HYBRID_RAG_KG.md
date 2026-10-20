# STATUS: Hybrid RAG + Knowledge Graph Module (hybrid_rag_kg)

**Commit SHA:** `f8e9a2e`
**Branch:** `upgrade/demiurge-enterprise-boost`
**Date:** 2026-10-19

---

## 1. Transcript Understanding

From ColeMedin's "Introducing RAG 2.0: Agentic RAG + Knowledge Graphs" (p0FERNkpyHE):

**Core Thesis:** Combine **Agentic RAG** (vector/semantic search where the *agent decides* which tool to call and can do multiple searches) with **Knowledge Graphs** (entities + relationships, temporal/multi-hop facts) into one hybrid retrieval system.

**Key distinctions from transcript:**
- **Vector DB (semantic)**: Good for broad lookups — "what are AI initiatives for Google", single-entity fact retrieval
- **Knowledge Graph (relational)**: Good for relational queries — "how are Amazon and Anthropic related", "path between X and Y", multi-hop dependencies, temporal facts
- **Agentic Router**: The agent chooses between vector vs graph per query:
  - "use the knowledge graph tool only when the user asks about two companies in the same question because then we want to analyze the relationship between two companies... Otherwise, just use the vector store tool. And combine both approaches only when you are asked to do so."
- **Temporal support**: Knowledge graph edges can have `valid_at` timestamps for temporal queries

---

## 2. Public API / Facade Methods

### Module Class: `HybridRagKgModule` (registered as `hybrid_rag_kg` v1.0.0)

| Method | Description |
|--------|-------------|
| `initialize()` | Async init: creates AgenticRouter (VectorStore + KnowledgeGraph), sets status HEALTHY |
| `health_check()` | Functional probe: adds chunk/entity/relation, runs a query, returns HEALTHY/UNHEALTHY |
| `shutdown()` | Cleans up router, sets status HEALTHY (not STOPPED per contract) |
| `set_event_bus(EventBus)` | Wires platform EventBus for event publishing |

### Facade Methods (on module instance):

| Method | Description |
|--------|-------------|
| `add_chunk(chunk_id, text, metadata?)` | Ingest chunk into VectorStore; publishes `hybrid_rag_kg.document_indexed` |
| `add_document(doc_id, text, chunk_size?, chunk_overlap?)` | Split + ingest document; returns chunk IDs; publishes event |
| `add_entity(id, type?, props?)` | Add entity to KnowledgeGraph; publishes `hybrid_rag_kg.entity_added` |
| `add_relation(src, rel, dst, props?, valid_at?)` | Add typed edge with optional temporal `valid_at`; publishes `hybrid_rag_kg.relation_added` |
| `classify(query)` | Returns `'vector'`, `'graph'`, or `'hybrid'` per agentic routing rules |
| `retrieve(query, top_k?)` | Execute hybrid pipeline; returns `{query, strategy, results[]}`; publishes `hybrid_rag_kg.query_served` |

### Core Classes (exported from `hybrid_rag_kg.py`):

| Class | Purpose |
|-------|---------|
| `VectorStore` | In-memory TF cosine similarity over chunks (stdlib-only, no numpy) |
| `KnowledgeGraph` | Typed directed graph with entities, relations, multi-hop BFS, shortest path, temporal queries |
| `AgenticRouter` | Routes query → vector/graph/hybrid using deterministic RELATIONAL_CUES; fuses with RRF |
| `RetrievalResult` | Dataclass: `ref`, `source` (vector/graph), `score`, `detail` |
| `RELATIONAL_CUES` | Tuple of keywords triggering graph routing (e.g., "related to", "how are", "depends on", "temporal", "when did") |
| `tokenize(text)` | Stdlib tokenizer: lowercase alphanumeric words |

### Factory:
- `create_hybrid_rag_kg_module(config?)` → `HybridRagKgModule`

---

## 3. Verification Results

### Pytest Suite (23 tests, all passing):
```
cd "/home/hunter/Desktop/Enterprise Builder/enterprise" && python3 -m pytest modules/hybrid_rag_kg/tests -q
.......................                                                  [100%]
23 passed in 0.06s
```

**Coverage:**
- Tokenize (basic cases)
- VectorStore: chunk ingest, document splitting, search, cosine similarity determinism
- KnowledgeGraph: entities, relations (auto-create), neighbors, query_relations (both dirs), multi_hop BFS, find_path (shortest), temporal queries
- AgenticRouter: classify → vector (semantic), graph (relational + known entities), hybrid (relational no entities, known entity + broad query); retrieve per strategy with correct sources
- Module lifecycle: initialize → health_check HEALTHY → shutdown
- Module facade: add_chunk, add_document, add_entity, add_relation, classify, retrieve

### Platform Kernel Registration:
```
cd "/home/hunter/Desktop/Enterprise Builder" && PYTHONPATH="/home/hunter/Desktop/Enterprise Builder" python3 -c "from enterprise.platform_kernel import _MODULE_REGISTRY; import enterprise.modules.hybrid_rag_kg; print('hybrid_rag_kg' in _MODULE_REGISTRY)"
True
```

---

## 4. Commit SHA

`f8e9a2e` (on branch `upgrade/demiurge-enterprise-boost`)

Files added:
- `modules/hybrid_rag_kg/__init__.py` (module registration, facade, lifecycle)
- `modules/hybrid_rag_kg/hybrid_rag_kg.py` (core: VectorStore, KnowledgeGraph, AgenticRouter, ~650 lines)
- `modules/hybrid_rag_kg/tests/test_hybrid_rag_kg.py` (23 tests)

---

## 5. Issues / Notes

- **Distinct from `hybrid_kg_retrieval`**: This module (`hybrid_rag_kg`) is grounded in the *same transcript* but implements its own VectorStore, KnowledgeGraph, and AgenticRouter with temporal edge support (`valid_at`), document chunking, and slightly different routing heuristics. No file/class name overlap with `hybrid_kg_retrieval`.

- **Stdlib-only constraint met**: No numpy, pandas, requests, yaml, or external deps. Uses `math.sqrt`, `collections.Counter`, `collections.deque`, `re`, `dataclasses`.

- **Line count**: `hybrid_rag_kg.py` is ~650 lines (under 700 limit).

- **Shutdown status**: Per contract, `shutdown()` sets status to `HealthStatus.HEALTHY` (not `STOPPED`).

- **Event publishing**: Uses `Event.create()` factory (not `EventBus.Event.create`).