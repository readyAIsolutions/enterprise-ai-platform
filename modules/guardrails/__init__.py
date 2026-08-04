"""ENI Guardrails OS Module.

Programmable input/output validators with a validate / fix / refix loop,
inspired by guardrails-ai but fully offline and stdlib-only.

Features:
- Validator base (name, validate(text, context) -> ValidationResult)
- Built-ins: NoPII, NoToxic, JSONSchema, Profanity, Length, Regex,
  NoPromptInjection validators
- Guard dataclass binding validators to on_fail policy
  ('filter' | 'raise' | 'fix' | 'refix') plus fail_action hold/continue
- GuardRailRunner orchestration with fix + refix loops and
  GuardrailViolationError on 'raise'
- GuardRailFacade registry (register_guard / validate / list_guards)
- GuardrailsModule: kernel @module lifecycle service exposing the facade
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Dict, List, Optional

from enterprise.platform_kernel import (
    EventBus,
    HealthStatus,
    Module,
    module,
)

from .guardrails import (
    Guard,
    GuardRailFacade,
    GuardRailRunner,
    GuardrailViolationError,
    GuardResult,
    JSONSchemaValidator,
    LengthValidator,
    NoPIIValidator,
    NoPromptInjectionValidator,
    NoToxicValidator,
    ProfanityValidator,
    RegexValidator,
    ValidationResult,
    Validator,
)

__version__ = "1.0.0"
__module__ = "guardrails"

__all__ = [
    "__version__",
    "GuardrailsModule",
    "Guard",
    "GuardRailFacade",
    "GuardRailRunner",
    "GuardrailViolationError",
    "GuardResult",
    "ValidationResult",
    "Validator",
    "NoPIIValidator",
    "NoToxicValidator",
    "JSONSchemaValidator",
    "ProfanityValidator",
    "LengthValidator",
    "RegexValidator",
    "NoPromptInjectionValidator",
]

_logger = logging.getLogger("enterprise.guardrails")


@module(name="guardrails", version="1.0.0",
        config_defaults={"default_guards": True})
class GuardrailsModule(Module):
    """Kernel service exposing the GuardRailFacade."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self._event_bus: Optional[EventBus] = None
        self._facade: Optional[GuardRailFacade] = None
        self._lock = threading.RLock()

    @property
    def facade(self) -> GuardRailFacade:
        with self._lock:
            if self._facade is None:
                raise RuntimeError("Guardrails module not initialized")
            return self._facade

    async def initialize(self) -> None:
        with self._lock:
            self._status = HealthStatus.STARTING
            _logger.info("Initializing Guardrails Module...")
            self._facade = GuardRailFacade(self._config)
            if self._config.get("default_guards", True):
                self._register_default_guards(self._facade)
            self._status = HealthStatus.HEALTHY
            _logger.info("Guardrails Module initialized")

    async def health_check(self) -> HealthStatus:
        with self._lock:
            if self._facade is not None and self._status == HealthStatus.HEALTHY:
                return HealthStatus.HEALTHY
            return HealthStatus.UNHEALTHY

    async def shutdown(self) -> None:
        with self._lock:
            self._status = HealthStatus.STOPPING
            _logger.info("Shutting down Guardrails Module...")
            self._facade = None
            self._status = HealthStatus.UNKNOWN

    def set_event_bus(self, event_bus: EventBus) -> None:
        with self._lock:
            self._event_bus = event_bus

    def get_event_bus(self) -> Optional[EventBus]:
        with self._lock:
            return self._event_bus

    def validate(self, name: str, text: str,
                 context: Optional[Dict[str, Any]] = None) -> GuardResult:
        """Validate text through a named guard via the module facade."""
        return self.facade.validate(name, text, context)

    def register_guard(self, guard: Guard) -> Guard:
        """Register a guard on the module facade."""
        return self.facade.register_guard(guard)

    def list_guards(self) -> List[str]:
        """List registered guard names."""
        return self.facade.list_guards()

    @staticmethod
    def _register_default_guards(facade: GuardRailFacade) -> None:
        facade.register_guard(
            Guard(name="pii", validators=[NoPIIValidator()], on_fail="fix")
        )
        facade.register_guard(
            Guard(name="toxic", validators=[NoToxicValidator()], on_fail="filter")
        )
        facade.register_guard(
            Guard(name="injection",
                  validators=[NoPromptInjectionValidator()],
                  on_fail="raise")
        )
        facade.register_guard(
            Guard(name="length",
                  validators=[LengthValidator(min=1, max=200)],
                  on_fail="fix")
        )


def create_guardrails_facade(
    config: Optional[Dict[str, Any]] = None,
    with_defaults: bool = True,
) -> GuardRailFacade:
    """Create a standalone GuardRailFacade (convenience helper)."""
    facade = GuardRailFacade(config)
    if with_defaults:
        GuardrailsModule._register_default_guards(facade)
    return facade
