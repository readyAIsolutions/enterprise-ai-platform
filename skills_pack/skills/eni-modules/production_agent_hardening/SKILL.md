---
name: eni-module-production_agent_hardening
description: Operate the ENI Enterprise `production_agent_hardening` module (Build Quality) — Demo->production hardening linter across 8 scored dimensions + systems loops. Use when working with production_agent_hardening in the Enterprise Platform.
---

# Module skill: production_agent_hardening

- Category: Build Quality (priority 3)
- Version: 1.0.0
- Purpose: Demo->production hardening linter across 8 scored dimensions + systems loops.

## What it does
Production Agent Hardening module — ship a demo agent that survives production.

Implements the production-readiness lessons from two pulled JE Van Clief
transcripts:

  * "Two Engineers on Why Your Agent Demo Will Not Survive Production"
    — observability ("understand how things are running"), error handling,
      retries, secrets, cost bounds, and the "demo trap" of canned/hardcoded
      behavior that does not generalize.

  * "Systems Thinking for People Who Build With AI"
    — a systems lens (feedback loops, coupling, emergent behavior) on why
      ~95% of agentic AI initiatives never make real-world impact (as cited
      from MIT Project Nanda), and how to reason about the whole system
      rather than only the happy path.

Export surface:
  * harden_spec — score an agent spec

## Key API (facade methods on the @module class)
- harden\n- health_check\n- initialize\n- readiness\n- shutdown\n- systems

## Use
Import via:
```python
from enterprise.modules.production_agent_hardening import create_production_agent_hardening_module
m = create_production_agent_hardening_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/production_agent_hardening/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.
