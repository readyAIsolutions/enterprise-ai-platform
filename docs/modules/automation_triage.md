# Module: `automation_triage`

- Category: Build Quality · priority 3
- Version: 1.0.0
- Purpose: What-to-automate ladder, wrong-layer detection, one-client scoping guard.
- Skill: `eni-module-automation_triage` (ICM stages) in skills_pack/skills/eni-modules/automation_triage/

## What it does
Automation Triage module — a decision framework for WHAT to automate.

Implements the task-triage ladder, wrong-layer detection, "what not to automate"
guard, and one-client scoping guard extracted from four pulled JE Van Clief
transcripts:

  * "The Ladder That Explains Every AI Failure (And How to Avoid Them)"
  * "You're Automating The Wrong Layer (How 30,000 People Build AI Without Frameworks)"
  * "The Real Skill in AI: Knowing What Not to Automate"
  * "Stop Building Production-Ready AI. Solve for One Client First"

Export surface:
  * triage_task / AutomationLayer / TriageAction / TriageDecision — the ladder.
  * detect_wrong_layer / WrongLayerReport — wrong-layer flagging.
  * what_not_to_automate / NotAutoDecision — the judgment-preservation guard.
  * scope_for_one_client / ScopeVerdict — the one-client-first scoping guard.

## Key API (facade methods)
detect_wrong_layer, health_check, initialize, scope_for_one_client, shutdown, triage, what_not_to_automate

## Tests
```bash
python3 -m pytest modules/automation_triage/tests -q
```

## Import
```python
from enterprise.modules.automation_triage import create_automation_triage_module
m = create_automation_triage_module()
```
