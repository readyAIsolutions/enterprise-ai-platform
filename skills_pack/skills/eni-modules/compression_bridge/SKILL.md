---
name: eni-module-compression_bridge
description: Operate the ENI Enterprise `compression_bridge` module (Legacy Core) — compression_bridge platform module. Use when working with compression_bridge in the Enterprise Platform.
---

# Module skill: compression_bridge

- Category: Legacy Core (priority ?)
- Version: 0.0.0
- Purpose: compression_bridge platform module.

## What it does
compression_bridge platform module.

## Key API (facade methods on the @module class)
(module-level API)

## Use
Import via:
```python
from enterprise.modules.compression_bridge import create_compression_bridge_module
m = create_compression_bridge_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/compression_bridge/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.
