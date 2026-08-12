"""
Provider Interface — Abstract Base Class
=======================================

Unified provider interface (ABC) that abstracts Anthropic, OpenAI, Google, local models.
Complete method signatures for chat completion, streaming, embeddings, and health checks.

Follows ENI patterns: stdlib-first, async-native, comprehensive type hints,
Prometheus metrics emission via callbacks.
"""

from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Callable

from .config_schema import (
    BUILTIN_PRICING,
    CircuitState,
    HealthCheckConfig,
    ProviderConfig,
    ProviderType,
    RetryPolicyConfig,
)


@dataclass
class ProviderMetrics:
    """Provider runtime metrics for Prometheus emission."""

    calls_total: int = 0
    calls_success: int = 0
    calls_failed: int = 0
    retries_total: int = 0
    total_latency_ms: float = 0.0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_cost_usd: float = 0.0
    circuit_breaker_trips: int = 0
    rate_limit_hits: int = 0
    last_error: str | None = None
    last_success_at: float | None = None
    last_failure_at: float | None = None

    def record_call(self, latency_ms: float, success: bool, prompt_tokens: int = 0, completion_tokens: int = 0, cost: float = 0.0, error: str | None = None) -> None:
        self.calls_total += 1
        self.total_latency_ms += latency_ms
        self.total_prompt_tokens += prompt_tokens
        self.total_completion_tokens += completion_tokens
        self.total_cost_usd += cost
        if success:
            self.calls_success += 1
            self.last_success_at = time.time()
        else:
            self.calls_failed += 1
            self.last_failure_at = time.time()
            self.last_error = error

    def record_retry(self) -> None:
        self.retries_total += 1

    def record_circuit_trip(self) -> None:
        self.circuit_breaker_trips += 1

    def record_rate_limit(self) -> None:
        self.rate_limit_hits += 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "calls_total": self.calls_total,
            "calls_success": self.calls_success,
            "calls_failed": self.calls_failed,
            "success_rate": self.calls_success / max(1, self.calls_total),
            "retries_total": self.retries_total,
            "avg_latency_ms": self.total_latency_ms / max(1, self.calls_total),
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_completion_tokens": self.total_completion_tokens,
            "total_tokens": self.total_prompt_tokens + self.total_completion_tokens,
            "total_cost_usd": round(self.total_cost_usd, 6),
            "circuit_breaker_trips": self.circuit_breaker_trips,
            "rate_limit_hits": self.rate_limit_hits,
            "last_error": self.last_error,
            "last_success_at": self.last_success_at,
            "last_failure_at": self.last_failure_at,
        }


@dataclass
class Message:
    """Normalized message format across all providers."""

    role: str  # "system", "user", "assistant", "tool"
    content: str | list[dict[str, Any]] = ""
    name: str | None = None
    tool_calls: list[dict[str, Any]] | None = None
    tool_call_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = {"role": self.role, "content": self.content}
        if self.name:
            d["name"] = self.name
        if self.tool_calls:
            d["tool_calls"] = self.tool_calls
        if self.tool_call_id:
            d["tool_call_id"] = self.tool_call_id
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Message:
        return cls(
            role=data.get("role", "user"),
            content=data.get("content", ""),
            name=data.get("name"),
            tool_calls=data.get("tool_calls"),
            tool_call_id=data.get("tool_call_id"),
        )


@dataclass
class ToolCall:
    """Normalized tool call format."""

    id: str
    name: str
    arguments: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "type": "function", "function": {"name": self.name, "arguments": self.arguments}}


@dataclass
class CompletionRequest:
    """Unified completion request."""

    messages: list[Message]
    model: str
    temperature: float = 0.7
    max_tokens: int | None = None
    top_p: float | None = None
    stop: list[str] | None = None
    stream: bool = False
    tools: list[dict[str, Any]] | None = None
    tool_choice: str | dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class CompletionResponse:
    """Unified completion response."""

    text: str
    model: str
    provider: str
    usage: dict[str, int] = field(default_factory=dict)
    finish_reason: str | None = None
    tool_calls: list[ToolCall] | None = None
    latency_ms: float = 0.0
    cost_usd: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def prompt_tokens(self) -> int:
        return self.usage.get("prompt_tokens", 0)

    @property
    def completion_tokens(self) -> int:
        return self.usage.get("completion_tokens", 0)

    @property
    def total_tokens(self) -> int:
        return self.usage.get("total_tokens", self.prompt_tokens + self.completion_tokens)

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "model": self.model,
            "provider": self.provider,
            "usage": self.usage,
            "finish_reason": self.finish_reason,
            "tool_calls": [tc.to_dict() for tc in self.tool_calls] if self.tool_calls else None,
            "latency_ms": self.latency_ms,
            "cost_usd": self.cost_usd,
            "metadata": self.metadata,
        }


