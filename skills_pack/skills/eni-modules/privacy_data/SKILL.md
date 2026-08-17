---
name: eni-module-privacy_data
description: Operate the ENI Enterprise `privacy_data` module (Legacy Core) — Privacy & Data Governance OS Module Use when working with privacy_data in the Enterprise Platform.
---

# Module skill: privacy_data

- Category: Legacy Core (priority ?)
- Version: 1.0.0
- Purpose: Privacy & Data Governance OS Module

## What it does
Privacy & Data Governance OS Module
====================================
Enterprise-grade privacy, data governance, security, and compliance module.

Modules:
  classifier  - Data classification engine (sensitivity, data type, PII detection)
  lifecycle   - Data lifecycle management (collection → deletion → audit)
  quality     - Data quality engine (8 dimensions, anomaly detection)
  privacy     - Privacy controls (consent, DSAR, retention, legal hold, residency)
  security    - Security controls (encryption, masking, tokenization, secrets, audit)
  compliance  - Compliance mapping (ISO 27001, SOC 2, NIST, GDPR, HIPAA, PCI DSS, CCPA)
  ai_data     - AI data governance (training data, RAG, embeddings, hallucination risk)
  monitoring  - Monitoring and alerting (access, leakage, drift, comp

## Key API (facade methods on the @module class)
- health_check\n- initialize\n- shutdown

## Use
Import via:
```python
from enterprise.modules.privacy_data import create_privacy_data_module
m = create_privacy_data_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/privacy_data/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.
