"""ENI LLMOps Trace OS Module — local, offline LLM tracing & observability.

A langfuse-style tracing/observability layer for LLM applications that runs
entirely locally and offline (zero cloud/external dependencies — stdlib only).

Design mirrors the ``model_security`` / ``eval_gate`` philosophy: everything is
deterministic, unit-testable, and never leaves the machine.

Core concepts:

  * :class:`Trace`  — a top-level request/unit of work (e.g. one LLM call tree).
  * :class:`Span`   — a single operation inside a trace (generation, retrieval,
    tool call, chain, ...). Spans form a tree via ``parent_id``.
  * :class:`TraceCollector` — in-memory store (thread-safe) that wires spans
    into traces correctly, supports optional JSONL file persistence, querying,
    span-tree reconstruction, export, and a size cap with eviction.
  * :class:`SpanContext` — a context-manager helper for manual
    ``with collector.span(...)`` nesting that auto-wires parent/child and
    marks error spans when an exception propagates.
  * :class:`SpanEvaluator` — aggregates spans into observability stats
    (count, p50/p95/p99 latency, error rate, cost, per-kind breakdown).
  * :class:`TraceFacade` — the public surface, wrapped by the @module-decorated
    :class:`TraceModule` for the Platform Kernel lifecycle.

All components are stdlib-only, zero external dependencies.
"""

from __future__ import annotations

import json
import logging
import math
import statistics
import threading
import time
import uuid
from collections import OrderedDict
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from enterprise.platform_kernel import (
    Event,
    EventBus,
    EventPriority,
    HealthStatus,
    Module,
    module,
)

logger = logging.getLogger("enterprise.llmops_trace")

__version__ = "1.0.0"
__module__ = "llmops_trace"


# =============================================================================
# Enums
# =============================================================================


class SpanStatus(Enum):
    """Lifecycle status of a span."""

    OPEN = "open"
    OK = "ok"
    ERROR = "error"


# =============================================================================
# Core data types
# =============================================================================


@dataclass
class Trace:
    """A top-level unit of work made up of one or more spans."""

    trace_id: str
    name: str
    created_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "name": self.name,
            "created_at": self.created_at,
            "metadata": dict(self.metadata),
        }


@dataclass
class Span:
    """A single operation (generation, retrieval, tool, chain, ...) in a trace."""

    span_id: str
    trace_id: str
    name: str
    kind: str = "general"
    parent_id: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    input: Optional[dict] = None
    output: Optional[dict] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    status: SpanStatus = SpanStatus.OPEN
    error: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    token_counts: Dict[str, int] = field(default_factory=dict)
    cost_est: float = 0.0

    @property
    def is_open(self) -> bool:
        return self.status is SpanStatus.OPEN

    @property
    def latency_ms(self) -> Optional[float]:
        """Wall-clock duration from start to end in milliseconds (or None)."""
        if self.start_time is None or self.end_time is None:
            return None
        return (self.end_time - self.start_time) * 1000.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "span_id": self.span_id,
            "trace_id": self.trace_id,
            "name": self.name,
            "kind": self.kind,
            "parent_id": self.parent_id,
            "created_at": self.created_at,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "latency_ms": self.latency_ms,
            "input": self.input,
            "output": self.output,
            "metadata": dict(self.metadata),
            "status": self.status.value,
            "error": self.error,
            "tags": list(self.tags),
            "token_counts": dict(self.token_counts),
            "cost_est": self.cost_est,
        }


def _new_id() -> str:
    return str(uuid.uuid4())


def _percentile_int(sorted_values: Sequence[float], percentile: float) -> float:
    """Nearest-rank percentile over an ascending-sorted sequence."""
    n = len(sorted_values)
    if n == 0:
        return 0.0
    rank = max(0, min(n - 1, int(math.ceil((percentile / 100.0) * n)) - 1))
    return sorted_values[rank]


# =============================================================================
# Collectors
# =============================================================================


