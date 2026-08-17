# Module: `developer_experience`

- Category: Legacy Core · priority 20
- Version: 1.0.0
- Purpose: Developer Experience OS Module
- Skill: `eni-module-developer_experience` (ICM stages) in skills_pack/skills/eni-modules/developer_experience/

## What it does
Developer Experience OS Module
==============================
Enterprise-grade Developer Experience operating system providing
a unified framework for developer journey, standards, environments,
golden paths, internal platform, AI coding rules, documentation,
and productivity metrics.

Architecture:
    journey.py      - Developer lifecycle journey stages
    standards.py    - Repository standards enforcement
    environment.py  - Development environment specifications
    golden_paths.py - Approved golden-path workflows
    platform.py     - Internal Developer Platform (IDP) capabilities
    ai_rules.py     - AI coding agent governance rules
    docs.py         - Documentation standards and quality gates
    metrics.py      - Developer productivity and DORA metrics

## Key API (facade methods)
health_check, initialize, shutdown

## Tests
```bash
python3 -m pytest modules/developer_experience/tests -q
```

## Import
```python
from enterprise.modules.developer_experience import create_developer_experience_module
m = create_developer_experience_module()
```
