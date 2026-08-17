---
name: eni-module-voice_agent_hub
description: Operate the ENI Enterprise `voice_agent_hub` module (Legacy Core) — voice_agent_hub — voice-driven orchestration of coding agents in a group call. Use when working with voice_agent_hub in the Enterprise Platform.
---

# Module skill: voice_agent_hub

- Category: Legacy Core (priority ?)
- Version: 0.0.0
- Purpose: voice_agent_hub — voice-driven orchestration of coding agents in a group call.

## What it does
voice_agent_hub — voice-driven orchestration of coding agents in a group call.

Grounded in JEVanClief's "We Ran Claude Code By Voice In A Group Call
(The Future of Work?)" (https://www.youtube.com/watch?v=McuxQvaWlNM).
The hub parses spoken utterances via keyword triggers, routes them to
target coding agents (including someone else's Claude Code), dispatches
commands for work, supports interruption, manages local-data access, and
triggers structured workflows by keywords in conversations.

## Key API (facade methods on the @module class)
- can_access_local_data\n- dispatch\n- grant_local_data_access\n- health_check\n- initialize\n- interrupt\n- parse_utterance\n- revoke_local_data_access\n- run_catalog_expansion\n- run_frontend_review\n- run_scale_review\n- set_event_bus\n- shutdown

## Use
Import via:
```python
from enterprise.modules.voice_agent_hub import create_voice_agent_hub_module
m = create_voice_agent_hub_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/voice_agent_hub/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.
