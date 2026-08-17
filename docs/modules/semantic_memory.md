# Module: `semantic_memory`

- Category: Legacy Core · priority 59
- Version: 2.0.0
- Purpose: ENI Semantic Memory OS Module.
- Skill: `eni-module-semantic_memory` (ICM stages) in skills_pack/skills/eni-modules/semantic_memory/

## What it does
ENI Semantic Memory OS Module.

Cognee-style graph/persistent memory + semantic retrieval capability:
a lightweight, dependency-free semantic retrieval layer built on sparse
feature-hash embeddings (deterministic), cosine similarity ranking, metadata
filtering, and an optional adapter into the existing knowledge-graph store.

The module is a registered Platform Kernel module implementing the standard
lifecycle (``initialize`` / ``health_check`` / ``shutdown``) and the event-bus
wiring contract (``set_event_bus``).

Version: 1.0.0
Python: 3.10+

## Key API (facade methods)
consolidate, db_path, dim, group_by_time_bucket, health_check, initialize, memory, ranking, recall, recall_since, remember, set_event_bus, shutdown, top_k

## Tests
```bash
python3 -m pytest modules/semantic_memory/tests -q
```

## Import
```python
from enterprise.modules.semantic_memory import create_semantic_memory_module
m = create_semantic_memory_module()
```
