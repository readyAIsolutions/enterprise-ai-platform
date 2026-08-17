---
name: eni-module-universal_score
description: Operate the ENI Enterprise `universal_score` module (Legacy Core) — ENI Universal Build Score module. Use when working with universal_score in the Enterprise Platform.
---

# Module skill: universal_score

- Category: Legacy Core (priority ?)
- Version: 1.0.0
- Purpose: ENI Universal Build Score module.

## What it does
ENI Universal Build Score module.

One accurate, industry-grounded build-quality number that tests any real
software build on disk and certifies it. 100 = fully sellable enterprise;
a excellence bonus lets transcendent builds exceed 100 (the singularity band).

This module is the canonical home for build-quality scoring in the platform.
It is the anti-stub: every dimension is computed from real filesystem / code
inspection probes, never hardcoded.

Version: 1.0.0

## Key API (facade methods on the @module class)
(module-level API)

## Use
Import via:
```python
from enterprise.modules.universal_score import create_universal_score_module
m = create_universal_score_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/universal_score/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.