@dataclass
class StreamChunk:
    """Streaming response chunk."""

    delta: str = ""
    finish_reason: str | None = None
    tool_calls: list[ToolCall] | None = None
    usage: dict[str, int] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_sse(self) -> str:
        import json

        data = {
            "delta": self.delta,
            "finish_reason": self.finish_reason,
        }
        if self.tool_calls:
            data["tool_calls"] = [tc.to_dict() for tc in self.tool_calls]
        if self.usage:
            data["usage"] = self.usage
        return f"data: {json.dumps(data)}\n\n"


@dataclass
class EmbeddingRequest:
    """Embedding request."""

    input: list[str] | str
    model: str
    encoding_format: str = "float"
    dimensions: int | None = None


@dataclass
class EmbeddingResponse:
    """Embedding response."""

    embeddings: list[list[float]]
    model: str
    provider: str
    usage: dict[str, int] = field(default_factory=dict)
    latency_ms: float = 0.0
    cost_usd: float = 0.0


@dataclass
class HealthStatus:
    """Provider health status."""

    healthy: bool
    latency_ms: float | None = None
    error: str | None = None
    details: dict[str, Any] = field(default_factory=dict)
    checked_at: float = field(default_factory=time.time)


class ProviderError(Exception):
    """Base provider error."""

    def __init__(self, message: str, provider: str, model: str | None = None, retryable: bool = False, status_code: int | None = None):
        super().__init__(message)
        self.provider = provider
        self.model = model
        self.retryable = retryable
        self.status_code = status_code


class RateLimitError(ProviderError):
    """Rate limit exceeded."""

    def __init__(self, message: str, provider: str, model: str | None = None, retry_after: float | None = None):
        super().__init__(message, provider, model, retryable=True, status_code=429)
        self.retry_after = retry_after


class AuthenticationError(ProviderError):
    """Authentication failed."""

    def __init__(self, message: str, provider: str):
        super().__init__(message, provider, retryable=False, status_code=401)


class ModelNotFoundError(ProviderError):
    """Model not available."""

    def __init__(self, message: str, provider: str, model: str):
        super().__init__(message, provider, model, retryable=False, status_code=404)


class ProviderUnavailableError(ProviderError):
    """Provider temporarily unavailable."""

    def __init__(self, message: str, provider: str, retryable: bool = True):
        super().__init__(message, provider, retryable=retryable, status_code=503)


