"""Unit tests for the enterprise ``autonomous_agent_runtime`` module.

These tests exercise the real production logic in ``provider_abstraction/``:
config schema validation, cost tracking math, fallback/circuit-breaker
behavior, the provider registry, and the streaming SSE normalization.

All tests are pure in-memory / stdlib (tempfile) — no external services.
"""

import asyncio
import json
import os
import tempfile

import pytest

from modules.autonomous_agent_runtime.provider_abstraction.config_schema import (
    BUILTIN_PRICING,
    CircuitBreakerConfig,
    CircuitState,
    CostTrackingConfig,
    ProviderAbstractionConfig,
    ProviderConfig,
    ProviderType,
    RateLimitConfig,
    RetryPolicyConfig,
)
from modules.autonomous_agent_runtime.provider_abstraction.cost_tracker import CostTracker
from modules.autonomous_agent_runtime.provider_abstraction.fallback_manager import (
    CircuitBreaker,
    FallbackManager,
    FallbackStrategy,
)
from modules.autonomous_agent_runtime.provider_abstraction.provider_interface import (
    ChatProvider,
    CompletionRequest,
    CompletionResponse,
    HealthStatus,
    Message,
    ProviderMetrics,
    ProviderUnavailableError,
    StreamChunk,
)
from modules.autonomous_agent_runtime.provider_abstraction.provider_registry import ProviderRegistry
from modules.autonomous_agent_runtime.provider_abstraction.providers.openai_compatible import (
    OpenAICompatibleProvider,
)
from modules.autonomous_agent_runtime.provider_abstraction.streaming_adapter import SSEEvent


# =============================================================================
# Fixtures / helpers
# =============================================================================


class DummyProvider(ChatProvider):
    """A predictable fake provider for fallback / registry tests."""

    def __init__(self, config, fail: bool = False, **kwargs):
        super().__init__(config, **kwargs)
        self.fail = fail

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        if self.fail:
            raise ProviderUnavailableError("provider down", self.name)
        return CompletionResponse(
            text=f"ok:{self.name}",
            model=request.model,
            provider=self.name,
            usage={"prompt_tokens": 10, "completion_tokens": 5},
        )

    async def stream(self, request):  # pragma: no cover - not used here
        yield StreamChunk(delta=self.name)

    async def health_check(self) -> HealthStatus:
        return HealthStatus(healthy=True)

    def get_supported_models(self) -> list[str]:
        return [self.config.default_model or "m"]

    def get_default_model(self) -> str:
        return self.config.default_model or "m"


def run(coro):
    return asyncio.run(coro)


# =============================================================================
# Config schema
# =============================================================================


def test_retry_policy_exponential_backoff():
    policy = RetryPolicyConfig(disable_sleep=False, jitter=False, base_delay=1.0)
    # 1-indexed attempts: 1s, 2s, 4s, 8s
    assert policy.calculate_delay(1) == pytest.approx(1.0)
    assert policy.calculate_delay(2) == pytest.approx(2.0)
    assert policy.calculate_delay(3) == pytest.approx(4.0)
    assert policy.calculate_delay(4) == pytest.approx(8.0)


def test_retry_policy_delay_capped_at_max():
    policy = RetryPolicyConfig(
        disable_sleep=False, jitter=False, base_delay=2.0, max_delay=5.0
    )
    assert policy.calculate_delay(1) == pytest.approx(2.0)
    assert policy.calculate_delay(2) == pytest.approx(4.0)
    # capped at max_delay
    assert policy.calculate_delay(3) == pytest.approx(5.0)
    assert policy.calculate_delay(10) == pytest.approx(5.0)


def test_retry_policy_disable_sleep_returns_zero():
    policy = RetryPolicyConfig(disable_sleep=True, jitter=False, base_delay=10.0)
    assert policy.calculate_delay(5) == 0.0


def test_retry_policy_validation_rejects_out_of_range():
    with pytest.raises(Exception):
        RetryPolicyConfig(max_attempts=0)
    with pytest.raises(Exception):
        RetryPolicyConfig(max_attempts=25)


def test_provider_config_openai_type_defaults():
    cfg = ProviderConfig(name="openai", type=ProviderType.OPENAI_COMPATIBLE)
    assert cfg.base_url == "https://api.openai.com/v1"
    assert cfg.api_key_env == "OPENAI_API_KEY"
    assert cfg.default_model == "gpt-4o-mini"


def test_provider_config_local_ollama_defaults():
    cfg = ProviderConfig(name="ollama", type=ProviderType.LOCAL_OLLAMA)
    assert cfg.base_url == "http://localhost:11434/v1"
    assert cfg.default_model == "llama3.1:8b"


