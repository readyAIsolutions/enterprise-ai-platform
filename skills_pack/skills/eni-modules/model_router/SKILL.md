---
name: eni-module-model_router
description: Operate the ENI Enterprise `model_router` module (Legacy Core) — ENI Model Router OS Module — enterprise model-routing / fallback gateway. Use when working with model_router in the Enterprise Platform.
---

# Module skill: model_router

- Category: Legacy Core (priority ?)
- Version: 1.0.0
- Purpose: ENI Model Router OS Module — enterprise model-routing / fallback gateway.

## What it does
ENI Model Router OS Module — enterprise model-routing / fallback gateway.

A production-grade, stdlib-only model-routing gateway ripped from the LiteLLM
retry/cooldown pattern. It manages a fleet of model deployments, selects healthy
ones per request via weighted (hash-bucket) selection, retries transient
failures per a per-exception-type policy, and falls back across a model group —
placing failing deployments into a time-based cooldown so they are excluded
from dispatch until they recover.

All components are stdlib-only (zero external dependencies beyond the kernel).

## Key API (facade methods on the @module class)
(module-level API)

## Use
Import via:
```python
from enterprise.modules.model_router import create_model_router_module
m = create_model_router_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/model_router/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.
