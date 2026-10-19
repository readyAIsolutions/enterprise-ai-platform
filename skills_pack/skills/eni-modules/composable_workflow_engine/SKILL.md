---
name: eni-module-composable_workflow_engine
description: Operate the ENI Enterprise `composable_workflow_engine` module (Legacy Core) — composable_workflow_engine — a compose-your-own context-engineering Use when working with composable_workflow_engine in the Enterprise Platform.
---

# Module skill: composable_workflow_engine

- Category: Legacy Core (priority ?)
- Version: 1.0.0
- Purpose: composable_workflow_engine — a compose-your-own context-engineering

## What it does
composable_workflow_engine — a compose-your-own context-engineering
workflow engine for the ENI Enterprise Platform.

Grounded ENTIRELY in ColeMedin's "The True Power of AI Coding - Build Your OWN
Workflows (Full Guide)" (https://www.youtube.com/watch?v=mHBk8Z7Exag). AI
coding is about building SYSTEMS/WORKFLOWS, not one-off prompts. Rather than
adopt an existing framework wholesale (PRP, BMAD, GitHub spec-kit), understand
the fundamental PHASES — planning -> implementation -> validation, with context
engineering (RAG, memory, task management, prompt engineering) — and COMPOSE
YOUR OWN. This module provides WorkflowPhase / WorkflowTemplate data structures,
built-in templates mirroring the named frameworks, custom composition, pure
deterministic execution producing a per-phase log, validati

## Key API (facade methods on the @module class)
- all_templates\n- compose\n- describe\n- get_template\n- health_check\n- initialize\n- register_template\n- run\n- set_event_bus\n- shutdown\n- validate_template

## Use
Import via:
```python
from enterprise.modules.composable_workflow_engine import create_composable_workflow_engine_module
m = create_composable_workflow_engine_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/composable_workflow_engine/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.
