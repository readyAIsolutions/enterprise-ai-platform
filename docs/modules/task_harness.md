# Module: `task_harness`

- Category: Legacy Core · priority 55
- Version: 1.0.0
- Purpose: ENI Task Harness OS Module
- Skill: `eni-module-task_harness` (ICM stages) in skills_pack/skills/eni-modules/task_harness/

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

## Key API (facade methods)
harness, health_check, initialize, set_event_bus, shutdown

## Tests
```bash
python3 -m pytest modules/task_harness/tests -q
```

## Import
```python
from enterprise.modules.task_harness import create_task_harness_module
m = create_task_harness_module()
```
