---
name: eni-module-threat_model
description: Operate the ENI Enterprise `threat_model` module (Legacy Core) — ENI Threat Model OS Module. Use when working with threat_model in the Enterprise Platform.
---

# Module skill: threat_model

- Category: Legacy Core (priority ?)
- Version: 1.0.0
- Purpose: ENI Threat Model OS Module.

## What it does
ENI Threat Model OS Module.

Offline MITRE ATLAS / STRIDE threat modeling and attack-surface analysis for
LLM systems. Provides a curated catalogue of MITRE ATLAS threats, a threat
library with category/technique lookups, an assessor that turns an asset
inventory into a risk register (risk = likelihood * impact, LOW/MEDIUM/HIGH/
CRITICAL severities), a STRIDE mapper, and a reporter for sorted registers,
top risks, and mitigation coverage.

All components are stdlib-only, zero external dependencies.

Version: 1.0.0
Python: 3.10+

## Key API (facade methods on the @module class)
(module-level API)

## Use
Import via:
```python
from enterprise.modules.threat_model import create_threat_model_module
m = create_threat_model_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/threat_model/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.
