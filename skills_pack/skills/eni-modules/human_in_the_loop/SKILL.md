---
name: eni-module-human_in_the_loop
description: Operate the ENI Enterprise `human_in_the_loop` module (Agent Workflow) — Human review/approval gates inside agent runs. Use when working with human_in_the_loop in the Enterprise Platform.
---

# Module skill: human_in_the_loop

- Category: Agent Workflow (priority 2)
- Version: 1.0.0
- Purpose: Human review/approval gates inside agent runs.

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

From that thesis this module p

## Key API (facade methods on the @module class)
- audit_log\n- health_check\n- initialize\n- pending_escalations\n- queue_stats\n- resolve_action\n- route_action\n- shutdown

## Use
Import via:
```python
from enterprise.modules.human_in_the_loop import create_human_in_the_loop_module
m = create_human_in_the_loop_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/human_in_the_loop/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.
