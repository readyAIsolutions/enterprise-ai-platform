# Module: `guardrails`

- Category: Legacy Core · priority 25
- Version: 2.0.0
- Purpose: ENI Guardrails OS Module.
- Skill: `eni-module-guardrails` (ICM stages) in skills_pack/skills/eni-modules/guardrails/

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
  built-in plugin validators (PII, PromptInjection, Jailbreak, ShellInjection,
  SQLInjection, ToxicLanguage, JSONSchema, SecretLeak, URL) and the
  ``Guardrails`` facade exposing ``validate(value, guard_names, metadata)``,
  ``list_validators()`` and ``register_validator``.

The kernel ``GuardrailsModule`` builds the registry + default validators on
``initialize()``, reports HEALTHY only while the registry carries validators,
and cleans up on ``shutdown()``.

## Key API (facade methods)
facade, get_event_bus, get_registry, guardrails, health_check, initialize, list_guards, list_validators, register_guard, register_validator, registry, set_event_bus, shutdown, validate

## Tests
```bash
python3 -m pytest modules/guardrails/tests -q
```

## Import
```python
from enterprise.modules.guardrails import create_guardrails_module
m = create_guardrails_module()
```
