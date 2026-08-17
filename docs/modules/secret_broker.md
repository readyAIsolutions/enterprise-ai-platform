# Module: `secret_broker`

- Category: Legacy Core · priority 57
- Version: 1.0.0
- Purpose: Enterprise Secret Broker OS Module — local-first secret handling.
- Skill: `eni-module-secret_broker` (ICM stages) in skills_pack/skills/eni-modules/secret_broker/

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

## Key API (facade methods)
(module-level API)

## Tests
```bash
python3 -m pytest modules/secret_broker/tests -q
```

## Import
```python
from enterprise.modules.secret_broker import create_secret_broker_module
m = create_secret_broker_module()
```
