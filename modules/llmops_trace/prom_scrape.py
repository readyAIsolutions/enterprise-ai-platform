"""Real, scrape-able Prometheus text-format telemetry endpoint for ENI LLMOps Trace.

Stdlib-only (``http.server``, ``threading``, ``socket``, ``http.client``): zero
external dependencies, deterministic, and hermetic. It proves end-to-end
telemetry ingestion — the ``PrometheusExporter`` renders the OTel gen_ai
semantic-convention spans as Prometheus counter/gauge lines, and this module
serves that live text over a real HTTP ``GET /metrics`` endpoint that a real
Prometheus scraper (or any HTTP client) can poll.

Components:

* :class:`PrometheusScrapeEndpoint` — an ``http.server`` endpoint that returns
  the registered :class:`PrometheusExporter`'s ``render()`` output with the
  Prometheus content-type ``text/plain; version=0.0.4; charset=utf-8`` on
  ``GET /metrics``. It is fed by the live :class:`ExportPipeline` that owns the
  exporter: every span flushed through the pipeline lands in the metric
  registry and is re-rendered on each scrape.
* :class:`ScrapeTarget` — a small factory that constructs an endpoint, binds an
  ephemeral port and serves ``/metrics`` in a daemon thread, returning the live
  endpoint so a real scraper or test client can pull from it.
* :func:`scrape_example` — a full-path demonstration: record a gen_ai span via
  ``start_genai_span`` / ``end_span``, flush it through the pipeline to the
  PrometheusExporter, scrape the live endpoint, and assert the served text
  carries the ``llmops_genai_duration_ms`` gauge / token-counter lines.
"""

from __future__ import annotations

import http.client
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from enterprise.modules.llmops_trace.otel_genai import (
    ExportPipeline,
    PrometheusExporter,
    end_span,
    reset,
    start_genai_span,
)

# Standard Prometheus text exposition content-type (version 0.0.4).
PROMETHEUS_CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"

HOST = "127.0.0.1"


class PrometheusScrapeEndpoint:
    """Serve a live :class:`PrometheusExporter` over HTTP ``GET /metrics``.

    The endpoint is fed by the :class:`ExportPipeline` that has the
    PrometheusExporter registered: every span the pipeline flushes is
    aggregated into the exporter's metric registry, and every ``/metrics`` GET
    re-renders the current Prometheus text from that live registry.
    """

    def __init__(
        self,
        pipeline: ExportPipeline | None = None,
        exporter: PrometheusExporter | None = None,
    ) -> None:
        if exporter is None:
            if pipeline is None:
                exporter = PrometheusExporter()
            else:
                # Reuse an exporter already wired into the pipeline so spans
                # flushed before this endpoint started are still served.
                wired = [e for e in pipeline.exporters if isinstance(e, PrometheusExporter)]
                exporter = wired[0] if wired else PrometheusExporter()
        if pipeline is None:
            pipeline = ExportPipeline(exporters=[exporter])
        elif exporter not in pipeline.exporters:
            # Only wire the exporter in if the caller hasn't already attached it
            # (avoids double-registration double-counting the same exporter).
            pipeline.register(exporter)
        self.pipeline = pipeline
        self.exporter = exporter
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    # -- connection info -----------------------------------------------------

    @property
    def host(self) -> str:
        return HOST

    @property
    def port(self) -> int | None:
        """The bound ephemeral port, or None while the endpoint is stopped."""
        if self._httpd is not None:
            return int(self._httpd.server_address[1])
        return None

    @property
    def url(self) -> str:
        port = self.port
        if port is None:
            msg = "endpoint is not running"
            raise RuntimeError(msg)
        return f"http://{self.host}:{port}/metrics"

    # -- data ----------------------------------------------------------------

    def exports(self) -> str:
        """The live Prometheus text served by this endpoint (no HTTP involved)."""
        return self.exporter.render()

    # -- HTTP serving --------------------------------------------------------

    def _make_handler(self) -> type:
        exporter_ref = self.exporter

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 (stdlib naming)
                if self.path not in ("/metrics", "/metrics/"):
                    self.send_response(404)
                    self.end_headers()
                    return
                body = exporter_ref.render().encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", PROMETHEUS_CONTENT_TYPE)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args: Any) -> None:  # keep the endpoint quiet
                pass

        return Handler

    def start(self) -> PrometheusScrapeEndpoint:
        """Bind an ephemeral port and serve ``/metrics`` in a daemon thread."""
        self.stop()
        handler = self._make_handler()
        self._httpd = ThreadingHTTPServer((self.host, 0), handler)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        """Shut the server down and release the ephemeral port."""
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None
        self._thread = None

    # -- context-manager convenience ----------------------------------------

    def __enter__(self) -> PrometheusScrapeEndpoint:
        return self.start()

    def __exit__(self, *exc: Any) -> None:
        self.stop()


def ScrapeTarget(
    pipeline: ExportPipeline | None = None,
    exporter: PrometheusExporter | None = None,
) -> PrometheusScrapeEndpoint:
    """Start a :class:`PrometheusScrapeEndpoint` on an ephemeral port.

    This is the tiny seam a real Prometheus scraper aims at: it returns a
    running endpoint whose ``/metrics`` route serves everything flushed through
    the pipeline. Hand it to a scraper config (``scrape_configs``-style) or
    pull it directly with ``http.client``.
    """
    endpoint = PrometheusScrapeEndpoint(pipeline=pipeline, exporter=exporter)
    return endpoint.start()


def fetch_metrics(
    endpoint: PrometheusScrapeEndpoint,
    path: str = "/metrics",
) -> tuple[int, dict[str, str], bytes]:
    """Perform a real HTTP scrape with ``http.client``.

    Returns ``(status, headers, body)`` from ``GET <path>`` on the endpoint — a
    genuine over-the-wire scrape, not a stub.
    """
    conn = http.client.HTTPConnection(endpoint.host, endpoint.port, timeout=5)
    try:
        conn.request("GET", path)
        resp = conn.getresponse()
        body = resp.read()
        return resp.status, dict(resp.getheaders()), body
    finally:
        conn.close()


def scrape_example(
    system: str = "openai",
    model: str = "gpt-4o",
) -> str:
    """Record a gen_ai span, flush it through the pipeline, serve & verify it.

    Demonstrates the full telemetry-injection path: a span recorded via
    ``start_genai_span`` / ``end_span`` is flushed through an
    :class:`ExportPipeline` to a :class:`PrometheusExporter`, so a real HTTP
    scrape of the live endpoint returns the gen_ai metrics. Returns the served
    text and asserts the ``llmops_genai_duration_ms`` gauge and the input /
    output token counter lines are present.
    """
    reset()
    endpoint = ScrapeTarget()
    try:
        span = start_genai_span(
            system,
            model,
            operation="generate",
            input_tokens=11,
            output_tokens=22,
        )
        end_span(span)
        endpoint.pipeline.add(span)
        endpoint.pipeline.flush()

        status, _headers, body = fetch_metrics(endpoint)
        text = body.decode("utf-8")

        assert status == 200, f"expected HTTP 200, got {status}"
        assert "llmops_genai_duration_ms{" in text, "duration gauge not served"
        assert "llmops_genai_input_tokens_total{" in text, "input counter not served"
        assert "llmops_genai_output_tokens_total{" in text, "output counter not served"
        return text
    finally:
        endpoint.stop()
        reset()
