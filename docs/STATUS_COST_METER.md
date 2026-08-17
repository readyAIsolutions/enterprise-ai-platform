# STATUS — Cost Meter (B3 per-tenant metering + C4 fractional reasoning)

**Date:** 2026-08-16
**Module:** `modules/cost_meter/` (NEW)
**Branch:** upgrade/demiurge-enterprise-boost (feature commit, local)

## What shipped

Upgrades B3 (per-tenant cost metering + budget guards) and C4 (fractional
reasoning — the escalation ladder as a feature) as a single first-class,
auto-discovered Platform Kernel module. No edits to `multiplayer/server/*.py`,
`licensing/*.py`, or `model_router/*` — all logic lives in the new module.

### 1. TenantMeter  (`modules/cost_meter/cost_meter.py`) — B3
- Per-tenant token/cost accumulators, isolated per tenant.
- `add(tenant, tokens, cost)` — verbose/cumulative metering (feeds C2 live BI),
  no budget enforcement.
- `spend(tenant, tokens, cost)` — **budget-enforced**: rejects a spend whose
  projected cost would exceed the tenant's monthly budget and returns
  `allowed: False` with `remaining` (the rejected spend mutates nothing).
  Exact-boundary spends are allowed; tenants without a budget are unlimited.
- `set_budget`, `remaining`, `summary`, `tenants`, `total`.
- **Persistence:** single JSON ledger, default `data/cost_meter.json`,
  written **atomically** (temp-file + `os.replace`, with `fsync`), so a crash
  mid-write never leaves a corrupt file. Rolls totals over when the
  `YYYY-MM` budget period changes.

### 2. Policy  (`Policy.from_config`) — C4
- Maps task class -> model tier. Default mapping:
  - `sequential` / `icm`  -> `cheap`      (deterministic ICM work pins to the cheapest model)
  - `swarm` / `judgment`  -> `frontier`   (judgment work may escalate)
  - unknown class -> `default_tier` (`cheap`).
- Fully configurable via `config={"by_class": {...}, "default_tier": ...}`;
  rejects unknown tiers.
- `resolve_task(task)` classifies a raw task (prefers the platform ICM
  classifier, falls back to a local keyword classifier) and returns
  `{task_class, tier}`.

## Tests — `modules/cost_meter/tests/test_cost_meter.py`  (12 tests, all green)

Proving the exact required behaviours:
- meter accumulates tokens/cost and isolates tenants;
- meter persists + reloads atomically (no stray tmp files);
- **within-budget spend -> `allowed: True`**;
- **over-budget spend -> `allowed: False`** and leaves the ledger untouched;
- unlimited-budget tenant always spends;
- policy pins **`sequential`/`icm` -> `cheap`**, **`swarm`/`judgment` -> `frontier`**;
- **compliance task -> `cheap`** and **legal-reasoning task -> `frontier`**;
- module registers, initializes, and its facade (set_budget/add_usage/spend/
  tier_for/resolve) round-trips a persisted ledger.

```
modules/cost_meter/tests/test_cost_meter.py .............. 12 passed in 0.05s
```

## Files
- `modules/cost_meter/cost_meter.py`      — TenantMeter + Policy (stdlib only)
- `modules/cost_meter/__init__.py`        — kernel module + facade (`CostMeterModule`,
  `create_cost_meter_module`)
- `modules/cost_meter/tests/test_cost_meter.py`
- `data/cost_meter.json`                  — runtime-persisted ledger (auto-created)

## Notes / issues
- `enterprise` package name resolves only through `conftest.py` (parent dir on
  `sys.path`) in this workspace layout; standalone scripts need
  `PYTHONPATH=".."`. All tests run green under pytest. Inherited environment
  quirk, not a code defect.
- Module is auto-discovered by the kernel (`@module` decorator, verified in a
  full modules sweep — `cost_meter` present with zero kernel edits).
