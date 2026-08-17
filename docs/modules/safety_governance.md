# Module: `safety_governance`

- Category: Legacy Core · priority 48
- Version: 1.0.0
- Purpose: ENI Enterprise — Safety & Governance OS v1.0.0
- Skill: `eni-module-safety_governance` (ICM stages) in skills_pack/skills/eni-modules/safety_governance/

## What it does
ENI Enterprise — Safety & Governance OS v1.0.0
AI Safety, Security, Guardrails, Evaluation, Monitoring, Incident Response.

## Key API (facade methods)
health_check, initialize, shutdown

## Tests
```bash
python3 -m pytest modules/safety_governance/tests -q
```

## Import
```python
from enterprise.modules.safety_governance import create_safety_governance_module
m = create_safety_governance_module()
```
