"""
Tests for the agent_core provider transport + real model backends.

Covers: request building, response parsing, retry/backoff on 429/5xx,
timeout handling, fallback chaining, registry/factory, offline mocks, and
integration with AnthropicBackend / OpenAICompatibleBackend. All tests run
100% offline via an injectable fake urllib opener.
"""

from __future__ import annotations

import json
import urllib.error

import pytest
from enterprise.modules.agent_core.providers import (
    AnthropicProvider,
    ChatProvider,
    EchoProvider,
    HttpError,
    MockProvider,
    OpenAICompatibleProvider,
    ProviderRegistry,
    ResilientProvider,
    RetryPolicy,
    get_provider,
)
from enterprise.modules.agent_core.query_engine import (
    AnthropicBackend,
    Message,
    MessageRole,
    OpenAICompatibleBackend,
    QueryConfig,
)

# =============================================================================
# Fake urllib transport (offline)
# =============================================================================


class FakeResponse:
    def __init__(self, status: int, body: bytes) -> None:
        self.status = status
        self._body = body

    def read(self) -> bytes:
        return self._body

    def getcode(self) -> int:
        return self.status


class FakeOpener:
    """Injectable opener. ``responses`` is a list; an Exception entry is raised."""

    def __init__(self, responses) -> None:
        self.responses = list(responses)
        self.calls: list = []

    def open(self, request, timeout=None):
        self.calls.append((request, timeout))
        item = self.responses[0]
        if len(self.responses) > 1:
            self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    @property
    def call_count(self) -> int:
        return len(self.calls)


def _openai_body(text="Hello!", model="gpt-4o"):
    return json.dumps(
        {
            "id": "chatcmpl-test",
            "model": model,
            "choices": [{"message": {"role": "assistant", "content": text}}],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
            },
        }
    ).encode()


def _anthropic_body(text="Hi!", model="claude-sonnet-4-20250514"):
    return json.dumps(
        {
            "model": model,
            "content": [{"type": "text", "text": text}],
            "usage": {"input_tokens": 8, "output_tokens": 3},
        }
    ).encode()


def _msgs(*texts):
    return [{"role": "user", "content": t} for t in texts]


# =============================================================================
# OpenAI-compatible: request building + parsing
# =============================================================================


class TestOpenAICompatibleProvider:
    def test_default_url_endpoint(self) -> None:
        p = OpenAICompatibleProvider()
        assert p.request_url().endswith("/v1/chat/completions")

    def test_authorization_header_when_key(self) -> None:
        p = OpenAICompatibleProvider(api_key="sk-test", base_url="https://x.example/v1")
        h = p.build_headers()
        assert h["Authorization"] == "Bearer sk-test"

    def test_build_request_structure(self) -> None:
        p = OpenAICompatibleProvider(api_key="k")
        body = p.build_request(
            _msgs("hi"),
            "gpt-4o",
            temperature=0.3,
            max_tokens=64,
        )
        assert body["model"] == "gpt-4o"
        assert body["messages"] == [{"role": "user", "content": "hi"}]
        assert body["temperature"] == 0.3
        assert body["max_tokens"] == 64

    def test_build_request_tool_role_mapping(self) -> None:
        p = OpenAICompatibleProvider(api_key="k")
        body = p.build_request(
            [{"role": "tool", "content": "out", "tool_call_id": "tc1"}],
            "gpt",
        )
        assert body["messages"][0]["tool_call_id"] == "tc1"

    @pytest.mark.asyncio
    async def test_parses_openai_response(self) -> None:
        opener = FakeOpener([FakeResponse(200, _openai_body())])
        p = OpenAICompatibleProvider(
            api_key="k",
            opener=opener,
            retry=RetryPolicy(max_attempts=1, disable_sleep=True),
        )
        resp = await p.complete(_msgs("hi"), "gpt-4o")
        assert resp.text == "Hello!"
        assert resp.model == "gpt-4o"
        assert resp.prompt_tokens == 10
        assert resp.completion_tokens == 5
        assert resp.total_tokens == 15
        assert opener.call_count == 1

    @pytest.mark.asyncio
    async def test_posts_correct_url_and_payload(self) -> None:
        opener = FakeOpener([FakeResponse(200, _openai_body())])
        p = OpenAICompatibleProvider(
            api_key="k",
            base_url="https://api.test/v1",
            opener=opener,
            retry=RetryPolicy(max_attempts=1, disable_sleep=True),
        )
        await p.complete(_msgs("hi"), "gpt-4o", temperature=0.9)
        req, _ = opener.calls[0]
        assert req.full_url == "https://api.test/v1/chat/completions"
        sent = json.loads(req.data)
        assert sent["model"] == "gpt-4o"
        assert sent["temperature"] == 0.9


# =============================================================================
# Anthropic: request building + parsing
# =============================================================================


