# Module: `skill_factory`

- Category: Legacy Core · priority 60
- Version: 1.0.0
- Purpose: ENI Skill Factory Module — Meta-Skill Generator / Registry / Self-Evolution.
- Skill: `eni-module-skill_factory` (ICM stages) in skills_pack/skills/eni-modules/skill_factory/

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
  SkillEvolutionLoop — benchmark / refine / self-evolve
  SkillRecord        — versioned skill data model

Version: 1.0.0
Python: 3.10+

## Key API (facade methods)
factory, health_check, initialize, set_event_bus, shutdown

## Tests
```bash
python3 -m pytest modules/skill_factory/tests -q
```

## Import
```python
from enterprise.modules.skill_factory import create_skill_factory_module
m = create_skill_factory_module()
```
