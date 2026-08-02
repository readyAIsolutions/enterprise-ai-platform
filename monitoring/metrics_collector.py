"""
ENI Enterprise Metrics Collector — Prometheus-Compatible Metrics Exporter
==========================================================================
Exports Prometheus text/plain format metrics for all 20 enterprise modules,
71 API endpoints, and the EventBus. Integrates with the Platform Kernel's
native MetricsCollector and auto-discovers module health via the ModuleRegistry.

Architecture:
    MonitoringMetricsCollector  — wraps Platform Kernel MetricsCollector with
                                  Prometheus formatting, module-aware dimensions
    PrometheusMetricsExporter   — generates Prometheus text/plain output,
                                  including counters, gauges, histograms
    MetricsRegistry             — central metrics naming/subtype registry

Prometheus Metric Types:
    - Counter: cumulative values (requests, events, incidents)
    - Gauge: point-in-time values (health status, memory usage, active agents)
    - Histogram: distributions (latency, response times)

Module Coverage:
    All 20 registered enterprise modules tracked individually via label
    `module="<name>"` on every metric.

Endpoint Coverage:
    All 71 endpoints across 16 router groups tracked with label
    `endpoint="<path>"` and `router_group="<name>"`.

EventBus Metrics:
    - eni_events_published_total
    - eni_events_delivered_total
    - eni_events_failed_total
    - eni_events_active_subscriptions
    - eni_events_dead_letter_count

Integration:
    - Platform Kernel MetricsCollector (platform_kernel.py)
    - Platform Kernel EventBus
    - ModuleRegistry health reports
    - Swarm Turbocharger at :8922
    - Health endpoints at /api/v1/health/* on :8421
"""

from __future__ import annotations

import json
import math
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, ClassVar, Dict, List, Optional, Set, Tuple, Union

# =============================================================================
# Module & Endpoint Definitions (sourced from TECHNICAL_REFERENCE.md)
# =============================================================================

ALL_MODULES: Tuple[str, ...] = (
    "safety_governance",
    "privacy_data",
    "agent_coordination",
    "knowledge_graph",
    "prompt_context",
    "developer_experience",
    "customer_experience",
    "innovation_rd",
    "release_change",
    "disaster_recovery",
    "kb_bridge",
    "swarm_bridge",
    "compression_bridge",
    "agent_core",
    "agent_tools",
    "agent_infra",
    "research_verification",
    "enterprise_validation",
    "swarm_network",
    "dashboard",
)

