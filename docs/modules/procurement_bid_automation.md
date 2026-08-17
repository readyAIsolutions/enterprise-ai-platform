# Module: `procurement_bid_automation`

- Category: Domain · priority 4
- Version: 1.0.0
- Purpose: Automate procurement/RFP bid intake, scoring and responses.
- Skill: `eni-module-procurement_bid_automation` (ICM stages) in skills_pack/skills/eni-modules/procurement_bid_automation/

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
  Models are DEAD": the ROI/fit critique (some solutions "thousands of percent
  of ROI. Other ones are absolutely negative"), "provide value beyond what the
  individual ... can do themselves", and knowing when a solution genuinely fits
  before investing. Here that critique powers the bid/no-bid fit assessment.

Pure core lives in :mod:`enterprise.modules.procurement_bid_automation
.procurement_bid_automation` (stdlib-only). This module exposes the ENI platform
facade around it.

Export surface:
  * CodeMatcher / Code / ScoredCode  — NAICS/NIGP/PSC code taxonomy scoring.
  * CompanyProfile / CapabilityStatement / generate_capability_statement
  * grade_profile / ProfileGrade    — vendor profile optimization.
  * Solicitation / analyze_solicitation / SolicitationAnalysis — RFP decoder.
  * assess_opportunity / OpportunityAssessment — bid/no-bid fit & ROI.
  * ProcurementBidAutomationModule — the ENI platform Module wrapper.
  * create_procurement_bid_automation_module(config) — platform factory.

## Key API (facade methods)
analyze_solicitation, assess_opportunity, generate_capability_statement, grade_profile, health_check, initialize, recommend_codes, set_event_bus, shutdown

## Tests
```bash
python3 -m pytest modules/procurement_bid_automation/tests -q
```

## Import
```python
from enterprise.modules.procurement_bid_automation import create_procurement_bid_automation_module
m = create_procurement_bid_automation_module()
```
