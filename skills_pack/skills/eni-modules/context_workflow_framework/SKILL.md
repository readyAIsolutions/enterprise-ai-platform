---
name: eni-module-context_workflow_framework
description: Operate the ENI Enterprise `context_workflow_framework` module (Legacy Core) — context_workflow_framework — build-your-own context-engineering workflow Use when working with context_workflow_framework in the Enterprise Platform.
---

# Module skill: context_workflow_framework

- Category: Legacy Core (priority ?)
- Version: 1.0.0
- Purpose: context_workflow_framework — build-your-own context-engineering workflow

## What it does
context_workflow_framework — build-your-own context-engineering workflow
framework for the ENI Enterprise Platform.

Grounded ENTIRELY in ColeMedin's "The True Power of AI Coding - Build Your
OWN Workflows (Full Guide)" (https://www.youtube.com/watch?v=mHBk8Z7Exag).
AI coding is about building REUSABLE WORKFLOWS/SYSTEMS, not one-off prompts.
Existing frameworks (PRP = Product Requirement Prompt, BMAD, GitHub spec-kit)
share one philosophy: scope the task, gather and assemble context (docs,
examples, rules), plan, implement, validate. Understand that structure and
COMPOSE YOUR OWN. This module exposes WorkflowPhase / WorkflowFramework /
ContextAssembler plus named built-in templates (prp/bmad/spec_kit).

## Key API (facade methods on the @module class)
- health_check\n- initialize\n- load_template\n- phase_names\n- render\n- set_event_bus\n- shutdown\n- validate_context

## Use
Import via:
```python
from enterprise.modules.context_workflow_framework import create_context_workflow_framework_module
m = create_context_workflow_framework_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/context_workflow_framework/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.
