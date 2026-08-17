# Module: `context_routing`

- Category: Agent Workflow · priority 2
- Version: 1.0.0
- Purpose: Task -> {read/skip/skills} routing table with token-budget guard.
- Skill: `eni-module-context_routing` (ICM stages) in skills_pack/skills/eni-modules/context_routing/

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

## Key API (facade methods)
budget, health_check, initialize, route, shutdown

## Tests
```bash
python3 -m pytest modules/context_routing/tests -q
```

## Import
```python
from enterprise.modules.context_routing import create_context_routing_module
m = create_context_routing_module()
```
