"""
ENI Enterprise Health Dashboard — Real-Time Health Aggregator
===============================================================
Provides real-time aggregation and visualization-ready data for the
platform health dashboard. Collects module health, endpoint status,
event bus statistics, alert summaries, resource utilization, and
swarm turbocharger metrics into a unified snapshot.

Architecture:
    DashboardSnapshot   — Complete point-in-time platform health picture
    ModuleHealthCard    — Per-module health summary
    EndpointHealthCard  — Per-endpoint or per-router-group health summary
    HealthDashboard     — Aggregator: collects from all sources, produces snapshots

Integration:
    - Platform Kernel health checks at /api/v1/health/* on :8421
    - Swarm Turbocharger at :8922 (/health, /stats, /network)
    - ModuleRegistry for module-level health
    - EventBus for event statistics
    - AlertManager for alert summaries
    - MonitoringMetricsCollector for metrics data

Dashboard Sections (9):
    1. Platform Overview — overall status, uptime, lifecycle state
    2. Module Grid — 20 modules with health status, response time, failures
    3. Endpoint Health — 71 endpoints grouped by 16 router groups
    4. Event Bus — published/delivered/failed events, subscriptions, DLQ
    5. Active Alerts — firing alerts by severity, escalation status
    6. Service Mesh — circuit breaker states, healthy instances
    7. Resources — CPU, memory, disk, network
    8. Swarm Turbocharger — WiFi signal, active agents, concurrency
    9. Recent Incidents — incident timeline
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from enterprise.monitoring.metrics_collector import (
    ALL_MODULES,
    ALL_ENDPOINTS,
    ENDPOINT_ROUTER_GROUPS,
)


# =============================================================================
# Enums
# =============================================================================


class HealthColor(Enum):
    """Dashboard health indicator colors."""
    GREEN = "green"        # healthy
    YELLOW = "yellow"      # degraded
    RED = "red"            # unhealthy
    GRAY = "gray"          # unknown / offline
    BLUE = "blue"          # informational


class DashboardStatus(Enum):
    """Overall dashboard status."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


# =============================================================================
# Health Cards
# =============================================================================