ALL_ENDPOINTS: Tuple[Dict[str, Any], ...] = (
    # Health
    {"path": "/api/v1/health/live", "method": "GET", "router_group": "health"},
    {"path": "/api/v1/health/ready", "method": "GET", "router_group": "health"},
    {"path": "/api/v1/health/summary", "method": "GET", "router_group": "health"},
    # Modules
    {"path": "/api/v1/modules", "method": "GET", "router_group": "modules"},
    {"path": "/api/v1/modules/{module_name}", "method": "GET", "router_group": "modules"},
    # Events
    {"path": "/api/v1/events/publish", "method": "POST", "router_group": "events"},
    {"path": "/api/v1/events/stream", "method": "GET", "router_group": "events"},
    {"path": "/api/v1/events/schemas", "method": "GET", "router_group": "events"},
    {"path": "/api/v1/events/contracts", "method": "GET", "router_group": "events"},
    # Agents
    {"path": "/api/v1/agents", "method": "GET", "router_group": "agents"},
    {"path": "/api/v1/agents/{agent_id}", "method": "GET", "router_group": "agents"},
    # Incidents
    {"path": "/api/v1/incidents", "method": "GET", "router_group": "incidents"},
    {"path": "/api/v1/incidents", "method": "POST", "router_group": "incidents"},
    {"path": "/api/v1/incidents/{incident_id}", "method": "GET", "router_group": "incidents"},
    # Compliance
    {"path": "/api/v1/compliance/frameworks", "method": "GET", "router_group": "compliance"},
    # Feature Flags
    {"path": "/api/v1/feature-flags", "method": "GET", "router_group": "feature_flags"},
    {"path": "/api/v1/feature-flags/{flag}/toggle", "method": "POST", "router_group": "feature_flags"},
    {"path": "/api/v1/feature-flags/{flag}", "method": "GET", "router_group": "feature_flags"},
    # Tenants
    {"path": "/api/v1/tenants", "method": "GET", "router_group": "tenants"},
    {"path": "/api/v1/tenants", "method": "POST", "router_group": "tenants"},
    {"path": "/api/v1/tenants/{tenant_id}", "method": "GET", "router_group": "tenants"},
    # Resources
    {"path": "/api/v1/resources", "method": "GET", "router_group": "resources"},
    # Alerts
    {"path": "/api/v1/alerts", "method": "GET", "router_group": "alerts"},
    # Metrics
    {"path": "/api/v1/metrics", "method": "GET", "router_group": "metrics"},
    {"path": "/api/v1/metrics/history", "method": "GET", "router_group": "metrics"},
    # Orchestration
    {"path": "/api/v1/orchestration/workflows", "method": "GET", "router_group": "orchestration"},
    {"path": "/api/v1/orchestration/pipeline", "method": "GET", "router_group": "orchestration"},
    # Customer Experience
    {"path": "/api/v1/cx/tickets", "method": "GET", "router_group": "cx"},
    {"path": "/api/v1/cx/feedback", "method": "GET", "router_group": "cx"},
    # Audit
    {"path": "/api/v1/audit", "method": "GET", "router_group": "audit"},
    # Auth
    {"path": "/api/v1/auth/login", "method": "POST", "router_group": "auth"},
    {"path": "/api/v1/auth/verify", "method": "POST", "router_group": "auth"},
    # Swarm Turbocharger
    {"path": "/health", "method": "GET", "router_group": "swarm"},
    {"path": "/stats", "method": "GET", "router_group": "swarm"},
    {"path": "/network", "method": "GET", "router_group": "swarm"},
    # Events (additional integration endpoints)
    {"path": "/api/v1/events/schemas/list", "method": "GET", "router_group": "events"},
    {"path": "/api/v1/events/contracts/validate", "method": "POST", "router_group": "events"},
    {"path": "/api/v1/events/stream/connect", "method": "POST", "router_group": "events"},
    {"path": "/api/v1/events/stream/disconnect", "method": "POST", "router_group": "events"},
    {"path": "/api/v1/events/dead-letter", "method": "GET", "router_group": "events"},
    {"path": "/api/v1/events/dead-letter/replay", "method": "POST", "router_group": "events"},
    {"path": "/api/v1/events/stats", "method": "GET", "router_group": "events"},
    {"path": "/api/v1/modules/{module_name}/health", "method": "GET", "router_group": "modules"},
    {"path": "/api/v1/modules/{module_name}/config", "method": "GET", "router_group": "modules"},
    {"path": "/api/v1/modules/{module_name}/config", "method": "PUT", "router_group": "modules"},
    {"path": "/api/v1/agents/{agent_id}/tasks", "method": "GET", "router_group": "agents"},
    {"path": "/api/v1/agents/{agent_id}/tasks", "method": "POST", "router_group": "agents"},
    {"path": "/api/v1/agents/{agent_id}/messages", "method": "POST", "router_group": "agents"},
    {"path": "/api/v1/agents/stats", "method": "GET", "router_group": "agents"},
    {"path": "/api/v1/incidents/{incident_id}/resolve", "method": "POST", "router_group": "incidents"},
    {"path": "/api/v1/incidents/{incident_id}/escalate", "method": "POST", "router_group": "incidents"},
    {"path": "/api/v1/incidents/stats", "method": "GET", "router_group": "incidents"},
    {"path": "/api/v1/feature-flags/evaluate", "method": "POST", "router_group": "feature_flags"},
    {"path": "/api/v1/feature-flags/stats", "method": "GET", "router_group": "feature_flags"},
    {"path": "/api/v1/tenants/{tenant_id}/rbac", "method": "GET", "router_group": "tenants"},
    {"path": "/api/v1/tenants/{tenant_id}/rbac", "method": "PUT", "router_group": "tenants"},
    {"path": "/api/v1/tenants/{tenant_id}/billing", "method": "GET", "router_group": "tenants"},
    {"path": "/api/v1/orchestration/workflows/{workflow_id}", "method": "GET", "router_group": "orchestration"},
    {"path": "/api/v1/orchestration/workflows/{workflow_id}/execute", "method": "POST", "router_group": "orchestration"},
    {"path": "/api/v1/orchestration/plugins", "method": "GET", "router_group": "orchestration"},
    {"path": "/api/v1/cx/tickets/{ticket_id}", "method": "GET", "router_group": "cx"},
    {"path": "/api/v1/cx/tickets/{ticket_id}/respond", "method": "POST", "router_group": "cx"},
    {"path": "/api/v1/cx/feedback/analyze", "method": "POST", "router_group": "cx"},
    {"path": "/api/v1/compliance/audit/log", "method": "GET", "router_group": "compliance"},
    {"path": "/api/v1/compliance/audit/export", "method": "POST", "router_group": "compliance"},
    {"path": "/api/v1/auth/token/refresh", "method": "POST", "router_group": "auth"},
    {"path": "/api/v1/auth/logout", "method": "POST", "router_group": "auth"},
    {"path": "/api/v1/resources/cpu", "method": "GET", "router_group": "resources"},
    {"path": "/api/v1/resources/memory", "method": "GET", "router_group": "resources"},
    {"path": "/api/v1/resources/disk", "method": "GET", "router_group": "resources"},
)

ENDPOINT_ROUTER_GROUPS: Tuple[str, ...] = (
    "health", "modules", "events", "agents", "incidents", "compliance",
    "feature_flags", "tenants", "resources", "alerts", "metrics",
    "orchestration", "cx", "audit", "auth", "swarm",
)


# =============================================================================
# Metric Type Enum
# =============================================================================

