---
name: eni-module-unified_inbox
description: Operate the ENI Enterprise `unified_inbox` module (Legacy Core) — Enterprise Platform Unified Inbox module package. Use when working with unified_inbox in the Enterprise Platform.
---

# Module skill: unified_inbox

- Category: Legacy Core (priority ?)
- Version: 1.0.0
- Purpose: Enterprise Platform Unified Inbox module package.

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
  create_unifie

## Key API (facade methods on the @module class)
- health_check\n- inbox\n- initialize\n- set_event_bus\n- shutdown

## Use
Import via:
```python
from enterprise.modules.unified_inbox import create_unified_inbox_module
m = create_unified_inbox_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/unified_inbox/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.
