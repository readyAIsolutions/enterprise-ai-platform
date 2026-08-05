"""OpenTelemetry GenAI semantic-convention tracing for ENI LLMOps Trace.

Stdlib-only, contextvars-backed GenAI span tracing that carries the standard
OpenTelemetry GenAI semantic-convention attribute vocabulary (``gen_ai.*``)
so gen-AI spans can be exported as OTLP-style JSON and Prometheus text format,
with head-based / filter sampling and a pluggable span-exporter pipeline.

Design notes:
  * A ``contextvars``-backed span stack keeps a parent/child chain per
    asyncio context / thread. ``start_span`` auto-selects the innermost open
    span as the parent, so nested calls form an accurate tree.
  * ``start_genai_span`` stamps the standard ``gen_ai.*`` attribute keys and
    records latency on end.
  * ``Sampler`` decides keep/drop head-based by ratio and/or name/attr filter;
    dropped spans are neither recorded in a facade nor exported.
  * ``SpanExporter`` / ``ConsoleExporter`` / ``JsonlExporter`` /
    ``PrometheusExporter`` + ``ExportPipeline`` provide a flush() batch hook.
  * ``trace_model_call`` is a context-manager integration helper that wraps a
    model call, records token costs, produces a span, and (optionally) submits
    it to a :class:`TraceFacade` for stats aggregation.

Everything is deterministic and stdlib-only (contextvars, time, uuid, json,
math, random, dataclasses) with zero external dependencies.
"""

from __future__ import annotations

import contextvars
import json
import math
import random
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Union
from contextlib import contextmanager
from pathlib import Path

__version__ = "1.1.0"

GenAIContext = Dict[str, Any]


# ---------------------------------------------------------------------------
# OTel GenAI semantic-convention key vocabulary
# ---------------------------------------------------------------------------

GEN_AI_KEYS: Dict[str, str] = {
    "system": "gen_ai.system",
    "request_model": "gen_ai.request.model",
    "response_model": "gen_ai.response.model",
    "operation_name": "gen_ai.operation.name",
    "usage_input_tokens": "gen_ai.usage.input_tokens",
    "usage_output_tokens": "gen_ai.usage.output_tokens",
    "usage_total_tokens": "gen_ai.usage.total_tokens",
    "server_address": "gen_ai.server.address",
    "request_temperature": "gen_ai.request.temperature",
    "latency_ms": "gen_ai.latency_ms",
    "error": "gen_ai.error",
}

SYSTEM_KEY = GEN_AI_KEYS["system"]
MODEL_KEY = GEN_AI_KEYS["request_model"]
OPERATION_KEY = GEN_AI_KEYS["operation_name"]
INPUT_TOKENS_KEY = GEN_AI_KEYS["usage_input_tokens"]
OUTPUT_TOKENS_KEY = GEN_AI_KEYS["usage_output_tokens"]
LATENCY_KEY = GEN_AI_KEYS["latency_ms"]

VALID_OPERATIONS = ("generate", "embed")

# Approx OpenAI-style $/token defaults (cheap, tunable).
DEFAULT_PRICING: Dict[str, float] = {
    "input": 2.5e-6,
    "output": 10.0e-6,
}


def _new_id() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Contextvars-backed span stack
# ---------------------------------------------------------------------------

_span_stack: "contextvars.ContextVar[List[GenAISpan]]" = contextvars.ContextVar(
    "llmops_genai_span_stack", default=[]
)


