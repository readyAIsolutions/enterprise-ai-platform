# Module: `model_router`

- Category: Legacy Core · priority 42
- Version: 1.0.0
- Purpose: ENI Model Router OS Module — enterprise model-routing / fallback gateway.
- Skill: `eni-module-model_router` (ICM stages) in skills_pack/skills/eni-modules/model_router/

## What it does
ENI Model Router OS Module — enterprise model-routing / fallback gateway.

A production-grade, stdlib-only model-routing gateway ripped from the LiteLLM
retry/cooldown pattern. It manages a fleet of model deployments, selects healthy
ones per request via weighted (hash-bucket) selection, retries transient
failures per a per-exception-type policy, and falls back across a model group —
placing failing deployments into a time-based cooldown so they are excluded
from dispatch until they recover.

All components are stdlib-only (zero external dependencies beyond the kernel).

## Key API (facade methods)
(module-level API)

## Tests
```bash
python3 -m pytest modules/model_router/tests -q
```

## Import
```python
from enterprise.modules.model_router import create_model_router_module
m = create_model_router_module()
```
