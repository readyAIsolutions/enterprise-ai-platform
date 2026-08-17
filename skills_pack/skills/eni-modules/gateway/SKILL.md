---
name: eni-module-gateway
description: Operate the ENI Enterprise `gateway` module (Legacy Core) — ENI Multi-Gateway Remote Control & Automations Module Use when working with gateway in the Enterprise Platform.
---

# Module skill: gateway

- Category: Legacy Core (priority ?)
- Version: 1.0.0
- Purpose: ENI Multi-Gateway Remote Control & Automations Module

## What it does
ENI Multi-Gateway Remote Control & Automations Module

Connects the ENI Enterprise platform to external messaging channels
(Telegram, Discord, generic webhooks) and provides a cron/interval scheduler
for running scheduled automations — enabling outbound alerts, notifications,
and remote-controlled automation.

Exports:
  GatewayModule      — @module-decorated Module subclass
  Gateway            — multi-channel registry: register/send/broadcast/route
  Scheduler          — pure cron + interval scheduler
  build_channel      — config-driven channel factory

Version: 1.0.0
Python: 3.10+

## Key API (facade methods on the @module class)
- gateway\n- health_check\n- initialize\n- scheduler\n- set_event_bus\n- shutdown

## Use
Import via:
```python
from enterprise.modules.gateway import create_gateway_module
m = create_gateway_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/gateway/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.
