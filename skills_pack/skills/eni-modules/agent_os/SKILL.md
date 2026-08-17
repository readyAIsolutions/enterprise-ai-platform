---
name: eni-module-agent_os
description: Operate the ENI Enterprise `agent_os` module (Legacy Core) — Enterprise Agent OS Module — a unified AI agent operating system. Use when working with agent_os in the Enterprise Platform.
---

# Module skill: agent_os

- Category: Legacy Core (priority ?)
- Version: 1.0.0
- Purpose: Enterprise Agent OS Module — a unified AI agent operating system.

## What it does
Enterprise Agent OS Module — a unified AI agent operating system.

Replicates Julian Goldie's "Agent OS" (Hermes + Oracle + Paperclip + Jarvis)
as a real, working ENI Enterprise module — but FOSS and built on top of the
platform Kernel instead of a paid zip + coaching upsell.

The four "tools" from the video, recreated with free/open-source pieces:

  * Hermes    -> this module IS the Hermes-facing surface: it wraps the
                 ENI controller facade (prompt expansion + routing) and
                 exposes one unified `run()` entrypoint so every tool is
                 reachable through a single command surface.
  * Oracle    -> a free news engine: pulls trending headlines via RSS
                 (feedparser — no API key, no paid tier), scores them by
                 attention 

## Key API (facade methods on the @module class)
- health_check\n- initialize\n- run\n- shutdown\n- surface

## Use
Import via:
```python
from enterprise.modules.agent_os import create_agent_os_module
m = create_agent_os_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/agent_os/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.