def test_rate_limit_config_rejects_bad_concurrency():
    with pytest.raises(Exception):
        RateLimitConfig(concurrent_requests=0)
    with pytest.raises(Exception):
        RateLimitConfig(concurrent_requests=2000)


def test_root_config_from_file_json(tmp_path):
    data = {
        "default_provider": "openai",
        "fallback_chain": ["openai", "anthropic"],
        "providers": [
            {
                "name": "openai",
                "type": "openai_compatible",
                "priority": 10,
            }
        ],
    }
    p = tmp_path / "cfg.json"
    p.write_text(json.dumps(data))
    cfg = ProviderAbstractionConfig.from_file(p)
    assert cfg.default_provider == "openai"
    assert cfg.fallback_chain == ["openai", "anthropic"]
    assert cfg.providers[0].name == "openai"


def test_root_config_from_file_unsupported_format(tmp_path):
    p = tmp_path / "cfg.toml"
    p.write_text("x = 1")
    with pytest.raises(ValueError):
        ProviderAbstractionConfig.from_file(p)


def test_builtin_pricing_has_common_models():
    assert "gpt-4o" in BUILTIN_PRICING
    assert "gpt-4o-mini" in BUILTIN_PRICING
    assert BUILTIN_PRICING["gpt-4o"]["input_per_1k"] == pytest.approx(0.005)


# =============================================================================
# Cost tracker
# =============================================================================


def test_cost_tracker_calculate_cost_math():
    ct = CostTracker()
    # gpt-4o: 0.005 in / 0.015 out per 1K
    cost = ct.calculate_cost("gpt-4o", 1000, 2000)
    assert cost == pytest.approx(0.005 * 1 + 0.015 * 2)


def test_cost_tracker_unknown_model_is_free():
    ct = CostTracker()
    assert ct.calculate_cost("unknown-model", 500, 500) == 0.0


def test_cost_tracker_estimate_cost_matches_calculate():
    ct = CostTracker()
    assert ct.estimate_cost("gpt-4o-mini", 1000, 1000) == pytest.approx(
        ct.calculate_cost("gpt-4o-mini", 1000, 1000)
    )


def test_cost_tracker_record_usage_aggregates():
    ct = CostTracker()
    resp = CompletionResponse(
        text="hi",
        model="gpt-4o",
        provider="openai",
        usage={"prompt_tokens": 1000, "completion_tokens": 2000},
    )
    rec = run(ct.record_usage(resp, "openai", session_id="s1"))
    assert rec.total_tokens == 3000
    assert rec.cost_usd == pytest.approx(0.035)

    total = ct.get_total_usage()
    assert total["total_prompt_tokens"] == 1000
    assert total["total_completion_tokens"] == 2000
    assert total["total_tokens"] == 3000
    assert total["total_requests"] == 1

    pv = ct.get_provider_usage("openai")
    assert pv["openai"]["total_tokens"] == 3000


def test_cost_tracker_session_tracking():
    ct = CostTracker()
    sid = ct.start_session("my-session")
    assert sid == "my-session"
    resp = CompletionResponse(
        text="x",
        model="gpt-4o-mini",
        provider="openai",
        usage={"prompt_tokens": 100, "completion_tokens": 50},
    )
    run(ct.record_usage(resp, "openai"))
    usage = ct.get_session_usage("my-session")
    assert usage is not None
    assert usage.total_tokens == 150
    assert usage.request_count == 1
    ended = ct.end_session("my-session")
    assert ended is not None
    assert ended.ended_at is not None


def test_cost_tracker_budget_alert_emitted():
    alerts = []
    ct = CostTracker(
        config=CostTrackingConfig(budget_per_session=0.01, alert_threshold_pct=0.5),
        metrics_callback=lambda name, _v: alerts.append(name),
    )
    ct.start_session("s")
    resp = CompletionResponse(
        text="x",
        model="gpt-4o",
        provider="openai",
        usage={"prompt_tokens": 1000, "completion_tokens": 2000},
    )
    run(ct.record_usage(resp, "openai"))
    assert "budget_alert" in alerts


def test_cost_tracker_persistence_jsonl_and_reload(tmp_path):
    storage = tmp_path / "usage.jsonl"
    ct = CostTracker(storage_path=storage)
    resp = CompletionResponse(
        text="y",
        model="gpt-4o",
        provider="openai",
        usage={"prompt_tokens": 500, "completion_tokens": 500},
    )
    run(ct.record_usage(resp, "openai", request_id="req-1"))
    assert storage.exists()

    # Reload into a fresh tracker and confirm the record comes back.
    ct2 = CostTracker(storage_path=storage)
    total = ct2.get_total_usage()
    assert total["total_requests"] == 1
    assert total["total_prompt_tokens"] == 500