class ChatProvider(ABC):
    """
    Abstract chat-completion provider.

    All providers must implement this interface. Provides unified access to
    Anthropic, OpenAI-compatible, Google, and local model APIs.
    """

    # Class attributes for registry
    provider_type: ProviderType = ProviderType.OPENAI_COMPATIBLE
    name: str = "base"
    requires_api_key: bool = True

    def __init__(
        self,
        config: ProviderConfig,
        metrics_callback: Callable[[str, dict[str, Any]], None] | None = None,
        **kwargs: Any,
    ) -> None:
        self.config = config
        self.name = config.name
        self._metrics_callback = metrics_callback
        self._metrics = ProviderMetrics()
        self._circuit_state = CircuitState.CLOSED
        self._circuit_failures = 0
        self._circuit_successes = 0
        self._circuit_last_failure: float | None = None
        self._health_status = HealthStatus(healthy=True)
        self._rate_limit_semaphore: asyncio.Semaphore | None = None
        self._init_rate_limiter()

    def _init_rate_limiter(self) -> None:
        """Initialize rate limiting semaphore."""
        if self.config.rate_limit.concurrent_requests > 0:
            self._rate_limit_semaphore = asyncio.Semaphore(self.config.rate_limit.concurrent_requests)

    @property
    def metrics(self) -> ProviderMetrics:
        return self._metrics

    @property
    def circuit_state(self) -> CircuitState:
        return self._circuit_state

    @property
    def health_status(self) -> HealthStatus:
        return self._health_status

    def _emit_metric(self, name: str, value: float, labels: dict[str, str] | None = None) -> None:
        """Emit metric via callback if registered."""
        if self._metrics_callback:
            try:
                self._metrics_callback(name, {"value": value, "labels": labels or {}})
            except Exception:
                pass  # Never let metrics break the request

    def _record_request(self, latency_ms: float, success: bool, prompt_tokens: int = 0, completion_tokens: int = 0, cost: float = 0.0, error: str | None = None) -> None:
        """Record request metrics."""
        self._metrics.record_call(latency_ms, success, prompt_tokens, completion_tokens, cost, error)
        self._emit_metric("provider_requests_total", 1, {"provider": self.name, "success": str(success).lower()})
        self._emit_metric("provider_latency_ms", latency_ms, {"provider": self.name})
        if prompt_tokens or completion_tokens:
            self._emit_metric("provider_tokens_total", prompt_tokens + completion_tokens, {"provider": self.name})
        if cost:
            self._emit_metric("provider_cost_usd", cost, {"provider": self.name})

    def _check_circuit_breaker(self) -> None:
        """Check and update circuit breaker state."""
        if not self.config.circuit_breaker.enabled:
            return

        now = time.time()

        if self._circuit_state == CircuitState.OPEN:
            # Check if timeout elapsed to transition to half-open
            if self._circuit_last_failure and (now - self._circuit_last_failure) >= self.config.circuit_breaker.timeout_seconds:
                self._circuit_state = CircuitState.HALF_OPEN
                self._circuit_successes = 0
            else:
                raise ProviderUnavailableError(
                    f"Circuit breaker OPEN for {self.name}",
                    provider=self.name,
                    retryable=True,
                )

        elif self._circuit_state == CircuitState.HALF_OPEN:
            # In half-open, allow one request through
            pass

    def _record_success(self) -> None:
        """Record successful call for circuit breaker."""
        self._circuit_failures = 0
        if self._circuit_state == CircuitState.HALF_OPEN:
            self._circuit_successes += 1
            if self._circuit_successes >= self.config.circuit_breaker.success_threshold:
                self._circuit_state = CircuitState.CLOSED

    def _record_failure(self, error: Exception) -> None:
        """Record failed call for circuit breaker."""
        if not self.config.circuit_breaker.enabled:
            return

        # Check if error is excluded
        excluded = self.config.circuit_breaker.excluded_exceptions
        if any(type(error).__name__ == exc.split(".")[-1] for exc in excluded):
            return

        self._circuit_failures += 1
        self._circuit_last_failure = time.time()

        if self._circuit_state == CircuitState.HALF_OPEN:
            # Any failure in half-open goes back to open
            self._circuit_state = CircuitState.OPEN
            self._metrics.record_circuit_trip()
        elif self._circuit_state == CircuitState.CLOSED:
            if self._circuit_failures >= self.config.circuit_breaker.failure_threshold:
                self._circuit_state = CircuitState.OPEN
                self._metrics.record_circuit_trip()

    async def _acquire_rate_limit(self) -> None:
        """Acquire rate limit slot with timeout."""
        if self._rate_limit_semaphore:
            try:
                await asyncio.wait_for(
                    self._rate_limit_semaphore.acquire(),
                    timeout=self.config.rate_limit.queue_timeout_seconds,
                )
            except TimeoutError:
                self._metrics.record_rate_limit()
                raise RateLimitError(
                    f"Rate limit queue timeout for {self.name}",
                    provider=self.name,
                )

    def _release_rate_limit(self) -> None:
        """Release rate limit slot."""
        if self._rate_limit_semaphore:
            self._rate_limit_semaphore.release()

    def _calculate_cost(self, model: str, prompt_tokens: int, completion_tokens: int) -> float:
        """Calculate cost for token usage."""
        if not self.config.cost_tracking.enabled:
            return 0.0

        pricing = self.config.cost_tracking.custom_pricing.get(model)
        if not pricing:
            pricing = BUILTIN_PRICING.get(model)

        if not pricing:
            return 0.0

        input_cost = (prompt_tokens / 1000) * pricing.get("input_per_1k", 0)
        output_cost = (completion_tokens / 1000) * pricing.get("output_per_1k", 0)
        return input_cost + output_cost

    # =========================================================================
    # Abstract methods (must be implemented by subclasses)
    # =========================================================================

    @abstractmethod
    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        """
        Complete a chat request.

        Args:
            request: Unified completion request

        Returns:
            Unified completion response

        Raises:
            ProviderError: On provider-specific errors
            RateLimitError: On rate limit (retryable)
            AuthenticationError: On auth failure (non-retryable)
            ModelNotFoundError: On model not found (non-retryable)
        """
        pass

    @abstractmethod
    async def stream(self, request: CompletionRequest) -> AsyncIterator[StreamChunk]:
        """
        Stream a chat request.

        Args:
            request: Unified completion request with stream=True

        Yields:
            StreamChunk objects

        Raises:
            ProviderError: On provider-specific errors
        """
        pass

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        """
        Generate embeddings (optional - not all providers support this).

        Args:
            request: Embedding request

        Returns:
            Embedding response

        Raises:
            NotImplementedError: If provider doesn't support embeddings
            ProviderError: On provider-specific errors
        """
        raise NotImplementedError(f"{self.name} does not support embeddings")

    @abstractmethod
    async def health_check(self) -> HealthStatus:
        """
        Check provider health.

        Returns:
            HealthStatus with healthy=True if provider is operational
        """
        pass

    @abstractmethod
    def get_supported_models(self) -> list[str]:
        """Return list of supported model names."""
        pass

    @abstractmethod
    def get_default_model(self) -> str:
        """Return default model name."""
        pass

    # =========================================================================
    # Helper methods for subclasses
    # =========================================================================

    def _build_headers(self) -> dict[str, str]:
        """Build request headers including auth."""
        headers = {"Content-Type": "application/json"}
        headers.update(self.config.extra_headers)

        api_key = self._get_api_key()
        if api_key:
            if self.provider_type == ProviderType.ANTHROPIC:
                headers["x-api-key"] = api_key
                headers["anthropic-version"] = "2023-06-01"
            elif self.provider_type == ProviderType.GOOGLE_GEMINI:
                headers["x-goog-api-key"] = api_key
            else:
                headers["Authorization"] = f"Bearer {api_key}"
        return headers

    def _get_api_key(self) -> str | None:
        """Get API key from config or environment."""
        if self.config.api_key:
            return self.config.api_key
        if self.config.api_key_env:
            import os

            return os.environ.get(self.config.api_key_env)
        return None

    def _get_request_url(self, endpoint: str = "") -> str:
        """Build full request URL."""
        base = (self.config.base_url or "").rstrip("/")
        if endpoint:
            return f"{base}/{endpoint.lstrip('/')}"
        return base

    def _normalize_messages(self, messages: list[Message]) -> list[dict[str, Any]]:
        """Normalize messages to provider-specific format."""
        return [m.to_dict() for m in messages]

    def _parse_usage(self, data: dict[str, Any]) -> dict[str, int]:
        """Parse usage from provider response."""
        usage = data.get("usage") or {}
        return {
            "prompt_tokens": usage.get("prompt_tokens", usage.get("input_tokens", 0)),
            "completion_tokens": usage.get("completion_tokens", usage.get("output_tokens", 0)),
            "total_tokens": usage.get("total_tokens", 0),
        }

    async def _execute_with_retry(self, operation: Callable, *args: Any, **kwargs: Any) -> Any:
        """Execute operation with retry policy."""
        policy = self.config.retry_policy
        last_error: Exception | None = None

        for attempt in range(1, policy.max_attempts + 1):
            try:
                return await operation(*args, **kwargs)
            except Exception as e:
                last_error = e

                # Check if retryable
                if not self._is_retryable(e):
                    raise

                if attempt < policy.max_attempts:
                    delay = policy.calculate_delay(attempt)
                    if delay > 0:
                        await asyncio.sleep(delay)
                    self._metrics.record_retry()
                else:
                    break

        raise last_error or RuntimeError("Retry policy exhausted")

    def _is_retryable(self, error: Exception) -> bool:
        """Check if error is retryable per policy."""
        policy = self.config.retry_policy

        # Check status code
        status_code = getattr(error, "status_code", None)
        if status_code is not None and status_code in policy.retryable_status_codes:
            return True

        # Check exception type
        error_type = type(error).__name__
        if error_type in policy.retryable_exceptions:
            return True

        # Check ProviderError retryable flag
        if isinstance(error, ProviderError):
            return error.retryable

        return False


class StreamingProvider(ChatProvider):
    """Mixin for providers with native streaming support."""

    @abstractmethod
    async def _stream_native(self, request: CompletionRequest) -> AsyncIterator[StreamChunk]:
        """Native streaming implementation."""
        pass

    async def stream(self, request: CompletionRequest) -> AsyncIterator[StreamChunk]:  # type: ignore[override]
        """Stream with circuit breaker and rate limiting."""
        self._check_circuit_breaker()
        await self._acquire_rate_limit()

        try:
            async for chunk in self._stream_native(request):
                yield chunk
            self._record_success()
        except Exception as e:
            self._record_failure(e)
            raise
        finally:
            self._release_rate_limit()


__all__ = [
    "ProviderMetrics",
    "Message",
    "ToolCall",
    "CompletionRequest",
    "CompletionResponse",
    "StreamChunk",
    "EmbeddingRequest",
    "EmbeddingResponse",
    "HealthStatus",
    "ProviderError",
    "RateLimitError",
    "AuthenticationError",
    "ModelNotFoundError",
    "ProviderUnavailableError",
    "ChatProvider",
    "StreamingProvider",
]