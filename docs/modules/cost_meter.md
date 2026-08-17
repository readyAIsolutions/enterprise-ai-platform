# Module: `cost_meter`

- Category: Legacy Core · priority 20
- Version: 1.0.0
- Purpose: Cost Meter — per-tenant cost metering + fractional-reasoning policy (B3 + C4).
- Skill: `eni-module-cost_meter` (ICM stages) in skills_pack/skills/eni-modules/cost_meter/

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

## Key API (facade methods)
add_usage, health_check, initialize, meter, policy, remaining, resolve, set_budget, shutdown, spend, tier_for

## Tests
```bash
python3 -m pytest modules/cost_meter/tests -q
```

## Import
```python
from enterprise.modules.cost_meter import create_cost_meter_module
m = create_cost_meter_module()
```
