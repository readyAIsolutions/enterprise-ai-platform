# Module: `agentic_workflow_builder`

- Category: Legacy Core · priority 13
- Version: 1.0.0
- Purpose: agentic_workflow_builder — compose agentic workflows (Claude Code + Cursor).
- Skill: `eni-module-agentic_workflow_builder` (ICM stages) in skills_pack/skills/eni-modules/agentic_workflow_builder/

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
:mod:`enterprise.modules.agentic_workflow_builder.agentic_workflow_builder`
(``AgentSpec``, ``Workflow``, ``ParsedStatement``, ``build_workflow``,
``create_todo_list``, ``decompose_module``, ``estimate_cost``,
``statement_matches``, ``workflow_stats``); this package registers it as an
enterprise module with an initialize / health_check / shutdown lifecycle and a
thin facade.

## Key API (facade methods)
compose_workflow, cost, create_agent, health_check, initialize, make_statement, make_todo_list, set_event_bus, shutdown, split_monolith, stats

## Tests
```bash
python3 -m pytest modules/agentic_workflow_builder/tests -q
```

## Import
```python
from enterprise.modules.agentic_workflow_builder import create_agentic_workflow_builder_module
m = create_agentic_workflow_builder_module()
```
