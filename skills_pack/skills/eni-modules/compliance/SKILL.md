---
name: eni-module-compliance
description: Operate the ENI Enterprise `compliance` module (Legacy Core) — ENI Enterprise Compliance OS Module. Use when working with compliance in the Enterprise Platform.
---

# Module skill: compliance

- Category: Legacy Core (priority ?)
- Version: 1.1.0
- Purpose: ENI Enterprise Compliance OS Module.

## What it does
ENI Enterprise Compliance OS Module.

Offline security-control mapping & audit evidence for the ENI platform across:

* OWASP LLM Top 10 (2025)
* NIST AI RMF 1.0 core functions (GOVERN / MAP / MEASURE / MANAGE)
* MITRE ATLAS (Adversarial Threat Landscape for AI Systems)

Provides a control catalogue, a ComplianceEvaluator that computes coverage,
residual risk and PASS/FAIL against a target, a GapAnalyzer for missing
controls, and a ComplianceReport for audit snapshots.

All components are stdlib-only, zero external dependencies.

## Key API (facade methods on the @module class)
(module-level API)

## Use
Import via:
```python
from enterprise.modules.compliance import create_compliance_module
m = create_compliance_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/compliance/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.
