# Module: `agentic_rag`

- Category: Agent Workflow · priority 2
- Version: 1.0.0
- Purpose: Agent-driven retrieval-augmented generation workflow.
- Skill: `eni-module-agentic_rag` (ICM stages) in skills_pack/skills/eni-modules/agentic_rag/

## What it does
Agentic RAG module — agentic RAG + knowledge-graph retrieval engine.

Grounded in the real pulled transcript ``ColeMedin/p0FERNkpyHE.md``
("Introducing RAG 2.0: Agentic RAG + Knowledge Graphs (FREE Template)"). The
talk contrasts inflexible *vanilla RAG* (embed query -> top-K chunks -> feed
fixed context to the LLM) with *agentic RAG*, where an agent reasons about how
it explores the knowledge base: a vector-store lookup for single-entity/fact
questions, a knowledge-graph traversal for relational / multi-hop questions
about two or more entities, or a combination of both. Nodes are entities, edges
are typed relationships (e.g. Amazon --invested_in--> Anthropic --runs_on-->> AWS;
Microsoft --partnered_with--> OpenAI --hosted_on--> Azure).

The engine lives in :mod:`enterprise.modules.agentic_rag.agentic_rag` and is
pure, network-free and deterministic so it can be unit-tested in isolation.

Export surface:
  * AgenticRag      — query planning, multi-hop graph traversal, retrieval,
                      reranking and answer assembly engine.
  * KnowledgeGraph  — entities (nodes) + typed relationships (edges).
  * VectorStore     — in-memory chunk store with lexical-overlap retrieval.
  * Chunk           — a single retrievable document chunk.
  * AgenticRagModule — the ENI platform Module wrapper.
  * create_agentic_rag_module(config) — factory used by the platform.

## Key API (facade methods)
answer, decompose, graph_info, health_check, initialize, rerank, retrieve, shutdown, traverse

## Tests
```bash
python3 -m pytest modules/agentic_rag/tests -q
```

## Import
```python
from enterprise.modules.agentic_rag import create_agentic_rag_module
m = create_agentic_rag_module()
```