@dataclass
class GenAISpan:
    """A single GenAI operation carrying the OTel ``gen_ai.*`` vocabulary."""

    name: str
    span_id: str = field(default_factory=_new_id)
    trace_id: str = field(default_factory=_new_id)
    parent_id: Optional[str] = None
    system: Optional[str] = None
    model: Optional[str] = None
    operation: str = "generate"
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    status: str = "ok"
    error: Optional[str] = None
    cost_est: float = 0.0
    attributes: Dict[str, Any] = field(default_factory=dict)
    dropped: bool = False

    # private reference to the parent object (used for duration clamping)
    _parent: Optional["GenAISpan"] = field(default=None, repr=False, compare=False)

    @property
    def latency_ms(self) -> Optional[float]:
        """Wall-clock duration in milliseconds (or None while open)."""
        if self.start_time is None or self.end_time is None:
            return None
        return (self.end_time - self.start_time) * 1000.0

    def to_otel_json(self) -> Dict[str, Any]:
        """Render this span as an OTLP-style GenAI JSON dict with standard keys."""
        status_code = "STATUS_CODE_ERROR" if self.status == "error" else "STATUS_CODE_OK"
        status_payload: Dict[str, Any] = {
            "code": status_code,
            "message": self.error if self.error is not None else "",
        }
        attrs = dict(self.attributes)
        attrs.setdefault(OPERATION_KEY, self.operation or "generate")
        if self.latency_ms is not None:
            attrs.setdefault(LATENCY_KEY, round(self.latency_ms, 6))
        return {
            "name": self.name,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_id": self.parent_id,
            "kind": "SPAN_KIND_CLIENT",
            "start_time_unix_nano": int(self.start_time * 1_000_000_000),
            "end_time_unix_nano": (
                int(self.end_time * 1_000_000_000) if self.end_time is not None else None
            ),
            "duration_ms": self.latency_ms,
            "cost_est": self.cost_est,
            "attributes": attrs,
            "status": status_payload,
            "dropped": self.dropped,
        }


def start_span(
    name: str,
    attrs: Optional[GenAIContext] = None,
    parent: Optional[GenAISpan] = None,
) -> GenAISpan:
    """Start a span, auto-selecting the innermost open span as its parent.

    A ``contextvars``-backed stack maintains the parent/child chain, so nested
    calls on the same context inherit trace/parent identity correctly.
    """
    stack = _span_stack.get()
    if parent is None and stack:
        parent = stack[-1]
    parent_id = parent.span_id if parent is not None else None
    trace_id = parent.trace_id if parent is not None else _new_id()
    span = GenAISpan(
        name=name,
        parent_id=parent_id,
        trace_id=trace_id,
        _parent=parent,
    )
    if attrs:
        for key, value in attrs.items():
            span.attributes.setdefault(key, value)
    stack.append(span)
    _span_stack.set(stack)
    return span


def end_span(
    span: Optional[GenAISpan] = None,
    status: Optional[str] = None,
    error: Optional[str] = None,
    end_time: Optional[float] = None,
) -> GenAISpan:
    """Close a span (default: the innermost open one), recording latency.

    Child duration is computed from the parent when the parent has already
    ended (its end_time is clamped), giving accurate parent/child timing even
    when a child is closed after its parent.
    """
    stack = _span_stack.get()
    if span is None:
        if not stack:
            raise RuntimeError("end_span called with no spans on the stack")
        span = stack[-1]
    now = end_time if end_time is not None else time.time()
    if error is not None:
        span.status = "error"
        span.error = error
    elif status is not None:
        span.status = status
    span.end_time = now
    # Clamp child duration from parent: a child can never outlive its parent.
    parent = span._parent
    if parent is not None and parent.end_time is not None:
        span.end_time = min(span.end_time, parent.end_time)
        # keep the recorded wall-clock but reflect the parent-constrained window
        if span.start_time < parent.end_time and span.end_time > parent.end_time:
            span.end_time = parent.end_time
    # Pop this span (by identity) from the stack.
    new_stack = [s for s in stack if s is not span]
    if len(new_stack) != len(stack):
        _span_stack.set(new_stack)
    return span


def _active() -> List[GenAISpan]:
    return list(_span_stack.get())


def reset() -> None:
    """Clear the contextvars span stack (idempotent; used for isolation in tests)."""
    _span_stack.set([])


# ---------------------------------------------------------------------------
# OTel GenAI semantic-convention attribute helpers
# ---------------------------------------------------------------------------


