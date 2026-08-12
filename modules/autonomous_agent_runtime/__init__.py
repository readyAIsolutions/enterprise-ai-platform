"""ENI Autonomous Agent Runtime Module -- Multi-provider LLM abstraction.

A first-class Platform Kernel module that wraps the ``provider_abstraction``
subsystem: a multi-provider LLM abstraction (provider registry with health
checks), session-aware cost tracking, circuit-breaking fallback orchestration,
and SSE streaming normalization.

The module auto-registers with the Platform Kernel when this package is
imported (via the ``@module`` decorator), implementing the standard lifecycle
(``initialize`` / ``health_check`` / ``shutdown``), the event-bus wiring
contract (``set_event_bus``), and exposing a public
``AutonomousAgentRuntimeFacade`` with ``register_providers_from_config`` /
``list_providers`` / ``get_provider`` / ``cost_summary`` /
``fallback_status`` / ``health_check_all``.

Version: 1.0.0
Python: 3.11+
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from enterprise.platform_kernel import (
    Event,
    EventBus,
    EventPriority,
    HealthStatus,
    Module,
    module,
)

# ---------------------------------------------------------------------------
# Re-export the provider_abstraction public API
# ---------------------------------------------------------------------------
# Config schema
from .provider_abstraction.config_schema import (
    BUILTIN_PRICING,
    CircuitBreakerConfig,
    CircuitState,
    CostTrackingConfig,
    DEFAULT_CONFIG,
    HealthCheckConfig,
    HealthCheckStrategy,
    ProviderAbstractionConfig,
    ProviderConfig,
    ProviderType,
    RateLimitConfig,
    RetryPolicyConfig,
    StreamingConfig,
)

# Cost tracking
from .provider_abstraction.cost_tracker import CostTracker, SessionUsage, UsageRecord

# Fallback / circuit breaking
from .provider_abstraction.fallback_manager import (
    CircuitBreaker,
    FallbackAttempt,
    FallbackManager,
    FallbackResult,
    FallbackStrategy,
)

# Provider interface primitives
from .provider_abstraction.provider_interface import (
    AuthenticationError,
    ChatProvider,
    CompletionRequest,
    CompletionResponse,
    EmbeddingRequest,
    EmbeddingResponse,
    ModelNotFoundError,
    Message,
    ProviderError,
    ProviderMetrics,
    ProviderUnavailableError,
    RateLimitError,
    StreamChunk,
    StreamingProvider,
    ToolCall,
)

# Provider registry
from .provider_abstraction.provider_registry import (
    ProviderRegistration,
    ProviderRegistry,
    get_registry,
    set_registry,
)

# Concrete providers (checked in this checkout)
from .provider_abstraction.providers.openai_compatible import OpenAICompatibleProvider

# Streaming adapter
from .provider_abstraction.streaming_adapter import (
    MultiProviderStreamingAdapter,
    SSEEvent,
    StreamingAdapter,
)

__version__ = "1.0.0"
__module__ = "autonomous_agent_runtime"

__all__ = [
    "__version__",
    "AutonomousAgentRuntimeModule",
    "AutonomousAgentRuntimeFacade",
    "create_autonomous_agent_runtime_module",
    # Provider interface
    "ChatProvider",
    "StreamingProvider",
    "CompletionRequest",
    "CompletionResponse",
    "EmbeddingRequest",
    "EmbeddingResponse",
    "Message",
    "ToolCall",
    "ProviderMetrics",
    "StreamChunk",
    "ProviderError",
    "ProviderUnavailableError",
    "AuthenticationError",
    "ModelNotFoundError",
    "RateLimitError",
    # Config
    "ProviderAbstractionConfig",
    "ProviderConfig",
    "ProviderType",
    "CircuitBreakerConfig",
    "CostTrackingConfig",
    "HealthCheckConfig",
    "HealthCheckStrategy",
    "RateLimitConfig",
    "RetryPolicyConfig",
    "StreamingConfig",
    "CircuitState",
    "BUILTIN_PRICING",
    "DEFAULT_CONFIG",
    # Registry
    "ProviderRegistry",
    "ProviderRegistration",
    "get_registry",
    "set_registry",
    # Cost tracker
    "CostTracker",
    "SessionUsage",
    "UsageRecord",
    # Fallback
    "FallbackManager",
    "FallbackResult",
    "FallbackAttempt",
    "FallbackStrategy",
    "CircuitBreaker",
    # Streaming
    "StreamingAdapter",
    "MultiProviderStreamingAdapter",
    "SSEEvent",
    # Provider
    "OpenAICompatibleProvider",
]

_logger = logging.getLogger("enterprise.autonomous_agent_runtime")


def _build_config(raw: dict[str, Any] | None) -> ProviderAbstractionConfig:
    """Coerce a plain dict into a :class:`ProviderAbstractionConfig`.

    Nested ``providers`` entries (plain dicts) are coerced by pydantic into
    :class:`ProviderConfig` instances; unknown keys are ignored.
    """
    raw = dict(raw or {})
    known = set(ProviderAbstractionConfig.model_fields.keys())
    kwargs = {k: v for k, v in raw.items() if k in known}
    return ProviderAbstractionConfig(**kwargs)


def _create_registry(config: ProviderAbstractionConfig) -> ProviderRegistry:
    """Build a :class:`ProviderRegistry` guarding against missing built-ins.

    ``ProviderRegistry.__init__`` eagerly imports a set of built-in provider
    modules (anthropic, google_gemini, local_ollama, local_llamacpp, mock)
    that may not be present in a given checkout. When that fails we fall back
    to a minimal registry wired to the providers that actually exist here
    (``OpenAICompatibleProvider``), preserving the normal registration and
    lookup behaviour.
    """
    try:
        registry = ProviderRegistry(config)
    except Exception:  # noqa: BLE001 - defensive fallback for partial checkouts
        registry = ProviderRegistry.__new__(ProviderRegistry)
        registry.config = config
        registry._metrics_callback = None
        registry._registrations = {}
        registry._provider_classes = {
            ProviderType.OPENAI_COMPATIBLE: OpenAICompatibleProvider,
        }
    registry.register_all_from_config()
    return registry


def _registry_snapshot(
    registry: ProviderRegistry,
) -> tuple[dict[str, ChatProvider], dict[str, ProviderConfig]]:
    """Return ``(providers, configs)`` for the enabled registered providers."""
    providers: dict[str, ChatProvider] = {}
    configs: dict[str, ProviderConfig] = {}
    for name in registry.list_providers(enabled_only=True):
        try:
            providers[name] = registry.get(name)
            reg = registry._registrations.get(name)
            if reg is not None:
                configs[name] = reg.config
        except Exception:  # noqa: BLE001
            _logger.warning("Skipping unavailable provider %r", name)
    return providers, configs


class AutonomousAgentRuntimeFacade:
    """Public operations facade for the autonomous agent runtime providers.

    Owns the provider registry, cost tracker, fallback manager and streaming
    adapter, and exposes high-level operations used by callers and by the
    :class:`AutonomousAgentRuntimeModule`.
    """

    def __init__(
        self,
        *,
        config: ProviderAbstractionConfig | None = None,
        registry: ProviderRegistry | None = None,
        track_costs: bool = True,
    ) -> None:
        self.config = (
            config
            if isinstance(config, ProviderAbstractionConfig)
            else _build_config(config)
        )
        self.registry = registry or _create_registry(self.config)
        self.track_costs = bool(track_costs)
        self._lock = threading.RLock()

        # Cost tracking
        if self.track_costs:
            cost_cfg = self.config.cost_tracking if hasattr(self.config, "cost_tracking") else None
            try:
                self.cost_tracker: CostTracker | None = CostTracker(cost_cfg)
            except Exception:  # noqa: BLE001
                self.cost_tracker = CostTracker()
        else:
            self.cost_tracker = None

        # Fallback manager
        providers, configs = _registry_snapshot(self.registry)
        self.providers = providers
        self.fallback_manager = FallbackManager(
            providers,
            configs,
            fallback_strategy=self._fallback_strategy(),
        )

        # Streaming adapter
        self.streaming_adapter: MultiProviderStreamingAdapter | None = None
        if providers:
            primary = self.config.default_provider or next(iter(providers))
            fallbacks = self.registry.get_fallback_chain(primary)
            fallback_names = [p.name for p in fallbacks if p.name != primary]
            stream_cfg = self.config.streaming if hasattr(self.config, "streaming") else None
            self.streaming_adapter = MultiProviderStreamingAdapter(
                providers,
                primary,
                fallback_names,
                config=stream_cfg,
            )

    def _fallback_strategy(self) -> FallbackStrategy:
        # The platform falls back in a deterministic priority order; the
        # strategy can be overridden by more specific configuration in future.
        return FallbackStrategy.PRIORITY

    # -- Provider registration ----------------------------------------------

    def register_providers_from_config(
        self,
        config: ProviderAbstractionConfig | dict[str, Any] | None = None,
    ) -> int:
        """Register every enabled provider from ``config`` (or the stored one).

        Returns the number of providers registered.
        """
        with self._lock:
            if config is not None:
                cfg = config if isinstance(config, ProviderAbstractionConfig) else _build_config(config)
                self.registry.config = cfg
                self.config = cfg
            before = set(self.registry.list_providers(enabled_only=False))
            self.registry.register_all_from_config()
            after = set(self.registry.list_providers(enabled_only=False))
            # Refresh the fallback manager + streaming adapter views.
            providers, configs = _registry_snapshot(self.registry)
            self.providers = providers
            self.fallback_manager = FallbackManager(
                providers,
                configs,
                fallback_strategy=self._fallback_strategy(),
            )
            return len(after - before)

    def list_providers(self, enabled_only: bool = True) -> list[str]:
        """Return the names of registered providers."""
        return self.registry.list_providers(enabled_only=enabled_only)

    def get_provider(self, name: str) -> ChatProvider:
        """Return the provider instance for ``name`` (raises if unknown)."""
        return self.registry.get(name)

    # -- Cost summary -------------------------------------------------------

    def cost_summary(self) -> dict[str, Any]:
        """Aggregate total usage, budget status and daily usage."""
        if self.cost_tracker is None:
            return {"enabled": False}
        try:
            return {
                "enabled": True,
                "total": self.cost_tracker.get_total_usage(),
                "budget": self.cost_tracker.get_budget_status(),
                "daily": self.cost_tracker.get_daily_usage(),
            }
        except Exception:  # noqa: BLE001
            _logger.exception("Failed to build cost summary")
            return {"enabled": True, "error": "cost_summary_failed"}

    # -- Fallback status ----------------------------------------------------

    def fallback_status(self) -> dict[str, Any]:
        """Return circuit states, active requests and recent attempts."""
        try:
            return {
                "circuits": self.fallback_manager.get_circuit_states(),
                "active_requests": self.fallback_manager.get_active_requests(),
                "recent_attempts": self.fallback_manager.get_attempt_history(limit=20),
            }
        except Exception:  # noqa: BLE001
            _logger.exception("Failed to build fallback status")
            return {}

    async def reset_circuit(self, provider_name: str) -> bool:
        """Manually reset the circuit breaker for ``provider_name``."""
        return await self.fallback_manager.reset_circuit(provider_name)

    async def reset_all_circuits(self) -> None:
        """Reset every circuit breaker."""
        await self.fallback_manager.reset_all_circuits()

    # -- Health -------------------------------------------------------------

    async def health_check_all(self, force: bool = False) -> dict[str, HealthStatus]:
        """Run health checks across all registered providers."""
        return await self.registry.health_check_all(force=force)

    def close(self) -> None:
        """Release providers and streaming resources."""
        try:
            if self.streaming_adapter is not None:
                self.streaming_adapter.close()
        except Exception:  # noqa: BLE001
            pass


@module(name="autonomous_agent_runtime", version="1.0.0")
class AutonomousAgentRuntimeModule(Module):
    """Enterprise Autonomous Agent Runtime Module.

    Wraps an :class:`AutonomousAgentRuntimeFacade` behind the Platform Kernel
    module lifecycle, exposing the facade operations (``register_providers_from_config``,
    ``list_providers``, ``get_provider``, ``cost_summary``, ``fallback_status``,
    ``health_check_all``).

    Configuration (dict passed to ``__init__``):
        - ``providers`` (list[dict]): provider configs, each with at least
          ``name`` and ``type`` (see ``ProviderType``).
        - ``default_provider`` (str): name of the default provider.
        - ``fallback_chain`` (list[str]): global fallback ordering.
        - ``enable_cost_tracking`` (bool): build the cost tracker (default True).
        - Any other key accepted by ``ProviderAbstractionConfig``.

    Events published (when an event bus is wired via ``set_event_bus``):
        - ``autonomous_agent_runtime.provider.registered`` -- a provider was registered.
        - ``autonomous_agent_runtime.initialized`` -- the module finished init.
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._facade: AutonomousAgentRuntimeFacade | None = None
        self._event_bus: EventBus | None = None
        self._lock = threading.RLock()
        self._track_costs = bool(self._config.get("enable_cost_tracking", True))

    # -- Properties ---------------------------------------------------------

    @property
    def facade(self) -> AutonomousAgentRuntimeFacade | None:
        """Return the active facade (None before initialization)."""
        with self._lock:
            return self._facade

    # -- Lifecycle ----------------------------------------------------------

    async def initialize(self) -> None:
        """Build the facade and mark the module healthy."""
        with self._lock:
            self._status = HealthStatus.STARTING
        _logger.info(
            "autonomous_agent_runtime module initializing (track_costs=%s)",
            self._track_costs,
        )
        try:
            cfg = _build_config(self._config)
            facade = AutonomousAgentRuntimeFacade(
                config=cfg,
                track_costs=self._track_costs,
            )
            with self._lock:
                self._facade = facade
                self._status = HealthStatus.HEALTHY
            registered = facade.list_providers()
            _logger.info(
                "autonomous_agent_runtime module initialized (providers=%s)",
                registered,
            )
            self._emit(
                "autonomous_agent_runtime.initialized",
                {"providers": registered},
            )
        except Exception as exc:  # noqa: BLE001 - lifecycle must report UNHEALTHY
            _logger.exception("Failed to initialize autonomous_agent_runtime module: %s", exc)
            with self._lock:
                self._status = HealthStatus.UNHEALTHY
            raise

    async def health_check(self) -> HealthStatus:
        """A healthy module has an initialized facade."""
        with self._lock:
            if self._facade is not None and self._status is HealthStatus.HEALTHY:
                return HealthStatus.HEALTHY
            if self._status is HealthStatus.UNHEALTHY:
                return HealthStatus.UNHEALTHY
            self._status = HealthStatus.UNKNOWN
            return self._status

    async def shutdown(self) -> None:
        """Gracefully shut down, releasing the facade and its resources."""
        with self._lock:
            self._status = HealthStatus.STOPPING
            _logger.info("Shutting down autonomous_agent_runtime module...")
            facade = self._facade
            self._facade = None
            if facade is not None:
                try:
                    facade.close()
                except Exception:  # noqa: BLE001
                    pass
            self._status = HealthStatus.HEALTHY

    # -- Event Bus Wiring ---------------------------------------------------

    def set_event_bus(self, event_bus: EventBus) -> None:
        """Wire the platform EventBus into this module."""
        with self._lock:
            self._event_bus = event_bus

    # -- Public facade ------------------------------------------------------

    def register_providers_from_config(
        self,
        config: ProviderAbstractionConfig | dict[str, Any] | None = None,
    ) -> int:
        """Register providers from ``config``; returns count registered."""
        count = self._require_facade().register_providers_from_config(config)
        self._emit(
            "autonomous_agent_runtime.provider.registered",
            {"count": count, "providers": self._require_facade().list_providers()},
        )
        return count

    def list_providers(self, enabled_only: bool = True) -> list[str]:
        """List registered provider names."""
        return self._require_facade().list_providers(enabled_only=enabled_only)

    def get_provider(self, name: str) -> ChatProvider:
        """Return the provider instance for ``name``."""
        return self._require_facade().get_provider(name)

    def cost_summary(self) -> dict[str, Any]:
        """Return an aggregate cost summary."""
        return self._require_facade().cost_summary()

    def fallback_status(self) -> dict[str, Any]:
        """Return circuit + fallback status."""
        return self._require_facade().fallback_status()

    async def reset_circuit(self, provider_name: str) -> bool:
        """Reset the circuit breaker for ``provider_name``."""
        return await self._require_facade().reset_circuit(provider_name)

    async def health_check_all(self, force: bool = False) -> dict[str, HealthStatus]:
        """Run health checks across all registered providers."""
        return await self._require_facade().health_check_all(force=force)

    # -- Helpers ------------------------------------------------------------

    def _require_facade(self) -> AutonomousAgentRuntimeFacade:
        facade = self.facade
        if facade is None:
            msg = "autonomous_agent_runtime module is not initialized"
            raise RuntimeError(msg)
        return facade

    def _emit(self, topic: str, payload: dict[str, Any]) -> None:
        with self._lock:
            bus = self._event_bus
        if bus is None:
            return
        try:
            bus.publish(
                Event.create(
                    topic,
                    source=self.name,
                    payload=payload,
                    priority=EventPriority.NORMAL,
                )
            )
        except Exception as exc:  # noqa: BLE001 - defensive
            _logger.warning("Failed to publish event %s: %s", topic, exc)


def create_autonomous_agent_runtime_module(
    config: dict[str, Any] | None = None,
) -> AutonomousAgentRuntimeModule:
    """Create (but do not initialize) an :class:`AutonomousAgentRuntimeModule`.

    Args:
        config: Optional dict. Supported keys:
            - ``providers`` (list[dict]): provider configs (each: ``name``, ``type``).
            - ``default_provider`` (str): name of the default provider.
            - ``fallback_chain`` (list[str]): global fallback ordering.
            - ``enable_cost_tracking`` (bool): build the cost tracker (default True).
    """
    return AutonomousAgentRuntimeModule(config=config or {})
