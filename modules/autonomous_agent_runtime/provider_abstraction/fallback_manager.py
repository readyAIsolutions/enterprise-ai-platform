"""
Fallback Manager — Circuit Breaker + Fallback Chains
=====================================================

Implements circuit breaker pattern with automatic failover across provider chains.
Supports configurable failure thresholds, half-open state, and fallback priorities.

Follows ENI patterns: stdlib-first, async-native, comprehensive type hints.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from .provider_interface import (
    ChatProvider,
    CircuitState,
    CompletionRequest,
    CompletionResponse,
    ProviderError,
    ProviderUnavailableError,
    RateLimitError,
)
from .config_schema import CircuitBreakerConfig, ProviderConfig, ProviderType

logger = logging.getLogger("provider_abstraction.fallback")


class FallbackStrategy(str, Enum):
    """Fallback selection strategy."""

    PRIORITY = "priority"  # Use provider priority order
    ROUND_ROBIN = "round_robin"  # Rotate through available
    LEAST_LOADED = "least_loaded"  # Pick provider with fewest active requests
    FASTEST = "fastest"  # Pick provider with lowest latency
    COST_OPTIMIZED = "cost_optimized"  # Pick cheapest provider


@dataclass
class FallbackAttempt:
    """Record of a fallback attempt."""

    provider_name: str
    model: str
    error: str | None
    latency_ms: float
    timestamp: float = field(default_factory=time.time)
    success: bool = False


@dataclass
class FallbackResult:
    """Result of fallback chain execution."""

    response: CompletionResponse | None = None
    attempts: list[FallbackAttempt] = field(default_factory=list)
    final_provider: str | None = None
    total_latency_ms: float = 0.0
    exhausted: bool = False


class CircuitBreaker:
    """
    Circuit breaker for individual providers.

    States:
    - CLOSED: Normal operation, requests pass through
    - OPEN: Failing fast, requests rejected immediately
    - HALF_OPEN: Testing recovery, limited requests allowed
    """

    def __init__(self, config: CircuitBreakerConfig, provider_name: str) -> None:
        self.config = config
        self.provider_name = provider_name
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: float | None = None
        self.last_state_change = time.time()
        self._lock = asyncio.Lock()

    @property
    def is_open(self) -> bool:
        return self.state == CircuitState.OPEN

    @property
    def is_half_open(self) -> bool:
        return self.state == CircuitState.HALF_OPEN

    @property
    def is_closed(self) -> bool:
        return self.state == CircuitState.CLOSED

    async def can_execute(self) -> bool:
        """Check if request can proceed."""
        async with self._lock:
            if self.state == CircuitState.CLOSED:
                return True

            if self.state == CircuitState.OPEN:
                # Check if timeout elapsed to transition to half-open
                if self.last_failure_time and (time.time() - self.last_failure_time) >= self.config.timeout_seconds:
                    self.state = CircuitState.HALF_OPEN
                    self.success_count = 0
                    logger.info(f"Circuit breaker for {self.provider_name} transitioned to HALF_OPEN")
                    return True
                return False

            # HALF_OPEN: allow one request through
            return True

    async def record_success(self) -> None:
        """Record successful call."""
        async with self._lock:
            self.failure_count = 0

            if self.state == CircuitState.HALF_OPEN:
                self.success_count += 1
                if self.success_count >= self.config.success_threshold:
                    self.state = CircuitState.CLOSED
                    self.last_state_change = time.time()
                    logger.info(f"Circuit breaker for {self.provider_name} CLOSED after recovery")

    async def record_failure(self, error: Exception) -> None:
        """Record failed call."""
        async with self._lock:
            # Check if error is excluded
            excluded = self.config.excluded_exceptions
            error_type = type(error).__name__
            if any(error_type == exc.split(".")[-1] for exc in excluded):
                return

            self.failure_count += 1
            self.last_failure_time = time.time()

            if self.state == CircuitState.HALF_OPEN:
                # Any failure in half-open goes back to open
                self.state = CircuitState.OPEN
                self.last_state_change = time.time()
                logger.warning(f"Circuit breaker for {self.provider_name} OPEN after half-open failure")

            elif self.state == CircuitState.CLOSED:
                if self.failure_count >= self.config.failure_threshold:
                    self.state = CircuitState.OPEN
                    self.last_state_change = time.time()
                    logger.warning(
                        f"Circuit breaker for {self.provider_name} OPEN after {self.failure_count} failures"
                    )

    def get_state(self) -> dict[str, Any]:
        """Get circuit breaker state for monitoring."""
        return {
            "provider": self.provider_name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "last_failure_time": self.last_failure_time,
            "last_state_change": self.last_state_change,
        }

    async def reset(self) -> None:
        """Manually reset circuit breaker to closed."""
        async with self._lock:
            self.state = CircuitState.CLOSED
            self.failure_count = 0
            self.success_count = 0
            self.last_failure_time = None
            self.last_state_change = time.time()


class FallbackManager:
    """
    Manages fallback chains with circuit breakers.

    Features:
    - Per-provider circuit breakers
    - Configurable fallback strategies
    - Automatic failover with exponential backoff
    - Attempt tracking and metrics
    - Integration with provider registry
    """

    def __init__(
        self,
        providers: dict[str, ChatProvider],
        configs: dict[str, ProviderConfig],
        fallback_strategy: FallbackStrategy = FallbackStrategy.PRIORITY,
        metrics_callback: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> None:
        self.providers = providers
        self.configs = configs
        self.fallback_strategy = fallback_strategy
        self._metrics_callback = metrics_callback

        # Circuit breakers per provider
        self._circuit_breakers: dict[str, CircuitBreaker] = {}
        for name, config in configs.items():
            self._circuit_breakers[name] = CircuitBreaker(config.circuit_breaker, name)

        # Fallback attempt history
        self._attempt_history: list[FallbackAttempt] = []
        self._max_history = 1000

        # Active request tracking for least_loaded strategy
        self._active_requests: dict[str, int] = {name: 0 for name in providers}

    def _emit_metric(self, name: str, value: float, labels: dict[str, str] | None = None) -> None:
        if self._metrics_callback:
            try:
                self._metrics_callback(name, {"value": value, "labels": labels or {}})
            except Exception:
                pass

    async def execute_with_fallback(
        self,
        request: CompletionRequest,
        primary_provider: str,
        fallback_providers: list[str] | None = None,
        operation: Callable[[ChatProvider, CompletionRequest], Any] | None = None,
    ) -> FallbackResult:
        """
        Execute request with automatic fallback.

        Args:
            request: Completion request
            primary_provider: Primary provider name
            fallback_providers: Optional override fallback chain
            operation: Custom operation (default: provider.complete)

        Returns:
            FallbackResult with response or error info
        """
        if operation is None:
            operation = lambda p, r: p.complete(r)

        # Build fallback chain
        chain = [primary_provider]
        if fallback_providers:
            chain.extend(fallback_providers)
        elif primary_provider in self.configs:
            chain.extend(self.configs[primary_provider].fallback_providers)

        # Remove duplicates while preserving order
        seen = set()
        unique_chain = []
        for p in chain:
            if p not in seen and p in self.providers:
                seen.add(p)
                unique_chain.append(p)

        result = FallbackResult()
        start_time = time.time()

        for provider_name in unique_chain:
            provider = self.providers.get(provider_name)
            if not provider:
                logger.warning(f"Provider {provider_name} not found in registry")
                continue

            # Check circuit breaker
            cb = self._circuit_breakers.get(provider_name)
            if cb and not await cb.can_execute():
                attempt = FallbackAttempt(
                    provider_name=provider_name,
                    model=request.model,
                    error="Circuit breaker OPEN",
                    latency_ms=0.0,
                    success=False,
                )
                result.attempts.append(attempt)
                self._emit_metric("fallback_circuit_blocked", 1, {"provider": provider_name})
                continue

            # Track active request for least_loaded strategy
            self._active_requests[provider_name] = self._active_requests.get(provider_name, 0) + 1

            attempt_start = time.time()
            error: Exception | None = None

            try:
                response = await operation(provider, request)
                latency_ms = (time.time() - attempt_start) * 1000

                attempt = FallbackAttempt(
                    provider_name=provider_name,
                    model=request.model,
                    error=None,
                    latency_ms=latency_ms,
                    success=True,
                )
                result.attempts.append(attempt)

                if cb:
                    await cb.record_success()

                result.response = response
                result.final_provider = provider_name
                result.total_latency_ms = (time.time() - start_time) * 1000

                self._emit_metric("fallback_success", 1, {"provider": provider_name, "attempt": str(len(result.attempts))})
                logger.info(f"Request succeeded on provider {provider_name} (attempt {len(result.attempts)})")
                return result

            except Exception as e:
                error = e
                latency_ms = (time.time() - attempt_start) * 1000

                attempt = FallbackAttempt(
                    provider_name=provider_name,
                    model=request.model,
                    error=str(e),
                    latency_ms=latency_ms,
                    success=False,
                )
                result.attempts.append(attempt)

                if cb:
                    await cb.record_failure(e)

                self._emit_metric("fallback_failure", 1, {"provider": provider_name, "error_type": type(e).__name__})
                logger.warning(f"Provider {provider_name} failed: {e}")

            finally:
                self._active_requests[provider_name] = max(0, self._active_requests.get(provider_name, 1) - 1)

        # All providers exhausted
        result.exhausted = True
        result.total_latency_ms = (time.time() - start_time) * 1000
        self._emit_metric("fallback_exhausted", 1, {"primary": primary_provider})

        # Build comprehensive error
        errors = [f"{a.provider_name}: {a.error}" for a in result.attempts if a.error]
        raise ProviderUnavailableError(
            f"All providers exhausted: {'; '.join(errors)}",
            provider=primary_provider,
            retryable=True,
        )

    async def execute_stream_with_fallback(
        self,
        request: CompletionRequest,
        primary_provider: str,
        fallback_providers: list[str] | None = None,
    ):
        """Execute streaming request with fallback (yields from first successful provider)."""
        # For streaming, we can't easily fallback mid-stream
        # So we try primary, and if it fails before yielding, try fallback
        chain = [primary_provider]
        if fallback_providers:
            chain.extend(fallback_providers)
        elif primary_provider in self.configs:
            chain.extend(self.configs[primary_provider].fallback_providers)

        seen = set()
        unique_chain = []
        for p in chain:
            if p not in seen and p in self.providers:
                seen.add(p)
                unique_chain.append(p)

        for provider_name in unique_chain:
            provider = self.providers.get(provider_name)
            if not provider:
                continue

            cb = self._circuit_breakers.get(provider_name)
            if cb and not await cb.can_execute():
                continue

            try:
                async for chunk in provider.stream(request):  # type: ignore[attr-defined]
                    yield chunk
                if cb:
                    await cb.record_success()
                return  # Success, don't try fallbacks
            except Exception as e:
                if cb:
                    await cb.record_failure(e)
                logger.warning(f"Streaming provider {provider_name} failed: {e}")
                continue

        raise ProviderUnavailableError(
            "All streaming providers exhausted",
            provider=primary_provider,
            retryable=True,
        )

    def get_circuit_states(self) -> dict[str, dict[str, Any]]:
        """Get all circuit breaker states."""
        return {name: cb.get_state() for name, cb in self._circuit_breakers.items()}

    def get_active_requests(self) -> dict[str, int]:
        """Get active request counts per provider."""
        return dict(self._active_requests)

    def select_provider(self, available: list[str]) -> str | None:
        """Select provider based on strategy."""
        if not available:
            return None

        if self.fallback_strategy == FallbackStrategy.PRIORITY:
            # Sort by priority (lower = higher priority)
            return min(available, key=lambda p: self.configs.get(p, ProviderConfig(name=p, type="mock")).priority)

        elif self.fallback_strategy == FallbackStrategy.LEAST_LOADED:
            return min(available, key=lambda p: self._active_requests.get(p, 0))

        elif self.fallback_strategy == FallbackStrategy.FASTEST:
            # Would need latency tracking - fallback to priority for now
            return min(available, key=lambda p: self.configs.get(p, ProviderConfig(name=p, type=ProviderType.MOCK)).priority)

        elif self.fallback_strategy == FallbackStrategy.COST_OPTIMIZED:
            # Would need cost tracking - fallback to priority for now
            return min(available, key=lambda p: self.configs.get(p, ProviderConfig(name=p, type=ProviderType.MOCK)).priority)

        elif self.fallback_strategy == FallbackStrategy.ROUND_ROBIN:
            # Simple round-robin using attempt history
            last_provider = self._attempt_history[-1].provider_name if self._attempt_history else None
            idx = 0
            if last_provider in available:
                idx = (available.index(last_provider) + 1) % len(available)
            return available[idx]

        return available[0]

    def record_attempt(self, attempt: FallbackAttempt) -> None:
        """Record fallback attempt for history."""
        self._attempt_history.append(attempt)
        if len(self._attempt_history) > self._max_history:
            self._attempt_history.pop(0)

    def get_attempt_history(self, limit: int = 100) -> list[FallbackAttempt]:
        """Get recent fallback attempt history."""
        return self._attempt_history[-limit:]

    async def reset_circuit(self, provider_name: str) -> bool:
        """Manually reset a provider's circuit breaker."""
        cb = self._circuit_breakers.get(provider_name)
        if cb:
            await cb.reset()
            return True
        return False

    async def reset_all_circuits(self) -> None:
        """Reset all circuit breakers."""
        for cb in self._circuit_breakers.values():
            await cb.reset()


__all__ = [
    "FallbackStrategy",
    "FallbackAttempt",
    "FallbackResult",
    "CircuitBreaker",
    "FallbackManager",
]