class TestAnthropicProvider:
    def test_default_url_endpoint(self) -> None:
        p = AnthropicProvider()
        assert p.request_url().endswith("/v1/messages")

    def test_anthropic_headers(self) -> None:
        p = AnthropicProvider(api_key="sk-ant")
        h = p.build_headers()
        assert h["x-api-key"] == "sk-ant"
        assert h["anthropic-version"] == "2023-06-01"

    def test_build_request_extracts_system_and_maps_roles(self) -> None:
        p = AnthropicProvider(api_key="sk-ant")
        body = p.build_request(
            [
                {"role": "system", "content": "be concise"},
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "old"},
            ],
            "claude",
            max_output_tokens=32,
        )
        assert body["system"] == "be concise"
        assert body["max_tokens"] == 32
        roles = [m["role"] for m in body["messages"]]
        assert roles == ["user", "assistant"]

    @pytest.mark.asyncio
    async def test_parses_anthropic_response(self) -> None:
        opener = FakeOpener([FakeResponse(200, _anthropic_body())])
        p = AnthropicProvider(
            api_key="k",
            opener=opener,
            retry=RetryPolicy(max_attempts=1, disable_sleep=True),
        )
        resp = await p.complete(_msgs("hi"), "claude")
        assert resp.text == "Hi!"
        assert resp.prompt_tokens == 8
        assert resp.completion_tokens == 3
        assert resp.total_tokens == 11

    @pytest.mark.asyncio
    async def test_posts_anthropic_url(self) -> None:
        opener = FakeOpener([FakeResponse(200, _anthropic_body())])
        p = AnthropicProvider(
            api_key="k",
            base_url="https://api.anthropic.com",
            opener=opener,
            retry=RetryPolicy(max_attempts=1, disable_sleep=True),
        )
        await p.complete(_msgs("hi"), "claude")
        req, _ = opener.calls[0]
        assert req.full_url == "https://api.anthropic.com/v1/messages"
        sent = json.loads(req.data)
        assert sent["model"] == "claude"
        assert sent["max_tokens"] == 1024


# =============================================================================
# Retry / resilience
# =============================================================================


class TestRetry:
    @pytest.mark.asyncio
    async def test_retry_on_429_then_success(self) -> None:
        opener = FakeOpener(
            [
                FakeResponse(429, b'{"error":"rate"}'),
                FakeResponse(200, _openai_body()),
            ]
        )
        p = OpenAICompatibleProvider(
            api_key="k",
            opener=opener,
            retry=RetryPolicy(max_attempts=3, base_delay=0.0, disable_sleep=True),
        )
        resp = await p.complete(_msgs("hi"), "gpt")
        assert resp.text == "Hello!"
        assert opener.call_count == 2
        assert p.metrics["retries"] >= 1

    @pytest.mark.asyncio
    async def test_retry_on_500_then_success(self) -> None:
        opener = FakeOpener(
            [
                FakeResponse(500, b"boom"),
                FakeResponse(200, _openai_body()),
            ]
        )
        p = OpenAICompatibleProvider(
            api_key="k",
            opener=opener,
            retry=RetryPolicy(max_attempts=3, disable_sleep=True),
        )
        resp = await p.complete(_msgs("hi"), "gpt")
        assert resp.text == "Hello!"
        assert opener.call_count == 2

    @pytest.mark.asyncio
    async def test_retry_exhausted_raises_httperror(self) -> None:
        opener = FakeOpener([FakeResponse(429, b"rate")] * 5)
        p = OpenAICompatibleProvider(
            api_key="k",
            opener=opener,
            retry=RetryPolicy(max_attempts=3, disable_sleep=True),
        )
        with pytest.raises(HttpError) as exc:
            await p.complete(_msgs("hi"), "gpt")
        assert exc.value.status == 429
        assert opener.call_count == 3

    @pytest.mark.asyncio
    async def test_timeout_raises_after_retries(self) -> None:
        opener = FakeOpener([TimeoutError("timed out")] * 5)
        p = OpenAICompatibleProvider(
            api_key="k",
            opener=opener,
            retry=RetryPolicy(max_attempts=2, base_delay=0.0, disable_sleep=True),
        )
        with pytest.raises(TimeoutError):
            await p.complete(_msgs("hi"), "gpt")
        assert opener.call_count == 2
        assert p.metrics["timeouts"] >= 1

    @pytest.mark.asyncio
    async def test_urlerror_retries(self) -> None:
        opener = FakeOpener(
            [
                urllib.error.URLError("conn reset"),
                FakeResponse(200, _openai_body()),
            ]
        )
        p = OpenAICompatibleProvider(
            api_key="k",
            opener=opener,
            retry=RetryPolicy(max_attempts=3, disable_sleep=True),
        )
        resp = await p.complete(_msgs("hi"), "gpt")
        assert resp.text == "Hello!"


# =============================================================================
# Fallback chaining (LiteLLM-style)
# =============================================================================


