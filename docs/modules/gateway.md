# Module: `gateway`

- Category: Legacy Core · priority 24
- Version: 1.0.0
- Purpose: ENI Multi-Gateway Remote Control & Automations Module
- Skill: `eni-module-gateway` (ICM stages) in skills_pack/skills/eni-modules/gateway/

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

## Key API (facade methods)
gateway, health_check, initialize, scheduler, set_event_bus, shutdown

## Tests
```bash
python3 -m pytest modules/gateway/tests -q
```

## Import
```python
from enterprise.modules.gateway import create_gateway_module
m = create_gateway_module()
```
