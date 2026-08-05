"""Enterprise Secret Broker OS Module — local-first secret handling.

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
"""

from __future__ import annotations

from typing import Any  # noqa: F401

from enterprise.platform_kernel import HealthStatus, Module, module  # noqa: F401

from .secret_broker import (
    OutboundSecretLeakError,
    PlaceholderSubstituter,
    SecretBroker,
    SecretBrokerModule,
    SecretDetector,
    SecretHit,
    SubstitutionResult,
)

__version__ = "1.0.0"
__module__ = "secret_broker"

__all__ = [
    "__version__",
    "SecretBrokerModule",
    "SecretBroker",
    "SecretDetector",
    "SecretHit",
    "PlaceholderSubstituter",
    "SubstitutionResult",
    "OutboundSecretLeakError",
]


def create_secret_broker_module(config: dict[str, Any] | None = None) -> SecretBrokerModule:
    """Create a :class:`SecretBrokerModule` from an optional config dict.

    Args:
        config: dict optionally containing ``detector`` (min_entropy /
            entropy_token_min_len / max_results) and/or ``guard_mode``
            ('raise' | 'redact' | 'off').
    """
    return SecretBrokerModule(config or {})


_installed = SecretBrokerModule  # noqa: F841  (ensures @module registration on import)
