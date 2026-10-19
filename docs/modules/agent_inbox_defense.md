# Module: `agent_inbox_defense`

- Category: Legacy Core · priority 10
- Version: 1.0.0
- Purpose: agent_inbox_defense — enterprise module wrapping a defensive scanner for
- Skill: `eni-module-agent_inbox_defense` (ICM stages) in skills_pack/skills/eni-modules/agent_inbox_defense/

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

## Key API (facade methods)
allow_sender, audit_log, block_sender, engine, health_check, initialize, reset, scan, set_event_bus, shutdown, stats

## Tests
```bash
python3 -m pytest modules/agent_inbox_defense/tests -q
```

## Import
```python
from enterprise.modules.agent_inbox_defense import create_agent_inbox_defense_module
m = create_agent_inbox_defense_module()
```
