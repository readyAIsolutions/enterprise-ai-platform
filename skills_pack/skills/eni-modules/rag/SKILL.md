---
name: eni-module-rag
description: Operate the ENI Enterprise `rag` module (Legacy Core) — Production RAG System — Enterprise-grade Retrieval-Augmented Generation. Use when working with rag in the Enterprise Platform.
---

# Module skill: rag

- Category: Legacy Core (priority ?)
- Version: 1.0.0
- Purpose: Production RAG System — Enterprise-grade Retrieval-Augmented Generation.

## What it does
Production RAG System — Enterprise-grade Retrieval-Augmented Generation.

This module provides a complete, production-ready RAG system with:
1. Chunking Strategies (Semantic + Fixed)
2. Embedding Model Selection (Pre-trained + Custom)
3. Retrieval (Vector + Keyword + Hybrid)
4. Re-Ranking (Gradual + Incremental)
5. Context Assembly (Summarization + Cross-Document Fusion)
6. Citation Handling (Research Integrity)

All components are designed to work independently or as a unified pipeline,
with full integration into the ENI Enterprise Platform (kb_bridge, memory,
semantic_memory, compression_bridge, eval_gate, agent_core).

## Key API (facade methods on the @module class)
(module-level API)

## Use
Import via:
```python
from enterprise.modules.rag import create_rag_module
m = create_rag_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/rag/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.
