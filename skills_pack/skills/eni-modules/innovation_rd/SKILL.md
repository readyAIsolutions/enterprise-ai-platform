---
name: eni-module-innovation_rd
description: Operate the ENI Enterprise `innovation_rd` module (Legacy Core) — Innovation R&D OS Module Use when working with innovation_rd in the Enterprise Platform.
---

# Module skill: innovation_rd

- Category: Legacy Core (priority ?)
- Version: 1.0.0
- Purpose: Innovation R&D OS Module

## What it does
Innovation R&D OS Module

Enterprise-grade innovation and research & development management system.
Provides tools for research tracking, experiment management, integrity checks,
sandboxed environments, technology scouting, and IP management.

Version: 1.0.0

## Key API (facade methods on the @module class)
- health_check\n- initialize\n- shutdown

## Use
Import via:
```python
from enterprise.modules.innovation_rd import create_innovation_rd_module
m = create_innovation_rd_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/innovation_rd/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.