def start_genai_span(
    system: str,
    model: str,
    operation: str = "generate",
    input_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None,
    **extra: Any,
) -> GenAISpan:
    """Start a GenAI span stamped with the standard OTel ``gen_ai.*`` attributes.

    Stamps ``gen_ai.system``, ``gen_ai.request.model``,
    ``gen_ai.operation.name`` and (when provided) the usage token counts;
    latency is recorded at :func:`end_span`.
    """
    if operation not in VALID_OPERATIONS:
        raise ValueError(f"operation must be one of {VALID_OPERATIONS}, got {operation!r}")
    attrs: Dict[str, Any] = {
        SYSTEM_KEY: system,
        MODEL_KEY: model,
        OPERATION_KEY: operation,
    }
    if input_tokens is not None:
        attrs[INPUT_TOKENS_KEY] = int(input_tokens)
    if output_tokens is not None:
        attrs[OUTPUT_TOKENS_KEY] = int(output_tokens)
    if input_tokens is not None or output_tokens is not None:
        attrs[GEN_AI_KEYS["usage_total_tokens"]] = int(input_tokens or 0) + int(
            output_tokens or 0
        )
    for key, value in extra.items():
        attrs[key] = value
    span = start_span(name=f"gen_ai.{operation}", attrs=attrs)
    span.system = system
    span.model = model
    span.operation = operation
    span.input_tokens = input_tokens
    span.output_tokens = output_tokens
    return span


def compute_cost(
    span: GenAISpan,
    pricing: Optional[Dict[str, float]] = None,
) -> float:
    """Estimate the cost of a span from its token counts and a price table."""
    prices = pricing or DEFAULT_PRICING
    return (
        (span.input_tokens or 0) * prices.get("input", 0.0)
        + (span.output_tokens or 0) * prices.get("output", 0.0)
    )


# ---------------------------------------------------------------------------
# Sampling
# ---------------------------------------------------------------------------


class Sampler:
    """Decide whether a GenAI span is kept or dropped.

    ``sample_ratio`` is a head-based/ratio sampler: ``1.0`` keeps everything,
    ``0.0`` drops everything, and values in between keep a deterministic
    hash-based fraction of spans. ``name_contains`` and ``attr_has`` add
    whitelist filters (spans failing a filter are dropped).
    """

    def __init__(
        self,
        sample_ratio: float = 1.0,
        name_contains: Optional[str] = None,
        attr_has: Optional[Dict[str, Any]] = None,
        rng: Optional[random.Random] = None,
    ) -> None:
        if not (0.0 <= sample_ratio <= 1.0):
            raise ValueError("sample_ratio must be in [0.0, 1.0]")
        self.sample_ratio = float(sample_ratio)
        self.name_contains = name_contains
        self.attr_has = dict(attr_has or {})
        self._rng = rng or random.Random()

    def should_sample(self, span: GenAISpan) -> bool:
        if self.name_contains is not None and self.name_contains not in span.name:
            return False
        for key, value in self.attr_has.items():
            if span.attributes.get(key) != value:
                return False
        if self.sample_ratio >= 1.0:
            return True
        if self.sample_ratio <= 0.0:
            return False
        # Deterministic head-based draw keyed on the (stable) span id.
        seed = int(uuid.UUID(span.span_id).int)
        return (self._rng.random() if self._rng else ((seed % 10000) / 10000.0)) < self.sample_ratio


# ---------------------------------------------------------------------------
# Exporters
# ---------------------------------------------------------------------------


class SpanExporter:
    """Base interface for span exporters. Subclasses implement :meth:`export`."""

    def export(self, spans: Sequence[Dict[str, Any]]) -> None:
        raise NotImplementedError

    def close(self) -> None:
        """Flush/close any resources. Default no-op."""


