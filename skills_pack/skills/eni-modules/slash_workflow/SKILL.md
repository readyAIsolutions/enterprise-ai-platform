---
name: eni-module-slash_workflow
description: Operate the ENI Enterprise `slash_workflow` module (Legacy Core) — slash_workflow — Plan->Implement->Validate AI-coding workflow with reusable markdown slash-commands, a plan-document schema, isolated-context sub-agents, a dete Use when working with slash_workflow in the Enterprise Platform.
---

# Module skill: slash_workflow

- Category: Legacy Core (priority ?)
- Version: 1.0.0
- Purpose: slash_workflow — Plan->Implement->Validate AI-coding workflow with reusable markdown slash-commands, a plan-document schema, isolated-context sub-agents, a dete

## What it does
slash_workflow — Plan->Implement->Validate AI-coding workflow with reusable markdown slash-commands, a plan-document schema, isolated-context sub-agents, a deterministic task cycle, and CLAUDE.md-style cascading global rules. Grounded in ColeMedin's "The True Power of AI Coding - Build Your OWN Workflows" (https://www.youtube.com/watch?v=mHBk8Z7Exag).

## Key API (facade methods on the @module class)
- health_check\n- initialize\n- render_command\n- run_workflow\n- shutdown\n- validate_plan

## Use
Import via:
```python
from enterprise.modules.slash_workflow import create_slash_workflow_module
m = create_slash_workflow_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/slash_workflow/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.
