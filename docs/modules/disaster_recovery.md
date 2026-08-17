# Module: `disaster_recovery`

- Category: Legacy Core · priority 21
- Version: 1.0.0
- Purpose: Disaster Recovery OS Module
- Skill: `eni-module-disaster_recovery` (ICM stages) in skills_pack/skills/eni-modules/disaster_recovery/

## What it does
Disaster Recovery OS Module

Enterprise-grade disaster recovery, business continuity, and crisis management.
Covers backup, recovery, cyber recovery, AI continuity, exercises, and crisis coordination.

Version: 1.0.0

## Key API (facade methods)
health_check, initialize, shutdown

## Tests
```bash
python3 -m pytest modules/disaster_recovery/tests -q
```

## Import
```python
from enterprise.modules.disaster_recovery import create_disaster_recovery_module
m = create_disaster_recovery_module()
```
