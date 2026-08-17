---
name: eni-module-knowledge_graph
description: Operate the ENI Enterprise `knowledge_graph` module (Legacy Core) — Knowledge Graph OS Module Use when working with knowledge_graph in the Enterprise Platform.
---

# Module skill: knowledge_graph

- Category: Legacy Core (priority ?)
- Version: 1.0.0
- Purpose: Knowledge Graph OS Module

## What it does
Knowledge Graph OS Module

Enterprise-grade knowledge graph for mapping and managing organizational
knowledge: entities, relationships, provenance, resolution, contradiction
management, and secure retrieval.

Version: 1.0.0

## Key API (facade methods on the @module class)
- health_check\n- initialize\n- shutdown

## Use
Import via:
```python
from enterprise.modules.knowledge_graph import create_knowledge_graph_module
m = create_knowledge_graph_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/knowledge_graph/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.
