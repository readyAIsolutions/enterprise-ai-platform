"""
Provider Abstraction Configuration Schema
==========================================

Pydantic models for config-driven provider selection, rate limiting,
cost tracking, and health check settings. Supports YAML/JSON loading.

Follows ENI patterns: stdlib-first, async-native, comprehensive type hints.
"""

from __future__ import annotations

import json
from enum import Enum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class ProviderType(str, Enum):
    """Supported provider types."""

    OPENAI_COMPATIBLE = "openai_compatible"
    ANTHROPIC = "anthropic"
    GOOGLE_GEMINI = "google_gemini"
    LOCAL_OLLAMA = "local_ollama"
    LOCAL_LLAMACPP = "local_llamacpp"
    MOCK = "mock"
    ECHO = "echo"


class HealthCheckStrategy(str, Enum):
    """Health check strategies."""

    HTTP_ENDPOINT = "http_endpoint"
    TEST_COMPLETION = "test_completion"
    NONE = "none"


class CircuitState(str, Enum):
    """Circuit breaker states."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class RetryPolicyConfig(BaseModel):
    """Exponential backoff retry configuration."""

    max_attempts: int = Field(default=3, ge=1, le=20, description="Maximum retry attempts")
    base_delay: float = Field(default=0.5, ge=0.01, le=60.0, description="Initial delay in seconds")
    max_delay: float = Field(default=30.0, ge=0.1, le=300.0, description="Maximum delay in seconds")
    jitter: bool = Field(default=True, description="Add random jitter to delay")
    jitter_factor: float = Field(default=0.5, ge=0.0, le=1.0, description="Jitter range multiplier")
    retryable_status_codes: set[int] = Field(
        default_factory=lambda: {429, 500, 502, 503, 504, 520, 521, 522, 524, 529},
        description="HTTP status codes that trigger retry",
    )
    retryable_exceptions: tuple[str, ...] = Field(
        default=("TimeoutError", "ConnectionError", "URLError", "HTTPError"),
        description="Exception types that trigger retry",
    )
    disable_sleep: bool = Field(default=False, description="Disable backoff sleep (for tests)")

    @field_validator("retryable_status_codes", mode="before")
    @classmethod
    def _coerce_status_codes(cls, v: Any) -> set[int]:
        if isinstance(v, (list, tuple, set)):
            return set(int(x) for x in v)
        return {429, 500, 502, 503, 504, 520, 521, 522, 524, 529}

    def calculate_delay(self, attempt: int) -> float:
        """Calculate exponential backoff delay for attempt number (1-indexed)."""
        if self.disable_sleep:
            return 0.0
        delay = min(self.max_delay, self.base_delay * (2 ** (attempt - 1)))
        if self.jitter:
            import random

            delay = delay * random.uniform(1.0 - self.jitter_factor, 1.0)
        return delay


class HealthCheckConfig(BaseModel):
    """Health check configuration."""

    strategy: HealthCheckStrategy = Field(default=HealthCheckStrategy.HTTP_ENDPOINT)
    endpoint: str | None = Field(default=None, description="Health check endpoint URL")
    interval_seconds: int = Field(default=30, ge=5, le=3600, description="Check interval")
    timeout_seconds: float = Field(default=5.0, ge=0.5, le=60.0, description="Request timeout")
    expected_status: int = Field(default=200, ge=100, le=599)
    test_prompt: str = Field(default="Hello", description="Prompt for test completion check")
    test_model: str | None = Field(default=None, description="Model for test completion")
    unhealthy_threshold: int = Field(default=3, ge=1, le=10, description="Consecutive failures before unhealthy")
    healthy_threshold: int = Field(default=2, ge=1, le=10, description="Consecutive successes before healthy")


class CircuitBreakerConfig(BaseModel):
    """Circuit breaker configuration."""

    enabled: bool = Field(default=True, description="Enable circuit breaker")
    failure_threshold: int = Field(default=5, ge=1, le=100, description="Failures before opening")
    success_threshold: int = Field(default=2, ge=1, le=100, description="Successes before closing from half-open")
    timeout_seconds: float = Field(default=60.0, ge=1.0, le=3600.0, description="Time before half-open")
    excluded_exceptions: tuple[str, ...] = Field(
        default=("asyncio.CancelledError", "KeyboardInterrupt"),
        description="Exceptions that don't count as failures",
    )


class RateLimitConfig(BaseModel):
    """Rate limiting configuration per provider."""

    requests_per_minute: int | None = Field(default=None, ge=1, description="Max RPM (None = unlimited)")
    tokens_per_minute: int | None = Field(default=None, ge=1, description="Max TPM (None = unlimited)")
    concurrent_requests: int = Field(default=10, ge=1, le=1000, description="Max concurrent requests")
    burst_allowance: float = Field(default=1.5, ge=1.0, le=10.0, description="Burst multiplier over base rate")
    queue_timeout_seconds: float = Field(default=30.0, ge=0.1, le=300.0, description="Max time waiting for rate limit slot")


class CostTrackingConfig(BaseModel):
    """Cost tracking configuration."""

    enabled: bool = Field(default=True, description="Enable cost tracking")
    pricing_source: Literal["builtin", "custom", "api"] = Field(default="builtin", description="Pricing source")
    custom_pricing: dict[str, dict[str, float]] = Field(
        default_factory=dict,
        description="Custom pricing: {model: {input_per_1k, output_per_1k}}",
    )
    currency: str = Field(default="USD", description="Currency for cost reporting")
    budget_per_session: float | None = Field(default=None, ge=0.0, description="Session budget limit")
    budget_per_day: float | None = Field(default=None, ge=0.0, description="Daily budget limit")
    alert_threshold_pct: float = Field(default=0.8, ge=0.0, le=1.0, description="Alert at % of budget")


class StreamingConfig(BaseModel):
    """Streaming (SSE) configuration."""

    enabled: bool = Field(default=True, description="Enable streaming")
    fake_sse_for_non_streaming: bool = Field(default=True, description="Synthesize SSE for non-streaming upstreams")
    chunk_size: int = Field(default=1024, ge=64, le=65536, description="SSE chunk size in bytes")
    heartbeat_interval_seconds: float = Field(default=15.0, ge=1.0, le=300.0, description="SSE heartbeat interval")
    max_buffer_size: int = Field(default=1024 * 1024, ge=1024, description="Max buffer before flush")


class ProviderConfig(BaseModel):
    """Complete provider configuration."""

    name: str = Field(description="Unique provider name")
    type: ProviderType = Field(description="Provider type")
    enabled: bool = Field(default=True, description="Whether provider is enabled")
    priority: int = Field(default=100, ge=0, le=1000, description="Selection priority (lower = preferred)")

    # Connection
    base_url: str | None = Field(default=None, description="API base URL")
    api_key_env: str | None = Field(default=None, description="Environment variable for API key")
    api_key: str | None = Field(default=None, description="Direct API key (not for production)")
    extra_headers: dict[str, str] = Field(default_factory=dict, description="Extra HTTP headers")

    # Model defaults
    default_model: str | None = Field(default=None, description="Default model name")
    supported_models: list[str] = Field(default_factory=list, description="Supported model names")

    # Behavior
    timeout_seconds: float = Field(default=60.0, ge=1.0, le=600.0, description="Request timeout")
    max_retries: int = Field(default=3, ge=0, le=20, description="Max retries (deprecated: use retry_policy)")

    # Nested configs
    retry_policy: RetryPolicyConfig = Field(default_factory=RetryPolicyConfig)
    health_check: HealthCheckConfig = Field(default_factory=HealthCheckConfig)
    circuit_breaker: CircuitBreakerConfig = Field(default_factory=CircuitBreakerConfig)
    rate_limit: RateLimitConfig = Field(default_factory=RateLimitConfig)
    cost_tracking: CostTrackingConfig = Field(default_factory=CostTrackingConfig)
    streaming: StreamingConfig = Field(default_factory=StreamingConfig)

    # Fallback chain
    fallback_providers: list[str] = Field(default_factory=list, description="Fallback provider names in order")

    # Provider-specific options
    options: dict[str, Any] = Field(default_factory=dict, description="Provider-specific options")

    @model_validator(mode="after")
    def _validate_type_consistency(self) -> ProviderConfig:
        # Set defaults based on type
        if self.type == ProviderType.OPENAI_COMPATIBLE:
            if not self.base_url:
                self.base_url = "https://api.openai.com/v1"
            if not self.api_key_env:
                self.api_key_env = "OPENAI_API_KEY"
            if not self.default_model:
                self.default_model = "gpt-4o-mini"
        elif self.type == ProviderType.ANTHROPIC:
            if not self.base_url:
                self.base_url = "https://api.anthropic.com"
            if not self.api_key_env:
                self.api_key_env = "ANTHROPIC_API_KEY"
            if not self.default_model:
                self.default_model = "claude-3-5-haiku-20241022"
        elif self.type == ProviderType.GOOGLE_GEMINI:
            if not self.base_url:
                self.base_url = "https://generativelanguage.googleapis.com/v1beta"
            if not self.api_key_env:
                self.api_key_env = "GOOGLE_API_KEY"
            if not self.default_model:
                self.default_model = "gemini-1.5-flash"
        elif self.type == ProviderType.LOCAL_OLLAMA:
            if not self.base_url:
                self.base_url = "http://localhost:11434/v1"
            if not self.api_key_env:
                self.api_key_env = "OLLAMA_API_KEY"
            if not self.default_model:
                self.default_model = "llama3.1:8b"
        elif self.type == ProviderType.LOCAL_LLAMACPP:
            if not self.base_url:
                self.base_url = "http://localhost:8080/v1"
            if not self.default_model:
                self.default_model = "local-model"
        elif self.type in (ProviderType.MOCK, ProviderType.ECHO):
            self.requires_api_key = False
        return self


class ProviderAbstractionConfig(BaseModel):
    """Root configuration for provider abstraction layer."""

    providers: list[ProviderConfig] = Field(default_factory=list, description="Provider configurations")
    default_provider: str | None = Field(default=None, description="Default provider name")
    fallback_chain: list[str] = Field(default_factory=list, description="Global fallback chain")

    # Global settings
    global_timeout_seconds: float = Field(default=120.0, ge=1.0, le=600.0)
    global_max_retries: int = Field(default=3, ge=0, le=20)
    enable_cost_tracking: bool = Field(default=True)
    enable_health_checks: bool = Field(default=True)
    enable_circuit_breaker: bool = Field(default=True)
    enable_fallback: bool = Field(default=True)
    enable_streaming: bool = Field(default=True)

    # Metrics
    metrics_enabled: bool = Field(default=True)
    metrics_prefix: str = Field(default="provider_abstraction")

    @classmethod
    def from_file(cls, path: str | Path) -> ProviderAbstractionConfig:
        """Load configuration from YAML or JSON file."""
        path = Path(path)
        content = path.read_text(encoding="utf-8")
        if path.suffix.lower() in (".yaml", ".yml"):
            import yaml

            data = yaml.safe_load(content)
        elif path.suffix.lower() == ".json":
            data = json.loads(content)
        else:
            raise ValueError(f"Unsupported config format: {path.suffix}")
        return cls(**data)

    @classmethod
    def from_env(cls, prefix: str = "PROVIDER_") -> ProviderAbstractionConfig:
        """Load configuration from environment variables."""
        import os

        # Simple env-based config for quick setup
        providers = []
        for i in range(10):  # Support up to 10 providers via env
            name_key = f"{prefix}PROVIDER_{i}_NAME"
            if name_key not in os.environ:
                continue
            provider_config = {
                "name": os.environ[name_key],
                "type": os.environ.get(f"{prefix}PROVIDER_{i}_TYPE", "openai_compatible"),
                "base_url": os.environ.get(f"{prefix}PROVIDER_{i}_BASE_URL"),
                "api_key_env": os.environ.get(f"{prefix}PROVIDER_{i}_API_KEY_ENV"),
                "default_model": os.environ.get(f"{prefix}PROVIDER_{i}_DEFAULT_MODEL"),
                "enabled": os.environ.get(f"{prefix}PROVIDER_{i}_ENABLED", "true").lower() == "true",
                "priority": int(os.environ.get(f"{prefix}PROVIDER_{i}_PRIORITY", "100")),
            }
            providers.append(ProviderConfig(**provider_config))

        return cls(providers=providers)


# Built-in pricing (USD per 1K tokens) - updated periodically
BUILTIN_PRICING: dict[str, dict[str, float]] = {
    # OpenAI
    "gpt-4o": {"input_per_1k": 0.005, "output_per_1k": 0.015},
    "gpt-4o-mini": {"input_per_1k": 0.00015, "output_per_1k": 0.0006},
    "gpt-4-turbo": {"input_per_1k": 0.01, "output_per_1k": 0.03},
    "gpt-4": {"input_per_1k": 0.03, "output_per_1k": 0.06},
    "gpt-3.5-turbo": {"input_per_1k": 0.0005, "output_per_1k": 0.0015},
    # Anthropic
    "claude-3-5-sonnet-20241022": {"input_per_1k": 0.003, "output_per_1k": 0.015},
    "claude-3-5-haiku-20241022": {"input_per_1k": 0.001, "output_per_1k": 0.005},
    "claude-3-opus-20240229": {"input_per_1k": 0.015, "output_per_1k": 0.075},
    "claude-3-sonnet-20240229": {"input_per_1k": 0.003, "output_per_1k": 0.015},
    "claude-3-haiku-20240307": {"input_per_1k": 0.00025, "output_per_1k": 0.00125},
    # Google
    "gemini-1.5-pro": {"input_per_1k": 0.00125, "output_per_1k": 0.005},
    "gemini-1.5-flash": {"input_per_1k": 0.000075, "output_per_1k": 0.0003},
    "gemini-1.0-pro": {"input_per_1k": 0.0005, "output_per_1k": 0.0015},
    # OpenRouter (approximate)
    "openrouter/auto": {"input_per_1k": 0.001, "output_per_1k": 0.003},
}

DEFAULT_CONFIG = ProviderAbstractionConfig(
    providers=[
        ProviderConfig(
            name="openai",
            type=ProviderType.OPENAI_COMPATIBLE,
            priority=10,
            default_model="gpt-4o-mini",
            fallback_providers=["anthropic", "google"],
        ),
        ProviderConfig(
            name="anthropic",
            type=ProviderType.ANTHROPIC,
            priority=20,
            default_model="claude-3-5-haiku-20241022",
            fallback_providers=["openai", "google"],
        ),
        ProviderConfig(
            name="google",
            type=ProviderType.GOOGLE_GEMINI,
            priority=30,
            default_model="gemini-1.5-flash",
            fallback_providers=["openai", "anthropic"],
        ),
        ProviderConfig(
            name="local-ollama",
            type=ProviderType.LOCAL_OLLAMA,
            priority=50,
            default_model="llama3.1:8b",
            fallback_providers=[],
        ),
    ],
    default_provider="openai",
    fallback_chain=["openai", "anthropic", "google", "local-ollama"],
)