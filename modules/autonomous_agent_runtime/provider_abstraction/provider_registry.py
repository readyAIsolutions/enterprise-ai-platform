"""
Provider Registry — Discovery, Registration, Health Checks
===========================================================

Registry for provider discovery, instantiation, health monitoring,
and lifecycle management. Integrates with ENI agent_core patterns.

Follows ENI patterns: stdlib-first, async-native, comprehensive type hints.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .config_schema import ProviderAbstractionConfig, ProviderConfig, ProviderType
from .provider_interface import (
    ChatProvider,
    HealthStatus,
    ProviderError,
    ProviderMetrics,
)

logger = logging.getLogger("provider_abstraction.registry")


@dataclass
class ProviderRegistration:
    """Provider registration entry."""

    config: ProviderConfig
    provider_class: type[ChatProvider]
    instance: ChatProvider | None = None
    created_at: float = field(default_factory=time.time)
    last_health_check: float = 0.0
    health_status: HealthStatus = field(default_factory=lambda: HealthStatus(healthy=True))


class ProviderRegistry:
    """
    Registry for provider discovery, instantiation, and health management.

    Features:
    - Config-driven provider registration from YAML/JSON
    - Lazy instantiation with caching
    - Periodic health checks with callbacks
    - Provider discovery from entry points
    - Metrics aggregation across all providers
    """

    def __init__(
        self,
        config: ProviderAbstractionConfig | None = None,
        metrics_callback: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> None:
        self.config = config or ProviderAbstractionConfig()
        self._metrics_callback = metrics_callback
        self._registrations: dict[str, ProviderRegistration] = {}
        self._health_check_task: asyncio.Task | None = None
        self._health_check_interval = 30.0
        self._shutdown_event = asyncio.Event()
        self._register_builtins()

    def _register_builtins(self) -> None:
        """Register built-in provider classes."""
        # Import here to avoid circular imports
        from .providers.openai_compatible import OpenAICompatibleProvider
        from .providers.anthropic import AnthropicProvider
        from .providers.google_gemini import GoogleGeminiProvider
        from .providers.local_ollama import LocalOllamaProvider
        from .providers.local_llamacpp import LocalLlamaCppProvider
        from .providers.mock import MockProvider, EchoProvider

        self._provider_classes: dict[ProviderType, type[ChatProvider]] = {
            ProviderType.OPENAI_COMPATIBLE: OpenAICompatibleProvider,
            ProviderType.ANTHROPIC: AnthropicProvider,
            ProviderType.GOOGLE_GEMINI: GoogleGeminiProvider,
            ProviderType.LOCAL_OLLAMA: LocalOllamaProvider,
            ProviderType.LOCAL_LLAMACPP: LocalLlamaCppProvider,
            ProviderType.MOCK: MockProvider,
            ProviderType.ECHO: EchoProvider,
        }

    def register_provider_class(self, provider_type: ProviderType, provider_class: type[ChatProvider]) -> None:
        """Register a custom provider class for a type."""
        self._provider_classes[provider_type] = provider_class

    def register_from_config(self, provider_config: ProviderConfig) -> None:
        """Register a provider from configuration."""
        if provider_config.name in self._registrations:
            logger.warning(f"Provider {provider_config.name} already registered, replacing")

        provider_class = self._provider_classes.get(provider_config.type)
        if not provider_class:
            raise ValueError(f"No provider class registered for type: {provider_config.type}")

        self._registrations[provider_config.name] = ProviderRegistration(
            config=provider_config,
            provider_class=provider_class,
        )
        logger.info(f"Registered provider: {provider_config.name} ({provider_config.type.value})")

    def register_all_from_config(self) -> None:
        """Register all providers from the main config."""
        for pc in self.config.providers:
            if pc.enabled:
                self.register_from_config(pc)

    def get(self, name: str, fresh: bool = False) -> ChatProvider:
        """
        Get or create a provider instance.

        Args:
            name: Provider name
            fresh: Force creation of new instance

        Returns:
            Provider instance

        Raises:
            KeyError: If provider not registered
        """
        reg = self._registrations.get(name)
        if not reg:
            raise KeyError(f"Provider {name!r} not registered. Available: {list(self._registrations.keys())}")

        if reg.instance is None or fresh:
            reg.instance = reg.provider_class(
                reg.config,
                metrics_callback=self._metrics_callback,
            )
            logger.debug(f"Created provider instance: {name}")

        return reg.instance

    def get_or_create_default(self) -> ChatProvider:
        """Get the default provider, or first available."""
        if self.config.default_provider:
            try:
                return self.get(self.config.default_provider)
            except KeyError:
                pass

        # Fallback to first enabled provider by priority
        enabled = [r for r in self._registrations.values() if r.config.enabled]
        if not enabled:
            raise RuntimeError("No providers registered")
        enabled.sort(key=lambda r: r.config.priority)
        return self.get(enabled[0].config.name)

    def get_fallback_chain(self, primary: str | None = None) -> list[ChatProvider]:
        """Get fallback chain for a primary provider."""
        chain_names: list[str] = []

        if primary and primary in self._registrations:
            chain_names = self._registrations[primary].config.fallback_providers
        elif self.config.fallback_chain:
            chain_names = self.config.fallback_chain
        else:
            # Build chain from all enabled providers by priority
            enabled = [r for r in self._registrations.values() if r.config.enabled]
            enabled.sort(key=lambda r: r.config.priority)
            chain_names = [r.config.name for r in enabled]

        chain = []
        for name in chain_names:
            try:
                chain.append(self.get(name))
            except KeyError:
                logger.warning(f"Fallback provider {name} not registered, skipping")

        return chain

    def list_providers(self, enabled_only: bool = True) -> list[str]:
        """List registered provider names."""
        if enabled_only:
            return [name for name, reg in self._registrations.items() if reg.config.enabled]
        return list(self._registrations.keys())

    def get_provider_info(self, name: str) -> dict[str, Any] | None:
        """Get provider metadata."""
        reg = self._registrations.get(name)
        if not reg:
            return None

        return {
            "name": reg.config.name,
            "type": reg.config.type.value,
            "enabled": reg.config.enabled,
            "priority": reg.config.priority,
            "default_model": reg.config.default_model,
            "supported_models": reg.config.supported_models,
            "has_instance": reg.instance is not None,
            "created_at": reg.created_at,
            "last_health_check": reg.last_health_check,
            "health_status": reg.health_status.__dict__,
            "metrics": reg.instance.metrics.to_dict() if reg.instance else {},
        }

    def get_all_metrics(self) -> dict[str, dict[str, Any]]:
        """Get aggregated metrics for all providers."""
        return {
            name: reg.instance.metrics.to_dict()
            for name, reg in self._registrations.items()
            if reg.instance
        }

    async def health_check(self, name: str, force: bool = False) -> HealthStatus:
        """Run health check on a specific provider."""
        reg = self._registrations.get(name)
        if not reg:
            return HealthStatus(healthy=False, error=f"Provider {name} not registered")

        # Check cache
        if not force and reg.last_health_check > 0:
            if time.time() - reg.last_health_check < reg.config.health_check.interval_seconds:
                return reg.health_status

        provider = self.get(name)
        try:
            status = await provider.health_check()
        except Exception as e:
            status = HealthStatus(healthy=False, error=str(e))

        reg.health_status = status
        reg.last_health_check = time.time()
        return status

    async def health_check_all(self, force: bool = False) -> dict[str, HealthStatus]:
        """Run health checks on all registered providers."""
        results = {}
        for name in self._registrations:
            results[name] = await self.health_check(name, force=force)
        return results

    def get_healthy_providers(self) -> list[ChatProvider]:
        """Get list of currently healthy provider instances."""
        healthy = []
        for name, reg in self._registrations.items():
            if reg.config.enabled and reg.health_status.healthy:
                try:
                    healthy.append(self.get(name))
                except Exception:
                    pass
        return healthy

    async def start_health_monitoring(self, interval: float | None = None) -> None:
        """Start background health monitoring."""
        if self._health_check_task and not self._health_check_task.done():
            return

        self._health_check_interval = interval or 30.0
        self._shutdown_event.clear()
        self._health_check_task = asyncio.create_task(self._health_monitor_loop())
        logger.info("Started provider health monitoring")

    async def stop_health_monitoring(self) -> None:
        """Stop background health monitoring."""
        self._shutdown_event.set()
        if self._health_check_task:
            await self._health_check_task
            self._health_check_task = None
        logger.info("Stopped provider health monitoring")

    async def _health_monitor_loop(self) -> None:
        """Background health check loop."""
        while not self._shutdown_event.is_set():
            try:
                await self.health_check_all()
            except Exception as e:
                logger.error(f"Health check error: {e}")

            try:
                await asyncio.wait_for(self._shutdown_event.wait(), timeout=self._health_check_interval)
            except TimeoutError:
                continue  # Normal loop iteration

    async def shutdown(self) -> None:
        """Shutdown registry and all providers."""
        await self.stop_health_monitoring()
        for reg in self._registrations.values():
            if reg.instance:
                shutdown_method = getattr(reg.instance, "shutdown", None)
                if callable(shutdown_method):
                    try:
                        result = shutdown_method()
                        if asyncio.iscoroutine(result):
                            await result
                    except Exception:
                        pass
        self._registrations.clear()
        logger.info("Provider registry shutdown complete")


# Global registry instance
_default_registry: ProviderRegistry | None = None


def get_registry(config: ProviderAbstractionConfig | None = None) -> ProviderRegistry:
    """Get or create the default provider registry."""
    global _default_registry
    if _default_registry is None:
        _default_registry = ProviderRegistry(config)
        _default_registry.register_all_from_config()
    return _default_registry


def set_registry(registry: ProviderRegistry) -> None:
    """Set the default provider registry."""
    global _default_registry
    _default_registry = registry


__all__ = [
    "ProviderRegistry",
    "ProviderRegistration",
    "get_registry",
    "set_registry",
]