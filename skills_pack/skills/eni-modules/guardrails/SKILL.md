---
name: eni-module-guardrails
description: Operate the ENI Enterprise `guardrails` module (Legacy Core) — ENI Guardrails OS Module. Use when working with guardrails in the Enterprise Platform.
---

# Module skill: guardrails

- Category: Legacy Core (priority ?)
- Version: 2.0.0
- Purpose: ENI Guardrails OS Module.

## What it does
ENI Guardrails OS Module.

Programmable input/output validators with a validate / fix / refix loop
inspired by guardrails-ai, fully offline and stdlib-only.

Two layers ship here:

* **Classic layer** — ``Validator`` / ``ValidationResult`` base, built-ins
  (NoPII, NoToxic, Profanity, Length, Regex, NoPromptInjection, JSONSchema),
  ``Guard`` + ``GuardRailRunner`` with ``filter|raise|fix|refix`` policies and
  ``GuardrailViolationError``, plus the ``GuardRailFacade`` registry.

* **Guardrails-AI validator-plugin layer** — ``ValidatorRegistry`` with a
  ``register_validator(name, data_type)`` decorator, ``PassResult`` /
  ``FailResult`` (error_message / fix_value / on_fail of fix|block|raise),
  a declarative ``Guard.run``, ``data_type`` dispatch (string/number/json),
  built-in plugin vali

## Key API (facade methods on the @module class)
- facade\n- get_event_bus\n- get_registry\n- guardrails\n- health_check\n- initialize\n- list_guards\n- list_validators\n- register_guard\n- register_validator\n- registry\n- set_event_bus\n- shutdown\n- validate

## Use
Import via:
```python
from enterprise.modules.guardrails import create_guardrails_module
m = create_guardrails_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/guardrails/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.
