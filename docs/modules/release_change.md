# Module: `release_change`

- Category: Legacy Core · priority 44
- Version: 1.0.0
- Purpose: Release & Change Management OS Module
- Skill: `eni-module-release_change` (ICM stages) in skills_pack/skills/eni-modules/release_change/

## What it does
Release & Change Management OS Module

Enterprise-grade release and change management for the ENI platform.
Manages the full lifecycle of changes: classification, workflow,
deployment strategies, quality gates, and deliverables.

Supports:
  - Structured change workflows with 14 stages
  - Risk-based classification (13 change types, 4 risk levels)
  - 8 deployment strategies (canary, blue-green, staged rollout, etc.)
  - 10 quality gate checks
  - 10 deliverable types for compliance and audit readiness

Version: 1.0.0

## Key API (facade methods)
health_check, initialize, shutdown

## Tests
```bash
python3 -m pytest modules/release_change/tests -q
```

## Import
```python
from enterprise.modules.release_change import create_release_change_module
m = create_release_change_module()
```
