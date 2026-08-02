# ENI Enterprise Monitoring Stack

Complete observability infrastructure for the ENI Enterprise AI Platform — 20 modules, 71 API endpoints, EventBus, Service Mesh.

## Components

| Component | File | Purpose |
|-----------|------|---------|
| Metrics Collector | `metrics_collector.py` | Prometheus-compatible metrics exporter |
| Alert Manager | `alert_manager.py` | Threshold-based alerting with escalation |
| Health Dashboard | `health_dashboard.py` | Real-time health data aggregation |
| Log Aggregator | `log_aggregator.py` | Centralized structured log collection |

## Quick Start

```python
from enterprise.monitoring import (
    MonitoringMetricsCollector,
    AlertManager,
    HealthDashboard,
    LogAggregator,
    LogAggregationConfig,
)

# 1. Metrics Collection (Prometheus-compatible)
metrics = MonitoringMetricsCollector()
metrics.record_endpoint_request("/api/v1/health/live", "GET", 200, 0.002)
metrics.sync_from_kernel(
    module_registry=platform.module_registry,
    health_checker=platform.health_checker,
    event_bus=platform.event_bus,
)
prometheus_text = metrics.export_prometheus()
# Serve at GET /metrics with Content-Type: text/plain

# 2. Alert Manager (threshold-based with escalation)
alerts = AlertManager(event_bus=platform.event_bus)
alerts.evaluate_all()
active = alerts.get_active_alerts()
summary = alerts.get_summary()

# 3. Health Dashboard (real-time snapshots)
dashboard = HealthDashboard(
    platform=platform,
    alert_manager=alerts,
    metrics_collector=metrics,
)
snapshot = dashboard.generate_snapshot()
json_data = snapshot.to_dict()

# 4. Log Aggregator (centralized logging)
logs = LogAggregator(config=LogAggregationConfig(
    outputs=[
        {"type": "console", "format": "text"},
        {"type": "json_file", "path": "logs/platform.jsonl"},
    ]
))
logs.start()
logs.ingest_raw(LogLevel.ERROR, "safety_governance", "Guardrail failed")
```

## Integration Points

- **Platform Kernel** (:8421) — health checks, metrics, module registry
- **Swarm Turbocharger** (:8922) — WiFi signal, agent concurrency, throughput
- **API Gateway** — 71 endpoints across 16 router groups
- **EventBus** — cross-module event flow metrics

## Metrics Exported (Prometheus)

| Metric | Type | Labels |
|--------|------|--------|
| `eni_platform_health_status` | Gauge | — |
| `eni_module_health_status` | Gauge | module |
| `eni_endpoint_requests_total` | Counter | endpoint, method, router_group, status_code |
| `eni_endpoint_requests_duration_seconds` | Histogram | endpoint, method, router_group |
| `eni_events_published_total` | Counter | topic, source |
| `eni_events_delivered_total` | Counter | topic, subscriber |
| `eni_events_failed_total` | Counter | topic, subscriber, error_type |
| `eni_alerts_active_total` | Gauge | severity |
| `eni_swarm_wifi_signal_dbm` | Gauge | — |
| `eni_circuit_breaker_state` | Gauge | service |

## Alert Rules (Built-in)

18 pre-configured rules covering:
- Module health (degraded / unhealthy / consecutive failures)
- Endpoint errors and latency
- Event bus failure rate and dead letter queue
- Circuit breaker open detection
- CPU / memory / disk resource thresholds
- WiFi signal degradation (swarm turbocharger)
- Swarm agent exhaustion
- Alert storm detection

## Dashboard Sections

1. Platform Overview — overall status, uptime, lifecycle state
2. Module Grid — 20 modules with health status, response time, failures
3. Endpoint Health — 71 endpoints grouped by 16 router groups
4. Event Bus — published/delivered/failed events, subscriptions, DLQ
5. Active Alerts — firing alerts by severity, escalation status
6. Service Mesh — circuit breaker states, healthy instances
7. Resources — CPU, memory, disk, network
8. Swarm Turbocharger — WiFi signal, active agents, concurrency

## Running Tests

```bash
cd /home/hunter/Desktop/Eni\ Builder
python3 -m pytest enterprise/monitoring/tests/ -v -p no:anyio
```

## Architecture

```
Platform Kernel (platform_kernel.py)
    ├── EventBus ────────────→ AlertManager (alert events)
    ├── HealthChecker ───────→ HealthDashboard (module health)
    ├── MetricsCollector ────→ MonitoringMetricsCollector (data ingestion)
    └── LoggingBridge ───────→ LogAggregator (log routing)

API Gateway (:8421)
    ├── /api/v1/health/* ───→ HealthDashboard (health endpoint data)
    ├── /api/v1/metrics ────→ PrometheusMetricsExporter (Prometheus text)
    └── /api/v1/alerts ─────→ AlertManager (alert queries)

Swarm Turbocharger (:8922)
    ├── /health ─────────────→ HealthDashboard (swarm health)
    └── /stats ──────────────→ MonitoringMetricsCollector (throughput)
```

## Version

1.0.0 — August 2026