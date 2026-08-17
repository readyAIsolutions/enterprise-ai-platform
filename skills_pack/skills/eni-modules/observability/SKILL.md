---
name: eni-module-observability
description: Operate the ENI Enterprise `observability` module (Legacy Core) — Observability — real, consolidated fleet health + Prometheus export. Use when working with observability in the Enterprise Platform.
---

# Module skill: observability

- Category: Legacy Core (priority ?)
- Version: 1.0.0
- Purpose: Observability — real, consolidated fleet health + Prometheus export.

## What it does
Observability — real, consolidated fleet health + Prometheus export.

A1 upgrade: replaces the old "health is a scored number" fiction with a live map
of what is ACTUALLY healthy right now. Provides:

* FleetHealthAggregator — probes each registered platform module's
  health_check() plus a set of external service endpoints (the multiplayer
  server, controller, dashboard, free router) and returns a live snapshot with
  per-entity status and a count summary. All real probes, no invented scores.
* Prometheus exporter — one text/metrics endpoint that surfaces counts and
  per-module up/down in the standard Prometheus exposition format, so existing
  :9090 tooling (and the dashboard) can ingest real numbers.

This is the "verified truth, not claims" layer: the dashboard reads this, never
a ha

## Key API (facade methods on the @module class)
- bind_registry\n- health_check\n- initialize\n- metrics\n- shutdown\n- snapshot

## Use
Import via:
```python
from enterprise.modules.observability import create_observability_module
m = create_observability_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/observability/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.
