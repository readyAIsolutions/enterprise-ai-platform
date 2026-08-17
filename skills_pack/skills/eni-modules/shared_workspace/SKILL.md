---
name: eni-module-shared_workspace
description: Operate the ENI Enterprise `shared_workspace` module (Agent Workflow) — Live multi-editor workspace: lock, merge-safe write, history, redact-before-share. Use when working with shared_workspace in the Enterprise Platform.
---

# Module skill: shared_workspace

- Category: Agent Workflow (priority 2)
- Version: 1.0.0
- Purpose: Live multi-editor workspace: lock, merge-safe write, history, redact-before-share.

## What it does
Shared Workspace module — live multi-editor collaboration (from transcript).

Implements the shared, live, versioned workspace described in the pulled
"Multiplayer AI" transcript: concurrent multi-editor writes with lock + merge
safety, an append-only queryable session history, and siloed/redact-before-share
handling for private values.

## Key API (facade methods on the @module class)
- health_check\n- history\n- initialize\n- list\n- lock\n- query\n- read\n- shutdown\n- unlock\n- write

## Use
Import via:
```python
from enterprise.modules.shared_workspace import create_shared_workspace_module
m = create_shared_workspace_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/shared_workspace/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.
