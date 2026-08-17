---
name: eni-module-memory
description: Operate the ENI Enterprise `memory` module (Legacy Core) — ENI Agent Memory OS Module. Use when working with memory in the Enterprise Platform.
---

# Module skill: memory

- Category: Legacy Core (priority ?)
- Version: 1.0.0
- Purpose: ENI Agent Memory OS Module.

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

## Key API (facade methods on the @module class)
- DEFAULT_DB\n- add\n- consolidate\n- database_path\n- delete\n- forget\n- get\n- get_memories\n- health_check\n- initialize\n- memory\n- remember\n- search\n- search_all\n- set_event_bus\n- shutdown\n- top_k\n- update

## Use
Import via:
```python
from enterprise.modules.memory import create_memory_module
m = create_memory_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/memory/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.
