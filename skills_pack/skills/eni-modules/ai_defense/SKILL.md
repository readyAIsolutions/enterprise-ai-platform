---
name: eni-module-ai_defense
description: Operate the ENI Enterprise `ai_defense` module (Legacy Core) — ENI Enterprise AI Defense OS Module. Use when working with ai_defense in the Enterprise Platform.
---

# Module skill: ai_defense

- Category: Legacy Core (priority ?)
- Version: 1.0.0
- Purpose: ENI Enterprise AI Defense OS Module.

## What it does
ENI Enterprise AI Defense OS Module.

Defense against *AI-driven / automated* attackers: statistical anomaly detection,
bot/agent traffic classification, model-extraction probing shield, credential-
stuffing lockout, and indirect prompt-injection detection. Complements the
``model_security`` module (which guards model *input/output*); this module
guards the *attacker side*.

The module exposes a ``@module``-registered kernel Module
(:class:`AIDefenseModule`) alongside a plain convenience facade
(:class:`AIDefenseFacade`) for direct, dependency-free use.

All components are stdlib-only with zero external dependencies.

## Key API (facade methods on the @module class)
(module-level API)

## Use
Import via:
```python
from enterprise.modules.ai_defense import create_ai_defense_module
m = create_ai_defense_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/ai_defense/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.