def test_cost_tracker_export_json(tmp_path):
    ct = CostTracker()
    resp = CompletionResponse(
        text="z",
        model="gpt-4o-mini",
        provider="openai",
        usage={"prompt_tokens": 10, "completion_tokens": 20},
    )
    run(ct.record_usage(resp, "openai"))
    out = tmp_path / "export.json"
    run(ct.export_usage(out, "json"))
    data = json.loads(out.read_text())
    assert len(data["records"]) == 1
    assert data["summary"]["total_requests"] == 1


def test_cost_tracker_export_bad_format(tmp_path):
    ct = CostTracker()
    with pytest.raises(ValueError):
        run(ct.export_usage(tmp_path / "x.out", "csv"))


def test_cost_tracker_reset_clears_state():
    ct = CostTracker()
    resp = CompletionResponse(
        text="q",
        model="gpt-4o",
        provider="openai",
        usage={"prompt_tokens": 1, "completion_tokens": 1},
    )
    run(ct.record_usage(resp, "openai"))
    assert ct.get_total_usage()["total_requests"] == 1
    run(ct.reset())
    assert ct.get_total_usage()["total_requests"] == 0


# =============================================================================
# Fallback manager + circuit breaker
# =============================================================================


def test_circuit_breaker_opens_after_failures():
    cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=2), "p")
    assert cb.is_closed
    run(cb.record_failure(Exception("e1")))
    assert cb.is_closed
    run(cb.record_failure(Exception("e2")))
    assert cb.is_open


def test_circuit_breaker_half_open_recovers_to_closed():
    cb = CircuitBreaker(CircuitBreakerConfig(success_threshold=2), "p")
    cb.state = CircuitState.HALF_OPEN
    cb.success_count = 0
    run(cb.record_success())
    assert cb.is_half_open
    run(cb.record_success())
    assert cb.is_closed


def test_circuit_breaker_half_open_failure_goes_open():
    cb = CircuitBreaker(CircuitBreakerConfig(), "p")
    cb.state = CircuitState.HALF_OPEN
    run(cb.record_failure(Exception("boom")))
    assert cb.is_open


def test_fallback_manager_falls_back_to_next_provider():
    req = CompletionRequest(messages=[Message(role="user", content="hi")], model="m")
    cfg_a = ProviderConfig(name="a", type=ProviderType.OPENAI_COMPATIBLE)
    cfg_b = ProviderConfig(name="b", type=ProviderType.OPENAI_COMPATIBLE)
    pa, pb = DummyProvider(cfg_a, fail=True), DummyProvider(cfg_b)
    fm = FallbackManager({"a": pa, "b": pb}, {"a": cfg_a, "b": cfg_b})
    result = run(fm.execute_with_fallback(req, "a", ["b"]))
    assert result.final_provider == "b"
    assert result.response is not None
    assert len(result.attempts) == 2  # a failed, b succeeded
    assert not result.exhausted


def test_fallback_manager_exhausted_raises():
    req = CompletionRequest(messages=[Message(role="user", content="hi")], model="m")
    cfg_a = ProviderConfig(name="a", type=ProviderType.OPENAI_COMPATIBLE)
    pa = DummyProvider(cfg_a, fail=True)
    fm = FallbackManager({"a": pa}, {"a": cfg_a})
    with pytest.raises(ProviderUnavailableError) as exc_info:
        run(fm.execute_with_fallback(req, "a"))
    assert exc_info.value.retryable is True


def test_fallback_manager_circuit_breaker_blocks_open_provider():
    req = CompletionRequest(messages=[Message(role="user", content="hi")], model="m")
    cfg_a = ProviderConfig(
        name="a",
        type=ProviderType.OPENAI_COMPATIBLE,
        circuit_breaker=CircuitBreakerConfig(failure_threshold=1),
    )
    cfg_b = ProviderConfig(name="b", type=ProviderType.OPENAI_COMPATIBLE)
    pa, pb = DummyProvider(cfg_a), DummyProvider(cfg_b)
    fm = FallbackManager({"a": pa, "b": pb}, {"a": cfg_a, "b": cfg_b})
    # Open provider 'a''s circuit with a single failure.
    run(fm._circuit_breakers["a"].record_failure(Exception("x")))
    assert fm._circuit_breakers["a"].is_open
    result = run(fm.execute_with_fallback(req, "a", ["b"]))
    # 'a' is blocked by the open circuit (recorded as an OPEN attempt),
    # so the request falls through to 'b'.
    assert result.final_provider == "b"
    assert result.attempts[0].error == "Circuit breaker OPEN"
    assert result.attempts[0].provider_name == "a"


