---
name: eni-module-swarm_network
description: Operate the ENI Enterprise `swarm_network` module (Legacy Core) — Swarm Network Optimization OS — Enterprise Module Use when working with swarm_network in the Enterprise Platform.
---

# Module skill: swarm_network

- Category: Legacy Core (priority ?)
- Version: 2.0.0
- Purpose: Swarm Network Optimization OS — Enterprise Module

## What it does
Swarm Network Optimization OS — Enterprise Module
==================================================
Enterprise-grade connection multiplexer for maximum agent concurrency.
Integrates the Swarm Turbocharger proxy as a first-class enterprise module.
The registered module name is 'swarm_network' (registered exactly ONCE at the
class definition via the @module decorator).

Capabilities:
  - 5-layer connection optimization (kernel TCP, token bucket, pooling, pacing, health)
  - Aggressive concurrency tiers: 80 max at -48 dBm, 50 at -59 dBm
  - Turbo mode: overrides conservative limits for burst workloads
  - Auto-discovery of Turbocharger proxy
  - Real-time metrics and health monitoring
  - Graceful degradation on WiFi drops

## Key API (facade methods on the @module class)
- bridge\n- health_check\n- initialize\n- shutdown

## Use
Import via:
```python
from enterprise.modules.swarm_network import create_swarm_network_module
m = create_swarm_network_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/swarm_network/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.
