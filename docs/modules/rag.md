# Module: `rag`

- Category: Legacy Core · priority 51
- Version: 1.0.0
- Purpose: Production RAG System — Enterprise-grade Retrieval-Augmented Generation.
- Skill: `eni-module-rag` (ICM stages) in skills_pack/skills/eni-modules/rag/

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

## Key API (facade methods)
(module-level API)

## Tests
```bash
python3 -m pytest modules/rag/tests -q
```

## Import
```python
from enterprise.modules.rag import create_rag_module
m = create_rag_module()
```
