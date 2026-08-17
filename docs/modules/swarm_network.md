# Module: `swarm_network`

- Category: Legacy Core · priority 63
- Version: 2.0.0
- Purpose: Swarm Network Optimization OS — Enterprise Module
- Skill: `eni-module-swarm_network` (ICM stages) in skills_pack/skills/eni-modules/swarm_network/

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

## Key API (facade methods)
bridge, health_check, initialize, shutdown

## Tests
```bash
python3 -m pytest modules/swarm_network/tests -q
```

## Import
```python
from enterprise.modules.swarm_network import create_swarm_network_module
m = create_swarm_network_module()
```
