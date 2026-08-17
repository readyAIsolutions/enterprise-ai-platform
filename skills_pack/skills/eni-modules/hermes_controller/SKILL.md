---
name: eni-module-hermes_controller
description: Operate the ENI Enterprise `hermes_controller` module (Legacy Core) — Enterprise Hermes Controller OS Module — autonomous controller for Hermes Agent. Use when working with hermes_controller in the Enterprise Platform.
---

# Module skill: hermes_controller

- Category: Legacy Core (priority ?)
- Version: 1.0.0
- Purpose: Enterprise Hermes Controller OS Module — autonomous controller for Hermes Agent.

## What it does
Enterprise Hermes Controller OS Module — autonomous controller for Hermes Agent.

A stdlib-only facade that wraps the ENI Hermes Controller (prompt expander +
router + privacy boundary + reinforcement). Exposes it to the enterprise
platform so every build can:
  - expand LO's short instructions into massive detailed prompts,
  - sanitize secrets on egress (cloud never sees private data),
  - auto-continue through free-model rate limits,
  - queue work for deferred continuation (e.g. 6pm local),
  - retain good outcomes to the KB and build skills.

All components are stdlib-only with zero external dependencies.

## Key API (facade methods on the @module class)
- facade\n- health_check\n- initialize\n- shutdown

## Use
Import via:
```python
from enterprise.modules.hermes_controller import create_hermes_controller_module
m = create_hermes_controller_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/hermes_controller/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.
