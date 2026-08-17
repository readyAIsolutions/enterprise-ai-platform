# Module: `ai_education_guardrails`

- Category: Domain · priority 4
- Version: 1.0.0
- Purpose: Guardrails for using AI in education (anti-cheating, learning-first).
- Skill: `eni-module-ai_education_guardrails` (ICM stages) in skills_pack/skills/eni-modules/ai_education_guardrails/

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
    tools not meeting assessment goals erode trust.
  * "Artificial Minds, Real Ideas Ep. 1: Who Controls EdTech?" (wpM-c--FE04) —
    mini-public / bottom-up governance; process AND outcome metrics; equity —
    tools not built with diverse learners widen the achievement gap.

Export surface:
  * UsagePolicyClassifier   — labels an AI use-case MISUSE / ASSISTIVE / LEGITIMATE
                              with matched signals and rationale.
  * AssignmentRobustnessChecker — does an assessment hold up against AI / test
                              durable skills (robust / at_risk / fragile).
  * detect_submission       — misuse-detection heuristics (AI-texture, disclosure,
                              citation).
  * EdTechGovernanceChecker — who controls the tool; inclusive vs top-down.
  * AIEducationGuardrailsEngine — facade engine composing every check.
  * Module + factory:       AiEducationGuardrailsModule / create_ai_education_guardrails_module.

## Key API (facade methods)
assess_assignment, assess_governance, classify_usage, detect, engine, health_check, initialize, shutdown

## Tests
```bash
python3 -m pytest modules/ai_education_guardrails/tests -q
```

## Import
```python
from enterprise.modules.ai_education_guardrails import create_ai_education_guardrails_module
m = create_ai_education_guardrails_module()
```
