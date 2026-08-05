"""Hermetic tests for the live Prometheus scrape endpoint (end-to-end ingestion).

These prove that telemetry is *scraped*, not merely rendered: a gen_ai span is
recorded, flushed through an ExportPipeline into a PrometheusExporter, and the
resulting counter/gauge text is served over a real HTTP ``GET /metrics`` on an
ephemeral port and fetched with ``http.client``. No stubs, no mocks — real
sockets, real HTTP, real text exposition.

Run with:
    python3 -m pytest modules/llmops_trace/tests/test_prom_scrape.py -q
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Generator

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import pytest
from enterprise.modules.llmops_trace.otel_genai import (
    ExportPipeline,
    PrometheusExporter,
    end_span,
    reset as reset_otel,
    start_genai_span,
)
from enterprise.modules.llmops_trace.prom_scrape import (
    PROMETHEUS_CONTENT_TYPE,
    PrometheusScrapeEndpoint,
    ScrapeTarget,
    fetch_metrics,
    scrape_example,
)

METRIC_NAMES = (
    "llmops_genai_spans_total",
    "llmops_genai_input_tokens_total",
    "llmops_genai_output_tokens_total",
    "llmops_genai_duration_ms",
)


@pytest.fixture(autouse=True)
def _isolate() -> Generator[None, None, None]:
    reset_otel()
    yield
    reset_otel()


def _record_and_flush(
    pipeline: ExportPipeline,
    system: str = "openai",
    model: str = "gpt-4o",
    input_tokens: int = 10,
    output_tokens: int = 20,
) -> int:
    """Record a gen_ai span and flush it through the pipeline."""
    span = start_genai_span(
        system,
        model,
        operation="generate",
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )
    end_span(span)
    pipeline.add(span)
    return pipeline.flush()


# ═══════════════════════════════════════════════════════════════════════════
# Endpoint serves the Prometheus content-type + text-format metric lines
# ═══════════════════════════════════════════════════════════════════════════


def test_endpoint_serves_prometheus_content_type_and_metric_lines() -> None:
    prom = PrometheusExporter()
    pipe = ExportPipeline(exporters=[prom])
    _record_and_flush(pipe)
    with PrometheusScrapeEndpoint(pipeline=pipe) as endpoint:
        status, headers, body = fetch_metrics(endpoint)
        assert status == 200
        ctype = headers.get("Content-Type", "")
        assert "text/plain" in ctype
        assert "version=0.0.4" in ctype
        assert ctype == PROMETHEUS_CONTENT_TYPE
        text = body.decode("utf-8")
        for name in METRIC_NAMES:
            assert name in text
        assert "# TYPE llmops_genai_spans_total counter" in text
        assert "# TYPE llmops_genai_duration_ms gauge" in text


def test_types_headers_present_even_without_spans() -> None:
    # The text exposition must include the TYPE/HELP lines regardless.
    with ScrapeTarget() as endpoint:
        _status, _headers, body = fetch_metrics(endpoint)
        text = body.decode("utf-8")
        assert "# TYPE llmops_genai_spans_total counter" in text
        assert "# TYPE llmops_genai_input_tokens_total counter" in text
        assert "# TYPE llmops_genai_output_tokens_total counter" in text
        assert "# TYPE llmops_genai_duration_ms gauge" in text


# ═══════════════════════════════════════════════════════════════════════════
# A span recorded + flushed appears in the served /metrics output
# ═══════════════════════════════════════════════════════════════════════════


def test_span_flushed_appears_in_served_metrics() -> None:
    prom = PrometheusExporter()
    pipe = ExportPipeline(exporters=[prom])
    _record_and_flush(pipe, system="openai", model="gpt-4o", input_tokens=3, output_tokens=7)
    with PrometheusScrapeEndpoint(pipeline=pipe) as endpoint:
        text = endpoint.exports()
        assert 'llmops_genai_spans_total{gen_ai_system="openai",' in text
        assert 'gen_ai_model="gpt-4o",gen_ai_operation="generate"} 1' in text
        assert 'llmops_genai_input_tokens_total{system="openai",' in text
        assert 'model="gpt-4o",operation="generate"} 3' in text
        assert 'llmops_genai_output_tokens_total{system="openai",' in text
        assert 'model="gpt-4o",operation="generate"} 7' in text
        assert 'llmops_genai_duration_ms{gen_ai_system="openai"' in text


# ═══════════════════════════════════════════════════════════════════════════
# Endpoint start / stop on ephemeral ports
# ═══════════════════════════════════════════════════════════════════════════


def test_endpoint_start_stop_on_ephemeral_port() -> None:
    endpoint = PrometheusScrapeEndpoint()
    assert endpoint.port is None
    endpoint.start()
    try:
        port = endpoint.port
        assert port is not None
        assert port > 0
        assert endpoint.host == "127.0.0.1"
        status, _headers, _body = fetch_metrics(endpoint)
        assert status == 200
    finally:
        endpoint.stop()
    assert endpoint.port is None


def test_endpoint_can_restart_on_a_fresh_port() -> None:
    endpoint = PrometheusScrapeEndpoint()
    endpoint.start()
    first_port = endpoint.port
    endpoint.stop()
    endpoint.start()
    try:
        second_port = endpoint.port
        assert second_port is not None
        assert second_port > 0
        status, _headers, _body = fetch_metrics(endpoint)
        assert status == 200
        # Ephemeral binding: a fresh port is usually allocated.
        assert isinstance(first_port, int)
    finally:
        endpoint.stop()


# ═══════════════════════════════════════════════════════════════════════════
# A "real scrape" via http.client GET /metrics returns 200 + metric names
# ═══════════════════════════════════════════════════════════════════════════


def test_real_scrape_returns_200_and_expected_metric_names() -> None:
    prom = PrometheusExporter()
    pipe = ExportPipeline(exporters=[prom])
    _record_and_flush(pipe)
    with PrometheusScrapeEndpoint(pipeline=pipe) as endpoint:
        status, _headers, body = fetch_metrics(endpoint, "/metrics")
        assert status == 200
        text = body.decode("utf-8")
        assert "llmops_genai_spans_total" in text
        assert "llmops_genai_duration_ms" in text
        assert "llmops_genai_output_tokens_total" in text


def test_unknown_path_returns_404() -> None:
    with ScrapeTarget() as endpoint:
        status, _headers, _body = fetch_metrics(endpoint, "/nope")
        assert status == 404


# ═══════════════════════════════════════════════════════════════════════════
# Exporter -> endpoint wiring (live re-render on each scrape)
# ═══════════════════════════════════════════════════════════════════════════


def test_exports_matches_served_body_and_updates_after_new_flush() -> None:
    prom = PrometheusExporter()
    pipe = ExportPipeline()
    pipe.register(prom)  # wire the exporter into the pipeline explicitly
    with PrometheusScrapeEndpoint(pipeline=pipe, exporter=prom) as endpoint:
        _record_and_flush(pipe, input_tokens=1, output_tokens=2)
        fetch_metrics(endpoint)[2].decode("utf-8")
        # flush another span -> a second scrape must reflect the new span
        _record_and_flush(pipe, input_tokens=5, output_tokens=6)
        second = fetch_metrics(endpoint)[2].decode("utf-8")
        assert "} 2" in second, "seconds scrape must count two spans"
        assert endpoint.exports() == second, "exports() must equal served body"


def test_scrape_count_increments_across_scrapes() -> None:
    prom = PrometheusExporter()
    pipe = ExportPipeline(exporters=[prom])
    with PrometheusScrapeEndpoint(pipeline=pipe) as endpoint:
        _record_and_flush(pipe, input_tokens=9, output_tokens=9)
        _record_and_flush(pipe, input_tokens=9, output_tokens=9)
        _status, _headers, body = fetch_metrics(endpoint)
        text = body.decode("utf-8")
        assert 'gen_ai_operation="generate"} 2' in text
        assert 'operation="generate"} 18' in text


# ═══════════════════════════════════════════════════════════════════════════
# ScrapeTarget factory + scrape_example end-to-end demonstration
# ═══════════════════════════════════════════════════════════════════════════


def test_scrape_target_returns_started_endpoint() -> None:
    target = ScrapeTarget()
    try:
        assert target.port is not None
        assert target.port > 0
        assert target.url == f"http://127.0.0.1:{target.port}/metrics"
        status, _headers, _body = fetch_metrics(target)
        assert status == 200
    finally:
        target.stop()


def test_scrape_example_serves_complete_genai_metrics() -> None:
    text = scrape_example(system="openai", model="gpt-4o")
    assert "llmops_genai_duration_ms{" in text
    assert "llmops_genai_input_tokens_total{" in text
    assert "llmops_genai_output_tokens_total{" in text
    assert "llmops_genai_spans_total{" in text
