"""ENI Guardrails OS Module.

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
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

from enterprise.platform_kernel import (
    EventBus,
    HealthStatus,
    Module,
    module,
)

from .guardrails import (
    FailResult,
    Guard,
    GuardRailFacade,
    GuardRailRunner,
    Guardrails,
    GuardrailViolationError,
    GuardResult,
    JailbreakValidator,
    JSONSchemaValidator,
    LengthValidator,
    NoPIIValidator,
    NoPromptInjectionValidator,
    NoToxicValidator,
    PassResult,
    PIIValidator,
    ProfanityValidator,
    PromptInjectionValidator,
    RegexValidator,
    SecretLeakValidator,
    ShellInjectionValidator,
    SQLInjectionValidator,
    ToxicLanguageValidator,
    URLValidator,
    ValidationResult,
    Validator,
    ValidatorRegistry,
    build_default_registry,
)

__version__ = "2.0.0"
__module__ = "guardrails"

__all__ = [
    "__version__",
    # kernel + facades
    "GuardrailsModule",
    "create_guardrails_module",
    "create_guardrails_facade",
    "GuardRailFacade",
    "GuardrailViolationError",
    # classic types
    "ValidationResult",
    "Validator",
    "Guard",
    "GuardResult",
    "GuardRailRunner",
    # plugin layer
    "PassResult",
    "FailResult",
    "ValidatorRegistry",
    "Guardrails",
    "build_default_registry",
    # classic built-ins
    "NoPIIValidator",
    "NoToxicValidator",
    "ProfanityValidator",
    "LengthValidator",
    "RegexValidator",
    "NoPromptInjectionValidator",
    "JSONSchemaValidator",
    # plugin built-ins
    "PIIValidator",
    "PromptInjectionValidator",
    "JailbreakValidator",
    "ShellInjectionValidator",
    "SQLInjectionValidator",
    "ToxicLanguageValidator",
    "SecretLeakValidator",
    "URLValidator",
]

_logger = logging.getLogger("enterprise.guardrails")


@module(name="guardrails", version="2.0.0", config_defaults={"default_guards": True})
class GuardrailsModule(Module):
    """Kernel service exposing both the classic GuardRailFacade and the
    Guardrails-AI validator-plugin system (registry + declarative facade)."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._event_bus: EventBus | None = None
        self._facade: GuardRailFacade | None = None
        self._registry: ValidatorRegistry | None = None
        self._guardrails: Guardrails | None = None
        self._lock = threading.RLock()

    # -- classic facade (legacy contract) ----------------------------------
    @property
    def facade(self) -> GuardRailFacade:
        with self._lock:
            if self._facade is None:
                msg = "Guardrails module not initialized"
                raise RuntimeError(msg)
            return self._facade

    @property
    def registry(self) -> ValidatorRegistry:
        with self._lock:
            if self._registry is None:
                msg = "Guardrails module not initialized"
                raise RuntimeError(msg)
            return self._registry

    @property
    def guardrails(self) -> Guardrails:
        """Declarative Guardrails-AI facade (registry + named guards)."""
        with self._lock:
            if self._guardrails is None:
                msg = "Guardrails module not initialized"
                raise RuntimeError(msg)
            return self._guardrails

    # -- lifecycle ---------------------------------------------------------
    async def initialize(self) -> None:
        with self._lock:
            self._status = HealthStatus.STARTING
            _logger.info("Initializing Guardrails Module...")

            # Classic facade + default guards.
            self._facade = GuardRailFacade(self._config)
            if self._config.get("default_guards", True):
                self._register_default_guards(self._facade)

            # Guardrails-AI plugin layer: registry + default validators.
            self._registry = build_default_registry()
            self._guardrails = Guardrails(self._config, registry=self._registry)
            self._register_plugin_guards(self._guardrails)

            self._status = HealthStatus.HEALTHY
            _logger.info(
                "Guardrails Module initialized (%d validators, %d guards)",
                len(self._registry),
                len(self._guardrails.list_guards()),
            )

    async def health_check(self) -> HealthStatus:
        with self._lock:
            healthy = (
                self._status == HealthStatus.HEALTHY
                and self._registry is not None
                and len(self._registry) > 0
            )
            if healthy:
                return HealthStatus.HEALTHY
            return HealthStatus.UNHEALTHY

    async def shutdown(self) -> None:
        with self._lock:
            self._status = HealthStatus.STOPPING
            _logger.info("Shutting down Guardrails Module...")
            self._facade = None
            self._registry = None
            self._guardrails = None
            self._status = HealthStatus.UNKNOWN

    # -- event bus ---------------------------------------------------------
    def set_event_bus(self, event_bus: EventBus) -> None:
        with self._lock:
            self._event_bus = event_bus

    def get_event_bus(self) -> EventBus | None:
        with self._lock:
            return self._event_bus

    # -- classic validation API --------------------------------------------
    def validate(self, name: str, text: str, context: dict[str, Any] | None = None) -> GuardResult:
        """Validate text through a named guard via the classic facade."""
        return self.facade.validate(name, text, context)

    def register_guard(self, guard: Guard) -> Guard:
        """Register a guard on the classic facade."""
        return self.facade.register_guard(guard)

    def list_guards(self) -> list[str]:
        """List classic facade guard names."""
        return self.facade.list_guards()

    # -- plugin-layer API --------------------------------------------------
    def list_validators(self) -> list[str]:
        """List validator names registered in the plugin registry."""
        return self.registry.list_validators()

    def register_validator(
        self, name: str, data_type: str = "string"
    ) -> Callable[[type[Validator]], type[Validator]]:
        """Register a plugin validator (decorator) into the module registry."""
        return self.registry.register_validator(name, data_type)

    def get_registry(self) -> ValidatorRegistry:
        return self.registry

    # -- defaults ----------------------------------------------------------
    @staticmethod
    def _register_default_guards(facade: GuardRailFacade) -> None:
        facade.register_guard(Guard(name="pii", validators=[NoPIIValidator()], on_fail="fix"))
        facade.register_guard(
            Guard(name="toxic", validators=[NoToxicValidator()], on_fail="filter")
        )
        facade.register_guard(
            Guard(name="injection", validators=[NoPromptInjectionValidator()], on_fail="raise")
        )
        facade.register_guard(
            Guard(name="length", validators=[LengthValidator(min=1, max=200)], on_fail="fix")
        )

    @staticmethod
    def _register_plugin_guards(guardrails: Guardrails) -> None:
        default_guards: list[Guard] = [
            Guard(name="pii", validators=[PIIValidator()]),
            Guard(name="injection", validators=[PromptInjectionValidator()]),
            Guard(name="jailbreak", validators=[JailbreakValidator()]),
            Guard(name="shell_injection", validators=[ShellInjectionValidator()]),
            Guard(name="sql_injection", validators=[SQLInjectionValidator()]),
            Guard(name="toxic_language", validators=[ToxicLanguageValidator()]),
            Guard(name="secret_leak", validators=[SecretLeakValidator()]),
            Guard(name="url", validators=[URLValidator()]),
        ]
        for guard in default_guards:
            guardrails.register_guard(guard)


def create_guardrails_facade(
    config: dict[str, Any] | None = None,
    with_defaults: bool = True,
) -> GuardRailFacade:
    """Create a standalone classic GuardRailFacade (convenience helper)."""
    facade = GuardRailFacade(config)
    if with_defaults:
        GuardrailsModule._register_default_guards(facade)
    return facade


def create_guardrails_module(config: dict[str, Any] | None = None) -> GuardrailsModule:
    """Create a standalone GuardrailsModule instance (module contract)."""
    return GuardrailsModule(config)
