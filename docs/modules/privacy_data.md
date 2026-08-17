# Module: `privacy_data`

- Category: Legacy Core · priority 48
- Version: 1.0.0
- Purpose: Privacy & Data Governance OS Module
- Skill: `eni-module-privacy_data` (ICM stages) in skills_pack/skills/eni-modules/privacy_data/

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
  monitoring  - Monitoring and alerting (access, leakage, drift, compliance, quality)

## Key API (facade methods)
health_check, initialize, shutdown

## Tests
```bash
python3 -m pytest modules/privacy_data/tests -q
```

## Import
```python
from enterprise.modules.privacy_data import create_privacy_data_module
m = create_privacy_data_module()
```
