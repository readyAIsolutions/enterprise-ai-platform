---
name: eni-module-agentic_rag
description: Operate the ENI Enterprise `agentic_rag` module (Agent Workflow) — Agent-driven retrieval-augmented generation workflow. Use when working with agentic_rag in the Enterprise Platform.
---

# Module skill: agentic_rag

- Category: Agent Workflow (priority 2)
- Version: 1.0.0
- Purpose: Agent-driven retrieval-augmented generation workflow.

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

The engine lives in :mod:`enterprise.modules.agentic

## Key API (facade methods on the @module class)
- answer\n- decompose\n- graph_info\n- health_check\n- initialize\n- rerank\n- retrieve\n- shutdown\n- traverse

## Use
Import via:
```python
from enterprise.modules.agentic_rag import create_agentic_rag_module
m = create_agentic_rag_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/agentic_rag/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.
