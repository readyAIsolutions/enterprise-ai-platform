---
name: eni-module-compression_bridge
description: Operate the ENI Enterprise `compression_bridge` module (Legacy Core) — Enterprise Platform — Compression Bridge Module v3.0.0 Use when working with compression_bridge in the Enterprise Platform.
---

# Module skill: compression_bridge

- Category: Legacy Core (priority ?)
- Version: 3.0.0
- Purpose: Enterprise Platform — Compression Bridge Module v3.0.0

## What it does
Enterprise Platform — Compression Bridge Module v3.0.0
======================================================

Enterprise-grade compression module bridging the core Compression engine
into the Enterprise Platform OS. Provides:

  - CompressionBridge  — unified API for all 12 compression modes + OMEGA transcendent
  - CompressionHealthCheck — validates all algorithms loadable, OMEGA accessible
  - Events: compression.completed, compression.omega.transcended, compression.algorithm.selected
  - Metrics: compression ratios per mode, throughput, omega efficiency

Architecture:
    __init__.py            — Module housekeeping, @module registration, exports
    compression_bridge.py  — CompressionBridge (compress, decompress, batch,
                              omega_transcend, stats, health_che

## Key API (facade methods on the @module class)
- bridge\n- health_check\n- initialize\n- shutdown

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
