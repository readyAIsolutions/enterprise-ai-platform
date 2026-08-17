---
name: eni-module-safety_governance
description: Operate the ENI Enterprise `safety_governance` module (Legacy Core) — ENI Enterprise — Safety & Governance OS v1.0.0 Use when working with safety_governance in the Enterprise Platform.
---

# Module skill: safety_governance

- Category: Legacy Core (priority ?)
- Version: 1.0.0
- Purpose: ENI Enterprise — Safety & Governance OS v1.0.0

## What it does
ENI Enterprise — Safety & Governance OS v1.0.0
AI Safety, Security, Guardrails, Evaluation, Monitoring, Incident Response.

## Key API (facade methods on the @module class)
- health_check\n- initialize\n- shutdown

## Use
Import via:
```python
from enterprise.modules.safety_governance import create_safety_governance_module
m = create_safety_governance_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/safety_governance/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.
