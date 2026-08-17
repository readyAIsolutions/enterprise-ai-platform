# Module: `model_security`

- Category: Legacy Core · priority 38
- Version: 1.0.0
- Purpose: ENI Model Security OS Module.
- Skill: `eni-module-model_security` (ICM stages) in skills_pack/skills/eni-modules/model_security/

## What it does
ENI Model Security OS Module.

Model-agnostic security pipeline providing infrastructure-level guards that work
regardless of whether the underlying model is compromised. Implements OWASP LLM
Top 10 mitigations at the infrastructure layer.

Features:
- Input sanitization (secrets, PII, credentials) before model sees them
- Prompt injection detection (OWASP LLM01) - infrastructure regex/heuristics
- Jailbreak detection - role-play, encoding, hypothetical, translation
- Output validation - secret leakage, PII, exfiltration, refusals, toxicity
- Tamper-evident audit logging with hash-chained entries
- Declarative policy engine (YAML) for allow/deny/transform rules
- SecurityPipeline orchestrating all guards in correct order

All components are stdlib-only, zero external dependencies.

## Key API (facade methods)
(module-level API)

## Tests
```bash
python3 -m pytest modules/model_security/tests -q
```

## Import
```python
from enterprise.modules.model_security import create_model_security_module
m = create_model_security_module()
```
