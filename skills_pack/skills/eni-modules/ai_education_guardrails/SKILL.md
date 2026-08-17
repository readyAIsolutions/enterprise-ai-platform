---
name: eni-module-ai_education_guardrails
description: Operate the ENI Enterprise `ai_education_guardrails` module (Domain) — Guardrails for using AI in education (anti-cheating, learning-first). Use when working with ai_education_guardrails in the Enterprise Platform.
---

# Module skill: ai_education_guardrails

- Category: Domain (priority 4)
- Version: 1.0.0
- Purpose: Guardrails for using AI in education (anti-cheating, learning-first).

## What it does
AI Education Guardrails — responsible & effective AI use in academics/edtech.

Distilled from four pulled JE Van Clief transcripts:

  * "AI in Academics: How NOT to Use It" (czIBNYeiAuw) — learning how NOT to use
    AI is the most important skill; AI as chisel vs crutch; the THINK writing
    process; equity/access (AI overwhelm, tool deficiency, community void).
  * "AI Cheating in Class? Redefining What 'Challenging' Means in Education"
    (iY_j0VKimQI) — raise the bar; redesign assessments to grade the critique
    and the prompts rather than the AI product; generic-AI-texture detection.
  * "Perils of AI and Ed-Tech" (THQH6Uc6PNU) — grade the process not the product;
    top-down critique method & structured dialogue; editable/deletable data;
    tools not meeting assessment goals e

## Key API (facade methods on the @module class)
- assess_assignment\n- assess_governance\n- classify_usage\n- detect\n- engine\n- health_check\n- initialize\n- shutdown

## Use
Import via:
```python
from enterprise.modules.ai_education_guardrails import create_ai_education_guardrails_module
m = create_ai_education_guardrails_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/ai_education_guardrails/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.
