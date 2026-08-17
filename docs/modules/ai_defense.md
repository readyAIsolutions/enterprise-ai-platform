# Module: `ai_defense`

- Category: Legacy Core · priority 13
- Version: 1.0.0
- Purpose: ENI Enterprise AI Defense OS Module.
- Skill: `eni-module-ai_defense` (ICM stages) in skills_pack/skills/eni-modules/ai_defense/

## What it does
ENI Enterprise AI Defense OS Module.

Defense against *AI-driven / automated* attackers: statistical anomaly detection,
bot/agent traffic classification, model-extraction probing shield, credential-
stuffing lockout, and indirect prompt-injection detection. Complements the
``model_security`` module (which guards model *input/output*); this module
guards the *attacker side*.

The module exposes a ``@module``-registered kernel Module
(:class:`AIDefenseModule`) alongside a plain convenience facade
(:class:`AIDefenseFacade`) for direct, dependency-free use.

All components are stdlib-only with zero external dependencies.

## Key API (facade methods)
(module-level API)

## Tests
```bash
python3 -m pytest modules/ai_defense/tests -q
```

## Import
```python
from enterprise.modules.ai_defense import create_ai_defense_module
m = create_ai_defense_module()
```