def test_select_provider_least_loaded_strategy():
    cfg_a = ProviderConfig(name="a", type=ProviderType.OPENAI_COMPATIBLE)
    cfg_b = ProviderConfig(name="b", type=ProviderType.OPENAI_COMPATIBLE)
    fm = FallbackManager(
        {}, {"a": cfg_a, "b": cfg_b}, FallbackStrategy.LEAST_LOADED
    )
    fm._active_requests["a"] = 5
    fm._active_requests["b"] = 1
    assert fm.select_provider(["a", "b"]) == "b"  # fewer active requests


def test_circuit_breaker_reset_returns_closed():
    cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=1), "p")
    run(cb.record_failure(Exception("x")))
    assert cb.is_open
    run(cb.reset())
    assert cb.is_closed
    assert cb.failure_count == 0


# =============================================================================
# Provider interface helpers
# =============================================================================


def test_completion_response_token_properties():
    resp = CompletionResponse(
        text="t",
        model="gpt-4o",
        provider="openai",
        usage={"prompt_tokens": 10, "completion_tokens": 20},
    )
    assert resp.prompt_tokens == 10
    assert resp.completion_tokens == 20
    assert resp.total_tokens == 30


def test_provider_metrics_record_call_and_to_dict():
    m = ProviderMetrics()
    m.record_call(latency_ms=25, success=True, prompt_tokens=100, completion_tokens=50, cost=0.01)
    m.record_call(latency_ms=75, success=False, error="boom")
    d = m.to_dict()
    assert d["calls_total"] == 2
    assert d["calls_success"] == 1
    assert d["calls_failed"] == 1
    assert d["total_prompt_tokens"] == 100
    assert d["total_cost_usd"] == pytest.approx(0.01)
    assert d["last_error"] == "boom"


def test_stream_chunk_to_sse_format():
    chunk = StreamChunk(delta="hello", finish_reason=None)
    sse = chunk.to_sse()
    assert sse.startswith("data: ")
    assert '"delta": "hello"' in sse


# =============================================================================
# Provider registry (constructed without the broken __init__ provider registry)
# =============================================================================


def _make_registry():
    """Build a ProviderRegistry, bypassing the ``_register_builtins`` step.

    ``_register_builtins`` tries to import provider modules (anthropic, mock,
    etc.) that don't exist in this checkout, so we construct the object without
    running ``__init__`` and inject the real OpenAI provider class manually.
    This still exercises the real registration/lookup logic.
    """
    reg = ProviderRegistry.__new__(ProviderRegistry)
    reg.config = ProviderAbstractionConfig()
    reg._metrics_callback = None
    reg._registrations = {}
    reg._provider_classes = {ProviderType.OPENAI_COMPATIBLE: OpenAICompatibleProvider}
    return reg


def test_registry_register_and_lookup():
    reg = _make_registry()
    reg.register_from_config(
        ProviderConfig(name="openai", type=ProviderType.OPENAI_COMPATIBLE)
    )
    assert reg.list_providers() == ["openai"]
    prov = reg.get("openai")
    assert isinstance(prov, OpenAICompatibleProvider)
    assert prov.name == "openai"
    # get() returns the cached instance by default
    assert reg.get("openai") is prov


def test_registry_get_missing_provider_raises():
    reg = _make_registry()
    with pytest.raises(KeyError):
        reg.get("nope")


def test_registry_fallback_chain():
    reg = _make_registry()
    reg.register_from_config(
        ProviderConfig(
            name="openai",
            type=ProviderType.OPENAI_COMPATIBLE,
            fallback_providers=["anthropic"],
        )
    )
    reg.register_from_config(
        ProviderConfig(name="anthropic", type=ProviderType.OPENAI_COMPATIBLE)
    )
    chain = reg.get_fallback_chain("openai")
    assert [c.name for c in chain] == ["anthropic"]


def test_registry_register_all_from_config():
    reg = _make_registry()
    reg.config = ProviderAbstractionConfig(
        providers=[
            ProviderConfig(name="openai", type=ProviderType.OPENAI_COMPATIBLE),
            ProviderConfig(
                name="disabled", type=ProviderType.OPENAI_COMPATIBLE, enabled=False
            ),
        ]
    )
    reg.register_all_from_config()
    assert reg.list_providers() == ["openai"]  # disabled excluded
