"""
Streaming Adapter — SSE Normalization
======================================

Normalizes streaming responses from all providers into unified SSE format.
Provides fake SSE generation for non-streaming upstreams.

Follows ENI patterns: stdlib-first, async-native, comprehensive type hints.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Callable

from .provider_interface import (
    ChatProvider,
    CompletionRequest,
    CompletionResponse,
    StreamChunk,
    ProviderError,
)
from .config_schema import StreamingConfig


@dataclass
class SSEEvent:
    """Server-Sent Event."""

    event: str | None = None
    data: str = ""
    id: str | None = None
    retry: int | None = None

    def to_sse(self) -> str:
        lines = []
        if self.event:
            lines.append(f"event: {self.event}")
        if self.id:
            lines.append(f"id: {self.id}")
        if self.retry is not None:
            lines.append(f"retry: {self.retry}")
        # Data can be multi-line
        for line in self.data.splitlines():
            lines.append(f"data: {line}")
        return "\n".join(lines) + "\n\n"

    @classmethod
    def from_chunk(cls, chunk: StreamChunk, event_id: str | None = None) -> SSEEvent:
        """Create SSE event from stream chunk."""
        return cls(
            event="message",
            data=chunk.to_sse().replace("data: ", "").strip(),
            id=event_id,
        )

    @classmethod
    def heartbeat(cls) -> SSEEvent:
        """Create heartbeat event."""
        return cls(event="heartbeat", data="{}", id=str(int(time.time())))

    @classmethod
    def error(cls, message: str, event_id: str | None = None) -> SSEEvent:
        """Create error event."""
        return cls(event="error", data=json.dumps({"error": message}), id=event_id)

    @classmethod
    def done(cls, event_id: str | None = None) -> SSEEvent:
        """Create done event."""
        return cls(event="done", data="[DONE]", id=event_id)


class StreamingAdapter:
    """
    Adapts provider streaming to unified SSE format.

    Features:
    - Normalizes all provider streams to SSE
    - Fake SSE generation for non-streaming providers
    - Heartbeat/keepalive for long connections
    - Buffering and backpressure handling
    - Automatic reconnection support
    """

    def __init__(
        self,
        provider: ChatProvider,
        config: StreamingConfig | None = None,
        metrics_callback: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> None:
        self.provider = provider
        self.config = config or StreamingConfig()
        self._metrics_callback = metrics_callback
        self._buffer: list[SSEEvent] = []
        self._buffer_size = 0
        self._event_counter = 0
        self._heartbeat_task: asyncio.Task | None = None
        self._closed = False

    def _emit_metric(self, name: str, value: float, labels: dict[str, str] | None = None) -> None:
        if self._metrics_callback:
            try:
                self._metrics_callback(name, {"value": value, "labels": labels or {}})
            except Exception:
                pass

    def _next_event_id(self) -> str:
        self._event_counter += 1
        return f"{self.provider.name}-{self._event_counter}-{int(time.time() * 1000)}"

    async def stream_sse(self, request: CompletionRequest) -> AsyncIterator[str]:
        """
        Stream completion as SSE events.

        Yields SSE-formatted strings ready for HTTP response.
        """
        if not self.config.enabled:
            # Fall back to non-streaming
            response = await self.provider.complete(request)
            yield self._response_to_sse(response)
            return

        self._closed = False

        # Start heartbeat if configured
        if self.config.heartbeat_interval_seconds > 0:
            self._heartbeat_queue: asyncio.Queue[SSEEvent] = asyncio.Queue()
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop(self._heartbeat_queue))

        try:
            if request.stream and hasattr(self.provider, "_stream_native"):
                # Provider has native streaming
                async for sse_event in self._stream_native_sse(request):
                    if self._closed:
                        break
                    yield sse_event.to_sse()
                    # Check for heartbeats
                    if hasattr(self, "_heartbeat_queue"):
                        try:
                            hb = self._heartbeat_queue.get_nowait()
                            yield hb.to_sse()
                        except asyncio.QueueEmpty:
                            pass
            else:
                # Fake SSE from non-streaming response
                async for sse_event in self._fake_sse(request):
                    if self._closed:
                        break
                    yield sse_event.to_sse()
                    # Check for heartbeats
                    if hasattr(self, "_heartbeat_queue"):
                        try:
                            hb = self._heartbeat_queue.get_nowait()
                            yield hb.to_sse()
                        except asyncio.QueueEmpty:
                            pass

        except Exception as e:
            yield SSEEvent.error(str(e), self._next_event_id()).to_sse()
            raise
        finally:
            if self._heartbeat_task:
                self._heartbeat_task.cancel()
                try:
                    await self._heartbeat_task
                except asyncio.CancelledError:
                    pass
            # Drain any remaining heartbeats
            if hasattr(self, "_heartbeat_queue"):
                while not self._heartbeat_queue.empty():
                    try:
                        hb = self._heartbeat_queue.get_nowait()
                        yield hb.to_sse()
                    except asyncio.QueueEmpty:
                        break
            yield SSEEvent.done(self._next_event_id()).to_sse()

    async def _stream_native_sse(self, request: CompletionRequest) -> AsyncIterator[SSEEvent]:  # type: ignore[return-type]
        """Stream from provider with native streaming support."""
        chunk_count = 0
        async for chunk in self.provider.stream(request):  # type: ignore[attr-defined]
            chunk_count += 1
            event_id = self._next_event_id()

            # Convert chunk to SSE event
            if chunk.delta:
                yield SSEEvent(
                    event="message",
                    data=json.dumps({"delta": chunk.delta, "finish_reason": chunk.finish_reason}),
                    id=event_id,
                )
            elif chunk.finish_reason:
                yield SSEEvent(
                    event="message",
                    data=json.dumps({"finish_reason": chunk.finish_reason}),
                    id=event_id,
                )

            if chunk.usage:
                yield SSEEvent(
                    event="usage",
                    data=json.dumps(chunk.usage),
                    id=self._next_event_id(),
                )

        self._emit_metric("stream_chunks_total", chunk_count, {"provider": self.provider.name})

    async def _fake_sse(self, request: CompletionRequest) -> AsyncIterator[SSEEvent]:  # type: ignore[return-type]
        """
        Generate fake SSE events from non-streaming response.

        Splits response into chunks and emits them with small delays
        to simulate streaming behavior.
        """
        # Get non-streaming response
        non_stream_request = CompletionRequest(
            messages=request.messages,
            model=request.model,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            top_p=request.top_p,
            stop=request.stop,
            stream=False,
            tools=request.tools,
            tool_choice=request.tool_choice,
            metadata=request.metadata,
        )

        response = await self.provider.complete(non_stream_request)

        if not response.text:
            yield SSEEvent.done(self._next_event_id())
            return

        # Split text into chunks
        text = response.text
        chunk_size = self.config.chunk_size
        chunks = [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]

        for i, chunk_text in enumerate(chunks):
            if self._closed:
                break

            event_id = self._next_event_id()
            is_last = i == len(chunks) - 1

            yield SSEEvent(
                event="message",
                data=json.dumps({
                    "delta": chunk_text,
                    "finish_reason": "stop" if is_last else None,
                }),
                id=event_id,
            )

            # Small delay to simulate streaming
            if not is_last and self.config.heartbeat_interval_seconds > 0:
                await asyncio.sleep(0.01)  # 10ms between chunks

        # Send usage if available
        if response.usage:
            yield SSEEvent(
                event="usage",
                data=json.dumps(response.usage),
                id=self._next_event_id(),
            )

        self._emit_metric("fake_sse_chunks_total", len(chunks), {"provider": self.provider.name})

    def _response_to_sse(self, response: CompletionResponse) -> str:
        """Convert non-streaming response to single SSE event."""
        event = SSEEvent(
            event="message",
            data=json.dumps({
                "text": response.text,
                "model": response.model,
                "provider": response.provider,
                "usage": response.usage,
                "finish_reason": response.finish_reason,
                "cost_usd": response.cost_usd,
            }),
            id=self._next_event_id(),
        )
        return event.to_sse() + SSEEvent.done(self._next_event_id()).to_sse()

    async def _heartbeat_loop(self, queue: asyncio.Queue[SSEEvent]) -> None:
        """Send periodic heartbeat events to queue."""
        try:
            while not self._closed:
                await asyncio.sleep(self.config.heartbeat_interval_seconds)
                if not self._closed:
                    await queue.put(SSEEvent.heartbeat())
        except asyncio.CancelledError:
            pass

    def close(self) -> None:
        """Close the adapter and stop streaming."""
        self._closed = True
        if self._heartbeat_task:
            self._heartbeat_task.cancel()


class MultiProviderStreamingAdapter:
    """
    Streaming adapter with automatic provider fallback.

    Wraps multiple providers and falls back seamlessly during streaming.
    """

    def __init__(
        self,
        providers: dict[str, ChatProvider],
        primary: str,
        fallbacks: list[str],
        config: StreamingConfig | None = None,
        metrics_callback: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> None:
        self.providers = providers
        self.primary_name = primary
        self.fallback_names = fallbacks
        self.config = config or StreamingConfig()
        self._metrics_callback = metrics_callback
        self._current_adapter: StreamingAdapter | None = None

    def _emit_metric(self, name: str, value: float, labels: dict[str, str] | None = None) -> None:
        if self._metrics_callback:
            try:
                self._metrics_callback(name, {"value": value, "labels": labels or {}})
            except Exception:
                pass

    async def stream_sse(self, request: CompletionRequest) -> AsyncIterator[str]:
        """Stream with automatic fallback on failure."""
        chain = [self.primary_name] + self.fallback_names

        for provider_name in chain:
            provider = self.providers.get(provider_name)
            if not provider:
                continue

            self._current_adapter = StreamingAdapter(provider, self.config, self._metrics_callback)

            try:
                async for sse_line in self._current_adapter.stream_sse(request):
                    yield sse_line
                return  # Success, don't try fallbacks

            except Exception as e:
                self._emit_metric("stream_fallback", 1, {"from": provider_name, "error": type(e).__name__})
                if provider_name == chain[-1]:
                    # Last provider, re-raise
                    raise
                # Continue to next fallback
                continue

    def close(self) -> None:
        """Close current adapter."""
        if self._current_adapter:
            self._current_adapter.close()


# Convenience function for direct SSE generation
async def generate_sse_stream(
    provider: ChatProvider,
    request: CompletionRequest,
    config: StreamingConfig | None = None,
) -> AsyncIterator[str]:
    """Generate SSE stream from provider (convenience function)."""
    adapter = StreamingAdapter(provider, config)
    async for line in adapter.stream_sse(request):
        yield line


# OpenAI-compatible SSE format helpers
def format_openai_chunk(
    delta: str = "",
    finish_reason: str | None = None,
    model: str = "",
    usage: dict[str, int] | None = None,
) -> str:
    """Format chunk in OpenAI streaming format."""
    chunk = {
        "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [{
            "index": 0,
            "delta": {"content": delta} if delta else {},
            "finish_reason": finish_reason,
        }],
    }
    if usage:
        chunk["usage"] = usage
    return f"data: {json.dumps(chunk)}\n\n"


def format_openai_done(model: str = "") -> str:
    """Format OpenAI done signal."""
    chunk = {
        "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [{
            "index": 0,
            "delta": {},
            "finish_reason": "stop",
        }],
    }
    return f"data: {json.dumps(chunk)}\n\ndata: [DONE]\n\n"


def format_anthropic_stream_start(model: str) -> str:
    """Format Anthropic stream start."""
    return f"event: message_start\ndata: {json.dumps({'type': 'message_start', 'message': {'id': f'msg_{uuid.uuid4().hex[:24]}', 'type': 'message', 'role': 'assistant', 'model': model, 'content': [], 'stop_reason': None, 'stop_sequence': None, 'usage': {'input_tokens': 0, 'output_tokens': 0}}})}\n\n"


def format_anthropic_delta(delta: str) -> str:
    """Format Anthropic content delta."""
    return f"event: content_block_delta\ndata: {json.dumps({'type': 'content_block_delta', 'index': 0, 'delta': {'type': 'text_delta', 'text': delta}})}\n\n"


def format_anthropic_stream_end() -> str:
    """Format Anthropic stream end."""
    return f"event: message_delta\ndata: {json.dumps({'type': 'message_delta', 'delta': {'stop_reason': 'end_turn', 'stop_sequence': None}, 'usage': {'output_tokens': 0}})}\n\nevent: message_stop\ndata: {json.dumps({'type': 'message_stop'})}\n\n"


__all__ = [
    "SSEEvent",
    "StreamingAdapter",
    "MultiProviderStreamingAdapter",
    "generate_sse_stream",
    "format_openai_chunk",
    "format_openai_done",
    "format_anthropic_stream_start",
    "format_anthropic_delta",
    "format_anthropic_stream_end",
]