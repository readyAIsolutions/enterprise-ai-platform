---
name: eni-module-prompt_guard
description: Operate the ENI Enterprise `prompt_guard` module (Legacy Core) — Enterprise Prompt Guard OS Module — injection / jailbreak / policy guarding. Use when working with prompt_guard in the Enterprise Platform.
---

# Module skill: prompt_guard

- Category: Legacy Core (priority ?)
- Version: 1.0.0
- Purpose: Enterprise Prompt Guard OS Module — injection / jailbreak / policy guarding.

## What it does
Enterprise Prompt Guard OS Module — injection / jailbreak / policy guarding.

A stdlib-only facade that inspects an inbound prompt and returns a
:class:`GuardVerdict` deciding whether it may proceed to a model. Chains
prompt-injection detection, jailbreak detection and declarative policy
enforcement in short-circuit order, and records every decision in an
append-only :class:`AuditLog`.

All components are stdlib-only with zero external dependencies.

## Key API (facade methods on the @module class)
(module-level API)

## Use
Import via:
```python
from enterprise.modules.prompt_guard import create_prompt_guard_module
m = create_prompt_guard_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/prompt_guard/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.
