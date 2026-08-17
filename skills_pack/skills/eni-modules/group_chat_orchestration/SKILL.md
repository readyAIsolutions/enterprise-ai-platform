---
name: eni-module-group_chat_orchestration
description: Operate the ENI Enterprise `group_chat_orchestration` module (Agent Workflow) — Multi-participant AI+human group chat: round-robin, moderator focus, escalation, handoffs. Use when working with group_chat_orchestration in the Enterprise Platform.
---

# Module skill: group_chat_orchestration

- Category: Agent Workflow (priority 2)
- Version: 1.0.0
- Purpose: Multi-participant AI+human group chat: round-robin, moderator focus, escalation, handoffs.

## What it does
Group Chat Orchestration module — multi-participant AI + human group chat.

Grounded in the pulled JE Van Clief transcripts:

* rWHHnIR30DE "Group Chat AI is game changing" — five-person group chat where
  three of the five participants are AI; each reads the shared context, forms
  an opinion and pipes it back in (multi-participant roles, reaction to prior
  context, round-robin turns).
* 0fCQ-4J_jzk "Why I Stopped Building AI Agents and Started Using Claude
  Cowork" — cowork over puppet agents: the human stays in the loop and "nips
  it in the bud" (moderator focus + human-in-the-loop escalation).
* pdoSAWWCDO8 "Claude Design Full Breakdown: GitHub Imports, Skills, and
  Local Model Handoff" — handing work to a specialist/local model with the
  human keeping "active code choice" (handof

## Key API (facade methods on the @module class)
- demo\n- escalate_to_human\n- handoff_to_agent\n- health_check\n- initialize\n- next_speaker\n- shutdown\n- start_group\n- stats\n- submit_message\n- summarize_round

## Use
Import via:
```python
from enterprise.modules.group_chat_orchestration import create_group_chat_orchestration_module
m = create_group_chat_orchestration_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/group_chat_orchestration/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.
