---
name: eni-module-semantic_memory
description: Operate the ENI Enterprise `semantic_memory` module (Legacy Core) — ENI Semantic Memory OS Module. Use when working with semantic_memory in the Enterprise Platform.
---

# Module skill: semantic_memory

- Category: Legacy Core (priority ?)
- Version: 2.0.0
- Purpose: ENI Semantic Memory OS Module.

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

## Key API (facade methods on the @module class)
- consolidate\n- db_path\n- dim\n- group_by_time_bucket\n- health_check\n- initialize\n- memory\n- ranking\n- recall\n- recall_since\n- remember\n- set_event_bus\n- shutdown\n- top_k

## Use
Import via:
```python
from enterprise.modules.semantic_memory import create_semantic_memory_module
m = create_semantic_memory_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/semantic_memory/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.