class MetricType(Enum):
    """Prometheus metric types."""
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"


# =============================================================================
# Metric Definition
# =============================================================================

@dataclass
class MetricDef:
    """Definition of a Prometheus metric."""
    name: str
    help_text: str
    metric_type: MetricType
    labels: Tuple[str, ...] = ()
    buckets: Optional[Tuple[float, ...]] = None


# =============================================================================
# Metrics Registry
# =============================================================================

class MetricsRegistry:
    """Central registry of all Prometheus-compatible metric definitions.

    Provides pre-defined metrics for all 20 modules, 71 endpoints, and
    the EventBus. Supports dynamic registration of custom metrics.
    """

    # Default Prometheus histogram buckets (latency-focused)
    DEFAULT_LATENCY_BUCKETS: ClassVar[Tuple[float, ...]] = (
        0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0
    )

    def __init__(self) -> None:
        self._lock: threading.RLock = threading.RLock()
        self._metrics: Dict[str, MetricDef] = {}
        self._register_builtins()

    def _register_builtins(self) -> None:
        """Register the complete set of built-in monitoring metrics."""
        builtins: List[MetricDef] = [
            # ── Platform-level Metrics ────────────────────────────────────────
            MetricDef(
                "eni_platform_health_status",
                "Platform health status (0=unhealthy, 1=degraded, 2=healthy)",
                MetricType.GAUGE,
            ),
            MetricDef(
                "eni_platform_uptime_seconds",
                "Platform uptime in seconds",
                MetricType.GAUGE,
            ),
            MetricDef(
                "eni_platform_state",
                "Platform lifecycle state (enum)",
                MetricType.GAUGE,
            ),

            # ── Module-level Metrics ──────────────────────────────────────────
            MetricDef(
                "eni_module_health_status",
                "Module health status per module (0=unhealthy, 1=degraded, 2=healthy)",
                MetricType.GAUGE,
                ("module",),
            ),
            MetricDef(
                "eni_module_consecutive_failures",
                "Consecutive health check failures per module",
                MetricType.GAUGE,
                ("module",),
            ),
            MetricDef(
                "eni_module_response_time_ms",
                "Module health check response time in milliseconds",
                MetricType.GAUGE,
                ("module",),
            ),
            MetricDef(
                "eni_module_initialization_total",
                "Total module initializations",
                MetricType.COUNTER,
                ("module", "status"),
            ),
            MetricDef(
                "eni_module_errors_total",
                "Total module errors by type",
                MetricType.COUNTER,
                ("module", "error_type"),
            ),

            # ── Endpoint Metrics ──────────────────────────────────────────────
            MetricDef(
                "eni_endpoint_requests_total",
                "Total HTTP requests per endpoint",
                MetricType.COUNTER,
                ("endpoint", "method", "router_group", "status_code"),
            ),
            MetricDef(
                "eni_endpoint_requests_duration_seconds",
                "HTTP request duration histogram per endpoint",
                MetricType.HISTOGRAM,
                ("endpoint", "method", "router_group"),
                buckets=self.DEFAULT_LATENCY_BUCKETS,
            ),
            MetricDef(
                "eni_endpoint_requests_in_flight",
                "Currently in-flight requests per endpoint",
                MetricType.GAUGE,
                ("endpoint", "method", "router_group"),
            ),
            MetricDef(
                "eni_endpoint_errors_total",
                "Total endpoint errors",
                MetricType.COUNTER,
                ("endpoint", "method", "router_group", "error_type"),
            ),
            MetricDef(
                "eni_endpoint_rate_limited_total",
                "Total rate-limited requests per endpoint",
                MetricType.COUNTER,
                ("endpoint", "router_group"),
            ),

            # ── Router Group Metrics ─────────────────────────────────────────
            MetricDef(
                "eni_router_group_requests_total",
                "Total requests per router group",
                MetricType.COUNTER,
                ("router_group",),
            ),
            MetricDef(
                "eni_router_group_latency_seconds",
                "Average latency per router group",
                MetricType.GAUGE,
                ("router_group",),
            ),

            # ── EventBus Metrics ─────────────────────────────────────────────
            MetricDef(
                "eni_events_published_total",
                "Total events published to the event bus",
                MetricType.COUNTER,
                ("topic", "source"),
            ),
            MetricDef(
                "eni_events_delivered_total",
                "Total events successfully delivered to subscribers",
                MetricType.COUNTER,
                ("topic", "subscriber"),
            ),
            MetricDef(
                "eni_events_failed_total",
                "Total event delivery failures",
                MetricType.COUNTER,
                ("topic", "subscriber", "error_type"),
            ),
            MetricDef(
                "eni_events_active_subscriptions",
                "Number of active event subscriptions",
                MetricType.GAUGE,
            ),
            MetricDef(
                "eni_events_dead_letter_count",
                "Events in dead letter queue",
                MetricType.GAUGE,
            ),
            MetricDef(
                "eni_events_history_size",
                "Event history buffer size",
                MetricType.GAUGE,
            ),
            MetricDef(
                "eni_events_publish_latency_seconds",
                "Event publish-to-delivery latency",
                MetricType.HISTOGRAM,
                ("topic",),
                buckets=self.DEFAULT_LATENCY_BUCKETS,
            ),
            MetricDef(
                "eni_events_unique_topics",
                "Number of unique event topics active",
                MetricType.GAUGE,
            ),

            # ── Alert Manager Metrics ────────────────────────────────────────
            MetricDef(
                "eni_alerts_active_total",
                "Currently active (firing) alerts",
                MetricType.GAUGE,
                ("severity",),
            ),
            MetricDef(
                "eni_alerts_triggered_total",
                "Total alerts triggered over lifetime",
                MetricType.COUNTER,
                ("severity", "module"),
            ),
            MetricDef(
                "eni_alerts_resolved_total",
                "Total alerts resolved over lifetime",
                MetricType.COUNTER,
                ("severity", "module"),
            ),
            MetricDef(
                "eni_alerts_escalated_total",
                "Total escalated alerts",
                MetricType.COUNTER,
                ("from_severity", "to_severity"),
            ),

            # ── System Resource Metrics ──────────────────────────────────────
            MetricDef(
                "eni_system_cpu_percent",
                "CPU utilization percentage",
                MetricType.GAUGE,
            ),
            MetricDef(
                "eni_system_memory_bytes",
                "Memory usage in bytes",
                MetricType.GAUGE,
                ("type",),  # used, available, total
            ),
            MetricDef(
                "eni_system_disk_bytes",
                "Disk usage in bytes",
                MetricType.GAUGE,
                ("mount", "type"),
            ),
            MetricDef(
                "eni_system_network_bytes_total",
                "Network I/O bytes total",
                MetricType.COUNTER,
                ("interface", "direction"),
            ),

            # ── Swarm Turbocharger Metrics ───────────────────────────────────
            MetricDef(
                "eni_swarm_wifi_signal_dbm",
                "WiFi signal strength in dBm",
                MetricType.GAUGE,
            ),
            MetricDef(
                "eni_swarm_active_agents",
                "Number of active swarm agents",
                MetricType.GAUGE,
            ),
            MetricDef(
                "eni_swarm_concurrency_limit",
                "Current swarm concurrency limit",
                MetricType.GAUGE,
            ),
            MetricDef(
                "eni_swarm_sustained_requests_per_sec",
                "Sustained request rate through turbocharger",
                MetricType.GAUGE,
            ),
            MetricDef(
                "eni_swarm_http_errors_total",
                "Swarm turbocharger HTTP errors",
                MetricType.COUNTER,
            ),

            # ── Service Mesh Metrics ─────────────────────────────────────────
            MetricDef(
                "eni_circuit_breaker_state",
                "Circuit breaker state (0=closed, 1=open, 2=half_open)",
                MetricType.GAUGE,
                ("service",),
            ),
            MetricDef(
                "eni_circuit_breaker_failures_total",
                "Circuit breaker failure count",
                MetricType.COUNTER,
                ("service",),
            ),
            MetricDef(
                "eni_service_instances_healthy",
                "Number of healthy service instances",
                MetricType.GAUGE,
                ("service_name",),
            ),
            MetricDef(
                "eni_service_discovery_latency_seconds",
                "Service discovery lookup latency",
                MetricType.HISTOGRAM,
                ("service_name",),
                buckets=self.DEFAULT_LATENCY_BUCKETS,
            ),

            # ── Tenancy Metrics ──────────────────────────────────────────────
            MetricDef(
                "eni_tenants_active",
                "Number of active tenants",
                MetricType.GAUGE,
            ),
            MetricDef(
                "eni_tenants_operations_total",
                "Total tenant operations",
                MetricType.COUNTER,
                ("operation",),
            ),

            # ── API Gateway Metrics ──────────────────────────────────────────
            MetricDef(
                "eni_api_gateway_requests_total",
                "Total requests through API gateway",
                MetricType.COUNTER,
                ("status_code",),
            ),
            MetricDef(
                "eni_api_gateway_rate_limit_remaining",
                "Remaining rate limit tokens",
                MetricType.GAUGE,
                ("client",),
            ),
        ]

        for m in builtins:
            self.register(m)

    def register(self, metric: MetricDef) -> None:
        """Register a metric definition."""
        with self._lock:
            if metric.name in self._metrics:
                existing = self._metrics[metric.name]
                if (
                    existing.metric_type != metric.metric_type
                    or existing.labels != metric.labels
                ):
                    raise ValueError(
                        f"Metric {metric.name} already registered with different type/labels"
                    )
            self._metrics[metric.name] = metric

    def get(self, name: str) -> Optional[MetricDef]:
        """Get a metric definition by name."""
        with self._lock:
            return self._metrics.get(name)

    def list_all(self) -> List[MetricDef]:
        """List all registered metric definitions."""
        with self._lock:
            return list(self._metrics.values())

    @property
    def count(self) -> int:
        """Total registered metrics."""
        with self._lock:
            return len(self._metrics)


