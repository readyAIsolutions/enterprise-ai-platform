---
name: eni-module-release_change
description: Operate the ENI Enterprise `release_change` module (Legacy Core) — Release & Change Management OS Module Use when working with release_change in the Enterprise Platform.
---

# Module skill: release_change

- Category: Legacy Core (priority ?)
- Version: 1.0.0
- Purpose: Release & Change Management OS Module

## What it does
Release & Change Management OS Module

Enterprise-grade release and change management for the ENI platform.
Manages the full lifecycle of changes: classification, workflow,
deployment strategies, quality gates, and deliverables.

Supports:
  - Structured change workflows with 14 stages
  - Risk-based classification (13 change types, 4 risk levels)
  - 8 deployment strategies (canary, blue-green, staged rollout, etc.)
  - 10 quality gate checks
  - 10 deliverable types for compliance and audit readiness

Version: 1.0.0

## Key API (facade methods on the @module class)
- health_check\n- initialize\n- shutdown

## Use
Import via:
```python
from enterprise.modules.release_change import create_release_change_module
m = create_release_change_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/release_change/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.
