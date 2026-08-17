---
name: eni-module-task_harness
description: Operate the ENI Enterprise `task_harness` module (Legacy Core) — ENI Task Harness OS Module Use when working with task_harness in the Enterprise Platform.
---

# Module skill: task_harness

- Category: Legacy Core (priority ?)
- Version: 1.0.0
- Purpose: ENI Task Harness OS Module

## What it does
ENI Task Harness OS Module

Maestro-style long-running task harness: SQLite-backed task cards with
pause/resume, dependency ordering, priority scheduling, heartbeat liveness,
and structured state so an agent can pause, resume, and track deep refactors.

Exports:
  TaskHarnessModule — @module-decorated Module subclass
  TaskHarness       — SQLite-backed task store
  TaskCard          — task card dataclass
  TaskStatus        — lifecycle enum
  TaskHarnessError  — base error for the module

Version: 1.0.0
Python: 3.10+

## Key API (facade methods on the @module class)
- harness\n- health_check\n- initialize\n- set_event_bus\n- shutdown

## Use
Import via:
```python
from enterprise.modules.task_harness import create_task_harness_module
m = create_task_harness_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/task_harness/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.
