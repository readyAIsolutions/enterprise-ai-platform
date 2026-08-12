"""
OpenAI-Compatible Provider
==========================

Supports OpenAI, OpenRouter, local OpenAI-compatible servers (vLLM, etc.).
"""

from __future__ import annotations

import asyncio
import json
import time
import urllib.error
import urllib.request
from typing import Any, AsyncIterator

from ..config_schema import ProviderConfig, ProviderType
from ..provider_interface import (
    ChatProvider,
    CompletionRequest,
    CompletionResponse,
    HealthStatus,
    Message,
    ProviderError,
    RateLimitError,
    StreamChunk,
    ToolCall,
)


class OpenAICompatibleProvider(ChatProvider):
    """OpenAI-compatible chat completion provider."""

    provider_type = ProviderType.OPENAI_COMPATIBLE
    name = "openai-compatible"
    requires_api_key = True

    def __init__(self, config: ProviderConfig, **kwargs: Any) -> None:
        super().__init__(config, **kwargs)
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPHandler(),
            urllib.request.HTTPSHandler(),
        )

    def get_default_model(self) -> str:
        return self.config.default_model or "gpt-4o-mini"

    def get_supported_models(self) -> list[str]:
        return self.config.supported_models or [
            "gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-4", "gpt-3.5-turbo"
        ]

    def _build_request(self, request: CompletionRequest) -> dict[str, Any]:
        payload = {
            "model": request.model,
            "messages": [m.to_dict() for m in request.messages],
            "temperature": request.temperature,
        }
        if request.max_tokens:
            payload["max_tokens"] = request.max_tokens
        if request.top_p is not None:
            payload["top_p"] = request.top_p
        if request.stop:
            payload["stop"] = request.stop
        if request.stream:
            payload["stream"] = True
            payload["stream_options"] = {"include_usage": True}
        if request.tools:
            payload["tools"] = request.tools
        if request.tool_choice:
            payload["tool_choice"] = request.tool_choice
        return payload

    def _get_request_url(self, endpoint: str = "") -> str:
        base = (self.config.base_url or "https://api.openai.com/v1").rstrip("/")
        if endpoint:
            return f"{base}/{endpoint.lstrip('/')}"
        if base.endswith("/v1"):
            return base + "/chat/completions"
        return base + "/v1/chat/completions"

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        start = time.monotonic()
        self._check_circuit_breaker()
        await self._acquire_rate_limit()

        try:
            payload = self._build_request(request)
            payload["stream"] = False

            body = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                self._get_request_url(),
                data=body,
                headers=self._build_headers(),
                method="POST",
            )

            # Execute request with retries in thread pool
            status, resp_body = await asyncio.to_thread(self._do_request, req)

            if status >= 400:
                error_data = json.loads(resp_body.decode("utf-8", "replace"))
                error_msg = error_data.get("error", {}).get("message", f"HTTP {status}")
                if status == 429:
                    raise RateLimitError(error_msg, self.name, request.model)
                elif status == 401:
                    raise ProviderError(error_msg, self.name, request.model, retryable=False, status_code=401)
                elif status == 404:
                    raise ProviderError(error_msg, self.name, request.model, retryable=False, status_code=404)
                else:
                    raise ProviderError(error_msg, self.name, request.model, retryable=status >= 500, status_code=status)

            data = json.loads(resp_body.decode("utf-8"))
            latency_ms = (time.monotonic() - start) * 1000

            choices = data.get("choices") or []
            text = ""
            tool_calls = None
            finish_reason = None

            if choices:
                msg = choices[0].get("message") or {}
                text = msg.get("content") or ""
                finish_reason = choices[0].get("finish_reason")

                if msg.get("tool_calls"):
                    tool_calls = [
                        ToolCall(
                            id=tc.get("id", ""),
                            name=tc.get("function", {}).get("name", ""),
                            arguments=json.loads(tc.get("function", {}).get("arguments", "{}")),
                        )
                        for tc in msg["tool_calls"]
                    ]

            usage = data.get("usage") or {}
            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)
            cost = self._calculate_cost(request.model, prompt_tokens, completion_tokens)

            self._record_success()
            self._record_request(latency_ms, True, prompt_tokens, completion_tokens, cost)

            return CompletionResponse(
                text=text,
                model=data.get("model", request.model),
                provider=self.name,
                usage={
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": usage.get("total_tokens", prompt_tokens + completion_tokens),
                },
                finish_reason=finish_reason,
                tool_calls=tool_calls,
                latency_ms=latency_ms,
                cost_usd=cost,
            )

        except ProviderError:
            raise
        except Exception as e:
            latency_ms = (time.monotonic() - start) * 1000
            self._record_failure(e)
            self._record_request(latency_ms, False, error=str(e))
            raise ProviderError(f"Request failed: {e}", self.name, request.model, retryable=True)
        finally:
            self._release_rate_limit()

    async def stream(self, request: CompletionRequest) -> AsyncIterator[StreamChunk]:  # type: ignore[override]
        self._check_circuit_breaker()
        await self._acquire_rate_limit()

        try:
            payload = self._build_request(request)
            payload["stream"] = True

            body = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                self._get_request_url(),
                data=body,
                headers=self._build_headers(),
                method="POST",
            )

            # Execute request in thread pool
            resp = await asyncio.to_thread(self._opener.open, req, self.config.timeout_seconds)

            buffer = b""
            while True:
                chunk = await asyncio.to_thread(resp.read, 1024)
                if not chunk:
                    break
                buffer += chunk
                lines = buffer.split(b"\n")
                buffer = lines[-1]  # Keep incomplete line

                for line in lines[:-1]:
                    line = line.strip()
                    if not line or line == b"data: [DONE]":
                        continue
                    if line.startswith(b"data: "):
                        try:
                            data = json.loads(line[6:].decode("utf-8"))
                            choices = data.get("choices") or []
                            if choices:
                                delta = choices[0].get("delta") or {}
                                content = delta.get("content", "")
                                finish_reason = choices[0].get("finish_reason")
                                tool_calls = None

                                if delta.get("tool_calls"):
                                    tool_calls = [
                                        ToolCall(
                                            id=tc.get("id", ""),
                                            name=tc.get("function", {}).get("name", ""),
                                            arguments=json.loads(tc.get("function", {}).get("arguments", "{}")),
                                        )
                                        for tc in delta["tool_calls"]
                                    ]

                                yield StreamChunk(
                                    delta=content,
                                    finish_reason=finish_reason,
                                    tool_calls=tool_calls,
                                )

                                if data.get("usage"):
                                    yield StreamChunk(
                                        delta="",
                                        usage=data["usage"],
                                    )

                        except json.JSONDecodeError:
                            continue

            self._record_success()

        except Exception as e:
            self._record_failure(e)
            raise ProviderError(f"Stream failed: {e}", self.name, request.model, retryable=True)
        finally:
            self._release_rate_limit()

    def _do_request(self, req: urllib.request.Request) -> tuple[int, bytes]:
        """Execute HTTP request with retries."""
        policy = self.config.retry_policy
        last_response: tuple[int, bytes] | None = None
        last_error: Exception | None = None

        for attempt in range(1, policy.max_attempts + 1):
            try:
                with self._opener.open(req, timeout=self.config.timeout_seconds) as resp:
                    status = getattr(resp, "status", None)
                    if status is None:
                        status = getattr(resp, "getcode", lambda: 200)()
                    body = resp.read()
                    return int(status), body
            except urllib.error.HTTPError as e:
                last_response = (e.code, e.read())
                if self._is_retryable(e):
                    if attempt < policy.max_attempts:
                        delay = policy.calculate_delay(attempt)
                        if delay:
                            time.sleep(delay)
                        continue
                raise
            except (TimeoutError, urllib.error.URLError) as e:
                last_error = e
                if attempt < policy.max_attempts:
                    delay = policy.calculate_delay(attempt)
                    if delay:
                        time.sleep(delay)
                    continue
                raise

        if last_response:
            raise urllib.error.HTTPError(req.full_url, last_response[0], "", {}, None)
        raise last_error or RuntimeError("Request failed")

    async def health_check(self) -> HealthStatus:
        start = time.monotonic()
        try:
            # Try a minimal request to models endpoint
            base = (self.config.base_url or "https://api.openai.com/v1").rstrip("/")
            if base.endswith("/v1"):
                url = base + "/models"
            else:
                url = base + "/v1/models"

            req = urllib.request.Request(url, headers=self._build_headers())
            with self._opener.open(req, timeout=self.config.health_check.timeout_seconds) as resp:
                status = getattr(resp, "status", None) or resp.getcode()
                latency_ms = (time.monotonic() - start) * 1000

                if status == 200:
                    return HealthStatus(healthy=True, latency_ms=latency_ms)
                else:
                    return HealthStatus(healthy=False, latency_ms=latency_ms, error=f"HTTP {status}")

        except Exception as e:
            latency_ms = (time.monotonic() - start) * 1000
            return HealthStatus(healthy=False, latency_ms=latency_ms, error=str(e))