---
name: eni-module-secret_broker
description: Operate the ENI Enterprise `secret_broker` module (Legacy Core) — Enterprise Secret Broker OS Module — local-first secret handling. Use when working with secret_broker in the Enterprise Platform.
---

# Module skill: secret_broker

- Category: Legacy Core (priority ?)
- Version: 1.0.0
- Purpose: Enterprise Secret Broker OS Module — local-first secret handling.

## What it does
Enterprise Secret Broker OS Module — local-first secret handling.

Keeps secrets away from remote LLM/API calls via the reversible local-first
flow ``detect -> substitute -> call model -> reverse-substitute``. Every secret
is replaced by a unique placeholder *before* text reaches a model, and restored
locally afterwards, so no raw secret can ever leak off-box.

Components:

* :class:`SecretDetector` — regex + entropy detection, returns typed hits.
* :class:`PlaceholderSubstituter` — reversible, idempotent placeholder swap.
* :class:`SecretBroker` — ``redact()``/``restore()``/``guard_outbound()`` facade.
* :class:`OutboundSecretLeakError` — outbound leak guard.

All components are stdlib-only with zero external dependencies.

## Key API (facade methods on the @module class)
(module-level API)

## Use
Import via:
```python
from enterprise.modules.secret_broker import create_secret_broker_module
m = create_secret_broker_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/secret_broker/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.
