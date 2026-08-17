---
name: eni-module-cost_meter
description: Operate the ENI Enterprise `cost_meter` module (Legacy Core) — Cost Meter — per-tenant cost metering + fractional-reasoning policy (B3 + C4). Use when working with cost_meter in the Enterprise Platform.
---

# Module skill: cost_meter

- Category: Legacy Core (priority ?)
- Version: 1.0.0
- Purpose: Cost Meter — per-tenant cost metering + fractional-reasoning policy (B3 + C4).

## What it does
Cost Meter — per-tenant cost metering + fractional-reasoning policy (B3 + C4).

Registers itself as a first-class Platform Kernel module so the rest of the
stack can:

  * meter tokens/cost per tenant (via :class:`TenantMeter`) and enforce a
    monthly budget — rejecting spends that would bust the quota,
  * map a task class (sequential/icm vs swarm/judgment) to a model tier
    (cheap vs frontier) via :class:`Policy`, so deterministic ICM work is
    pinned to the cheapest model and judgment work may escalate.

Both capabilities are plain, stdlib-only objects living in
:mod:`enterprise.modules.cost_meter.cost_meter`; this package exposes them as a
kernel module with an initialize / health_check / shutdown lifecycle and a
thin always-available facade.

## Key API (facade methods on the @module class)
- add_usage\n- health_check\n- initialize\n- meter\n- policy\n- remaining\n- resolve\n- set_budget\n- shutdown\n- spend\n- tier_for

## Use
Import via:
```python
from enterprise.modules.cost_meter import create_cost_meter_module
m = create_cost_meter_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/cost_meter/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.
