---
name: eni-module-agentic_workflow_builder
description: Operate the ENI Enterprise `agentic_workflow_builder` module (Legacy Core) — agentic_workflow_builder — compose agentic workflows (Claude Code + Cursor). Use when working with agentic_workflow_builder in the Enterprise Platform.
---

# Module skill: agentic_workflow_builder

- Category: Legacy Core (priority ?)
- Version: 1.0.0
- Purpose: agentic_workflow_builder — compose agentic workflows (Claude Code + Cursor).

## What it does
agentic_workflow_builder — compose agentic workflows (Claude Code + Cursor).

Grounded in the JEVanClief transcript *"Claude Code + Cursor: Making Agentic
workflows with an Agentic workflow!"*
(https://www.youtube.com/watch?v=v2UnNFmkia0). The speaker builds a multi-agent
pipeline by running Claude Code (CLI or Cursor plugin) inside WSL/PowerShell,
authoring ``.md`` system-prompt files, composing sections of parser/auditor/
framework-loader agents, modelling parsed compliance statements with a
Pydantic-style schema (``ParsedStatement``), generating agent to-do lists before
editing, refactoring a monolithic ``massive.py`` into modules that initiate from
each other, and estimating cost from token usage.

The deterministic, stdlib-only core lives in
:mod:`enterprise.modules.agentic_workflow_b

## Key API (facade methods on the @module class)
- compose_workflow\n- cost\n- create_agent\n- health_check\n- initialize\n- make_statement\n- make_todo_list\n- set_event_bus\n- shutdown\n- split_monolith\n- stats

## Use
Import via:
```python
from enterprise.modules.agentic_workflow_builder import create_agentic_workflow_builder_module
m = create_agentic_workflow_builder_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/agentic_workflow_builder/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.
