---
name: eni-module-enterprise_validation
description: Operate the ENI Enterprise `enterprise_validation` module (Legacy Core) — Enterprise Validation & Certification OS — Module Entry Point Use when working with enterprise_validation in the Enterprise Platform.
---

# Module skill: enterprise_validation

- Category: Legacy Core (priority ?)
- Version: 1.0.0
- Purpose: Enterprise Validation & Certification OS — Module Entry Point

## What it does
Enterprise Validation & Certification OS — Module Entry Point
==============================================================

@module(name='enterprise_validation', version='1.0.0')

## Key API (facade methods on the @module class)
- engine\n- health_check\n- initialize\n- shutdown\n- validate_all\n- validate_module

## Use
Import via:
```python
from enterprise.modules.enterprise_validation import create_enterprise_validation_module
m = create_enterprise_validation_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/enterprise_validation/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.
