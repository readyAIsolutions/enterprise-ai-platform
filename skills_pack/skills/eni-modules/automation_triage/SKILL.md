---
name: eni-module-automation_triage
description: Operate the ENI Enterprise `automation_triage` module (Build Quality) — What-to-automate ladder, wrong-layer detection, one-client scoping guard. Use when working with automation_triage in the Enterprise Platform.
---

# Module skill: automation_triage

- Category: Build Quality (priority 3)
- Version: 1.0.0
- Purpose: What-to-automate ladder, wrong-layer detection, one-client scoping guard.

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
  * scope_for_one_client / Scope

## Key API (facade methods on the @module class)
- detect_wrong_layer\n- health_check\n- initialize\n- scope_for_one_client\n- shutdown\n- triage\n- what_not_to_automate

## Use
Import via:
```python
from enterprise.modules.automation_triage import create_automation_triage_module
m = create_automation_triage_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/automation_triage/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.
