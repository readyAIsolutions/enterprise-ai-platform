# STATUS — Demiurge Wave: `agentic_rag` module

**Branch:** `upgrade/demiurge-enterprise-boost`
**Transcript source:** `data/transcripts/ColeMedin/p0FERNkpyHE.md`
("Introducing RAG 2.0: Agentic RAG + Knowledge Graphs (FREE Template)")

## Module
`modules/agentic_rag/` — Agentic RAG + knowledge-graph retrieval engine.

| File | Purpose |
|------|---------|
| `modules/agentic_rag/agentic_rag.py` | pure, network-free logic engine |
| `modules/agentic_rag/__init__.py` | ENI `Module` wrapper + facade |
| `modules/agentic_rag/tests/test_agentic_rag.py` | unit tests |

## PASS/FAIL board
| Check | Result |
|-------|--------|
| `pytest modules/agentic_rag/tests -q` | **PASS — 19 passed, 0 failed** |
| Registration (`'agentic_rag' in _MODULE_REGISTRY`) | **True** |
| Git commit created | **Yes** |
| Commit SHA | see `git log -1` below |

## Real numbers
- Test pass count: **19**
- Test fail count: **0**
- Registration: **True**
- Knowledge-graph fixture: **8 nodes, 5 edges** (Amazon–Anthropic–AWS
  invested_in/runs_on; Microsoft–OpenAI–Azure partnered_with/hosted_on;
  Google–DeepMind own) — direct from the transcript's Big-Tech demo.
- Vector-store fixture: **4 chunks** ("big tech AI initiatives").

## Public API (module)
- `create_agentic_rag_module(config=None) -> AgenticRagModule`
- `AgenticRagModule(answer|decompose|traverse|retrieve|rerank|graph_info)`
- `AgenticRag`, `KnowledgeGraph`, `VectorStore`, `Chunk`,
  `make_agentic_rag`, `builtin_bigtech_graph`, `builtin_bigtech_store`

## What was understood from the transcript
The talk contrasts inflexible *vanilla/naive RAG* (embed query → top-K chunks →
force-feed context to the LLM) with *agentic RAG*, where the agent reasons
about **how** it explores the knowledge base. The agent chooses a vector-store
lookup for single-entity / fact questions ("Google AI initiatives"), a
**knowledge-graph traversal** for relational / multi-hop questions about two or
more entities ("how are OpenAI and Microsoft related?" — via typed edges:
Amazon -invested_in-> Anthropic -runs_on-> AWS; Microsoft -partnered_with->
OpenAI -hosted_on-> Azure), or **combines both** when asked. Entities are
graph nodes, relationships are edges; retrieval + reranking hone in on the most
relevant chunks. The engine implements exactly this plan/decompose → traverse →
retrieve → rerank → assemble loop in pure Python (no embeddings/LLM/DB), so it
is deterministic and unit-testable.

## UNVALIDATED
- No integration with a real PGVector/Neo4j backend (transcript uses
  PostgreSQL+PGVector and Neo4j via Graphiti); this module is the in-memory
  pure-logic core only and is intentionally network-free.
- Full platform boot / end-to-end demo not run (task scope limited to module
  tests + registration). Orchestrator merges the manifest centrally; not
  touched here.
- No embedding-model similarity; retrieval uses lexical-overlap scoring as a
  stand-in for vector similarity.