@dataclass
class ModuleHealthCard:
    """Health summary for a single module.

    Attributes:
        module_name: Module identifier.
        status: Health status string ("healthy", "degraded", "unhealthy", "unknown").
        color: Dashboard color indicator.
        response_time_ms: Last health check response time.
        consecutive_failures: Consecutive failed health checks.
        uptime_pct: Uptime percentage (0-100).
        version: Module version.
        last_check: UTC timestamp of last health check.
        details: Additional module-specific details.
    """

    module_name: str
    status: str = "unknown"
    color: HealthColor = HealthColor.GRAY
    response_time_ms: float = 0.0
    consecutive_failures: int = 0
    uptime_pct: float = 0.0
    version: str = "0.0.0"
    last_check: Optional[datetime] = None
    details: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_module(
        cls,
        module_name: str,
        status: str = "unknown",
        response_time_ms: float = 0.0,
        consecutive_failures: int = 0,
        version: str = "0.0.0",
        details: Optional[Dict[str, Any]] = None,
    ) -> "ModuleHealthCard":
        """Create a ModuleHealthCard from raw module data."""
        color_map = {
            "healthy": HealthColor.GREEN,
            "degraded": HealthColor.YELLOW,
            "unhealthy": HealthColor.RED,
            "unknown": HealthColor.GRAY,
        }
        return cls(
            module_name=module_name,
            status=status,
            color=color_map.get(status, HealthColor.GRAY),
            response_time_ms=response_time_ms,
            consecutive_failures=consecutive_failures,
            version=version,
            last_check=datetime.now(timezone.utc),
            details=details or {},
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict."""
        return {
            "module_name": self.module_name,
            "status": self.status,
            "color": self.color.value,
            "response_time_ms": self.response_time_ms,
            "consecutive_failures": self.consecutive_failures,
            "uptime_pct": self.uptime_pct,
            "version": self.version,
            "last_check": self.last_check.isoformat() if self.last_check else None,
            "details": self.details,
        }


@dataclass
class EndpointHealthCard:
    """Health summary for an API endpoint or router group.

    Attributes:
        path: Endpoint path or router group name.
        method: HTTP method (for endpoints) or "AGGREGATE" (for groups).
        router_group: Router group name.
        requests_total: Total request count.
        error_rate: Error rate (0.0 - 1.0).
        avg_latency_ms: Average latency in milliseconds.
        p95_latency_ms: 95th percentile latency.
        p99_latency_ms: 99th percentile latency.
        in_flight: Currently in-flight requests.
        status: Health status for this endpoint/group.
        color: Dashboard color indicator.
    """

    path: str
    method: str = "GET"
    router_group: str = ""
    requests_total: int = 0
    error_rate: float = 0.0
    avg_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0
    in_flight: int = 0
    status: str = "unknown"
    color: HealthColor = HealthColor.GRAY

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict."""
        return {
            "path": self.path,
            "method": self.method,
            "router_group": self.router_group,
            "requests_total": self.requests_total,
            "error_rate": self.error_rate,
            "avg_latency_ms": self.avg_latency_ms,
            "p95_latency_ms": self.p95_latency_ms,
            "p99_latency_ms": self.p99_latency_ms,
            "in_flight": self.in_flight,
            "status": self.status,
            "color": self.color.value,
        }


# =============================================================================
# Dashboard Snapshot
# =============================================================================


@dataclass
class DashboardSnapshot:
    """Complete point-in-time platform health snapshot.

    Contains all sections needed to render the ENI Enterprise health dashboard.
    """

    # Metadata
    snapshot_id: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    generation_time_ms: float = 0.0

    # Platform Overview
    platform_status: DashboardStatus = DashboardStatus.UNKNOWN
    platform_state: str = "unknown"
    uptime_seconds: float = 0.0
    platform_version: str = "0.0.0"

    # Module Grid
    modules: List[ModuleHealthCard] = field(default_factory=list)
    module_count: int = 0
    modules_healthy: int = 0
    modules_degraded: int = 0
    modules_unhealthy: int = 0
    modules_unknown: int = 0

    # Endpoint Health
    endpoints: List[EndpointHealthCard] = field(default_factory=list)
    endpoint_count: int = 0
    router_groups: Dict[str, EndpointHealthCard] = field(default_factory=dict)

    # Event Bus
    event_bus_stats: Dict[str, Any] = field(default_factory=dict)

    # Active Alerts
    alerts_active: int = 0
    alerts_by_severity: Dict[str, int] = field(default_factory=dict)
    alerts_recent: List[Dict[str, Any]] = field(default_factory=list)

    # Service Mesh
    circuit_breakers: Dict[str, str] = field(default_factory=dict)  # service -> state
    service_instances: Dict[str, int] = field(default_factory=dict)  # service -> count

    # Resources
    cpu_percent: float = 0.0
    memory_used_bytes: float = 0.0
    memory_total_bytes: float = 0.0
    disk_used_bytes: float = 0.0
    disk_total_bytes: float = 0.0
    network_rx_bytes: float = 0.0
    network_tx_bytes: float = 0.0

    # Swarm Turbocharger
    wifi_signal_dbm: float = 0.0
    swarm_active_agents: int = 0
    swarm_concurrency_limit: int = 0
    swarm_sustained_rps: float = 0.0
    swarm_status: str = "unknown"
    swarm_color: HealthColor = HealthColor.GRAY

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a JSON-compatible dict."""
        return {
            "snapshot_id": self.snapshot_id,
            "timestamp": self.timestamp.isoformat(),
            "generation_time_ms": self.generation_time_ms,
            "platform": {
                "status": self.platform_status.value,
                "state": self.platform_state,
                "uptime_seconds": self.uptime_seconds,
                "version": self.platform_version,
            },
            "modules": {
                "count": self.module_count,
                "healthy": self.modules_healthy,
                "degraded": self.modules_degraded,
                "unhealthy": self.modules_unhealthy,
                "unknown": self.modules_unknown,
                "list": [m.to_dict() for m in self.modules],
            },
            "endpoints": {
                "count": self.endpoint_count,
                "router_groups": {
                    k: v.to_dict() for k, v in self.router_groups.items()
                },
                "list": [e.to_dict() for e in self.endpoints[:20]],  # Top 20
            },
            "event_bus": self.event_bus_stats,
            "alerts": {
                "active": self.alerts_active,
                "by_severity": self.alerts_by_severity,
                "recent": self.alerts_recent,
            },
            "service_mesh": {
                "circuit_breakers": self.circuit_breakers,
                "service_instances": self.service_instances,
            },
            "resources": {
                "cpu_percent": self.cpu_percent,
                "memory_used_bytes": self.memory_used_bytes,
                "memory_total_bytes": self.memory_total_bytes,
                "memory_used_pct": (
                    (self.memory_used_bytes / self.memory_total_bytes * 100)
                    if self.memory_total_bytes > 0
                    else 0.0
                ),
                "disk_used_bytes": self.disk_used_bytes,
                "disk_total_bytes": self.disk_total_bytes,
                "network_rx_bytes": self.network_rx_bytes,
                "network_tx_bytes": self.network_tx_bytes,
            },
            "swarm": {
                "wifi_signal_dbm": self.wifi_signal_dbm,
                "active_agents": self.swarm_active_agents,
                "concurrency_limit": self.swarm_concurrency_limit,
                "sustained_rps": self.swarm_sustained_rps,
                "status": self.swarm_status,
                "color": self.swarm_color.value,
            },
        }


# =============================================================================
# Health Dashboard Aggregator
# =============================================================================


class HealthDashboard:
    """Real-time health dashboard data aggregator.

    Collects data from all platform sources and produces complete
    DashboardSnapshot instances for dashboard rendering or API delivery.

    Usage::

        dashboard = HealthDashboard(
            platform=platform,
            alert_manager=alerts,
            metrics_collector=metrics,
        )
        snapshot = dashboard.generate_snapshot()
        json_data = snapshot.to_dict()
    """

    def __init__(
        self,
        platform: Optional[Any] = None,
        alert_manager: Optional[Any] = None,
        metrics_collector: Optional[Any] = None,
        module_registry: Optional[Any] = None,
        health_checker: Optional[Any] = None,
        event_bus: Optional[Any] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Initialize the HealthDashboard.

        Args:
            platform: PlatformOS instance for platform-level data.
            alert_manager: AlertManager instance for alert summaries.
            metrics_collector: MonitoringMetricsCollector for metrics.
            module_registry: ModuleRegistry for module data.
            health_checker: HealthChecker for health reports.
            event_bus: EventBus for event statistics.
            config: Dashboard configuration.
        """
        self._platform = platform
        self._alert_manager = alert_manager
        self._metrics = metrics_collector
        self._module_registry = module_registry
        self._health_checker = health_checker
        self._event_bus = event_bus
        self._config: Dict[str, Any] = config or {}
        self._lock: threading.RLock = threading.RLock()
        self._snapshot_history: List[DashboardSnapshot] = []
        self._history_limit: int = self._config.get("snapshot_history_limit", 1000)
        self._generation_count: int = 0

    # ── Snapshot Generation ──────────────────────────────────────────────────

    def generate_snapshot(self) -> DashboardSnapshot:
        """Generate a complete dashboard snapshot from all data sources.

        Returns:
            A populated DashboardSnapshot.
        """
        start = time.perf_counter()

        snapshot = DashboardSnapshot()
        snapshot.snapshot_id = self._next_snapshot_id()

        # 1. Platform Overview
        self._collect_platform_overview(snapshot)

        # 2. Module Grid
        self._collect_module_grid(snapshot)

        # 3. Endpoint Health
        self._collect_endpoint_health(snapshot)

        # 4. Event Bus Stats
        self._collect_event_bus_stats(snapshot)

        # 5. Active Alerts
        self._collect_alert_summary(snapshot)

        # 6. Service Mesh
        self._collect_service_mesh(snapshot)

        # 7. Resources
        self._collect_resources(snapshot)

        # 8. Swarm Turbocharger
        self._collect_swarm_health(snapshot)

        elapsed = (time.perf_counter() - start) * 1000.0
        snapshot.generation_time_ms = round(elapsed, 2)

        # Store in history
        with self._lock:
            self._snapshot_history.append(snapshot)
            if len(self._snapshot_history) > self._history_limit:
                self._snapshot_history = self._snapshot_history[-self._history_limit :]
            self._generation_count += 1

        return snapshot

    def _next_snapshot_id(self) -> str:
        """Generate the next snapshot ID."""
        import uuid
        return f"snap-{uuid.uuid4().hex[:12]}"

    # ── Section Collectors ───────────────────────────────────────────────────

    def _collect_platform_overview(self, snapshot: DashboardSnapshot) -> None:
        """Collect platform-level overview data."""
        if self._platform:
            try:
                state_val = getattr(self._platform, 'state', None)
                if state_val:
                    snapshot.platform_state = state_val.value if hasattr(state_val, 'value') else str(state_val)

                uptime = getattr(self._platform, 'uptime_seconds', None)
                if uptime is not None:
                    snapshot.uptime_seconds = uptime

                config = getattr(self._platform, 'config', {})
                snapshot.platform_version = config.get('platform', {}).get('version', '1.0.0')

                # Determine overall status from state
                state_str = snapshot.platform_state
                if state_str == "running":
                    snapshot.platform_status = DashboardStatus.HEALTHY
                elif state_str == "degraded":
                    snapshot.platform_status = DashboardStatus.DEGRADED
                elif state_str in ("stopped", "crashed"):
                    snapshot.platform_status = DashboardStatus.UNHEALTHY
            except Exception:
                snapshot.platform_state = "unknown"
                snapshot.platform_status = DashboardStatus.UNKNOWN

    def _collect_module_grid(self, snapshot: DashboardSnapshot) -> None:
        """Collect health data for all 20 modules."""
        modules: List[ModuleHealthCard] = []

        # Try to get data from health_checker reports
        reports_map: Dict[str, Any] = {}
        if self._health_checker:
            try:
                reports_map = self._health_checker.get_all_reports()
            except Exception:
                pass

        # Try to get data from module_registry
        records_map: Dict[str, Any] = {}
        if self._module_registry:
            try:
                for rec in self._module_registry.list_modules():
                    records_map[rec.name] = rec
            except Exception:
                pass

        for module_name in ALL_MODULES:
            status = "unknown"
            response_time = 0.0
            failures = 0
            version = "0.0.0"

            # From health reports
            reports = reports_map.get(module_name, [])
            if reports:
                latest = reports[-1]
                status = latest.status.value if hasattr(latest.status, 'value') else str(latest.status)
                response_time = getattr(latest, 'response_time_ms', 0.0)
                failures = getattr(latest, 'consecutive_failures', 0)

            # From module registry
            record = records_map.get(module_name)
            if record:
                version = getattr(record, 'version', '0.0.0')
                if record.instance and status == "unknown":
                    inst_status = getattr(record.instance, 'status', None)
                    if inst_status:
                        status = inst_status.value if hasattr(inst_status, 'value') else str(inst_status)

            # From metrics collector
            if self._metrics:
                try:
                    gauge_val = self._metrics.get_gauge(
                        "eni_module_health_status",
                        {"module": module_name},
                    )
                    if gauge_val == 2:
                        status = "healthy"
                    elif gauge_val == 1:
                        status = "degraded"
                    elif gauge_val == 0:
                        status = "unhealthy"

                    failures_gauge = self._metrics.get_gauge(
                        "eni_module_consecutive_failures",
                        {"module": module_name},
                    )
                    if failures_gauge > 0:
                        failures = int(failures_gauge)
                except Exception:
                    pass

            card = ModuleHealthCard.from_module(
                module_name=module_name,
                status=status,
                response_time_ms=response_time,
                consecutive_failures=failures,
                version=version,
            )
            modules.append(card)

        snapshot.modules = modules
        snapshot.module_count = len(modules)
        snapshot.modules_healthy = sum(1 for m in modules if m.status == "healthy")
        snapshot.modules_degraded = sum(1 for m in modules if m.status == "degraded")
        snapshot.modules_unhealthy = sum(1 for m in modules if m.status == "unhealthy")
        snapshot.modules_unknown = sum(1 for m in modules if m.status == "unknown")

    def _collect_endpoint_health(self, snapshot: DashboardSnapshot) -> None:
        """Collect health data for endpoints and router groups."""
        endpoints: List[EndpointHealthCard] = []
        router_group_cards: Dict[str, EndpointHealthCard] = {}

        # Create cards for each endpoint
        for ep in ALL_ENDPOINTS:
            path = ep["path"]
            method = ep.get("method", "GET")
            router_group = ep.get("router_group", "")

            # Read metrics from collector
            requests_total = 0
            avg_latency = 0.0
            error_count = 0

            if self._metrics:
                try:
                    requests_total = int(
                        self._metrics.get_counter(
                            "eni_endpoint_requests_total",
                            {
                                "endpoint": path,
                                "method": method,
                                "router_group": router_group,
                                "status_code": "200",
                            },
                        )
                    )
                    stats = self._metrics.get_histogram_stats(
                        "eni_endpoint_requests_duration_seconds",
                        {
                            "endpoint": path,
                            "method": method,
                            "router_group": router_group,
                        },
                    )
                    avg_latency = stats.get("avg", 0.0) * 1000.0  # Convert to ms
                except Exception:
                    pass

            # Determine status
            if avg_latency > 5000:  # >5s latency
                status = "degraded"
                color = HealthColor.YELLOW
            elif avg_latency > 10000:  # >10s
                status = "unhealthy"
                color = HealthColor.RED
            else:
                status = "healthy"
                color = HealthColor.GREEN

            card = EndpointHealthCard(
                path=path,
                method=method,
                router_group=router_group,
                requests_total=requests_total,
                avg_latency_ms=avg_latency,
                status=status,
                color=color,
            )
            endpoints.append(card)

            # Aggregate into router group
            if router_group not in router_group_cards:
                router_group_cards[router_group] = EndpointHealthCard(
                    path=router_group,
                    method="AGGREGATE",
                    router_group=router_group,
                    status="healthy",
                    color=HealthColor.GREEN,
                )
            rg_card = router_group_cards[router_group]
            rg_card.requests_total += requests_total
            if avg_latency > rg_card.avg_latency_ms:
                rg_card.avg_latency_ms = avg_latency

        snapshot.endpoints = endpoints
        snapshot.endpoint_count = len(endpoints)
        snapshot.router_groups = router_group_cards

    def _collect_event_bus_stats(self, snapshot: DashboardSnapshot) -> None:
        """Collect EventBus statistics."""
        if self._event_bus:
            try:
                stats = self._event_bus.get_stats()
                snapshot.event_bus_stats = stats
            except Exception:
                snapshot.event_bus_stats = {}

        # Augment with metrics collector data
        if self._metrics:
            try:
                snapshot.event_bus_stats.update({
                    "published_total": self._metrics.get_gauge("eni_events_published_total") or 0,
                    "delivered_total": self._metrics.get_gauge("eni_events_delivered_total") or 0,
                    "failed_total": self._metrics.get_gauge("eni_events_failed_total") or 0,
                    "active_subscriptions": self._metrics.get_gauge(
                        "eni_events_active_subscriptions"
                    ) or 0,
                    "dead_letter_count": self._metrics.get_gauge(
                        "eni_events_dead_letter_count"
                    ) or 0,
                })
            except Exception:
                pass

    def _collect_alert_summary(self, snapshot: DashboardSnapshot) -> None:
        """Collect alert summaries from AlertManager."""
        if self._alert_manager:
            try:
                summary = self._alert_manager.get_summary()
                snapshot.alerts_active = summary.get("active_count", 0)
                snapshot.alerts_by_severity = summary.get("by_severity", {})

                # Recent alerts (last 10)
                history = self._alert_manager.get_alert_history(limit=10)
                snapshot.alerts_recent = [
                    {
                        "alert_id": a.alert_id,
                        "rule_name": a.rule_name,
                        "severity": a.severity.label(),
                        "state": a.state.value,
                        "module": a.module,
                        "message": a.message,
                        "created_at": a.created_at.isoformat(),
                    }
                    for a in history
                ]
            except Exception:
                pass

    def _collect_service_mesh(self, snapshot: DashboardSnapshot) -> None:
        """Collect service mesh status."""
        if self._metrics:
            try:
                # Circuit breakers
                for service in ("api-gateway", "event-hub", "swarm-turbocharger", "free-router"):
                    state_val = self._metrics.get_gauge(
                        "eni_circuit_breaker_state",
                        {"service": service},
                    )
                    state_map = {0: "closed", 1: "open", 2: "half_open"}
                    snapshot.circuit_breakers[service] = state_map.get(int(state_val), "unknown")

                # Service instances
                for svc in ("gateway", "event_hub", "swarm"):
                    count = self._metrics.get_gauge(
                        "eni_service_instances_healthy",
                        {"service_name": svc},
                    )
                    snapshot.service_instances[svc] = int(count) if count else 0
            except Exception:
                pass

    def _collect_resources(self, snapshot: DashboardSnapshot) -> None:
        """Collect system resource metrics."""
        try:
            import os
            # CPU
            try:
                import psutil  # type: ignore
                snapshot.cpu_percent = psutil.cpu_percent(interval=0)
            except ImportError:
                pass

            if self._metrics:
                cpu = self._metrics.get_gauge("eni_system_cpu_percent")
                if cpu:
                    snapshot.cpu_percent = cpu

            # Memory (from psutil or metrics)
            if snapshot.memory_total_bytes == 0.0:
                try:
                    import psutil
                    mem = psutil.virtual_memory()
                    snapshot.memory_used_bytes = mem.used
                    snapshot.memory_total_bytes = mem.total
                except ImportError:
                    pass

            if self._metrics:
                mem_used = self._metrics.get_gauge("eni_system_memory_bytes", {"type": "used"})
                if mem_used:
                    snapshot.memory_used_bytes = mem_used
                mem_total = self._metrics.get_gauge("eni_system_memory_bytes", {"type": "total"})
                if mem_total:
                    snapshot.memory_total_bytes = mem_total

        except Exception:
            pass

    def _collect_swarm_health(self, snapshot: DashboardSnapshot) -> None:
        """Collect swarm turbocharger health metrics."""
        if self._metrics:
            try:
                signal = self._metrics.get_gauge("eni_swarm_wifi_signal_dbm")
                if signal:
                    snapshot.wifi_signal_dbm = signal

                agents = self._metrics.get_gauge("eni_swarm_active_agents")
                if agents:
                    snapshot.swarm_active_agents = int(agents)

                limit = self._metrics.get_gauge("eni_swarm_concurrency_limit")
                if limit:
                    snapshot.swarm_concurrency_limit = int(limit)

                rps = self._metrics.get_gauge("eni_swarm_sustained_requests_per_sec")
                if rps:
                    snapshot.swarm_sustained_rps = rps
            except Exception:
                pass

        # Determine swarm status
        if snapshot.wifi_signal_dbm == 0.0:
            snapshot.swarm_status = "unknown"
            snapshot.swarm_color = HealthColor.GRAY
        elif snapshot.wifi_signal_dbm <= -80:
            snapshot.swarm_status = "critical"
            snapshot.swarm_color = HealthColor.RED
        elif snapshot.wifi_signal_dbm <= -70:
            snapshot.swarm_status = "degraded"
            snapshot.swarm_color = HealthColor.YELLOW
        elif snapshot.wifi_signal_dbm <= -60:
            snapshot.swarm_status = "fair"
            snapshot.swarm_color = HealthColor.BLUE
        else:
            snapshot.swarm_status = "good"
            snapshot.swarm_color = HealthColor.GREEN

    # ── History & Query ──────────────────────────────────────────────────────

    def get_latest_snapshot(self) -> Optional[DashboardSnapshot]:
        """Get the most recent snapshot."""
        with self._lock:
            if self._snapshot_history:
                return self._snapshot_history[-1]
        return None

    def get_snapshot_history(self, limit: int = 50) -> List[DashboardSnapshot]:
        """Get recent snapshots."""
        with self._lock:
            return self._snapshot_history[-limit:]

    def get_module_card(self, module_name: str) -> Optional[ModuleHealthCard]:
        """Get the latest health card for a specific module."""
        snapshot = self.get_latest_snapshot()
        if snapshot is None:
            return None
        for card in snapshot.modules:
            if card.module_name == module_name:
                return card
        return None

    def get_endpoint_summary(self) -> Dict[str, Any]:
        """Get a high-level endpoint health summary."""
        snapshot = self.get_latest_snapshot()
        if snapshot is None:
            return {"endpoint_count": 71, "healthy": 0, "degraded": 0, "unhealthy": 0}

        healthy = sum(1 for e in snapshot.endpoints if e.status == "healthy")
        degraded = sum(1 for e in snapshot.endpoints if e.status == "degraded")
        unhealthy = sum(1 for e in snapshot.endpoints if e.status == "unhealthy")

        return {
            "endpoint_count": snapshot.endpoint_count,
            "healthy": healthy,
            "degraded": degraded,
            "unhealthy": unhealthy,
            "router_groups": {
                k: {
                    "status": v.status,
                    "requests_total": v.requests_total,
                    "avg_latency_ms": v.avg_latency_ms,
                }
                for k, v in snapshot.router_groups.items()
            },
        }

    def get_summary(self) -> Dict[str, Any]:
        """Get a concise platform health summary."""
        snapshot = self.get_latest_snapshot()
        if snapshot is None:
            return {
                "status": "unknown",
                "modules_healthy": 0,
                "modules_total": 20,
                "alerts_active": 0,
                "endpoints_healthy": 0,
                "endpoints_total": 71,
            }

        return {
            "status": snapshot.platform_status.value,
            "state": snapshot.platform_state,
            "uptime_seconds": snapshot.uptime_seconds,
            "modules": {
                "total": snapshot.module_count,
                "healthy": snapshot.modules_healthy,
                "degraded": snapshot.modules_degraded,
                "unhealthy": snapshot.modules_unhealthy,
            },
            "endpoints": {
                "total": snapshot.endpoint_count,
                "healthy": sum(1 for e in snapshot.endpoints if e.status == "healthy"),
                "degraded": sum(1 for e in snapshot.endpoints if e.status == "degraded"),
            },
            "alerts_active": snapshot.alerts_active,
            "wifi_signal_dbm": snapshot.wifi_signal_dbm,
            "swarm_agents": snapshot.swarm_active_agents,
            "generation_time_ms": snapshot.generation_time_ms,
        }

    # ── Management ───────────────────────────────────────────────────────────

    def reset(self) -> None:
        """Reset dashboard history (useful for testing)."""
        with self._lock:
            self._snapshot_history.clear()
            self._generation_count = 0

    @property
    def generation_count(self) -> int:
        """Number of snapshots generated."""
        return self._generation_count