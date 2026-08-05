"""ENI LLMOps Trace OS Module — local, offline LLM tracing & observability.

A langfuse-style, fully-offline tracing/observability subsystem for LLM
applications. Mirrors the ``model_security`` / ``eval_gate`` philosophy: all
components are deterministic and stdlib-only.

An :class:`TraceCollector` stores traces and nested spans, supports querying,
span-tree reconstruction, JSON / JSONL export, an optional JSONL file backend,
and a size cap with FIFO eviction. :class:`SpanEvaluator` aggregates spans into
observability stats, :class:`SpanContext` enables manual ``with collector.span()``
nesting, and :class:`TraceFacade` (wrapped by the @module-decorated
:class:`TraceModule`) exposes the public surface to the rest of the platform.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from enterprise.platform_kernel import (
    EventBus,
    HealthStatus,
    Module,
    module,
)

from .llmops_trace import (
    Span,
    SpanContext,
    SpanEvaluator,
    SpanStatus,
    Trace,
    TraceCollector,
    TraceFacade,
    TraceModule,
)
from .otel_genai import (
    GEN_AI_KEYS,
    ConsoleExporter,
    ExportPipeline,
    GenAISpan,
    JsonlExporter,
    PrometheusExporter,
    Sampler,
    SpanExporter,
    compute_cost,
    end_span,
    reset as reset_otel_state,
    start_genai_span,
    start_span,
    trace_model_call,
    trace_model_call_decorator,
)

__version__ = "1.1.0"
__module__ = "llmops_trace"

__all__ = [
    "__version__",
    # Module
    "TraceModule",
    # Core framework
    "TraceCollector",
    "TraceFacade",
    "SpanEvaluator",
    "SpanContext",
    # Types
    "Trace",
    "Span",
    "SpanStatus",
    # OTel GenAI semantic-convention tracing
    "GenAISpan",
    "GEN_AI_KEYS",
    "start_span",
    "end_span",
    "start_genai_span",
    "compute_cost",
    "Sampler",
    "SpanExporter",
    "ConsoleExporter",
    "JsonlExporter",
    "PrometheusExporter",
    "ExportPipeline",
    "trace_model_call",
    "trace_model_call_decorator",
    "reset_otel_state",
]

_logger = logging.getLogger("enterprise.llmops_trace")


def create_trace_collector(
    config: Optional[Dict[str, Any]] = None,
) -> TraceCollector:
    """Create a :class:`TraceCollector` from an optional config dict.

    Args:
        config: Optional dict with ``max_spans`` (int) and/or ``file_path`` (str).
    """
    cfg = config or {}
    return TraceCollector(
        max_spans=int(cfg.get("max_spans", 1000)),
        file_path=cfg.get("file_path"),
    )
