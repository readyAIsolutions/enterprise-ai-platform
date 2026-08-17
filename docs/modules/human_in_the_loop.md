# Module: `human_in_the_loop`

- Category: Agent Workflow · priority 2
- Version: 1.0.0
- Purpose: Human review/approval gates inside agent runs.
- Skill: `eni-module-human_in_the_loop` (ICM stages) in skills_pack/skills/eni-modules/human_in_the_loop/

## What it does
Human-in-the-Loop module — a human-oversight orchestration layer for the
compute layer.

Grounded in the real pulled JE Van Clief transcript "Afternoon tea: Why Humans
Belong in the Compute Layer" (30N9gLucrHg), whose central thesis is that
humans belong *inside* the compute layer and should never be removed from it:

  * "humans in the compute layer is super important. We don't want them
     removed from it. Humans are extremely compute efficient."  →  humans must
     stay in the loop for judgment, not be bypassed by autonomous agents.
  * "Augmenting Human Intellect" (Douglas Engelbart)  →  humans + machines
     collaborate; escalating uncertain or high-stakes work to a human keeps the
     machine useful without letting it act alone where it is unsure.

From that thesis this module provides an approval / escalation / routing /
audit engine:

  * ApprovalPolicy    — when must a human sign off (low confidence, high stakes).
  * HumanInTheLoop    — confidence-based routing + prioritized escalation queue.
  * EscalationQueue   — priority/deadline-ordered work awaiting a human.
  * DecisionAudit     — transparent record of every routing & override.

Export surface:
  * ApprovalPolicy, Action, Escalation, AuditEntry — pure engine types.
  * HumanInTheLoop, make_human_in_the_loop          — the orchestration engine.
  * HumanInTheLoopModule                            — the ENI platform wrapper.
  * create_human_in_the_loop_module(config)         — factory used by platform.

## Key API (facade methods)
audit_log, health_check, initialize, pending_escalations, queue_stats, resolve_action, route_action, shutdown

## Tests
```bash
python3 -m pytest modules/human_in_the_loop/tests -q
```

## Import
```python
from enterprise.modules.human_in_the_loop import create_human_in_the_loop_module
m = create_human_in_the_loop_module()
```
