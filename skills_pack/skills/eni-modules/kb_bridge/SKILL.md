---
name: eni-module-kb_bridge
description: Operate the ENI Enterprise `kb_bridge` module (Legacy Core) — ENI Knowledge Base OS Module Use when working with kb_bridge in the Enterprise Platform.
---

# Module skill: kb_bridge

- Category: Legacy Core (priority ?)
- Version: 1.0.0
- Purpose: ENI Knowledge Base OS Module

## What it does
ENI Knowledge Base OS Module

Enterprise-grade wrapper around Hermes KB Universal, providing
structured CRUD, search, vector search, metrics, and health checks
as a registered Platform Kernel module.

Exports:
  ENIKBModule        — @module-decorated Module subclass
  KnowledgeBaseBridge — Full KB wrapper with event publishing
  KBHealthCheck      — DB connectivity health verification

Version: 1.0.0
Python: 3.10+

## Key API (facade methods on the @module class)
- bridge\n- health_check\n- health_checker\n- initialize\n- set_event_bus\n- shutdown

## Use
Import via:
```python
from enterprise.modules.kb_bridge import create_kb_bridge_module
m = create_kb_bridge_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/kb_bridge/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.
