# Module: `observability`

- Category: Legacy Core · priority 39
- Version: 1.0.0
- Purpose: Observability — real, consolidated fleet health + Prometheus export.
- Skill: `eni-module-observability` (ICM stages) in skills_pack/skills/eni-modules/observability/

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
a hard-coded score.

## Key API (facade methods)
bind_registry, health_check, initialize, metrics, shutdown, snapshot

## Tests
```bash
python3 -m pytest modules/observability/tests -q
```

## Import
```python
from enterprise.modules.observability import create_observability_module
m = create_observability_module()
```