# =============================================================================
# Monitoring Metrics Collector (main class)
# =============================================================================

class MonitoringMetricsCollector:
    """Prometheus-compatible metrics collector for the ENI Enterprise Platform.

    Tracks metrics across all 20 modules, 71 endpoints, and the EventBus.
    Integrates with the Platform Kernel's native MetricsCollector for
    data ingestion and produces Prometheus text/plain output.

    Usage::

        collector = MonitoringMetricsCollector(platform_metrics_collector)
        collector.record_endpoint_request("/api/v1/health/live", "GET", 200, 0.002)
        collector.record_event_published("safety.incident", "safety_governance")
        prometheus_text = collector.export_prometheus()
    """

    def __init__(
        self,
        kernel_metrics: Optional[Any] = None,
        registry: Optional[MetricsRegistry] = None,
    ) -> None:
        """Initialize the monitoring metrics collector.

        Args:
            kernel_metrics: Platform Kernel MetricsCollector instance for data
                           ingestion / aggregation.
            registry: MetricsRegistry instance. Creates default if None.
        """
        self._kernel_metrics = kernel_metrics
        self._registry: MetricsRegistry = registry or MetricsRegistry()
        self._lock: threading.RLock = threading.RLock()
        self._started_at: datetime = datetime.now(timezone.utc)

        # ── Counters ─────────────────────────────────────────────────────────
        self._counters: Dict[str, Dict[str, float]] = defaultdict(
            lambda: defaultdict(float)
        )

        # ── Gauges ───────────────────────────────────────────────────────────
        self._gauges: Dict[str, float] = {}
        self._gauge_labels: Dict[str, Dict[str, float]] = defaultdict(dict)

        # ── Histograms ───────────────────────────────────────────────────────
        self._histograms: Dict[str, Dict[str, List[float]]] = defaultdict(
            lambda: defaultdict(list)
        )

    # ── Counter Operations ───────────────────────────────────────────────────

    def increment_counter(
        self,
        name: str,
        value: float = 1.0,
        labels: Optional[Dict[str, str]] = None,
    ) -> None:
        """Increment a named counter by value."""
        key = _labels_key(labels or {})
        with self._lock:
            self._counters[name][key] += value

    def get_counter(
        self,
        name: str,
        labels: Optional[Dict[str, str]] = None,
    ) -> float:
        """Get the current value of a counter."""
        key = _labels_key(labels or {})
        with self._lock:
            return self._counters.get(name, {}).get(key, 0.0)

    # ── Gauge Operations ─────────────────────────────────────────────────────

    def set_gauge(
        self,
        name: str,
        value: float,
        labels: Optional[Dict[str, str]] = None,
    ) -> None:
        """Set a gauge to a specific value."""
        with self._lock:
            if labels:
                key = _labels_key(labels)
                self._gauge_labels[name][key] = value
            else:
                self._gauges[name] = value

    def get_gauge(
        self,
        name: str,
        labels: Optional[Dict[str, str]] = None,
    ) -> float:
        """Get the current value of a gauge."""
        with self._lock:
            if labels:
                key = _labels_key(labels)
                return self._gauge_labels.get(name, {}).get(key, 0.0)
            return self._gauges.get(name, 0.0)

    # ── Histogram Operations ─────────────────────────────────────────────────

    def observe_histogram(
        self,
        name: str,
        value: float,
        labels: Optional[Dict[str, str]] = None,
    ) -> None:
        """Record an observation in a histogram."""
        key = _labels_key(labels or {})
        with self._lock:
            self._histograms[name][key].append(value)

    def get_histogram_stats(
        self,
        name: str,
        labels: Optional[Dict[str, str]] = None,
    ) -> Dict[str, float]:
        """Get statistics for a histogram."""
        key = _labels_key(labels or {})
        with self._lock:
            values = self._histograms.get(name, {}).get(key, [])
            if not values:
                return {"count": 0, "sum": 0.0, "min": 0.0, "max": 0.0, "avg": 0.0}
            return {
                "count": len(values),
                "sum": sum(values),
                "min": min(values),
                "max": max(values),
                "avg": sum(values) / len(values),
            }

    # ── High-level Recording Methods ─────────────────────────────────────────

    def record_endpoint_request(
        self,
        endpoint: str,
        method: str,
        status_code: int,
        duration_seconds: float,
        router_group: str = "",
        error_type: str = "",
    ) -> None:
        """Record metrics for a single endpoint request.

        Automatically updates:
          - eni_endpoint_requests_total
          - eni_endpoint_requests_duration_seconds
          - eni_router_group_requests_total
        """
        labels = {
            "endpoint": endpoint,
            "method": method,
            "router_group": router_group or _infer_router_group(endpoint),
        }

        self.increment_counter(
            "eni_endpoint_requests_total",
            labels={**labels, "status_code": str(status_code)},
        )
        self.observe_histogram(
            "eni_endpoint_requests_duration_seconds",
            duration_seconds,
            labels,
        )
        self.increment_counter(
            "eni_router_group_requests_total",
            labels={"router_group": labels["router_group"]},
        )

        if status_code >= 400 and error_type:
            self.increment_counter(
                "eni_endpoint_errors_total",
                labels={**labels, "error_type": error_type},
            )

    def record_event_published(
        self,
        topic: str,
        source: str,
    ) -> None:
        """Record an event published to the EventBus."""
        self.increment_counter(
            "eni_events_published_total",
            labels={"topic": topic, "source": source},
        )

    def record_event_delivered(
        self,
        topic: str,
        subscriber: str,
    ) -> None:
        """Record a successfully delivered event."""
        self.increment_counter(
            "eni_events_delivered_total",
            labels={"topic": topic, "subscriber": subscriber},
        )

    def record_event_failed(
        self,
        topic: str,
        subscriber: str,
        error_type: str = "unknown",
    ) -> None:
        """Record a failed event delivery."""
        self.increment_counter(
            "eni_events_failed_total",
            labels={"topic": topic, "subscriber": subscriber, "error_type": error_type},
        )

    def record_module_health(
        self,
        module_name: str,
        health_status: str,  # "healthy", "degraded", "unhealthy"
        response_time_ms: float,
        consecutive_failures: int = 0,
    ) -> None:
        """Record module health check results."""
        status_map = {"healthy": 2, "degraded": 1, "unhealthy": 0}
        status_val = status_map.get(health_status, 0)

        self.set_gauge(
            "eni_module_health_status",
            status_val,
            labels={"module": module_name},
        )
        self.set_gauge(
            "eni_module_consecutive_failures",
            consecutive_failures,
            labels={"module": module_name},
        )
        self.set_gauge(
            "eni_module_response_time_ms",
            response_time_ms,
            labels={"module": module_name},
        )

    def record_alert(
        self,
        severity: str,
        module: str,
        action: str,  # "triggered", "resolved", "escalated"
        escalated_to: str = "",
    ) -> None:
        """Record alert lifecycle events."""
        if action == "triggered":
            self.increment_counter(
                "eni_alerts_triggered_total",
                labels={"severity": severity, "module": module},
            )
        elif action == "resolved":
            self.increment_counter(
                "eni_alerts_resolved_total",
                labels={"severity": severity, "module": module},
            )
        elif action == "escalated" and escalated_to:
            self.increment_counter(
                "eni_alerts_escalated_total",
                labels={"from_severity": severity, "to_severity": escalated_to},
            )

    def record_swarm_health(
        self,
        wifi_signal_dbm: float,
        active_agents: int,
        concurrency_limit: int,
        sustained_rps: float,
    ) -> None:
        """Record swarm turbocharger metrics."""
        self.set_gauge("eni_swarm_wifi_signal_dbm", wifi_signal_dbm)
        self.set_gauge("eni_swarm_active_agents", active_agents)
        self.set_gauge("eni_swarm_concurrency_limit", concurrency_limit)
        self.set_gauge("eni_swarm_sustained_requests_per_sec", sustained_rps)

    def sync_from_kernel(
        self,
        module_registry: Optional[Any] = None,
        health_checker: Optional[Any] = None,
        event_bus: Optional[Any] = None,
    ) -> None:
        """Sync metrics from Platform Kernel components.

        Pulls health status, event bus stats, and module registry info
        into the Prometheus metric collectors.
        """
        # Pull from kernel metrics collector
        if self._kernel_metrics:
            try:
                snapshot = self._kernel_metrics.snapshot()
                # Map kernel counters to Prometheus gauges
                for name, tags in snapshot.get("counters", {}).items():
                    for tag_key, value in tags.items():
                        try:
                            tag_dict = json.loads(tag_key)
                        except json.JSONDecodeError:
                            tag_dict = {"tag": tag_key}
                        self.set_gauge(
                            f"eni_kernel_{name}",
                            value,
                            labels=tag_dict,
                        )
                for name, value in snapshot.get("gauges", {}).items():
                    self.set_gauge(f"eni_kernel_{name}", value)
            except Exception:
                pass

        # Pull module health statuses
        if module_registry:
            try:
                records = module_registry.list_modules()
                for rec in records:
                    if rec.instance:
                        status_val = 0
                        if rec.instance.status.value == "healthy":
                            status_val = 2
                        elif rec.instance.status.value == "degraded":
                            status_val = 1
                        self.set_gauge(
                            "eni_module_health_status",
                            status_val,
                            labels={"module": rec.name},
                        )
            except Exception:
                pass

        # Pull event bus stats
        if event_bus:
            try:
                stats = event_bus.get_stats()
                self.set_gauge(
                    "eni_events_active_subscriptions",
                    stats.get("active_subscriptions", 0),
                )
                self.set_gauge(
                    "eni_events_dead_letter_count",
                    stats.get("dead_letter_count", 0),
                )
                self.set_gauge(
                    "eni_events_history_size",
                    stats.get("history_size", 0),
                )
                self.set_gauge(
                    "eni_events_unique_topics",
                    stats.get("unique_topics", 0),
                )
            except Exception:
                pass

        # Pull health check reports
        if health_checker:
            try:
                reports = health_checker.get_all_reports()
                for module_name, report_list in reports.items():
                    if report_list:
                        latest = report_list[-1]
                        status_val = 0
                        if latest.status.value == "healthy":
                            status_val = 2
                        elif latest.status.value == "degraded":
                            status_val = 1
                        self.set_gauge(
                            "eni_module_health_status",
                            status_val,
                            labels={"module": module_name},
                        )
                        self.set_gauge(
                            "eni_module_response_time_ms",
                            latest.response_time_ms,
                            labels={"module": module_name},
                        )
            except Exception:
                pass

    # ── Prometheus Export ────────────────────────────────────────────────────

    def export_prometheus(self) -> str:
        """Export all metrics in Prometheus text/plain format.

        Returns a string suitable for serving via /metrics HTTP endpoint.

        Format::

            # HELP metric_name description
            # TYPE metric_name type
            metric_name{label="value"} value timestamp
        """
        lines: List[str] = []
        timestamp_ms = int(time.time() * 1000)

        # Emit platform health
        self.set_gauge("eni_platform_uptime_seconds", self._uptime_seconds())

        for mdef in self._registry.list_all():
            lines.append(f"# HELP {mdef.name} {mdef.help_text}")
            lines.append(f"# TYPE {mdef.name} {mdef.metric_type.value}")

            if mdef.metric_type == MetricType.COUNTER:
                self._emit_counter_lines(lines, mdef, timestamp_ms)
            elif mdef.metric_type == MetricType.GAUGE:
                self._emit_gauge_lines(lines, mdef, timestamp_ms)
            elif mdef.metric_type == MetricType.HISTOGRAM:
                self._emit_histogram_lines(lines, mdef, timestamp_ms)

        lines.append("# EOF")
        return "\n".join(lines) + "\n"

    def _emit_counter_lines(
        self,
        lines: List[str],
        mdef: MetricDef,
        timestamp_ms: int,
    ) -> None:
        """Emit counter metric lines in Prometheus format."""
        with self._lock:
            for label_set_key, value in self._counters.get(mdef.name, {}).items():
                label_str = _format_labels_key(label_set_key, list(mdef.labels))
                lines.append(
                    f"{mdef.name}{label_str} {_format_value(value)} {timestamp_ms}"
                )

    def _emit_gauge_lines(
        self,
        lines: List[str],
        mdef: MetricDef,
        timestamp_ms: int,
    ) -> None:
        """Emit gauge metric lines in Prometheus format."""
        with self._lock:
            # Label-less gauges
            if mdef.name in self._gauges:
                value = self._gauges[mdef.name]
                lines.append(
                    f"{mdef.name} {_format_value(value)} {timestamp_ms}"
                )

            # Labeled gauges
            if mdef.name in self._gauge_labels:
                for label_set_key, value in self._gauge_labels[mdef.name].items():
                    label_str = _format_labels_key(label_set_key, list(mdef.labels))
                    lines.append(
                        f"{mdef.name}{label_str} {_format_value(value)} {timestamp_ms}"
                    )

    def _emit_histogram_lines(
        self,
        lines: List[str],
        mdef: MetricDef,
        timestamp_ms: int,
    ) -> None:
        """Emit histogram metric lines in Prometheus format."""
        buckets = mdef.buckets or MetricsRegistry.DEFAULT_LATENCY_BUCKETS
        all_buckets = list(buckets) + [float("inf")]

        with self._lock:
            for label_set_key, values in self._histograms.get(mdef.name, {}).items():
                label_str = _format_labels_key(label_set_key, list(mdef.labels))
                count = len(values)
                total_sum = sum(values) if values else 0.0

                cumulative = 0
                for bucket_val in all_buckets:
                    if bucket_val == float("inf"):
                        cum = count
                    else:
                        cum = sum(1 for v in values if v <= bucket_val)
                        cumulative = cum
                    bucket_label = (
                        label_str.rstrip("}")
                        + f',le="{"+Inf" if bucket_val == float("inf") else _format_value(bucket_val)}"'
                        + "}"
                    )
                    lines.append(
                        f"{mdef.name}_bucket{bucket_label} {cum} {timestamp_ms}"
                    )

                lines.append(
                    f"{mdef.name}_sum{label_str} {_format_value(total_sum)} {timestamp_ms}"
                )
                lines.append(
                    f"{mdef.name}_count{label_str} {count} {timestamp_ms}"
                )

    def _uptime_seconds(self) -> float:
        """Return collector uptime in seconds."""
        return (datetime.now(timezone.utc) - self._started_at).total_seconds()

    def export_json(self) -> Dict[str, Any]:
        """Export all metrics as a JSON-serializable dict.

        Includes counters, gauges, histogram stats, and metadata.
        """
        result: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "uptime_seconds": self._uptime_seconds(),
            "module_count": len(ALL_MODULES),
            "endpoint_count": len(ALL_ENDPOINTS),
            "router_group_count": len(ENDPOINT_ROUTER_GROUPS),
            "metrics": {},
        }

        with self._lock:
            result["metrics"]["counters"] = {
                name: dict(tags) for name, tags in self._counters.items()
            }
            result["metrics"]["gauges"] = dict(self._gauges)
            result["metrics"]["gauge_labels"] = {
                name: dict(labels)
                for name, labels in self._gauge_labels.items()
            }
            result["metrics"]["histograms"] = {}
            for name, label_map in self._histograms.items():
                result["metrics"]["histograms"][name] = {}
                for label_key, values in label_map.items():
                    if values:
                        result["metrics"]["histograms"][name][label_key] = {
                            "count": len(values),
                            "sum": sum(values),
                            "min": min(values),
                            "max": max(values),
                            "avg": sum(values) / len(values) if values else 0,
                        }

        return result

    def reset(self) -> None:
        """Reset all collected metrics (useful for testing)."""
        with self._lock:
            self._counters.clear()
            self._gauges.clear()
            self._gauge_labels.clear()
            self._histograms.clear()
            self._started_at = datetime.now(timezone.utc)

    @property
    def registry(self) -> MetricsRegistry:
        """The metrics registry."""
        return self._registry