class SpanEvaluator:
    """Aggregate a collection of spans into observability statistics.

    Stats returned by :meth:`summarize`:
      - ``count``           — total completed (non-open) spans.
      - ``open_count``      — spans still open.
      - ``error_count`` / ``error_rate`` — errored spans proportion.
      - ``p50`` / ``p95`` / ``p99`` — latency percentiles (ms), 0.0 if none.
      - ``mean_latency_ms``, ``max_latency_ms``.
      - ``cost_total``      — summed estimated cost.
      - ``by_kind``         — per-kind span counts (dict kind -> count).
    """

    def summarize(self, spans: Sequence[Span]) -> Dict[str, Any]:
        completed = [s for s in spans if s.end_time is not None]
        open_spans = [s for s in spans if s.is_open]
        latencies = sorted(
            (s.latency_ms for s in completed if s.latency_ms is not None),
        )
        errors = [s for s in completed if s.status is SpanStatus.ERROR]
        by_kind: Dict[str, int] = {}
        for s in spans:
            by_kind[s.kind] = by_kind.get(s.kind, 0) + 1

        error_count = len(errors)
        total_completed = len(completed)
        error_rate = (error_count / total_completed) if total_completed else 0.0

        return {
            "count": total_completed,
            "open_count": len(open_spans),
            "error_count": error_count,
            "error_rate": error_rate,
            "p50": _percentile_int(latencies, 50) if latencies else 0.0,
            "p95": _percentile_int(latencies, 95) if latencies else 0.0,
            "p99": _percentile_int(latencies, 99) if latencies else 0.0,
            "mean_latency_ms": statistics.fmean(latencies) if latencies else 0.0,
            "max_latency_ms": max(latencies) if latencies else 0.0,
            "cost_total": sum(s.cost_est or 0.0 for s in spans),
            "by_kind": by_kind,
        }


