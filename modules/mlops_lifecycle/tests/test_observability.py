"""Tests for the Observability Engine (tracing, metrics, logs, alerts)."""

from modules.mlops_lifecycle.observability_engine import (
    AlertRule,
    AlertSeverity,
    ObservabilityEngine,
    SpanStatus,
    TraceContext,
    create_observability_engine,
)


def test_create_observability_engine_returns_default_instance():
    eng = create_observability_engine()
    assert isinstance(eng, ObservabilityEngine)


def test_trace_context_start_and_end():
    eng = ObservabilityEngine()
    span = eng.start_span("train", service="trainer")
    assert isinstance(span, TraceContext)
    assert span.duration_ms is None
    eng.end_span(span, SpanStatus.OK)
    assert span.status is SpanStatus.OK
    assert span.duration_ms is not None and span.duration_ms >= 0
    assert eng.get_span(span.span_id).span_id == span.span_id


def test_parent_child_spans_share_trace():
    eng = ObservabilityEngine()
    root = eng.start_span("experiment")
    child = eng.start_span("eval", parent=root)
    assert child.trace_id == root.trace_id
    assert child.parent_span_id == root.span_id
    eng.end_span(root)
    eng.end_span(child)
    assert len(eng.spans_for_trace(root.trace_id)) == 2


def test_metric_recording_and_query():
    eng = ObservabilityEngine()
    eng.record_metric("accuracy", 0.94, labels={"version": "v1"})
    eng.record_metric("accuracy", 0.96)
    pts = eng.query_metrics("accuracy")
    assert len(pts) == 2
    assert eng.latest_metric("accuracy").value == 0.96


def test_log_emission_and_filter():
    eng = ObservabilityEngine()
    eng.emit_log("info", "started", trace_id="t1")
    eng.emit_log("error", "boom", trace_id="t1")
    assert len(eng.query_logs(level="error")) == 1
    assert len(eng.query_logs(trace_id="t1")) == 2


def test_alert_rule_fires_on_threshold_breach():
    eng = ObservabilityEngine()
    rule = AlertRule(name="high_latency", metric="latency_p99", operator=">", threshold=500.0)
    eng.register_alert_rule(rule)
    eng.record_metric("latency_p99", 900.0)
    fired = eng.check_alerts()
    assert len(fired) == 1
    assert fired[0].rule.severity == AlertSeverity.WARNING


def test_alert_rule_does_not_fire_within_threshold():
    eng = ObservabilityEngine()
    rule = AlertRule(name="high_latency", metric="latency_p99", operator=">", threshold=500.0)
    eng.register_alert_rule(rule)
    eng.record_metric("latency_p99", 100.0)
    assert eng.check_alerts() == []
