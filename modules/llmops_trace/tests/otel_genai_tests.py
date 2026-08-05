"""Unit tests for the OTel GenAI semantic-convention tracing layer.

Covers the contextvars-backed span stack (parent/child timing), the
``gen_ai.*`` attribute vocabulary, head-based/filter sampling, the exporter
pipeline (JsonlExporter file flush + Prometheus rendering), and the
``trace_model_call`` integration helper that records a span + cost into a
TraceFacade. All file-based tests are hermetic (use tmp_path).

Run with:
    python3 -m pytest modules/llmops_trace -q
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from enterprise.modules.llmops_trace.otel_genai import (
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
    reset as reset_otel,
    start_genai_span,
    start_span,
    trace_model_call,
    trace_model_call_decorator,
)
from enterprise.modules.llmops_trace.llmops_trace import TraceFacade


def _fixture():
    reset_otel()


# ═══════════════════════════════════════════════════════════════════════════
# contextvars span stack: parent/child timing
# ═══════════════════════════════════════════════════════════════════════════


def test_start_span_auto_parent_via_contextvars():
    reset_otel()
    root = start_span("root")
    time.sleep(0.005)
    child = start_span("child")  # no explicit parent -> innermost open span
    assert child.parent_id == root.span_id, "child must inherit root as parent"
    assert child.trace_id == root.trace_id, "child must inherit trace id"
    assert isinstance(child, GenAISpan)


def test_end_span_computes_latency_and_child_duration_within_parent():
    reset_otel()
    root = start_span("root")
    time.sleep(0.002)
    child = start_span("child")
    time.sleep(0.003)
    end_span(child)
    end_span(root)
    assert root.latency_ms is not None and root.latency_ms > 0
    assert child.latency_ms is not None and child.latency_ms > 0
    # child duration must not exceed its parent (accurate parent/child timing)
    assert child.latency_ms <= root.latency_ms + 1e-9
    assert child.end_time <= root.end_time


def test_end_span_clamps_child_duration_from_parent():
    reset_otel()
    root = start_span("root")
    time.sleep(0.001)
    child = start_span("child")
    end_span(root)  # parent ends first (order violation)
    time.sleep(0.003)
    end_span(child)  # child ends after parent -> clamped to parent end
    assert child.end_time is not None and root.end_time is not None
    assert child.end_time <= root.end_time, "child end must be clamped to parent"


def test_end_span_missing_stack_raises():
    reset_otel()
    import pytest

    with pytest.raises(RuntimeError):
        end_span()


# ═══════════════════════════════════════════════════════════════════════════
# gen_ai.* semantic-convention attributes
# ═══════════════════════════════════════════════════════════════════════════


def test_gen_ai_keys_vocabulary():
    assert GEN_AI_KEYS["system"] == "gen_ai.system"
    assert GEN_AI_KEYS["request_model"] == "gen_ai.request.model"
    assert GEN_AI_KEYS["operation_name"] == "gen_ai.operation.name"
    assert GEN_AI_KEYS["usage_input_tokens"] == "gen_ai.usage.input_tokens"


def test_start_genai_span_stamps_standard_attributes():
    reset_otel()
    sp = start_genai_span(
        system="openai",
        model="gpt-4o",
        operation="generate",
        input_tokens=10,
        output_tokens=20,
    )
    end_span(sp)
    assert sp.attributes["gen_ai.system"] == "openai"
    assert sp.attributes["gen_ai.request.model"] == "gpt-4o"
    assert sp.attributes["gen_ai.operation.name"] == "generate"
    assert sp.attributes["gen_ai.usage.input_tokens"] == 10
    assert sp.attributes["gen_ai.usage.output_tokens"] == 20
    assert sp.attributes["gen_ai.usage.total_tokens"] == 30
    assert sp.latency_ms is not None
    assert sp.operation == "generate" and sp.system == "openai" and sp.model == "gpt-4o"


def test_start_genai_span_embed_and_invalid_operation():
    reset_otel()
    import pytest

    emb = start_genai_span("voyage", "embed-3", operation="embed", input_tokens=4)
    end_span(emb)
    assert emb.attributes["gen_ai.operation.name"] == "embed"
    with pytest.raises(ValueError):
        start_genai_span("x", "y", operation="nope")


def test_compute_cost_from_tokens():
    sp = GenAISpan(name="g", input_tokens=10, output_tokens=20)
    cost = compute_cost(sp, pricing={"input": 1e-6, "output": 2e-6})
    assert cost == 10 * 1e-6 + 20 * 2e-6
    assert cost > 0


# ═══════════════════════════════════════════════════════════════════════════
# Sampling
# ═══════════════════════════════════════════════════════════════════════════


def test_sampler_ratio_one_keeps_all_and_zero_drops_all():
    reset_otel()
    keep = Sampler(sample_ratio=1.0)
    drop = Sampler(sample_ratio=0.0)
    for i in range(5):
        sp = start_genai_span("sys", f"model{i}", input_tokens=1)
        assert keep.should_sample(sp) is True
        assert drop.should_sample(sp) is False
        end_span(sp)


def test_sampler_name_and_attr_filter():
    s = Sampler(sample_ratio=1.0, name_contains="generate", attr_has={"gen_ai.system": "openai"})
    ok = start_genai_span("openai", "gpt-4o", operation="generate")
    bad_name = start_genai_span("openai", "gpt-4o", operation="embed")
    bad_sys = start_genai_span("anthropic", "claude", operation="generate")
    assert s.should_sample(ok) is True
    assert s.should_sample(bad_name) is False
    assert s.should_sample(bad_sys) is False
    end_span(ok)
    end_span(bad_name)
    end_span(bad_sys)


def test_sampler_ratio_below_drops_some():
    # sample_ratio 0.0 => every span dropped (deterministic)
    s = Sampler(sample_ratio=0.0)
    dropped = []
    for i in range(20):
        sp = start_span(f"s{i}")
        dropped.append(s.should_sample(sp))
        end_span(sp)
    assert all(d is False for d in dropped)


# ═══════════════════════════════════════════════════════════════════════════
# OTel JSON export + pipeline -> JsonlExporter file
# ═══════════════════════════════════════════════════════════════════════════


def test_to_otel_json_standard_keys():
    reset_otel()
    sp = start_genai_span("openai", "gpt-4o", operation="generate", input_tokens=5, output_tokens=7)
    end_span(sp)
    d = sp.to_otel_json()
    assert d["name"] == "gen_ai.generate"
    assert d["kind"] == "SPAN_KIND_CLIENT"
    assert d["span_id"] and d["trace_id"]
    assert d["attributes"]["gen_ai.operation.name"] == "generate"
    assert d["attributes"]["gen_ai.usage.input_tokens"] == 5
    assert d["status"]["code"] == "STATUS_CODE_OK"
    assert d["duration_ms"] is not None
    assert d["start_time_unix_nano"] and d["end_time_unix_nano"]


def test_pipeline_flushes_to_jsonl_file(tmp_path):
    reset_otel()
    path = tmp_path / "genai_spans.jsonl"
    exporter = JsonlExporter(path)
    pipe = ExportPipeline(exporters=[exporter])
    sp = start_genai_span("openai", "gpt-4o", operation="generate", input_tokens=3, output_tokens=4)
    end_span(sp)
    pipe.add(sp)
    assert pipe.pending == 1
    flushed = pipe.flush()
    assert flushed == 1
    lines = [l for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["attributes"]["gen_ai.system"] == "openai"
    assert record["attributes"]["gen_ai.request.model"] == "gpt-4o"
    assert record["name"] == "gen_ai.generate"
    assert pipe.pending == 0


def test_pipeline_dropped_span_not_exported(tmp_path):
    reset_otel()
    path = tmp_path / "dropped.jsonl"
    exporter = JsonlExporter(path)
    pipe = ExportPipeline(exporters=[exporter])
    sp = start_genai_span("openai", "gpt-4o")
    sp.dropped = True
    end_span(sp)
    pipe.add(sp)
    assert pipe.pending == 0
    pipe.flush()
    assert path.read_text(encoding="utf-8") == ""


# ═══════════════════════════════════════════════════════════════════════════
# Prometheus exporter rendering
# ═══════════════════════════════════════════════════════════════════════════


def test_prometheus_exporter_renders_counter_and_gauge(tmp_path):
    reset_otel()
    prom = PrometheusExporter()
    pipe = ExportPipeline(exporters=[prom])
    sp = start_genai_span("openai", "gpt-4o", operation="generate", input_tokens=10, output_tokens=20)
    end_span(sp)
    pipe.add(sp)
    pipe.flush()
    text = prom.render()
    assert '# TYPE llmops_genai_spans_total counter' in text
    assert 'llmops_genai_spans_total{gen_ai_system="openai",gen_ai_model="gpt-4o",gen_ai_operation="generate"} 1' in text
    assert 'llmops_genai_input_tokens_total{system="openai",model="gpt-4o",operation="generate"} 10' in text
    assert 'llmops_genai_output_tokens_total{system="openai",model="gpt-4o",operation="generate"} 20' in text
    assert 'llmops_genai_duration_ms{gen_ai_system="openai"' in text
    assert '# TYPE llmops_genai_duration_ms gauge' in text


# ═══════════════════════════════════════════════════════════════════════════
# Integration helper: trace_model_call -> span + cost -> TraceFacade
# ═══════════════════════════════════════════════════════════════════════════


def test_trace_model_call_records_span_and_cost_in_facade(tmp_path):
    reset_otel()
    facade = TraceFacade()
    path = tmp_path / "integ.jsonl"
    pipe = ExportPipeline(exporters=[JsonlExporter(path)])

    with trace_model_call(
        model="gpt-4o",
        system="openai",
        operation="generate",
        pipeline=pipe,
        facade=facade,
    ) as span:
        span.input_tokens = 100
        span.output_tokens = 50

    # cost computed from tokens
    assert span.cost_est > 0
    assert span.latency_ms is not None
    assert span.status == "ok"

    # span recorded in facade + aggregated by the evaluator
    stats = facade.stats()
    assert stats["count"] == 1
    assert stats["cost_total"] > 0
    assert stats["by_kind"] == {"generation": 1}

    # span exported through pipeline to the file
    pipe.flush()
    lines = [l for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) == 1
    assert json.loads(lines[0])["attributes"]["gen_ai.request.model"] == "gpt-4o"


def test_trace_model_call_sampler_drops_not_recorded(tmp_path):
    reset_otel()
    facade = TraceFacade()
    pipe = ExportPipeline(exporters=[JsonlExporter(tmp_path / "none.jsonl")])
    sampler = Sampler(sample_ratio=0.0)
    with trace_model_call(
        model="gpt-4o",
        system="openai",
        pipeline=pipe,
        facade=facade,
        sampler=sampler,
    ) as span:
        span.input_tokens = 10
        span.output_tokens = 10
    assert span.dropped is True
    assert facade.stats()["count"] == 0, "dropped spans must not be recorded"
    pipe.flush()
    assert (tmp_path / "none.jsonl").read_text(encoding="utf-8") == ""


def test_trace_model_call_decorator_form(tmp_path):
    reset_otel()
    facade = TraceFacade()

    @trace_model_call_decorator(model="claude-3", system="anthropic", operation="generate", facade=facade)
    def _llm(n: int):
        return n, 10, 5  # (result, input_tokens, output_tokens)

    result = _llm(7)
    assert result == 7
    stats = facade.stats()
    assert stats["count"] == 1
    assert stats["cost_total"] > 0
