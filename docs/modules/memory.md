# Module: `memory`

- Category: Legacy Core · priority 34
- Version: 1.0.0
- Purpose: ENI Agent Memory OS Module.
- Skill: `eni-module-memory` (ICM stages) in skills_pack/skills/eni-modules/memory/

## What it does
ENI Agent Memory OS Module.

A mem0-style hybrid long-term memory engine: dependency-free semantic /
episodic / declarative / procedural memory with per-user profiles,
deterministic feature-hash embeddings, relevance/importance/recency ranking,
consolidation & de-duplication, and persistent SQLite storage.

The module is a registered Platform Kernel module implementing the standard
lifecycle (``initialize`` / ``health_check`` / ``shutdown``) and the
event-bus wiring contract (``set_event_bus``).

Version: 1.0.0
Python: 3.11+

## Key API (facade methods)
DEFAULT_DB, add, consolidate, database_path, delete, forget, get, get_memories, health_check, initialize, memory, remember, search, search_all, set_event_bus, shutdown, top_k, update

## Tests
```bash
python3 -m pytest modules/memory/tests -q
```

## Import
```python
from enterprise.modules.memory import create_memory_module
m = create_memory_module()
```
