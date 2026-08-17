# Module: `customer_experience`

- Category: Legacy Core · priority 22
- Version: 1.0.0
- Purpose: Customer Experience OS Module.
- Skill: `eni-module-customer_experience` (ICM stages) in skills_pack/skills/eni-modules/customer_experience/

## What it does
Customer Experience OS Module.

Provides a comprehensive suite for managing the end-to-end customer journey,
including journey mapping, support ticketing, AI-assisted support guardrails,
CX metrics, feedback analysis, and communication templates.

Version: 1.0.0

## Key API (facade methods)
health_check, initialize, shutdown

## Tests
```bash
python3 -m pytest modules/customer_experience/tests -q
```

## Import
```python
from enterprise.modules.customer_experience import create_customer_experience_module
m = create_customer_experience_module()
```
