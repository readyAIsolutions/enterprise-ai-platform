---
name: eni-module-agent_inbox_defense
description: Operate the ENI Enterprise `agent_inbox_defense` module (Legacy Core) — agent_inbox_defense — enterprise module wrapping a defensive scanner for Use when working with agent_inbox_defense in the Enterprise Platform.
---

# Module skill: agent_inbox_defense

- Category: Legacy Core (priority ?)
- Version: 1.0.0
- Purpose: agent_inbox_defense — enterprise module wrapping a defensive scanner for

## What it does
agent_inbox_defense — enterprise module wrapping a defensive scanner for
untrusted inbound content handed to an AI agent.

Grounded in the matthew_berman transcript *"I was hacked..."*
(https://www.youtube.com/watch?v=_E4ZT1h7MZs). See
:mod:`enterprise.modules.agent_inbox_defense.agent_inbox_defense` for the full
mapping of the five attacks (token-aid flood, siege/quota-drain, jailbreak,
format-override prompt injection, system-command spoof, memory-exfil probe) to
the detectors and controls (quarantine, token budget, allow-list, human review,
frontier-model scanner) implemented here.

The deterministic, network-free core lives in the sibling logic module; this
package registers it as a Platform Kernel module with an
initialize / health_check / shutdown lifecycle and a thin facade.

## Key API (facade methods on the @module class)
- allow_sender\n- audit_log\n- block_sender\n- engine\n- health_check\n- initialize\n- reset\n- scan\n- set_event_bus\n- shutdown\n- stats

## Use
Import via:
```python
from enterprise.modules.agent_inbox_defense import create_agent_inbox_defense_module
m = create_agent_inbox_defense_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/agent_inbox_defense/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.
