---
name: eni-module-context_routing
description: Operate the ENI Enterprise `context_routing` module (Agent Workflow) — Task -> {read/skip/skills} routing table with token-budget guard. Use when working with context_routing in the Enterprise Platform.
---

# Module skill: context_routing

- Category: Agent Workflow (priority 2)
- Version: 1.0.0
- Purpose: Task -> {read/skip/skills} routing table with token-budget guard.

## What it does
Context Routing module — task→(read/skip/skills) routing with token discipline.

Implements the routing-table + progressive-disclosure principles extracted from
the pulled JE Van Clief transcript "Stop Building AI Agents. Use This Folder
System Instead": tell the agent exactly which files to read and skip for a task,
within a token budget, so it never wastes context or guesses wrong.

Export surface:
  * ContextRouter — the routing table engine.
  * RoutingRule — one task's read/skip/skills/budget rule.
  * example_rules() — a ready-made ruleset (project-doc oriented).

## Key API (facade methods on the @module class)
- budget\n- health_check\n- initialize\n- route\n- shutdown

## Use
Import via:
```python
from enterprise.modules.context_routing import create_context_routing_module
m = create_context_routing_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/context_routing/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.
