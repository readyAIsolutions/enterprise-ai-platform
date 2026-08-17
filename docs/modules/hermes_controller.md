# Module: `hermes_controller`

- Category: Legacy Core · priority 31
- Version: 1.0.0
- Purpose: Enterprise Hermes Controller OS Module — autonomous controller for Hermes Agent.
- Skill: `eni-module-hermes_controller` (ICM stages) in skills_pack/skills/eni-modules/hermes_controller/

## What it does
Enterprise Hermes Controller OS Module — autonomous controller for Hermes Agent.

A stdlib-only facade that wraps the ENI Hermes Controller (prompt expander +
router + privacy boundary + reinforcement). Exposes it to the enterprise
platform so every build can:
  - expand LO's short instructions into massive detailed prompts,
  - sanitize secrets on egress (cloud never sees private data),
  - auto-continue through free-model rate limits,
  - queue work for deferred continuation (e.g. 6pm local),
  - retain good outcomes to the KB and build skills.

All components are stdlib-only with zero external dependencies.

## Key API (facade methods)
facade, health_check, initialize, shutdown

## Tests
```bash
python3 -m pytest modules/hermes_controller/tests -q
```

## Import
```python
from enterprise.modules.hermes_controller import create_hermes_controller_module
m = create_hermes_controller_module()
```
