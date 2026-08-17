# Module: `threat_model`

- Category: Legacy Core · priority 65
- Version: 1.0.0
- Purpose: ENI Threat Model OS Module.
- Skill: `eni-module-threat_model` (ICM stages) in skills_pack/skills/eni-modules/threat_model/

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

## Key API (facade methods)
(module-level API)

## Tests
```bash
python3 -m pytest modules/threat_model/tests -q
```

## Import
```python
from enterprise.modules.threat_model import create_threat_model_module
m = create_threat_model_module()
```
