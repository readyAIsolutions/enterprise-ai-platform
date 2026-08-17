# Module: `prompt_guard`

- Category: Legacy Core · priority 42
- Version: 1.0.0
- Purpose: Enterprise Prompt Guard OS Module — injection / jailbreak / policy guarding.
- Skill: `eni-module-prompt_guard` (ICM stages) in skills_pack/skills/eni-modules/prompt_guard/

## What it does
Enterprise Prompt Guard OS Module — injection / jailbreak / policy guarding.

A stdlib-only facade that inspects an inbound prompt and returns a
:class:`GuardVerdict` deciding whether it may proceed to a model. Chains
prompt-injection detection, jailbreak detection and declarative policy
enforcement in short-circuit order, and records every decision in an
append-only :class:`AuditLog`.

All components are stdlib-only with zero external dependencies.

## Key API (facade methods)
(module-level API)

## Tests
```bash
python3 -m pytest modules/prompt_guard/tests -q
```

## Import
```python
from enterprise.modules.prompt_guard import create_prompt_guard_module
m = create_prompt_guard_module()
```
