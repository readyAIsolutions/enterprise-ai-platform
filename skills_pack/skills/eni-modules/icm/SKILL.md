---
name: eni-module-icm
description: Operate the ENI Enterprise `icm` module (Legacy Core) — ICM (Interpretable Context Methodology) — skill/prompt-engineering layer. Use when working with icm in the Enterprise Platform.
---

# Module skill: icm

- Category: Legacy Core (priority ?)
- Version: 1.0.0
- Purpose: ICM (Interpretable Context Methodology) — skill/prompt-engineering layer.

## What it does
ICM (Interpretable Context Methodology) — skill/prompt-engineering layer.

Registers the ICM engine as a first-class Platform Kernel module so the rest of
the stack can:
  * scaffold standard numbered-stage skill projects,
  * route a task to the correct stage folder via 00_master.md,
  * load ONLY the current stage's markdown (progressive disclosure → lighter
    token spend per OpenRouter / swarm call),
  * classify whether a task belongs in deterministic sequential ICM work or in
    the concurrent multi-agent swarm layer (division of labor, spec §3).

This is the prompt-engineering discipline layer: orchestration decides WHICH
agent runs a task; ICM governs HOW that single agent structures its execution.

## Key API (facade methods on the @module class)
- health_check\n- initialize\n- new_project\n- route\n- shutdown\n- stage_context

## Use
Import via:
```python
from enterprise.modules.icm import create_icm_module
m = create_icm_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/icm/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.
