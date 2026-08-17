---
name: eni-module-custom_agent_workflows
description: Operate the ENI Enterprise `custom_agent_workflows` module (Legacy Core) — custom_agent_workflows — build your OWN AI coding workflows as a module. Use when working with custom_agent_workflows in the Enterprise Platform.
---

# Module skill: custom_agent_workflows

- Category: Legacy Core (priority ?)
- Version: 1.0.0
- Purpose: custom_agent_workflows — build your OWN AI coding workflows as a module.

## What it does
custom_agent_workflows — build your OWN AI coding workflows as a module.

Grounded in the Cole Medin transcript *"The True Power of AI Coding — Build
Your OWN Workflows (Full Guide)"* (https://www.youtube.com/watch?v=mHBk8Z7Exag):
creating AI coding systems is far more than prompts — it is about building
reusable workflows (plan -> implement -> validate) composed of global rules,
slash commands, and subagents that can evolve to fit your needs.

The deterministic core lives in
:mod:`enterprise.modules.custom_agent_workflows.custom_agent_workflows`
(``CodingWorkflow``, ``TaskManager``, ``WorkflowPlan``, ``Task``, ``SubAgent``,
``build_initial_md``, ``build_plan``, ``validate_plan``, ``validate_code``,
``research_codebase`` and the slash-command builders). This package registers
it as a Platf

## Key API (facade methods on the @module class)
- build_initial_md\n- execute\n- health_check\n- initialize\n- plan\n- primer\n- research_codebase\n- set_event_bus\n- shutdown\n- stats\n- validate_code\n- validate_plan

## Use
Import via:
```python
from enterprise.modules.custom_agent_workflows import create_custom_agent_workflows_module
m = create_custom_agent_workflows_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/custom_agent_workflows/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.
