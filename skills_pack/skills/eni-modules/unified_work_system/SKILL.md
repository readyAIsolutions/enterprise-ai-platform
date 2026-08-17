---
name: eni-module-unified_work_system
description: Operate the ENI Enterprise `unified_work_system` module (Legacy Core) — ENI Unified Work System Module Use when working with unified_work_system in the Enterprise Platform.
---

# Module skill: unified_work_system

- Category: Legacy Core (priority ?)
- Version: 1.0.0
- Purpose: ENI Unified Work System Module

## What it does
ENI Unified Work System Module

Enterprise-grade module that runs creative, technical/software, and business
work as ONE system — grounded in the JEVanClief one-system thesis.

At the heart of the module is a :class:`WorkSystem` that centers on a single
*artifact* and renders it through multiple *lenses* (creative, technical,
business).  Each lens derives structured facts from the same artifact, and a
lens-consistency check verifies that the lenses are actually telling the same
story (flagging disagreements).  The module also implements the transcript's
memory model: an external AI :class:`MemoryStore` with position/link/content
addressing plus an explicit :class:`HumanMemory` that stays in the loop.

Exports:
  UnifiedWorkSystemModule  — @module-decorated Module subclass
  WorkSystem     

## Key API (facade methods on the @module class)
- check_consistency\n- health_check\n- initialize\n- render\n- set_event_bus\n- shutdown\n- store_memory\n- work_system

## Use
Import via:
```python
from enterprise.modules.unified_work_system import create_unified_work_system_module
m = create_unified_work_system_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/unified_work_system/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.
