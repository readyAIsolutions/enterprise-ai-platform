# Module: `icm`

- Category: Legacy Core · priority 27
- Version: 1.0.0
- Purpose: ICM (Interpretable Context Methodology) — skill/prompt-engineering layer.
- Skill: `eni-module-icm` (ICM stages) in skills_pack/skills/eni-modules/icm/

## What it does
ICM (Interpretable Context Methodology) — skill/prompt-engineering layer.

Registers the ICM engine as a first-class Platform Kernel module so the rest of
the stack can:
  * scaffold standard numbered-stage skill projects,
  * route a task to the correct stage folder via 00_master.md,
  * load ONLY the current stage's markdown (progressive disclosure → lighter
    token spend per OpenRouter / swarm call),
  * classify whether a task belongs in deterministic sequential ICM work or in
    the concurrent multi-agent swarm layer (division of labor, spec §3).

This is the prompt-engineering discipline layer: orchestration decides WHICH
agent runs a task; ICM governs HOW that single agent structures its execution.

## Key API (facade methods)
health_check, initialize, new_project, route, shutdown, stage_context

## Tests
```bash
python3 -m pytest modules/icm/tests -q
```

## Import
```python
from enterprise.modules.icm import create_icm_module
m = create_icm_module()
```
