"""
Provider Transport — Resilient model backend transport for agent_core
=====================================================================

MASTER CLASS transport layer wiring the real Anthropic and OpenAI-compatible
HTTP APIs into the ENI agent_core query engine.

Pure stdlib (urllib.request) — no third-party deps. Features:

  * ``ChatProvider`` ABC with an async ``complete()`` -> ``ProviderResponse``.
  * ``OpenAICompatibleProvider``  — POSTs ``/v1/chat/completions`` and parses the
    OpenAI chat-completion response.
  * ``AnthropicProvider``         — POSTs the Anthropic ``/v1/messages`` API and
    parses the Claude messages response.
  * ``MockProvider`` / ``EchoProvider`` — deterministic offline providers for
    unit/integration tests (injectable).
  * ``ProviderRegistry`` + ``get_provider(name, config)`` factory.
  * Resilience: exponential backoff on HTTP 429/5xx, connect/timeout retries,
    max-attempts cap, and fallthrough to a fallback provider (LiteLLM style).
  * Fully injectable transport: pass a custom ``opener`` (any object with
    ``open(request, timeout=...)``) so tests run 100% offline.

The blocking urllib call is pushed to an executor thread so the public API stays
asyncio-native.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import time
import urllib.error
import urllib.request
from abc import ABC
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("enterprise.agent.providers")

__all__ = [
    "ProviderResponse",
    "ChatProvider",
    "RetryPolicy",
    "OpenAICompatibleProvider",
    "AnthropicProvider",
    "MockProvider",
    "EchoProvider",
    "ResilientProvider",
    "ProviderRegistry",
    "get_provider",
    "default_opener",
]


# =============================================================================
# Data types
# =============================================================================


@dataclass
class ProviderResponse:
    """Result of a single chat completion."""

    text: str
    usage: dict[str, int] = field(default_factory=dict)
    model: str = ""
    latency: float = 0.0

    @property
    def prompt_tokens(self) -> int:
        return int(self.usage.get("prompt_tokens", 0))

    @property
    def completion_tokens(self) -> int:
        return int(self.usage.get("completion_tokens", 0))

    @property
    def total_tokens(self) -> int:
        return int(self.usage.get("total_tokens", 0))


@dataclass
class RetryPolicy:
    """Exponential backoff + timeout + fallback policy."""

    max_attempts: int = 3
    base_delay: float = 0.5
    max_delay: float = 8.0
    timeout: float = 60.0
    jitter: bool = True
    #: 0.0 disables backoff sleep (used by offline tests)
    disable_sleep: bool = False


# =============================================================================
# HTTP helpers
# =============================================================================


def default_opener() -> urllib.request.OpenerDirector:
    """Build a production-grade opener with sane defaults & retrying redirects.

    Keep-alive is not available in stdlib; we use a short-lived opener per call
    which is acceptable for this transport layer.
    """
    return urllib.request.build_opener(
        urllib.request.HTTPHandler(),
        urllib.request.HTTPSHandler(),
    )


class HttpError(Exception):
    """Raised for non-2xx HTTP responses."""

    def __init__(self, status: int, body: Any = None) -> None:  # noqa: ANN401  # arbitrary response body
        self.status = status
        self.body = body
        super().__init__(f"HTTP {status}: {body if body is not None else ''}")


def _should_retry(status: int) -> bool:
    """429 (rate limit) and 5xx (server) errors are transient."""
    return status == 429 or (500 <= status <= 599)


# =============================================================================
# ChatProvider ABC
# =============================================================================


class ChatProvider(ABC):  # noqa: B024  # interface marker; subclasses implement hooks
    """Abstract chat-completion provider."""

    name: str = "base"
    #: OpenAI-style role mapping fallback; providers override for Anthropic.
    api_key_env: str = ""

    def __init__(
        self,
        base_url: str | None = None,
        api_key_env: str | None = None,
        api_key: str | None = None,
        timeout: float = 60.0,
        opener: Any = None,  # noqa: ANN401  # injectable transport object
        retry: RetryPolicy | None = None,
        fallback: ChatProvider | None = None,
        **kwargs: Any,  # noqa: ARG002, ANN401  # subclasses accept extra ctor kwargs
    ) -> None:
        self.base_url = (base_url or self.default_base_url()).rstrip("/")
        self.api_key_env = api_key_env or self.api_key_env
        self.api_key = api_key
        self.timeout = timeout
        self._opener = opener
        self.retry = retry or RetryPolicy(timeout=timeout)
        self.fallback = fallback
        self.metrics: dict[str, int] = {"calls": 0, "retries": 0, "timeouts": 0}

    # ---- subclass hooks --------------------------------------------------

    def default_base_url(self) -> str:
        return "http://localhost"

    #: Whether this provider needs an API key to authenticate (subclass sets).
    requires_api_key: bool = True

    # ---- request building (subclasses override) --------------------------
    def build_request(
        self,
        messages: list[dict[str, Any]],
        model: str,
        **kw: Any,  # noqa: ANN401
    ) -> dict[str, Any]:
        raise NotImplementedError

    def build_headers(self) -> dict[str, str]:
        return {"Content-Type": "application/json"}

    def parse_response(self, status: int, body_bytes: bytes) -> ProviderResponse:
        raise NotImplementedError

    # ---- public ----------------------------------------------------------

    def get_api_key(self) -> str | None:
        if self.api_key:
            return self.api_key
        if self.api_key_env:
            return os.environ.get(self.api_key_env)
        return None

    def request_url(self) -> str:
        return self.base_url

    def _open_loop(self, request: urllib.request.Request) -> tuple[int, bytes]:
        """Run the urllib POST with retry/backoff, return (status, body)."""
        policy = self.retry
        attempts = max(1, policy.max_attempts)
        last_response: tuple[int, bytes] | None = None
        last_error: Exception | None = None

        for attempt in range(1, attempts + 1):
            try:
                status, body = self._single_post(request)
                self.metrics["calls"] += 1
                if _should_retry(status):
                    last_response = (status, body)
                    if attempt < attempts:
                        _sleep = self._backoff(attempt)
                        if _sleep:
                            time.sleep(_sleep)
                        self.metrics["retries"] += 1
                        logger.warning(
                            "provider %s transient HTTP %s, retry %d/%d",
                            self.name,
                            status,
                            attempt + 1,
                            attempts,
                        )
                        continue
                    return status, body
                return status, body
            except (TimeoutError, urllib.error.URLError, urllib.error.HTTPError) as exc:
                last_error = exc
                self.metrics["timeouts"] += 1
                logger.warning(
                    "provider %s network error %r, retry %d/%d",
                    self.name,
                    exc,
                    attempt + 1,
                    attempts,
                )
                if attempt < attempts:
                    _sleep = self._backoff(attempt)
                    if _sleep:
                        time.sleep(_sleep)
                    self.metrics["retries"] += 1
                    continue
                raise

        # all retries exhausted on a transient/http status
        if last_response is not None:
            status, body = last_response
            raise HttpError(
                status,
                body[:200].decode("utf-8", "replace") if isinstance(body, bytes) else body,
            )
        if last_error is not None:
            raise last_error
        msg = "provider request failed unexpectedly"
        raise RuntimeError(msg)

    def _single_post(self, request: urllib.request.Request) -> tuple[int, bytes]:
        opener = self._opener or default_opener()
        resp = opener.open(request, timeout=self.timeout)
        status = getattr(resp, "status", None)
        if status is None:
            status = getattr(resp, "getcode", lambda: 200)()
        body = resp.read()
        return int(status), body

    def _backoff(self, attempt: int) -> float:
        policy = self.retry
        if policy.disable_sleep:
            return 0.0
        delay = min(policy.max_delay, policy.base_delay * (2 ** (attempt - 1)))
        if policy.jitter:
            delay = delay * random.uniform(0.5, 1.0)
        return delay

    async def complete(
        self,
        messages: list[dict[str, Any]],
        model: str,
        **kw: Any,  # noqa: ANN401
    ) -> ProviderResponse:
        """Complete a chat. Blocking I/O runs in a worker thread."""
        t0 = time.monotonic()
        start = time.monotonic()
        try:
            resp = await asyncio.to_thread(self._complete_sync, messages, model, **kw)
            resp.latency = round(time.monotonic() - start, 4)
            return resp
        finally:
            self.metrics["latency_ms"] = round((time.monotonic() - t0) * 1000, 2)

    def _complete_sync(
        self,
        messages: list[dict[str, Any]],
        model: str,
        **kw: Any,  # noqa: ANN401
    ) -> ProviderResponse:
        payload = self.build_request(messages, model, **kw)
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.request_url(),
            data=body,
            headers=self.build_headers(),
            method="POST",
        )
        status, resp_body = self._open_loop(request)
        return self.parse_response(status, resp_body)


# =============================================================================
# OpenAI-Compatible provider
# =============================================================================


class OpenAICompatibleProvider(ChatProvider):
    """POST /v1/chat/completions, OpenAI-style request/response."""

    name = "openai-compatible"
    api_key_env = "OPENAI_API_KEY"

    def default_base_url(self) -> str:
        return "https://api.openai.com/v1"

    def request_url(self) -> str:
        # base_url typically ends with /v1
        base = self.base_url.rstrip("/")
        if base.endswith("/v1"):
            return base + "/chat/completions"
        return base + "/v1/chat/completions"

    def build_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        key = self.get_api_key()
        if key:
            headers["Authorization"] = f"Bearer {key}"
        # allow caller-supplied extra headers from config
        headers.update(getattr(self, "extra_headers", {}))
        return headers

    def build_request(
        self,
        messages: list[dict[str, Any]],
        model: str,
        **kw: Any,  # noqa: ANN401
    ) -> dict[str, Any]:
        request: dict[str, Any] = {
            "model": model,
            "messages": self._normalize_messages(messages),
            "temperature": kw.get("temperature", 0.7),
        }
        max_tokens = kw.get("max_tokens", kw.get("max_output_tokens"))
        if max_tokens:
            request["max_tokens"] = int(max_tokens)
        if kw.get("top_p") is not None:
            request["top_p"] = kw["top_p"]
        if kw.get("stop") is not None:
            request["stop"] = kw["stop"]
        if kw.get("stream"):
            request["stream"] = True
        if kw.get("tools"):
            request["tools"] = kw["tools"]
        return request

    def _normalize_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out = []
        for m in messages:
            role = m.get("role", "user")
            content = m.get("content", "")
            entry: dict[str, Any] = {"role": role, "content": content}
            if role == "assistant" and m.get("tool_calls"):
                entry["tool_calls"] = m["tool_calls"]
            if m.get("name"):
                entry["name"] = m["name"]
            # tool results
            if role == "tool":
                entry["tool_call_id"] = m.get("tool_call_id", "")
            out.append(entry)
        return out

    def parse_response(self, status: int, body_bytes: bytes) -> ProviderResponse:
        if status < 200 or status >= 300:
            raise HttpError(status, body_bytes.decode("utf-8", "replace"))
        data = json.loads(body_bytes.decode("utf-8"))
        choices = data.get("choices") or []
        text = ""
        if choices:
            msg = choices[0].get("message") or {}
            content = msg.get("content")
            text = content if isinstance(content, str) else ""
        usage = data.get("usage") or {}
        return ProviderResponse(
            text=text,
            usage={
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
            },
            model=data.get("model") or "",
        )


# =============================================================================
# Anthropic provider
# =============================================================================


class AnthropicProvider(ChatProvider):
    """POST the Anthropic /v1/messages API (Claude)."""

    name = "anthropic"
    api_key_env = "ANTHROPIC_API_KEY"
    api_version = "2023-06-01"

    def default_base_url(self) -> str:
        return "https://api.anthropic.com"

    def request_url(self) -> str:
        base = self.base_url.rstrip("/")
        if base.endswith("/v1"):
            return base + "/messages"
        return base + "/v1/messages"

    def build_headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "anthropic-version": self.api_version,
        }
        key = self.get_api_key()
        if key:
            headers["x-api-key"] = key
        headers.update(getattr(self, "extra_headers", {}))
        return headers

    def build_request(
        self,
        messages: list[dict[str, Any]],
        model: str,
        **kw: Any,  # noqa: ANN401
    ) -> dict[str, Any]:
        system_parts = [m["content"] for m in messages if m.get("role") == "system"]
        api_messages = [
            {"role": self._map_role(m.get("role", "user")), "content": m.get("content", "")}
            for m in messages
            if m.get("role") not in ("system",)
        ]
        request: dict[str, Any] = {
            "model": model,
            "max_tokens": int(kw.get("max_tokens", kw.get("max_output_tokens", 1024))),
            "messages": api_messages,
        }
        if system_parts:
            request["system"] = "\n".join(system_parts)
        if kw.get("temperature") is not None:
            request["temperature"] = kw["temperature"]
        if kw.get("top_p") is not None:
            request["top_p"] = kw["top_p"]
        if kw.get("stream"):
            request["stream"] = True
        return request

    @staticmethod
    def _map_role(role: str) -> str:
        # Anthropic accepts only "user" / "assistant" / "tool".
        if role in ("user", "assistant", "tool"):
            return role
        # map system->user; tool messages -> user
        return "user"

    def parse_response(self, status: int, body_bytes: bytes) -> ProviderResponse:
        if status < 200 or status >= 300:
            raise HttpError(status, body_bytes.decode("utf-8", "replace"))
        data = json.loads(body_bytes.decode("utf-8"))
        text = ""
        for block in data.get("content") or []:
            if block.get("type") == "text":
                text += block.get("text", "")
        usage = data.get("usage") or {}
        return ProviderResponse(
            text=text,
            usage={
                "prompt_tokens": usage.get("input_tokens", 0),
                "completion_tokens": usage.get("output_tokens", 0),
                "total_tokens": usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
            },
            model=data.get("model") or "",
        )


# =============================================================================
# Resilient wrapper (fallback chaining)
# =============================================================================


class ResilientProvider(ChatProvider):
    """Wrap a primary provider with retry + fallback delegation.

    On exhausted retries (HttpError or network error), delegates to ``fallback``
    (LiteLLM-style provider fallthrough). Injectable so tests stay offline.
    """

    name = "resilient"

    def __init__(self, primary: ChatProvider, fallback: ChatProvider | None = None) -> None:
        super().__init__(base_url=primary.base_url, fallback=fallback)
        self.primary = primary
        self.fallback = fallback

    async def complete(
        self,
        messages: list[dict[str, Any]],
        model: str,
        **kw: Any,  # noqa: ANN401
    ) -> ProviderResponse:
        try:
            return await self.primary.complete(messages, model, **kw)
        except Exception as exc:
            logger.warning("primary provider failed (%r); trying fallback", exc)
            if self.fallback is None:
                raise
            return await self.fallback.complete(messages, model, **kw)


# =============================================================================
# Offline / mock providers
# =============================================================================


class EchoProvider(ChatProvider):
    """Deterministic offline provider that echoes the last user message."""

    name = "echo"
    requires_api_key = False

    def default_base_url(self) -> str:
        return "mock://echo"

    async def complete(
        self,
        messages: list[dict[str, Any]],
        model: str,
        **kw: Any,  # noqa: ANN401, ARG002
    ) -> ProviderResponse:
        text = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                text = m.get("content", "")
                break
        prompt_tokens = sum(len(str(m.get("content", ""))) // 4 for m in messages)
        return ProviderResponse(
            text=f"{text} [echo]",
            usage={
                "prompt_tokens": prompt_tokens,
                "completion_tokens": max(1, len(text) // 4),
                "total_tokens": prompt_tokens + max(1, len(text) // 4),
            },
            model=model,
        )


class MockProvider(ChatProvider):
    """Configurable offline provider for tests.

    Supports scripted responses and failure injection (429 / 500 / timeout) so
    retry and fallback behaviour can be exercised without network.
    """

    name = "mock"
    requires_api_key = False

    def __init__(
        self,
        responses: list[ProviderResponse] | None = None,
        failures: list[Exception | int] | None = None,
        **kw: Any,  # noqa: ANN401
    ) -> None:
        super().__init__(**kw)
        #: list of ProviderResponse to return in order (last repeats)
        self.responses = list(responses or [])
        #: list of exceptions to raise in order (last repeats)
        self.failures = list(failures or [])
        self.calls: list[dict[str, Any]] = []

    def default_base_url(self) -> str:
        return "mock://mock"

    async def complete(
        self,
        messages: list[dict[str, str]],
        model: str,
        **kw: Any,  # noqa: ANN401
    ) -> ProviderResponse:
        self.calls.append({"model": model, "messages": messages, "kw": kw})
        if self.failures:
            failure = self.failures[0]
            if len(self.failures) > 1:
                self.failures.pop(0)
            if isinstance(failure, Exception):
                raise failure
            if isinstance(failure, int):
                raise HttpError(failure, b"mock failure")
        if self.responses:
            resp = self.responses[0]
            if len(self.responses) > 1:
                self.responses.pop(0)
            if resp is None:
                return ProviderResponse(text="")
            if isinstance(resp, str):
                return ProviderResponse(text=resp, model=model)
            return resp
        return ProviderResponse(
            text="mock response",
            usage={"prompt_tokens": 5, "completion_tokens": 4, "total_tokens": 9},
            model=model,
        )


# =============================================================================
# Registry / factory
# =============================================================================


class ProviderRegistry:
    """Registry of provider *builders* + constructed instances."""

    def __init__(self) -> None:
        self._builders: dict[str, Any] = {}
        self._instances: dict[str, ChatProvider] = {}
        self._register_builtins()

    def _register_builtins(self) -> None:
        self.register("openai", OpenAICompatibleProvider)
        self.register("openai-compatible", OpenAICompatibleProvider)
        self.register("anthropic", AnthropicProvider)
        self.register("claude", AnthropicProvider)
        self.register("mock", MockProvider)
        self.register("echo", EchoProvider)

    def register(self, name: str, builder: Any) -> None:  # noqa: ANN401  # provider class/factory
        self._builders[name] = builder

    def has(self, name: str) -> bool:
        return name in self._builders

    def names(self) -> list[str]:
        return sorted(self._builders)

    def get(self, name: str, config: dict[str, Any] | None = None) -> ChatProvider:
        """Build (or return cached) provider from config."""
        config = config or {}
        if name in self._instances and not config.get("_fresh"):
            return self._instances[name]
        builder = self._builders.get(name)
        if builder is None:
            msg = f"Unknown provider {name!r}; known: {self.names()}"
            raise KeyError(msg)
        allowed = {k: v for k, v in config.items() if k != "_fresh"}
        provider = builder(**allowed)
        if not config.get("_fresh"):
            self._instances[name] = provider
        return provider


_DEFAULT_REGISTRY: ProviderRegistry | None = None


def _registry() -> ProviderRegistry:
    global _DEFAULT_REGISTRY
    if _DEFAULT_REGISTRY is None:
        _DEFAULT_REGISTRY = ProviderRegistry()
    return _DEFAULT_REGISTRY


def get_provider(
    name: str,
    config: dict[str, Any] | None = None,
    registry: ProviderRegistry | None = None,
) -> ChatProvider:
    """Factory: return a provider instance for ``name`` from ``config``."""
    reg = registry or _registry()
    return reg.get(name, config)
