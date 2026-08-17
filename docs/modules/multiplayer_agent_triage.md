# Module: `multiplayer_agent_triage`

- Category: Legacy Core · priority 44
- Version: 1.0.0
- Purpose: multiplayer_agent_triage — a Platform Kernel module for triaging problems and
- Skill: `eni-module-multiplayer_agent_triage` (ICM stages) in skills_pack/skills/eni-modules/multiplayer_agent_triage/

## What it does
multiplayer_agent_triage — a Platform Kernel module for triaging problems and
wins when many AI agents / players operate together in one shared product.

Grounded in the JEVanClief transcript *"Alpha Launch 24 Hours in: AI multiplayer
Problems and Wins!"* (https://www.youtube.com/watch?v=e3RgzvuYTBY), which is a
24-hour post-mortem of a multiplayer AI platform: many users and coding agents
sharing workspaces. The transcript catalogues concrete failures (oversized
per-request reads, deployment / Azure blob file-naming problems leaving agents
stuck in thinking mode, workspace files not surfacing, sandbox read failures
that needed a fallback, token/cost monitoring) and wins (extremely efficient
shared token usage, a community knowledge-corpus upload, a "choose your own
adventure" template with memories/states, workflow/explainer automation, and
organizations enabling people to work together).

The deterministic, stdlib-only logic lives in
:mod:`enterprise.modules.multiplayer_agent_triage.multiplayer_agent_triage`
(``MultiplayerTriageEngine``, ``classify_problem``, ``classify_win``,
``analyze_token_spend``, ``summarize_incidents``). This package registers it as
a module with an initialize / health_check / shutdown lifecycle, a thin facade,
and EventBus publishing for triaged problems and wins.

## Key API (facade methods)
critical_items, engine, health_check, initialize, record_win, set_event_bus, shutdown, summary, token_spend, triage

## Tests
```bash
python3 -m pytest modules/multiplayer_agent_triage/tests -q
```

## Import
```python
from enterprise.modules.multiplayer_agent_triage import create_multiplayer_agent_triage_module
m = create_multiplayer_agent_triage_module()
```
