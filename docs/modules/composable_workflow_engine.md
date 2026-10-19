# Module: `composable_workflow_engine`

- Category: Legacy Core · priority 23
- Version: 1.0.0
- Purpose: composable_workflow_engine — a compose-your-own context-engineering
- Skill: `eni-module-composable_workflow_engine` (ICM stages) in skills_pack/skills/eni-modules/composable_workflow_engine/

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
deterministic execution producing a per-phase log, validation, and JSON-safe
serialization.

## Key API (facade methods)
all_templates, compose, describe, get_template, health_check, initialize, register_template, run, set_event_bus, shutdown, validate_template

## Tests
```bash
python3 -m pytest modules/composable_workflow_engine/tests -q
```

## Import
```python
from enterprise.modules.composable_workflow_engine import create_composable_workflow_engine_module
m = create_composable_workflow_engine_module()
```