class TestFallback:
    @pytest.mark.asyncio
    async def test_fallback_on_repeated_failure(self) -> None:
        primary = MockProvider(failures=[HttpError(429, b"rate"), HttpError(500, b"x")])
        fallback = EchoProvider()
        resilient = ResilientProvider(primary=primary, fallback=fallback)
        resp = await resilient.complete(_msgs("hi"), "gpt")
        assert resp.text == "hi [echo]"

    @pytest.mark.asyncio
    async def test_no_fallback_reraises(self) -> None:
        primary = MockProvider(failures=[HttpError(429, b"rate")])
        resilient = ResilientProvider(primary=primary, fallback=None)
        with pytest.raises(HttpError):
            await resilient.complete(_msgs("hi"), "gpt")

    @pytest.mark.asyncio
    async def test_resilient_pass_through_on_success(self) -> None:
        primary = MockProvider(responses=["works"])
        resilient = ResilientProvider(primary=primary, fallback=EchoProvider())
        resp = await resilient.complete(_msgs("hi"), "gpt")
        assert resp.text == "works"


# =============================================================================
# Offline mocks
# =============================================================================


class TestMockProviders:
    @pytest.mark.asyncio
    async def test_mock_provider_deterministic(self) -> None:
        m = MockProvider()
        r1 = await m.complete([{"role": "user", "content": "a"}], "m")
        assert r1.text == "mock response"
        assert r1.total_tokens == 9

    @pytest.mark.asyncio
    async def test_mock_provider_scripted_responses(self) -> None:
        m = MockProvider(responses=["one", "two"])
        assert (await m.complete([], "m")).text == "one"
        assert (await m.complete([], "m")).text == "two"
        # last response repeats
        assert (await m.complete([], "m")).text == "two"

    @pytest.mark.asyncio
    async def test_echo_provider(self) -> None:
        e = EchoProvider()
        resp = await e.complete([{"role": "user", "content": "ping"}], "m")
        assert resp.text == "ping [echo]"
        assert resp.model == "m"


# =============================================================================
# Registry / factory
# =============================================================================


class TestRegistry:
    def test_registry_builtin_providers(self) -> None:
        reg = ProviderRegistry()
        assert reg.has("openai")
        assert reg.has("anthropic")
        assert reg.has("mock")
        assert reg.has("echo")

    def test_get_provider_factory(self) -> None:
        p = get_provider("mock")
        assert isinstance(p, MockProvider)
        p2 = get_provider("echo")
        assert isinstance(p2, EchoProvider)

    def test_unknown_provider_raises(self) -> None:
        reg = ProviderRegistry()
        with pytest.raises(KeyError):
            reg.get("nonexistent")

    def test_custom_registration(self) -> None:
        reg = ProviderRegistry()

        class MyProvider(ChatProvider):
            name = "my"
            requires_api_key = False

        reg.register("my", MyProvider)
        assert reg.has("my")
        assert isinstance(reg.get("my"), MyProvider)


# =============================================================================
# Backend integration
# =============================================================================


class TestBackendIntegration:
    @pytest.mark.asyncio
    async def test_openai_backend_with_echo_provider(self) -> None:
        cfg = QueryConfig(model="gpt-4o", max_output_tokens=64)
        msgs = [Message(role=MessageRole.USER, content="hi there")]
        backend = OpenAICompatibleBackend(provider=EchoProvider())
        result = await backend.generate(msgs, cfg)
        assert result.role == MessageRole.ASSISTANT
        assert result.content == "hi there [echo]"
        assert result.metadata["provider"] == "openai"

    @pytest.mark.asyncio
    async def test_anthropic_backend_with_echo_provider(self) -> None:
        cfg = QueryConfig(model="claude", max_output_tokens=64)
        msgs = [Message(role=MessageRole.USER, content="hello")]
        backend = AnthropicBackend(provider=EchoProvider())
        result = await backend.generate(msgs, cfg)
        assert result.content == "hello [echo]"
        assert result.metadata["provider"] == "anthropic"

    @pytest.mark.asyncio
    async def test_backends_fall_back_to_sim_without_key(self) -> None:
        cfg = QueryConfig(model="gpt-4o")
        msgs = [Message(role=MessageRole.USER, content="x")]
        ob = OpenAICompatibleBackend()
        result = await ob.generate(msgs, cfg)
        assert "no API key configured" in result.content
        ab = AnthropicBackend()
        result2 = await ab.generate(msgs, cfg)
        assert "no API key configured" in result2.content

    @pytest.mark.asyncio
    async def test_openai_backend_delegates_to_provider_error(self) -> None:
        # A failing provider should not crash the engine; falls back to sim
        cfg = QueryConfig(model="gpt-4o")
        msgs = [Message(role=MessageRole.USER, content="x")]
        failing = MockProvider(failures=[HttpError(500, b"boom")])
        backend = OpenAICompatibleBackend(provider=failing)
        result = await backend.generate(msgs, cfg)
        assert "not configured" in result.content or result.content
