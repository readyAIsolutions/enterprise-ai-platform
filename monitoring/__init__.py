"""
ENI Enterprise Monitoring Package — Complete Observability Stack
=================================================================
Provides Prometheus-compatible metrics export, threshold-based alerting,
real-time health dashboards, and centralized log aggregation for the
entire ENI Enterprise AI Platform (20 modules, 71 endpoints, EventBus).

Components:
    MetricsCollector    — Prometheus exporter for all platform metrics
    AlertManager        — Threshold-based alerting with severity levels + escalation
    HealthDashboard     — Real-time health dashboard data aggregator
    LogAggregator       — Centralized log collection with correlation tracing

Integration Points:
    - Platform Kernel (:8421)   — health checks, metrics, events, module registry
    - Swarm Turbocharger (:8922) — network health, WiFi signal, concurrency
    - API Gateway                — 71 endpoints, 16 router groups
    - EventBus                   — cross-module event flows

Version: 1.0.0
"""

__version__ = "1.0.0"

from enterprise.monitoring.metrics_collector import (
    MonitoringMetricsCollector,
    PrometheusMetricsExporter,
    MetricsRegistry,
    ALL_MODULES,
    ALL_ENDPOINTS,
    ENDPOINT_ROUTER_GROUPS,
)
from enterprise.monitoring.alert_manager import (
    AlertManager,
    AlertSeverity,
    AlertRule,
    Alert,
    EscalationPolicy,
    AlertState,
)
from enterprise.monitoring.health_dashboard import (
    HealthDashboard,
    DashboardSnapshot,
    ModuleHealthCard,
    EndpointHealthCard,
)
from enterprise.monitoring.log_aggregator import (
    LogAggregator,
    LogEntry,
    LogLevel,
    LogAggregationConfig,
)

__all__ = [
    # Metrics
    "MonitoringMetricsCollector",
    "PrometheusMetricsExporter",
    "MetricsRegistry",
    "ALL_MODULES",
    "ALL_ENDPOINTS",
    "ENDPOINT_ROUTER_GROUPS",
    # Alerts
    "AlertManager",
    "AlertSeverity",
    "AlertRule",
    "Alert",
    "EscalationPolicy",
    "AlertState",
    # Dashboard
    "HealthDashboard",
    "DashboardSnapshot",
    "ModuleHealthCard",
    "EndpointHealthCard",
    # Logging
    "LogAggregator",
    "LogEntry",
    "LogLevel",
    "LogAggregationConfig",
]