class ConsoleExporter(SpanExporter):
    """Print exported OTEL JSON spans to stdout (one per line)."""

    def export(self, spans: Sequence[Dict[str, Any]]) -> None:
        for span in spans:
            print(json.dumps(span, default=str))


class JsonlExporter(SpanExporter):
    """Append exported spans as newline-delimited OTEL JSON to a file."""

    def __init__(self, path: Union[str, Path]) -> None:
        self.path = Path(path)

    def export(self, spans: Sequence[Dict[str, Any]]) -> None:
        with self.path.open("a", encoding="utf-8") as fh:
            for span in spans:
                fh.write(json.dumps(span, default=str) + "\n")


class PrometheusExporter(SpanExporter):
    """Render exported spans as Prometheus text-format counter/gauge lines.

    Counters are aggregated by ``(system, model, operation)``; a latency gauge
    and token counters are emitted per distinct label set.
    """

    def __init__(self) -> None:
        self._lines: List[str] = []
        self._counts: Dict[tuple, int] = {}
        self._input_tokens: Dict[tuple, int] = {}
        self._output_tokens: Dict[tuple, int] = {}

    def export(self, spans: Sequence[Dict[str, Any]]) -> None:
        for span in spans:
            attrs = span.get("attributes", {})
            system = attrs.get(SYSTEM_KEY, "unknown")
            model = attrs.get(MODEL_KEY, "unknown")
            operation = attrs.get(OPERATION_KEY, "generate")
            labels = (system, model, operation)
            self._counts[labels] = self._counts.get(labels, 0) + 1
            self._input_tokens[labels] = self._input_tokens.get(labels, 0) + int(
                attrs.get(INPUT_TOKENS_KEY, 0)
            )
            self._output_tokens[labels] = self._output_tokens.get(labels, 0) + int(
                attrs.get(OUTPUT_TOKENS_KEY, 0)
            )
            self._lines.append(
                'llmops_genai_duration_ms{gen_ai_system="%s",gen_ai_model="%s",'
                'gen_ai_operation="%s",span_id="%s"} %s'
                % (
                    system,
                    model,
                    operation,
                    span.get("span_id", ""),
                    span.get("duration_ms") if span.get("duration_ms") is not None else 0,
                )
            )

    def render(self) -> str:
        lines = [
            "# HELP llmops_genai_spans_total Total gen_ai spans exported.",
            "# TYPE llmops_genai_spans_total counter",
        ]
        for (system, model, operation), count in sorted(self._counts.items()):
            lines.append(
                'llmops_genai_spans_total{gen_ai_system="%s",gen_ai_model="%s",'
                'gen_ai_operation="%s"} %d' % (system, model, operation, count)
            )
        lines.append("# TYPE llmops_genai_input_tokens_total counter")
        for (system, model, operation), value in sorted(self._input_tokens.items()):
            lines.append(
                'llmops_genai_input_tokens_total{system="%s",model="%s",'
                'operation="%s"} %d' % (system, model, operation, value)
            )
        lines.append("# TYPE llmops_genai_output_tokens_total counter")
        for (system, model, operation), value in sorted(self._output_tokens.items()):
            lines.append(
                'llmops_genai_output_tokens_total{system="%s",model="%s",'
                'operation="%s"} %d' % (system, model, operation, value)
            )
        lines.append("# TYPE llmops_genai_duration_ms gauge")
        lines.extend(self._lines)
        return "\n".join(lines) + ("\n" if lines else "")


# ---------------------------------------------------------------------------
# Export pipeline
# ---------------------------------------------------------------------------


