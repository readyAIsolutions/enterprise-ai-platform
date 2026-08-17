# Module: `slash_workflow`

- Category: Legacy Core · priority 61
- Version: 1.0.0
- Purpose: slash_workflow — Plan->Implement->Validate AI-coding workflow with reusable markdown slash-commands, a plan-document schema, isolated-context sub-agents, a dete
- Skill: `eni-module-slash_workflow` (ICM stages) in skills_pack/skills/eni-modules/slash_workflow/

## What it does
slash_workflow — Plan->Implement->Validate AI-coding workflow with reusable markdown slash-commands, a plan-document schema, isolated-context sub-agents, a deterministic task cycle, and CLAUDE.md-style cascading global rules. Grounded in ColeMedin's "The True Power of AI Coding - Build Your OWN Workflows" (https://www.youtube.com/watch?v=mHBk8Z7Exag).

## Key API (facade methods)
health_check, initialize, render_command, run_workflow, shutdown, validate_plan

## Tests
```bash
python3 -m pytest modules/slash_workflow/tests -q
```

## Import
```python
from enterprise.modules.slash_workflow import create_slash_workflow_module
m = create_slash_workflow_module()
```
