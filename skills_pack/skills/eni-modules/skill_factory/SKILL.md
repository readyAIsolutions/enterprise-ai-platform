---
name: eni-module-skill_factory
description: Operate the ENI Enterprise `skill_factory` module (Legacy Core) — ENI Skill Factory Module — Meta-Skill Generator / Registry / Self-Evolution. Use when working with skill_factory in the Enterprise Platform.
---

# Module skill: skill_factory

- Category: Legacy Core (priority ?)
- Version: 1.0.0
- Purpose: ENI Skill Factory Module — Meta-Skill Generator / Registry / Self-Evolution.

## What it does
ENI Skill Factory Module — Meta-Skill Generator / Registry / Self-Evolution.

Enterprise-grade module that discovers, generates, stores, versions, benchmarks,
and self-evolves markdown skill recipes (superpowers / hermes-skill-factory /
SkillClaw concepts).

Capabilities
------------
* SkillRegistry  — filesystem-backed versioned registry of ``SKILL.md`` recipes.
* SkillGenerator — meta-skill auto-generation from prompts or command sequences.
* SkillEvolutionLoop — benchmark scores, feedback trails, and self-evolution.

Exports:
  SkillFactoryModule — @module-decorated Module subclass
  SkillFactory       — facade over registry + generator + evolution
  SkillRegistry      — versioned markdown skill store
  SkillGenerator     — meta-skill auto-generation
  SkillEvolutionLoop — benchmark / r

## Key API (facade methods on the @module class)
- factory\n- health_check\n- initialize\n- set_event_bus\n- shutdown

## Use
Import via:
```python
from enterprise.modules.skill_factory import create_skill_factory_module
m = create_skill_factory_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/skill_factory/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.
