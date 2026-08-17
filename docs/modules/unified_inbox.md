# Module: `unified_inbox`

- Category: Legacy Core · priority 58
- Version: 1.0.0
- Purpose: Enterprise Platform Unified Inbox module package.
- Skill: `eni-module-unified_inbox` (ICM stages) in skills_pack/skills/eni-modules/unified_inbox/

## What it does
Enterprise Platform Unified Inbox module package.

Grounded in the JEVanClief "Clawdbot (Moltbot) Has 100K Stars. It Has Zero AI."
transcript: a zero-AI universal assistant that consolidates every messaging
platform (Slack, Discord, WhatsApp, Telegram, email, calendar, Teams) into one
place and routes messages deterministically — no neural model required.

Exports:
  UnifiedInboxModule      — @module-decorated Module subclass registered with
                            the Platform Kernel.
  CrossChannelInbox       — pure-stdlib zero-AI routing/triage/consolidation core.
  ChannelAdapter          — named channel adapter descriptor.
  InboundMessage          — a message arriving from any channel.
  TriageDecision          — deterministic routing/triage verdict for a message.
  create_unified_inbox_module — factory for the registered module.

Version: 1.0.0
Python: 3.10+

## Key API (facade methods)
health_check, inbox, initialize, set_event_bus, shutdown

## Tests
```bash
python3 -m pytest modules/unified_inbox/tests -q
```

## Import
```python
from enterprise.modules.unified_inbox import create_unified_inbox_module
m = create_unified_inbox_module()
```
