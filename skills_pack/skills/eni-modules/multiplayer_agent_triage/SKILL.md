---
name: eni-module-multiplayer_agent_triage
description: Operate the ENI Enterprise `multiplayer_agent_triage` module (Legacy Core) — multiplayer_agent_triage — a Platform Kernel module for triaging problems and Use when working with multiplayer_agent_triage in the Enterprise Platform.
---

# Module skill: multiplayer_agent_triage

- Category: Legacy Core (priority ?)
- Version: 1.0.0
- Purpose: multiplayer_agent_triage — a Platform Kernel module for triaging problems and

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
adventure" template wit

## Key API (facade methods on the @module class)
- critical_items\n- engine\n- health_check\n- initialize\n- record_win\n- set_event_bus\n- shutdown\n- summary\n- token_spend\n- triage

## Use
Import via:
```python
from enterprise.modules.multiplayer_agent_triage import create_multiplayer_agent_triage_module
m = create_multiplayer_agent_triage_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/multiplayer_agent_triage/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.