class ExportPipeline:
    """Batch spans and deliver them to registered exporters on :meth:`flush`."""

    def __init__(self, exporters: Optional[Sequence[SpanExporter]] = None) -> None:
        self.exporters: List[SpanExporter] = list(exporters or [])
        self._batch: List[GenAISpan] = []

    def register(self, exporter: SpanExporter) -> "ExportPipeline":
        self.exporters.append(exporter)
        return self

    def add(self, span: GenAISpan) -> "ExportPipeline":
        if span.dropped:
            return self
        self._batch.append(span)
        return self

    @property
    def pending(self) -> int:
        return len(self._batch)

    def flush(self) -> int:
        """Convert the batch to OTEL JSON and hand it to every exporter."""
        exported = [span.to_otel_json() for span in self._batch]
        for exporter in self.exporters:
            exporter.export(exported)
        count = len(self._batch)
        self._batch = []
        return count

    def close(self) -> None:
        self.flush()
        for exporter in self.exporters:
            exporter.close()


# ---------------------------------------------------------------------------
# Integration helper
# ---------------------------------------------------------------------------


@contextmanager
def trace_model_call(
    model: str,
    system: Optional[str] = None,
    operation: str = "generate",
    input_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None,
    sampler: Optional[Sampler] = None,
    pipeline: Optional[ExportPipeline] = None,
    facade: Optional[Any] = None,
    pricing: Optional[Dict[str, float]] = None,
    trace_name: Optional[str] = None,
):
    """Context manager that wraps a model call with GenAI tracing.

    Yields a :class:`GenAISpan`; set ``span.input_tokens`` / ``span.output_tokens``
    inside the block before exiting. On exit the helper computes token cost,
    ends the span, and (when provided) records it in a ``TraceFacade`` for stats
    aggregation and submits it to an ``ExportPipeline``. A ``Sampler`` can drop
    the span (then it is neither recorded in the facade nor exported).
    """
    span = start_genai_span(
        system=system or "unknown",
        model=model,
        operation=operation,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )
    keep = True
    if sampler is not None:
        keep = sampler.should_sample(span)
    span.dropped = not keep

    facade_span = None
    facade_trace = None
    if keep and facade is not None:
        facade_trace = facade.start_trace(name=trace_name or f"gen_ai.{operation}")
        facade_span = facade.start_span(
            span.name, kind="generation", trace_id=facade_trace
        )

    try:
        yield span
    finally:
        # tokens may have been set inside the wrapped block
        span.input_tokens = span.input_tokens if span.input_tokens is not None else int(
            span.attributes.get(INPUT_TOKENS_KEY, 0) or 0
        )
        span.output_tokens = (
            span.output_tokens
            if span.output_tokens is not None
            else int(span.attributes.get(OUTPUT_TOKENS_KEY, 0) or 0)
        )
        cost = compute_cost(span, pricing)
        span.cost_est = cost
        end_span(span)

        if keep:
            if facade_span is not None:
                facade.end_span(
                    facade_span["span_id"],
                    cost_est=cost,
                    token_counts={
                        "input": span.input_tokens,
                        "output": span.output_tokens,
                    },
                )
            if pipeline is not None:
                pipeline.add(span)


# ---------------------------------------------------------------------------
# Convenience: trace a plain callable as a decorator
# ---------------------------------------------------------------------------


def trace_model_call_decorator(
    model: str,
    system: Optional[str] = None,
    operation: str = "generate",
    sampler: Optional[Sampler] = None,
    pipeline: Optional[ExportPipeline] = None,
    facade: Optional[Any] = None,
    pricing: Optional[Dict[str, float]] = None,
):
    """Decorator form of :func:`trace_model_call`.

    The wrapped callable should return ``(result, input_tokens, output_tokens)``
    or a dict with an ``"output"`` plus ``input_tokens`` / ``output_tokens``.
    """

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            with trace_model_call(
                model=model,
                system=system,
                operation=operation,
                sampler=sampler,
                pipeline=pipeline,
                facade=facade,
                pricing=pricing,
            ) as span:
                result = fn(*args, **kwargs)
                if isinstance(result, dict):
                    span.output_tokens = result.get("output_tokens")
                    span.input_tokens = result.get("input_tokens")
                elif isinstance(result, tuple) and len(result) == 3:
                    result, span.input_tokens, span.output_tokens = result
            return result

        return wrapper

    return decorator
