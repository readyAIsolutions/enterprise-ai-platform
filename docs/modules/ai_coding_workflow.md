# Module: `ai_coding_workflow`

- Category: Legacy Core · priority 16
- Version: 1.0.0
- Purpose: ai_coding_workflow — a framework-agnostic, 3-phase AI-coding workflow
- Skill: `eni-module-ai_coding_workflow` (ICM stages) in skills_pack/skills/eni-modules/ai_coding_workflow/

## What it does
ai_coding_workflow — a framework-agnostic, 3-phase AI-coding workflow
engine for the ENI Enterprise Platform.

Grounded in ColeMedin's "The True Power of AI Coding - Build Your OWN
Workflows" (https://www.youtube.com/watch?v=mHBk8Z7Exag). The workflow runs
REQUIREMENTS -> PLAN -> EXECUTE -> VALIDATE -> COMPLETE: a codebase-analyst
research step builds a granular task plan, a per-task state machine cycles
each task TODO->DOING->REVIEW->DONE one at a time (to prevent hallucination),
and a validation gate generates tests + a human code-review step that can
reopen tasks. Works with PRP / BMAD / spec-kit / plain markdown.

## Key API (facade methods)
advance_task, create_plan, create_workflow, get_workflow, health_check, initialize, progress, render, set_event_bus, set_requirements, shutdown, start_task, summary, validate

## Tests
```bash
python3 -m pytest modules/ai_coding_workflow/tests -q
```

## Import
```python
from enterprise.modules.ai_coding_workflow import create_ai_coding_workflow_module
m = create_ai_coding_workflow_module()
```
