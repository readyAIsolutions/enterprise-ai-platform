---
name: eni-module-customer_experience
description: Operate the ENI Enterprise `customer_experience` module (Legacy Core) — Customer Experience OS Module. Use when working with customer_experience in the Enterprise Platform.
---

# Module skill: customer_experience

- Category: Legacy Core (priority ?)
- Version: 1.0.0
- Purpose: Customer Experience OS Module.

## What it does
Customer Experience OS Module.

Provides a comprehensive suite for managing the end-to-end customer journey,
including journey mapping, support ticketing, AI-assisted support guardrails,
CX metrics, feedback analysis, and communication templates.

Version: 1.0.0

## Key API (facade methods on the @module class)
- health_check\n- initialize\n- shutdown

## Use
Import via:
```python
from enterprise.modules.customer_experience import create_customer_experience_module
m = create_customer_experience_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/customer_experience/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.
