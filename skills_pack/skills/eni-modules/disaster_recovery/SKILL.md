---
name: eni-module-disaster_recovery
description: Operate the ENI Enterprise `disaster_recovery` module (Legacy Core) — Disaster Recovery OS Module Use when working with disaster_recovery in the Enterprise Platform.
---

# Module skill: disaster_recovery

- Category: Legacy Core (priority ?)
- Version: 1.0.0
- Purpose: Disaster Recovery OS Module

## What it does
Disaster Recovery OS Module

Enterprise-grade disaster recovery, business continuity, and crisis management.
Covers backup, recovery, cyber recovery, AI continuity, exercises, and crisis coordination.

Version: 1.0.0

## Key API (facade methods on the @module class)
- health_check\n- initialize\n- shutdown

## Use
Import via:
```python
from enterprise.modules.disaster_recovery import create_disaster_recovery_module
m = create_disaster_recovery_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/disaster_recovery/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.
