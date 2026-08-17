# Module: `compression_bridge`

- Category: Legacy Core · priority 19
- Version: 3.0.0
- Purpose: Enterprise Platform — Compression Bridge Module v3.0.0
- Skill: `eni-module-compression_bridge` (ICM stages) in skills_pack/skills/eni-modules/compression_bridge/

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
                              omega_transcend, stats, health_check)
    tests/test_compression.py — 40+ production-quality tests

## Key API (facade methods)
bridge, health_check, initialize, shutdown

## Tests
```bash
python3 -m pytest modules/compression_bridge/tests -q
```

## Import
```python
from enterprise.modules.compression_bridge import create_compression_bridge_module
m = create_compression_bridge_module()
```
