---
name: eni-module-response_ops
description: Operate the ENI Enterprise `response_ops` module (Legacy Core) — ENI Response Ops Module — self-healing fleet supervisor + ICM routing hook. Use when working with response_ops in the Enterprise Platform.
---

# Module skill: response_ops

- Category: Legacy Core (priority ?)
- Version: 1.0.0
- Purpose: ENI Response Ops Module — self-healing fleet supervisor + ICM routing hook.

## What it does
ENI Response Ops Module — self-healing fleet supervisor + ICM routing hook.

Public surface:

  * :class:`FleetSupervisor` / :func:`create_fleet_supervisor` — the
    self-healing supervisor that probes known local service endpoints and, when
    a service is down, attempts a restart, logging to ``logs/supervisor.log``
    and publishing events on the kernel :class:`EventBus`.
  * :func:`icm_preflight` — a tiny broker-facing hook that imports the ICM
    classifier and returns ``{"route": "sequential" | "swarm",
    "sequential": bool}`` so an orchestration broker can pick an execution lane.
  * :class:`ResponseOpsModule` — the Platform Kernel module wrapper (registered
    via the ``@module`` decorator for auto-discovery).

CLI: ``python3 scripts/fleet_supervisor.py --check`` (one pass) o

## Key API (facade methods on the @module class)
(module-level API)

## Use
Import via:
```python
from enterprise.modules.response_ops import create_response_ops_module
m = create_response_ops_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/response_ops/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.
