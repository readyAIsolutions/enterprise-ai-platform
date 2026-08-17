---
name: eni-module-prd_audit
description: Operate the ENI Enterprise `prd_audit` module (Legacy Core) — prd_audit — PRD-gated build workflow: write the PRD, audit it with a second Use when working with prd_audit in the Enterprise Platform.
---

# Module skill: prd_audit

- Category: Legacy Core (priority ?)
- Version: 1.0.0
- Purpose: prd_audit — PRD-gated build workflow: write the PRD, audit it with a second

## What it does
prd_audit — PRD-gated build workflow: write the PRD, audit it with a second
instance, then gate execution until it clears a threshold. Grounded in
JEVanClief's "I'm Building a Custom Front End for Claude Code" (J2GLzkaUrBc).

## Key API (facade methods on the @module class)
- audit\n- audit_markdown\n- gate\n- gate_document\n- gate_markdown\n- health_check\n- initialize\n- parse_prd\n- set_event_bus\n- shutdown

## Use
Import via:
```python
from enterprise.modules.prd_audit import create_prd_audit_module
m = create_prd_audit_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/prd_audit/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.
