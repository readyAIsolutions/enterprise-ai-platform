"""
Observability Engine — distributed tracing (spans), metrics collection, log
aggregation and alerting for the MLOps/LLMOps lifecycle.

Pure-stdlib implementation. Spans form a tree keyed by trace/span id; metric
points and log entries are retained in memory with simple query support;
alert rules are evaluated against the latest metric values.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger("enterprise.mlops_lifecycle.observability_engine")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SpanStatus(Enum):
    OK = "ok"
    ERROR = "error"
    PENDING = "pending"


class AlertSeverity(Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class TraceContext:
    """A single span within a distributed trace."""

    name: str
    service: str
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    span_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    parent_span_id: Optional[str] = None
    status: SpanStatus = SpanStatus.PENDING
    started_at: float = field(default_factory=time.monotonic)
    ended_at: Optional[float] = None
    attributes: Dict[str, Any] = field(default_factory=dict)

    @property
    def duration_ms(self) -> Optional[float]:
        if self.ended_at is None:
            return None
        return (self.ended_at - self.started_at) * 1000.0

    def end(self, status: SpanStatus = SpanStatus.OK) -> None:
        self.status = status
        self.ended_at = time.monotonic()


@dataclass
class MetricPoint:
    """A single timestamped metric reading."""

    name: str
    value: float
    timestamp: str = field(default_factory=_now_iso)
    labels: Dict[str, str] = field(default_factory=dict)
    trace_id: Optional[str] = None


@dataclass
class LogEntry:
    """A structured log line."""

    level: str
    message: str
    timestamp: str = field(default_factory=_now_iso)
    service: str = "mlops_lifecycle"
    trace_id: Optional[str] = None
    attributes: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AlertRule:
    """Rule that fires when a metric crosses a threshold."""

    name: str
    metric: str
    operator: str = ">"
    threshold: float = 1.0
    severity: AlertSeverity | str = AlertSeverity.WARNING
    rule_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def __post_init__(self) -> None:
        if isinstance(self.severity, str):
            self.severity = AlertSeverity(self.severity)


@dataclass
class Alert:
    """A fired alert, created when an AlertRule is violated."""

    rule: AlertRule
    value: float
    timestamp: str = field(default_factory=_now_iso)
    alert_id: str = field(default_factory=lambda: str(uuid.uuid4()))


class ObservabilityEngine:
    """Collects spans, metrics and logs; evaluates alert rules."""

    def __init__(self) -> None:
        self._spans: Dict[str, TraceContext] = {}
        self._metrics: List[MetricPoint] = []
        self._logs: List[LogEntry] = []
        self._rules: Dict[str, AlertRule] = {}
        self._alerts: List[Alert] = []
        self._lock = threading.RLock()

    # -- Tracing ------------------------------------------------------------

    def start_span(
        self,
        name: str,
        service: str = "mlops_lifecycle",
        parent: Optional[TraceContext] = None,
        trace_id: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> TraceContext:
        span = TraceContext(
            name=name,
            service=service,
            trace_id=trace_id or (parent.trace_id if parent else str(uuid.uuid4())),
            parent_span_id=parent.span_id if parent else None,
            attributes=attributes or {},
        )
        with self._lock:
            self._spans[span.span_id] = span
        return span

    def end_span(self, span: TraceContext, status: SpanStatus = SpanStatus.OK) -> None:
        span.end(status=status)
        with self._lock:
            self._spans[span.span_id] = span

    def get_span(self, span_id: str) -> Optional[TraceContext]:
        with self._lock:
            return self._spans.get(span_id)

    def spans_for_trace(self, trace_id: str) -> List[TraceContext]:
        with self._lock:
            return [s for s in self._spans.values() if s.trace_id == trace_id]

    def trace_duration_ms(self, trace_id: str) -> float:
        """Total wall-clock time for the root span of a trace."""
        spans = self.spans_for_trace(trace_id)
        roots = [s for s in spans if s.parent_span_id is None]
        if not roots:
            return 0.0
        return roots[0].duration_ms or 0.0

    # -- Metrics ------------------------------------------------------------

    def record_metric(
        self,
        name: str,
        value: float,
        labels: Optional[Dict[str, str]] = None,
        trace_id: Optional[str] = None,
    ) -> MetricPoint:
        point = MetricPoint(name=name, value=float(value), labels=labels or {}, trace_id=trace_id)
        with self._lock:
            self._metrics.append(point)
            self._evaluate_rules(point)
        return point

    def query_metrics(self, name: str) -> List[MetricPoint]:
        with self._lock:
            return [m for m in self._metrics if m.name == name]

    def latest_metric(self, name: str) -> Optional[MetricPoint]:
        pts = self.query_metrics(name)
        return pts[-1] if pts else None

    # -- Logs ---------------------------------------------------------------

    def emit_log(
        self,
        level: str,
        message: str,
        service: str = "mlops_lifecycle",
        trace_id: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> LogEntry:
        entry = LogEntry(
            level=level, message=message, service=service,
            trace_id=trace_id, attributes=attributes or {},
        )
        with self._lock:
            self._logs.append(entry)
        return entry

    def query_logs(self, level: Optional[str] = None, trace_id: Optional[str] = None) -> List[LogEntry]:
        with self._lock:
            out = self._logs
            if level is not None:
                out = [l for l in out if l.level == level]
            if trace_id is not None:
                out = [l for l in out if l.trace_id == trace_id]
            return list(out)

    # -- Alerting -----------------------------------------------------------

    def register_alert_rule(self, rule: AlertRule) -> str:
        with self._lock:
            self._rules[rule.rule_id] = rule
        return rule.rule_id

    def _evaluate_rules(self, point: MetricPoint) -> None:
        for rule in self._rules.values():
            if rule.metric != point.name:
                continue
            fired = self._compare(rule.operator, point.value, rule.threshold)
            if fired:
                self._alerts.append(Alert(rule=rule, value=point.value))

    @staticmethod
    def _compare(op: str, value: float, threshold: float) -> bool:
        if op == ">":
            return value > threshold
        if op == ">=":
            return value >= threshold
        if op == "<":
            return value < threshold
        if op == "<=":
            return value <= threshold
        if op == "==":
            return abs(value - threshold) < 1e-9
        return False

    def check_alerts(self) -> List[Alert]:
        """Re-evaluate all rules against the latest metric values."""
        with self._lock:
            latest: Dict[str, float] = {}
            for m in self._metrics:
                latest[m.name] = m.value
            fired = []
            for rule in self._rules.values():
                if rule.metric in latest and self._compare(rule.operator, latest[rule.metric], rule.threshold):
                    fired.append(Alert(rule=rule, value=latest[rule.metric]))
            return fired

    def fired_alerts(self) -> List[Alert]:
        with self._lock:
            return list(self._alerts)


def create_observability_engine(config: Optional[Dict[str, Any]] = None) -> ObservabilityEngine:
    """Create a default :class:`ObservabilityEngine`.

    Args:
        config: Optional dict (currently unused; kept for interface parity).
    """
    return ObservabilityEngine()
