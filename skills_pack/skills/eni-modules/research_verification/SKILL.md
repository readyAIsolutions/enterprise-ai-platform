---
name: eni-module-research_verification
description: Operate the ENI Enterprise `research_verification` module (Legacy Core) — Research & Verification OS — Enterprise Platform Kernel Module v1.0.0 Use when working with research_verification in the Enterprise Platform.
---

# Module skill: research_verification

- Category: Legacy Core (priority ?)
- Version: 1.0.0
- Purpose: Research & Verification OS — Enterprise Platform Kernel Module v1.0.0

## What it does
Research & Verification OS — Enterprise Platform Kernel Module v1.0.0
======================================================================

Enterprise-grade module implementing the Research & Verification Operating
System for the ENI Enterprise AI platform, per the Research OS spec.

Produces trustworthy, evidence-based outputs by retrieving, validating,
comparing, ranking, and synthesizing information before it is accepted
into organizational memory or engineering decisions.

Core components (aligned with Research OS spec):
  - ResearchPlanner       — plan research, classify domain, scope investigation
  - SourceRanker          — rank sources by authority (internal > vendor > standard >
    academic > tech pub > community)
  - ClaimDetector         — detect conflicting claims, distingui

## Key API (facade methods on the @module class)
- confidence\n- detector\n- execute_pipeline\n- health_check\n- initialize\n- planner\n- ranker\n- shutdown\n- synthesizer\n- tracker

## Use
Import via:
```python
from enterprise.modules.research_verification import create_research_verification_module
m = create_research_verification_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/research_verification/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.