class TraceCollector:
    """Thread-safe in-memory store for traces and spans.

    Supports an optional JSONL file backend: when ``file_path`` is provided,
    lifecycle records are appended as JSON lines so the trace stream survives
    across processes and can be replayed with :meth:`load_jsonl`.

    A size cap (``max_spans``) bounds the in-memory span table; the oldest
    spans are evicted first (FIFO by insertion time).
    """

    def __init__(
        self,
        max_spans: int = 1000,
        file_path: Optional[Union[str, Path]] = None,
    ) -> None:
        if max_spans < 1:
            raise ValueError("max_spans must be >= 1")
        self._max_spans = int(max_spans)
        self._file_path: Optional[Path] = Path(file_path) if file_path else None
        self._lock = threading.RLock()
        self._spans: "OrderedDict[str, Span]" = OrderedDict()
        self._traces: Dict[str, Trace] = {}
        self._local = threading.local()  # per-thread active context stack

    # -- internal persistence -------------------------------------------------

    def _append_record(self, record: Dict[str, Any]) -> None:
        if self._file_path is None:
            return
        try:
            with self._file_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, default=str) + "\n")
        except OSError as exc:
            logger.warning("Failed to append JSONL record: %s", exc)

    # -- trace management ------------------------------------------------------

    def start_trace(
        self,
        name: str,
        metadata: Optional[Dict[str, Any]] = None,
        trace_id: Optional[str] = None,
    ) -> Trace:
        """Create a new :class:`Trace` and register it (idempotent by id)."""
        with self._lock:
            tid = trace_id or _new_id()
            if tid not in self._traces:
                trace = Trace(
                    trace_id=tid,
                    name=name,
                    metadata=dict(metadata or {}),
                )
                self._traces[tid] = trace
                self._append_record(
                    {"type": "trace_start", "trace": trace.to_dict()}
                )
            return self._traces[tid]

    def get_trace(self, trace_id: str) -> Optional[Dict[str, Any]]:
        """Return trace info plus its spans (as dicts), or None if unknown."""
        with self._lock:
            trace = self._traces.get(trace_id)
            if trace is None:
                return None
            spans = [
                s.to_dict()
                for s in self._spans.values()
                if s.trace_id == trace_id
            ]
            result = trace.to_dict()
            result["spans"] = spans
            return result

    # -- span management -------------------------------------------------------

    def start_span(
        self,
        name: str,
        kind: str = "general",
        parent_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        input: Optional[dict] = None,
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[Sequence[str]] = None,
        token_counts: Optional[Dict[str, int]] = None,
        start_time: Optional[float] = None,
        span_id: Optional[str] = None,
    ) -> Span:
        """Start a span.

        If ``parent_id`` is given it must reference an existing (open or
        completed) span. If ``trace_id`` is omitted the span joins its parent's
        trace, or a new trace (named after the span) is created.
        """
        with self._lock:
            if parent_id is not None and parent_id not in self._spans:
                raise KeyError(f"parent span not found: {parent_id}")
            if trace_id is None and parent_id is not None:
                trace_id = self._spans[parent_id].trace_id
            trace = self._traces.get(trace_id) if trace_id is not None else None
            if trace is None:
                trace = self.start_trace(name=name, trace_id=trace_id)
            span = Span(
                span_id=span_id or _new_id(),
                trace_id=trace.trace_id,
                name=name,
                kind=kind,
                parent_id=parent_id,
                start_time=start_time if start_time is not None else time.time(),
                input=input,
                metadata=dict(metadata or {}),
                tags=list(tags or []),
                token_counts=dict(token_counts or {}),
            )
            self._spans[span.span_id] = span
            self._spans.move_to_end(span.span_id)
            self._evict_locked()
            self._append_record({"type": "span_start", "span": span.to_dict()})
            return span

    def end_span(
        self,
        span_id: str,
        output: Optional[dict] = None,
        status: Union[SpanStatus, str] = SpanStatus.OK,
        error: Optional[str] = None,
        cost_est: Optional[float] = None,
        token_counts: Optional[Dict[str, int]] = None,
        end_time: Optional[float] = None,
    ) -> Span:
        """Close a span, recording its output/status/error/latency."""
        with self._lock:
            span = self._spans.get(span_id)
            if span is None:
                raise KeyError(f"span not found: {span_id}")
            if isinstance(status, str):
                status = SpanStatus(status)
            if error is not None:
                status = SpanStatus.ERROR
                span.error = error
            span.output = output
            span.status = status
            span.end_time = end_time if end_time is not None else time.time()
            if cost_est is not None:
                span.cost_est = float(cost_est)
            if token_counts is not None:
                span.token_counts = dict(token_counts)
            self._append_record({"type": "span_end", "span": span.to_dict()})
            return span

    # -- queries ----------------------------------------------------------------

    def query(
        self,
        kind: Optional[str] = None,
        status: Optional[Union[SpanStatus, str]] = None,
        trace_id: Optional[str] = None,
    ) -> List[Span]:
        """Return spans filtered by kind and/or status (and optional trace)."""
        with self._lock:
            if isinstance(status, str):
                status = SpanStatus(status)
            result: List[Span] = []
            for span in self._spans.values():
                if trace_id is not None and span.trace_id != trace_id:
                    continue
                if kind is not None and span.kind != kind:
                    continue
                if status is not None and span.status is not status:
                    continue
                result.append(span)
            return result

    def children_of(self, span_id: str) -> List[Span]:
        """Return the direct children (spans whose parent is ``span_id``)."""
        with self._lock:
            return [s for s in self._spans.values() if s.parent_id == span_id]

    def span_tree(self, trace_id: str) -> List[Dict[str, Any]]:
        """Reconstruct the nested span tree for a trace.

        Returns a list of root nodes, each ``{"span": {...}, "children": [...]}``.
        """
        with self._lock:
            spans = [s for s in self._spans.values() if s.trace_id == trace_id]
            by_id = {s.span_id: s for s in spans}
            children: Dict[str, List[Span]] = {}
            for s in spans:
                p = s.parent_id
                if p is not None and p in by_id:
                    children.setdefault(p, []).append(s)
                else:
                    children.setdefault(None, []).append(s)

            def build(span: Span) -> Dict[str, Any]:
                node: Dict[str, Any] = {"span": span.to_dict(), "children": []}
                for child in children.get(span.span_id, []):
                    node["children"].append(build(child))
                return node

            return [build(r) for r in children.get(None, [])]

    # -- export ------------------------------------------------------------------

    def export_json(self, trace_id: Optional[str] = None) -> str:
        """Serialize the trace store (optionally one trace) to a JSON string."""
        with self._lock:
            payload = {"traces": [], "spans": []}
            for trace in self._traces.values():
                if trace_id is not None and trace.trace_id != trace_id:
                    continue
                payload["traces"].append(trace.to_dict())
            for span in self._spans.values():
                if trace_id is not None and span.trace_id != trace_id:
                    continue
                payload["spans"].append(span.to_dict())
            return json.dumps(payload, default=str)

    def export_jsonl(self, trace_id: Optional[str] = None) -> str:
        """Serialize the store as newline-delimited JSON (one span per line)."""
        with self._lock:
            lines = []
            for span in self._spans.values():
                if trace_id is not None and span.trace_id != trace_id:
                    continue
                lines.append(json.dumps(span.to_dict(), default=str))
            return "\n".join(lines) + ("\n" if lines else "")

    def _evict_locked(self) -> None:
        """Enforce the size cap, evicting the oldest spans first."""
        while len(self._spans) > self._max_spans:
            _oldest_key, _oldest = self._spans.popitem(last=False)

    def clear(self) -> None:
        """Remove all traces and spans (and rewrite the file backend if set)."""
        with self._lock:
            self._spans.clear()
            self._traces.clear()
            if self._file_path is not None:
                try:
                    self._file_path.write_text("", encoding="utf-8")
                except OSError as exc:
                    logger.warning("Failed to clear JSONL file: %s", exc)

    # -- persistence loading -----------------------------------------------------

    @classmethod
    def load_jsonl(
        cls,
        path: Union[str, Path],
        max_spans: int = 1000,
    ) -> "TraceCollector":
        """Reconstruct a collector by replaying a JSONL file written earlier."""
        collector = cls(max_spans=max_spans)
        path = Path(path)
        if not path.exists():
            return collector
        for line in path.open("r", encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            rtype = record.get("type")
            if rtype == "trace_start":
                td = record.get("trace", {})
                collector.start_trace(
                    name=td.get("name", "trace"),
                    trace_id=td.get("trace_id"),
                )
            elif rtype == "span_start":
                sd = record.get("span", {})
                collector.start_span(
                    name=sd.get("name", "span"),
                    kind=sd.get("kind", "general"),
                    parent_id=sd.get("parent_id"),
                    trace_id=sd.get("trace_id"),
                    input=sd.get("input"),
                    metadata=sd.get("metadata"),
                    tags=sd.get("tags"),
                    token_counts=sd.get("token_counts"),
                    start_time=sd.get("start_time"),
                    span_id=sd.get("span_id"),
                )
            elif rtype == "span_end":
                sd = record.get("span", {})
                sid = sd.get("span_id")
                if sid is None or sid not in collector._spans:
                    continue
                collector.end_span(
                    sid,
                    output=sd.get("output"),
                    status=sd.get("status", "ok"),
                    error=sd.get("error"),
                    cost_est=sd.get("cost_est"),
                    token_counts=sd.get("token_counts"),
                    end_time=sd.get("end_time"),
                )
        return collector

    # -- context-manager helper --------------------------------------------------

    def span(
        self,
        name: str,
        kind: str = "general",
        parent_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        input: Optional[dict] = None,
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[Sequence[str]] = None,
        token_counts: Optional[Dict[str, int]] = None,
    ) -> "SpanContext":
        """Return a :class:`SpanContext` for ``with collector.span(...)``.

        Nested contexts auto-wire parent/child on the same thread and mark the
        span as ERROR when an exception propagates out of the block.
        """
        return SpanContext(
            collector=self,
            name=name,
            kind=kind,
            parent_id=parent_id,
            trace_id=trace_id,
            input=input,
            metadata=metadata,
            tags=tags,
            token_counts=token_counts,
        )

    # -- stats ---------------------------------------------------------------------

    def evaluate(self, trace_id: Optional[str] = None) -> Dict[str, Any]:
        """Aggregate observability stats via :class:`SpanEvaluator`."""
        spans = (
            [s for s in self._spans.values() if s.trace_id == trace_id]
            if trace_id is not None
            else list(self._spans.values())
        )
        return SpanEvaluator().summarize(spans)


class SpanContext:
    """Context manager that starts a span on enter and ends it on exit.

    Nested ``with collector.span(...)`` blocks on the same thread automatically
    select the innermost open span as the parent, so typical usage is::

        with collector.span("chain") as root:
            with collector.span("generate") as gen:
                ...
    """

    def __init__(
        self,
        collector: TraceCollector,
        name: str,
        kind: str = "general",
        parent_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        input: Optional[dict] = None,
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[Sequence[str]] = None,
        token_counts: Optional[Dict[str, int]] = None,
    ) -> None:
        self._collector = collector
        self.name = name
        self.kind = kind
        self._explicit_parent = parent_id
        self._explicit_trace = trace_id
        self.input = input
        self.metadata = metadata
        self.tags = tags
        self.token_counts = token_counts
        self.span: Optional[Span] = None

    def _stack(self) -> List[Tuple[str, str]]:
        if not hasattr(self._collector._local, "stack"):
            self._collector._local.stack = []  # type: ignore[attr-defined]
        return self._collector._local.stack  # type: ignore[attr-defined]

    def __enter__(self) -> Span:
        stack = self._stack()
        with self._collector._lock:
            active = stack[-1] if stack else None
            trace_id = self._explicit_trace
            if trace_id is None and active is not None:
                trace_id = active[0]
            parent_id = self._explicit_parent
            if parent_id is None and active is not None:
                parent_id = active[1]
        self.span = self._collector.start_span(
            name=self.name,
            kind=self.kind,
            parent_id=parent_id,
            trace_id=trace_id,
            input=self.input,
            metadata=self.metadata,
            tags=self.tags,
            token_counts=self.token_counts,
        )
        stack.append((self.span.trace_id, self.span.span_id))
        return self.span

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        stack = self._stack()
        if self.span is not None:
            if exc_type is not None:
                self._collector.end_span(
                    self.span.span_id,
                    status=SpanStatus.ERROR,
                    error=str(exc_val) if exc_val is not None else exc_type.__name__,
                )
            else:
                self._collector.end_span(self.span.span_id)
        if stack and (stack[-1][1] == (self.span.span_id if self.span else None)):
            stack.pop()
        return False


# =============================================================================
# Event helper + Facade
# =============================================================================

_SPAN_END_TOPIC = "llmops_trace.span.end"
_TRACE_TOPIC = "llmops_trace.trace.start"


def _emit(
    bus: Optional[EventBus],
    topic: str,
    source: str,
    payload: Dict[str, Any],
) -> None:
    if bus is None:
        return
    try:
        bus.publish(
            Event.create(
                topic, source=source, payload=payload, priority=EventPriority.NORMAL
            )
        )
    except Exception as exc:  # noqa: BLE001 - never break tracing on emit failure
        logger.warning("Failed to publish trace event %s: %s", topic, exc)


class TraceFacade:
    """Public facade over an :class:`TraceCollector` used by the module/callers.

    Exposes ``start_trace``, ``start_span``, ``end_span``, ``get_trace``,
    ``query``, ``span_tree``, ``export``, ``stats`` and ``clear``. Optionally
    publishes events on a wired EventBus.
    """

    def __init__(
        self,
        collector: Optional[TraceCollector] = None,
        event_bus: Optional[EventBus] = None,
        source: str = "llmops_trace",
    ) -> None:
        self.collector = collector if collector is not None else TraceCollector()
        self._event_bus = event_bus
        self._source = source

    @property
    def event_bus(self) -> Optional[EventBus]:
        return self._event_bus

    @event_bus.setter
    def event_bus(self, value: Optional[EventBus]) -> None:
        self._event_bus = value

    def start_trace(
        self,
        name: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        trace = self.collector.start_trace(name=name, metadata=metadata)
        _emit(
            self._event_bus,
            _TRACE_TOPIC,
            self._source,
            {"trace_id": trace.trace_id, "name": trace.name},
        )
        return trace.trace_id

    def start_span(
        self,
        name: str,
        kind: str = "general",
        parent_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        input: Optional[dict] = None,
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[Sequence[str]] = None,
        token_counts: Optional[Dict[str, int]] = None,
    ) -> Dict[str, Any]:
        span = self.collector.start_span(
            name=name,
            kind=kind,
            parent_id=parent_id,
            trace_id=trace_id,
            input=input,
            metadata=metadata,
            tags=tags,
            token_counts=token_counts,
        )
        return span.to_dict()

    def end_span(
        self,
        span_id: str,
        output: Optional[dict] = None,
        status: Union[SpanStatus, str] = SpanStatus.OK,
        error: Optional[str] = None,
        cost_est: Optional[float] = None,
        token_counts: Optional[Dict[str, int]] = None,
    ) -> Dict[str, Any]:
        span = self.collector.end_span(
            span_id,
            output=output,
            status=status,
            error=error,
            cost_est=cost_est,
            token_counts=token_counts,
        )
        _emit(
            self._event_bus,
            _SPAN_END_TOPIC,
            self._source,
            {
                "span_id": span.span_id,
                "trace_id": span.trace_id,
                "status": span.status.value,
                "latency_ms": span.latency_ms,
            },
        )
        return span.to_dict()

    def get_trace(self, trace_id: str) -> Optional[Dict[str, Any]]:
        return self.collector.get_trace(trace_id)

    def query(
        self,
        kind: Optional[str] = None,
        status: Optional[Union[SpanStatus, str]] = None,
        trace_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        return [s.to_dict() for s in self.collector.query(kind, status, trace_id)]

    def span_tree(self, trace_id: str) -> List[Dict[str, Any]]:
        return self.collector.span_tree(trace_id)

    def export(self, trace_id: Optional[str] = None, jsonl: bool = False) -> str:
        if jsonl:
            return self.collector.export_jsonl(trace_id)
        return self.collector.export_json(trace_id)

    def stats(self, trace_id: Optional[str] = None) -> Dict[str, Any]:
        return self.collector.evaluate(trace_id)

    def clear(self) -> None:
        self.collector.clear()


# =============================================================================
# Platform Kernel module
# =============================================================================


@module(name="llmops_trace", version="1.0.0")
class TraceModule(Module):
    """Platform Kernel module wrapping :class:`TraceFacade`.

    Configuration:
        max_spans (int): size cap for the in-memory span table (default 1000).
        file_path (str): optional JSONL persistence path for the trace stream.

    Events (when a bus is wired via :meth:`set_event_bus` before init):
        - llmops_trace.trace.start — a new trace was created.
        - llmops_trace.span.end    — a span was closed.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(config)
        self._event_bus: Optional[EventBus] = None
        self._facade: Optional[TraceFacade] = None
        self._lock = threading.RLock()

    @property
    def facade(self) -> Optional[TraceFacade]:
        with self._lock:
            return self._facade

    @property
    def event_bus(self) -> Optional[EventBus]:
        with self._lock:
            return self._event_bus

    async def initialize(self) -> None:
        with self._lock:
            self._status = HealthStatus.STARTING
        try:
            max_spans = int(self._config.get("max_spans", 1000))
            file_path = self._config.get("file_path")
            collector = TraceCollector(
                max_spans=max_spans,
                file_path=file_path,
            )
            facade = TraceFacade(
                collector=collector,
                event_bus=self._event_bus,
                source=self.name,
            )
            with self._lock:
                self._facade = facade
                self._status = HealthStatus.HEALTHY
            logger.info(
                "llmops_trace initialized (max_spans=%d, file=%s)",
                max_spans,
                file_path,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to initialize llmops_trace: %s", exc)
            with self._lock:
                self._status = HealthStatus.UNHEALTHY
            raise

    async def health_check(self) -> HealthStatus:
        with self._lock:
            if self._facade is not None and self._status is HealthStatus.HEALTHY:
                return HealthStatus.HEALTHY
            if self._status is HealthStatus.UNHEALTHY:
                return HealthStatus.UNHEALTHY
            self._status = HealthStatus.UNKNOWN
            return self._status

    async def shutdown(self) -> None:
        with self._lock:
            self._status = HealthStatus.STOPPING
            self._facade = None
            logger.info("Shutting down llmops_trace module...")
            self._status = HealthStatus.HEALTHY

    def set_event_bus(self, event_bus: EventBus) -> None:
        """Wire the platform EventBus into the module and its facade."""
        with self._lock:
            self._event_bus = event_bus
            if self._facade is not None:
                self._facade.event_bus = event_bus

    # -- convenience delegates ----------------------------------------------------

    def start_trace(self, name: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        return self._require_facade().start_trace(name, metadata)

    def start_span(self, name: str, kind: str = "general", **kwargs: Any) -> Dict[str, Any]:
        return self._require_facade().start_span(name, kind, **kwargs)

    def end_span(self, span_id: str, **kwargs: Any) -> Dict[str, Any]:
        return self._require_facade().end_span(span_id, **kwargs)

    def get_trace(self, trace_id: str) -> Optional[Dict[str, Any]]:
        return self._require_facade().get_trace(trace_id)

    def query(self, kind: Optional[str] = None, status: Optional[Any] = None) -> List[Dict[str, Any]]:
        return self._require_facade().query(kind, status)

    def span_tree(self, trace_id: str) -> List[Dict[str, Any]]:
        return self._require_facade().span_tree(trace_id)

    def export(self, trace_id: Optional[str] = None, jsonl: bool = False) -> str:
        return self._require_facade().export(trace_id, jsonl)

    def stats(self, trace_id: Optional[str] = None) -> Dict[str, Any]:
        return self._require_facade().stats(trace_id)

    def clear(self) -> None:
        self._require_facade().clear()

    def _require_facade(self) -> TraceFacade:
        facade = self.facade
        if facade is None:
            raise RuntimeError("llmops_trace module is not initialized")
        return facade
