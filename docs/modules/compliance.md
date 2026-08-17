# Module: `compliance`

- Category: Legacy Core · priority 16
- Version: 1.1.0
- Purpose: ENI Enterprise Compliance OS Module.
- Skill: `eni-module-compliance` (ICM stages) in skills_pack/skills/eni-modules/compliance/

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

## Key API (facade methods)
(module-level API)

## Tests
```bash
python3 -m pytest modules/compliance/tests -q
```

## Import
```python
from enterprise.modules.compliance import create_compliance_module
m = create_compliance_module()
```
