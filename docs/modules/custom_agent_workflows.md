# Module: `custom_agent_workflows`

- Category: Legacy Core · priority 21
- Version: 1.0.0
- Purpose: custom_agent_workflows — build your OWN AI coding workflows as a module.
- Skill: `eni-module-custom_agent_workflows` (ICM stages) in skills_pack/skills/eni-modules/custom_agent_workflows/

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
it as a Platform Kernel module with an initialize / health_check / shutdown
lifecycle and a thin facade.

## Key API (facade methods)
build_initial_md, execute, health_check, initialize, plan, primer, research_codebase, set_event_bus, shutdown, stats, validate_code, validate_plan

## Tests
```bash
python3 -m pytest modules/custom_agent_workflows/tests -q
```

## Import
```python
from enterprise.modules.custom_agent_workflows import create_custom_agent_workflows_module
m = create_custom_agent_workflows_module()
```
