"""ENI Model Router OS Module — enterprise model-routing / fallback gateway.

A production-grade, stdlib-only model-routing gateway ripped from the LiteLLM
retry/cooldown pattern. It manages a fleet of model deployments, selects healthy
ones per request via weighted (hash-bucket) selection, retries transient
failures per a per-exception-type policy, and falls back across a model group —
placing failing deployments into a time-based cooldown so they are excluded
from dispatch until they recover.

All components are stdlib-only (zero external dependencies beyond the kernel).
"""

from __future__ import annotations

import logging
from typing import Any  # noqa: F401

from enterprise.platform_kernel import EventBus, HealthStatus, Module, module  # noqa: F401

from .live import (
    LiveFailoverSmoke,
    LiveProbe,
    ProbeResult,
    ping_local_free_router,
)
from .model_router import (
    CAT_AUTH,
    CAT_OK,
    CAT_PROTOCOL,
    CAT_RATE_LIMIT,
    CAT_TIMEOUT,
    CAT_UNAVAILABLE,
    CAT_UNKNOWN,
    AuthenticationError,
    BaseProviderAdapter,
    CooldownCache,
    DeploymentModel,
    EchoAdapter,
    HTTPAdapter,
    ModelRouter,
    ModelRouterModule,
    NoDeploymentAvailableError,
    NoopAdapter,
    ProviderError,
    ProviderResponse,
    ProviderTimeoutError,
    RateLimitError,
    Router,
    RouteResult,
    ServiceUnavailableError,
    classify_http_error,
)

__version__ = "1.0.0"
__module__ = "model_router"

__all__ = [
    "__version__",
    # Module
    "ModelRouterModule",
    # Routing engine
    "Router",
    "ModelRouter",
    "DeploymentModel",
    "CooldownCache",
    "RouteResult",
    "ProviderResponse",
    # Adapters
    "BaseProviderAdapter",
    "HTTPAdapter",
    "EchoAdapter",
    "NoopAdapter",
    # Exceptions
    "ProviderError",
    "RateLimitError",
    "ProviderTimeoutError",
    "AuthenticationError",
    "ServiceUnavailableError",
    "NoDeploymentAvailableError",
    # Classification / diagnosis
    "classify_http_error",
    "CAT_AUTH",
    "CAT_RATE_LIMIT",
    "CAT_UNAVAILABLE",
    "CAT_TIMEOUT",
    "CAT_PROTOCOL",
    "CAT_UNKNOWN",
    "CAT_OK",
    # Live smoke / sanity
    "LiveProbe",
    "LiveFailoverSmoke",
    "ProbeResult",
    "ping_local_free_router",
]

_logger = logging.getLogger("enterprise.model_router")


def create_model_router_module(
    config: dict[str, Any] | None = None,
) -> ModelRouterModule:
    """Create a :class:`ModelRouterModule` from an optional config dict.

    Args:
        config: dict with ``deployments`` (list of deployment dicts),
            ``route_metrics`` (bool) and/or ``blacklist`` (list[str]).
    """
    return ModelRouterModule(config or {})
