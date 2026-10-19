# Module: `context_workflow_framework`

- Category: Legacy Core · priority 25
- Version: 1.0.0
- Purpose: context_workflow_framework — build-your-own context-engineering workflow
- Skill: `eni-module-context_workflow_framework` (ICM stages) in skills_pack/skills/eni-modules/context_workflow_framework/

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

## Key API (facade methods)
health_check, initialize, load_template, phase_names, render, set_event_bus, shutdown, validate_context

## Tests
```bash
python3 -m pytest modules/context_workflow_framework/tests -q
```

## Import
```python
from enterprise.modules.context_workflow_framework import create_context_workflow_framework_module
m = create_context_workflow_framework_module()
```
