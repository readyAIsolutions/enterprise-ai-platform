---
name: eni-module-procurement_bid_automation
description: Operate the ENI Enterprise `procurement_bid_automation` module (Domain) — Automate procurement/RFP bid intake, scoring and responses. Use when working with procurement_bid_automation in the Enterprise Platform.
---

# Module skill: procurement_bid_automation

- Category: Domain (priority 4)
- Version: 1.0.0
- Purpose: Automate procurement/RFP bid intake, scoring and responses.

## What it does
Procurement Bid Automation module — deterministic government/RFP bid
assistant.

Grounded in the real JE Van Clief transcripts:

* ``data/transcripts/JEVanClief/I-enT6szVQQ.md`` — "I Used AI to Fix Government
  Contracting": Bidnet Direct / SAM.gov portals, RFQ/RFP/IFB/RFI solicitation
  types, NAICS / NIGP / PSC code selection, CAGE codes, capability statements
  ("a one to two page PDF, government buyers expect this format"), vendor
  profile optimization and profile grading, and company-info -> apply/codes
  guidance. Central to the talk is using a *deterministic reference list* of
  codes/terms ("instead of having to fine-tune a model ... the AI references
  this list ... for accuracy").

* ``data/transcripts/JEVanClief/AjzBaEkWkNA.md`` — "AI Agency and Consulting
  Models are DEAD": t

## Key API (facade methods on the @module class)
- analyze_solicitation\n- assess_opportunity\n- generate_capability_statement\n- grade_profile\n- health_check\n- initialize\n- recommend_codes\n- set_event_bus\n- shutdown

## Use
Import via:
```python
from enterprise.modules.procurement_bid_automation import create_procurement_bid_automation_module
m = create_procurement_bid_automation_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/procurement_bid_automation/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.