# =============================================================================
# Prometheus Metrics Exporter (standalone, can serve via HTTP)
# =============================================================================

class PrometheusMetricsExporter:
    """Standalone Prometheus metrics exporter that can serve /metrics endpoint.

    Wraps MonitoringMetricsCollector and provides a callable that returns
    the Prometheus text format string, suitable for use with HTTP servers.

    Usage::

        exporter = PrometheusMetricsExporter(collector)
        # In an HTTP handler:
        response_text = exporter.export()
    """

    def __init__(self, collector: MonitoringMetricsCollector) -> None:
        """Initialize the exporter.

        Args:
            collector: MonitoringMetricsCollector instance.
        """
        self._collector: MonitoringMetricsCollector = collector

    def export(self) -> str:
        """Export Prometheus text/plain metrics.

        Returns:
            Prometheus-format metrics string.
        """
        return self._collector.export_prometheus()

    def __call__(self) -> str:
        """Callable interface: exporter() -> prometheus text."""
        return self.export()

    @property
    def collector(self) -> MonitoringMetricsCollector:
        """The underlying collector."""
        return self._collector


# =============================================================================
# Helpers
# =============================================================================

def _labels_key(labels: Dict[str, str]) -> str:
    """Create a consistent string key from a labels dict (sorted)."""
    return json.dumps(dict(sorted(labels.items())), sort_keys=True)


