---
name: eni-module-production_hardening
description: Operate the ENI Enterprise `production_hardening` module (Build Quality) — Operational hardening checks for shipping an agent into production. Use when working with production_hardening in the Enterprise Platform.
---

# Module skill: production_hardening

- Category: Build Quality (priority 3)
- Version: 1.0.0
- Purpose: Operational hardening checks for shipping an agent into production.

## What it does
Production Hardening module — production-readiness for ML / agent systems.

Grounded in the real pulled JE Van Clief transcript
"data/transcripts/JEVanClief/ezRtp6K6zwE.md" — "Two Engineers on Why Your
Agent Demo Will Not Survive Production" — a 57-minute NLP Logix interview
with Anton Corner (Director of Data & AI Engineering) and Ryan Nent
(Software Engineer).  The episode's thesis is that a demo and a sustained
production system live under different constraints: the invisible 80% of
the work (governance, monitoring, runtime, databases, monitoring tooling)
is what makes a system operate reliably, and shipping a one-off demo
over-enthusiastically is exactly how production fails.

Export surface:
  * ProductionReadinessRule / ReadinessReport / SystemProfile — data model.
  * assess() / ass

## Key API (facade methods on the @module class)
- assess\n- assess_answers\n- breaker\n- categories\n- check_determinism\n- check_drift\n- escalation\n- health_check\n- initialize\n- retry\n- rules\n- set_event_bus\n- shutdown

## Use
Import via:
```python
from enterprise.modules.production_hardening import create_production_hardening_module
m = create_production_hardening_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/production_hardening/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.
