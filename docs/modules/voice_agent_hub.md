# Module: `voice_agent_hub`

- Category: Legacy Core · priority 70
- Version: 0.0.0
- Purpose: voice_agent_hub — voice-driven orchestration of coding agents in a group call.
- Skill: `eni-module-voice_agent_hub` (ICM stages) in skills_pack/skills/eni-modules/voice_agent_hub/

## What it does
voice_agent_hub — voice-driven orchestration of coding agents in a group call.

Grounded in JEVanClief's "We Ran Claude Code By Voice In A Group Call
(The Future of Work?)" (https://www.youtube.com/watch?v=McuxQvaWlNM).
The hub parses spoken utterances via keyword triggers, routes them to
target coding agents (including someone else's Claude Code), dispatches
commands for work, supports interruption, manages local-data access, and
triggers structured workflows by keywords in conversations.

## Key API (facade methods)
can_access_local_data, dispatch, grant_local_data_access, health_check, initialize, interrupt, parse_utterance, revoke_local_data_access, run_catalog_expansion, run_frontend_review, run_scale_review, set_event_bus, shutdown

## Tests
```bash
python3 -m pytest modules/voice_agent_hub/tests -q
```

## Import
```python
from enterprise.modules.voice_agent_hub import create_voice_agent_hub_module
m = create_voice_agent_hub_module()
```