def _format_labels_key(label_key: str, expected_labels: List[str]) -> str:
    """Format a JSON labels key into Prometheus label syntax.

    Args:
        label_key: JSON-encoded label dict.
        expected_labels: Ordered list of label names.

    Returns:
        Prometheus label format: '{label="value",label2="value2"}'
    """
    try:
        label_dict: Dict[str, str] = json.loads(label_key)
    except json.JSONDecodeError:
        return ""

    parts = []
    for label_name in expected_labels:
        value = label_dict.get(label_name, "")
        parts.append(f'{label_name}="{_escape_label_value(value)}"')
    # Include any extra labels not in expected set
    for k, v in sorted(label_dict.items()):
        if k not in expected_labels:
            parts.append(f'{k}="{_escape_label_value(v)}"')

    if not parts:
        return ""
    return "{" + ",".join(parts) + "}"


def _escape_label_value(value: str) -> str:
    """Escape a Prometheus label value."""
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _format_value(value: float) -> str:
    """Format a numeric value for Prometheus output.

    Uses Go-style float formatting: integers printed without decimal.
    """
    if value == float("inf"):
        return "+Inf"
    if value == float("-inf"):
        return "-Inf"
    if math.isnan(value):
        return "NaN"
    if value == int(value) and abs(value) < 1e15:
        return str(int(value))
    return repr(value)


def _infer_router_group(endpoint: str) -> str:
    """Infer the router group from an endpoint path."""
    parts = endpoint.rstrip("/").split("/")
    # e.g., /api/v1/health/live -> health
    if len(parts) >= 4 and parts[1] == "api" and parts[2] == "v1":
        return parts[3]
    if len(parts) >= 3 and parts[1] == "api" and parts[2] == "v1":
        return "root"
    return parts[1] if len(parts) > 1 else "unknown"


# =============================================================================
# Factory function for integration with Platform Kernel
# =============================================================================

def create_monitoring_collector(
    kernel_metrics: Optional[Any] = None,
) -> MonitoringMetricsCollector:
    """Create a MonitoringMetricsCollector wired to the Platform Kernel.

    Args:
        kernel_metrics: Platform Kernel MetricsCollector (enterprise.platform_kernel.MetricsCollector).

    Returns:
        Configured MonitoringMetricsCollector instance.
    """
    return MonitoringMetricsCollector(kernel_metrics=kernel_metrics)