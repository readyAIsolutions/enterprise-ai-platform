---
name: eni-module-ai_coding_workflow
description: Operate the ENI Enterprise `ai_coding_workflow` module (Legacy Core) — ai_coding_workflow — a framework-agnostic, 3-phase AI-coding workflow Use when working with ai_coding_workflow in the Enterprise Platform.
---

# Module skill: ai_coding_workflow

- Category: Legacy Core (priority ?)
- Version: 1.0.0
- Purpose: ai_coding_workflow — a framework-agnostic, 3-phase AI-coding workflow

## What it does
ai_coding_workflow — a framework-agnostic, 3-phase AI-coding workflow
engine for the ENI Enterprise Platform.

Grounded in ColeMedin's "The True Power of AI Coding - Build Your OWN
Workflows" (https://www.youtube.com/watch?v=mHBk8Z7Exag). The workflow runs
REQUIREMENTS -> PLAN -> EXECUTE -> VALIDATE -> COMPLETE: a codebase-analyst
research step builds a granular task plan, a per-task state machine cycles
each task TODO->DOING->REVIEW->DONE one at a time (to prevent hallucination),
and a validation gate generates tests + a human code-review step that can
reopen tasks. Works with PRP / BMAD / spec-kit / plain markdown.

## Key API (facade methods on the @module class)
- advance_task\n- create_plan\n- create_workflow\n- get_workflow\n- health_check\n- initialize\n- progress\n- render\n- set_event_bus\n- set_requirements\n- shutdown\n- start_task\n- summary\n- validate

## Use
Import via:
```python
from enterprise.modules.ai_coding_workflow import create_ai_coding_workflow_module
m = create_ai_coding_workflow_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/ai_coding_workflow/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.
