---
name: eni-module-model_security
description: Operate the ENI Enterprise `model_security` module (Legacy Core) — ENI Model Security OS Module. Use when working with model_security in the Enterprise Platform.
---

# Module skill: model_security

- Category: Legacy Core (priority ?)
- Version: 1.0.0
- Purpose: ENI Model Security OS Module.

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

## Key API (facade methods on the @module class)
(module-level API)

## Use
Import via:
```python
from enterprise.modules.model_security import create_model_security_module
m = create_model_security_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/model_security/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.
