---
name: eni-module-developer_experience
description: Operate the ENI Enterprise `developer_experience` module (Legacy Core) — Developer Experience OS Module Use when working with developer_experience in the Enterprise Platform.
---

# Module skill: developer_experience

- Category: Legacy Core (priority ?)
- Version: 1.0.0
- Purpose: Developer Experience OS Module

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

## Key API (facade methods on the @module class)
- health_check\n- initialize\n- shutdown

## Use
Import via:
```python
from enterprise.modules.developer_experience import create_developer_experience_module
m = create_developer_experience_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/developer_experience/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.
