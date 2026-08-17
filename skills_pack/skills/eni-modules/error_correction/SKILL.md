---
name: eni-module-error_correction
description: Operate the ENI Enterprise `error_correction` module (Legacy Core) — error_correction platform module. Use when working with error_correction in the Enterprise Platform.
---

# Module skill: error_correction

- Category: Legacy Core (priority ?)
- Version: 0.0.0
- Purpose: error_correction platform module.

## What it does
error_correction platform module.

## Key API (facade methods on the @module class)
(module-level API)

## Use
Import via:
```python
from enterprise.modules.error_correction import create_error_correction_module
m = create_error_correction_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/error_correction/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.
